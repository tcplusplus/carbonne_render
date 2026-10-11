"""Gestapelde verflagen (T24): van een lijst `Paint`-lagen naar een effectieve enkelvoudige verf per kant.

Fysica. Een doorschijnende pigmentlaag verstrooit en absorbeert licht binnen een dunne laag. Het standaardmodel
daarvoor is Kubelka-Munk (tweestroommodel): per kleurkanaal volgt uit de albedo van een oneindig dikke laag R_inf
de verhouding K/S = (1 - R_inf)^2 / (2 R_inf), en voor een laag met optische dikte t = S*X boven een achtergrond
met reflectie Rg:

    R = (1 - Rg (a - b coth(b t))) / (a - Rg + b coth(b t)),   a = 1 + K/S,  b = sqrt(a^2 - 1)
    T = b / (a sinh(b t) + b cosh(b t))         (doorlating boven een zwarte achtergrond)

`dekking` van een laag is 1 - T, gemiddeld over de drie kanalen; daaruit volgt t. Dekking 1 is ondoorzichtig
(t = oneindig, R = R_inf), dekking 0 is onzichtbaar. De lagen worden van de ondergrond naar buiten opgebouwd, met
de reflectie van alles eronder als Rg van de volgende laag. Hier komt geen kleurmenging "naar gevoel" in voor:
de kleur van een doorschijnende toplaag over een andere ondergrond volgt uit de absorptie en verstrooiing van
die laag.

Een stapel wordt in Mitsuba een gewone `twosided`-BSDF: de buitenkant (lucht) ziet de stapel met de buitenste
laag boven, de binnenkant (epoxy) ziet de omgekeerde volgorde. De glans (lak, lucht/verf-grensvlak) komt van de
buitenste laag aan de luchtkant, het pigment is de effectieve diffuse albedo.

Beperkingen (zie docs/evidence/T24.md):
- Doorschijnende lagen (dekking < 1) zijn alleen matte of glossy pigment, geen metallic of candy; een
  doorschijnende laag boven een metallic of candy ondergrond wordt geweigerd.
- Licht dat door alle lagen heen gaat (er is geen ondoorzichtige laag) gaat verloren in plaats van de epoxy in
  te gaan: er is geen terugkoppeling met het blok. Lagen onder een ondoorzichtige laag zijn onzichtbaar vanaf die kant.
- Kubelka-Munk is een diffuus tweestroommodel; reflecties aan de grenzen tussen lagen (Saunderson) en
  gerichte glans per laag ontbreken.
"""

from __future__ import annotations

import numpy as np

from carbonne.core.config import Paint, PaintStack

_R_MIN, _R_MAX = 1e-4, 1.0 - 1e-4


def km_reflectie(r_inf, t: float, rg):
    """Reflectie van een Kubelka-Munk-laag (albedo `r_inf`, optische dikte `t`) boven een achtergrond `rg`,
    per kanaal."""
    r_inf = np.clip(np.asarray(r_inf, dtype=float), _R_MIN, _R_MAX)
    rg = np.asarray(rg, dtype=float)
    if t <= 0:
        return rg.copy()
    a = 1.0 + (1.0 - r_inf) ** 2 / (2.0 * r_inf)
    b = np.sqrt(a * a - 1.0)
    coth = 1.0 / np.tanh(b * t)
    return (1.0 - rg * (a - b * coth)) / (a - rg + b * coth)


def km_doorlating(r_inf, t: float):
    """Doorlating van de laag boven een zwarte achtergrond, per kanaal (1 bij t = 0)."""
    r_inf = np.clip(np.asarray(r_inf, dtype=float), _R_MIN, _R_MAX)
    if t <= 0:
        return np.ones_like(r_inf)
    a = 1.0 + (1.0 - r_inf) ** 2 / (2.0 * r_inf)
    b = np.sqrt(a * a - 1.0)
    # overloopveilig: b / (a sinh + b cosh) = 2 b e^(-bt) / ((a + b) - (a - b) e^(-2bt))
    e = np.exp(-b * t)
    return 2.0 * b * e / ((a + b) - (a - b) * e * e)


def dikte_uit_dekking(kleur, dekking: float) -> float:
    """Optische dikte t waarvoor gemiddeld over de kanalen 1 - T = `dekking` (bisectie; T daalt met t)."""
    if dekking <= 0.0:
        return 0.0
    doel = 1.0 - dekking
    lo, hi = 0.0, 1.0
    while float(np.mean(km_doorlating(kleur, hi))) > doel and hi < 1e4:
        hi *= 2.0
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        if float(np.mean(km_doorlating(kleur, mid))) > doel:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def effectieve_verf(lagen_buiten_naar_binnen: list[Paint]) -> Paint:
    """De verf zoals gezien vanaf de kant waar de eerste laag van de lijst zit (de lagen eronder tellen mee).

    Loopt van buiten naar binnen tot de eerste ondoorzichtige laag; die vormt de basis. Een stapel zonder
    ondoorzichtige laag heeft een zwarte basis (doorgelaten licht gaat verloren, zie moduledocstring).
    """
    doorschijnend: list[Paint] = []
    basis: Paint | None = None
    for laag in lagen_buiten_naar_binnen:
        if laag.dekking >= 1.0:
            basis = laag
            break
        doorschijnend.append(laag)
    if not doorschijnend:
        assert basis is not None
        return basis  # zelfde object: bit-identiek aan de losse Paint
    for laag in doorschijnend:
        if laag.kind not in ("matte", "glossy"):
            raise ValueError(
                f"een doorschijnende laag (dekking < 1) kan alleen matte of glossy zijn, niet {laag.kind!r}; "
                "gebruik dekking 1 of kies candy voor een transparant gekleurde laag"
            )
    if basis is not None and basis.kind not in ("matte", "glossy"):
        raise ValueError(
            f"een doorschijnende laag boven een {basis.kind!r}-ondergrond wordt niet ondersteund "
            "(kleurmenging met een spiegelende basis volgt niet uit het model)"
        )
    rg = np.array(basis.color if basis is not None else (0.0, 0.0, 0.0), dtype=float)
    for laag in reversed(doorschijnend):  # van de basis naar buiten
        t = dikte_uit_dekking(laag.color, laag.dekking)
        rg = km_reflectie(laag.color, t, rg)
    bovenste = doorschijnend[0]
    return bovenste.model_copy(update={"color": tuple(float(x) for x in np.clip(rg, 0.0, 1.0)), "dekking": 1.0})


def stapel_twosided(stapel: PaintStack) -> dict:
    """`twosided`-BSDF: voorkant (lucht) ziet de buitenste laag boven, achterkant (epoxy) de binnenste."""
    from carbonne.core.scene import verf_bsdf

    buiten = effectieve_verf(list(reversed(stapel.lagen)))
    binnen = effectieve_verf(list(stapel.lagen))
    return {"type": "twosided", "front": verf_bsdf(buiten, binnen=False), "back": verf_bsdf(binnen, binnen=True)}
