"""T16: klik-herkomst en reekspaneel in de browser (nep-renderer met herkomstkanalen uit test_t15)."""

from __future__ import annotations

import socket
import threading
import time
from pathlib import Path

import pytest
import uvicorn
from test_t15 import NepHerkomst

from carbonne.server.app import maak_app

CHROME = "/usr/bin/google-chrome"
KLEIN = "() => { const c = window.carbonne.cfg(); c.render.breedte = 160; c.render.hoogte = 90; return window.carbonne.laad(c); }"


@pytest.fixture
def live(tmp_path):
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    poort = s.getsockname()[1]
    s.close()
    app = maak_app(renderer=NepHerkomst(), cache_map=tmp_path / "cache", configs_map=tmp_path / "configs")
    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=poort, log_level="warning"))
    th = threading.Thread(target=srv.run, daemon=True)
    th.start()
    t0 = time.time()
    while not srv.started and time.time() - t0 < 20:
        time.sleep(0.05)
    yield f"http://127.0.0.1:{poort}/"
    srv.should_exit = True
    th.join(5)


def test_zet_pad_js_en_selectie_js():
    import json
    import shutil
    import subprocess

    if shutil.which("node") is None:
        pytest.skip("node ontbreekt")
    web = Path(__file__).resolve().parents[1] / "web" / "src"
    code = f"""
globalThis.document = {{ createElement: () => ({{}}), createElementNS: () => ({{}}) }};
import {{ plekNaarPixels }} from "{(web / 'selectie.ts').as_uri()}";
console.log(JSON.stringify([plekNaarPixels({{x0: .5, y0: .25, x1: .5, y1: .25}}, 320, 180),
  plekNaarPixels({{x0: .1, y0: .2, x1: .3, y1: .6}}, 100, 50), plekNaarPixels({{x0: 1, y0: 1, x1: 1, y1: 1}}, 100, 50)]));
"""
    uit = subprocess.run(["node", "--input-type=module", "-e", code], capture_output=True, text=True, check=True).stdout
    punt, vak, hoek = json.loads(uit)
    assert punt == {"x": 160, "y": 45, "r": 2}
    assert vak == {"x0": 10, "y0": 10, "x1": 30, "y1": 30}
    assert hoek["x"] == 100 and hoek["y"] == 50


@pytest.mark.skipif(not Path(CHROME).exists(), reason="google-chrome ontbreekt")
def test_browser_herkomst_en_reeks(live):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME, args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader",
                                                             "--ignore-gpu-blocklist", "--no-sandbox"])
        pg = b.new_page(viewport={"width": 1500, "height": 1400})
        fouten: list[str] = []
        pg.on("pageerror", lambda e: fouten.append(str(e)))
        pg.on("console", lambda m: fouten.append(m.text) if m.type == "error" and "404" not in m.text else None)
        pg.goto(live)
        pg.wait_for_function("document.body.dataset.app==='klaar'", timeout=60000)
        pg.evaluate(KLEIN)

        # render zonder herkomst: klik geeft een plek, maar geen herkomst
        pg.click("#hq-start")
        pg.wait_for_function("document.getElementById('hq-status').textContent.startsWith('Klaar')", timeout=30000)
        kader = pg.locator("#hq-kader").bounding_box()
        pg.mouse.click(kader["x"] + kader["width"] * 0.5, kader["y"] + kader["height"] * 0.5)
        pg.wait_for_selector("#hq-kader .markering.punt")
        assert "geen herkomst" in pg.inner_text("#herkomst")

        # render mee met herkomst: klik toont de balk, de stalen en de kerngetallen
        pg.check("#hq-herkomst")
        pg.click("#hq-start")
        pg.wait_for_function("document.querySelectorAll('.thumb').length === 2", timeout=30000)
        pg.mouse.click(kader["x"] + kader["width"] * 0.5, kader["y"] + kader["height"] * 0.5)
        pg.wait_for_selector("#herkomst .balk .seg")
        assert pg.locator("#herkomst .balk .seg").count() >= 2
        assert "interne reflecties" in pg.inner_text("#herkomst") and "weg in epoxy" in pg.inner_text("#herkomst")
        som = pg.evaluate("[...document.querySelectorAll('#herkomst .hk-tabel tbody td.r')].reduce((a, e) => a + parseFloat(e.textContent.replace(',', '.')), 0)")
        assert abs(som - 100) < 0.5

        # slepen kiest een rechthoek
        pg.mouse.move(kader["x"] + 30, kader["y"] + 20)
        pg.mouse.down()
        pg.mouse.move(kader["x"] + 90, kader["y"] + 60, steps=4)
        pg.mouse.up()
        pg.wait_for_selector("#hq-kader .markering.gebied")

        # A/B: dezelfde klik geeft de herkomst van beide beelden
        pg.click("#hq-start")
        pg.wait_for_function("document.querySelectorAll('.thumb').length === 3", timeout=30000)
        pg.select_option("#vergelijk-modus", "naast")
        pg.locator(".vergelijk-beeld img").first.click()
        pg.wait_for_function("document.querySelectorAll('#herkomst .hk').length === 2")

        # reeks over de dikte op de gekozen plek
        pg.select_option("[data-rol=parameter]", "hoogte")
        pg.click("[data-rol=reeks-start]")
        pg.wait_for_selector(".reeks-item", timeout=30000)
        pg.wait_for_function("document.querySelectorAll('.reeks-item').length === 5", timeout=30000)
        assert pg.locator("svg.grafiek").count() == 2
        pg.locator(".reeks-item").nth(3).click()
        pg.wait_for_function("Math.abs(window.carbonne.cfg().hoogte - 0.05) < 1e-9")
        assert fouten == []
        b.close()
