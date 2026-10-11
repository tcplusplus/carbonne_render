"""Verfvertaling (T18): producteigenschappen -> `Paint`-instellingen, met herkomst per veld en waarschuwingen.

De vertaling is een vaste, geteste functie (geen LLM-gok). De regels staan als data in dit bestand
(`GLANS_TERMEN`, `EFFECT_REGELS`, `GLANS_DREMPEL_MATTE_GU`) en in `data/glans_tabel.json` (GU -> GGX-alpha, gemeten met
de gesimuleerde glansmeter van `core/glansmeter.py`, script `scripts/maak_glans_tabel.py`). `regels_versie()` is een
hash van al die data; de bibliotheek vertaalt opnieuw als hij verandert.

Glans gaat alleen over de BUITENKANT van de verf (verf in lucht). Het binnenvlak (verf in optisch contact met de epoxy)
blijft zoals T03/T05 het definieert: pigment zonder Fresnel-grensvlak, dus zonder glans.
"""

from __future__ import annotations

import hashlib
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from carbonne.core.config import Paint
from carbonne.core.kleur import parse_kleur

GLANS_TABEL = Path(__file__).resolve().parent.parent / "data" / "glans_tabel.json"

# --- regels als data -------------------------------------------------------------------------------------------------
# GU-bereik (60 graden) per glansterm; een term gebruikt het midden van het bereik. Bereiken uit het taakdossier T18;
# ze komen overeen met de gangbare indeling van verffabrikanten en glansmeterleveranciers (Rhopoint: laag < 10,
# middel 10-70, hoog > 70 GU; EN 13300 gebruikt 60 graden en 85 graden). Niet online opnieuw gecontroleerd tijdens T18.
GLANS_TERMEN: dict[str, tuple[float, float]] = {
    "mat": (0.0, 10.0),
    "zijdemat": (10.0, 35.0),
    "zijdeglans": (35.0, 70.0),
    "glans": (70.0, 85.0),
    "hoogglans": (85.0, 100.0),
}
GLANS_ALIASSEN: dict[str, str] = {
    "mat": "mat", "matt": "mat", "flat": "mat", "dead flat": "mat", "ultramat": "mat", "diepmat": "mat",
    "zijdemat": "zijdemat", "eggshell": "zijdemat", "satin matt": "zijdemat", "satin matte": "zijdemat",
    "zijdeglans": "zijdeglans", "satijn": "zijdeglans", "satin": "zijdeglans", "semi-gloss": "zijdeglans",
    "semi gloss": "zijdeglans", "semigloss": "zijdeglans", "halfglans": "zijdeglans", "semi-glans": "zijdeglans",
    "glans": "glans", "gloss": "glans", "glanzend": "glans",
    "hoogglans": "hoogglans", "high gloss": "hoogglans", "high-gloss": "hoogglans", "hoog glans": "hoogglans",
}
GLANS_STANDAARD = "zijdeglans"  # als er geen glans is opgegeven (met waarschuwing)
# Onder deze GU (GGX-alpha > ~0,25, zie de gemeten tabel) is er van de glossy-verf alleen nog een brede, zwakke gloed
# over (< 3 % van de reflectie van zwart glas); die is niet van een diffuse verf te onderscheiden. Daaronder wordt het
# `matte` (Lambert).
GLANS_DREMPEL_MATTE_GU = 3.0
CHROOM_RUWHEID = 0.01  # GGX-alpha van chroom: bijna een spiegel
EFFECTEN = ("geen", "metallic", "chroom", "candy", "parelmoer", "glitter", "fluo")
EFFECT_REGELS: dict[str, dict] = {
    "geen": {"kind": None, "regel": "geen effect: matte of glossy volgens de glans"},
    "metallic": {"kind": "metallic", "regel": "metallic -> roughconductor met de kleur als spiegelreflectie"},
    "chroom": {"kind": "metallic", "regel": f"chroom -> metallic met zeer lage ruwheid (alpha {CHROOM_RUWHEID})"},
    "candy": {"kind": "candy", "regel": "candy -> gekleurde transparante laag over een ondergrond (kleur^2)"},
    "parelmoer": {
        "kind": "metallic",
        "regel": "parelmoer -> dichtstbijzijnde soort: metallic",
        "waarschuwing": "Parelmoer wordt niet nagebootst: het effect komt uit hoekafhankelijke interferentie in "
        "dunne laagjes, de app heeft alleen een vaste kleur per verfsoort. Metallic is de dichtstbijzijnde soort.",
    },
    "glitter": {
        "kind": "metallic",
        "regel": "glitter -> dichtstbijzijnde soort: metallic",
        "waarschuwing": "Glitter wordt niet nagebootst: het zijn losse spiegelende deeltjes die elk apart flitsen, "
        "de app rekent met een gladde microstructuur (GGX). Metallic is de dichtstbijzijnde soort.",
    },
    "fluo": {
        "kind": None,
        "regel": "fluo -> dichtstbijzijnde soort: matte of glossy volgens de glans",
        "waarschuwing": "Fluorescentie wordt niet nagebootst: fluo-pigment zet UV en blauw licht om in extra zichtbaar "
        "licht, de app is niet-fluorescerend (energiebehoud per golflengte). De kleur wordt als gewone verf gerenderd, "
        "dus fluo ziet er in de app doffer uit dan in het echt.",
    },
}

