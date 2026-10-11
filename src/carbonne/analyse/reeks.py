"""Wat-als-reeks (T14): laat een instelling over een reeks waarden variëren en meet op een plek wat er gebeurt.

Per waarde wordt de config aangepast (`zet_pad`), met de herkomst-integrator (T13) gerenderd via de pijplijn (T08,
dus met cache) op een lage resolutie met een vaste spp, en op het gebied gemeten: gemiddelde lineaire RGB, CIELAB
en LCh, ΔE2000 tegenover de eerste waarde en de herkomst (aandelen per categorie en kerngetallen).

Reproduceerbaarheid en ruis: elke waarde wordt twee keer gerenderd met een halve spp, met twee vaste zaden
(`seed` en `seed + 1`). Alle waarden gebruiken **dezelfde twee zaden**, zodat verschillen niet uit andere ruis komen.
De meting is het gemiddelde van de twee helften; het verschil tussen de helften geeft de standaardfout van die
meting (|A - B| / 2, zoals in de T08-pijplijn). Een ΔE die kleiner is dan `RUIS_FACTOR` keer de gecombineerde
standaardfout van de twee betrokken metingen wordt als "binnen de ruis" gemarkeerd.

L* is relatief aan een radiantie van 1,0 (= L* 100), zoals in `herkomst.lineair_naar_lab`.
"""

from __future__ import annotations

import math
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from pydantic import BaseModel, ValidationError

from carbonne.core.config import TableConfig
from carbonne.core.herkomst import Herkomst, herkomst_opties, herkomst_van

RUIS_FACTOR = 2.0  # een ΔE onder 2 x de gecombineerde standaardfout geldt als "binnen de ruis"


# ---------------------------------------------------------------------------------------------------------------
# Parameterpad


def _naar_gewoon(v: Any) -> Any:
    return v.model_dump(mode="python") if isinstance(v, BaseModel) else v


def zet_pad(config: TableConfig, pad: str, waarde: Any) -> TableConfig:
    """Nieuwe config met `pad` (bv. `hoogte`, `zijkant.color`, `onderkant`, `scene.camera.fov`, `layers.0.height_m`)
    op `waarde` gezet. `waarde` mag een scalar, een tuple/lijst, een dict of een model zijn (`Paint(...)`).
    De config zelf blijft ongemoeid. Een ongeldig pad of een ongeldige waarde geeft een `ValueError` met uitleg."""
    if not pad or not isinstance(pad, str):
        raise ValueError("parameterpad is leeg")
    data = config.model_dump(mode="python")
    delen = pad.split(".")
    if delen[0] == "poten" and len(delen) > 1 and data.get("poten") is None:
        from carbonne.core.config import Legs

        data["poten"] = Legs().model_dump()  # T26: een wat-als over de poten zet ze aan met de standaardwaarden
    huidig: Any = data
    for i, d in enumerate(delen):
        waar = ".".join(delen[: i + 1])
        laatste = i == len(delen) - 1
        if isinstance(huidig, dict):
            if d not in huidig:
                raise ValueError(f"ongeldig parameterpad '{pad}': '{d}' bestaat niet (kies uit: {', '.join(huidig)})")
            sleutel: Any = d
        elif isinstance(huidig, list):
            try:
                sleutel = int(d)
                huidig[sleutel]
            except (ValueError, IndexError):
                raise ValueError(f"ongeldig parameterpad '{pad}': '{d}' is geen geldige index (0..{len(huidig) - 1})") from None
        else:
            raise ValueError(f"ongeldig parameterpad '{pad}': '{waar}' heeft geen onderdelen")  # noqa: TRY004
        if laatste:
            huidig[sleutel] = _naar_gewoon(waarde)
        else:
            huidig = huidig[sleutel]
    try:
        return TableConfig.model_validate(data)
    except ValidationError as e:
        regels = "; ".join(f"{'.'.join(str(x) for x in f['loc'])}: {f['msg']}" for f in e.errors()[:4])
        raise ValueError(f"ongeldige waarde {waarde!r} voor '{pad}': {regels}") from None


def _srgb(x: float) -> float:
    return 12.92 * x if x <= 0.0031308 else 1.055 * x ** (1 / 2.4) - 0.055


