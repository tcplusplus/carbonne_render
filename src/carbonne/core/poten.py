"""T26: metalen poten onder het blok (geometrie, BSDF en de hoogte van de vloer).

Coordinaten als in scene.py: de onderkant van het blok ligt op y = 0, het blok staat boven y = 0. De poten hangen
onder het blok (of onder de plaat van `PlateBelow`, `ophangpunt_y`) en reiken tot de vloer.

Float32-epsilon (omgeving.md): een poot die het blok raakt zou in het grensvlak epoxy/lucht vallen. De bovenkant
van een poot ligt daarom `effectieve_gap_mm` onder het ophangpunt (een haarspleet lucht, zoals bij een poot met
een montageplaatje); de onderkant steekt 1 mm in de vloer zodat er geen lek tussen poot en vloer is.
"""

from __future__ import annotations

import math

import numpy as np

from carbonne.core.config import Legs, PlateBelow, TableConfig

POOT_SEGMENTEN = 48
INZINKING_VLOER = 0.001  # m, de poot steekt zoveel in de vloer

# Metaalafwerkingen. Geborsteld en gepoetst zijn echte geleiders met de gemeten complexe brekingsindex uit de
# Mitsuba-bibliotheek (Al, Cr); de ruwheid (GGX-alpha) onderscheidt ze. Zwart gepoederlakt is geen blank metaal
# maar een poedercoating: bijna zwart pigment onder een dielectrische lak (n = 1,5).
METALEN: dict[str, dict] = {
    "geborsteld": {"materiaal": "Al", "alpha": 0.2, "omschrijving": "geborsteld aluminium"},
    "gepoetst": {"materiaal": "Cr", "alpha": 0.02, "omschrijving": "gepoetst chroom"},
    "zwart": {"pigment": (0.02, 0.02, 0.02), "alpha": 0.3, "omschrijving": "zwart gepoederlakt"},
}


def ophangpunt_y(config: TableConfig) -> float:
    """Hoogte (m) waaronder de poten hangen: onderkant van het blok, of van de plaat onder het blok."""
    from carbonne.core.scene import PLAAT_DIKTE, effectieve_gap_mm

    if isinstance(config.onderkant, PlateBelow):
        return -(effectieve_gap_mm(config, config.onderkant.gap_mm) / 1000.0 + PLAAT_DIKTE)
    return 0.0


def vloer_y(config: TableConfig) -> float | None:
    """Hoogte van de vloer als er poten zijn (ophangpunt min poothoogte), anders None."""
    return None if config.poten is None else ophangpunt_y(config) - config.poten.hoogte_m


def poot_bsdf(metaal: str) -> dict:
    m = METALEN[metaal]
    if "pigment" in m:
        return {"type": "roughplastic", "distribution": "ggx", "alpha": m["alpha"], "int_ior": 1.5, "ext_ior": 1.000277,
                "nonlinear": True, "diffuse_reflectance": {"type": "rgb", "value": list(m["pigment"])}}
    return {"type": "roughconductor", "distribution": "ggx", "alpha": m["alpha"], "material": m["materiaal"]}


def poot_posities(config: TableConfig) -> list[tuple[float, float, float]]:
    """(x, z, hoek) van elk poot-midden. Oneven aantal: een poot achter (-z, van de camera af), even: diagonaal."""
    p = config.poten
    assert p is not None
    r = p.midden_straal_mm(config.diameter) / 1000.0
    start = -math.pi / 2 if p.aantal % 2 else math.pi / 4
    uit = []
    for i in range(p.aantal):
        a = start + 2 * math.pi * i / p.aantal
        uit.append((r * math.cos(a), r * math.sin(a), a))
    return uit


def _rond(d: float, y0: float, y1: float, cx: float, cz: float) -> dict[str, np.ndarray]:
    from carbonne.core.scene import cilinder_geometrie

    g = cilinder_geometrie(d, y1 - y0, POOT_SEGMENTEN)
    return _samenvoegen([{**v, "v": v["v"] + np.array([cx, y0, cz])} for v in g.values()])


def _doos(zijde: float, y0: float, y1: float, cx: float, cz: float, hoek: float) -> dict[str, np.ndarray]:
    """Vierkante poot, een zijde radiaal naar buiten (kijkrichting `hoek` in het xz-vlak). Vlakke normalen, 24 hoekpunten."""
    half = np.array([zijde / 2, (y1 - y0) / 2, zijde / 2])
    mid = np.array([0.0, (y0 + y1) / 2, 0.0])
    vs, ns, fs = [], [], []
    for a in range(3):
        for teken in (1.0, -1.0):
            au, av = (a + 1) % 3, (a + 2) % 3  # (u, v, n) is cyclisch, dus u x v = n voor teken +1
            if teken < 0:
                au, av = av, au
            u, v, n = np.eye(3)[au], np.eye(3)[av], np.eye(3)[a] * teken
            o = len(vs)
            vs += [mid + n * half[a] + su * u * half[au] + sv * v * half[av] for su, sv in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
            ns += [n] * 4
            fs += [[o, o + 1, o + 2], [o, o + 2, o + 3]]
    c, s = math.cos(hoek), math.sin(hoek)
    rot = np.array([[c, 0, -s], [0, 1, 0], [s, 0, c]])  # (1,0,0) -> (cos, 0, sin)
    return {"v": np.array(vs) @ rot.T + np.array([cx, 0.0, cz]), "n": np.array(ns) @ rot.T, "f": np.array(fs, dtype=int)}


def _samenvoegen(delen: list[dict[str, np.ndarray]]) -> dict[str, np.ndarray]:
    o, vs, ns, fs = 0, [], [], []
    for d in delen:
        vs.append(d["v"]); ns.append(d["n"]); fs.append(np.asarray(d["f"]) + o)
        o += len(d["v"])
    return {"v": np.concatenate(vs), "n": np.concatenate(ns), "f": np.concatenate(fs)}


def poot_geometrieen(config: TableConfig) -> list[dict[str, np.ndarray]]:
    """Per poot een gesloten mesh {'v','n','f'} (naar buiten wijzende normalen); leeg zonder poten."""
    from carbonne.core.scene import effectieve_gap_mm

    p: Legs | None = config.poten
    if p is None:
        return []
    boven = ophangpunt_y(config) - effectieve_gap_mm(config, 0.0) / 1000.0
    onder = vloer_y(config) - INZINKING_VLOER  # type: ignore[operator]
    d = p.afmeting_mm / 1000.0
    return [_rond(d, onder, boven, x, z) if p.vorm == "rond" else _doos(d, onder, boven, x, z, a)
            for x, z, a in poot_posities(config)]
