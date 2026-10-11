import numpy as np

from carbonne.core.variant import KANDIDATEN, select_variant
from carbonne.smoke import render_smoke


def test_select_variant():
    assert select_variant() in KANDIDATEN


def test_env_voorrang(monkeypatch):
    monkeypatch.setenv("CARBONNE_VARIANT", "scalar_spectral")
    assert select_variant() == "scalar_spectral"


def test_render_64():
    select_variant()
    bmp, _ = render_smoke(res=64, spp=8)
    arr = np.array(bmp)
    assert arr.shape[:2] == (64, 64)
    assert np.isfinite(arr).all() and arr.max() > 0 and arr.std() > 0