def waarde_label(waarde: Any) -> str:
    """Korte leesbare naam van een waarde voor onder het beeld."""
    v = _naar_gewoon(waarde)
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, (int, float)):
        return f"{v:g}"
    if isinstance(v, (tuple, list)):
        if len(v) == 3 and all(isinstance(x, (int, float)) and 0 <= x <= 1 for x in v):
            return "#" + "".join(f"{round(_srgb(x) * 255):02x}" for x in v)  # lineair RGB -> sRGB-hex
        return str(list(v))
    if isinstance(v, dict):
        naam = {"bare": "kaal", "paint": "verf", "clearcoat": "matte lak", "plate": "plaat"}.get(v.get("type"), v.get("type", "?"))
        extra = []
        if v.get("kind") and v["kind"] != "matte":
            extra.append(str(v["kind"]))
        if isinstance(v.get("color"), (tuple, list)):
            extra.append(waarde_label(tuple(v["color"])))
        if "gap_mm" in v:
            extra.append(f"{v['gap_mm']:g}mm")
        if "roughness" in v and v["roughness"] is not None:
            extra.append(f"r{v['roughness']:g}")
        return " ".join([naam, *extra])
    return str(v)


# ---------------------------------------------------------------------------------------------------------------
# Kleurmaten


def lch(lab: tuple[float, float, float]) -> tuple[float, float, float]:
    L, a, b = lab
    return (L, math.hypot(a, b), math.degrees(math.atan2(b, a)) % 360.0)


def delta_e2000(l1: tuple[float, float, float], l2: tuple[float, float, float]) -> float:
    """CIEDE2000 (Sharma, Wu, Dalal 2005)."""
    L1, a1, b1 = l1
    L2, a2, b2 = l2
    c1, c2 = math.hypot(a1, b1), math.hypot(a2, b2)
    cm = (c1 + c2) / 2
    g = 0.5 * (1 - math.sqrt(cm**7 / (cm**7 + 25**7)))
    a1p, a2p = (1 + g) * a1, (1 + g) * a2
    c1p, c2p = math.hypot(a1p, b1), math.hypot(a2p, b2)
    h1p = math.degrees(math.atan2(b1, a1p)) % 360 if c1p else 0.0
    h2p = math.degrees(math.atan2(b2, a2p)) % 360 if c2p else 0.0
    dL, dC = L2 - L1, c2p - c1p
    if c1p * c2p == 0:
        dh = 0.0
    else:
        dh = h2p - h1p
        dh -= 360 * round(dh / 360)
    dH = 2 * math.sqrt(c1p * c2p) * math.sin(math.radians(dh) / 2)
    Lm, Cm = (L1 + L2) / 2, (c1p + c2p) / 2
    if c1p * c2p == 0:
        hm = h1p + h2p
    elif abs(h1p - h2p) <= 180:
        hm = (h1p + h2p) / 2
    else:
        hm = (h1p + h2p + 360) / 2 if h1p + h2p < 360 else (h1p + h2p - 360) / 2
    t = (1 - 0.17 * math.cos(math.radians(hm - 30)) + 0.24 * math.cos(math.radians(2 * hm))
         + 0.32 * math.cos(math.radians(3 * hm + 6)) - 0.20 * math.cos(math.radians(4 * hm - 63)))
    sl = 1 + 0.015 * (Lm - 50) ** 2 / math.sqrt(20 + (Lm - 50) ** 2)
    sc, sh = 1 + 0.045 * Cm, 1 + 0.015 * Cm * t
    rt = (-2 * math.sqrt(Cm**7 / (Cm**7 + 25**7))
          * math.sin(math.radians(60 * math.exp(-(((hm - 275) / 25) ** 2)))))
    return math.sqrt((dL / sl) ** 2 + (dC / sc) ** 2 + (dH / sh) ** 2 + rt * (dC / sc) * (dH / sh))


# ---------------------------------------------------------------------------------------------------------------
# Resultaat


@dataclass
class Meting:
    waarde: Any  # gewone Python-waarde (dict/getal/tuple), JSON-serialiseerbaar
    label: str
    rgb: tuple[float, float, float]  # gemiddelde lineaire RGB op het gebied
    lab: tuple[float, float, float]
    lch: tuple[float, float, float]
    de2000: float  # tegenover de eerste waarde (0 voor de eerste)
    ruis_lab: float  # standaardfout van de meting, afstand in Lab (|A - B| / 2 tussen de twee zaden)
    ruis_de: float  # gecombineerde standaardfout met de eerste waarde (0 voor de eerste)
    binnen_ruis: bool  # True: het verschil met de eerste waarde is kleiner dan RUIS_FACTOR x ruis_de
    herkomst: Herkomst
    spp: int
    tijd_s: float
    uit_cache: bool


@dataclass
class ReeksResultaat:
    parameter: str
    gebied: tuple
    straal: float
    breedte: int
    hoogte: int
    spp: int
    seed: int
    metingen: list[Meting] = field(default_factory=list)
    beelden: list[np.ndarray] = field(default_factory=list)  # (h, w, 3) lineair RGB per meting
    geannuleerd: bool = False

    def naar_dict(self) -> dict:
        from dataclasses import asdict

        d = asdict(self)
        d.pop("beelden")
        return d


