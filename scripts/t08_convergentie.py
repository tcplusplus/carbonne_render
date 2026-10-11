#!/usr/bin/env python3
"""T08: convergentiecurve (ruisschatting en werkelijke fout tegenover samples/tijd) en eindbeeld voor een preset.

Preset: rode zijkant, witte geverfde onderkant, houtschijfjes en bloemen in een laag, omgeving `woonkamer`, camera
`schuin30`. De werkelijke fout is de relatieve RMS-afwijking (zelfde maat als de ruisschatting) tegenover een
onafhankelijke referentie met veel samples en een ander zaad.

Gebruik: uv run python scripts/t08_convergentie.py [--res 320] [--max-spp 2048] [--ref-spp 8192] [--uit docs/evidence/img]
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import mitsuba as mi
import numpy as np

from carbonne.core.config import Flower, Layer, Paint, TableConfig, WoodSlice
from carbonne.core.scene import build_scene
from carbonne.core.variant import select_variant
from carbonne.render.pipeline import MIN_PASSES, ZWART_OFFSET, ruis_schatting
from carbonne.render.uitvoer import png_van_lineair


def preset(breedte: int) -> TableConfig:
    c = TableConfig(
        diameter=0.35,
        zijkant=Paint(color=(0.75, 0.04, 0.04)),
        onderkant=Paint(color=(0.9, 0.9, 0.9)),
        layers=[Layer(height_m=0.02, seed=4, items=[WoodSlice(count=4), Flower(count=3)])],
    )
    c.scene.omgeving, c.scene.camera_preset = "woonkamer", "schuin30"
    c.render.breedte, c.render.hoogte = breedte, breedte * 9 // 16
    return c


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--res", type=int, default=320)
    p.add_argument("--max-spp", type=int, default=2048)
    p.add_argument("--ref-spp", type=int, default=8192)
    p.add_argument("--depth", type=int, default=32)
    p.add_argument("--uit", type=Path, default=Path("out"))
    a = p.parse_args()
    select_variant()
    cfg = preset(a.res)
    cfg.render.max_depth = a.depth
    scene = mi.load_dict(build_scene(cfg))

    t0 = time.perf_counter()
    ref = np.array(mi.render(scene, spp=a.ref_spp, seed=999), dtype=np.float64)
    print(f"referentie {a.ref_spp} spp: {time.perf_counter() - t0:.1f} s", flush=True)

    stap, som, n, rijen = 16, [None, None], [0, 0], []
    t0 = time.perf_counter()
    nr = spp = 0
    while spp < a.max_spp:
        img = np.array(mi.render(scene, spp=stap, seed=100003 + nr), dtype=np.float64)
        h = nr % 2
        som[h] = img * stap if som[h] is None else som[h] + img * stap
        n[h] += stap
        spp += stap
        nr += 1
        tijd = time.perf_counter() - t0
        if nr >= MIN_PASSES:
            gem = (som[0] + som[1]) / spp
            echt = float(np.sqrt(np.mean(((gem - ref)[..., :3] / (ref[..., :3] + ZWART_OFFSET)) ** 2)))
            rijen.append({"spp": spp, "tijd_s": round(tijd, 3), "schatting": ruis_schatting(som[0], n[0], som[1], n[1]), "echt": echt})
    a.uit.mkdir(parents=True, exist_ok=True)
    (a.uit / "t08-curve.json").write_text(json.dumps(rijen, indent=1))
    for r in rijen[:: max(1, len(rijen) // 12)]:
        print(r)
    gem = (som[0] + som[1]) / spp
    (a.uit / "t08-eind.png").write_bytes(png_van_lineair(gem))
    for drempel in (0.05, 0.03, 0.02, 0.01):
        hit = next((r for r in rijen if r["schatting"] <= drempel), None)
        print(f"drempel {drempel}: ", hit)


if __name__ == "__main__":
    main()
