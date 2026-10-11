"""T15: API voor herkomst en wat-als-reeksen (nep-renderer met herkomstkanalen; één echte render op lage res.)."""

from __future__ import annotations

import threading
import time

import numpy as np
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from carbonne.analyse.parameters import PARAMETERS
from carbonne.analyse.reeks import zet_pad
from carbonne.core.config import TableConfig
from carbonne.core.herkomst import N_CAT, STAT_NAMEN
from carbonne.render.pipeline import RenderResultaat, Voortgang, cache_sleutel
from carbonne.render.uitvoer import png_van_lineair
from carbonne.server.app import maak_app

NK = 3 + N_CAT * 3 + len(STAT_NAMEN)


class NepHerkomst:
    """Levert 55-kanaalsbeelden: categorie 1 (zijkant) en 8 (glans/omgeving?) krijgen vaste bijdragen; de
    helderheid hangt af van `config.hoogte` zodat een reeks over de hoogte meetbaar verschilt."""

    def __init__(self, poort: threading.Event | None = None):
        self.aanroepen = 0
        self.poort = poort
        self.opties: list = []

    def __call__(self, config, opties, on_progress=None, annuleer=None):
        self.aanroepen += 1
        self.opties.append(opties)
        if self.poort is not None:
            while not self.poort.wait(0.01):
                if annuleer is not None and annuleer.is_set():
                    break
        sleutel = cache_sleutel(config, opties)
        if annuleer is not None and annuleer.is_set():
            b = np.zeros((6, 8, 3), np.float32)
            return RenderResultaat(b, ["R", "G", "B"], png_van_lineair(b), 1, None, 0.0, "geannuleerd", sleutel)
        h = config.render.hoogte, config.render.breedte
        beeld = np.zeros((h[0], h[1], NK), np.float32)
        cats = beeld[..., 3 : 3 + N_CAT * 3].reshape(h[0], h[1], N_CAT, 3)
        cats[:, :, 1, :] = (0.2, 0.05, 0.05)  # "zijkant"
        cats[:, :, 0, :] = np.array([0.3, 0.3, 0.3]) * (config.hoogte / 0.04)  # glans/omgeving
        beeld[..., :3] = cats.sum(axis=2)
        beeld[..., 3 + N_CAT * 3] = 0.5  # n_tir (gewicht met luminantie)
        png = png_van_lineair(beeld[..., :3])
        if on_progress:
            on_progress(Voortgang(1, 8, 8, 0.01, 0.01, png, True, "max_spp"))
        return RenderResultaat(beeld, ["R", "G", "B"] + [f"k{i}" for i in range(3, NK)], png, 8, 0.01, 0.01,
                               "max_spp", sleutel)


def wacht(client, pad, tijd=10):
    t0 = time.time()
    while time.time() - t0 < tijd:
        s = client.get(pad).json()
        if s["status"] in ("klaar", "fout", "geannuleerd"):
            return s
        time.sleep(0.02)
    raise AssertionError(f"timeout, laatste status {s}")


def maak(tmp_path, renderer):
    return TestClient(maak_app(renderer=renderer, cache_map=tmp_path / "c", configs_map=tmp_path / "k",
                               web_map=tmp_path / "w"))


def klein() -> dict:
    c = TableConfig()
    c.render.breedte, c.render.hoogte = 32, 24
    return c.model_dump(mode="json")


# --- herkomst ---

def test_render_met_herkomst_punt_gebied_en_npz(tmp_path):
    nep = NepHerkomst()
    with maak(tmp_path, nep) as client:
        jid = client.post("/api/render", json={"config": klein(), "herkomst": True}).json()["id"]
        s = wacht(client, f"/api/render/{jid}")
        assert s["status"] == "klaar" and s["herkomst"] is True
        assert nep.opties[0].integrator == "herkomst" and "eta" in nep.opties[0].integrator_params
        d = client.get(f"/api/render/{jid}/herkomst", params={"x": 10, "y": 8, "r": 3}).json()
        assert d["n_pixels"] > 1 and d["straal"] == 3
        assert d["hex"].startswith("#") and len(d["hex"]) == 7 and len(d["lab"]) == 3
        assert sum(c["aandeel_pct"] for c in d["categorieen"]) == pytest.approx(100.0)
        namen = {c["naam"] for c in d["categorieen"]}
        assert any("zijkant" in n for n in namen)
        assert all(len(c["hex"]) == 7 and len(c["hex_per_pad"]) == 7 and len(c["lab"]) == 3 for c in d["categorieen"])
        assert d["kerngetallen"]["n_tir"] > 0  # = padstatistiek / luminantie, hier een vast getal uit de nep
        g = client.get(f"/api/render/{jid}/herkomst", params={"x0": 0, "y0": 0, "x1": 16, "y1": 12}).json()
        assert g["n_pixels"] == 16 * 12 and g["straal"] is None
        z = client.get(f"/api/render/{jid}/herkomst.npz")
        assert z.status_code == 200
        import io
        npz = np.load(io.BytesIO(z.content))
        assert npz["beeld"].shape == (24, 32, NK) and len(npz["kanaalnamen"]) == NK


