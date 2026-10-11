"""Toegestane parameterpaden voor een wat-als-reeks (T15), met type en voorbeeldwaarden voor een keuzelijst.

Elke voorbeeldwaarde moet door `zet_pad` geaccepteerd worden; `tests/test_t15.py` controleert dat tegen de
standaardconfig, zodat deze lijst niet ongemerkt achterloopt op `core/config.py`."""

from __future__ import annotations

from typing import Any

from carbonne.core.environments import CAMERA_PRESETS, OMGEVINGEN

_VERF = [{"type": "bare"}, {"type": "clearcoat", "roughness": 0.3},
         {"type": "paint", "color": "#000000", "kind": "matte"}, {"type": "paint", "color": "#c1121f", "kind": "glossy"},
         {"type": "paint", "color": "#c1121f", "kind": "metallic"}]
_ZWART_PLAAT = {"type": "plate", "color": "#000000", "gap_mm": 1.0}


def _p(pad: str, soort: str, omschrijving: str, voorbeelden: list[Any], eenheid: str | None = None,
       min_: float | None = None, max_: float | None = None, patroon: bool = False) -> dict:
    d: dict[str, Any] = {"pad": pad, "type": soort, "omschrijving": omschrijving, "voorbeelden": voorbeelden,
                         "eenheid": eenheid, "min": min_, "max": max_}
    if patroon:
        d["patroon"] = True  # `n` in het pad is een laagnummer (0, 1, ...)
    return d


PARAMETERS: list[dict] = [
    _p("hoogte", "getal", "dikte van het blok", [0.02, 0.03, 0.04, 0.05, 0.06], "m", 0.02, 0.06),
    _p("diameter", "getal", "diameter van het tafeltje", [0.25, 0.35, 0.5], "m", 0.01, 2.0),
    _p("zijkant", "afwerking", "afwerking van de zijkant", _VERF),
    _p("onderkant", "afwerking", "afwerking van de onderkant", [*_VERF, _ZWART_PLAAT]),
    _p("zijkant.color", "kleur", "kleur van de zijkantverf (alleen als de zijkant verf is)",
       ["#c1121f", "#1d4ed8", "RAL 3020", "RAL 9005"]),
    _p("onderkant.color", "kleur", "kleur van de onderkantverf of -plaat (alleen als die verf of plaat is)",
       ["#000000", "#ffffff", "#c1121f", "RAL 9005"]),
    _p("onderkant.gap_mm", "getal", "luchtspleet tussen blok en plaat (alleen bij een plaat)",
       [0.1, 1.0, 5.0, 20.0], "mm", 0.0, 50.0),
    _p("epoxy.cauchy_a", "getal", "brekingsindex van de epoxy (Cauchy A)", [1.48, 1.517, 1.56], None, 1.0, 3.0),
    _p("epoxy.cauchy_b", "getal", "dispersie van de epoxy (Cauchy B)", [0.0, 0.0045, 0.01], "um^2", 0.0, 0.1),
    _p("scene.camera.fov", "getal", "horizontaal beeldveld van de camera", [25, 40, 60], "graden", 1.0, 120.0),
    _p("scene.omgeving", "keuze", "omgeving (HDRI)", list(OMGEVINGEN)),
    _p("scene.camera_preset", "keuze", "camerastandpunt", list(CAMERA_PRESETS)),
    _p("scene.spot", "waar/onwaar", "extra spot boven het tafeltje", [False, True]),
    _p("layers.n.height_m", "getal", "hoogte van gietlaag n (0 is de onderste; laag moet bestaan)",
       [0.01, 0.02, 0.03], "m", 0.0, 0.06, patroon=True),
]
