"""T24: dezelfde doorschijnende toplaag op witte, zwarte en rode grondlaag, met een ondoorzichtige toplaag als
controle. Zijkant, camera schuin boven, studio. Gebruik: `uv run python scripts/render_t24.py --out docs/evidence/img/T24-lagen.png`."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import mitsuba as mi
import numpy as np

from carbonne.core.config import CameraConfig, Paint, PaintStack, TableConfig
from carbonne.core.scene import build_scene
from carbonne.core.variant import select_variant

BLAUW = "#1f4fcc"
GRONDEN = {"wit": "#f2f2f2", "zwart": "#050505", "rood": "#b01010"}


def render(stapel: PaintStack, res: int, spp: int) -> np.ndarray:
    c = TableConfig(zijkant=stapel)
    c.scene.camera = CameraConfig(positie=(0.0, 0.2, 0.62), doel=(0.0, 0.0, 0.0), fov=38.0)
    c.scene.omgeving, c.scene.spot = "studio", True
    c.render.breedte, c.render.hoogte = res, res * 3 // 4
    img = mi.render(mi.load_dict(build_scene(c)), spp=spp)
    return np.array(mi.Bitmap(img).convert(mi.Bitmap.PixelFormat.RGB, mi.Struct.Type.Float32, srgb_gamma=False))


def mantel_gemiddelde(img: np.ndarray) -> list[float]:
    h, w, _ = img.shape  # onderste middenstuk van het beeld = de zijkant van de voorkant
    roi = img[int(h * 0.58):int(h * 0.68), int(w * 0.40):int(w * 0.60)]
    return [round(float(x), 4) for x in roi.reshape(-1, 3).mean(0)]


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--res", type=int, default=256)
    p.add_argument("--spp", type=int, default=256)
    p.add_argument("--out", type=Path, default=Path("out/T24-lagen.png"))
    p.add_argument("--json", type=Path, default=None)
    a = p.parse_args()
    select_variant()
    kolommen, metingen = [], {}
    for naam, g in GRONDEN.items():
        for dek in (0.5, 1.0):
            beeld = render(PaintStack(lagen=[Paint(color=g), Paint(color=BLAUW, dekking=dek)]), a.res, a.spp)
            kolommen.append((dek, beeld))
            metingen[f"{naam}_dekking{dek}"] = mantel_gemiddelde(beeld)
    rij1 = np.concatenate([b for d, b in kolommen if d == 0.5], axis=1)
    rij2 = np.concatenate([b for d, b in kolommen if d == 1.0], axis=1)
    raster = np.concatenate([rij1, rij2], axis=0).astype(np.float32)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    mi.Bitmap(raster).convert(mi.Bitmap.PixelFormat.RGB, mi.Struct.Type.UInt8, srgb_gamma=True).write(str(a.out))
    print(json.dumps(metingen, indent=1))
    if a.json:
        a.json.write_text(json.dumps(metingen, indent=1))


if __name__ == "__main__":
    main()
