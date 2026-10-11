"""Maakt het bewijsbeeld van de webinterface (docs/evidence/img/T10-ui*.png) met headless Chrome via Playwright.

Gebruik: uv run python scripts/maak_ui_screenshot.py [--url http://127.0.0.1:8011/] [--uit docs/evidence/img]
Zonder --url start het script zelf een server op een vrije poort. Chrome: /usr/bin/google-chrome (geen download nodig).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
CHROME = "/usr/bin/google-chrome"
ARGS = ["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist", "--no-sandbox"]

SCENE = """
(async () => {
  const c = window.carbonne;
  const cfg = c.cfg();
  Object.assign(cfg, { diameter: 0.35, hoogte: 0.04 });
  cfg.zijkant = { type: "paint", color: "RAL 5010", kind: "glossy", roughness: null, candy_base: "metallic" };
  cfg.onderkant = { type: "paint", color: "#e8e2d0", kind: "matte", roughness: null, candy_base: "metallic" };
  cfg.layers = [
    { height_m: 0.012, seed: 3, edge_margin_mm: 3, items: [{ type: "wood", count: 7, color: [0.45, 0.28, 0.13], radius_mm: [9, 15], thickness_mm: 3, irregularity: 0.12 }] },
    { height_m: 0.026, seed: 5, edge_margin_mm: 3, items: [{ type: "flower", count: 5, color: [0.9, 0.3, 0.45], petals: 6, radius_mm: [8, 12], cup_mm: 2.5, tilt_deg: 15, translucency: 0.4 }] },
  ];
  cfg.render.breedte = 640; cfg.render.hoogte = 360;
  await c.laad(cfg);
})()
"""


def wacht_op_server(url: str, tot: float = 60) -> None:
    t0 = time.time()
    while time.time() - t0 < tot:
        try:
            urllib.request.urlopen(url + "api/presets", timeout=2)
            return
        except OSError:
            time.sleep(0.5)
    raise SystemExit("server komt niet op")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url")
    ap.add_argument("--uit", default=str(ROOT / "docs/evidence/img"))
    ap.add_argument("--poort", type=int, default=8013)
    ap.add_argument("--hq-timeout", type=int, default=600)
    ap.add_argument("--kwaliteit", default="normaal", choices=["concept", "normaal", "hoog", "maximaal"])
    a = ap.parse_args()
    uit = Path(a.uit)
    srv = None
    url = a.url
    if url is None:
        url = f"http://127.0.0.1:{a.poort}/"
        srv = subprocess.Popen(["uv", "run", "carbonne-app", "start", "--port", str(a.poort)], cwd=ROOT,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        wacht_op_server(url)
        with sync_playwright() as p:
            b = p.chromium.launch(executable_path=CHROME, args=ARGS)
            pg = b.new_page(viewport={"width": 1600, "height": 1500})
            fouten: list[str] = []
            pg.on("pageerror", lambda e: fouten.append(str(e)))
            pg.on("console", lambda m: fouten.append(m.text) if m.type == "error" and "404" not in m.text else None)
            pg.goto(url)
            pg.wait_for_function("document.body.dataset.app==='klaar'", timeout=60000)
            pg.evaluate(SCENE)
            pg.wait_for_function("document.body.dataset.preview==='klaar'", timeout=60000)
            pg.wait_for_timeout(1500)
            pg.locator("#preview-kader").screenshot(path=str(uit / "T10-preview.png"))
            # twee HQ-renders (A: glanzend blauw, B: ander blauw) voor de A/B-vergelijking
            for nr in range(2):
                if nr == 1:
                    pg.evaluate("(() => { const c = window.carbonne.cfg(); c.zijkant.color = 'RAL 3020'; window.carbonne.laad(c); })()")
                    pg.wait_for_function("document.body.dataset.preview==='klaar'", timeout=60000)
                pg.select_option("#paneel select:has(option[value=concept])", a.kwaliteit)
                pg.click("#hq-start")
                if nr == 0:
                    pg.wait_for_function("document.getElementById('hq-balk').value > 0", timeout=120000)
                    pg.wait_for_timeout(500)
                    pg.screenshot(path=str(uit / "T10-ui-bezig.png"))
                pg.wait_for_function("document.getElementById('hq-status').textContent.startsWith('Klaar')",
                                     timeout=a.hq_timeout * 1000)
            pg.wait_for_timeout(800)
            pg.screenshot(path=str(uit / "T10-ui.png"), full_page=True)
            print("fouten in de browser:", fouten or "geen")
            b.close()
    finally:
        if srv:
            srv.terminate()


if __name__ == "__main__":
    sys.exit(main())
