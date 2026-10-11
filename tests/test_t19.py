"""T19: verf-API (vertalen, bibliotheek, ChatGPT-vraag, uit-tekst)."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from carbonne.core.config import TableConfig
from carbonne.server.app import maak_app

BLOK = {"merk": "Sikkens", "product": "Rubbol", "kleurnaam": "Roodbruin", "kleurcode": "RAL 3011",
        "hex": "#7b1e1e", "glansgraad": "hoogglans", "glans_gu_60": 85, "effect": "geen", "transparant": False,
        "ondergrond_candy": None, "bron_url": "https://example.com/tds.pdf", "opmerking": None}


@pytest.fixture
def client(tmp_path):
    app = maak_app(cache_map=tmp_path / "c", configs_map=tmp_path / "k", web_map=tmp_path / "w",
                   verven_map=tmp_path / "verven")
    with TestClient(app) as c:
        yield c


def test_schema_en_vertaal(client):
    s = client.get("/api/verven/schema").json()
    assert "hex" in s["properties"]
    r = client.post("/api/verven/vertaal", json=BLOK)
    assert r.status_code == 200
    v = r.json()
    assert v["paint"]["kind"] == "glossy" and v["uitleg"]
    assert client.get("/api/verven").json() == []  # niets opgeslagen
    assert client.post("/api/verven/vertaal", json={"merk": "x"}).status_code == 422


def test_bibliotheek_crud_en_config(client):
    r = client.post("/api/verven", json=BLOK)
    assert r.status_code == 201
    slug = r.json()["slug"]
    assert slug == "sikkens-rubbol-roodbruin"
    assert client.post("/api/verven", json=BLOK).status_code == 409
    assert client.post("/api/verven?overschrijf=1", json=BLOK).status_code == 201
    lijst = client.get("/api/verven").json()
    assert lijst == [{"slug": slug, "naam": "Sikkens Rubbol Roodbruin", "staal": lijst[0]["staal"]}]
    assert len(lijst[0]["staal"]) == 7 and lijst[0]["staal"].startswith("#")
    item = client.get(f"/api/verven/{slug}").json()
    assert item["vertaling"]["paint"]["bibliotheek_id"] == slug
    # in een config gebruiken
    cfg = TableConfig(diameter=0.4).model_dump(mode="json")
    cfg["zijkant"] = item["vertaling"]["paint"]
    assert client.post("/api/configs", json={"naam": "met-verf", "config": cfg}).status_code == 201
    assert client.get("/api/configs/met-verf").json()["zijkant"]["bibliotheek_id"] == slug
    assert client.delete(f"/api/verven/{slug}").status_code == 200
    assert client.get(f"/api/verven/{slug}").status_code == 404
    assert client.delete(f"/api/verven/{slug}").status_code == 404
    assert client.get("/api/verven/..%2Fboos").status_code in (404, 422)


def test_chatgpt_vraag(client):
    t = client.get("/api/verven/chatgpt-vraag", params={"merk": "Sikkens", "product": "Rubbol", "kleur": "RAL 3011"}).json()["vraag"]
    for w in ("Sikkens", "Rubbol", "RAL 3011", "glans_gu_60", "bron_url", "null", "ALLEEN", "candy", "transparant"):
        assert w in t
    assert '"properties"' in t  # het schema zit erin


ANTWOORD_CODEBLOK = "```json\n" + json.dumps(BLOK, indent=2) + "\n```"
ANTWOORD_INLEIDING = ("Natuurlijk! Ik heb het technische fiche gevonden. Hier is het resultaat:\n\n```\n"
                      + json.dumps(BLOK) + "\n```\n\nLet op: de hex komt van de kleurkaart {niet} van het fiche.")
ANTWOORD_ONTBREKEND = "Hier:\n```json\n" + json.dumps({k: v for k, v in BLOK.items() if k not in ("hex", "kleurcode")}) + "\n```"


@pytest.mark.parametrize("tekst", [ANTWOORD_CODEBLOK, ANTWOORD_INLEIDING, "Zo:\n" + json.dumps(BLOK) + "\nSucces!"])
def test_uit_tekst_ok(client, tekst):
    r = client.post("/api/verven/uit-tekst", json={"tekst": tekst})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["eigenschappen"]["hex"] == "#7b1e1e" and j["vertaling"]["paint"]["kind"] == "glossy"


def test_uit_tekst_ontbrekende_optionele_velden_en_nulls(client):
    blok = {"hex": "#112233", "glansgraad": None, "glans_gu_60": None, "effect": "geen"}
    r = client.post("/api/verven/uit-tekst", json={"tekst": "```json\n" + json.dumps(blok) + "\n```"})
    assert r.status_code == 200


def test_uit_tekst_fouten(client):
    r = client.post("/api/verven/uit-tekst", json={"tekst": ANTWOORD_ONTBREKEND})
    assert r.status_code == 422
    d = r.json()["detail"]
    assert "hex" in d["melding"]
    r = client.post("/api/verven/uit-tekst", json={"tekst": "```json\n" + json.dumps({**BLOK, "glansgraad": "kletsnat"}) + "\n```"})
    assert r.status_code == 422 and r.json()["detail"]["veld"] == "glansgraad"
    r = client.post("/api/verven/uit-tekst", json={"tekst": "Sorry, dat fiche vond ik niet."})
    assert r.status_code == 422 and "JSON" in r.json()["detail"]["melding"]
    r = client.post("/api/verven/uit-tekst", json={"tekst": json.dumps({**BLOK, "kleur": "rood"})})
    assert r.status_code == 422 and r.json()["detail"]["veld"] == "kleur"
