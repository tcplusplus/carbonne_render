import numpy as np
import pytest
from pydantic import ValidationError

from carbonne.core.config import TableConfig
from carbonne.core.scene import VLAKKEN, build_scene, cilinder_geometrie
from carbonne.core.variant import select_variant


@pytest.mark.parametrize("d,h", [(0.35, 0.04), (0.50, 0.02), (0.50, 0.06)])
def test_geometrie_gesloten_en_naar_buiten(d, h):
    geo = cilinder_geometrie(d, h, 64)
    # lassen: voeg samenvallende posities samen, elke kant moet in precies twee driehoeken zitten, tegengesteld
    alle_v = np.concatenate([g["v"] for g in geo.values()])
    sleutels = {tuple(np.round(v, 9)): i for i, v in reversed(list(enumerate(alle_v)))}
    kanten: dict[tuple[int, int], int] = {}
    volume = 0.0
    for g in geo.values():
        idx = np.array([sleutels[tuple(np.round(v, 9))] for v in g["v"]])
        for f in g["f"]:
            a, b, c = idx[f]
            for u, w in ((a, b), (b, c), (c, a)):
                kanten[(u, w)] = kanten.get((u, w), 0) + 1
        p = g["v"][g["f"]]
        volume += np.einsum("ij,ij->i", p[:, 0], np.cross(p[:, 1], p[:, 2])).sum() / 6
        # vlaknormaal komt overeen met de aangegeven vertexnormalen
        fn = np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0])
        vn = g["n"][g["f"]].mean(axis=1)
        assert (np.einsum("ij,ij->i", fn, vn) > 0).all()
    assert all(v == 1 for v in kanten.values())
    assert all((w, u) in kanten for (u, w) in kanten)  # gesloten, consistent georienteerd
    assert volume == pytest.approx(0.25 * np.pi * d**2 * h * _polygoon(64), rel=1e-6)
    assert volume > 0  # positief = normalen naar buiten


def _polygoon(n):  # oppervlak regelmatige n-hoek / cirkel
    return n * np.sin(2 * np.pi / n) / (2 * np.pi)


def test_validatie():
    for h in (0, -0.01, 0.01, 0.07):
        with pytest.raises(ValidationError):
            TableConfig(hoogte=h)
    with pytest.raises(ValidationError):
        TableConfig(diameter=0)


def test_json_rondreis():
    c = TableConfig(diameter=0.5, hoogte=0.03)
    assert TableConfig.model_validate_json(c.model_dump_json()) == c
    assert "diameter" in TableConfig.model_json_schema()["properties"]
    assert c.epoxy.n_d == pytest.approx(1.53, abs=1e-3)
    assert c.epoxy.ior(400) > c.epoxy.ior(700)


@pytest.mark.parametrize("d", [0.35, 0.5])
def test_render(d):
    import mitsuba as mi

    select_variant()
    c = TableConfig(diameter=d, hoogte=0.04)
    c.render.breedte, c.render.hoogte, c.render.spp = 64, 48, 8
    sc = build_scene(c)
    assert all(n in sc for n in VLAKKEN)
    img = np.array(mi.render(mi.load_dict(sc), spp=8))
    assert img.shape[:2] == (48, 64) and np.isfinite(img).all() and img.std() > 0
