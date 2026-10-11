"""T12: kalibratie aangetoond met een synthetische foto (render van een 'echt' tafeltje met een bekende kleurafwijking).

Draai: `uv run python scripts/render_t12.py [--spp 256]`. Schrijft docs/evidence/img/T12-*.png en
docs/evidence/T12-metingen.json."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from carbonne.core.config import Paint, RenderSettings, SceneConfig, TableConfig
from carbonne.kalibratie import kern
from carbonne.kalibratie.cli import kalibreer, render_lineair, zet_verfkleur

WAARHEID = "#8a2a1c"  # de echte verf (bakstenenrood)
MODEL = "RAL 3020"  # wat de gebruiker zou invullen (verkeersrood, veel te fel)
PAPIER_FOTO = (255, 195, 310, 232)
STAAL_FOTO = (8, 8, 48, 40)
ZIJKANT = (110, 168, 210, 182)
PLAN = {"papier_albedo": 0.85, "papier_foto": PAPIER_FOTO, "papier_render": PAPIER_FOTO,
        "staal": [{"verf": "zijkant", "foto": STAAL_FOTO}],
        "gebieden": [{"naam": "zijkant", "foto": ZIJKANT, "render": ZIJKANT, "verf": "zijkant"},
                     {"naam": "vloer", "foto": (20, 205, 80, 235), "render": (20, 205, 80, 235)}]}


def basis_config() -> TableConfig:
    return TableConfig(zijkant=Paint(color=MODEL, kind="matte"), onderkant=Paint(color="#dddddd", kind="matte"),
                       scene=SceneConfig(camera_preset="schuin30"), render=RenderSettings(breedte=320, hoogte=240))


def maak_foto(spp: int, versterking, ev: float, s_curve: float) -> tuple[np.ndarray, np.ndarray]:
    """Nep-gsmfoto van het echte tafeltje (verf WAARHEID). Geeft (lineaire foto zoals de gsm hem opslaat, 8 bit)."""
    echt = zet_verfkleur(basis_config(), "zijkant", kern.parse_hex(WAARHEID))
    r = render_lineair(echt, 0.85, spp, 0.02)
    papier = kern.roi_gemiddelde(r, PAPIER_FOTO)
    vlak = {STAAL_FOTO: tuple(np.asarray(kern.parse_hex(WAARHEID)) * papier / 0.85)}  # staal onder hetzelfde licht
    img8 = kern.synthetische_foto(r, versterking, ev, s_curve, vlak)
    return kern.srgb_naar_lineair_arr(img8 / 255.0), img8


def hoofd(spp: int) -> dict:
    uit: dict = {}
    img = Path("docs/evidence/img")
    for naam, vers, ev, sc in (("lineair", (1.25, 1.0, 0.72), -1.0, 0.0), ("tonemapping", (1.25, 1.0, 0.72), -1.0, 0.35)):
        foto, img8 = maak_foto(spp, vers, ev, sc)
        cfg = basis_config()
        vorig = {**PLAN, "staal": []}
        voor = kalibreer(cfg, foto, vorig, spp)
        na = kalibreer(cfg, foto, PLAN, spp)
        # bijstellen: nieuwe render met de bijgestelde config, opnieuw vergelijken (geen staal meer)
        rb = render_lineair(na["config_bijgesteld"], 0.85, spp, 0.02)
        bij = kalibreer(na["config_bijgesteld"], foto, vorig, spp, render_lin=rb)
        uit[naam] = {
            "versterking": vers, "ev": ev, "s_curve": sc, "waarheid": WAARHEID, "gemeten": na["gemeten"]["zijkant"]["hex"],
            "model": MODEL,
            "de_voor": {v.naam: round(v.de2000, 2) for v in voor["verschillen"]},
            "de_na_meting": {v.naam: round(v.de2000, 2) for v in na["verschillen"]},
            "de_na_bijstellen": {v.naam: round(v.de2000, 2) for v in bij["verschillen"]},
            "bijgesteld_hex": kern.rgb_naar_hex(na["config_bijgesteld"].zijkant.color),
            "dL_dC_dh_voor": [round(voor["verschillen"][0].d_l, 1), round(voor["verschillen"][0].d_c, 1),
                              round(voor["verschillen"][0].d_h, 1)],
        }
        if naam == "lineair":
            (img / "T12-foto-synthetisch.png").write_bytes(kern.foto_naar_png(img8))
            for kop, res in (("voor", voor), ("na", na)):
                b = kern.vergelijkingsbeeld(res["foto_norm"], res["render_norm"], PLAN["gebieden"], res["verschillen"])
                (img / f"T12-vergelijking-{kop}.png").write_bytes(kern.foto_naar_png(b))
            (img / "T12-vergelijking.png").write_bytes(
                kern.foto_naar_png(np.concatenate([_lees(img / "T12-vergelijking-voor.png"),
                                                   _lees(img / "T12-vergelijking-na.png")], axis=0)))
    Path("docs/evidence/T12-metingen.json").write_text(json.dumps(uit, indent=1, default=str))
    return uit


def _lees(p: Path) -> np.ndarray:
    return (kern.lineair_naar_srgb_arr(kern.laad_foto(p)) * 255).round().astype(np.uint8)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--spp", type=int, default=256)
    print(json.dumps(hoofd(ap.parse_args().spp), indent=1, default=str))
