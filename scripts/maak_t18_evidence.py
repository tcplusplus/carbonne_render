"""T18 bewijsbeeld: GU tegenover GGX-alpha (gemeten tabel + controlemetingen) en vijf voorbeeldverven als zijkantstaal.
Gebruik: `uv run python scripts/maak_t18_evidence.py [--res 256 --spp 512]` -> docs/evidence/img/T18-glans.png"""

from __future__ import annotations

import argparse
from pathlib import Path

import mitsuba as mi
import numpy as np

from carbonne.core import glansmeter as g
from carbonne.core.config import CameraConfig, TableConfig
from carbonne.core.herkomst_cli import tekst
from carbonne.core.scene import build_scene
from carbonne.core.variant import select_variant
from carbonne.core.verf import GLANS_TERMEN, VerfEigenschappen, glans_tabel, vertaal_verf

VOORBEELDEN = {
    "MAT ZWART": dict(hex="#141414", glansgraad="mat"),
    "ZIJDEGLANS WIT": dict(hex="#f0f0ea", glansgraad="zijdeglans"),
    "HOOGGLANS ROOD": dict(kleurcode="RAL 3020", glansgraad="hoogglans"),
    "METALLIC GOUD": dict(hex="#d4af37", effect="metallic", glans_gu_60=45),
    "CANDY BLAUW": dict(hex="#1f5fd1", effect="candy", glans_gu_60=85),
}
BANDEN = [(0, 10, (40, 40, 40)), (10, 35, (52, 46, 40)), (35, 70, (40, 52, 46)), (70, 85, (40, 46, 56)), (85, 100, (56, 44, 56))]


def render(paint, res: int, spp: int) -> np.ndarray:
    c = TableConfig(diameter=0.35, hoogte=0.04)
    c.zijkant = paint
    c.scene.camera = CameraConfig(positie=(0.0, 0.2, 0.62), doel=(0.0, 0.0, 0.0), fov=38.0)
    c.scene.omgeving, c.scene.spot = "studio", True
    c.render.breedte, c.render.hoogte, c.render.spp = res, res * 3 // 4, spp
    img = mi.render(mi.load_dict(build_scene(c)), spp=spp)
    b = mi.Bitmap(img).convert(mi.Bitmap.PixelFormat.RGB, mi.Struct.Type.UInt8, srgb_gamma=True)
    return np.array(b)


def grafiek(controle: list[tuple[float, float]], breed=640, hoog=360) -> np.ndarray:
    t = glans_tabel()
    p = np.full((hoog, breed, 3), (24, 24, 24), np.uint8)
    x0, x1, y0, y1 = 60, breed - 14, 34, hoog - 40
    xmin, xmax = np.log10(0.002), 0.0
    px = lambda a: int(x0 + (np.log10(a) - xmin) / (xmax - xmin) * (x1 - x0))
    py = lambda gu: int(y1 - gu / 100 * (y1 - y0))
    for lo, hi, kl in BANDEN:
        p[py(hi) : py(lo), x0:x1] = kl
    for naam, (lo, hi) in GLANS_TERMEN.items():
        tekst(p, x0 + 4, py(hi) + 3, naam.upper(), (150, 150, 150), schaal=1)
    p[y0:y1, x0] = (140, 140, 140)
    p[y1, x0:x1] = (140, 140, 140)
    for gu in (0, 20, 40, 60, 80, 100):
        tekst(p, 30, py(gu) - 3, str(gu), (170, 170, 170), schaal=1)
    for a in (0.002, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1.0):
        p[y1 : y1 + 4, px(a)] = (140, 140, 140)
        tekst(p, px(a) - 3 * len(f"{a:g}"), y1 + 8, f"{a:g}", (170, 170, 170), schaal=1)
    tekst(p, 8, 8, "GLANS (GU BIJ 60 GRADEN, GESIMULEERD) TEGENOVER GGX-ALPHA, GLOSSY BUITENKANT", schaal=1)
    tekst(p, x0, hoog - 14, "GGX-ALPHA (LOG)", (170, 170, 170), schaal=1)
    pts = [(px(a), py(gu)) for a, gu in zip(t["alpha"], t["gu"], strict=True)]
    for (xa, ya), (xb, yb) in zip(pts, pts[1:], strict=False):
        for s in np.linspace(0, 1, 60):
            p[int(ya + s * (yb - ya)), int(xa + s * (xb - xa))] = (230, 120, 60)
    for a, gu in controle:
        xx, yy = px(a), py(gu)
        p[yy - 3 : yy + 4, xx - 3 : xx + 4] = (90, 170, 230)
    tekst(p, x1 - 230, y0 + 4, "ORANJE = TABEL  BLAUW = CONTROLE", schaal=1)
    return p


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--res", type=int, default=256)
    ap.add_argument("--spp", type=int, default=512)
    ap.add_argument("--out", type=Path, default=Path("docs/evidence/img/T18-glans.png"))
    a = ap.parse_args()
    select_variant()
    ref = g.meet_gu({"type": "dielectric", "int_ior": g.N_REFERENTIE, "ext_ior": 1.000277}, n=2_000_000)
    controle = [(al, g.meet_gu(g.glossy_buitenkant(al), n=2_000_000, zaad=7)) for al in (0.005, 0.015, 0.04, 0.1, 0.25, 0.6)]
    print("referentie zwart glas n=1,567:", round(ref, 2), "GU (moet 100 +- 2)")
    print("controle (alpha, GU):", [(al, round(gu, 2)) for al, gu in controle])
    plot = grafiek(controle)
    stalen = []
    for naam, kw in VOORBEELDEN.items():
        v = vertaal_verf(VerfEigenschappen(**kw))
        print(naam, v.paint.kind, v.paint.roughness, v.waarschuwingen)
        stalen.append(render(v.paint, a.res, a.spp))
    rij = np.concatenate(stalen, axis=1)
    breed = max(rij.shape[1], plot.shape[1])
    uit = np.full((plot.shape[0] + rij.shape[0] + 16, breed, 3), (24, 24, 24), np.uint8)
    uit[: plot.shape[0], : plot.shape[1]] = plot
    uit[plot.shape[0] + 16 :, : rij.shape[1]] = rij
    for i, naam in enumerate(VOORBEELDEN):
        tekst(uit, i * a.res + 6, plot.shape[0] + 20, naam, (255, 255, 255), schaal=1)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    mi.Bitmap(uit).write(str(a.out))
    print("->", a.out, uit.shape)


if __name__ == "__main__":
    main()