def test_herkomst_fouten(tmp_path):
    nep = NepHerkomst()
    with maak(tmp_path, nep) as client:
        zonder = client.post("/api/render", json={"config": klein()}).json()["id"]
        wacht(client, f"/api/render/{zonder}")
        assert client.get(f"/api/render/{zonder}/herkomst", params={"x": 1, "y": 1}).status_code == 409
        assert client.get(f"/api/render/{zonder}/herkomst.npz").status_code == 409
        jid = client.post("/api/render", json={"config": klein(), "herkomst": True}).json()["id"]
        wacht(client, f"/api/render/{jid}")
        u = f"/api/render/{jid}/herkomst"
        assert client.get(u).status_code == 422  # geen gebied
        assert client.get(u, params={"x": 1}).status_code == 422
        assert client.get(u, params={"x": 1, "y": 1, "x0": 0, "y0": 0, "x1": 2, "y1": 2}).status_code == 422
        assert client.get(u, params={"x": 500, "y": 500, "r": 2}).status_code == 422  # buiten het beeld
        assert client.get(u, params={"x": 1, "y": 1, "r": 0}).status_code == 422
        assert client.get("/api/render/nietbestaand/herkomst", params={"x": 1, "y": 1}).status_code == 404


def test_herkomst_nog_niet_klaar(tmp_path):
    poort = threading.Event()
    with maak(tmp_path, NepHerkomst(poort)) as client:
        jid = client.post("/api/render", json={"config": klein(), "herkomst": True}).json()["id"]
        assert client.get(f"/api/render/{jid}/herkomst", params={"x": 1, "y": 1}).status_code == 409
        poort.set()
        wacht(client, f"/api/render/{jid}")


# --- reeksen ---

def reeks_aanvraag(**kw) -> dict:
    a = {"config": klein(), "parameter": "hoogte", "waarden": [0.02, 0.04, 0.06], "gebied": [16, 12],
         "breedte": 32, "spp": 4}
    a.update(kw)
    return a


def test_parameters_lijst_is_geldig():
    c = TableConfig(layers=[{"height_m": 0.02}])
    assert len({p["pad"] for p in PARAMETERS}) == len(PARAMETERS)
    for p in PARAMETERS:
        assert {"pad", "type", "omschrijving", "voorbeelden"} <= set(p) and p["voorbeelden"]
        pad = p["pad"].replace(".n.", ".0.")
        for w in p["voorbeelden"]:
            if pad in ("zijkant.color", "onderkant.color", "onderkant.gap_mm"):
                continue  # alleen geldig bij een verf/plaat; hieronder apart
            zet_pad(c, pad, w)
    c2 = zet_pad(c, "onderkant", {"type": "plate", "color": "#000000", "gap_mm": 1.0})
    for p in PARAMETERS:
        if p["pad"] in ("onderkant.color", "onderkant.gap_mm"):
            for w in p["voorbeelden"]:
                zet_pad(c2, p["pad"], w)
    c3 = zet_pad(c, "zijkant", {"type": "paint", "color": "#ff0000"})
    for w in next(p for p in PARAMETERS if p["pad"] == "zijkant.color")["voorbeelden"]:
        zet_pad(c3, "zijkant.color", w)


def test_parameters_endpoint(tmp_path):
    with maak(tmp_path, NepHerkomst()) as client:
        r = client.get("/api/reeks/parameters")
        assert r.status_code == 200
        pads = {p["pad"] for p in r.json()}
        assert {"hoogte", "zijkant", "onderkant", "scene.camera.fov"} <= pads


def test_reeks_levenscyclus_websocket_json_en_beelden(tmp_path):
    nep = NepHerkomst()
    with maak(tmp_path, nep) as client:
        r = client.post("/api/reeks", json=reeks_aanvraag())
        assert r.status_code == 202
        rid = r.json()["id"]
        berichten = []
        with client.websocket_connect(f"/api/reeks/{rid}") as ws:
            while True:
                try:
                    berichten.append(ws.receive_json())
                except WebSocketDisconnect:
                    break
                if berichten[-1]["status"] in ("klaar", "fout", "geannuleerd"):
                    break
        assert berichten[-1]["status"] == "klaar", berichten[-1]
        klaar = [b["voortgang"]["klaar"] for b in berichten if b["voortgang"]]
        assert klaar == sorted(klaar) and klaar[-1] == 3 and berichten[-1]["voortgang"]["van"] == 3
        d = client.get(f"/api/reeks/{rid}").json()
        res = d["resultaat"]
        assert [m["waarde"] for m in res["metingen"]] == [0.02, 0.04, 0.06] and res["parameter"] == "hoogte"
        assert res["metingen"][0]["de2000"] == 0 and res["metingen"][2]["de2000"] > 1  # helderder bij dikker
        assert len(d["urls"]["beelden"]) == 3
        for u in [*d["urls"]["beelden"], d["urls"]["contact"], d["urls"]["grafiek"]]:
            png = client.get(u)
            assert png.status_code == 200 and png.content[:8] == b"\x89PNG\r\n\x1a\n", u
        assert client.get(f"/api/reeks/{rid}/beeld/3.png").status_code == 404
        assert nep.aanroepen == 6  # 3 waarden x 2 zaden


