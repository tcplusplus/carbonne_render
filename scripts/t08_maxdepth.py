#!/usr/bin/env python3
"""T08: effect van `max_depth` op het A/B-beeld uit T04 (steile camera, witte omgeving, zwarte vloer).

Per variant en per diepte: luminantie in het ROI (midden van het bovenvlak), luminantie over het hele beeld en
rendertijd, met vaste samples en vaste zaden (gepaard: zelfde zaad voor elke diepte).
Gebruik: uv run python scripts/t08_maxdepth.py [--res 256] [--spp 512] [--out out/t08-maxdepth.json]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import mitsuba as mi
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import ab_experiment as ab

from carbonne.core.config import PlateBelow
from carbonne.core.scene import build_scene
from carbonne.core.variant import select_variant

DIEPTEN = (4, 8, 16, 32, 64, 128)
CODES = ("0", "W1", "W2", "WB1")
ZADEN = (3, 11)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--res", type=int, default=256)
    p.add_argument("--spp", type=int, default=512)
    p.add_argument("--out", type=Path, default=Path("out/t08-maxdepth.json"))
    a = p.parse_args()
    select_variant()
    rijen = []
    for code, omschr, z, o in ab.VARIANTEN:
        if code not in CODES:
            continue
        for d in DIEPTEN:
            cfg = ab.maak_config(z, o, a.res, a.spp)
            cfg.render.max_depth = d
            sd = build_scene(cfg)
            if not isinstance(o, PlateBelow):
                ab.vloer_omlaag(sd, cfg)
            scene = mi.load_dict(sd)
            t = time.perf_counter()
            imgs = [np.array(mi.render(scene, spp=a.spp, seed=s))[..., :3] for s in ZADEN]
            tijd = (time.perf_counter() - t) / len(ZADEN)
            lum_roi = [ab.luminantie(ab.roi(i)) for i in imgs]
            lum_rand = [ab.luminantie(ab.roi(i, 0.25)) for i in imgs]
            lum_all = [ab.luminantie(i.mean(axis=(0, 1))) for i in imgs]
            rijen.append({"code": code, "omschrijving": omschr, "max_depth": d, "tijd_s": round(tijd, 2),
                          "lum_roi": float(np.mean(lum_roi)), "lum_rand": float(np.mean(lum_rand)),
                          "lum_beeld": float(np.mean(lum_all)),
                          "ruis_roi": float(abs(lum_roi[0] - lum_roi[1]) / 2)})
            print(rijen[-1], flush=True)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(rijen, indent=1, ensure_ascii=False))
    for code in CODES:
        sel = [r for r in rijen if r["code"] == code]
        ref = sel[-1]
        print(f"\n{code}: {sel[0]['omschrijving']}")
        print("| max_depth | lum ROI | t.o.v. 128 | lum rand | t.o.v. 128 | lum beeld | t.o.v. 128 | ruis ROI | tijd |")
        print("|---|---|---|---|---|---|---|---|---|")
        for r in sel:
            print(f"| {r['max_depth']} | {r['lum_roi']:.4f} | {r['lum_roi'] / ref['lum_roi'] - 1:+.2%} | "
                  f"{r['lum_rand']:.4f} | {r['lum_rand'] / ref['lum_rand'] - 1:+.2%} | {r['lum_beeld']:.4f} | "
                  f"{r['lum_beeld'] / ref['lum_beeld'] - 1:+.2%} | {r['ruis_roi']:.4f} | {r['tijd_s']} s |")


if __name__ == "__main__":
    main()
