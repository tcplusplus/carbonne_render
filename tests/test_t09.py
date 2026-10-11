"""T09: webbackend (API-tests met een nep-renderer; één echte render op lage resolutie)."""

from __future__ import annotations

import threading
import time

import numpy as np
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from carbonne.core.config import TableConfig
from carbonne.render.pipeline import RenderResultaat, Voortgang, cache_sleutel
from carbonne.render.uitvoer import png_van_lineair
from carbonne.server.app import maak_app


class NepRenderer:
    """Snelle vervanger van `render`: 3 passes, eigen cache op sleutel, wacht optioneel op een event."""

    def __init__(self, poort: threading.Event | None = None):
        self.aanroepen = 0
        self.cache: dict[str, RenderResultaat] = {}
        self.poort = poort

    def __call__(self, config, opties, on_progress=None, annuleer=None):
        sleutel = cache_sleutel(config, opties)
        if sleutel in self.cache:
            r = self.cache[sleutel]
            return RenderResultaat(r.beeld, r.kanaalnamen, r.png, r.spp, r.ruis, 0.0, "cache", sleutel, True)
        self.aanroepen += 1
        beeld = np.full((8, 8, 3), 0.5, np.float32)
        png = png_van_lineair(beeld)
        for nr in range(1, 4):
            if self.poort is not None:
                while not self.poort.wait(0.01):
                    if annuleer is not None and annuleer.is_set():
                        break
            if annuleer is not None and annuleer.is_set():
                return RenderResultaat(beeld, ["R", "G", "B"], png, nr * 16, None, 0.1, "geannuleerd", sleutel)
            if on_progress:
                on_progress(Voortgang(nr, nr * 16, 48, None, nr * 0.01, png, nr == 3, "max_spp" if nr == 3 else None))
        r = RenderResultaat(beeld, ["R", "G", "B"], png, 48, 0.01, 0.03, "max_spp", sleutel)
        self.cache[sleutel] = r
        return r


@pytest.fixture
def nep():
    return NepRenderer()


@pytest.fixture
def client(tmp_path, nep):
    app = maak_app(renderer=nep, cache_map=tmp_path / "cache", configs_map=tmp_path / "configs",
                   web_map=tmp_path / "web")
    with TestClient(app) as c:
        yield c


def wacht_tot(client, job_id, eind=("klaar", "fout", "geannuleerd"), tijd=10):
    t0 = time.time()
    while time.time() - t0 < tijd:
        s = client.get(f"/api/render/{job_id}").json()
        if s["status"] in eind:
            return s
        time.sleep(0.02)
    raise AssertionError(f"timeout, laatste status {s}")


def test_schema_en_presets(client):
    s = client.get("/api/schema").json()
    assert "diameter" in s["properties"] and "$defs" in s
    p = client.get("/api/presets").json()
    assert {"woonkamer", "studio", "spot"} <= {o["naam"] for o in p["omgevingen"]}
    assert "boven" in p["camera_presets"]
    assert any(r["code"] == "9005" for r in p["ral"])
    cam = client.get("/api/camera/schuin30", params={"diameter": 0.5}).json()
    assert len(cam["positie"]) == 3
    assert client.get("/api/camera/bestaatniet").status_code == 404


def test_geometrie_met_inhoud(client):
    c = TableConfig(layers=[{"height_m": 0.02, "items": [{"count": 2, "type": "wood", "color": [0.4, 0.3, 0.1],
                                                          "radius_mm": [8, 12], "thickness_mm": 3}]}])
    g = client.post("/api/geometrie", json=c.model_dump(mode="json")).json()
    assert set(g["vlakken"]) == {"boven", "mantel", "onder"}
    assert len(g["inhoud"]) == 2 and g["inhoud"][0]["soort"] == "wood"
    v = g["vlakken"]["boven"]
    assert len(v["posities"]) == 3 * (c.segmenten + 1)
    assert max(v["indices"]) < len(v["posities"]) // 3


def test_hdri_1k_synthetisch_en_gecachet(client, tmp_path, monkeypatch):
    monkeypatch.setenv("CARBONNE_ASSETS", str(tmp_path / "geen-assets"))
    r = client.get("/api/hdri/studio")
    assert r.status_code == 200 and r.content.startswith(b"#?RADIANCE")
    _kop, _, rest = r.content.partition(b"-Y ")
    h, _, b = rest.split(b"\n", 1)[0].decode().partition(" +X ")
    assert (int(h), int(b)) == (512, 1024) and len(rest.split(b"\n", 1)[1]) == 512 * 1024 * 4
    t = (tmp_path / "cache" / "hdri" / "donker_1k.hdr")
    assert client.get("/api/hdri/spot").status_code == 200 and t.exists()
    assert client.get("/api/hdri/nietbestaand").status_code == 404


def test_rgbe_roundtrip():
    import pathlib
    import tempfile

    from carbonne.server.hdri import schrijf_rgbe
    rgb = np.array([[[1.0, 0.5, 0.25], [100.0, 2.0, 0.0]]], np.float32)
    with tempfile.TemporaryDirectory() as d:
        p = pathlib.Path(d) / "x.hdr"
        schrijf_rgbe(p, rgb)
        data = p.read_bytes().split(b"\n\n", 1)[1].split(b"\n", 1)[1]
    px = np.frombuffer(data, np.uint8).reshape(1, 2, 4).astype(float)
    uit = px[..., :3] * 2.0 ** (px[..., 3:] - 136)
    assert np.allclose(uit, rgb, rtol=0.02, atol=0.01)


