"""Gedeelde verfbibliotheek (T18): een JSON-bestand per verf in `data/verven/<slug>.json` (gebruikersdata, in git).

Een bestand bevat de eigenschappen, de vertaalde `Paint`, de datum en de versie van de vertaalregels. Bij het laden
wordt opnieuw vertaald als die versie niet meer klopt. De map is aan te wijzen met `CARBONNE_VERVEN` of via `map_`.
"""

from __future__ import annotations

import os
import re
import unicodedata
from datetime import date
from pathlib import Path

from pydantic import BaseModel

from carbonne.core.verf import VerfEigenschappen, Vertaling, regels_versie, vertaal_verf

STANDAARD_MAP = Path(__file__).resolve().parents[3] / "data" / "verven"


class BibliotheekItem(BaseModel):
    slug: str
    datum: str
    regels_versie: str
    eigenschappen: VerfEigenschappen
    vertaling: Vertaling

    @property
    def bron(self) -> str | None:
        return self.eigenschappen.bron_url


def verf_map(map_: Path | None = None) -> Path:
    return Path(map_ or os.environ.get("CARBONNE_VERVEN") or STANDAARD_MAP)


def maak_slug(e: VerfEigenschappen) -> str:
    delen = [e.merk, e.product, e.kleurnaam] if (e.merk or e.product or e.kleurnaam) else [e.kleurcode or e.hex]
    tekst = " ".join(d for d in delen if d)
    tekst = unicodedata.normalize("NFKD", tekst).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", tekst).strip("-") or "verf"


def _pad(slug: str, map_: Path | None) -> Path:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", slug):
        raise ValueError(f"ongeldige slug {slug!r}")
    return verf_map(map_) / f"{slug}.json"


def _met_id(v: Vertaling, slug: str) -> Vertaling:
    return v.model_copy(update={"paint": v.paint.model_copy(update={"bibliotheek_id": slug})})


def bewaar(e: VerfEigenschappen, overschrijf: bool = False, map_: Path | None = None, slug: str | None = None) -> BibliotheekItem:
    """Vertaal en bewaar. Bestaat de slug al, dan volgt `FileExistsError` tenzij `overschrijf`."""
    slug = slug or maak_slug(e)
    pad = _pad(slug, map_)
    if pad.exists() and not overschrijf:
        raise FileExistsError(f"verf {slug!r} bestaat al; gebruik overschrijf=True")
    item = BibliotheekItem(
        slug=slug,
        datum=date.today().isoformat(),
        regels_versie=regels_versie(),
        eigenschappen=e,
        vertaling=_met_id(vertaal_verf(e), slug),
    )
    pad.parent.mkdir(parents=True, exist_ok=True)
    pad.write_text(item.model_dump_json(indent=1) + "\n", encoding="utf-8")
    return item


def laad(slug: str, map_: Path | None = None) -> BibliotheekItem:
    """Laad een verf; is de versie van de vertaalregels veranderd, dan wordt opnieuw vertaald (het bestand blijft
    staan tot `bewaar(..., overschrijf=True)`)."""
    pad = _pad(slug, map_)
    if not pad.exists():
        raise KeyError(f"onbekende verf {slug!r}")
    item = BibliotheekItem.model_validate_json(pad.read_text(encoding="utf-8"))
    if item.regels_versie != regels_versie():
        item = item.model_copy(
            update={"regels_versie": regels_versie(), "vertaling": _met_id(vertaal_verf(item.eigenschappen), slug)}
        )
    return item


def lijst(map_: Path | None = None) -> list[BibliotheekItem]:
    m = verf_map(map_)
    return [laad(p.stem, map_) for p in sorted(m.glob("*.json"))] if m.is_dir() else []


def verwijder(slug: str, map_: Path | None = None) -> None:
    pad = _pad(slug, map_)
    if not pad.exists():
        raise KeyError(f"onbekende verf {slug!r}")
    pad.unlink()
