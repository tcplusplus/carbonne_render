"""T14 evidence: twee wat-als-reeksen. (1) dikte 2-6 cm met rode zijkant en een zwarte plaat met luchtspleet;
(2) de onderkant als zwarte verf, matte lak en zwarte plaat. Schrijft docs/evidence/img/T14-*.png en
docs/evidence/T14-*.json.

Gebruik: uv run python scripts/maak_t14_evidence.py [--breedte 256 --spp 1024 --cache-map cache]"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from carbonne.analyse.reeks import reeks
from carbonne.analyse.uitvoer import schrijf_reeks
from carbonne.core.config import MatteClearCoat, Paint, PlateBelow, TableConfig

ZIJKANT = Paint(color=(0.75, 0.04, 0.04), kind="matte")
ZWART = (0.02, 0.02, 0.02)
UIT = Path("docs/evidence/img")


def basis(onderkant) -> TableConfig:
    c = TableConfig(zijkant=ZIJKANT, onderkant=onderkant)
    c.render.breedte, c.render.hoogte = 256, 144
    c.scene.omgeving, c.scene.camera_preset = "studio", "schuin30"
    return c


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--breedte", type=int, default=256)
    ap.add_argument("--spp", type=int, default=1024)
    ap.add_argument("--cache-map", type=Path, default=Path("cache"))
    a = ap.parse_args()
    b = a.breedte
    midden = (b // 2, round(b * 9 / 16) // 2)
    achter = (b // 2, round(b * 9 / 16 / 3))
    kw = {"breedte": b, "spp": a.spp, "cache_map": a.cache_map, "straal": max(2.0, b / 100)}
    runs = [
        ("T14-dikte", basis(PlateBelow(color=ZWART, gap_mm=1.0)), "hoogte", [0.02, 0.03, 0.04, 0.05, 0.06], midden),
        ("T14-dikte-achterrand", basis(PlateBelow(color=ZWART, gap_mm=1.0)), "hoogte", [0.02, 0.03, 0.04, 0.05, 0.06], achter),
        ("T14-onderkant", basis(Paint(color=ZWART)), "onderkant",
         [Paint(color=ZWART), MatteClearCoat(), PlateBelow(color=ZWART, gap_mm=1.0)], midden),
    ]
    for naam, cfg, param, waarden, punt in runs:
        t0 = time.perf_counter()
        res = reeks(cfg, param, waarden, punt, **kw, on_progress=lambda i, n, lab: print(f"  [{i}/{n}] {lab}"))
        schrijf_reeks(res, UIT, naam)
        (UIT / f"{naam}.json").replace(UIT.parent / f"{naam}.json")
        if naam != "T14-dikte":  # alleen de hoofdreeks als apart samengesteld beeld; de rest als contact + grafiek
            (UIT / f"{naam}.png").unlink()
        else:
            (UIT / f"{naam}-contact.png").unlink()
            (UIT / f"{naam}-grafiek.png").unlink()
        print(f"{naam}: {time.perf_counter() - t0:.0f} s, punt {punt}")
        for m in res.metingen:
            print(f"  {m.label:22} L {m.lch[0]:5.1f} C {m.lch[1]:5.1f} h {m.lch[2]:4.0f} dE {m.de2000:5.2f} "
                  f"ruis {m.ruis_lab:4.2f} {'(binnen ruis)' if m.binnen_ruis else ''}")


if __name__ == "__main__":
    main()
