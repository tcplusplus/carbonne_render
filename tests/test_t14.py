"""T14: wat-als-reeks (parameterpaden, ΔE2000, reproduceerbaarheid, uitvoer, annuleren)."""

from __future__ import annotations

import json
import threading

import pytest

from carbonne.analyse.cli import main, parse_waarden
from carbonne.analyse.reeks import delta_e2000, reeks, waarde_label, zet_pad
from carbonne.analyse.uitvoer import contactblad_png, grafiek_png, schrijf_reeks
from carbonne.core.config import MatteClearCoat, Paint, PlateBelow, TableConfig


def cfg(**kw) -> TableConfig:
    return TableConfig(**kw)


def test_pad_scalar_kleur_en_afwerking():
    c = cfg(zijkant=Paint(color=(0.5, 0.1, 0.1)))
    assert zet_pad(c, "hoogte", 0.05).hoogte == 0.05
    assert c.hoogte == 0.04  # origineel ongemoeid
    assert zet_pad(c, "zijkant.color", "#00ff00").zijkant.color[1] == pytest.approx(1.0)
    assert zet_pad(c, "zijkant.color", "RAL 3020").zijkant.color[0] > 0.3
    assert zet_pad(c, "scene.camera.fov", 30).scene.camera.fov == 30
    n = zet_pad(c, "onderkant", PlateBelow(color=(0, 0, 0), gap_mm=1))
    assert isinstance(n.onderkant, PlateBelow) and n.onderkant.gap_mm == 1
    assert isinstance(zet_pad(c, "onderkant", MatteClearCoat()).onderkant, MatteClearCoat)
    assert zet_pad(c, "onderkant", {"type": "paint", "color": [0, 0, 0]}).onderkant.color == (0, 0, 0)
    p = zet_pad(zet_pad(c, "onderkant", PlateBelow()), "onderkant.gap_mm", 2.0)
    assert p.onderkant.gap_mm == 2.0
    assert zet_pad(c, "scene.camera", {"fov": 55.0}).scene.camera.fov == 55.0


def test_pad_fouten_zijn_duidelijk():
    c = cfg()
    with pytest.raises(ValueError, match="bestaat niet"):
        zet_pad(c, "hoogt", 0.05)
    with pytest.raises(ValueError, match="bestaat niet"):
        zet_pad(c, "epoxy.bestaatniet", 1)
    with pytest.raises(ValueError, match="geen onderdelen"):
        zet_pad(c, "hoogte.x", 1)
    with pytest.raises(ValueError, match="geldige index"):
        zet_pad(c, "layers.0.height_m", 0.02)
    with pytest.raises(ValueError, match="ongeldige waarde"):
        zet_pad(c, "hoogte", 0.5)  # boven de grens
    with pytest.raises(ValueError, match="bestaat niet"):
        zet_pad(c, "zijkant.color", "#ff0000")  # zijkant is kaal: heeft geen kleur
    with pytest.raises(ValueError, match="ongeldige waarde"):
        zet_pad(cfg(zijkant=Paint()), "zijkant.color", "geenkleur")
    with pytest.raises(ValueError, match="parameterpad is leeg"):
        zet_pad(c, "", 1)
    with pytest.raises(ValueError):
        reeks(c, "hoogte", [0.03, 0.9], (5, 5))  # faalt vooraf, vóór er gerenderd is


def test_delta_e2000_sharma():
    # referentiewaarden uit Sharma, Wu & Dalal (2005), tabel 1
    assert delta_e2000((50, 2.6772, -79.7751), (50, 0, -82.7485)) == pytest.approx(2.0425, abs=1e-3)
    assert delta_e2000((50, 2.5, 0), (73, 25, -18)) == pytest.approx(27.1492, abs=1e-3)
    assert delta_e2000((50, 3, 4), (50, 3, 4)) == 0


def test_labels_en_parse():
    assert waarde_label(0.03) == "0.03"
    assert waarde_label(PlateBelow(color=(0, 0, 0), gap_mm=1)) == "plaat #000000 1mm"
    assert waarde_label(MatteClearCoat()) == "matte lak r0.3"
    assert parse_waarden("0.02,0.03") == [0.02, 0.03]
    assert parse_waarden("#ff0000,RAL 3020") == ["#ff0000", "RAL 3020"]
    assert parse_waarden('[[1,0,0],{"type":"bare"}]') == [[1, 0, 0], {"type": "bare"}]