def test_reeks_deelt_wachtrij_met_renders_en_annuleren(tmp_path):
    poort = threading.Event()
    nep = NepHerkomst(poort)
    with maak(tmp_path, nep) as client:
        a = client.post("/api/render", json={"config": klein()}).json()["id"]
        rid = client.post("/api/reeks", json=reeks_aanvraag()).json()["id"]
        time.sleep(0.2)
        assert client.get(f"/api/render/{a}").json()["status"] == "bezig"
        assert client.get(f"/api/reeks/{rid}").json()["status"] == "wachtend"
        assert client.get(f"/api/reeks/{rid}/contact.png").status_code == 409
        assert client.delete(f"/api/reeks/{rid}").json()["status"] == "geannuleerd"
        poort.set()
        wacht(client, f"/api/render/{a}")
        assert nep.aanroepen == 1  # de reeks is nooit gestart
        # een lopende reeks annuleren: gedeeltelijk resultaat blijft beschikbaar
        poort.clear()
        r2 = client.post("/api/reeks", json=reeks_aanvraag()).json()["id"]
        time.sleep(0.2)
        assert client.get(f"/api/reeks/{r2}").json()["status"] == "bezig"
        poort.set()
        client.delete(f"/api/reeks/{r2}")
        assert wacht(client, f"/api/reeks/{r2}")["status"] in ("geannuleerd", "klaar")


def test_reeks_annuleren_midden_in(tmp_path):
    class Een(NepHerkomst):
        def __call__(self, config, opties, on_progress=None, annuleer=None):
            if self.aanroepen >= 2 and annuleer is not None:
                annuleer.set()
            return super().__call__(config, opties, on_progress, annuleer)

    with maak(tmp_path, Een()) as client:
        rid = client.post("/api/reeks", json=reeks_aanvraag()).json()["id"]
        s = wacht(client, f"/api/reeks/{rid}")
        assert s["status"] == "geannuleerd"
        d = client.get(f"/api/reeks/{rid}").json()
        assert d["resultaat"]["geannuleerd"] is True and len(d["resultaat"]["metingen"]) == 1


def test_reeks_ongeldige_aanvragen(tmp_path):
    with maak(tmp_path, NepHerkomst()) as client:
        post = lambda **kw: client.post("/api/reeks", json=reeks_aanvraag(**kw))  # noqa: E731
        r = post(parameter="bestaat.niet")
        assert r.status_code == 422 and "ongeldig parameterpad" in r.json()["detail"]
        assert post(waarden=[0.5]).status_code == 422  # hoogte buiten bereik
        assert post(waarden=[]).status_code == 422
        assert post(gebied=[1, 2, 3]).status_code == 422
        assert post(spp=1).status_code == 422
        assert post(onzin=1).status_code == 422
        assert client.get("/api/reeks/nietbestaand").status_code == 404
        assert client.delete("/api/reeks/nietbestaand").status_code == 404
        with pytest.raises(WebSocketDisconnect), client.websocket_connect("/api/reeks/nietbestaand"):
            pass
        assert not client.app.state.jobs.reeksen  # geen job voor een afgekeurde aanvraag


def test_reeks_fout_in_job_wordt_gemeld(tmp_path):
    with maak(tmp_path, NepHerkomst()) as client:
        rid = client.post("/api/reeks", json=reeks_aanvraag(gebied=[500, 500])).json()["id"]
        s = wacht(client, f"/api/reeks/{rid}")
        assert s["status"] == "fout" and "bevat geen pixels" in s["fout"]


# --- echt ---

def test_echte_render_met_herkomst_en_punt(tmp_path):
    app = maak_app(cache_map=tmp_path / "c", configs_map=tmp_path / "k", web_map=tmp_path / "w")
    cfg = TableConfig(zijkant={"type": "paint", "color": "#c1121f"})
    cfg.render.breedte, cfg.render.hoogte = 64, 48
    with TestClient(app) as client:
        jid = client.post("/api/render", json={"config": cfg.model_dump(mode="json"), "herkomst": True, "opties": {
            "max_spp": 32, "spp_per_pass": 16, "max_depth": 8}}).json()["id"]
        s = wacht(client, f"/api/render/{jid}", tijd=240)
        assert s["status"] == "klaar", s
        d = client.get(f"/api/render/{jid}/herkomst", params={"x": 32, "y": 24, "r": 3}).json()
        assert d["n_pixels"] > 1 and sum(c["aandeel_pct"] for c in d["categorieen"]) == pytest.approx(100.0)
        assert d["categorieen"] and d["hex"].startswith("#")
