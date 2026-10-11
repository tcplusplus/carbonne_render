"""T19: het ChatGPT-vraagsjabloon en het uitlezen van het antwoord (JSON-blok uit vrije tekst, validatie met veldnaam)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import get_args

from pydantic import ValidationError

from carbonne.core.verf import Effect, VerfEigenschappen

SJABLOON = Path(__file__).resolve().parent.parent / "data" / "chatgpt_vraag.txt"
_CODEBLOK = re.compile(r"```[A-Za-z0-9_-]*\s*\n?(.*?)```", re.S)
_KROM = str.maketrans({"“": '"', "”": '"', "‘": "'", "’": "'"})


class TekstFout(ValueError):
    """Het antwoord bevat geen bruikbaar JSON-blok, of de velden kloppen niet (`veld` noemt het probleemveld)."""

    def __init__(self, bericht: str, veld: str | None = None):
        super().__init__(bericht)
        self.veld = veld


def vraag(merk: str, product: str, kleur: str) -> str:
    """De kopieerbare vraag voor een gewone ChatGPT."""
    schema = json.dumps(VerfEigenschappen.model_json_schema(), indent=1, ensure_ascii=False)
    return SJABLOON.read_text(encoding="utf-8").format(
        merk=merk or "(onbekend)", product=product or "(onbekend)", kleur=kleur or "(onbekend)",
        effecten=", ".join(f'"{e}"' for e in get_args(Effect)), schema=schema)


def _objecten(tekst: str):
    dec = json.JSONDecoder()
    i = tekst.find("{")
    while i != -1:
        try:
            obj, einde = dec.raw_decode(tekst, i)
        except ValueError:
            i = tekst.find("{", i + 1)
            continue
        if isinstance(obj, dict):
            yield obj
        i = tekst.find("{", einde)


def haal_json(tekst: str) -> dict:
    """Het eerste JSON-object: eerst in codeblokken, dan in de lopende tekst; ook met 'slimme' aanhalingstekens."""
    for t in (tekst, tekst.translate(_KROM)):
        bronnen = [m.group(1) for m in _CODEBLOK.finditer(t)] + [t]
        for b in bronnen:
            for obj in _objecten(b):
                return obj
    raise TekstFout("geen JSON-blok gevonden in de tekst; plak het hele antwoord van ChatGPT")


def uit_tekst(tekst: str) -> VerfEigenschappen:
    obj = haal_json(tekst)
    try:
        return VerfEigenschappen.model_validate({k: v for k, v in obj.items() if v is not None})
    except ValidationError as e:
        fouten = []
        eerste = None
        for f in e.errors():
            veld = ".".join(str(p) for p in f["loc"]) or None
            if veld is None and "hex" in f["msg"]:
                veld = "hex"
            eerste = eerste or veld
            fouten.append(f"veld {veld or 'kleur (hex/kleurcode)'}: {f['msg'].removeprefix('Value error, ')}")
        raise TekstFout("; ".join(fouten), eerste) from e
