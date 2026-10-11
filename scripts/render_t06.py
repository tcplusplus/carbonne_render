#!/usr/bin/env python3
"""T06: schijf met twee lagen inhoud (hout beneden, bloemen boven), schuin en van boven bekeken.

Gebruik: `uv run python scripts/render_t06.py --out docs/evidence/img/T06-lagen.png`.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import mitsuba as mi
import numpy as np

from carbonne.core.config import Flower, Layer, TableConfig, WoodSlice
from carbonne.core.scene import build_scene
from carbonne.core.variant import select_variant

CAMERAS = {
    "schuin": ((0.0, 0.3, 0.42), (0.0, 0.02, 0.0), 42.0),
    "boven": ((0.0, 0.55, 0.001), (0.0, 0.02, 0.0), 42.0),
}


def tafel(breedte: int, spp: int, cam: str, seed: int = 7, zijkant=None) -> TableConfig:
    c = TableConfig(
        diameter=0.35,
        hoogte=0.05,
        layers=[
            Layer(height_m=0.014, seed=seed, items=[WoodSlice(count=7, radius_mm=(9, 15), thickness_mm=3)]),
            Layer(
                height_m=0.036,
                seed=seed + 1,
                items=[
                    Flower(count=4, color=(0.92, 0.25, 0.4), petals=7, radius_mm=(12, 16)),
                    Flower(count=3, color=(1.0, 0.85, 0.15), petals=5, radius_mm=(10, 13)),
                    Flower(count=3, color=(0.95, 0.95, 0.98), petals=8, radius_mm=(11, 14)),
                ],
            ),
        ],
    )
    if zijkant is not None:
        c.zijkant = zijkant
    c.render.breedte, c.render.hoogte, c.render.spp, c.render.max_depth = breedte, breedte * 3 // 4, spp, 40
    c.scene.omgeving = "studio"
    c.scene.camera.positie, c.scene.camera.doel, c.scene.camera.fov = CAMERAS[cam]
    return c


def render(c: TableConfig) -> np.ndarray:
    img = mi.render(mi.load_dict(build_scene(c)), spp=c.render.spp)
    return np.array(mi.Bitmap(img).convert(mi.Bitmap.PixelFormat.RGB, mi.Struct.Type.Float32, srgb_gamma=False))


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--res", type=int, default=560)
    p.add_argument("--spp", type=int, default=512)
    p.add_argument("--out", type=Path, default=Path("out/T06-lagen.png"))
    a = p.parse_args()
    select_variant()
    t0 = time.time()
    beelden = [render(tafel(a.res, a.spp, cam)) for cam in ("schuin", "boven")]
    print(f"{time.time() - t0:.1f} s")
    grid = np.concatenate(beelden, axis=1)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    mi.Bitmap(grid.astype(np.float32)).convert(mi.Bitmap.PixelFormat.RGB, mi.Struct.Type.UInt8, srgb_gamma=True).write(str(a.out))
    print("->", a.out)


if __name__ == "__main__":
    main()
