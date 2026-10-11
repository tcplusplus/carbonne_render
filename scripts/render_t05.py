#!/usr/bin/env python3
"""T05: dezelfde kleur in vier verftypes. Rij 1: op de zijkant (camera schuin boven); rij 2: op een plaat onder het
blok (camera ooghoogte). Gebruik: `uv run python scripts/render_t05.py --out docs/evidence/img/T05-verftypes.png`.
Omgeving studio met spot (de glans van gloss/metallic vraagt om gerichte lichtbronnen)."""

from __future__ import annotations

import argparse
from pathlib import Path

import mitsuba as mi
import numpy as np

from carbonne.core.config import CameraConfig, Paint, PlateBelow, TableConfig
from carbonne.core.scene import build_scene
from carbonne.core.variant import select_variant

SOORTEN = ("matte", "glossy", "metallic", "candy")


def render(kind: str, plek: str, kleur: str, res: int, spp: int, candy_base: str = "metallic") -> np.ndarray:
    verf = dict(color=kleur, kind=kind, candy_base=candy_base)
    c = TableConfig(diameter=0.35, hoogte=0.04)
    if plek == "zijkant":
        c.zijkant = Paint(**verf)
        c.scene.camera = CameraConfig(positie=(0.0, 0.2, 0.62), doel=(0.0, 0.0, 0.0), fov=38.0)
    else:
        c.onderkant = PlateBelow(gap_mm=3.0, **verf)
        c.zijkant = Paint(**verf)
        c.scene.camera = CameraConfig(positie=(0.0, 0.09, 0.62), doel=(0.0, 0.0, 0.0), fov=38.0)
    c.scene.omgeving, c.scene.spot = "studio", True
    c.render.breedte, c.render.hoogte, c.render.spp = res, res * 3 // 4, spp
    img = mi.render(mi.load_dict(build_scene(c)), spp=spp)
    return np.array(mi.Bitmap(img).convert(mi.Bitmap.PixelFormat.RGB, mi.Struct.Type.Float32, srgb_gamma=False))


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--res", type=int, default=320)
    p.add_argument("--spp", type=int, default=128)
    p.add_argument("--kleur", default="RAL 3020")
    p.add_argument("--candy-base", default="metallic", choices=["metallic", "white"])
    p.add_argument("--schaal", type=float, default=1.0, help="verklein het eindbeeld (bestandsgrootte)")
    p.add_argument("--out", type=Path, default=Path("out/T05-verftypes.png"))
    a = p.parse_args()
    select_variant()
    rijen = [
        np.concatenate([render(k, plek, a.kleur, a.res, a.spp, a.candy_base) for k in SOORTEN], axis=1)
        for plek in ("zijkant", "plaat")
    ]
    a.out.parent.mkdir(parents=True, exist_ok=True)
    raster = mi.Bitmap(np.concatenate(rijen, axis=0).astype(np.float32))
    if a.schaal != 1.0:
        raster = raster.resample([int(raster.width() * a.schaal), int(raster.height() * a.schaal)])
    raster.convert(
        mi.Bitmap.PixelFormat.RGB, mi.Struct.Type.UInt8, srgb_gamma=True
    ).write(str(a.out))
    print("->", a.out)


if __name__ == "__main__":
    main()