def test_render_levenscyclus_websocket_png_exr(client, nep):
    cfg = TableConfig().model_dump(mode="json")
    r = client.post("/api/render", json={"config": cfg, "opties": {"preview": True}})
    assert r.status_code == 202
    jid = r.json()["id"]
    berichten = []
    with client.websocket_connect(f"/api/render/{jid}") as ws:
        while True:
            try:
                berichten.append(ws.receive_json())
            except WebSocketDisconnect:
                break
            if berichten[-1]["status"] in ("klaar", "fout", "geannuleerd"):
                break
    assert berichten[-1]["status"] == "klaar" and berichten[-1]["resultaat"]["reden"] == "max_spp"
    assert berichten[-1]["png_base64"]
    versies = [b["versie"] for b in berichten]
    assert versies == sorted(set(versies))
    png = client.get(f"/api/render/{jid}/result.png")
    assert png.status_code == 200 and png.content[:8] == b"\x89PNG\r\n\x1a\n"
    exr = client.get(f"/api/render/{jid}/result.exr")
    assert exr.status_code == 200 and exr.content[:4] == b"v/1\x01"


def test_zelfde_hash_komt_uit_cache(client, nep):
    cfg = TableConfig().model_dump(mode="json")
    a = client.post("/api/render", json={"config": cfg}).json()["id"]
    wacht_tot(client, a)
    b = client.post("/api/render", json={"config": cfg}).json()["id"]
    sb = wacht_tot(client, b)
    assert nep.aanroepen == 1 and sb["resultaat"]["uit_cache"] is True and sb["resultaat"]["reden"] == "cache"


def test_een_tegelijk_in_volgorde_en_annuleren(tmp_path):
    poort = threading.Event()
    nep = NepRenderer(poort)
    app = maak_app(renderer=nep, cache_map=tmp_path / "c", configs_map=tmp_path / "k", web_map=tmp_path / "w")
    with TestClient(app) as client:
        c1 = TableConfig().model_dump(mode="json")
        c2 = TableConfig(diameter=0.5).model_dump(mode="json")
        a = client.post("/api/render", json={"config": c1}).json()["id"]
        b = client.post("/api/render", json={"config": c2}).json()["id"]
        time.sleep(0.2)
        assert client.get(f"/api/render/{a}").json()["status"] == "bezig"
        assert client.get(f"/api/render/{b}").json()["status"] == "wachtend"
        assert client.delete(f"/api/render/{b}").json()["status"] == "geannuleerd"
        assert client.delete(f"/api/render/{a}").status_code == 200
        assert wacht_tot(client, a)["status"] == "geannuleerd"
        assert nep.aanroepen == 1  # b is nooit gestart
        assert client.get(f"/api/render/{a}/result.png").status_code in (200, 409)
        assert client.delete("/api/render/nietbestaand").status_code == 404


def test_renderfout_wordt_gemeld(tmp_path):
    def stuk(*a, **k):
        raise RuntimeError("kapot")

    app = maak_app(renderer=stuk, cache_map=tmp_path / "c", configs_map=tmp_path / "k", web_map=tmp_path / "w")
    with TestClient(app) as client:
        jid = client.post("/api/render", json={"config": TableConfig().model_dump(mode="json")}).json()["id"]
        s = wacht_tot(client, jid)
        assert s["status"] == "fout" and "kapot" in s["fout"]
        assert client.get(f"/api/render/{jid}/result.png").status_code == 409


def test_ongeldige_aanvragen(client):
    assert client.post("/api/render", json={"config": {"diameter": -1}}).status_code == 422
    assert client.post("/api/render", json={"config": {}, "opties": {"onzin": 1}}).status_code == 422
    assert client.get("/api/render/nietbestaand").status_code == 404
    with pytest.raises(WebSocketDisconnect), client.websocket_connect("/api/render/nietbestaand"):
        pass


def test_configs_opslaan_en_lezen(client):
    assert client.get("/api/configs").json() == []
    cfg = TableConfig(diameter=0.5).model_dump(mode="json")
    assert client.post("/api/configs", json={"naam": "mijn-tafel_1", "config": cfg}).status_code == 201
    assert client.get("/api/configs").json() == ["mijn-tafel_1"]
    assert client.get("/api/configs/mijn-tafel_1").json()["diameter"] == 0.5
    assert client.get("/api/configs/nee").status_code == 404
    assert client.post("/api/configs", json={"naam": "../boos", "config": cfg}).status_code == 422
    assert client.get("/api/configs/..%2Fboos").status_code in (404, 422)


def test_statische_bestanden_naast_api(tmp_path):
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text("<h1>hoi</h1>")
    app = maak_app(renderer=NepRenderer(), cache_map=tmp_path / "c", configs_map=tmp_path / "k", web_map=web)
    with TestClient(app) as c:
        assert "hoi" in c.get("/").text
        assert "properties" in c.get("/api/schema").json()


def test_echte_render_laag_res(tmp_path):
    app = maak_app(cache_map=tmp_path / "c", configs_map=tmp_path / "k", web_map=tmp_path / "w")
    cfg = TableConfig()
    cfg.render.breedte, cfg.render.hoogte = 64, 48
    with TestClient(app) as client:
        jid = client.post("/api/render", json={"config": cfg.model_dump(mode="json"), "opties": {
            "max_spp": 32, "spp_per_pass": 8, "max_depth": 8}}).json()["id"]
        s = wacht_tot(client, jid, tijd=120)
        assert s["status"] == "klaar", s
        assert client.get(f"/api/render/{jid}/result.png").content[:4] == b"\x89PNG"
        assert client.get(f"/api/render/{jid}/result.exr").status_code == 200
