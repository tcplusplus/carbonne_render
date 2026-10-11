"""T17: absorptie en verstrooiing in de epoxy (homogeen medium, volpath) en ruw bovenvlak."""

import numpy as np
import pytest

from carbonne.core.config import EpoxyMaterial, TableConfig
from carbonne.core.scene import build_scene, epoxy_medium
from carbonne.core.variant import select_variant

N = 1.530
EXT = 1.000277


@pytest.fixture(scope="module", autouse=True)
def _variant():
    select_variant()


def _plaat(medium: dict | None, dikte: float = 0.02, spp: int = 256) -> float:
    """Epoxyplaat (kubus, zeer breed) in een witte constante omgeving; geeft de gemiddelde pixel."""
    import mitsuba as mi

    sc = {
        "type": "scene",
        "integrator": {"type": "volpath", "max_depth": 200},
        "sensor": {
            "type": "perspective",
            "fov": 2.0,
            "to_world": mi.ScalarTransform4f().look_at(origin=[0, 0, 3], target=[0, 0, 0], up=[0, 1, 0]),
            "film": {"type": "hdrfilm", "width": 16, "height": 16, "rfilter": {"type": "box"}},
            "sampler": {"type": "independent", "sample_count": spp},
        },
        "env": {"type": "constant", "radiance": {"type": "rgb", "value": [1.0, 1.0, 1.0]}},
        "plaat": {
            "type": "cube",
            "to_world": mi.ScalarTransform4f().scale([5, 5, dikte / 2]),
            "bsdf": {"type": "dielectric", "int_ior": N, "ext_ior": EXT},
        },
    }
    if medium is not None:
        sc["medium"] = medium
        sc["plaat"]["interior"] = {"type": "ref", "id": "medium"}
    return float(np.array(mi.render(mi.load_dict(sc), seed=3))[..., :3].mean())


def test_standaard_geen_medium_en_path():
    c = TableConfig()
    assert not c.epoxy.heeft_medium
    assert epoxy_medium(c) is None
    sd = build_scene(c)
    assert sd["integrator"]["type"] == "path"
    assert sd["boven"].interior_medium() is None
    assert c.top_roughness == 0.0


def test_scene_met_medium_gebruikt_volpath_en_alle_blokvlakken():
    c = TableConfig()
    c.epoxy.scattering_coeff = 20.0
    sd = build_scene(c)
    assert sd["integrator"]["type"] == "volpath"
    for naam in ("boven", "mantel", "onder"):
        assert sd[naam].interior_medium() is not None


def test_absorptie_via_epoxy_medium_is_beer_lambert():
    """Zelfde formule als tests/test_physics.py, maar nu via de spectrale curve van EpoxyMaterial."""
    sigma, d = 50.0, 0.02
    ep = EpoxyMaterial(absorptie_nm=[400.0, 700.0], absorptie_per_m=[sigma, sigma])
    c = TableConfig(epoxy=ep)
    r = ((N - EXT) / (N + EXT)) ** 2
    x = np.exp(-sigma * d)
    t = (1 - r) ** 2 * x / (1 - r**2 * x**2)
    r_tot = r + (1 - r) ** 2 * r * x**2 / (1 - r**2 * x**2)
    assert _plaat(epoxy_medium(c), d) == pytest.approx(t + r_tot, abs=0.006)


def test_verstrooiing_zonder_absorptie_behoudt_energie():
    """Albedo 1: alles wat de plaat ingaat komt er weer uit; in een witte omgeving blijft de pixel 1."""
    for g in (0.0, 0.6):
        c = TableConfig(epoxy=EpoxyMaterial(scattering_coeff=150.0, scattering_g=g))
        assert _plaat(epoxy_medium(c), 0.02, spp=512) == pytest.approx(1.0, abs=0.01)


def test_verstrooiing_met_absorptie_verliest_energie():
    c = TableConfig(epoxy=EpoxyMaterial(scattering_coeff=150.0, absorptie_per_m=[20.0, 20.0]))
    assert _plaat(epoxy_medium(c), 0.02, spp=512) < 0.97


def test_albedo_per_golflengte():
    """Absorptie die met de golflengte toeneemt geeft een albedo die afneemt."""
    ep = EpoxyMaterial(absorptie_nm=[400.0, 700.0], absorptie_per_m=[0.0, 100.0], scattering_coeff=100.0)
    d = epoxy_medium(TableConfig(epoxy=ep))
    nm = [w for w, _ in d["albedo"]["value"]]
    al = dict(d["albedo"]["value"])
    assert al[400.0] == pytest.approx(1.0) and al[700.0] == pytest.approx(0.5)
    assert min(nm) < 400 and max(nm) > 700  # afgedekt tot het hele spectrale bereik


def test_ruw_bovenvlak_wordt_roughdielectric():
    c = TableConfig(top_roughness=0.03)
    assert "RoughDielectric" in str(build_scene(c)["boven"].bsdf())


def test_validatie():
    with pytest.raises(ValueError):
        EpoxyMaterial(scattering_coeff=-1.0)
    with pytest.raises(ValueError):
        EpoxyMaterial(scattering_g=1.0)
    with pytest.raises(ValueError):
        TableConfig(top_roughness=-0.1)


def test_herkomst_weigert_medium():
    from carbonne.render import RenderOpties, render

    c = TableConfig(epoxy=EpoxyMaterial(scattering_coeff=10.0))
    c.render.breedte, c.render.hoogte = 32, 24
    with pytest.raises(ValueError, match="medium"):
        render(c, RenderOpties(integrator="herkomst", cache=False, max_spp=2))
