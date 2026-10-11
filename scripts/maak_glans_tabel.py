"""T18: meet de gesimuleerde glanswaarde (GU, ISO 2813 60 graden) van de buitenkant van `glossy` als functie van de
GGX-alpha en schrijf de tabel naar src/carbonne/data/glans_tabel.json. Gebruik: `uv run python scripts/maak_glans_tabel.py`."""

from __future__ import annotations

import json

import numpy as np

from carbonne.core import glansmeter as g
from carbonne.core.variant import select_variant
from carbonne.core.verf import GLANS_TABEL

ALPHAS = np.round(np.geomspace(0.002, 1.0, 40), 5)


def main() -> None:
    select_variant()
    gu = [round(float(np.mean([g.meet_gu(g.glossy_buitenkant(float(a)), n=2_000_000, zaad=z) for z in (1, 2)])), 3) for a in ALPHAS]
    ref = round(g.meet_gu({"type": "dielectric", "int_ior": g.N_REFERENTIE, "ext_ior": 1.000277}), 2)
    data = {
        "beschrijving": "GU (60 graden, ISO 2813, gesimuleerd) van de luchtkant van Paint(kind=glossy): roughplastic GGX, n=1,5",
        "referentie_zwart_glas_gu": ref,
        "venster_graden": [g.VENSTER_VLAK_DEG, g.VENSTER_LOODRECHT_DEG],
        "alpha": [float(a) for a in ALPHAS],
        "gu": gu,
    }
    GLANS_TABEL.write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")
    print(ref, list(zip(ALPHAS.tolist(), gu, strict=True)))


if __name__ == "__main__":
    main()