Glansterm = Literal["mat", "zijdemat", "zijdeglans", "glans", "hoogglans"]
Effect = Literal["geen", "metallic", "chroom", "candy", "parelmoer", "glitter", "fluo"]


class VerfFout(ValueError):
    """De eigenschappen zijn niet genoeg of niet geldig om een verf te vertalen."""


def _norm_term(t: str) -> str:
    return re.sub(r"\s+", " ", t.strip().lower())


# --- invoer en uitvoer -----------------------------------------------------------------------------------------------
class VerfEigenschappen(BaseModel):
    """Eigenschappen van het product, zoals op het blik of het technische fiche staan."""

    model_config = ConfigDict(extra="forbid")

    merk: str | None = None
    product: str | None = None
    kleurnaam: str | None = None
    kleurcode: str | None = Field(None, description="RAL-code ('RAL 3020') of hex; een merkcode alleen samen met `hex`")
    hex: str | None = Field(None, description="#rrggbb (sRGB-weergave van de kleur)")
    glansgraad: str | None = Field(None, description="mat, zijdemat, zijdeglans, satijn, glans, hoogglans (ook Engels)")
    glans_gu_60: float | None = Field(None, ge=0.0, le=120.0, description="gloss units bij 60 graden (technisch fiche)")
    effect: Effect = "geen"
    transparant: bool = False
    ondergrond_candy: Literal["metallic", "white"] | None = None
    bron_url: str | None = None
    opmerking: str | None = None

    @field_validator("glansgraad")
    @classmethod
    def _term(cls, v: str | None) -> str | None:
        if v is not None and _norm_term(v) not in GLANS_ALIASSEN:
            raise ValueError(f"onbekende glansgraad {v!r}; kies uit {', '.join(sorted(GLANS_ALIASSEN))} of geef glans_gu_60")
        return v

    @field_validator("hex")
    @classmethod
    def _hex(cls, v: str | None) -> str | None:
        if v is not None:
            parse_kleur(v)  # ValueError bij een ongeldige hex
        return v

    @model_validator(mode="after")
    def _kleur_aanwezig(self) -> VerfEigenschappen:
        if not (self.kleurcode or self.hex):
            raise ValueError("geef een kleur: `hex` of een RAL-`kleurcode` (er volgt geen gok)")
        return self


class VeldVertaling(BaseModel):
    veld: str
    waarde: str
    bron: str = Field(description="welk invoerveld de waarde bepaalde, of 'standaard'")
    regel: str


class Vertaling(BaseModel):
    paint: Paint
    uitleg: list[VeldVertaling]
    waarschuwingen: list[str] = Field(default_factory=list)


# --- glanstabel ------------------------------------------------------------------------------------------------------
@lru_cache(maxsize=1)
def glans_tabel() -> dict:
    return json.loads(GLANS_TABEL.read_text(encoding="utf-8"))


