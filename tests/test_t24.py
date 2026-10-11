"""T24: gestapelde verflagen (Kubelka-Munk)."""

import numpy as np
import pytest

from carbonne.core.config import Paint, PaintStack, TableConfig
from carbonne.core.lagen import dikte_uit_dekking, effectieve_verf, km_doorlating, km_reflectie
from carbonne.core.scene import afwerking_bsdf, build_scene
from carbonne.core.variant import select_variant

C = TableConfig()
WIT, ZWART, ROOD = (0.9, 0.9, 0.9), (0.02, 0.02, 0.02), (0.7, 0.05, 0.05)
BLAUW = (0.1, 0.3, 0.8)


@pytest.mark.parametrize("kind", ["matte", "glossy", "metallic", "candy"])
def test_een_laag_is_bit_identiek_aan_paint(kind):
    p = Paint(color=ROOD, kind=kind)
    assert afwerking_bsdf(PaintStack(lagen=[p]), C) == afwerking_bsdf(p, C)


def test_km_grenzen():
    assert km_reflectie(BLAUW, 0.0, WIT) == pytest.approx(WIT)  # geen laag
    assert km_reflectie(BLAUW, 500.0, WIT) == pytest.approx(BLAUW, abs=1e-6)  # oneindig dik = R_inf
    assert km_doorlating(BLAUW, 0.0) == pytest.approx(1.0)
    assert km_doorlating(BLAUW, 500.0) == pytest.approx(0.0, abs=1e-6)
    t = dikte_uit_dekking(BLAUW, 0.6)
    assert np.mean(km_doorlating(BLAUW, t)) == pytest.approx(0.4, abs=1e-6)


def test_doorschijnend_laat_ondergrond_zien():
    top = Paint(color=BLAUW, dekking=0.5)
    over = {n: np.array(effectieve_verf([top, Paint(color=k)]).color) for n, k in
            [("wit", WIT), ("zwart", ZWART), ("rood", ROOD)]}
    assert over["wit"].sum() > over["rood"].sum() > over["zwart"].sum()
    # wit eronder: lichter dan de toplaag zelf; zwart eronder: donkerder
    assert over["wit"].sum() > sum(BLAUW) > over["zwart"].sum()


def test_ondoorzichtige_toplaag_verbergt_ondergrond():
    top = Paint(color=BLAUW)
    a = effectieve_verf([top, Paint(color=WIT)])
    assert a is top and effectieve_verf([top, Paint(color=ZWART)]) is top


def test_binnenkant_ziet_omgekeerde_volgorde():
    st = PaintStack(lagen=[Paint(color=WIT), Paint(color=BLAUW, dekking=0.5)])
    b = afwerking_bsdf(st, C)
    assert b["back"]["reflectance"]["value"] == list(WIT)  # epoxykant: witte grondlaag, ondoorzichtig
    assert b["front"]["reflectance"]["value"] != list(WIT)  # luchtkant: doorschijnend blauw over wit


def test_dekking_nul_is_onzichtbaar():
    r = effectieve_verf([Paint(color=BLAUW, dekking=0.0), Paint(color=ROOD)])
    assert r.color == pytest.approx(ROOD)


def test_ongeldige_combinaties():
    with pytest.raises(ValueError, match="matte of glossy"):
        effectieve_verf([Paint(color=BLAUW, kind="candy", dekking=0.5), Paint(color=WIT)])
    with pytest.raises(ValueError, match="metallic"):
        effectieve_verf([Paint(color=BLAUW, dekking=0.5), Paint(color=WIT, kind="metallic")])
    with pytest.raises(ValueError):
        PaintStack(lagen=[])


def test_json_rondreis_en_losse_doorschijnende_paint():
    c = TableConfig(zijkant=PaintStack(lagen=[Paint(color=WIT), Paint(color=BLAUW, dekking=0.4)]),
                    onderkant=Paint(color=BLAUW, dekking=0.5))
    c2 = TableConfig.model_validate_json(c.model_dump_json())
    assert c2 == c and c2.zijkant.type == "paintstack"
    assert afwerking_bsdf(c2.onderkant, C)["type"] == "twosided"


def test_rendert():
    select_variant()
    import mitsuba as mi

    c = TableConfig(zijkant=PaintStack(lagen=[Paint(color=WIT), Paint(color=BLAUW, dekking=0.5, kind="glossy")]))
    c.render.breedte, c.render.hoogte, c.render.spp = 48, 36, 8
    img = np.array(mi.render(mi.load_dict(build_scene(c)), spp=8))
    assert np.isfinite(img).all() and img.std() > 0




def test_api_geometrie_en_schema_met_stapel(tmp_path):
    from fastapi.testclient import TestClient

    from carbonne.server.app import maak_app

    app = maak_app(renderer=None, cache_map=tmp_path / "cache", configs_map=tmp_path / "configs", web_map=tmp_path / "web")
    with TestClient(app) as client:
        _api(client)


def _api(client):
    c = TableConfig(zijkant=PaintStack(lagen=[Paint(color=WIT), Paint(color=BLAUW, dekking=0.5)]))
    r = client.post("/api/geometrie", json=c.model_dump(mode="json"))
    assert r.status_code == 200 and "mantel" in r.json()["vlakken"]
    assert "PaintStack" in str(client.get("/api/schema").json())
