"""Kleurinvoer: `#rrggbb` of `RAL 9005` -> lineair RGB (de basis van Mitsuba's `rgb`-waarde).

Let op, dit is een BENADERING. Hex- en RAL-waarden zijn sRGB-weergaven op een scherm. In spectrale modus zet
Mitsuba een RGB-waarde om naar een glad spectrum (spectral upsampling, Jakob & Hanika 2019) dat onder wit licht
dezelfde RGB geeft. Een echte verf heeft een ander spectrum: onder een ander licht of in combinatie met andere
verflagen kan hij daardoor anders van kleur zijn (metamerie). T12 kalibreert dit later aan metingen.
De RAL-tabel is een sRGB-benadering van Wikipedia, geen RAL-licentiedata.
"""

from __future__ import annotations

import csv
import re
from functools import lru_cache
from pathlib import Path

RGB = tuple[float, float, float]
RAL_BESTAND = Path(__file__).resolve().parent.parent / "data" / "ral_classic.csv"
_HEX = re.compile(r"^#?([0-9a-fA-F]{6})$")
_HEX3 = re.compile(r"^#([0-9a-fA-F]{3})$")
_RAL = re.compile(r"^(?:RAL)?[\s_-]*(\d{4})$", re.IGNORECASE)


def srgb_naar_lineair(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def lineair_naar_srgb(c: float) -> float:
    return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


@lru_cache(maxsize=1)
def ral_tabel() -> dict[str, tuple[str, str]]:
    """{'9005': ('131516', 'Jet black'), ...}"""
    with RAL_BESTAND.open(encoding="utf-8") as f:
        rijen = csv.reader(r for r in f if not r.startswith("#"))
        return {code: (hexw, naam) for code, hexw, naam in rijen}


def hex_naar_lineair(h: str) -> RGB:
    m = _HEX.match(h)
    if not m:
        raise ValueError(f"ongeldige hex-kleur {h!r}; verwacht #rrggbb")
    s = m.group(1)
    r, g, b = (int(s[i : i + 2], 16) / 255 for i in (0, 2, 4))
    return (srgb_naar_lineair(r), srgb_naar_lineair(g), srgb_naar_lineair(b))


def parse_kleur(tekst: str) -> RGB:
    """`#rrggbb`, `#rgb`, `rrggbb`, `RAL 9005`, `ral9005` of `9005` -> lineair RGB (0..1)."""
    t = tekst.strip()
    m3 = _HEX3.match(t)
    if m3:
        t = "#" + "".join(ch * 2 for ch in m3.group(1))
    if t.upper().startswith("RAL") or (len(t) == 4 and t.isdigit()):
        m = _RAL.match(t)
        if not m or m.group(1) not in ral_tabel():
            raise ValueError(f"onbekende RAL Classic-code {tekst!r}")
        return hex_naar_lineair(ral_tabel()[m.group(1)][0])
    if _HEX.match(t):
        return hex_naar_lineair(t)
    raise ValueError(f"onbekende kleur {tekst!r}; gebruik #rrggbb of RAL nnnn")


def als_kleur(v):
    """Pydantic-voorbewerking: tekst -> lineair RGB, anders ongewijzigd."""
    return parse_kleur(v) if isinstance(v, str) else v
