"""`carbonne-reeks config.json --param hoogte --waarden 0.02,0.03,0.04 --punt x,y`: wat-als-reeks."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from carbonne.analyse.reeks import reeks
from carbonne.analyse.uitvoer import schrijf_reeks
from carbonne.core.config import TableConfig


def parse_waarden(s: str) -> list:
    """`[...]` is een JSON-lijst (voor kleuren en objecten); anders komma-gescheiden, elk item als JSON of tekst
    (`#ff0000`, `RAL 3020`)."""
    s = s.strip()
    if s.startswith("["):
        return json.loads(s)
    uit = []
    for deel in s.split(","):
        deel = deel.strip()
        try:
            uit.append(json.loads(deel))
        except json.JSONDecodeError:
            uit.append(deel)
    return uit


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="carbonne-reeks", description=__doc__)
    ap.add_argument("config", type=Path)
    ap.add_argument("--param", required=True, help="parameterpad, bv. hoogte, zijkant.color, onderkant, scene.camera.fov")
    ap.add_argument("--waarden", required=True, help="0.02,0.03,0.04 of een JSON-lijst, bv. '[{\"type\":\"bare\"},{\"type\":\"clearcoat\"}]'")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--punt", help="x,y in pixels van het reeksbeeld")
    g.add_argument("--rechthoek", help="x0,y0,x1,y1 in pixels")
    ap.add_argument("--straal", type=float, default=2.0)
    ap.add_argument("--breedte", type=int, default=256, help="breedte van het reeksbeeld in pixels")
    ap.add_argument("--spp", type=int, default=512, help="totaal aantal samples per waarde (twee helften)")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--ev", type=float, default=0.0)
    ap.add_argument("--geen-cache", action="store_true")
    ap.add_argument("-o", "--uit", type=Path, default=Path("out/reeks"))
    ap.add_argument("--naam", default="reeks")
    a = ap.parse_args(argv)

    config = TableConfig.model_validate(json.loads(a.config.read_text()))
    gebied = tuple(float(v) for v in (a.punt or a.rechthoek).split(","))
    if a.punt and len(gebied) != 2 or a.rechthoek and len(gebied) != 4:
        ap.error("--punt is x,y en --rechthoek is x0,y0,x1,y1")
    try:
        res = reeks(config, a.param, parse_waarden(a.waarden), gebied, straal=a.straal, breedte=a.breedte, spp=a.spp,
                    seed=a.seed, ev=a.ev, cache=not a.geen_cache,
                    on_progress=lambda i, n, lab: print(f"[{i}/{n}] {lab}", file=sys.stderr))
    except ValueError as e:
        print(f"fout: {e}", file=sys.stderr)
        return 2
    pad = schrijf_reeks(res, a.uit, a.naam, a.ev)
    print(f"{'waarde':24} {'L*':>6} {'C*':>6} {'h':>5} {'dE2000':>7} {'ruis':>5}")
    for m in res.metingen:
        print(f"{m.label[:24]:24} {m.lch[0]:6.1f} {m.lch[1]:6.1f} {m.lch[2]:5.0f} {m.de2000:7.2f} {m.ruis_lab:5.2f}"
              + ("  binnen ruis" if m.binnen_ruis else ""))
    for p in pad.values():
        print(p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
