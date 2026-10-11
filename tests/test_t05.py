"""T05: kleurinvoer (hex, RAL) en verftypes (matte, gloss, metallic, candy)."""

import numpy as np
import pytest
from pydantic import ValidationError

from carbonne.core.config import Paint, PlateBelow, TableConfig
from carbonne.core.kleur import hex_naar_lineair, lineair_naar_srgb, parse_kleur, ral_tabel
from carbonne.core.scene import afwerking_bsdf, build_scene, candy_kleur, verf_bsdf
from carbonne.core.variant import select_variant

GRIJS = (0.5, 0.5, 0.5)


def _cfg(**kw) -> TableConfig:
    c = TableConfig(**kw)
    c.render.breedte, c.render.hoogte, c.render.spp = 64, 48, 16
    return c


# --- kleurinvoer -------------------------------------------------------------------------------------------
def test_hex_naar_lineair_en_terug():
    assert parse_kleur("#ffffff") == pytest.approx((1, 1, 1))
    assert parse_kleur("#000000") == (0, 0, 0)
    r = parse_kleur("#808080")
    assert r[0] == pytest.approx(0.2158, abs=1e-3)  # sRGB 128 -> lineair 0,216
    assert lineair_naar_srgb(r[0]) * 255 == pytest.approx(128, abs=0.01)
    assert parse_kleur("#f00") == parse_kleur("#ff0000") == (1.0, 0.0, 0.0)
    assert parse_kleur("FF0000") == (1.0, 0.0, 0.0)


@pytest.mark.parametrize("tekst", ["RAL 9005", "ral9005", "RAL9005", "ral-9005", "9005", " RAL 9005 "])
def test_ral_schrijfwijzen(tekst):
    assert parse_kleur(tekst) == hex_naar_lineair("#131516")  # Jet black


def test_ral_tabel_compleet_en_geldig():
    t = ral_tabel()
    assert len(t) >= 200
    for code in ("1000", "3020", "5002", "6018", "9001", "9005", "9010"):
        assert code in t
    assert all(len(h) == 6 and int(h, 16) >= 0 for h, _ in t.values())
    assert parse_kleur("RAL 3020")[0] > parse_kleur("RAL 3020")[2]  # verkeersrood is rood


@pytest.mark.parametrize("fout", ["", "rood", "#12345", "#gg0000", "RAL 0000", "RAL 99999", "RAL", "#1234567"])
def test_ongeldige_kleur(fout):
    with pytest.raises(ValueError):
        parse_kleur(fout)


def test_config_accepteert_tekstkleur_en_json_rondreis():
    p = Paint(color="RAL 3020")
    assert p.color == parse_kleur("RAL 3020")
    assert PlateBelow(color="#102030").color == parse_kleur("#102030")
    c = TableConfig(zijkant=Paint(color="#ff8800", kind="gloss"))
    assert c.zijkant.kind == "glossy"
    assert TableConfig.model_validate_json(c.model_dump_json()) == c
    with pytest.raises(ValidationError):
        Paint(color="geen kleur")
    with pytest.raises(ValidationError):
        Paint(kind="chroom")


# --- verftypes: scenedict ----------------------------------------------------------------------------------
def test_scenedict_per_soort():
    select_variant()
    c = _cfg()
    typ = lambda kind, **kw: afwerking_bsdf(Paint(color=GRIJS, kind=kind, **kw), c)  # noqa: E731
    m = typ("matte")
    assert m["front"]["type"] == m["back"]["type"] == "diffuse"
    g = typ("glossy")
    assert g["front"]["type"] == "roughplastic" and g["front"]["alpha"] == 0.05 and g["back"]["type"] == "diffuse"
    assert typ("glossy", roughness=0.2)["front"]["alpha"] == 0.2
    me = typ("metallic")
    assert me["front"]["type"] == me["back"]["type"] == "roughconductor"
    assert me["front"]["specular_reflectance"]["value"] == list(GRIJS)
    cm = typ("candy")  # standaard metalen ondergrond
    assert cm["front"]["type"] == "roughconductor"
    assert cm["front"]["specular_reflectance"]["value"] == pytest.approx([0.25] * 3)
    cw = typ("candy", candy_base="white")
    assert cw["front"]["type"] == "roughplastic" and cw["back"]["type"] == "diffuse"
    assert cw["back"]["reflectance"]["value"] == pytest.approx(candy_kleur(GRIJS))


def test_plaat_neemt_verftype():
    select_variant()
    import mitsuba as mi

    sc = build_scene(_cfg(onderkant=PlateBelow(color=GRIJS, kind="metallic")))
    assert "plaat_boven" in sc
    mi.load_dict(sc)


