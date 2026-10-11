"""T06: inhoud in gietlagen. Config, reproduceerbaarheid, ligging in het volume, breking en energiebehoud."""

import mitsuba as mi
import numpy as np
import pytest
from pydantic import ValidationError

from carbonne.core.config import Flower, Layer, TableConfig, WoodSlice
from carbonne.core.inhoud import VERTICALE_MARGE_M, plaats_alles
from carbonne.core.scene import build_scene
from carbonne.core.variant import select_variant


def _cfg(seed=1, **kw) -> TableConfig:
    c = TableConfig(
        layers=[
            Layer(height_m=0.012, seed=seed, items=[WoodSlice(count=4), Flower(count=3)]),
            Layer(height_m=0.028, seed=seed + 1, items=[Flower(count=4, color=(1, 0.8, 0.1)), WoodSlice(count=2)]),
        ],
        **kw,
    )
    c.render.breedte, c.render.hoogte, c.render.spp = 96, 72, 16
    return c


def _geom(c):
    return [(i.soort, i.posities().round(9).tolist()) for laag in plaats_alles(c) for i in laag]


def test_config_rondreis_en_validatie():
    c = _cfg()
    assert TableConfig.model_validate_json(c.model_dump_json()) == c
    assert isinstance(c.layers[0].items[1], Flower)
    with pytest.raises(ValidationError):
        WoodSlice(color=(2, 0, 0))
    with pytest.raises(ValidationError):
        Layer(height_m=0.01, items=[{"type": "steen"}])


def test_zelfde_seed_zelfde_posities_andere_seed_anders():
    assert _geom(_cfg(1)) == _geom(_cfg(1))
    assert _geom(_cfg(1)) != _geom(_cfg(2))


def test_items_binnen_volume_zonder_overlap():
    for d in (0.35, 0.5):
        c = _cfg(diameter=d)
        lagen = plaats_alles(c)
        alle = [i for laag in lagen for i in laag]
        assert len(alle) == 4 + 3 + 4 + 2
        R = d / 2
        for i in alle:
            p = i.posities()
            assert np.hypot(p[:, 0], p[:, 2]).max() <= R - c.layers[0].edge_margin_mm * 1e-3 + 1e-9
            assert p[:, 1].min() >= VERTICALE_MARGE_M - 1e-9
            assert p[:, 1].max() <= c.hoogte - VERTICALE_MARGE_M + 1e-9
        for a in range(len(alle)):
            for b in range(a + 1, len(alle)):
                A, B = alle[a], alle[b]
                if A.y_bereik[1] < B.y_bereik[0] or B.y_bereik[1] < A.y_bereik[0]:
                    continue
                assert np.hypot(A.x - B.x, A.z - B.z) >= A.straal + B.straal


def test_te_veel_of_te_hoog_geeft_fout():
    c = TableConfig(layers=[Layer(height_m=0.04, items=[WoodSlice()])])  # middenvlak op bovenkant
    with pytest.raises(ValueError, match="buiten het blok"):
        plaats_alles(c)
    c = TableConfig(layers=[Layer(height_m=0.02, items=[WoodSlice(count=300, radius_mm=(14, 14))])])
    with pytest.raises(ValueError):
        plaats_alles(c)


def test_scene_bevat_inhoud_en_rendert():
    select_variant()
    c = _cfg()
    d = build_scene(c)
    assert sum(k.startswith("inhoud_") for k in d) == 13
    img = np.array(mi.render(mi.load_dict(d), spp=8))
    assert np.isfinite(img).all() and img.mean() > 0.01


def _render(d, spp):
    return np.array(mi.render(mi.load_dict(d), spp=spp))


def test_witte_schijf_in_furnace_behoudt_energie():
    """Constante omgeving 1, geen vloer, schijf met albedo 1 in het blok: overal L = 1. Een extra Fresnel-
    verlies of -winst rond het item zou hier zichtbaar zijn (de houtkleurvariatie wordt overschreven)."""
    select_variant()
    c = TableConfig(layers=[Layer(height_m=0.02, items=[WoodSlice(count=1, color=(1, 1, 1), radius_mm=(30, 30))])])
    c.render.breedte, c.render.hoogte, c.render.max_depth = 64, 64, 200
    c.scene.camera.positie, c.scene.camera.doel, c.scene.camera.fov = (0.0, 0.5, 0.25), (0, 0.03, 0), 30.0
    d = build_scene(c)
    del d["floor"]
    d = {k: v for k, v in d.items()}
    img = _render(d, 512)
    # schijf heeft albedo <= 1 (variatie 0,8..1,2 geknipt op 1), dus L <= 1 en dicht bij 1 in het hele beeld
    assert 0.9 < img.mean() <= 1.03


def test_schijnbare_diepte_volgt_snellius():
    """Een zwarte schijf op diepte d onder het bovenvlak, bekeken onder 45 graden door een smalle lens: het beeld
    van de schijf ligt op d*tan(theta_t)*cos(theta_i) van het punt boven de schijf (theta_t uit Snellius met
    n_d); zonder breking zou het d*tan(theta_i)*cos(theta_i) zijn."""
    select_variant()
    n = TableConfig().epoxy.n_d
    diepte, hoek, hoogte, L = 0.012, np.radians(45), 0.04, 2.0
    c = TableConfig(
        layers=[
            Layer(
                height_m=hoogte - diepte - 0.0005,
                items=[WoodSlice(color=(0, 0, 0), radius_mm=(8, 8), thickness_mm=1.0, irregularity=0.0)],
            )
        ]
    )
    it = plaats_alles(c)[0][0]
    doel = np.array([it.x, hoogte, it.z])
    c.render.breedte, c.render.hoogte, c.render.max_depth = 160, 160, 12
    c.scene.camera.positie = tuple(doel + L * np.array([np.sin(hoek), np.cos(hoek), 0.0]))
    c.scene.camera.doel = tuple(doel)
    c.scene.camera.fov = 2.0
    d = build_scene(c)
    del d["floor"]
    gem = _render(d, 128).mean(axis=2)
    ys, xs = np.nonzero(gem < 0.3)
    assert len(ys) > 200
    schaal = 2 * L * np.tan(np.radians(1.0)) / 160  # m per pixel in het beeldvlak
    omhoog = (80 - ys.mean()) * schaal
    zijwaarts = abs((xs.mean() - 80) * schaal)
    t = np.arcsin(np.sin(hoek) / n)
    verwacht = diepte * np.tan(t) * np.cos(hoek)  # ~4,4 mm
    zonder_breking = diepte * np.tan(hoek) * np.cos(hoek)  # 8,5 mm
    assert abs(abs(omhoog) - verwacht) < 0.0007, (omhoog, verwacht, zonder_breking)
    assert zijwaarts < 0.0007
