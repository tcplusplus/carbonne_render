"""`carbonne-herkomst config.json --punt x,y`: render met de herkomst-integrator en teken een PNG met het beeld,
een kruisje op het punt en ernaast de balk met percentages, kleurstalen en kerngetallen (enkel getallen, geen tekst
uitleg). Bevat een klein 5x7-lettertype zodat er geen extra afhankelijkheid voor tekst nodig is."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

from carbonne.core.config import TableConfig
from carbonne.core.herkomst import (
    BRONNEN,
    N_CAT,
    Herkomst,
    categorie_beelden,
    herkomst_opties,
    herkomst_van,
)
from carbonne.render.pipeline import render
from carbonne.render.uitvoer import png_bytes, tonemap_srgb

_GLYPHS = {
    "A": ".###.|#...#|#...#|#####|#...#|#...#|#...#", "B": "####.|#...#|#...#|####.|#...#|#...#|####.",
    "C": ".###.|#...#|#....|#....|#....|#...#|.###.", "D": "####.|#...#|#...#|#...#|#...#|#...#|####.",
    "E": "#####|#....|#....|####.|#....|#....|#####", "F": "#####|#....|#....|####.|#....|#....|#....",
    "G": ".###.|#...#|#....|#.###|#...#|#...#|.###.", "H": "#...#|#...#|#...#|#####|#...#|#...#|#...#",
    "I": ".###.|..#..|..#..|..#..|..#..|..#..|.###.", "J": "..###|...#.|...#.|...#.|...#.|#..#.|.##..",
    "K": "#...#|#..#.|#.#..|##...|#.#..|#..#.|#...#", "L": "#....|#....|#....|#....|#....|#....|#####",
    "M": "#...#|##.##|#.#.#|#.#.#|#...#|#...#|#...#", "N": "#...#|##..#|#.#.#|#..##|#...#|#...#|#...#",
    "O": ".###.|#...#|#...#|#...#|#...#|#...#|.###.", "P": "####.|#...#|#...#|####.|#....|#....|#....",
    "Q": ".###.|#...#|#...#|#...#|#.#.#|#..#.|.##.#", "R": "####.|#...#|#...#|####.|#.#..|#..#.|#...#",
    "S": ".####|#....|#....|.###.|....#|....#|####.", "T": "#####|..#..|..#..|..#..|..#..|..#..|..#..",
    "U": "#...#|#...#|#...#|#...#|#...#|#...#|.###.", "V": "#...#|#...#|#...#|#...#|#...#|.#.#.|..#..",
    "W": "#...#|#...#|#...#|#.#.#|#.#.#|##.##|#...#", "X": "#...#|#...#|.#.#.|..#..|.#.#.|#...#|#...#",
    "Y": "#...#|#...#|.#.#.|..#..|..#..|..#..|..#..", "Z": "#####|....#|...#.|..#..|.#...|#....|#####",
    "0": ".###.|#...#|#..##|#.#.#|##..#|#...#|.###.", "1": "..#..|.##..|..#..|..#..|..#..|..#..|.###.",
    "2": ".###.|#...#|....#|...#.|..#..|.#...|#####", "3": "####.|....#|....#|.###.|....#|....#|####.",
    "4": "...#.|..##.|.#.#.|#..#.|#####|...#.|...#.", "5": "#####|#....|####.|....#|....#|#...#|.###.",
    "6": ".###.|#....|#....|####.|#...#|#...#|.###.", "7": "#####|....#|...#.|..#..|.#...|.#...|.#...",
    "8": ".###.|#...#|#...#|.###.|#...#|#...#|.###.", "9": ".###.|#...#|#...#|.####|....#|....#|.###.",
    ".": ".....|.....|.....|.....|.....|.##..|.##..", "%": "##..#|##..#|...#.|..#..|.#...|#..##|#..##",
    "+": ".....|..#..|..#..|#####|..#..|..#..|.....", "-": ".....|.....|.....|#####|.....|.....|.....",
    "/": "....#|....#|...#.|..#..|.#...|#....|#....", ":": ".....|.##..|.##..|.....|.##..|.##..|.....",
    ",": ".....|.....|.....|.....|.##..|..#..|.#...", " ": ".....|.....|.....|.....|.....|.....|.....",
    "*": ".....|#.#.#|.###.|#####|.###.|#.#.#|.....", "=": ".....|.....|#####|.....|#####|.....|.....",
}
_FONT = {k: np.array([[c == "#" for c in rij] for rij in v.split("|")]) for k, v in _GLYPHS.items()}


def tekst(img: np.ndarray, x: int, y: int, s: str, kleur=(255, 255, 255), schaal: int = 2) -> int:
    """Teken hoofdletters/cijfers in `img` (h, w, 3 uint8) vanaf (x, y); geeft de x achter de tekst terug."""
    for ch in s.upper():
        g = _FONT.get(ch, _FONT[" "])
        blok = np.kron(g, np.ones((schaal, schaal), bool))
        h, w = blok.shape
        y1, x1 = min(y + h, img.shape[0]), min(x + w, img.shape[1])
        if y1 > y and x1 > x:
            sub = img[y:y1, x:x1]
            sub[blok[: y1 - y, : x1 - x]] = kleur
        x += (5 + 1) * schaal
    return x


def staal_rgb8(rgb) -> tuple[int, int, int]:
    """sRGB-weergavekleur van een lineaire RGB (normaal 0..1; hoger wordt afgekapt)."""
    return tuple(int(v) for v in tonemap_srgb(np.asarray(rgb, float).reshape(1, 1, 3))[0, 0])


def kruisje(img: np.ndarray, x: int, y: int, r: int = 6) -> None:
    for kleur, d in (((0, 0, 0), 1), ((255, 255, 255), 0)):
        img[max(y - r, 0) : y + r + 1, max(x - d, 0) : x + d + 1] = kleur
        img[max(y - d, 0) : y + d + 1, max(x - r, 0) : x + r + 1] = kleur


def bron_beelden(beeld: np.ndarray) -> dict[str, np.ndarray]:
    """Per bron een lineair RGB-deelbeeld: de som van alle categorieen waarin die bron voorkomt (een pad met
    zijkant en onderkant telt dus in beide), plus `glans/omgeving` (categorie 0) en `som` (de gewone render)."""
    cats = categorie_beelden(beeld)
    uit = {"glans/omgeving": cats[:, :, 0]}
    for i, naam in enumerate(BRONNEN):
        uit[naam] = cats[:, :, [k for k in range(N_CAT) if k >> i & 1]].sum(axis=2)
    uit["som"] = cats.sum(axis=2)
    return uit


def paneel(h: Herkomst, hoogte: int, breedte: int = 330, titel: str = "") -> np.ndarray:
    """Het cijferpaneel: gestapelde balk, rijen met staal en percentage, en de kerngetallen."""
    p = np.full((hoogte, breedte, 3), 24, np.uint8)
    y = 6
    if titel:
        tekst(p, 8, y, titel, schaal=2)
        y += 20
    # gestapelde balk
    x0, x1 = 8, breedte - 8
    kleuren = [staal_rgb8(c.rgb_per_pad) for c in h.categorieen]
    pos = x0
    for c, kl in zip(h.categorieen, kleuren, strict=True):
        w = round((x1 - x0) * c.aandeel_pct / 100.0)
        p[y : y + 22, pos : pos + w] = kl
        pos += w
    p[y : y + 22, pos:x1] = kleuren[-1] if kleuren else 24
    y += 32
    for c, kl in zip(h.categorieen, kleuren, strict=True):
        p[y : y + 16, 8:30] = kl
        x = tekst(p, 38, y + 1, f"{c.aandeel_pct:5.1f}%", schaal=2)
        tekst(p, x + 8, y + 1, c.naam, schaal=2)
        y += 22
    y += 8
    k = h.kerngetallen
    for naam, waarde in (
        ("TIR PER PAD", f"{k.n_tir:.2f}"), ("FRESNEL PER PAD", f"{k.n_fresnel:.2f}"),
        ("PADEN MET TIR", f"{k.aandeel_tir_pct:.1f}%"), ("WEG IN EPOXY", f"{k.weg_epoxy_cm:.1f} CM"),
        ("L*A*B* TOTAAL", " ".join(f"{v:.0f}" for v in h.lab)),
    ):
        x = tekst(p, 8, y, naam, (170, 170, 170), schaal=1)
        tekst(p, max(x + 6, 150), y, waarde, schaal=1)
        y += 12
    return p


def paneel_png(beeld: np.ndarray, punt: tuple[int, int], straal: float = 2.0, ev: float = 0.0) -> tuple[bytes, Herkomst]:
    """Render + kruisje + cijferpaneel als PNG-bytes."""
    h = herkomst_van(beeld, punt, straal)
    rgb = tonemap_srgb(beeld[..., :3], ev).copy()
    kruisje(rgb, *punt)
    pan = paneel(h, rgb.shape[0])
    return png_bytes(np.concatenate([rgb, pan], axis=1)), h


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="carbonne-herkomst", description=__doc__)
    ap.add_argument("config", type=Path)
    ap.add_argument("--punt", required=True, help="x,y in pixels van het beeld")
    ap.add_argument("--straal", type=float, default=2.0, help="straal van het gebied rond het punt, pixels")
    ap.add_argument("-o", "--uit", type=Path, default=Path("out/herkomst.png"))
    ap.add_argument("--max-spp", type=int, default=256)
    ap.add_argument("--ruisdrempel", type=float, default=0.02)
    ap.add_argument("--tijdslimiet", type=float, default=None)
    ap.add_argument("--ev", type=float, default=0.0)
    ap.add_argument("--json", action="store_true", help="schrijf de getallen ook als JSON naast de PNG")
    a = ap.parse_args(argv)

    config = TableConfig.model_validate(json.loads(a.config.read_text()))
    x, y = (int(float(v)) for v in a.punt.split(","))
    r = render(config, herkomst_opties(config, max_spp=a.max_spp, ruisdrempel=a.ruisdrempel,
                                       tijdslimiet_s=a.tijdslimiet, ev=a.ev))
    png, h = paneel_png(r.beeld, (x, y), a.straal, a.ev)
    a.uit.parent.mkdir(parents=True, exist_ok=True)
    a.uit.write_bytes(png)
    if a.json:
        from dataclasses import asdict

        a.uit.with_suffix(".json").write_text(json.dumps(asdict(h), indent=1, default=float))
    for c in h.categorieen:
        print(f"{c.aandeel_pct:6.1f} %  {c.naam}", file=sys.stdout)
    print(f"{a.uit}  spp {r.spp}  ruis {r.ruis}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
