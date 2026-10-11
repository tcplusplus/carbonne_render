"""T08: renderpijplijn (ruisschatting, stopcriteria, cache, uitvoer, annulering, meerdere kanalen)."""

from __future__ import annotations

import struct
import threading
import zlib

import numpy as np
import pytest

from carbonne.core.config import TableConfig
from carbonne.render.pipeline import MIN_PASSES, RenderOpties, cache_sleutel, render, ruis_schatting
from carbonne.render.uitvoer import png_bytes, tonemap_srgb


def klein_config() -> TableConfig:
    c = TableConfig()
    c.render.breedte, c.render.hoogte = 64, 48
    return c


def opties(tmp_path, **kw) -> RenderOpties:
    return RenderOpties(cache_map=tmp_path / "cache", spp_per_pass=8, **kw)


def test_ruisschatting_schaalt_met_wortel_n():
    rng = np.random.default_rng(0)
    rel = []
    for n in (16, 64, 256):
        a = rng.normal(0.5, 0.2, (64, 64, 3)).mean(axis=0) * 0 + 0.5 + rng.normal(0, 0.2 / np.sqrt(n), (64, 64, 3))
        b = 0.5 + rng.normal(0, 0.2 / np.sqrt(n), (64, 64, 3))
        rel.append(ruis_schatting(a * n, n, b * n, n))
    # 4x meer samples -> 2x minder ruis
    assert rel[0] / rel[1] == pytest.approx(2.0, rel=0.1)
    assert rel[1] / rel[2] == pytest.approx(2.0, rel=0.1)


def test_tonemap_en_png():
    lin = np.array([[[0.0, 0.2159, 1.0], [2.0, 0.5, 0.0]]])
    s = tonemap_srgb(lin)
    assert list(s[0, 0]) == [0, 128, 255] and s[0, 1, 0] == 255  # clip boven 1
    assert list(tonemap_srgb(np.full((1, 1, 3), 0.25), ev=1)[0, 0]) == list(tonemap_srgb(np.full((1, 1, 3), 0.5))[0, 0])
    png = png_bytes(s)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    w, h = struct.unpack(">II", png[16:24])
    assert (w, h) == (2, 1)
    assert zlib.decompress(png[png.index(b"IDAT") + 4 : png.index(b"IEND") - 8])  # leesbare data


def test_stopt_op_max_spp_en_cachet(tmp_path):
    cfg = klein_config()
    o = opties(tmp_path, max_spp=32, ruisdrempel=1e-6)
    calls = []
    r = render(cfg, o, calls.append)
    assert r.reden == "max_spp" and r.spp == 32 and not r.uit_cache
    assert r.beeld.shape == (48, 64, 3) and r.png[:4] == b"\x89PNG"
    assert [c.pass_nr for c in calls] == [1, 2, 3, 4] and calls[-1].klaar and calls[0].ruis is None
    assert all(c.png[:4] == b"\x89PNG" for c in calls)
    assert (r.pad / "beeld.exr").exists() and (r.pad / "beeld.png").exists()
    # tweede keer: cache, identiek beeld, geen renderpasses
    calls2 = []
    r2 = render(cfg, o, calls2.append)
    assert r2.uit_cache and r2.reden == "cache" and np.array_equal(r2.beeld, r.beeld)
    assert len(calls2) == 1 and calls2[0].klaar


def test_stopt_op_drempel(tmp_path):
    r = render(klein_config(), opties(tmp_path, max_spp=4096, ruisdrempel=0.5, cache=False))
    assert r.reden == "drempel" and r.spp == MIN_PASSES * 8 and r.ruis <= 0.5


def test_tijdslimiet_en_annulering_cachen_niet(tmp_path):
    cfg = klein_config()
    r = render(cfg, opties(tmp_path, max_spp=4096, ruisdrempel=1e-9, tijdslimiet_s=0.01))
    assert r.reden == "tijdslimiet" and r.pad is None
    ev = threading.Event()
    r2 = render(cfg, opties(tmp_path, max_spp=4096, ruisdrempel=1e-9), lambda v: ev.set() if v.pass_nr == 2 else None, ev)
    assert r2.reden == "geannuleerd" and r2.spp == 16 and r2.pad is None
    assert not (tmp_path / "cache").exists()


def test_cachesleutel_gevoeligheid(tmp_path):
    cfg, o = klein_config(), opties(tmp_path)
    k = cache_sleutel(cfg, o)
    assert k == cache_sleutel(klein_config(), opties(tmp_path))
    assert k != cache_sleutel(cfg, opties(tmp_path, seed=1))
    assert k != cache_sleutel(cfg, opties(tmp_path, max_depth=8))
    assert k != cache_sleutel(cfg, opties(tmp_path, integrator="volpath"))
    c2 = klein_config()
    c2.diameter = 0.5
    assert k != cache_sleutel(c2, o)
    # EV en tijdslimiet veranderen de EXR niet
    assert k == cache_sleutel(cfg, opties(tmp_path, ev=1.0, tijdslimiet_s=5))


def test_zelfde_zaad_reproduceerbaar_ander_zaad_niet(tmp_path):
    cfg = klein_config()
    kw = {"max_spp": 16, "ruisdrempel": 1e-9, "cache": False}
    a = render(cfg, opties(tmp_path, **kw))
    b = render(cfg, opties(tmp_path, **kw))
    c = render(cfg, opties(tmp_path, seed=5, **kw))
    # zelfde zaad: gelijk op float-afrondingsverschillen na (parallelle sommatie)
    assert np.allclose(a.beeld, b.beeld, rtol=1e-3, atol=1e-4)
    assert np.abs(a.beeld - c.beeld).mean() > 100 * np.abs(a.beeld - b.beeld).mean()


def test_preview_is_klein_en_niet_gecachet(tmp_path):
    r = render(klein_config(), opties(tmp_path, preview=True, preview_breedte=32, max_spp=4096))
    assert r.beeld.shape[:2] == (24, 32) and r.spp <= 64 and r.pad is None


def test_alle_kanalen_worden_bewaard(tmp_path):
    """Extra film-kanalen (AOV's, T13) komen door accumulatie, cache en EXR heen: simuleer met Mitsuba's
    `aov`-integrator (diepte-kanaal + shading-normaal naast de gewone path-integrator)."""
    import mitsuba as mi

    o = opties(
        tmp_path, max_spp=16, ruisdrempel=1e-9, integrator="aov",
        integrator_params={"max_depth": None, "aovs": "dd.y:depth,nn:sh_normal", "img": {"type": "path", "max_depth": 8}},
    )
    r = render(klein_config(), o)
    assert r.beeld.shape == (48, 64, 7) and len(r.kanaalnamen) == 7
    assert np.isfinite(r.beeld).all() and np.ptp(r.beeld[..., 0]) > 0  # kanaal 0 is niet leeg
    r2 = render(klein_config(), o)
    assert r2.uit_cache and np.array_equal(r.beeld, r2.beeld)
    exr = mi.Bitmap(str(r.pad / "beeld.exr"))
    assert exr.channel_count() == 7 and tuple(exr.size()) == (64, 48)
