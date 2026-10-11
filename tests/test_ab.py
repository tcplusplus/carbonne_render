"""T04: korte versie van het A/B-experiment (scripts/ab_experiment.py) als regressietest op de gevonden richting."""

import importlib.util
import sys
from pathlib import Path

import pytest

pad = Path(__file__).resolve().parents[1] / "scripts" / "ab_experiment.py"
spec = importlib.util.spec_from_file_location("ab_experiment", pad)
ab = importlib.util.module_from_spec(spec)
sys.modules["ab_experiment"] = ab
spec.loader.exec_module(ab)


@pytest.fixture(scope="module")
def r():
    ab.select_variant()
    rijen, _ = ab.run(96, 256, codes=("A1", "A2", "B1", "B2", "C", "WB1", "WB2"), zaden=(3,))
    return {x["code"]: x for x in rijen}


def test_zwart_geverfd_is_niet_zwarte_plaat(r):
    """De plaat met luchtspleet houdt het onderste epoxy/lucht-grensvlak (4 % terugkaatsing) en is dus lichter
    dan zwarte verf in contact: pure verhouding > 1,5 (gemeten ~1,9)."""
    assert r["A2"]["luminantie"] / r["A1"]["luminantie"] > 1.5


def test_matte_lak_tussen_verf_en_plaat(r):
    assert r["A1"]["luminantie"] < r["C"]["luminantie"] <= r["A2"]["luminantie"] * 1.02


def test_kleurverschuiving_zijkant_gemeten_richting(r):
    """Gemeten (niet het verwachte) resultaat: de rode zijkant kleurt het midden van het bovenvlak bij verf in
    contact met een lichte onderkant sterk, bij een plaat met luchtspleet bijna niet. Zie docs/evidence/T04.md."""
    assert r["WB1"]["rood_aandeel"] > r["WB2"]["rood_aandeel"] + 0.03
    assert abs(r["B2"]["rood_aandeel"] - 1 / 3) < 0.003
