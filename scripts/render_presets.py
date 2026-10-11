#!/usr/bin/env python3
"""Render hetzelfde tafeltje in elke omgeving (rij 1) en in elke camerapreset (rij 2) naar een overzichtsbeeld.

Volgorde rij 1: woonkamer, studio, avond, bewolkt, spot. Rij 2 (omgeving woonkamer): boven, schuin30, schuin60,
zittend, staand. Gebruik: `uv run python scripts/render_presets.py --out docs/evidence/img/T07-presets.png`.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import mitsuba as mi
import numpy as np

from carbonne.core.config import TableConfig
from carbonne.core.environments import CAMERA_PRESETS, OMGEVINGEN
from carbonne.core.scene import build_scene
from carbonne.core.variant import select_variant


def render(omgeving: str, cam: str, breedte: int, spp: int, spot: bool = False) -> np.ndarray:
    c = TableConfig(diameter=0.5)
    c.render.breedte, c.render.hoogte, c.render.spp = breedte, breedte * 3 // 4, spp
    c.scene.omgeving, c.scene.camera_preset, c.scene.spot = omgeving, cam, spot
    img = mi.render(mi.load_dict(build_scene(c)), spp=spp)
    return np.array(mi.Bitmap(img).convert(mi.Bitmap.PixelFormat.RGB, mi.Struct.Type.Float32, srgb_gamma=False))


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--res", type=int, default=320)
    p.add_argument("--spp", type=int, default=96)
    p.add_argument("--out", type=Path, default=Path("out/T07-presets.png"))
    a = p.parse_args()
    select_variant()
    rij1, rij2 = [], []
    t0 = time.time()
    for naam in OMGEVINGEN:
        rij1.append(render(naam, "schuin30", a.res, a.spp))
        print(f"{naam}: {time.time() - t0:.1f} s")
    for cam in CAMERA_PRESETS:
        rij2.append(render("woonkamer", cam, a.res, a.spp))
        print(f"{cam}: {time.time() - t0:.1f} s")
    grid = np.concatenate([np.concatenate(r, axis=1) for r in (rij1, rij2)], axis=0)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    mi.Bitmap(grid.astype(np.float32)).convert(
        mi.Bitmap.PixelFormat.RGB, mi.Struct.Type.UInt8, srgb_gamma=True
    ).write(str(a.out))
    print("->", a.out)


if __name__ == "__main__":
    main()