def gu_naar_alpha(gu: float) -> tuple[float, str | None]:
    """GU (60 graden) -> GGX-alpha uit de gemeten tabel (log-lineair geinterpoleerd); buiten de tabel afgekapt.
    Geeft (alpha, opmerking over afkappen of None). Monotoon: meer glans geeft nooit meer ruwheid."""
    t = glans_tabel()
    alpha, tgu = np.array(t["alpha"]), np.array(t["gu"])
    # tgu daalt met alpha; maak hem strikt monotoon (meetruis in de staart) en keer om voor np.interp
    tgu = np.minimum.accumulate(tgu)
    lo_gu, hi_gu = float(tgu[-1]), float(tgu[0])
    opm = None
    if gu > hi_gu:
        opm = f"{gu:g} GU is meer dan een lak met n = 1,5 kan geven ({hi_gu:.0f} GU bij alpha {alpha[0]:g}); afgekapt"
        gu = hi_gu
    elif gu < lo_gu:
        gu = lo_gu
    xs = tgu[::-1] + np.arange(len(tgu)) * 1e-9  # strikt stijgend voor interp
    la = np.interp(gu, xs, np.log(alpha[::-1]))
    return float(np.exp(la)), opm


def alpha_naar_gu(alpha: float) -> float:
    t = glans_tabel()
    return float(np.interp(np.log(alpha), np.log(t["alpha"]), t["gu"]))


def regels_versie() -> str:
    """Hash van alle vertaalregels en de glanstabel; verandert zodra de vertaling kan veranderen."""
    data = json.dumps(
        [GLANS_TERMEN, GLANS_ALIASSEN, GLANS_STANDAARD, GLANS_DREMPEL_MATTE_GU, CHROOM_RUWHEID, EFFECT_REGELS, glans_tabel()],
        sort_keys=True,
    )
    return hashlib.sha1(data.encode()).hexdigest()[:10]


# --- vertaling -------------------------------------------------------------------------------------------------------
def _kleur(e: VerfEigenschappen, uitleg: list[VeldVertaling], waarsch: list[str]) -> tuple[float, float, float]:
    if e.hex:
        rgb = parse_kleur(e.hex)
        bron, regel = "hex", "hex (sRGB) -> lineair RGB"
        if e.kleurcode:
            try:
                if max(abs(a - b) for a, b in zip(parse_kleur(e.kleurcode), rgb, strict=True)) > 0.02:
                    waarsch.append(f"kleurcode {e.kleurcode!r} en hex {e.hex} wijken af; de hex is gebruikt")
            except ValueError:
                pass  # een merkcode: geen tabel, de hex is het enige
    else:
        try:
            rgb = parse_kleur(e.kleurcode or "")
        except ValueError as exc:
            raise VerfFout(
                f"kleurcode {e.kleurcode!r} is geen RAL Classic-code of hex. Een merkcode (bv. 'Montana GOLD Shock Blue') "
                "kan niet vertaald worden: er is geen merkcodetabel. Geef er een `hex` bij."
            ) from exc
        bron, regel = "kleurcode", "RAL Classic-tabel (sRGB-benadering) -> lineair RGB"
    uitleg.append(VeldVertaling(veld="color", waarde=", ".join(f"{c:.4f}" for c in rgb), bron=bron, regel=regel))
    return tuple(float(c) for c in rgb)  # type: ignore[return-value]


def _glans(e: VerfEigenschappen, waarsch: list[str]) -> tuple[float, str, str]:
    """-> (GU, bron, regel)."""
    term = GLANS_ALIASSEN[_norm_term(e.glansgraad)] if e.glansgraad else None
    if e.glans_gu_60 is not None:
        gu = e.glans_gu_60
        if term:
            lo, hi = GLANS_TERMEN[term]
            if not lo <= gu <= hi:
                waarsch.append(f"glansgraad {e.glansgraad!r} ({lo:g}-{hi:g} GU) past niet bij {gu:g} GU; de GU-waarde is gebruikt")
        return gu, "glans_gu_60", "gemeten GU bij 60 graden uit het technische fiche"
    if term:
        lo, hi = GLANS_TERMEN[term]
        return (lo + hi) / 2, "glansgraad", f"term {term!r} = {lo:g}-{hi:g} GU, midden gebruikt"
    lo, hi = GLANS_TERMEN[GLANS_STANDAARD]
    waarsch.append(f"geen glans opgegeven; aangenomen {GLANS_STANDAARD} ({(lo + hi) / 2:g} GU). Geef glansgraad of glans_gu_60.")
    return (lo + hi) / 2, "standaard", f"geen glans opgegeven: {GLANS_STANDAARD}, midden van {lo:g}-{hi:g} GU"


