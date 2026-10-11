"""Render het 2x3-raster van randafwerkingen (T03): `uv run carbonne-t03 --out docs/evidence/img/T03-raster.png`."""

from __future__ import annotations

import argparse
from pathlib import Path

import mitsuba as mi
import numpy as np

from carbonne.core.config import Bare, MatteClearCoat, Paint, PlateBelow, TableConfig
from carbonne.core.variant import select_variant

ROOD = (0.75, 0.04, 0.04)
WIT = (0.9, 0.9, 0.9)

# (titel, zijkant, onderkant), rij voor rij van linksboven naar rechtsonder
COMBINATIES = [
    ("1 zijkant onbehandeld / onder onbehandeld", Bare(), Bare()),
    ("2 zijkant rood / onder onbehandeld", Paint(color=ROOD), Bare()),
    ("3 zijkant rood / onder wit geverfd", Paint(color=ROOD), Paint(color=WIT)),
    ("4 zijkant rood / onder kleurloze matte lak", Paint(color=ROOD), MatteClearCoat()),
    ("5 zijkant rood / witte plaat, spleet 0,1 mm", Paint(color=ROOD), PlateBelow(color=WIT, gap_mm=0.1)),
    ("6 zijkant rood / onder rood geverfd", Paint(color=ROOD), Paint(color=ROOD)),
]


def render_combinatie(zijkant, onderkant, res: int, spp: int) -> np.ndarray:
    from carbonne.core.scene import build_scene

    cfg = TableConfig(zijkant=zijkant, onderkant=onderkant)
    cfg.render.breedte, cfg.render.hoogte, cfg.render.spp = res, res * 3 // 4, spp
    scene = mi.load_dict(build_scene(cfg))
    return np.array(mi.render(scene, spp=spp, seed=3))


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--res", type=int, default=320)
    p.add_argument("--spp", type=int, default=256)
    p.add_argument("--out", type=Path, default=Path("out/t03-raster.png"))
    a = p.parse_args()
    print("variant:", select_variant())
    beelden = []
    for titel, z, o in COMBINATIES:
        img = render_combinatie(z, o, a.res, a.spp)
        h, w = img.shape[:2]
        mid = img[int(h * 0.42) : int(h * 0.75), int(w * 0.35) : int(w * 0.65), :3].mean(axis=(0, 1))
        print(f"{titel}: beeldgemiddelde {img.mean():.4f}; midden-van-schijf R,G,B = {mid.round(3).tolist()}")
        beelden.append(img[..., :3])
    rijen = [np.concatenate(beelden[i : i + 3], axis=1) for i in (0, 3)]
    raster = np.concatenate(rijen, axis=0)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    mi.Bitmap(raster.astype(np.float32)).convert(
        mi.Bitmap.PixelFormat.RGB, mi.Struct.Type.UInt8, srgb_gamma=True
    ).write(str(a.out))
    print("->", a.out)


if __name__ == "__main__":
    main()
