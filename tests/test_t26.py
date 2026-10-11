"""T26: metalen poten onder het blok."""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError

from carbonne.core.config import Legs, PlateBelow, TableConfig
from carbonne.core.environments import TAFEL_HOOGTE, assets_dir, camera_preset
from carbonne.core.herkomst import bron_bits
from carbonne.core.poten import METALEN, poot_bsdf, poot_geometrieen, poot_posities, vloer_y
from carbonne.core.scene import build_scene, effectieve_gap_mm
from carbonne.core.variant import select_variant

DATA = Path(__file__).parent / "data"


@pytest.fixture(autouse=True, scope="module")
def _variant():
    select_variant()


def cfg(**kw) -> TableConfig:
    poten = kw.pop("poten", {})
    return TableConfig(poten=Legs(**poten) if poten is not None else None, **kw)


# --- model ---
def test_standaard_geen_poten():
    assert TableConfig().poten is None


@pytest.mark.parametrize("poten", [{"aantal": 2}, {"aantal": 7}, {"afmeting_mm": 5}, {"hoogte_m": 0.01}, {"metaal": "goud"}, {"vorm": "driehoek"}])
def test_ongeldige_poten(poten):
    with pytest.raises(ValidationError):
        Legs(**poten)


def test_poten_moeten_passen():
    with pytest.raises(ValidationError, match="passen niet"):
        TableConfig(diameter=0.1, poten=Legs(afmeting_mm=60, rand_mm=40))
    with pytest.raises(ValidationError, match="naast elkaar"):
        TableConfig(diameter=0.2, poten=Legs(aantal=6, afmeting_mm=60, rand_mm=30))
    for vorm in ("rond", "vierkant"):  # de grens van de UI (T27-contract)
        TableConfig(diameter=0.2, poten=Legs(aantal=6, vorm=vorm, afmeting_mm=30, rand_mm=40))
    with pytest.raises(ValidationError, match="naast elkaar"):  # vierkant: de hoeken raken eerder dan de middens
        TableConfig(diameter=0.2, poten=Legs(aantal=6, vorm="vierkant", afmeting_mm=40, rand_mm=40))
    TableConfig(diameter=0.2, poten=Legs(aantal=6, vorm="rond", afmeting_mm=40, rand_mm=40))


# --- geometrie ---
@pytest.mark.parametrize("vorm", ["rond", "vierkant"])
@pytest.mark.parametrize("aantal", [3, 4, 5, 6])
def test_geometrie_plaatsing_en_windrichting(vorm, aantal):
    c = cfg(poten={"aantal": aantal, "vorm": vorm, "afmeting_mm": 30, "rand_mm": 20})
    geos = poot_geometrieen(c)
    assert len(geos) == aantal
    r = c.diameter / 2
    gap = effectieve_gap_mm(c, 0.0) / 1000
    for g in geos:
        v = g["v"]
        assert np.hypot(v[:, 0], v[:, 2]).max() == pytest.approx(r - 0.020, abs=1e-4)  # buitenkant (hoek) van de poot: 20 mm van de rand
        assert v[:, 1].max() == pytest.approx(-gap)  # niet rakend aan het blok (float32-epsilon)
        assert v[:, 1].min() < vloer_y(c)  # steekt in de vloer
        tri = v[g["f"]]
        geo_n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
        assert (np.einsum("ij,ij->i", geo_n, g["n"][g["f"]].mean(1)) > 0).all()  # normalen wijzen naar buiten
        # gesloten volume: de som van de naar buiten gerichte vlakken (vector-oppervlak) is nul
        assert np.abs(geo_n.sum(0)).max() < 1e-9
    mids = np.array([[x, z] for x, z, _ in poot_posities(c)])
    assert np.allclose(np.linalg.norm(mids, axis=1), np.linalg.norm(mids[0]))  # gelijkmatig op een cirkel


def test_vierkante_poot_zijde_wijst_naar_buiten():
    c = cfg(poten={"aantal": 4, "vorm": "vierkant", "afmeting_mm": 30})
    for (x, z, _), g in zip(poot_posities(c), poot_geometrieen(c), strict=True):
        radiaal = np.array([x, z]) / np.hypot(x, z)
        xz = g["v"][:, [0, 2]] - np.array([x, z])
        assert (xz @ radiaal).max() == pytest.approx(0.015, abs=1e-6)
        assert abs(xz @ np.array([-radiaal[1], radiaal[0]])).max() == pytest.approx(0.015, abs=1e-6)
        assert np.hypot(*(xz + [x, z]).T).max() < c.diameter / 2  # niet buiten het blok


