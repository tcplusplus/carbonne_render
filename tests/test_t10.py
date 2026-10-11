"""T10: webfrontend (statische controles, kleurfuncties via node, end-to-end in headless Chrome met een nep-renderer)."""

from __future__ import annotations

import json
import re
import shutil
import socket
import subprocess
import threading
import time
from pathlib import Path

import pytest
import uvicorn
from fastapi.testclient import TestClient
from test_t09 import NepRenderer

from carbonne.server import app as app_mod
from carbonne.server.app import maak_app

WEB = Path(__file__).resolve().parents[1] / "web"
CHROME = "/usr/bin/google-chrome"


def test_standaardpoort_is_8011(monkeypatch):
    gezien = {}
    monkeypatch.setattr(uvicorn, "run", lambda app, host, port: gezien.update(host=host, port=port))
    app_mod.main(["start"])
    assert gezien == {"host": "127.0.0.1", "port": 8011}


def test_index_en_modules_worden_geserveerd(tmp_path):
    with TestClient(maak_app(cache_map=tmp_path / "c", configs_map=tmp_path / "k")) as c:
        html = c.get("/").text
        assert "importmap" in html and "js/main.js" in html
        assert "benadering" in html  # de preview is zichtbaar als benadering gemarkeerd
        # elk relatief geimporteerd modulebestand bestaat en wordt geserveerd
        todo, gezien = ["js/main.js"], set()
        while todo:
            m = todo.pop()
            if m in gezien:
                continue
            gezien.add(m)
            r = c.get("/" + m)
            assert r.status_code == 200, m
            for imp in re.findall(r'from "\./([\w./-]+)"', r.text):
                todo.append(str(Path(m).parent / imp))
        assert {"js/hq.js", "js/preview.js", "js/paneel.js", "js/vergelijk.js"} <= gezien
        for pad in ("vendor/three/three.module.js", "vendor/three/addons/controls/OrbitControls.js",
                    "vendor/three/addons/loaders/RGBELoader.js", "uitleg/matte-lak.svg"):
            assert c.get("/" + pad).status_code == 200, pad


def test_geometrie_geeft_kleur_van_inhoud(tmp_path):
    with TestClient(maak_app(cache_map=tmp_path / "c", configs_map=tmp_path / "k")) as c:
        cfg = {"layers": [{"height_m": 0.02, "items": [{"type": "wood", "count": 2, "color": [0.45, 0.28, 0.13]}]}]}
        g = c.post("/api/geometrie", json=cfg).json()
        assert g["inhoud"] and all(abs(a - b) < 0.05 for it in g["inhoud"] for a, b in zip(it["kleur"], [0.45, 0.28, 0.13]))


@pytest.mark.skipif(shutil.which("node") is None, reason="node ontbreekt")
def test_kleurfuncties_js():
    code = f"""
import {{ hexNaarLineair, lineairNaarHex, tekstNaarHex, waardeNaarHex }} from "{(WEB / 'js/kleur.js').as_uri()}";
const ral = {{ "9005": "131516" }};
console.log(JSON.stringify([hexNaarLineair("#ffffff"), lineairNaarHex(hexNaarLineair("#336699")), tekstNaarHex("RAL 9005", ral),
  tekstNaarHex("#abc", ral), tekstNaarHex("RAL 1", ral), waardeNaarHex([1, 1, 1], ral), waardeNaarHex("RAL 9005", ral)]));
"""
    uit = subprocess.run(["node", "--input-type=module", "-e", code], capture_output=True, text=True, check=True).stdout
    wit, rond, ral, kort, slecht, drie, tekst = json.loads(uit)
    assert wit == [1, 1, 1] and rond == "#336699" and ral == "#131516" and kort == "#aabbcc"
    assert slecht is None and drie == "#ffffff" and tekst == "#131516"


# --- end-to-end ---
@pytest.fixture
def live(tmp_path):
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    poort = s.getsockname()[1]
    s.close()
    app = maak_app(renderer=NepRenderer(), cache_map=tmp_path / "cache", configs_map=tmp_path / "configs")
    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=poort, log_level="warning"))
    th = threading.Thread(target=srv.run, daemon=True)
    th.start()
    t0 = time.time()
    while not srv.started and time.time() - t0 < 20:
        time.sleep(0.05)
    yield f"http://127.0.0.1:{poort}/"
    srv.should_exit = True
    th.join(5)


@pytest.mark.skipif(not Path(CHROME).exists(), reason="google-chrome ontbreekt")
def test_browser_end_to_end(live):
    from playwright.sync_api import sync_playwright

    kleuren_js = """() => { const c = document.querySelector('#preview-kader canvas'); const t = document.createElement('canvas');
      t.width = c.width; t.height = c.height; const x = t.getContext('2d'); x.drawImage(c, 0, 0);
      const d = x.getImageData(0, 0, t.width, t.height).data; const s = new Set();
      for (let i = 0; i < d.length; i += 4 * 97) s.add((d[i] << 16) | (d[i + 1] << 8) | d[i + 2]); return s.size; }"""
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME, args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader",
                                                             "--ignore-gpu-blocklist", "--no-sandbox"])
        pg = b.new_page(viewport={"width": 1500, "height": 1000})
        fouten: list[str] = []
        pg.on("pageerror", lambda e: fouten.append(str(e)))
        pg.on("console", lambda m: fouten.append(m.text) if m.type == "error" and "404" not in m.text else None)
        pg.goto(live)
        pg.wait_for_function("document.body.dataset.preview==='klaar'", timeout=60000)
        assert pg.evaluate(kleuren_js) > 20  # de preview tekent echt iets (geen effen vlak)
        assert "benadering" in pg.inner_text("#stage")

        # de preview verandert mee: verf op de zijkant verandert de pixels van de preview
        voor = pg.locator("#preview-kader").screenshot()
        pg.select_option("#paneel details:nth-of-type(2) select", "paint")
        pg.fill(".kleurtekst", "RAL 3020")
        pg.wait_for_function("document.body.dataset.preview==='klaar'")
        pg.wait_for_timeout(500)
        assert pg.locator("#preview-kader").screenshot() != voor
        assert pg.locator("figure.schets img").count() >= 1  # uitlegschets bij de afwerking

        # HQ: de camera van de preview gaat mee, de nep-render meldt klaar, het resultaat komt in de geschiedenis
        pg.click("#hq-start")
        pg.wait_for_function("document.getElementById('hq-status').textContent.startsWith('Klaar')", timeout=30000)
        assert pg.locator(".thumb").count() == 1
        cam = pg.evaluate("window.carbonne.vergelijk.lijst[0].cfg.scene")
        assert cam["camera_preset"] is None and len(cam["camera"]["positie"]) == 3
        assert cam["camera"]["positie"][2] > 0  # schuin30: camera staat voor het tafeltje

        # tweede render met een andere kleur, dan A/B
        pg.fill(".kleurtekst", "#00aa00")
        pg.click("#hq-start")
        pg.wait_for_function("document.querySelectorAll('.thumb').length === 2", timeout=30000)
        assert "zijkant.color" in pg.inner_text("#verschil")

        # opslaan en laden
        pg.fill("#config-naam", "proef")
        pg.click("#config-opslaan")
        pg.wait_for_function("document.querySelectorAll('#config-lijst option').length === 1")
        pg.fill(".kleurtekst", "#0000ff")
        pg.click("#config-laden")
        pg.wait_for_function("window.carbonne.cfg().zijkant.color.toLowerCase().startsWith('#00a')")
        assert fouten == []
        b.close()
