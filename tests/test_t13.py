"""T13: herkomst-integrator (som = path, bronnen, kleurstalen, kerngetallen, paneel)."""

from __future__ import annotations

import numpy as np
import pytest

from carbonne.core.config import Layer, Paint, PlateBelow, TableConfig, WoodSlice
from carbonne.core.herkomst import (
    N_CAT,
    STAT_NAMEN,
    bron_bits,
    categorie_beelden,
    categorie_naam,
    herkomst_opties,
    herkomst_van,
    kanaal_namen,
    lineair_naar_lab,
)
from carbonne.core.herkomst_cli import bron_beelden, paneel_png, tekst
from carbonne.render.pipeline import RenderOpties, render


def cfg(b=64, h=64, **kw) -> TableConfig:
    c = TableConfig(**kw)
    c.render.breedte, c.render.hoogte = b, h
    return c


def herk(c: TableConfig, spp=64, **kw):
    return render(c, herkomst_opties(c, max_spp=spp, spp_per_pass=spp, cache=False, ruisdrempel=1e-9, **kw))


def test_kanalen_en_namen():
    assert len(kanaal_namen()) == N_CAT * 3 + len(STAT_NAMEN) == 52
    assert categorie_naam(0) == "glans/omgeving" and categorie_naam(3) == "zijkant + onderkant"


def test_bron_bits():
    assert bron_bits("mantel", "twosided") == 1
    assert bron_bits("mantel", "roughdielectric") == 1  # matte lak telt als bron
    assert bron_bits("mantel", "smoothdielectric") == 0  # onbehandeld = geen bron
    assert bron_bits("onder", "smoothdielectric") == 0 and bron_bits("onder", "twosided") == 2
    assert bron_bits("plaat_boven", "twosided") == 2 and bron_bits("inhoud_0_1_wood", "twosided") == 4
    assert bron_bits("floor", "smoothdiffuse") == 8 and bron_bits("boven", "smoothdielectric") == 0


def test_som_van_categorieen_is_de_path_render():
    # zijkant, onderkant (verf) en inhoud: alle bronnen
    c = cfg(
        zijkant=Paint(color=(0.8, 0.05, 0.05)), onderkant=Paint(color=(0.9, 0.9, 0.9), kind="glossy"),
        layers=[Layer(height_m=0.02, items=[WoodSlice(count=3)])],
    )
    h = herk(c, spp=256)
    p = render(c, RenderOpties(integrator="path", max_spp=256, spp_per_pass=256, cache=False, ruisdrempel=1e-9,
                               max_depth=32))
    som = categorie_beelden(h.beeld).sum(axis=2)
    # hetzelfde zaad en dezelfde stappen: de herkomst-render is de path-render
    assert np.mean(np.abs(h.beeld[..., :3] - p.beeld) / (p.beeld + 0.01)) < 0.02
    assert np.mean(np.abs(som - p.beeld) / (p.beeld + 0.01)) < 0.02
    assert som.mean() == pytest.approx(p.beeld.mean(), rel=0.02)


def test_zonder_verf_of_plaat_geen_zijkant_of_onderkant():
    c = cfg(48, 48)
    r = herk(c)
    h = herkomst_van(r, (0, 0, 48, 48), drempel_pct=0.0)
    assert h.bevat("zijkant") == 0.0 and h.bevat("onderkant") == 0.0 and h.bevat("inhoud") == 0.0
    assert h.aandeel() + h.aandeel("vloer") == pytest.approx(100.0, abs=1e-6)


def test_rode_zijkant_geeft_rood_staal():
    c = cfg(zijkant=Paint(color=(0.9, 0.02, 0.02)))
    r = herk(c, spp=128)
    h = herkomst_van(r, (0, 0, 64, 64), drempel_pct=0.0)
    zij = [k for k in h.categorieen if k.bronnen == ("zijkant",)]
    assert zij and zij[0].aandeel_pct > 0.5
    rgb = zij[0].rgb_per_pad
    assert rgb[0] > 5 * rgb[1] and rgb[0] > 5 * rgb[2]
    assert zij[0].lab_per_pad[1] > 40  # a* sterk positief = rood
    assert sum(k.aandeel_pct for k in h.categorieen) == pytest.approx(100.0)


def test_plaat_telt_als_onderkant_en_tir_alleen_met_glad_vlak():
    r = herk(cfg(onderkant=PlateBelow(color=(0.02, 0.02, 0.02), gap_mm=1.0)), spp=64)
    h = herkomst_van(r, (0, 0, 64, 64), drempel_pct=0.0)
    assert h.bevat("onderkant") > 0.1
    assert h.kerngetallen.n_fresnel > 0 and h.kerngetallen.weg_epoxy_cm > 0
    # alles met verf er omheen: geen glad vlak van binnen, dus nooit TIR
    r2 = herk(cfg(zijkant=Paint(color=(0.5, 0.5, 0.5)), onderkant=Paint(color=(0.5, 0.5, 0.5))), spp=64)
    h2 = herkomst_van(r2, (0, 0, 64, 64))
    assert h2.kerngetallen.n_tir < 0.2  # alleen het bovenvlak is glad: lichte TIR van binnenuit


def test_herkomst_van_voegt_kleine_categorieen_samen_en_telt_op():
    b = np.zeros((4, 4, 55), np.float32)
    cats = b[..., 3:51].reshape(4, 4, 16, 3)
    cats[:, :, 0] = (0.5, 0.5, 0.5)
    cats[:, :, 1] = (0.2, 0.0, 0.0)
    cats[:, :, 4] = (0.001, 0.001, 0.001)  # < 1 %
    b[..., :3] = cats.sum(axis=2)
    b[..., 51] = 0.5 * b[..., 3]  # stats
    h = herkomst_van(b, (1, 1), straal=1)
    assert [c.naam for c in h.categorieen] == ["glans/omgeving", "zijkant", "overig"]
    assert sum(c.aandeel_pct for c in h.categorieen) == pytest.approx(100.0)
    assert h.categorieen[1].rgb_per_pad[0] / h.categorieen[1].rgb[0] == pytest.approx(100.0 / h.categorieen[1].aandeel_pct)
    with pytest.raises(ValueError):
        herkomst_van(b, (100, 100), straal=1)
    with pytest.raises(ValueError):
        herkomst_van(b[..., :3], (1, 1))


def test_lab_bekende_waarden():
    assert lineair_naar_lab((1, 1, 1)) == pytest.approx((100, 0, 0), abs=0.05)
    assert lineair_naar_lab((0, 0, 0)) == pytest.approx((0, 0, 0), abs=1e-6)
    assert lineair_naar_lab((0.2159, 0.2159, 0.2159))[0] == pytest.approx(53.4, abs=0.3)  # sRGB 128


def test_paneel_en_deelbeelden():
    r = herk(cfg(48, 48, zijkant=Paint(color=(0.8, 0.05, 0.05))), spp=16)
    png, h = paneel_png(r.beeld, (24, 24))
    assert png[:8] == b"\x89PNG\r\n\x1a\n" and h.n_pixels > 1
    d = bron_beelden(r.beeld)
    assert d["som"].shape == (48, 48, 3) and set(d) >= {"zijkant", "vloer", "glans/omgeving"}
    img = np.zeros((20, 40, 3), np.uint8)
    assert tekst(img, 1, 1, "TIR 12.5%", schaal=1) > 1 and img.any()