def test_drie_poten_een_achter():
    pos = poot_posities(cfg(poten={"aantal": 3}))
    assert min(z for _, z, _ in pos) < -0.05 and sum(z > 0 for _, z, _ in pos) == 2


# --- scene: vloer, camera, plaat ---
def test_vloer_op_de_poothoogte():
    for hoogte_m, blok in [(0.41, 0.04), (0.2, 0.04), (0.6, 0.06)]:
        sc = build_scene(cfg(hoogte=blok, poten={"hoogte_m": hoogte_m}))
        assert float(sc["floor"]["to_world"].matrix[1, 3]) == pytest.approx(-hoogte_m)
        assert {f"poot_{i}" for i in range(4)} <= set(sc)


def test_vloer_met_omgeving_en_plaat():
    c = cfg(poten={"hoogte_m": 0.3}, scene={"omgeving": "studio"})
    assert float(build_scene(c)["floor"]["to_world"].matrix[1, 3]) == pytest.approx(-0.3)
    c = cfg(poten={"hoogte_m": 0.3}, onderkant=PlateBelow(gap_mm=1.0))
    y = float(build_scene(c)["floor"]["to_world"].matrix[1, 3])
    assert y < -0.3  # de poten hangen onder de plaat
    assert max(g["v"][:, 1].max() for g in poot_geometrieen(c)) < -0.003 - 0.001  # onder de plaat, er doorheen is uitgesloten


def test_camera_oog_blijft_op_dezelfde_hoogte_boven_de_vloer():
    for naam, oog in [("zittend", 1.10), ("staand", 1.65)]:
        for L in (0.2, 0.41, 0.7):
            c = cfg(poten={"hoogte_m": L}, scene={"omgeving": "studio", "camera_preset": naam})
            sc = build_scene(c)
            oog_y = float(sc["sensor"]["to_world"].matrix[1, 3])
            assert oog_y - float(sc["floor"]["to_world"].matrix[1, 3]) == pytest.approx(oog, abs=1e-5)
    assert camera_preset("zittend", 0.35, 0.04).positie[1] == pytest.approx(1.10 - TAFEL_HOOGTE + 0.04)  # zonder poten ongewijzigd


# --- zonder poten: niets verandert ---
def test_zonder_poten_scene_ongewijzigd():
    sc = build_scene(TableConfig())
    assert not any(k.startswith("poot") for k in sc)
    assert float(sc["floor"]["to_world"].matrix[1, 3]) == 0.0
    sc = build_scene(TableConfig(scene={"omgeving": "studio"}))
    assert float(sc["floor"]["to_world"].matrix[1, 3]) == pytest.approx(0.04 - TAFEL_HOOGTE)


def _render(c: TableConfig, spp: int = 16) -> np.ndarray:
    import mitsuba as mi

    select_variant()
    c.render.breedte, c.render.hoogte = 32, 24
    return np.array(mi.render(mi.load_dict(build_scene(c)), spp=spp, seed=3), dtype=np.float32)


def test_zonder_poten_beeld_gelijk_aan_voor_t26():
    """`tests/data/t26_basis.npz` is gerenderd met de code van vlak voor T26 (git archive van de basiscommit). Bit-identiek
    is niet te toetsen: twee runs van dezelfde code verschillen al in de laatste bit (volgorde van de threads in de film);
    we eisen gelijkheid op 1e-6 relatief, ruim onder alles wat een poot of vloerverschuiving zou veroorzaken."""
    basis = np.load(DATA / "t26_basis.npz")
    np.testing.assert_allclose(_render(TableConfig()), basis["constant"], rtol=1e-6, atol=1e-7)
    if (assets_dir() / "hdri").exists():  # de basis is met de echte HDRI gemaakt
        c = TableConfig(scene={"omgeving": "studio", "camera_preset": "zittend"})
        np.testing.assert_allclose(_render(c), basis["studio"], rtol=1e-6, atol=1e-7)


# --- materialen ---
def _gem_gewicht(bsdf_dict: dict, golflengte: float, n: int = 20000) -> float:
    """Gemiddeld BSDF-gewicht (f cos / pdf) bij loodrechte inval = albedo van het materiaal."""
    import mitsuba as mi

    select_variant()
    b = mi.load_dict(bsdf_dict)
    si = mi.SurfaceInteraction3f()
    si.wi = mi.Vector3f(0, 0, 1)
    si.wavelengths = mi.Float(golflengte) + mi.Float(np.zeros(n, np.float32))
    si.sh_frame = mi.Frame3f(mi.Vector3f(0, 0, 1))
    si.t = 1.0
    rng = np.random.default_rng(1)
    bs, w = b.sample(mi.BSDFContext(), si, mi.Float(rng.random(n).astype(np.float32)),
                     mi.Point2f(rng.random(n).astype(np.float32), rng.random(n).astype(np.float32)))
    kleur = np.array(w[0])  # eerste spectrale component
    return float(kleur.mean())


