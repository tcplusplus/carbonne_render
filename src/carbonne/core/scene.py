"""TableConfig -> Mitsuba-scenedict.

De cilinder (as = y, onderkant op y = 0) bestaat uit drie aparte meshes: bovenschijf, mantel, onderschijf, met
naar buiten wijzende normalen. Samen vormen ze een gesloten volume; elk vlak krijgt later zijn eigen BSDF.

Dispersie: Mitsuba 3 (`dielectric`) accepteert alleen een scalaire IOR (float of naam), geen spectrum. We
gebruiken daarom n(589,3 nm) uit de Cauchy-curve; zie docs/queue/vragen/T02-1.md.
"""

from __future__ import annotations

import numpy as np

from carbonne.core.config import Bare, EdgeFinish, MatteClearCoat, Paint, PlateBelow, TableConfig

VLAKKEN = ("boven", "mantel", "onder")


def cilinder_geometrie(diameter: float, hoogte: float, segmenten: int) -> dict[str, dict[str, np.ndarray]]:
    """Geef per vlak {'v': posities (N,3), 'n': normalen (N,3), 'f': driehoeken (M,3)}."""
    r = diameter / 2
    hoek = 2 * np.pi * np.arange(segmenten) / segmenten
    cx, cz = np.cos(hoek), np.sin(hoek)
    k = np.arange(segmenten)
    k1 = (k + 1) % segmenten

    def ring(y: float) -> np.ndarray:
        return np.stack([r * cx, np.full(segmenten, y), r * cz], axis=1)

    # mantel: onderring 0..S-1, bovenring S..2S-1; radiale (geinterpoleerde) normalen
    mv = np.concatenate([ring(0.0), ring(hoogte)])
    mn = np.concatenate([np.stack([cx, 0 * cx, cz], axis=1)] * 2)
    mf = np.concatenate(
        [np.stack([k, segmenten + k1, k1], axis=1), np.stack([k, segmenten + k, segmenten + k1], axis=1)]
    )

    def schijf(y: float, ny: float) -> dict[str, np.ndarray]:
        v = np.concatenate([[[0.0, y, 0.0]], ring(y)])
        n = np.tile([0.0, ny, 0.0], (segmenten + 1, 1))
        f = np.stack([np.zeros(segmenten, dtype=int), 1 + k1, 1 + k], axis=1)  # draaiing: normaal +y
        if ny < 0:
            f = f[:, ::-1]
        return {"v": v, "n": n, "f": f}

    return {
        "boven": schijf(hoogte, 1.0),
        "mantel": {"v": mv, "n": mn, "f": mf},
        "onder": schijf(0.0, -1.0),
    }


def _mesh(naam: str, g: dict[str, np.ndarray], bsdf: dict):
    import drjit as dr
    import mitsuba as mi

    m = mi.Mesh(naam, vertex_count=len(g["v"]), face_count=len(g["f"]), has_vertex_normals=True)
    p = mi.traverse(m)
    p["vertex_positions"] = dr.ravel(mi.TensorXf(g["v"].astype(np.float32)))
    p["vertex_normals"] = dr.ravel(mi.TensorXf(g["n"].astype(np.float32)))
    p["faces"] = dr.ravel(mi.TensorXu(g["f"].astype(np.uint32)))
    p.update()
    m.set_bsdf(mi.load_dict(bsdf))
    return m


def raster_bitmap(cel_px: int = 128, lijn_px: int = 3, achtergrond=(0.75, 0.75, 0.72), lijn=(0.03,) * 3):
    """Een cel van het rasterpatroon (lijn langs de rand), tegelbaar."""
    import mitsuba as mi

    img = np.empty((cel_px, cel_px, 3), np.float32)
    img[:] = achtergrond
    img[:lijn_px, :] = lijn
    img[:, :lijn_px] = lijn
    return mi.Bitmap(img)


def epoxy_bsdf(config: TableConfig) -> dict:
    """Epoxy/lucht-grensvlak (scalaire IOR, zie moduledocstring)."""
    return {"type": "dielectric", "int_ior": float(config.epoxy.n_d), "ext_ior": 1.000277}


PLAAT_DIKTE = 0.003  # m
PLAAT_OVERMAAT = 0.01  # m, de plaat steekt zoveel buiten de straal van het blok


def _diffuus(kleur) -> dict:
    return {"type": "diffuse", "reflectance": {"type": "rgb", "value": list(kleur)}}


