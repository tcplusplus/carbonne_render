"""T03: randafwerkingen. Scènedict-controles, eenstraals-BSDF-test en A/B-renders."""

import numpy as np
import pytest
from pydantic import ValidationError

from carbonne.core.config import Bare, MatteClearCoat, Paint, PlateBelow, TableConfig
from carbonne.core.scene import VLAKKEN, afwerking_bsdf, build_scene, effectieve_gap_mm
from carbonne.core.variant import select_variant

ROOD = (0.8, 0.05, 0.05)


def _cfg(**kw) -> TableConfig:
    c = TableConfig(**kw)
    c.render.breedte, c.render.hoogte, c.render.spp = 96, 72, 32
    return c


def test_config_union_json_rondreis():
    c = TableConfig(zijkant=Paint(color=ROOD), onderkant=PlateBelow(color=(1, 1, 1), gap_mm=0.2))
    assert TableConfig.model_validate_json(c.model_dump_json()) == c
    c2 = TableConfig.model_validate({"zijkant": {"type": "clearcoat"}, "onderkant": {"type": "bare"}})
    assert isinstance(c2.zijkant, MatteClearCoat) and c2.zijkant.roughness == 0.3
    with pytest.raises(ValidationError):
        TableConfig(zijkant=PlateBelow())  # plaat alleen onderkant
    with pytest.raises(ValidationError):
        Paint(color=(1.5, 0, 0))


def test_scenedict_per_afwerking():
    select_variant()
    c = _cfg()
    assert afwerking_bsdf(Bare(), c)["type"] == "dielectric"
    p = afwerking_bsdf(Paint(color=ROOD), c)
    assert p["type"] == "twosided" and p["front"]["type"] == "diffuse" and p["back"]["type"] == "diffuse"
    assert p["back"]["reflectance"]["value"] == list(ROOD)
    lak = afwerking_bsdf(MatteClearCoat(roughness=0.4), c)
    assert lak["type"] == "roughdielectric" and lak["alpha"] == 0.4 and lak["int_ior"] == pytest.approx(c.epoxy.n_d)
    with pytest.raises(NotImplementedError):
        afwerking_bsdf(Paint(kind="metallic"), c)

    sc = build_scene(_cfg(zijkant=Paint(color=ROOD), onderkant=PlateBelow(color=(1, 1, 1), gap_mm=0.1)))
    assert all(n in sc for n in VLAKKEN) and "plaat_boven" in sc
    assert "plaat_boven" not in build_scene(_cfg())
    # onderkant met plaat blijft een glad dielectric
    import mitsuba as mi

    scene = mi.load_dict(sc)
    ys = {s.id(): s.bbox().max.y for s in scene.shapes()}
    assert ys["plaat_boven"] == pytest.approx(-effectieve_gap_mm(_cfg(), 0.1) / 1000, abs=1e-7)
    assert effectieve_gap_mm(_cfg(), 5.0) == 5.0  # grote spleten blijven zoals ingesteld


def _sample(bsdf_dict: dict, wi_z_teken: int, hoek_deg: float, n: int = 4000):
    """Monster n stralen op de BSDF in het lokale vlak (normaal +z). wi_z_teken -1: straal van binnen
    (epoxykant), +1: van buiten. Geef (gemiddeld gewicht, fractie transmissie)."""
    import mitsuba as mi

    b = mi.load_dict(bsdf_dict)
    th = np.radians(hoek_deg)  # hoek met de normaal
    si = mi.SurfaceInteraction3f()
    si.wi = mi.Vector3f(mi.Float(np.full(n, np.sin(th))), mi.Float(np.zeros(n)), mi.Float(np.full(n, wi_z_teken * np.cos(th))))
    si.sh_frame = mi.Frame3f(mi.Normal3f(0, 0, 1))
    si.n = mi.Normal3f(0, 0, 1)
    si.wavelengths = mi.Spectrum([450.0, 520.0, 590.0, 650.0]) if mi.variant().endswith("spectral") else None
    rng = np.random.default_rng(1)
    bs, w = b.sample(
        mi.BSDFContext(), si, mi.Float(rng.random(n)), mi.Point2f(mi.Float(rng.random(n)), mi.Float(rng.random(n)))
    )
    gew = np.array(w[0])
    trans = np.array(bs.wo.z)
    ok = np.array(bs.pdf) > 0
    return float(gew[ok].mean()), float((trans[ok] * wi_z_teken < 0).mean())


