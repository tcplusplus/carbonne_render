"""Maakt de bewijsbeelden van T16 (docs/evidence/img/T16-*.png) met headless Chrome: echte renders met herkomst,
klik op de render, A/B-herkomst en een reeks over de dikte.

Gebruik: uv run python scripts/maak_t16_evidence.py [--punt 0.5,0.4] [--reeks-parameter hoogte]
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import urllib.request
from pathlib import Path

from maak_ui_screenshot import ARGS, CHROME, ROOT, wacht_op_server
from playwright.sync_api import sync_playwright

SCENE = """
(async () => {
  const c = window.carbonne, cfg = c.cfg();
  Object.assign(cfg, { diameter: 0.35, hoogte: 0.04 });
  cfg.zijkant = { type: "paint", color: "#c1121f", kind: "matte", roughness: null, candy_base: "metallic" };
  cfg.onderkant = { type: "plate", color: "#000000", gap_mm: 1.0, kind: "matte", roughness: null, candy_base: "metallic" };
  cfg.scene.omgeving = "studio"; cfg.scene.camera_preset = "schuin30";
  cfg.render.breedte = 640; cfg.render.hoogte = 360;
  await c.laad(cfg);
})()
"""


def wacht_klaar(pg, n: int, tijd: int) -> None:
    pg.wait_for_function(f"document.querySelectorAll('.thumb').length === {n}", timeout=tijd * 1000)


def sleep(pg, k, x0, y0, x1, y1) -> None:
    """Sleep een rechthoek (fracties van het beeld `k`)."""
    pg.mouse.move(k["x"] + k["width"] * x0, k["y"] + k["height"] * y0)
    pg.mouse.down()
    pg.mouse.move(k["x"] + k["width"] * x1, k["y"] + k["height"] * y1, steps=5)
    pg.mouse.up()


def klip(pg, van: str, tot: str, pad: Path) -> None:
    """Screenshot van het gebied vanaf de bovenkant van `van` tot de onderkant van `tot`."""
    a, z = pg.locator(van).bounding_box(), pg.locator(tot).bounding_box()
    pg.screenshot(path=str(pad), full_page=True, clip={"x": a["x"], "y": a["y"], "width": a["width"], "height": z["y"] + z["height"] - a["y"]})


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--uit", default=str(ROOT / "docs/evidence/img"))
    ap.add_argument("--poort", type=int, default=8016)
    ap.add_argument("--gebied", default="0.42,0.31,0.58,0.35", help="fracties x0,y0,x1,y1 van de gekozen plek (achterrand)")
    ap.add_argument("--reeks-parameter", default="zijkant")
    ap.add_argument("--kwaliteit", default="normaal")
    ap.add_argument("--timeout", type=int, default=900)
    a = ap.parse_args()
    uit = Path(a.uit)
    fx0, fy0, fx1, fy1 = (float(v) for v in a.gebied.split(","))
    url = f"http://127.0.0.1:{a.poort}/"
    srv = subprocess.Popen(["uv", "run", "carbonne-app", "start", "--port", str(a.poort)], cwd=ROOT,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        wacht_op_server(url)
        with sync_playwright() as p:
            b = p.chromium.launch(executable_path=CHROME, args=ARGS)
            pg = b.new_page(viewport={"width": 1500, "height": 1300})
            fouten: list[str] = []
            pg.on("pageerror", lambda e: fouten.append(str(e)))
            pg.on("console", lambda m: fouten.append(m.text) if m.type == "error" and "404" not in m.text else None)
            pg.goto(url)
            pg.wait_for_function("document.body.dataset.app==='klaar'", timeout=60000)
            pg.evaluate(SCENE)
            pg.wait_for_function("document.body.dataset.preview==='klaar'", timeout=60000)
            pg.wait_for_timeout(1500)
            pg.select_option("#paneel select:has(option[value=concept])", a.kwaliteit)
            pg.check("#hq-herkomst")
            for nr in range(2):
                if nr == 1:
                    pg.evaluate("(() => { const c = window.carbonne.cfg(); c.zijkant.color = '#1d4ed8'; window.carbonne.laad(c); })()")
                    pg.wait_for_function("document.body.dataset.preview==='klaar'", timeout=60000)
                pg.click("#hq-start")
                wacht_klaar(pg, nr + 1, a.timeout)
            pg.evaluate("(() => { const c = window.carbonne.cfg(); c.zijkant.color = '#c1121f'; window.carbonne.laad(c); })()")
            sleep(pg, pg.locator("#hq-kader").bounding_box(), fx0, fy0, fx1, fy1)
            pg.wait_for_selector("#herkomst .balk .seg")
            pg.wait_for_timeout(500)
            hq_id = pg.evaluate("window.carbonne.hq.laatste.id")
            urllib.request.urlretrieve(f"{url}api/render/{hq_id}/result.png", str(uit / "T15-render-herkomst.png"))
            klip(pg, ".stage-rij", "#herkomst-sectie", uit / "T16-herkomst.png")
            # A/B naast elkaar: dezelfde klik geeft de herkomst van beide
            pg.select_option("#vergelijk-modus", "naast")
            sleep(pg, pg.locator(".vergelijk-beeld img").first.bounding_box(), fx0, fy0, fx1, fy1)
            pg.wait_for_function("document.querySelectorAll('#herkomst .hk').length === 2")
            pg.wait_for_timeout(500)
            klip(pg, "#herkomst-sectie", "#vergelijken", uit / "T16-herkomst-ab.png")
            # reeks
            pg.select_option("[data-rol=parameter]", a.reeks_parameter)
            pg.click("[data-rol=reeks-start]")
            pg.wait_for_function("document.querySelectorAll('.reeks-item').length >= 5 && !document.querySelector('[data-rol=reeks-start]').disabled",
                                 timeout=a.timeout * 1000)
            pg.wait_for_timeout(500)
            pg.locator("#reeks-sectie").screenshot(path=str(uit / "T16-reeks.png"))
            print("fouten in de browser:", fouten or "geen")
            b.close()
    finally:
        srv.terminate()


if __name__ == "__main__":
    sys.exit(main())
