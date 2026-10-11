"""T13 evidence: herkomst van het midden van het blad voor (a) zwarte verf onderaan en (b) een zwarte plaat met
luchtspleet, met een rode zijkant. Schrijft docs/evidence/img/T13-herkomst.png en docs/evidence/T13-herkomst.json.

Gebruik: uv run python scripts/maak_t13_evidence.py [--res 480 --spp 512 --meet-res 160 --meet-spp 2048]"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

import numpy as np

from carbonne.core.config import Paint, PlateBelow, TableConfig
from carbonne.core.herkomst import herkomst_opties, herkomst_van
from carbonne.core.herkomst_cli import bron_beelden, kruisje, paneel, tekst
from carbonne.render.pipeline import render
from carbonne.render.uitvoer import png_bytes, tonemap_srgb

ZIJKANT = Paint(color=(0.75, 0.04, 0.04), kind="matte")
VARIANTEN = {
    "a_verf_zwart": ("(A) ZWARTE VERF ONDERAAN", Paint(color=(0.02, 0.02, 0.02))),
    "b_plaat_luchtspleet": ("(B) ZWARTE PLAAT, SPLEET 1 MM", PlateBelow(color=(0.02, 0.02, 0.02), gap_mm=1.0)),
}


def maak_config(onderkant, breedte: int) -> TableConfig:
    c = TableConfig(zijkant=ZIJKANT, onderkant=onderkant)
    c.render.breedte, c.render.hoogte = breedte, round(breedte * 9 / 16)
    c.scene.omgeving, c.scene.camera_preset = "studio", "schuin30"
    return c


PUNTEN = {"midden": (0.5, 0.5), "achterrand": (0.5, 1 / 3)}  # fractie van breedte/hoogte (camera schuin30)


def punt_px(r: np.ndarray, naam: str) -> tuple[int, int]:
    f = PUNTEN[naam]
    return round(f[0] * r.shape[1]), round(f[1] * r.shape[0])


def meet(beeld: np.ndarray) -> dict:
    uit = {}
    for naam in PUNTEN:
        h = herkomst_van(beeld, punt_px(beeld, naam), max(2.0, beeld.shape[1] / 100))
        uit[naam] = {"punt": punt_px(beeld, naam), **asdict(h)}
    return uit


def rij(titel: str, onderkant, breedte: int, spp: int, ev: float) -> tuple[np.ndarray, dict]:
    c = maak_config(onderkant, breedte)
    zaden = {}
    for zaad in (0, 1):
        r = render(c, herkomst_opties(c, max_spp=spp, ruisdrempel=1e-9, cache=False, spp_per_pass=32, seed=zaad))
        zaden[zaad] = r
    r = zaden[0]
    h_, b_ = r.beeld.shape[:2]
    rgb = tonemap_srgb(r.beeld[..., :3], ev).copy()
    for naam in PUNTEN:
        kruisje(rgb, *punt_px(r.beeld, naam), r=5)
    delen = bron_beelden(r.beeld)
    half = []
    for n in ("zijkant", "onderkant", "vloer", "glans/omgeving"):
        im = tonemap_srgb(delen[n], ev).copy()
        tekst(im, 4, 4, n, (255, 255, 0), schaal=1)
        k = im[::2, ::2]
        half.append(np.pad(k, ((0, h_ // 2 - k.shape[0]), (0, b_ // 2 - k.shape[1]), (0, 0))))
    raster = np.concatenate([np.concatenate(half[:2], axis=1), np.concatenate(half[2:], axis=1)], axis=0)
    metingen = {z: meet(rz.beeld) for z, rz in zaden.items()}
    panelen = [
        paneel(herkomst_van(r.beeld, punt_px(r.beeld, n), max(2.0, b_ / 100)), 236, 300, f"{titel[:3]} {n}")
        for n in PUNTEN
    ]
    hoog = max(h_, 236)

    def vul(a):
        return np.pad(a, ((0, hoog - a.shape[0]), (0, 0), (0, 0)))

    beeld = np.concatenate([vul(rgb), vul(raster), *[vul(p) for p in panelen]], axis=1)
    return beeld, {"titel": titel, "spp": r.spp, "ruis": [zaden[z].ruis for z in zaden], "tijd_s": r.tijd_s,
                   "zaden": metingen}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--res", type=int, default=256)
    ap.add_argument("--spp", type=int, default=1024)
    ap.add_argument("--bevestig-res", type=int, default=0, help="extra run op dit formaat (breedte); 0 = geen")
    ap.add_argument("--bevestig-spp", type=int, default=256)
    ap.add_argument("--ev", type=float, default=0.0)
    ap.add_argument("--uit", type=Path, default=Path("docs/evidence"))
    a = ap.parse_args()
    rijen, data = [], {}
    for naam, (titel, ond) in VARIANTEN.items():
        beeld, d = rij(titel, ond, a.res, a.spp, a.ev)
        if a.bevestig_res:
            c = maak_config(ond, a.bevestig_res)
            r = render(c, herkomst_opties(c, max_spp=a.bevestig_spp, ruisdrempel=1e-9, cache=False, spp_per_pass=16))
            d["bevestiging"] = {"res": a.bevestig_res, "spp": r.spp, "tijd_s": r.tijd_s, **meet(r.beeld)}
        rijen.append(beeld)
        data[naam] = d
    breed = max(r.shape[1] for r in rijen)
    rijen = [np.pad(r, ((0, 0), (0, breed - r.shape[1]), (0, 0))) for r in rijen]
    (a.uit / "img").mkdir(parents=True, exist_ok=True)
    (a.uit / "img" / "T13-herkomst.png").write_bytes(png_bytes(np.concatenate(rijen, axis=0)))
    (a.uit / "T13-herkomst.json").write_text(json.dumps(data, indent=1, default=float))


if __name__ == "__main__":
    main()