def _gewicht_en_kant(bsdf_dict: dict, hoek_deg: float):
    return _sample(bsdf_dict, -1, hoek_deg)


def test_een_straal_tir_bare_tegenover_paint():
    select_variant()
    c = _cfg()
    # 60 graden > kritische hoek (~40.8 graden): Bare reflecteert alles terug, zonder verlies
    g, t = _gewicht_en_kant(afwerking_bsdf(Bare(), c), 60.0)
    assert t == 0.0 and g == pytest.approx(1.0, abs=1e-3)
    # dezelfde straal op Paint (albedo 0.2): diffuus, gewicht = albedo, geen TIR-gedrag
    g, t = _gewicht_en_kant(afwerking_bsdf(Paint(color=(0.2, 0.2, 0.2)), c), 60.0)
    assert t == 0.0 and g == pytest.approx(0.2, abs=0.01)
    # onder de kritische hoek (30 graden) gaat Bare grotendeels door (Fresnel ~4-5 % terug), Paint nooit,
    # en Paint heeft geen hoekafhankelijke Fresnel: gewicht blijft het albedo
    g, t = _gewicht_en_kant(afwerking_bsdf(Bare(), c), 30.0)
    assert t > 0.9
    g, t = _gewicht_en_kant(afwerking_bsdf(Paint(color=(0.2, 0.2, 0.2)), c), 30.0)
    assert t == 0.0 and g == pytest.approx(0.2, abs=0.01)
    # matte lak breekt de TIR gedeeltelijk: bij 60 graden gaat nu een deel toch door
    g, t = _gewicht_en_kant(afwerking_bsdf(MatteClearCoat(roughness=0.5), c), 60.0)
    assert 0.0 < t < 1.0


def test_paint_buitenkant_is_luchtkant():
    """Een straal van buiten (wi.z > 0) op Paint levert eveneens albedo-diffuus gedrag."""
    select_variant()
    g, t = _sample(afwerking_bsdf(Paint(color=(0.3, 0.3, 0.3)), _cfg()), +1, 20.0)
    assert t == 0.0 and g == pytest.approx(0.3, abs=0.01)


def _lum(cfg: TableConfig) -> float:
    import mitsuba as mi

    img = np.array(mi.render(mi.load_dict(build_scene(cfg)), spp=cfg.render.spp, seed=7))
    return float(img.mean())


@pytest.mark.parametrize(
    "zijkant,onderkant",
    [
        (Bare(), Bare()),
        (Paint(color=ROOD), Bare()),
        (Bare(), Paint(color=ROOD)),
        (Bare(), MatteClearCoat()),
        (Bare(), PlateBelow(color=(0.9, 0.9, 0.9))),
        (MatteClearCoat(), Bare()),
    ],
)
def test_elke_optie_rendert(zijkant, onderkant):
    select_variant()
    import mitsuba as mi

    c = _cfg(zijkant=zijkant, onderkant=onderkant)
    img = np.array(mi.render(mi.load_dict(build_scene(c)), spp=c.render.spp))
    assert np.isfinite(img).all() and img.std() > 0


def test_ab_witte_plaat_tegenover_witte_verf_en_onbehandeld():
    """Onderkant: onbehandeld, wit geverfd en plaat met luchtspleet geven meetbaar verschillende beelden."""
    select_variant()
    wit = (0.9, 0.9, 0.9)
    a = _lum(_cfg(onderkant=Bare()))
    b = _lum(_cfg(onderkant=Paint(color=wit)))
    p = _lum(_cfg(onderkant=PlateBelow(color=wit)))
    assert abs(a - b) > 0.002 and abs(b - p) > 0.0005


def test_plaat_gelijkmatig_zichtbaar_geen_ray_epsilon_artefact():
    """Van boven gezien is de plaat overal even helder (geen donker gebied bij kleine spleet)."""
    select_variant()
    import mitsuba as mi

    c = _cfg(onderkant=PlateBelow(color=(0.2, 0.9, 0.2), gap_mm=0.1))
    c.scene.camera.positie = (0.0, 0.7, 0.02)
    c.render.breedte = c.render.hoogte = 96
    img = np.array(mi.render(mi.load_dict(build_scene(c)), spp=64))
    midden = img[44:52, 44:52, 1].mean()
    rand = img[44:52, 73:79, 1].mean()  # ~0,14-0,16 m van het midden (buiten het L-oneindig-vlak van 0,11 m)
    assert rand > 0.8 * midden
