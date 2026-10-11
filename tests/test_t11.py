"""T11: uitlegschetsen (2D-stralendoorsnede)."""

import importlib.util
import math
import sys
from pathlib import Path

import numpy as np

_pad = Path(__file__).resolve().parent.parent / "scripts" / "maak_uitlegschetsen.py"
_spec = importlib.util.spec_from_file_location("maak_uitlegschetsen", _pad)
m = importlib.util.module_from_spec(_spec)
sys.modules["maak_uitlegschetsen"] = m
_spec.loader.exec_module(m)

N = m.N_EPOXY


def test_kritische_hoek():
    assert math.isclose(m.kritische_hoek_graden(), math.degrees(math.asin(1 / N)), rel_tol=1e-12)
    assert 40.7 < m.kritische_hoek_graden() < 40.9


def test_fresnel_loodrecht():
    f, _ = m.fresnel(1.0, N, 1.0)
    assert math.isclose(f, ((N - 1) / (N + 1)) ** 2, rel_tol=1e-9)
    f2, _ = m.fresnel(N, 1.0, 1.0)
    assert math.isclose(f2, f, rel_tol=1e-9)


def test_tir_en_net_onder_kritiek():
    kh = math.asin(1 / N)
    assert m.fresnel(N, 1.0, math.cos(kh + 0.01))[0] == 1.0
    assert m.fresnel(N, 1.0, math.cos(kh - 0.01))[0] < 1.0


def test_60_graden_onbehandeld_volledig_terug(monkeypatch):
    monkeypatch.setattr(m, "MAX_DIEPTE", 1)  # alleen de eerste botsing en haar kinderen
    # kinderen met diepte > MAX worden weggegooid, dus we tellen via een nieuwe tracing met diepte 0 en
    # vergelijken de energie van het eerste segment na de onderkant
    opst = m.Opstelling("t", "kaal", "kaal")
    r = math.radians(60.0)
    d = np.array([math.sin(r), -math.cos(r)])
    st = m.Straal(np.array([30.0, 1.0]), d, 1.0, 0, True)
    segs = m.trace(opst, [st])
    na = [s for s in segs if s.p0[1] < 1e-4 and s.p1[1] > s.p0[1]]  # omhoog vanaf de onderkant
    assert na and math.isclose(na[0].energie, 1.0, rel_tol=1e-9)
    # niets verlaat het blok door de onderkant
    assert not any(s.p1[1] < -1e-6 for s in segs)


def test_60_graden_op_verf_niet_teruggekaatst_als_spiegel(monkeypatch):
    monkeypatch.setattr(m, "MAX_DIEPTE", 1)  # alleen de eerste botsing en haar kinderen
    opst = m.Opstelling("t", "verf", "kaal")
    r = math.radians(60.0)
    d = np.array([math.sin(r), -math.cos(r)])
    segs = m.trace(opst, [m.Straal(np.array([30.0, 1.0]), d, 1.0, 0, True)])
    na = [s for s in segs if s.p0[1] < 1e-4 and s.p1[1] > s.p0[1]]
    assert na
    assert math.isclose(sum(s.energie for s in na), m.ALBEDO, rel_tol=1e-9)  # albedo, niet 1
    assert max(s.energie for s in na) < 0.5  # verdeeld over richtingen, geen spiegelstraal
    assert all(s.p1[1] >= -1e-6 for s in segs)  # in contact: niets de onderkant uit


def test_energiebehoud_kaal(monkeypatch):
    monkeypatch.setattr(m, "MAX_DIEPTE", 1)  # alleen de eerste botsing en haar kinderen
    # onder het kritieke punt: gereflecteerd + doorgelaten = 1
    opst = m.Opstelling("t", "kaal", "kaal")
    r = math.radians(20.0)
    d = np.array([math.sin(r), -math.cos(r)])
    segs = m.trace(opst, [m.Straal(np.array([30.0, 1.0]), d, 1.0, 0, True)])
    eerste = [s for s in segs if abs(s.p0[1]) < 1e-4]
    assert math.isclose(sum(s.energie for s in eerste), 1.0, rel_tol=1e-6)


def test_svg_bestanden(tmp_path):
    for opst in m.OPSTELLINGEN:
        svg = m.maak_svg(opst)
        assert svg.startswith("<svg") and opst.naam in svg and "40,8" in svg


def test_straal_uit_lucht_breekt_het_blok_in(monkeypatch):
    # inval onder 35 graden op het bovenvlak: gebroken hoek volgens Snellius, en het blok in
    opst = m.Opstelling("t", "kaal", "kaal")
    r = math.radians(35.0)
    d = np.array([-math.sin(r), -math.cos(r)])
    segs = m.trace(opst, [m.Straal(np.array([50.0, 60.0]), d, 1.0, 0, False)])
    binnen = [s for s in segs if s.p0[1] <= m.DIKTE + 1e-3 and s.p1[1] < s.p0[1] and s.p0[1] > m.DIKTE - 1e-3]
    s = binnen[0]
    hoek = math.atan2(abs(s.p1[0] - s.p0[0]), abs(s.p1[1] - s.p0[1]))
    assert math.isclose(math.sin(hoek) * N, math.sin(r), rel_tol=1e-6)
    assert s.energie < 1.0
