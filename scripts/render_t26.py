"""T26: tafeltje met metalen poten. Raster: drie en vier poten (rijen) x schuin van boven en laag van onderen (kolommen),
en een tweede beeld met de drie metaalafwerkingen. Gebruik: `uv run python scripts/render_t26.py --res 320 --spp 256`."""

from __future__ import annotations

import argparse
from pathlib import Path

import mitsuba as mi
import numpy as np

from carbonne.core.config import CameraConfig, Legs, TableConfig
from carbonne.core.scene import build_scene
from carbonne.core.variant import select_variant

CAMERAS = {
    "boven": CameraConfig(positie=(0.0, 0.55, 0.75), doel=(0.0, -0.12, 0.0), fov=42.0),
    "onder": CameraConfig(positie=(0.0, -0.36, 0.7), doel=(0.0, -0.1, 0.0), fov=42.0),
}


def maak(aantal: int, cam: str, metaal: str = "gepoetst", vorm: str = "rond", res: int = 320, spp: int = 256, omgeving: str = "studio") -> np.ndarray:
    c = TableConfig(poten=Legs(aantal=aantal, metaal=metaal, vorm=vorm))
    c.scene.omgeving = omgeving
    c.scene.camera = CAMERAS[cam]
    c.render.breedte, c.render.hoogte = res, res * 3 // 4
    img = mi.render(mi.load_dict(build_scene(c)), spp=spp)
    return np.array(mi.Bitmap(img).convert(mi.Bitmap.PixelFormat.RGB, mi.Struct.Type.Float32, srgb_gamma=False))


def schrijf(rijen: list[list[np.ndarray]], pad: Path) -> None:
    raster = np.concatenate([np.concatenate(r, axis=1) for r in rijen], axis=0).astype(np.float32)
    pad.parent.mkdir(parents=True, exist_ok=True)
    mi.Bitmap(raster).convert(mi.Bitmap.PixelFormat.RGB, mi.Struct.Type.UInt8, srgb_gamma=True).write(str(pad))


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--res", type=int, default=320)
    p.add_argument("--spp", type=int, default=256)
    p.add_argument("--out", type=Path, default=Path("out/T26-poten.png"))
    p.add_argument("--metalen", type=Path, default=Path("out/T26-metalen.png"))
    a = p.parse_args()
    select_variant()
    schrijf([[maak(n, cam, res=a.res, spp=a.spp) for cam in ("boven", "onder")] for n in (3, 4)], a.out)
    schrijf([[maak(4, "onder", m, v, res=a.res, spp=a.spp) for m in ("geborsteld", "gepoetst", "zwart")] for v in ("rond", "vierkant")], a.metalen)


if __name__ == "__main__":
    main()
