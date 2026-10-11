"""Gesimuleerde glansmeter volgens ISO 2813 (60 graden), op de BSDF's van de app (T18).

Een glansmeter beschijnt het oppervlak onder 60 graden met een bijna evenwijdige bundel en meet de flux die in een
klein venster rond de spiegelrichting terugkomt. De uitkomst is relatief aan een referentie: zwart glas met
n = 1,567 geeft per definitie 100 GU (gloss units). Het venster van de ontvanger is volgens de norm 4,4 graden in
het invalsvlak en 11,7 graden loodrecht daarop. Wij laten een enkele straal (de bronapertuur van 0,75 x 2,5 graden
is veel kleiner dan het ontvangervenster en wordt verwaarloosd) onder 60 graden op de BSDF vallen, trekken veel
reflectierichtingen en tellen het gewicht dat in het venster valt. Deze meting is Monte Carlo op de BSDF-sample.
"""

from __future__ import annotations

import numpy as np

HOEK_DEG = 60.0
VENSTER_VLAK_DEG = 4.4  # ontvangervenster in het invalsvlak (totale breedte)
VENSTER_LOODRECHT_DEG = 11.7  # loodrecht op het invalsvlak (totale breedte)
N_REFERENTIE = 1.567  # zwart glas = 100 GU


def fresnel_onbepolariseerd(cos_i: float, n: float) -> float:
    """Reflectie van een glad diëlektricum (lucht -> n), gemiddeld over s en p."""
    sin_t = np.sqrt(1 - cos_i**2) / n
    cos_t = np.sqrt(1 - sin_t**2)
    rs = (cos_i - n * cos_t) / (cos_i + n * cos_t)
    rp = (n * cos_i - cos_t) / (n * cos_i + cos_t)
    return float(0.5 * (rs**2 + rp**2))


REFERENTIE_R = fresnel_onbepolariseerd(np.cos(np.radians(HOEK_DEG)), N_REFERENTIE)


def meet_gu(bsdf_dict: dict, n: int = 1_000_000, zaad: int = 1) -> float:
    """Glanswaarde (GU, 60 graden) van een enkelzijdige BSDF met de luchtkant naar boven (normaal +z)."""
    import mitsuba as mi

    b = mi.load_dict(bsdf_dict)
    th = np.radians(HOEK_DEG)
    si = mi.SurfaceInteraction3f()
    si.wi = mi.Vector3f(mi.Float(np.full(n, np.sin(th))), mi.Float(np.zeros(n)), mi.Float(np.full(n, np.cos(th))))
    si.sh_frame = mi.Frame3f(mi.Normal3f(0, 0, 1))
    si.n = mi.Normal3f(0, 0, 1)
    si.wavelengths = mi.Spectrum([450.0, 520.0, 590.0, 650.0]) if mi.variant().endswith("spectral") else None
    rng = np.random.default_rng(zaad)
    bs, w = b.sample(
        mi.BSDFContext(), si, mi.Float(rng.random(n)), mi.Point2f(mi.Float(rng.random(n)), mi.Float(rng.random(n)))
    )
    gew = np.array(w[0]) if len(np.array(w).shape) > 1 else np.array(w)
    wo = np.stack([np.array(bs.wo.x), np.array(bs.wo.y), np.array(bs.wo.z)], axis=1)
    geldig = (np.array(bs.pdf) > 0) & (wo[:, 2] > 0)
    # ontvangerframe: u = spiegelrichting, e1 in het invalsvlak, e2 = y
    u = np.array([-np.sin(th), 0.0, np.cos(th)])
    e1 = np.array([np.cos(th), 0.0, np.sin(th)])
    e2 = np.array([0.0, 1.0, 0.0])
    cu = wo @ u
    in_venster = (
        geldig
        & (cu > 0)
        & (np.abs(np.degrees(np.arctan2(wo @ e1, cu))) <= VENSTER_VLAK_DEG / 2)
        & (np.abs(np.degrees(np.arctan2(wo @ e2, cu))) <= VENSTER_LOODRECHT_DEG / 2)
    )
    r = float(gew[in_venster].sum() / n)
    return 100.0 * r / REFERENTIE_R


def glossy_buitenkant(alpha: float) -> dict:
    """De luchtkant van `Paint(kind="glossy")` met zwart pigment (alleen de glans, zonder diffuus aandeel)."""
    from carbonne.core.scene import _plastic

    return _plastic((0.0, 0.0, 0.0), alpha)
