"""T04: analytische fysicatests in kleine scenes: Fresnel, kritische hoek, Beer-Lambert."""

import numpy as np
import pytest

from carbonne.core.variant import select_variant

N = 1.530  # vaste IOR (plan §2)
EXT = 1.000277


def _r0(n: float = N, ext: float = EXT) -> float:
    return ((n - ext) / (n + ext)) ** 2


def _fresnel_onverpol(cos_i: float, n1: float, n2: float) -> float:
    """Analytische Fresnel-reflectie (gemiddeld over polarisaties) van medium n1 naar n2."""
    sin_t = n1 / n2 * np.sqrt(max(0.0, 1 - cos_i**2))
    if sin_t >= 1:
        return 1.0
    cos_t = np.sqrt(1 - sin_t**2)
    rs = ((n1 * cos_i - n2 * cos_t) / (n1 * cos_i + n2 * cos_t)) ** 2
    rp = ((n1 * cos_t - n2 * cos_i) / (n1 * cos_t + n2 * cos_i)) ** 2
    return 0.5 * (rs + rp)


def _plaatscene(dikte: float | None, sigma: float = 0.0, spp: int = 256, achter_zwart: bool = False) -> dict:
    """Camera op z=3 kijkt langs -z naar een epoxyplaat (kubus, dikte `dikte`, zeer breed) in een witte
    constante omgeving (radiantie 1). `dikte` None: een enkel grensvlak (dun rechthoek) met zwarte achterkant."""
    import mitsuba as mi

    sc: dict = {
        "type": "scene",
        "integrator": {"type": "volpath", "max_depth": 64},
        "sensor": {
            "type": "perspective",
            "fov": 2.0,
            "to_world": mi.ScalarTransform4f().look_at(origin=[0, 0, 3], target=[0, 0, 0], up=[0, 1, 0]),
            "film": {"type": "hdrfilm", "width": 16, "height": 16, "rfilter": {"type": "box"}},
            "sampler": {"type": "independent", "sample_count": spp},
        },
        "env": {"type": "constant", "radiance": {"type": "rgb", "value": [1.0, 1.0, 1.0]}},
    }
    diel = {"type": "dielectric", "int_ior": N, "ext_ior": EXT}
    if dikte is None:
        sc["vlak"] = {"type": "rectangle", "to_world": mi.ScalarTransform4f().scale(5), "bsdf": diel}
        sc["zwart"] = {
            "type": "rectangle",
            "to_world": mi.ScalarTransform4f().translate([0, 0, -0.5]).scale(5),
            "bsdf": {"type": "diffuse", "reflectance": {"type": "rgb", "value": [0, 0, 0]}},
        }
    else:
        sc["medium"] = {
            "type": "homogeneous",
            "albedo": {"type": "rgb", "value": [0, 0, 0]},
            "sigma_t": {"type": "uniform", "value": 1.0},
            "scale": float(sigma),
        }
        plaat = {
            "type": "cube",
            "to_world": mi.ScalarTransform4f().scale([5, 5, dikte / 2]),
            "bsdf": diel,
        }
        if sigma > 0:
            plaat["interior"] = {"type": "ref", "id": "medium"}
        sc["plaat"] = plaat
        if achter_zwart:
            sc["zwart"] = {
                "type": "rectangle",
                "to_world": mi.ScalarTransform4f().translate([0, 0, -dikte]).scale(5),
                "bsdf": {"type": "diffuse", "reflectance": {"type": "rgb", "value": [0, 0, 0]}},
            }
    return sc


def _pixel(sc: dict, seed: int = 1) -> float:
    import mitsuba as mi

    img = np.array(mi.render(mi.load_dict(sc), seed=seed))
    return float(img[..., :3].mean())


@pytest.fixture(scope="module", autouse=True)
def _variant():
    select_variant()


def test_fresnel_loodrecht_een_vlak():
    """Eén grensvlak lucht/epoxy, zwart erachter: pixel = reflectie = ((n-1)/(n+1))^2 ~ 4,4 %."""
    r = _pixel(_plaatscene(None, spp=1024))
    assert r == pytest.approx(_r0(), abs=0.005)  # +-0,5 procentpunt
    assert 0.038 < r < 0.049


def test_fresnel_loodrecht_plaat_twee_vlakken():
    """Een dikke plaat zonder absorptie in een witte omgeving: alles wat niet reflecteert gaat door en
    de omgeving is overal 1, dus pixel = 1 (energiebehoud, geen verlies in het grensvlak)."""
    assert _pixel(_plaatscene(0.02, spp=256)) == pytest.approx(1.0, abs=0.01)


