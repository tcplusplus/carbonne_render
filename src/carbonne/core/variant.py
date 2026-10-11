"""Kies de snelste Mitsuba-variant die op deze machine werkt."""

from __future__ import annotations

import os

import mitsuba as mi

KANDIDATEN = ("cuda_ad_spectral", "llvm_ad_spectral", "scalar_spectral")
ENV = "CARBONNE_VARIANT"


def _werkt(variant: str) -> bool:
    """Zet de variant en voer een minuscule rekenstap uit; False bij elke fout."""
    try:
        mi.set_variant(variant)
        import drjit as dr

        if variant.startswith("scalar"):
            mi.Point3f(1, 2, 3)
        else:
            float(dr.sum(dr.arange(mi.Float, 4))[0])
        return True
    except Exception:  # noqa: BLE001
        return False


def select_variant() -> str:
    """Zet en geef de gekozen variant terug. `CARBONNE_VARIANT` heeft voorrang (geen terugval)."""
    gevraagd = os.environ.get(ENV)
    if gevraagd:
        mi.set_variant(gevraagd)
        return gevraagd
    for variant in KANDIDATEN:
        if _werkt(variant):
            return variant
    raise RuntimeError(f"Geen werkende Mitsuba-variant gevonden uit {KANDIDATEN}")