def klein() -> TableConfig:
    c = cfg(zijkant=Paint(color=(0.75, 0.04, 0.04)), onderkant=Paint(color=(0.9, 0.9, 0.9)))
    c.render.breedte, c.render.hoogte = 64, 64
    return c


def test_reeks_reproduceerbaar_en_uitvoer(tmp_path):
    c = klein()
    voortgang = []
    kw = {"breedte": 48, "spp": 32, "cache": False, "on_progress": lambda i, n, lab: voortgang.append((i, n, lab))}
    r1 = reeks(c, "hoogte", [0.03, 0.05], (24, 24), **kw)
    r2 = reeks(c, "hoogte", [0.03, 0.05], (24, 24), **kw)
    # zelfde zaad: gelijk op float-afronding na (de threads tellen in wisselende volgorde op)
    for a, b in zip(r1.metingen, r2.metingen, strict=True):
        assert a.rgb == pytest.approx(b.rgb, rel=1e-5)
        assert a.ruis_lab == pytest.approx(b.ruis_lab, rel=1e-3, abs=1e-5)
    r3 = reeks(c, "hoogte", [0.03, 0.05], (24, 24), seed=7, **{**kw, "on_progress": None})
    assert r3.metingen[0].rgb != pytest.approx(r1.metingen[0].rgb, rel=1e-5)
    assert voortgang[:2] == [(1, 2, "0.03"), (2, 2, "0.05")]
    m0, m1 = r1.metingen
    assert m0.de2000 == 0 and not m0.binnen_ruis and m1.ruis_lab > 0
    assert m0.lch[0] == pytest.approx(m0.lab[0])
    assert abs(sum(cat.aandeel_pct for cat in m0.herkomst.categorieen) - 100) < 1e-6
    assert r1.beelden[0].shape == (48, 48, 3)
    paden = schrijf_reeks(r1, tmp_path)
    for p in paden.values():
        assert p.stat().st_size > 100
    j = json.loads(paden["json"].read_text())
    assert j["parameter"] == "hoogte" and len(j["metingen"]) == 2 and "beelden" not in j
    assert j["metingen"][0]["herkomst"]["categorieen"]
    assert paden["contact"].read_bytes()[:4] == b"\x89PNG"


def test_afwerkingsobjecten_en_rechthoek():
    c = klein()
    r = reeks(c, "onderkant", [Paint(color=(0, 0, 0)), MatteClearCoat()], (10, 10, 30, 30), breedte=40, spp=16, cache=False)
    assert len(r.metingen) == 2 and r.metingen[1].label.startswith("matte lak")
    assert contactblad_png(r)[:4] == b"\x89PNG" and grafiek_png(r)[:4] == b"\x89PNG"  # niet-numerieke waarden


def test_annuleren():
    ev = threading.Event()
    ev.set()
    r = reeks(klein(), "hoogte", [0.03, 0.05], (5, 5), breedte=32, spp=16, cache=False, annuleer=ev)
    assert r.geannuleerd and r.metingen == []
    ev2 = threading.Event()
    r = reeks(klein(), "hoogte", [0.03, 0.05], (5, 5), breedte=32, spp=16, cache=False, annuleer=ev2,
              on_progress=lambda i, n, lab: ev2.set())
    assert r.geannuleerd and len(r.metingen) == 1


def test_cli(tmp_path, capsys):
    p = tmp_path / "c.json"
    p.write_text(klein().model_dump_json())
    a = ["--param", "hoogte", "--waarden", "0.03,0.05", "--punt", "16,16", "--breedte", "32", "--spp", "16",
         "--geen-cache", "-o", str(tmp_path / "uit")]
    assert main([str(p), *a]) == 0
    assert (tmp_path / "uit" / "reeks.json").exists()
    assert "0.05" in capsys.readouterr().out
    assert main([str(p), "--param", "hoogtee", "--waarden", "1", "--punt", "1,1"]) == 2
