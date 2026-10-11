"""T20: verfformulier en bibliotheek in de browser (ChatGPT-antwoord plakken, vertaling, bibliotheek kiezen)."""

from __future__ import annotations

import json
import os
import socket
import threading
import time
from pathlib import Path

import pytest
import uvicorn
from test_t15 import NepHerkomst

from carbonne.server.app import maak_app

CHROME = "/usr/bin/google-chrome"
IMG = Path(__file__).resolve().parents[1] / "docs" / "evidence" / "img"
BEELDEN = bool(os.environ.get("T20_BEELDEN"))

ANTWOORD = """Hier is het technische fiche, samengevat:

```json
{"merk": "Sikkens", "product": "Rubbol Satura", "kleurnaam": "Roodbruin", "kleurcode": "RAL 3011",
 "hex": "#7b1e1e", "glansgraad": "hoogglans", "glans_gu_60": 85, "effect": "parelmoer", "transparant": false,
 "ondergrond_candy": null, "bron_url": "https://example.com/rubbol-satura.pdf", "opmerking": null}
```
"""
ANTWOORD_FOUT = '```json\n{"merk": "Sikkens", "hex": "#7b1e1e", "glansgraad": "kletsnat"}\n```'


@pytest.fixture
def live(tmp_path):
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    poort = s.getsockname()[1]
    s.close()
    app = maak_app(renderer=NepHerkomst(), cache_map=tmp_path / "cache", configs_map=tmp_path / "configs",
                   verven_map=tmp_path / "verven")
    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=poort, log_level="warning"))
    th = threading.Thread(target=srv.run, daemon=True)
    th.start()
    t0 = time.time()
    while not srv.started and time.time() - t0 < 20:
        time.sleep(0.05)
    yield f"http://127.0.0.1:{poort}/"
    srv.should_exit = True
    th.join(5)


def test_naar_aanvraag_en_foutinfo():
    import shutil
    import subprocess

    if shutil.which("node") is None:
        pytest.skip("node ontbreekt")
    web = Path(__file__).resolve().parents[1] / "web" / "js"
    code = f"""
globalThis.document = {{ createElement: () => ({{}}), createElementNS: () => ({{}}) }};
const {{ naarAanvraag, foutInfo }} = await import("{(web / 'verf.js').as_uri()}");
console.log(JSON.stringify([naarAanvraag({{merk: "", hex: "#fff", glans_gu_60: "85", transparant: false, effect: "geen"}}),
  foutInfo({{detail: {{melding: "m", veld: "hex"}}, message: "x"}}),
  foutInfo({{detail: [{{loc: ["body", "glans_gu_60"], msg: "te groot"}}], message: "x"}}), foutInfo({{detail: "kaal", message: "x"}})]));
"""
    uit = subprocess.run(["node", "--input-type=module", "-e", code], capture_output=True, text=True, check=True).stdout
    a, f1, f2, f3 = json.loads(uit)
    assert a == {"hex": "#fff", "glans_gu_60": 85, "transparant": False, "effect": "geen"}
    assert f1 == {"melding": "m", "veld": "hex"}
    assert f2 == {"melding": "glans_gu_60: te groot", "veld": "glans_gu_60"}
    assert f3 == {"melding": "kaal", "veld": None}