def afwerking_bsdf(finish: EdgeFinish, config: TableConfig) -> dict:
    """BSDF voor een vlak van het blok. Normalen wijzen naar buiten: de voorkant van `twosided` is de
    luchtkant, de achterkant (bsdf1) is de epoxykant."""
    if isinstance(finish, (Bare, PlateBelow)):
        return epoxy_bsdf(config)  # bij PlateBelow blijft het blok zelf onbehandeld
    if isinstance(finish, Paint):
        if finish.kind != "matte":
            raise NotImplementedError(f"verfsoort {finish.kind!r} komt in T05")
        # binnen: pigmentlaag direct op de epoxy (zelfde index, dus geen Fresnel, geen TIR);
        # buiten: matte verf in lucht
        return {
            "type": "twosided",
            "front": _diffuus(finish.color),
            "back": _diffuus(finish.color),
        }
    if isinstance(finish, MatteClearCoat):
        return {**epoxy_bsdf(config), "type": "roughdielectric", "distribution": "ggx", "alpha": finish.roughness}
    raise TypeError(finish)


RAY_EPS_FACTOR = 2e-3  # veilige onder-spleet als fractie van de plaatstraal, zie effectieve_gap_mm


def effectieve_gap_mm(config: TableConfig, gap_mm: float) -> float:
    """Spleet zoals gerenderd. Mitsuba (float32) verschuift het startpunt van een straal na een botsing met
    ~1e-3 x de grootste coordinaat; is de spleet kleiner (0,1 mm bij straal > ~0,11 m), dan springt de straal
    over het grensvlak epoxy/lucht heen en is de plaat ineens in optisch contact (ontdekt in T03, zichtbaar als
    donker vierkant-gebied). Voor geometrische optiek maakt de dikte van een luchtspleet >> golflengte niets uit,
    dus we renderen minstens `RAY_EPS_FACTOR * straal` (0,35 m: ~0,37 mm; 0,5 m: ~0,52 mm)."""
    r = config.diameter / 2 + PLAAT_OVERMAAT
    return max(gap_mm, RAY_EPS_FACTOR * r * 1000.0)


def plaat_geometrie(config: TableConfig, gap_mm: float) -> dict[str, dict[str, np.ndarray]]:
    """Dunne ronde plaat met de bovenkant `gap_mm` (effectief) onder het blok (y = 0)."""
    gap_mm = effectieve_gap_mm(config, gap_mm)
    geo = cilinder_geometrie(config.diameter + 2 * PLAAT_OVERMAAT, PLAAT_DIKTE, config.segmenten)
    y0 = -gap_mm / 1000.0 - PLAAT_DIKTE
    return {k: {**g, "v": g["v"] + np.array([0.0, y0, 0.0])} for k, g in geo.items()}


def build_scene(config: TableConfig) -> dict:
    """Bouw het Mitsuba-scenedict; de Mitsuba-variant moet al gezet zijn."""
    import mitsuba as mi

    sc, rs = config.scene, config.render
    geo = cilinder_geometrie(config.diameter, config.hoogte, config.segmenten)
    plaat = config.onderkant if isinstance(config.onderkant, PlateBelow) else None
    vloer_y = -(effectieve_gap_mm(config, plaat.gap_mm) / 1000.0 + PLAAT_DIKTE) if plaat else 0.0
    scene: dict = {
        "type": "scene",
        "integrator": {"type": "path", "max_depth": rs.max_depth},
        "sensor": {
            "type": "perspective",
            "fov": sc.camera.fov,
            "to_world": mi.ScalarTransform4f().look_at(
                origin=list(sc.camera.positie), target=list(sc.camera.doel), up=[0, 1, 0]
            ),
            "film": {
                "type": "hdrfilm",
                "width": rs.breedte,
                "height": rs.hoogte,
                "rfilter": {"type": "gaussian"},
            },
            "sampler": {"type": "independent", "sample_count": rs.spp},
        },
        "env": {"type": "constant", "radiance": {"type": "rgb", "value": list(sc.omgeving_radiantie)}},
        "floor": {
            "type": "rectangle",
            "to_world": mi.ScalarTransform4f().translate([0, vloer_y, 0]).rotate([1, 0, 0], -90).scale(sc.vloer_grootte / 2),
            "bsdf": {
                "type": "diffuse",
                "reflectance": {
                    "type": "bitmap",
                    "bitmap": raster_bitmap(achtergrond=sc.vloer_albedo, lijn=sc.vloer_lijn_albedo),
                    "raw": False,
                    "wrap_mode": "repeat",
                    "filter_type": "bilinear",
                    "to_uv": mi.ScalarTransform4f().scale([sc.vloer_grootte / sc.vloer_rastercel] * 2 + [1]),
                },
            },
        },
    }
    finish = {"boven": Bare(), "mantel": config.zijkant, "onder": config.onderkant}
    for naam in VLAKKEN:
        scene[naam] = _mesh(naam, geo[naam], afwerking_bsdf(finish[naam], config))
    if plaat:
        for naam, g in plaat_geometrie(config, plaat.gap_mm).items():
            if plaat.kind != "matte":
                raise NotImplementedError(f"verfsoort {plaat.kind!r} komt in T05")
            scene[f"plaat_{naam}"] = _mesh(f"plaat_{naam}", g, _diffuus(plaat.color))
    return scene
