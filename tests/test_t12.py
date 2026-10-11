"""T12: kalibratie met een gsm-foto (witbalans op papier, gemeten verfkleur, vergelijking in dE2000)."""

import json

import numpy as np
import pytest

from carbonne.core.config import Paint, SceneConfig, TableConfig
from carbonne.kalibratie import kern
from carbonne.kalibratie.cli import kalibreer, main, zet_verfkleur

PAPIER = (0, 0, 20, 20)
STAAL = (30, 0, 50, 20)


def _tafereel(albedo, licht=(0.9, 0.8, 0.7)):
    """64x32 beeld: links papier (albedo 0,85) en een staal, onder een gekleurd licht."""
    img = np.zeros((32, 64, 3))
    img[:] = 0.3 * np.asarray(licht)
    img[0:20, 0:20] = 0.85 * np.asarray(licht)
    img[0:20, 30:50] = np.asarray(albedo) * np.asarray(licht)
    return img


def test_normaliseren_haalt_lichtkleur_en_belichting_weg():
    alb = (0.4, 0.1, 0.05)
    a = kern.normaliseer(_tafereel(alb, (0.9, 0.8, 0.7)), PAPIER)
    b = kern.normaliseer(_tafereel(alb, (0.3, 0.4, 0.5)), PAPIER)
    assert np.allclose(a, b, atol=1e-9)
    assert np.allclose(kern.roi_gemiddelde(a, PAPIER), 0.85)
    m = kern.meet_verfkleur(_tafereel(alb, (0.3, 0.4, 0.5)), PAPIER, STAAL)
    assert np.allclose(m["rgb"], alb, atol=1e-9) and not m["afgekapt"]
    assert m["hex"] == kern.rgb_naar_hex(alb)


def test_roi_fouten_en_overbelichting():
    img = _tafereel((0.4, 0.1, 0.05))
    with pytest.raises(ValueError, match="buiten het beeld"):
        kern.roi_gemiddelde(img, (100, 100, 120, 120))
    with pytest.raises(ValueError, match="overbelicht"):
        kern.normaliseer(img * 1.3, PAPIER)
    with pytest.raises(ValueError, match="zwart"):
        kern.normaliseer(img * 0, PAPIER)
    assert kern.meet_verfkleur(img, PAPIER, STAAL, papier_albedo=0.3)["afgekapt"] in (False, True)


def test_vergelijk_en_bijstellen():
    f = kern.normaliseer(_tafereel((0.4, 0.1, 0.05)), PAPIER)
    r = kern.normaliseer(_tafereel((0.5, 0.1, 0.05)), PAPIER)
    geb = [{"naam": "staal", "foto": STAAL, "render": STAAL}, {"naam": "papier", "foto": PAPIER, "render": PAPIER}]
    v = kern.vergelijk(f, r, geb)
    assert v[1].de2000 < 1e-9 and v[0].de2000 > 2 and v[0].d_l < 0  # foto donkerder dan render
    nieuw = kern.bijgestelde_verf((0.5, 0.1, 0.05), v[0].rgb_foto, v[0].rgb_render)
    assert np.allclose(nieuw, (0.4, 0.1, 0.05), atol=1e-9)
    assert kern.vergelijk(f, f, geb)[0].de2000 == 0


def test_zet_verfkleur_alleen_op_verf():
    c = TableConfig(zijkant=Paint(color="#ff0000", kind="gloss"))
    assert zet_verfkleur(c, "zijkant", (0.1, 0.2, 0.3)).zijkant.kind == "glossy"
    with pytest.raises(ValueError, match="geen verf"):
        zet_verfkleur(c, "onderkant", (0.1, 0.2, 0.3))


def test_png_rondrit_en_cli(tmp_path, capsys):
    img8 = kern.synthetische_foto(_tafereel((0.4, 0.1, 0.05)), (0.9, 0.9, 0.9), 0.0)
    pad = tmp_path / "foto.png"
    pad.write_bytes(kern.foto_naar_png(img8))
    lin = kern.laad_foto(pad)
    assert lin.shape == (32, 64, 3)
    assert abs(lin[5, 5, 0] - kern.srgb_naar_lineair_arr(img8[5, 5, 0] / 255)) < 2e-3
    plan = {"papier_foto": PAPIER, "staal": [{"verf": "zijkant", "foto": STAAL}]}
    (tmp_path / "p.json").write_text(json.dumps(plan))
    assert main(["meet", str(pad), str(tmp_path / "p.json")]) == 0
    assert "zijkant" in capsys.readouterr().out
    assert main(["raster", str(pad), "-o", str(tmp_path / "r.png"), "--stap", "16"]) == 0
    assert (tmp_path / "r.png").stat().st_size > 100
    plan["papier_foto"] = (500, 500, 510, 510)
    (tmp_path / "p.json").write_text(json.dumps(plan))
    assert main(["meet", str(pad), str(tmp_path / "p.json")]) == 2


def test_hele_keten_met_synthetische_foto_en_render():
    """Echte (kleine) render: de foto komt van een tafeltje met andere verf, kleurzweem en belichting; de gemeten
    kleur herstelt de verf en dE2000 daalt van duidelijk zichtbaar naar onder 1."""
    from carbonne.core.config import RenderSettings

    papier, staal, zijkant = (255, 195, 310, 232), (8, 8, 48, 40), (110, 168, 210, 182)
    cfg = TableConfig(zijkant=Paint(color="RAL 3020"), onderkant=Paint(color="#dddddd"),
                      scene=SceneConfig(camera_preset="schuin30"), render=RenderSettings(breedte=320, hoogte=240))
    waar = kern.parse_hex("#8a2a1c")
    from carbonne.kalibratie.cli import render_lineair

    r = render_lineair(zet_verfkleur(cfg, "zijkant", waar), 0.85, 64, 0.05)
    vlak = {staal: tuple(np.asarray(waar) * kern.roi_gemiddelde(r, papier) / 0.85)}
    foto = kern.srgb_naar_lineair_arr(kern.synthetische_foto(r, (1.25, 1.0, 0.72), -1.0, 0.0, vlak) / 255.0)
    plan = {"papier_foto": papier, "papier_render": papier, "staal": [{"verf": "zijkant", "foto": staal}],
            "gebieden": [{"naam": "zijkant", "foto": zijkant, "render": zijkant, "verf": "zijkant"}]}
    voor = kalibreer(cfg, foto, {**plan, "staal": []}, spp=64, ruisdrempel=0.05)
    na = kalibreer(cfg, foto, plan, spp=64, ruisdrempel=0.05)
    assert voor["verschillen"][0].de2000 > 5
    assert na["verschillen"][0].de2000 < 1.0
    assert np.allclose(na["gemeten"]["zijkant"]["rgb"], waar, atol=0.01)