def _transmissie_binnen_naar_buiten(hoek_deg: float, n: int = 20000) -> float:
    """Aandeel van de monsters dat vanuit de epoxy naar buiten gaat (dielectric-BSDF, eenstraals)."""
    import mitsuba as mi

    b = mi.load_dict({"type": "dielectric", "int_ior": N, "ext_ior": EXT})
    th = np.radians(hoek_deg)
    si = mi.SurfaceInteraction3f()
    si.wi = mi.Vector3f(mi.Float(np.full(n, np.sin(th))), mi.Float(np.zeros(n)), mi.Float(np.full(n, -np.cos(th))))
    si.sh_frame = mi.Frame3f(mi.Normal3f(0, 0, 1))
    si.n = mi.Normal3f(0, 0, 1)
    si.wavelengths = mi.Spectrum([450.0, 520.0, 590.0, 650.0]) if mi.variant().endswith("spectral") else None
    rng = np.random.default_rng(7)
    bs, _ = b.sample(
        mi.BSDFContext(), si, mi.Float(rng.random(n)), mi.Point2f(mi.Float(rng.random(n)), mi.Float(rng.random(n)))
    )
    wz = np.array(bs.wo.z)
    ok = np.array(bs.pdf) > 0
    return float((wz[ok] > 0).mean())  # wi.z < 0: binnenkant; wo.z > 0: aan de andere kant, dus doorgelaten


def test_kritische_hoek():
    th_c = np.degrees(np.arcsin(EXT / N))
    assert 40.5 < th_c < 41.0
    # ruim onder de kritische hoek: bijna alles gaat door, en gelijk aan 1 - Fresnel (onverpolariseerd)
    for h in (0.0, 20.0, 35.0):
        t = _transmissie_binnen_naar_buiten(h)
        assert t == pytest.approx(1 - _fresnel_onverpol(np.cos(np.radians(h)), N, EXT), abs=0.01)
    # vlak bij de kritische hoek valt de transmissie weg; erboven is er helemaal geen
    assert _transmissie_binnen_naar_buiten(th_c - 3.0) > 0.4
    assert _transmissie_binnen_naar_buiten(th_c - 0.3) < _transmissie_binnen_naar_buiten(th_c - 3.0)
    for h in (th_c + 0.05, th_c + 1.0, 50.0, 70.0, 89.0):
        assert _transmissie_binnen_naar_buiten(h) == 0.0
    # de rand is scherp: de hoek waaronder de transmissie < 5 % wordt, ligt binnen 1 graad van arcsin(1/n)
    hoeken = np.arange(th_c - 3.0, th_c + 0.5, 0.05)
    t = np.array([_transmissie_binnen_naar_buiten(h, 8000) for h in hoeken])
    h5 = hoeken[np.argmax(t < 0.05)]
    assert abs(h5 - th_c) < 1.0


@pytest.mark.parametrize("sigma,dikte", [(20.0, 0.02), (50.0, 0.02), (100.0, 0.03)])
def test_beer_lambert(sigma, dikte):
    """Plaat met kunstmatige absorptie sigma (1/m), dikte d, in witte omgeving. Incoherent door twee vlakken:
    T = (1-R)^2 e^(-sd) / (1 - R^2 e^(-2sd)) bij loodrechte inval, R = Fresnel-reflectie per vlak."""
    r = _r0()
    x = np.exp(-sigma * dikte)
    verwacht = (1 - r) ** 2 * x / (1 - r**2 * x**2)
    # pixel = transmissie (wit erachter) + het reflecterende deel van de omgeving (wit) wordt ook gezien:
    # camera ziet R + T_geabsorbeerd-vrij; de absorptie trekt A = 1 - R_tot - T af. Dus meten we direct
    # met zwart erachter niet nodig: pixel = R_tot + T, met R_tot = R + (1-R)^2 R x^2/(1 - R^2 x^2)
    r_tot = r + (1 - r) ** 2 * r * x**2 / (1 - r**2 * x**2)
    pix = _pixel(_plaatscene(dikte, sigma, spp=512))
    assert pix == pytest.approx(verwacht + r_tot, abs=0.005)


def test_beer_lambert_verhouding():
    """De afname tussen twee diktes volgt e^(-sigma*dd) na correctie voor Fresnel (via de reflectie weg te halen
    uit de zwart-erachter-meting is lastig; we meten de transmissie T = pixel - R_tot in beide diktes)."""
    r, sigma = _r0(), 40.0

    def t_gemeten(d: float) -> float:
        x = np.exp(-sigma * d)
        r_tot = r + (1 - r) ** 2 * r * x**2 / (1 - r**2 * x**2)
        return _pixel(_plaatscene(d, sigma, spp=1024)) - r_tot

    d1, d2 = 0.01, 0.04
    t1, t2 = t_gemeten(d1), t_gemeten(d2)
    # (1-R)^2 verdwijnt uit de verhouding bij kleine R^2 x^2; tolerantie 3 %
    assert (t2 / t1) == pytest.approx(np.exp(-sigma * (d2 - d1)), rel=0.03)
