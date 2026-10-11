import numpy as np
import pytest

from carbonne.core.config import TableConfig
from carbonne.core.environments import CAMERA_PRESETS, OMGEVINGEN, TAFEL_HOOGTE, camera_preset
from carbonne.core.scene import build_scene
from carbonne.core.variant import select_variant


def _config(omgeving=None, cam=None, spot=False):
    c = TableConfig(diameter=0.35)
    c.render.breedte, c.render.hoogte, c.render.spp = 64, 48, 8
    c.scene.omgeving, c.scene.camera_preset, c.scene.spot = omgeving, cam, spot
    return c


@pytest.mark.parametrize("naam", list(OMGEVINGEN))
def test_elke_omgeving_geldig_scenedict(naam, tmp_path, monkeypatch):
    import mitsuba as mi

    select_variant()
    monkeypatch.setenv("CARBONNE_ASSETS", str(tmp_path))  # leeg: valt terug op nep-HDRI en effen vloer
    sc = build_scene(_config(naam, "schuin30"))
    assert sc["env"]["type"] == "envmap" and "bitmap" in sc["env"]
    img = np.array(mi.render(mi.load_dict(sc), spp=8))
    assert np.isfinite(img).all() and img.std() > 0
    assert ("spot" in sc) == (OMGEVINGEN[naam].spot is not None)


@pytest.mark.parametrize("naam", list(OMGEVINGEN))
def test_omgeving_met_echte_assets(naam):
    """Gebruikt assets/ als die er zijn (scripts/fetch_assets.py), anders overgeslagen."""
    import mitsuba as mi

    from carbonne.core.environments import assets_dir

    om = OMGEVINGEN[naam]
    if om.hdri.bestand and not (assets_dir() / om.hdri.bestand).exists():
        pytest.skip("assets niet opgehaald")
    select_variant()
    sc = build_scene(_config(naam, "zittend"))
    img = np.array(mi.render(mi.load_dict(sc), spp=8))
    assert np.isfinite(img).all() and img.mean() > 0


def test_camerapresets_kijken_naar_tafel():
    for naam in CAMERA_PRESETS:
        cam = camera_preset(naam, 0.35, 0.04)
        d = np.array(cam.doel) - np.array(cam.positie)
        assert np.linalg.norm(d) > 0.5
    assert camera_preset("boven", 0.35, 0.04).positie[1] > 0.8
    def elevatie(n):
        c = camera_preset(n, 0.5, 0.04)
        return np.degrees(np.arctan2(c.positie[1] - c.doel[1], c.positie[2] - c.doel[2]))

    assert elevatie("schuin30") == pytest.approx(30, abs=0.01)
    assert elevatie("schuin60") == pytest.approx(60, abs=0.01)
    with pytest.raises(KeyError):
        camera_preset("onzin", 0.35, 0.04)


def test_vloer_hoogte():
    sc = build_scene(_config("studio"))
    # blad-bovenkant op 0,45 m boven de vloer: vloer op y = hoogte - TAFEL_HOOGTE
    m = sc["floor"]["to_world"]
    assert float(m.matrix[1, 3]) == pytest.approx(0.04 - TAFEL_HOOGTE)


def test_standaard_ongewijzigd():
    sc = build_scene(_config())
    assert sc["env"]["type"] == "constant" and "spot" not in sc


def test_spot_los_te_combineren():
    sc = build_scene(_config("studio", spot=True))
    assert sc["env"]["type"] == "envmap" and sc["spot"]["type"] == "spot"