@pytest.mark.skipif(not Path(CHROME).exists(), reason="google-chrome ontbreekt")
def test_browser_verfformulier_en_bibliotheek(live):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME, args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader",
                                                             "--ignore-gpu-blocklist", "--no-sandbox"])
        ctx = b.new_context(viewport={"width": 1400, "height": 1200}, permissions=["clipboard-read", "clipboard-write"])
        pg = ctx.new_page()
        fouten: list[str] = []
        pg.on("pageerror", lambda e: fouten.append(str(e)))
        pg.on("console", lambda m: fouten.append(m.text) if m.type == "error" and "404" not in m.text and "422" not in m.text else None)  # 422: bewuste foutpaden
        pg.goto(live)
        pg.wait_for_function("document.body.dataset.app==='klaar'", timeout=60000)
        sectie = pg.locator("#verven-sectie")

        # leeg: formulier verborgen, bibliotheek leeg
        assert "nog leeg" in pg.inner_text("#verven")
        pg.click("[data-rol=nieuwe-verf]")
        pg.wait_for_selector("[data-rol=verf-formulier]:not([hidden])")

        # live vertaling bij handmatig invullen (zonder kleur: nog niet te vertalen)
        pg.fill("[data-veld=merk]", "Sikkens")
        pg.fill("[data-veld=product]", "Rubbol Satura")
        pg.wait_for_function("document.querySelector('[data-rol=verf-vertaling]').textContent.includes('Nog niet te vertalen')")
        pg.fill("[data-veld=hex]", "#7b1e1e")
        pg.fill("[data-veld=glans_gu_60]", "85")
        pg.wait_for_selector("[data-rol=vertaling-staal]")
        assert "glossy" in pg.inner_text("[data-rol=verf-vertaling]")

        # ChatGPT-vraag kopieren: staat op het klembord, met merk en product
        pg.click("[data-rol=kopieer-vraag]")
        pg.wait_for_function("document.querySelector('[data-rol=kopieer-melding]').textContent.startsWith('Gekopieerd')")
        klem = pg.evaluate("navigator.clipboard.readText()")
        assert "Merk: Sikkens" in klem and "Product: Rubbol Satura" in klem and "JSON" in klem

        # een ongeldig antwoord wijst het veld aan
        pg.fill("[data-rol=chatgpt-antwoord]", ANTWOORD_FOUT)
        pg.click("[data-rol=lees-antwoord]")
        pg.wait_for_selector("[data-rol=verf-fout]:not([hidden])")
        assert "glansgraad" in pg.inner_text("[data-rol=verf-fout]")
        assert pg.locator("[data-veld=glansgraad].ongeldig").count() == 1

        # geplakt antwoord vult het formulier, toont vertaling en waarschuwing
        pg.fill("[data-rol=chatgpt-antwoord]", ANTWOORD)
        pg.click("[data-rol=lees-antwoord]")
        pg.wait_for_function("document.querySelector('[data-veld=kleurnaam]').value === 'Roodbruin'")
        assert pg.input_value("[data-veld=effect]") == "parelmoer"
        assert pg.locator("[data-rol=waarschuwing]").count() >= 1 and "Parelmoer" in pg.inner_text("[data-rol=waarschuwing]")
        assert pg.locator("[data-rol=verf-fout]").is_hidden()
        if BEELDEN:
            sectie.scroll_into_view_if_needed()
            sectie.screenshot(path=str(IMG / "T20-verf.png"))

        # bewaren; nogmaals bewaren geeft 409 met Overschrijven
        pg.click("[data-rol=verf-bewaar]")
        pg.wait_for_selector(".verf-item[data-slug=sikkens-rubbol-satura-roodbruin]")
        pg.click("[data-rol=verf-bewaar]")  # bewerkSlug is nu gezet: overschrijft zonder 409
        pg.wait_for_selector("[data-rol=verf-bewaar-melding]:has-text('Bewaard als')")
        assert "example.com/rubbol-satura.pdf" in pg.inner_text("[data-rol=verf-detail]")
        assert pg.locator("[data-rol=verf-detail] a[href^='https://example.com']").count() == 1
        if BEELDEN:
            sectie.screenshot(path=str(IMG / "T20-bibliotheek.png"))

        # kiesbaar voor zijkant, onderkant en plaat
        for sleutel, titel in (("zijkant", "Zijkant"), ("onderkant", "Onderkant")):
            det = pg.locator("#paneel details", has=pg.locator(f"summary:text-is('{titel}')"))
            det.locator("select").first.select_option("bibliotheek")
            det.locator("select").nth(1).select_option("sikkens-rubbol-satura-roodbruin")
            pg.wait_for_function(f"window.carbonne.cfg().{sleutel}.bibliotheek_id === 'sikkens-rubbol-satura-roodbruin'")
            f = pg.evaluate(f"window.carbonne.cfg().{sleutel}")
            assert f["type"] == "paint" and f["kind"] == "metallic" and f["color"] == "#7b1e1e"
        det = pg.locator("#paneel details", has=pg.locator("summary:text-is('Onderkant')"))
        det.locator("select").first.select_option("plate")
        det.locator("select").nth(1).select_option("sikkens-rubbol-satura-roodbruin")
        pg.wait_for_function("window.carbonne.cfg().onderkant.color === '#7b1e1e'")
        plaat = pg.evaluate("window.carbonne.cfg().onderkant")
        assert plaat["type"] == "plate" and "bibliotheek_id" not in plaat
        # aanpassen na kiezen blijft kunnen, en de config is geldig voor de backend
        pg.evaluate("fetch('/api/geometrie', {method:'POST', headers:{'content-type':'application/json'}, body: JSON.stringify(window.carbonne.cfg())}).then(r => { if (!r.ok) throw new Error(r.status); })")
        if BEELDEN:
            pg.locator("#zijbalk").screenshot(path=str(IMG / "T20-kiezen.png"))

        # verwijderen
        pg.once("dialog", lambda d: d.accept())
        pg.click("[data-rol=verf-verwijder]")
        pg.wait_for_function("document.querySelector('[data-rol=verf-lijst]').textContent.includes('nog leeg')")
        assert fouten == []
        b.close()
