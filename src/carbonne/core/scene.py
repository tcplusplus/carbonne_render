"""TableConfig -> Mitsuba-scenedict.

De cilinder (as = y, onderkant op y = 0) bestaat uit drie aparte meshes: bovenschijf, mantel, onderschijf, met
naar buiten wijzende normalen. Samen vormen ze een gesloten volume; elk vlak krijgt later zijn eigen BSDF.

Dispersie: Mitsuba 3 (`dielectric`) accepteert alleen een scalaire IOR (float of naam), geen spectrum. We
gebruiken daarom n(589,3 nm) uit de Cauchy-curve; zie docs/queue/vragen/T02-1.md.
"""

from __future__ import annotations

import numpy as np

from carbonne.core.config import TableConfig

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


def build_scene(config: TableConfig) -> dict:
    """Bouw het Mitsuba-scenedict; de Mitsuba-variant moet al gezet zijn."""
    import mitsuba as mi

    sc, rs = config.scene, config.render
    geo = cilinder_geometrie(config.diameter, config.hoogte, config.segmenten)
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
            "to_world": mi.ScalarTransform4f().rotate([1, 0, 0], -90).scale(sc.vloer_grootte / 2),
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
    for naam in VLAKKEN:
        scene[naam] = _mesh(naam, geo[naam], epoxy_bsdf(config))
    return scene