def vertaal_verf(e: VerfEigenschappen) -> Vertaling:
    """Zet de producteigenschappen om in `Paint`-instellingen. Faalt met `VerfFout` als de kleur ontbreekt of een
    merkcode zonder hex is gegeven."""
    uitleg: list[VeldVertaling] = []
    waarsch: list[str] = []
    kleur = _kleur(e, uitleg, waarsch)
    gu, gu_bron, gu_regel = _glans(e, waarsch)

    effect = e.effect
    if e.transparant and effect == "geen":
        effect = "candy"
        eff_bron, eff_extra = "transparant", "transparant=True met een kleur -> candy"
    else:
        eff_bron, eff_extra = ("effect" if e.effect != "geen" else "standaard"), None
        if e.transparant and effect != "candy":
            waarsch.append(f"transparant=True genegeerd: effect {effect!r} gaat voor")
    regel = EFFECT_REGELS[effect]
    if "waarschuwing" in regel:
        waarsch.append(regel["waarschuwing"])

    kind = regel["kind"]
    roughness: float | None = None
    glans_regel = "geen glans-instelling nodig"
    if effect == "chroom":
        roughness = CHROOM_RUWHEID
        glans_regel = "chroom: vaste zeer lage ruwheid, de glans wordt niet gebruikt"
    elif kind is None:  # geen of fluo: matte of glossy volgens de glans
        if gu < GLANS_DREMPEL_MATTE_GU:
            kind, glans_regel = "matte", f"{gu:g} GU < {GLANS_DREMPEL_MATTE_GU:g} GU: diffuse verf (Lambert)"
        else:
            kind = "glossy"
    if kind in ("glossy", "metallic", "candy") and effect != "chroom":
        if gu_bron == "standaard" and kind in ("metallic", "candy"):
            glans_regel = "geen glans opgegeven: standaardruwheid van de verfsoort"  # roughness blijft None
        else:
            roughness, opm = gu_naar_alpha(gu)
            roughness = round(roughness, 4)
            glans_regel = f"{gu:g} GU -> GGX-alpha {roughness:g} (gemeten tabel, ISO 2813 60 graden)"
            if opm:  # een term als 'hoogglans' (midden 92,5 GU) kapt altijd af: dat is geen waarschuwing waard
                if gu_bron == "glans_gu_60":
                    waarsch.append(opm)
                else:
                    glans_regel += f" ({opm})"
            if kind != "glossy":
                glans_regel += "; tabel gemeten voor lak, voor metaal bij benadering"

    candy_base = "metallic"
    if kind == "candy":
        candy_base = e.ondergrond_candy or "metallic"
        cb_bron = "ondergrond_candy" if e.ondergrond_candy else "standaard"
    paint = Paint(color=kleur, kind=kind, roughness=roughness, candy_base=candy_base)

    uitleg.append(VeldVertaling(veld="kind", waarde=paint.kind, bron=eff_bron, regel=eff_extra or regel["regel"]))
    uitleg.append(
        VeldVertaling(
            veld="roughness",
            waarde="standaard van de soort" if roughness is None else f"{roughness:g}",
            bron="effect" if effect == "chroom" else gu_bron,
            regel=glans_regel if effect == "chroom" or not glans_regel.startswith(f"{gu:g} GU ->") else f"{glans_regel} [{gu_regel}]",
        )
    )
    if kind == "candy":
        uitleg.append(VeldVertaling(veld="candy_base", waarde=candy_base, bron=cb_bron, regel="ondergrond onder de gekleurde laag"))
    uitleg.append(
        VeldVertaling(
            veld="binnenvlak",
            waarde="ongewijzigd",
            bron="model",
            regel="de glans geldt alleen voor de buitenkant in lucht; het vlak in contact met de epoxy blijft pigment zonder "
            "grensvlak (T03/T05)",
        )
    )
    return Vertaling(paint=paint, uitleg=uitleg, waarschuwingen=waarsch)