# ---------------------------------------------------------------------------------------------------------------
# De reeks


def _lab_afstand(a, b) -> float:
    return float(np.linalg.norm(np.asarray(a) - np.asarray(b)))


def reeks(
    config: TableConfig,
    parameter: str,
    waarden: list[Any],
    gebied: tuple,
    *,
    straal: float = 2.0,
    breedte: int = 256,
    spp: int = 512,
    seed: int = 0,
    ev: float = 0.0,
    cache: bool = True,
    cache_map: Path | None = None,
    on_progress: Callable[[int, int, str], None] | None = None,
    annuleer: threading.Event | None = None,
    renderer: Callable[..., Any] | None = None,
) -> ReeksResultaat:
    """Render `config` voor elke waarde van `parameter` en meet op `gebied` (punt `(x, y)` met `straal`, of
    rechthoek `(x0, y0, x1, y1)`; pixels van het beeld met `breedte` kolommen, de hoogte volgt de beeldverhouding).

    `spp` is het totaal per waarde (twee helften met zaad `seed` en `seed + 1`). `on_progress(i, n, label)` wordt
    na elke afgeronde waarde aangeroepen. Bij `annuleer.set()` stopt de reeks en bevat het resultaat de tot dan
    toe afgeronde waarden (`geannuleerd=True`). Een ongeldig pad of ongeldige waarde faalt vooraf (ValueError),
    voordat er iets gerenderd is. `renderer` vervangt `render` (voor tests en de server; zelfde signatuur)."""
    from carbonne.render.pipeline import STANDAARD_CACHE, render

    render = renderer or render
    if not waarden:
        raise ValueError("geen waarden")
    cfgs = [zet_pad(config, parameter, w) for w in waarden]  # valideer alles vooraf
    helft = max(spp // 2, 1)
    res = None
    n = len(cfgs)
    ref_lab = None
    ref_ruis = 0.0
    for i, (w, c) in enumerate(zip(waarden, cfgs, strict=True)):
        if annuleer is not None and annuleer.is_set():
            break
        c = c.model_copy(deep=True)
        c.render.hoogte = max(16, round(breedte * c.render.hoogte / c.render.breedte))
        c.render.breedte = breedte
        if res is None:
            res = ReeksResultaat(parameter, tuple(gebied), straal, c.render.breedte, c.render.hoogte, 2 * helft, seed)
        helften = []
        for z in (seed, seed + 1):
            extra = {"cache_map": cache_map} if cache_map is not None else {"cache_map": STANDAARD_CACHE}
            o = herkomst_opties(c, max_spp=helft, spp_per_pass=min(16, helft), ruisdrempel=1e-9, seed=z, ev=ev,
                                cache=cache, **extra)
            helften.append(render(c, o, annuleer=annuleer))
        if any(h.reden == "geannuleerd" for h in helften):
            break
        hk = [herkomst_van(h.beeld, gebied, straal, drempel_pct=0.0) for h in helften]
        beeld = (helften[0].beeld.astype(np.float64) + helften[1].beeld) / 2
        her = herkomst_van(beeld, gebied, straal, drempel_pct=0.0)
        ruis = _lab_afstand(hk[0].lab, hk[1].lab) / 2
        if ref_lab is None:
            ref_lab, ref_ruis = her.lab, ruis
        de = delta_e2000(ref_lab, her.lab)
        ruis_de = math.hypot(ruis, ref_ruis) if i else 0.0
        res.metingen.append(Meting(
            waarde=_naar_gewoon(w), label=waarde_label(w), rgb=her.rgb, lab=her.lab, lch=lch(her.lab), de2000=de,
            ruis_lab=ruis, ruis_de=ruis_de, binnen_ruis=bool(i and de < RUIS_FACTOR * ruis_de), herkomst=her,
            spp=sum(h.spp for h in helften), tijd_s=sum(h.tijd_s for h in helften),
            uit_cache=all(h.uit_cache for h in helften),
        ))
        res.beelden.append(beeld[..., :3].astype(np.float32))
        if on_progress:
            on_progress(i + 1, n, waarde_label(w))
    if res is None:
        c0 = cfgs[0]
        res = ReeksResultaat(parameter, tuple(gebied), straal, breedte, max(16, round(breedte * c0.render.hoogte / c0.render.breedte)), 2 * helft, seed)
    res.geannuleerd = len(res.metingen) < n
    return res