def _nk(materiaal: str, nm: float) -> tuple[float, float]:
    """n en k uit de brekingsindextabellen die Mitsuba meelevert (data/ior/<materiaal>.{eta,k}.spd)."""
    import mitsuba as mi

    kaal = Path(mi.__file__).parent / "data" / "ior"
    uit = []
    for soort in ("eta", "k"):
        rijen = [tuple(map(float, r.split())) for r in (kaal / f"{materiaal}.{soort}.spd").read_text().splitlines()
                 if r.strip() and not r.startswith("#")]
        uit.append(float(np.interp(nm, [x for x, _ in rijen], [y for _, y in rijen])))
    return uit[0], uit[1]


def test_aluminium_en_chroom_hebben_hun_echte_reflectie():
    """Loodrechte reflectie R = ((n-1)^2 + k^2) / ((n+1)^2 + k^2) uit de n en k van het materiaal, bij 450, 550 en 650 nm."""
    glad = {"alpha": 0.005}  # vrijwel spiegelend: het gewicht is dan de Fresnelreflectie zelf
    for naam, mat in (("geborsteld", "Al"), ("gepoetst", "Cr")):
        for nm in (450.0, 550.0, 650.0):
            n, k = _nk(mat, nm)
            verwacht = ((n - 1) ** 2 + k**2) / ((n + 1) ** 2 + k**2)
            assert _gem_gewicht({**poot_bsdf(naam), **glad}, nm) == pytest.approx(verwacht, abs=0.02), (mat, nm)
    al, cr = (_gem_gewicht({**poot_bsdf(n), **glad}, 550.0) for n in ("geborsteld", "gepoetst"))
    assert al > cr + 0.15  # aluminium (~0,92) is duidelijk helderder dan chroom (~0,65)


def test_poot_bsdf_typen():
    assert METALEN["geborsteld"]["alpha"] > METALEN["gepoetst"]["alpha"]  # geborsteld is ruwer
    assert poot_bsdf("geborsteld")["type"] == poot_bsdf("gepoetst")["type"] == "roughconductor"
    assert poot_bsdf("zwart")["type"] == "roughplastic"  # poedercoating = dielectrische lak op pigment
    zwart = _gem_gewicht(poot_bsdf("zwart"), 550.0)
    assert 0.03 < zwart < 0.12  # ~4 % lak plus bijna zwart pigment


def test_herkomst_bron_van_poten():
    assert bron_bits("poot_2", "roughconductor") == bron_bits("floor", "smoothdiffuse") == 8


# --- poten zijn zichtbaar door de epoxy ---
def test_poten_zichtbaar_door_de_epoxy():
    """Van boven recht omlaag door het blok: boven een pootmidden verandert het beeld, ver ervan af niet."""
    from carbonne.core.config import CameraConfig

    def beeld(poten):
        c = TableConfig(poten=poten)
        c.scene.camera = CameraConfig(positie=(0.0, 0.8, 1e-4), doel=(0.0, 0.0, 0.0), fov=30.0)
        c.render.breedte, c.render.hoogte = 96, 96
        import mitsuba as mi

        select_variant()
        return np.array(mi.render(mi.load_dict(build_scene(c)), spp=128, seed=1), dtype=np.float32).mean(-1)

    met = beeld(Legs(aantal=4, metaal="gepoetst", afmeting_mm=40, rand_mm=20))
    zonder = beeld(None)
    # camera 'up' is +y en kijkt langs -y: het beeld heeft x naar rechts, z naar beneden
    schaal = 96 / (2 * 0.8 * math.tan(math.radians(15)))
    pos = poot_posities(cfg(poten={"aantal": 4, "afmeting_mm": 40, "rand_mm": 20}))
    x, z, _ = pos[0]
    px, py = int(48 + x * schaal), int(48 + z * schaal)
    roi = (slice(py - 2, py + 3), slice(px - 2, px + 3))
    verschil_poot = np.abs(met[roi] - zonder[roi]).mean()
    verschil_hoek = np.abs(met[:8, :8] - zonder[:8, :8]).mean()
    assert verschil_poot > 5 * max(verschil_hoek, 1e-3)
