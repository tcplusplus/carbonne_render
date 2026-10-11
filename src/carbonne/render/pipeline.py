"""Progressieve HQ-render met ruisschatting, stopcriteria en cache.

Werking: de scene wordt eenmaal opgebouwd en dan in passes van `spp_per_pass` samples gerenderd, elke pass met een
eigen zaad (`seed * 100003 + pass`). Passes gaan afwisselend naar accumulatie A en B. Het verschil tussen de
gemiddelden van A en B is een onbevooroordeelde schatting van de ruis van het totale gemiddelde:
voor elk pixel is |A - B| / 2 de standaardfout van (A + B) / 2.

Ruismaat (`ruis`): RMS over alle pixels van |A - B| / 2 gedeeld door (gemiddelde RGB-waarde + 0,05). Het is dus een
relatieve fout in beeldwaarden; de 0,05 voorkomt dat bijna zwarte pixels de maat domineren. Geen denoiser op
voorspellende renders (plan): ruis wordt alleen weggewerkt door meer samples.

Alle kanalen van de film worden geaccumuleerd, ook AOV's (T13); de ruismaat gebruikt de eerste drie (RGB).
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from carbonne.core.config import TableConfig
from carbonne.render.uitvoer import png_van_lineair, schrijf_exr

ZWART_OFFSET = 0.05  # in de ruismaat, zie moduledocstring
MIN_PASSES = 4  # minder passes geeft een te onbetrouwbare halve-tegen-halve schatting
STANDAARD_CACHE = Path("cache")


class RenderOpties(BaseModel):
    model_config = ConfigDict(extra="forbid")

    integrator: str = "path"  # T13 geeft hier de naam van de herkomst-integrator
    integrator_params: dict = Field(default_factory=dict)
    max_depth: int = Field(32, ge=1, le=256, description="zie docs/evidence/T08.md voor de motivatie")
    spp_per_pass: int = Field(16, ge=1)
    max_spp: int = Field(4096, ge=1, description="harde bovengrens op het totaal aantal samples")
    ruisdrempel: float = Field(0.02, gt=0, description="stop als de relatieve ruis hieronder komt")
    tijdslimiet_s: float | None = Field(None, gt=0)
    seed: int = 0
    ev: float = 0.0  # belichting in stops, alleen voor de PNG
    preview: bool = False  # lage resolutie, weinig samples
    preview_breedte: int = 320
    preview_max_spp: int = 64
    cache: bool = True
    cache_map: Path = STANDAARD_CACHE


@dataclass
class Voortgang:
    pass_nr: int
    spp: int
    max_spp: int
    ruis: float | None  # None zolang er minder dan MIN_PASSES passes zijn
    tijd_s: float
    png: bytes  # tussenbeeld
    klaar: bool = False
    reden: str | None = None


@dataclass
class RenderResultaat:
    beeld: np.ndarray  # (h, w, c) float32, lineair; kanalen 0..2 = RGB
    kanaalnamen: list[str]
    png: bytes
    spp: int
    ruis: float | None
    tijd_s: float
    reden: str  # drempel | max_spp | tijdslimiet | geannuleerd | cache
    sleutel: str
    uit_cache: bool = False
    curve: list[tuple[float, int, float | None]] = field(default_factory=list)  # (tijd, spp, ruis)
    pad: Path | None = None  # cachemap (alleen als er geschreven is)


def code_versie() -> str:
    """Hash van de bronbestanden die het beeld bepalen (core + render) en de Mitsuba-versie."""
    import mitsuba as mi

    h = hashlib.sha256(mi.__version__.encode())
    root = Path(__file__).resolve().parents[1]
    for sub in ("core", "render"):
        for f in sorted((root / sub).glob("*.py")):
            h.update(f.name.encode())
            h.update(f.read_bytes())
    return h.hexdigest()[:12]


def cache_sleutel(config: TableConfig, opties: RenderOpties) -> str:
    """Hash van de genormaliseerde config, de renderinstellingen die het beeld beinvloeden en de codeversie.
    Tijdslimiet, EV en cache-instellingen horen er niet in: ze veranderen de geconvergeerde EXR niet."""
    o = opties.model_dump(mode="json", exclude={"tijdslimiet_s", "ev", "cache", "cache_map"})
    payload = json.dumps(
        {"config": config.model_dump(mode="json"), "opties": o, "code": code_versie()}, sort_keys=True
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:20]


def ruis_schatting(a_som: np.ndarray, na: int, b_som: np.ndarray, nb: int) -> float:
    """Relatieve RMS-fout van het totaalgemiddelde uit twee onafhankelijke halve accumulaties."""
    a, b = a_som[..., :3] / na, b_som[..., :3] / nb
    gem = (a * na + b * nb) / (na + nb)
    fout = np.abs(a - b) / 2
    return float(np.sqrt(np.mean((fout / (gem + ZWART_OFFSET)) ** 2)))


def _effectieve_config(config: TableConfig, opties: RenderOpties) -> TableConfig:
    cfg = config.model_copy(deep=True)
    if opties.preview:
        cfg.render.hoogte = max(16, round(opties.preview_breedte * cfg.render.hoogte / cfg.render.breedte))
        cfg.render.breedte = opties.preview_breedte
    cfg.render.max_depth = opties.max_depth
    return cfg


def _laad_cache(map_: Path, ev: float) -> RenderResultaat | None:
    meta_pad, data_pad = map_ / "meta.json", map_ / "beeld.npz"
    if not (meta_pad.exists() and data_pad.exists()):
        return None
    meta = json.loads(meta_pad.read_text())
    beeld = np.load(data_pad)["beeld"]
    return RenderResultaat(
        beeld=beeld, kanaalnamen=meta["kanaalnamen"], png=png_van_lineair(beeld, ev), spp=meta["spp"],
        ruis=meta["ruis"], tijd_s=meta["tijd_s"], reden="cache", sleutel=map_.name, uit_cache=True,
        curve=[tuple(x) for x in meta["curve"]], pad=map_,
    )


def _schrijf_cache(map_: Path, r: RenderResultaat, config: TableConfig, opties: RenderOpties) -> None:
    map_.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(map_ / "beeld.npz", beeld=r.beeld)
    schrijf_exr(map_ / "beeld.exr", r.beeld, r.kanaalnamen)
    (map_ / "beeld.png").write_bytes(r.png)
    meta = {
        "spp": r.spp, "ruis": r.ruis, "tijd_s": r.tijd_s, "reden": r.reden, "kanaalnamen": r.kanaalnamen,
        "curve": r.curve, "code": code_versie(), "opties": opties.model_dump(mode="json"),
        "config": config.model_dump(mode="json"),
    }
    (map_ / "meta.json").write_text(json.dumps(meta, indent=1, default=str))


def render(
    config: TableConfig,
    opties: RenderOpties | None = None,
    on_progress: Callable[[Voortgang], None] | None = None,
    annuleer: threading.Event | None = None,
) -> RenderResultaat:
    """Render `config` progressief. Stopt op de ruisdrempel, `max_spp`, de tijdslimiet of bij `annuleer.set()`.

    Een resultaat dat de drempel of `max_spp` haalt komt in de cache (sleutel: config + opties + codeversie);
    een tijdgelimiteerd of geannuleerd resultaat niet. De eerste callback na een cachehit is `klaar=True`."""
    import mitsuba as mi

    from carbonne.core.scene import build_scene
    from carbonne.core.variant import select_variant

    opties = opties or RenderOpties()
    sleutel = cache_sleutel(config, opties)
    map_ = opties.cache_map / sleutel
    if opties.cache and not opties.preview:
        hit = _laad_cache(map_, opties.ev)
        if hit is not None:
            if on_progress:
                on_progress(Voortgang(0, hit.spp, opties.max_spp, hit.ruis, 0.0, hit.png, True, "cache"))
            return hit

    select_variant()
    if opties.integrator == "herkomst":
        from carbonne.core.herkomst import registreer

        registreer()
    cfg = _effectieve_config(config, opties)
    sd = build_scene(cfg)
    # integrator_params overschrijft; een waarde None laat de sleutel weg (voor integratoren zonder max_depth)
    soort = opties.integrator
    if config.epoxy.heeft_medium:
        if soort == "herkomst":
            raise ValueError("de herkomst-integrator ondersteunt geen medium (absorptie/verstrooiing in de epoxy, T17)")
        if soort == "path":
            soort = "volpath"  # path negeert media
    ints = {"type": soort, "max_depth": opties.max_depth, **opties.integrator_params}
    sd["integrator"] = {k: v for k, v in ints.items() if v is not None}
    scene = mi.load_dict(sd)
    namen = ["R", "G", "B"] + list(scene.integrator().aov_names())
    kanalen: int | None = None  # wordt na de eerste pass gecontroleerd tegen `namen`
    max_spp = min(opties.max_spp, opties.preview_max_spp) if opties.preview else opties.max_spp

    som = [None, None]  # A (even passes), B (oneven passes)
    n = [0, 0]  # aantal passes per helft
    t0 = time.perf_counter()
    spp, nr, ruis, reden = 0, 0, None, "max_spp"
    curve: list[tuple[float, int, float | None]] = []
    while True:
        if annuleer is not None and annuleer.is_set():
            reden = "geannuleerd"
            break
        stap = min(opties.spp_per_pass, max_spp - spp)
        img = np.array(mi.render(scene, spp=stap, seed=opties.seed * 100003 + nr), dtype=np.float64)
        if kanalen is None:
            kanalen = img.shape[2]
            if len(namen) != kanalen:  # integrator zonder (juiste) aov_names: noem de kanalen neutraal
                namen = ["R", "G", "B"][:kanalen] + [f"kanaal{i}" for i in range(3, kanalen)]
        h = nr % 2
        # passes kunnen een kleinere laatste stap hebben; weeg per sample zodat de gemiddelden kloppen
        som[h] = img * stap if som[h] is None else som[h] + img * stap
        n[h] += stap
        spp += stap
        nr += 1
        tijd = time.perf_counter() - t0
        ruis = ruis_schatting(som[0], n[0], som[1], n[1]) if nr >= MIN_PASSES else None
        curve.append((round(tijd, 3), spp, ruis))
        totaal = (som[0] + (som[1] if som[1] is not None else 0)) / spp
        klaar = False
        if ruis is not None and ruis <= opties.ruisdrempel:
            reden, klaar = "drempel", True
        elif spp >= max_spp:
            reden, klaar = "max_spp", True
        elif opties.tijdslimiet_s is not None and tijd >= opties.tijdslimiet_s:
            reden, klaar = "tijdslimiet", True
        if on_progress:
            on_progress(Voortgang(nr, spp, max_spp, ruis, tijd, png_van_lineair(totaal, opties.ev), klaar,
                                  reden if klaar else None))
        if klaar:
            break
    if nr == 0:
        raise RuntimeError("geannuleerd voor de eerste pass; geen beeld")
    beeld = ((som[0] + (som[1] if som[1] is not None else 0)) / spp).astype(np.float32)
    res = RenderResultaat(
        beeld=beeld, kanaalnamen=namen, png=png_van_lineair(beeld, opties.ev), spp=spp, ruis=ruis,
        tijd_s=time.perf_counter() - t0, reden=reden, sleutel=sleutel, curve=curve,
    )
    if opties.cache and not opties.preview and reden in ("drempel", "max_spp"):
        _schrijf_cache(map_, res, config, opties)
        res.pad = map_
    return res