# --- verftypes: eenstraals-BSDF (zie test_t03._sample) -----------------------------------------------------
def _enkel(bsdf: dict, wi_z: int, hoek: float, n: int = 3000):
    from test_t03 import _sample

    return _sample(bsdf, wi_z, hoek, n)


def test_gewichten_komen_uit_de_kleur():
    select_variant()
    k = (0.6, 0.6, 0.6)
    # metallic: ideale metaalkleur, alles gereflecteerd, gewicht = specular_reflectance
    g, t = _enkel(verf_bsdf(Paint(color=k, kind="metallic"), binnen=False), +1, 20.0)
    # (GGX-monsters die onder de horizon vallen, enkele procenten bij alpha 0,25, geven gewicht 0)
    assert t < 0.1 and g == pytest.approx(0.6, abs=0.06)
    # candy op metaal: transmissie^2 = 0,36
    g, t = _enkel(verf_bsdf(Paint(color=k, kind="candy"), binnen=False), +1, 20.0)
    assert t < 0.1 and g == pytest.approx(0.36, abs=0.04)
    # candy op wit, epoxykant: diffuus met kleur^2
    g, t = _enkel(verf_bsdf(Paint(color=k, kind="candy", candy_base="white"), binnen=True), -1, 50.0)
    assert t == 0.0 and g == pytest.approx(0.36, abs=0.01)
    # gloss, epoxykant: pigment alleen, zoals matte (geen lak/lucht-grensvlak in contact)
    g, t = _enkel(verf_bsdf(Paint(color=k, kind="glossy"), binnen=True), -1, 50.0)
    assert t == 0.0 and g == pytest.approx(0.6, abs=0.01)


def _eval_spiegel(bsdf: dict, hoek: float, afwijking: float) -> float:
    """BSDF-waarde (eval, zonder cos-factor weggelaten: zoals Mitsuba) voor wo = spiegelrichting + afwijking."""
    import mitsuba as mi

    th = np.radians(hoek)
    si = mi.SurfaceInteraction3f()
    si.wi = mi.Vector3f(float(np.sin(th)), 0.0, float(np.cos(th)))
    si.sh_frame = mi.Frame3f(mi.Normal3f(0, 0, 1))
    si.n = mi.Normal3f(0, 0, 1)
    si.wavelengths = mi.Spectrum([450.0, 520.0, 590.0, 650.0]) if mi.variant().endswith("spectral") else None
    ta = np.radians(hoek + afwijking)
    wo = mi.Vector3f(float(-np.sin(ta)), 0.0, float(np.cos(ta)))
    return float(np.array(mi.load_dict(bsdf).eval(mi.BSDFContext(), si, wo)[0]).mean())


def test_gloss_heeft_spiegelpiek_matte_niet():
    select_variant()
    k = (0.5, 0.5, 0.5)
    pk = lambda kind: _eval_spiegel(verf_bsdf(Paint(color=k, kind=kind), binnen=False), 30.0, 0.0)  # noqa: E731
    af = lambda kind: _eval_spiegel(verf_bsdf(Paint(color=k, kind=kind), binnen=False), 30.0, 25.0)  # noqa: E731
    assert pk("glossy") > 3 * pk("matte")  # piek in de spiegelrichting
    assert af("glossy") < 1.1 * af("matte")  # ver van de piek: alleen het pigment
    assert pk("metallic") > 3 * pk("matte") and af("metallic") < 0.5 * pk("metallic")
    # ruwer metaal: lagere en bredere piek
    ruw = _eval_spiegel(verf_bsdf(Paint(color=k, kind="metallic", roughness=0.6), binnen=False), 30.0, 0.0)
    assert ruw < pk("metallic")


@pytest.mark.parametrize("kind", ["matte", "glossy", "metallic", "candy"])
@pytest.mark.parametrize("plek", ["zijkant", "onderkant", "plaat"])
def test_elke_soort_rendert_op_elke_plek(kind, plek):
    select_variant()
    import mitsuba as mi

    kleur = (0.7, 0.1, 0.1)
    f = {
        "zijkant": dict(zijkant=Paint(color=kleur, kind=kind)),
        "onderkant": dict(onderkant=Paint(color=kleur, kind=kind)),
        "plaat": dict(onderkant=PlateBelow(color=kleur, kind=kind)),
    }[plek]
    c = _cfg(**f)
    img = np.array(mi.render(mi.load_dict(build_scene(c)), spp=c.render.spp))
    assert np.isfinite(img).all() and img.std() > 0
