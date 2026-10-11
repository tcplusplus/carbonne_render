#!/usr/bin/env python3
"""T08: zet beelden bij ruisdrempel 0,10 / 0,05 / 0,03 / 0,02 naast elkaar om "visueel geconvergeerd" te kalibreren.
Gebruik: uv run python scripts/t08_drempels.py [--res 480] [--uit out/t08-drempels.png]"""

import argparse
from pathlib import Path

import numpy as np
from t08_convergentie import preset

from carbonne.render.pipeline import RenderOpties, render
from carbonne.render.uitvoer import png_bytes, tonemap_srgb

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--res", type=int, default=480)
    p.add_argument("--uit", type=Path, default=Path("out/t08-drempels.png"))
    a = p.parse_args()
    cfg = preset(a.res)
    delen = []
    for d in (0.10, 0.05, 0.03, 0.02):
        r = render(cfg, RenderOpties(ruisdrempel=d, cache=False, seed=7))
        print(f"drempel {d}: {r.spp} spp, {r.tijd_s:.1f} s, ruis {r.ruis:.4f}", flush=True)
        delen.append(tonemap_srgb(r.beeld))
    h, w = delen[0].shape[:2]
    # 2x2: elk beeld volledig, zodat de korreligheid op ware grootte te beoordelen is
    raster = np.concatenate([np.concatenate(delen[:2], axis=1), np.concatenate(delen[2:], axis=1)], axis=0)
    a.uit.parent.mkdir(parents=True, exist_ok=True)
    a.uit.write_bytes(png_bytes(raster))
