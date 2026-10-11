"""`carbonne-render config.json -o out/`: render een TableConfig (JSON) en schrijf EXR + PNG."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from carbonne.core.config import TableConfig
from carbonne.render.pipeline import RenderOpties, Voortgang, render
from carbonne.render.uitvoer import schrijf_exr


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="carbonne-render", description=__doc__)
    p.add_argument("config", type=Path, help="JSON-bestand met een TableConfig")
    p.add_argument("-o", "--uit", type=Path, default=Path("out"))
    p.add_argument("--naam", default=None, help="basisnaam van de uitvoer (standaard: naam van de config)")
    p.add_argument("--ruisdrempel", type=float, default=None)
    p.add_argument("--max-spp", type=int, default=None)
    p.add_argument("--tijdslimiet", type=float, default=None, help="seconden")
    p.add_argument("--max-depth", type=int, default=None)
    p.add_argument("--integrator", default=None)
    p.add_argument("--seed", type=int, default=None)
    p.add_argument("--ev", type=float, default=None)
    p.add_argument("--preview", action="store_true")
    p.add_argument("--geen-cache", action="store_true")
    a = p.parse_args(argv)

    config = TableConfig.model_validate(json.loads(a.config.read_text()))
    keuze = {"ruisdrempel": a.ruisdrempel, "max_spp": a.max_spp, "tijdslimiet_s": a.tijdslimiet,
             "max_depth": a.max_depth, "integrator": a.integrator, "seed": a.seed, "ev": a.ev}
    opties = RenderOpties(**{k: v for k, v in keuze.items() if v is not None},
                          preview=a.preview, cache=not a.geen_cache)

    def voortgang(v: Voortgang) -> None:
        ruis = "-" if v.ruis is None else f"{v.ruis:.4f}"
        print(f"\rpass {v.pass_nr:3d}  spp {v.spp:5d}/{v.max_spp}  ruis {ruis}  {v.tijd_s:6.1f} s", end="", file=sys.stderr)
        if v.klaar:
            print(f"  -> {v.reden}", file=sys.stderr)

    r = render(config, opties, voortgang)
    naam = a.naam or a.config.stem
    a.uit.mkdir(parents=True, exist_ok=True)
    schrijf_exr(a.uit / f"{naam}.exr", r.beeld, r.kanaalnamen)
    (a.uit / f"{naam}.png").write_bytes(r.png)
    print(f"{a.uit / naam}.exr/.png  spp {r.spp}  ruis {r.ruis}  reden {r.reden}  sleutel {r.sleutel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
