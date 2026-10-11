"""T27: contracttest tussen de UI (web/js) en de backend-API, en leesbare 422-meldingen.

Alles wat de UI kan maken (standaardwaarden, alle slidergrenzen, alle itemtypes, afwerkingen en lagen) moet door
de backend aanvaard worden. Een falende test wijst aan of de UI-waarde (`web/js/staat.js`) of het schema
(`src/carbonne/core/config.py`) niet klopt."""

from __future__ import annotations

import copy
import itertools
import json
import os
import shutil
import socket
import subprocess
import threading
import time
from pathlib import Path

import pytest
import uvicorn
from fastapi.testclient import TestClient
from test_t15 import NepHerkomst

from carbonne.server.app import maak_app

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web" / "js"
CHROME = "/usr/bin/google-chrome"
IMG = ROOT / "docs" / "evidence" / "img"
BEELDEN = bool(os.environ.get("T27_BEELDEN"))
node = pytest.mark.skipif(shutil.which("node") is None, reason="node ontbreekt")


def js(code: str):
    pre = 'globalThis.document = { createElement: () => ({}), createElementNS: () => ({}) };\n'
    uit = subprocess.run(["node", "--input-type=module", "-e", pre + code], capture_output=True, text=True, check=True).stdout
    return json.loads(uit)


@pytest.fixture(scope="module")
def ui() -> dict:
    """De staten die de UI maakt: standaardconfig, nieuwe lagen/items/afwerkingen en de slidergrenzen."""
    if shutil.which("node") is None:
        pytest.skip("node ontbreekt")
    return js(f"""
const s = await import("{(WEB / 'staat.js').as_uri()}");
const k = await import("{(WEB / 'kleur.js').as_uri()}");
const lagen = {{}};
for (const h of [0.02, 0.03, 0.04, 0.05, 0.06]) lagen[h] = s.nieuweLaag(h);
const afw = {{}};
for (const t of ["bare", "paint", "paintstack", "clearcoat", "plate"]) afw[t] = s.nieuweAfwerking(t, {{ color: "#b22222", kind: "glossy" }});
console.log(JSON.stringify({{ cfg: s.standaardConfig(), lagen, afw, poten: s.nieuwePoten(), wood: s.nieuwItem("wood"), flower: s.nieuwItem("flower"),
  lim: s.LIMIETEN, bereik: Object.fromEntries([0.02, 0.04, 0.06].map((h) => [h, s.laagBereik(h)])),
  wit: k.hexNaarLineair("#ffffff"), zwart: k.hexNaarLineair("#000000"), kamers: Object.keys(s.KWALITEIT), res: s.RESOLUTIES }}));
""")


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    t = tmp_path_factory.mktemp("t27")
    app = maak_app(renderer=NepHerkomst(), cache_map=t / "cache", configs_map=t / "configs", verven_map=t / "verven")
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


GEZIEN: list[dict] = []  # alle configs die de backend aanvaardde; test_client_validator_aanvaardt_alles controleert ze achteraf


def aanvaard(client, cfg: dict, naam: str, mag_niet_passen: bool = False) -> None:
    """Geometrie, render en config-opslaan moeten de config aanvaarden. `mag_niet_passen`: een inhoud die fysiek niet
    past (te vol, buiten het blok) mag 422 geven, maar alleen als leesbare inhoudsmelding en nooit als 500."""
    GEZIEN.append(cfg)
    for pad, body, soort in [("/api/geometrie", cfg, "geometrie"), ("/api/render", {"config": cfg, "opties": {}}, "render"),
                             ("/api/configs", {"naam": "t27", "config": cfg}, "opslaan")]:
        r = client.post(pad, json=body)
        if r.status_code == 422 and mag_niet_passen:
            d = r.json()["detail"]
            assert [f["type"] for f in d] == ["inhoud_past_niet"], f"{naam} ({soort}): {d}"
            assert d[0]["loc"][-2] == "layers" and d[0]["msg"], f"{naam} ({soort}): {d}"
            continue
        assert r.status_code in (200, 201, 202), f"{naam} ({soort}): {r.status_code} {r.text[:600]}"


def met(ui, **w):
    cfg = copy.deepcopy(ui["cfg"])
    cfg.update(w)
    return cfg


# --- 1. de slidergrenzen van de UI liggen binnen het schema ---

def grenzen(schema: dict, model: str, veld: str) -> tuple[float | None, float | None, bool]:
    """(onder, boven, onder_exclusief) van een veld in het JSON-schema, ook binnen anyOf (Optional)."""
    eig = schema["$defs"][model]["properties"][veld] if model != "TableConfig" or "$defs" not in schema or model in schema["$defs"] \
        else schema["properties"][veld]
    lo, hi, excl = None, None, False

    def loop(s):
        nonlocal lo, hi, excl
        tuple_ = "prefixItems" in s  # (min, max)-paar: minItems/maxItems zijn de lengte, geen bereik
        for sleutel in ("minimum", "exclusiveMinimum", "minItems"):
            if sleutel in s and not (tuple_ and sleutel == "minItems"):
                lo, excl = s[sleutel], sleutel == "exclusiveMinimum"
        for sleutel in ("maximum", "exclusiveMaximum", "maxItems"):
            if sleutel in s and not (tuple_ and sleutel == "maxItems"):
                hi = s[sleutel]
        for a in s.get("anyOf", []):
            if a.get("type") != "null":
                loop(a)

    loop(eig)
    return lo, hi, excl


def test_ui_limieten_binnen_schema(client, ui):
    schema = client.get("/api/schema").json()
    gecontroleerd = 0
    for naam, lim in ui["lim"].items():
        for model, veld in lim["schema"]:
            lo, hi, excl = grenzen(schema, model, veld)
            if lo is not None:
                ok = lim["min"] > lo if excl and not lim.get("naarNull") else lim["min"] >= lo
                assert ok, f"UI-min van {naam} ({lim['min']}) valt buiten schema {model}.{veld} (>= {lo}, exclusief={excl})"
                gecontroleerd += 1
            if hi is not None:
                assert lim["max"] <= hi, f"UI-max van {naam} ({lim['max']}) valt buiten schema {model}.{veld} (<= {hi})"
                gecontroleerd += 1
    assert gecontroleerd >= 20  # de test controleert echt iets


def test_nieuwe_laag_hoogte_binnen_blok(ui):
    """Oorzaak 1 van de 422: `nieuweLaag` gaf hoogte*5/1000 (0,1 m bij een blok van 40 mm; schema: <= 0,06)."""
    for h, laag in ui["lagen"].items():
        assert 0.004 <= laag["height_m"] <= float(h) - 0.004, (h, laag)
        assert laag["height_m"] <= 0.06


# --- 2. configs die de UI kan maken, tegen de backend ---

def test_standaardconfig_en_nieuwe_laag_per_blokdikte(client, ui):
    aanvaard(client, ui["cfg"], "standaard")
    for h, laag in ui["lagen"].items():
        for items in ([ui["wood"]], [ui["flower"]], [ui["wood"], ui["flower"]]):
            l = copy.deepcopy(laag)
            l["items"] = copy.deepcopy(items)
            aanvaard(client, met(ui, hoogte=float(h), layers=[l]), f"laag in blok van {h} m, {len(items)} items")


def test_alle_afwerkingen_op_beide_vlakken(client, ui):
    for z, o in itertools.product(["bare", "paint", "paintstack", "clearcoat"], ["bare", "paint", "paintstack", "clearcoat", "plate"]):
        aanvaard(client, met(ui, zijkant=ui["afw"][z], onderkant=ui["afw"][o]), f"zijkant {z} / onderkant {o}")


def test_verf_extremen_kleur_soort_dekking_ruwheid(client, ui):
    lim = ui["lim"]
    for kleur, kind, ruw in itertools.product(["#000000", "#ffffff", "#b22222", "RAL 9005", [0.5, 0.5, 0.5]],
                                              ["matte", "glossy", "metallic", "candy"], [None, lim["ruwheid"]["min"] or 0.01, lim["ruwheid"]["max"]]):
        v = {"type": "paint", "color": kleur, "kind": kind, "roughness": ruw, "candy_base": "white"}
        aanvaard(client, met(ui, zijkant=v, onderkant=v), f"verf {kleur} {kind} {ruw}")
    # gestapeld: 1 en het maximum aantal lagen, dekking op min en max
    for n, dek in itertools.product([lim["verflagen"]["min"], lim["verflagen"]["max"]], [lim["dekking"]["min"], 0.5, lim["dekking"]["max"]]):
        laag = {"type": "paint", "color": "#336699", "kind": "glossy", "roughness": None, "candy_base": "metallic", "dekking": dek}
        st = {"type": "paintstack", "lagen": [laag] * n}
        aanvaard(client, met(ui, zijkant=st, onderkant=st), f"stapel {n} lagen dekking {dek}")
    aanvaard(client, met(ui, onderkant={"type": "clearcoat", "roughness": lim["lakRuwheid"]["min"]}), "lak min")
    aanvaard(client, met(ui, onderkant={"type": "clearcoat", "roughness": lim["lakRuwheid"]["max"]}), "lak max")
    for gap in (lim["spleet"]["min"], lim["spleet"]["max"]):
        aanvaard(client, met(ui, onderkant={**ui["afw"]["plate"], "gap_mm": gap}), f"plaat spleet {gap}")


def test_slidergrenzen_blok_en_scene(client, ui):
    lim = ui["lim"]
    for d, h in itertools.product([lim["diameter"]["min"], 0.35, lim["diameter"]["max"]], [lim["hoogte"]["min"], 0.04, lim["hoogte"]["max"]]):
        aanvaard(client, met(ui, diameter=d, hoogte=h), f"diameter {d} dikte {h}")
    for b, hh in ui["res"]:
        cfg = met(ui)
        cfg["render"].update(breedte=b, hoogte=hh)
        aanvaard(client, cfg, f"resolutie {b}x{hh}")
    for cam in ["kamer", "boven", "schuin30", "schuin60", "zittend", "staand", None]:
        cfg = met(ui)
        cfg["scene"]["camera_preset"] = cam
        aanvaard(client, cfg, f"camera {cam}")
    for omg in ["woonkamer", None]:
        for spot in (True, False):
            cfg = met(ui)
            cfg["scene"].update(omgeving=omg, spot=spot)
            aanvaard(client, cfg, f"omgeving {omg} spot {spot}")


def test_poten_op_min_en_max(client, ui):
    """T26: elke combinatie van de slidergrenzen van de poten, in het kleinste en het grootste blok, en alle metaalsoorten."""
    lim = ui["lim"]
    g = lambda k: (lim[k]["min"], lim[k]["max"])  # noqa: E731
    aanvaard(client, met(ui, poten=ui["poten"]), "standaardpoten")
    for d, n, vorm, afm, rand, lengte in itertools.product(g("diameter"), g("potenAantal"), ["rond", "vierkant"], g("potenAfmeting"),
                                                           g("potenRand"), g("potenHoogte")):
        poten = {**ui["poten"], "aantal": n, "vorm": vorm, "afmeting_mm": afm, "rand_mm": rand, "hoogte_m": lengte}
        aanvaard(client, met(ui, diameter=d, poten=poten), f"poten d {d} n {n} {vorm} afm {afm} rand {rand} lengte {lengte}")
    for metaal in ["geborsteld", "gepoetst", "zwart"]:
        aanvaard(client, met(ui, poten={**ui["poten"], "metaal": metaal}, onderkant=ui["afw"]["plate"]), f"poten {metaal} onder plaat")


def test_inhoud_op_min_en_max(client, ui):
    """Alle sliders van een laag op min of max, in blokken van minimale, gewone en maximale dikte. Fysiek onmogelijke
    combinaties (te vol, buiten het blok) mogen 422 geven, maar alleen als leesbare inhoudsmelding."""
    lim = ui["lim"]
    for blok, d in itertools.product([lim["hoogte"]["min"], 0.04, lim["hoogte"]["max"]], [lim["diameter"]["min"], 0.35, lim["diameter"]["max"]]):
        be = ui["bereik"].get(str(blok)) or {"min": lim["laagHoogte"]["min"], "max": lim["laagHoogte"]["max"]}
        for hoogte, aantal, straal, blaadjes in itertools.product([be["min"], be["max"]], [lim["aantal"]["min"], lim["aantal"]["max"]],
                                                                  [lim["straal"]["min"], lim["straal"]["max"]],
                                                                  [lim["bloemblaadjes"]["min"], lim["bloemblaadjes"]["max"]]):
            hout = {**ui["wood"], "count": aantal, "radius_mm": [straal, straal]}
            bloem = {**ui["flower"], "count": aantal, "radius_mm": [straal, straal], "petals": blaadjes}
            laag = {"height_m": hoogte, "items": [hout, bloem], "seed": lim["seed"]["max"], "edge_margin_mm": 3}
            aanvaard(client, met(ui, hoogte=blok, diameter=d, layers=[laag, {**laag, "seed": 0, "items": [hout]}]),
                     f"blok {blok} d {d} hoogte {hoogte} n {aantal} straal {straal} blaadjes {blaadjes}", mag_niet_passen=True)


def test_gewone_inhoud_past_altijd(client, ui):
    """Wat de UI aanbiedt zonder iets te verzwaren (nieuwe laag, houtschijfje, bloem) past in elk blok en elke diameter."""
    for blok, d in itertools.product([0.02, 0.04, 0.06], [0.2, 0.35, 0.7]):
        laag = ui["lagen"][str(blok)]
        laag = {**laag, "items": [ui["wood"], ui["flower"]]}
        aanvaard(client, met(ui, hoogte=blok, diameter=d, layers=[laag, {**laag, "height_m": laag["height_m"] / 2, "seed": 1}]),
                 f"gewone inhoud blok {blok} d {d}")


def test_inhoud_die_niet_past_geeft_leesbare_422(client, ui):
    cfg = met(ui, layers=[{**ui["lagen"]["0.04"], "height_m": 0.058}])
    for pad, body in [("/api/geometrie", cfg), ("/api/render", {"config": cfg, "opties": {}})]:
        r = client.post(pad, json=body)
        assert r.status_code == 422
        d = r.json()["detail"]
        assert d[0]["loc"][-2:] == ["layers", 0] and "steekt buiten het blok" in d[0]["msg"]


# --- 3. foutmeldingen en begrenzen in de UI-code ---

@node
def test_foutmelding_wijst_het_veld_aan():
    uit = js(f"""
const f = await import("{(WEB / 'fout.js').as_uri()}");
console.log(JSON.stringify([
  f.detailNaarTekst([{{loc: ["body","config","layers",0,"height_m"], msg: "Input should be less than or equal to 0.06", input: 0.1}}]),
  f.detailNaarTekst([{{loc: ["body","layers",1,"items",2,"wood","count"], msg: "Input should be less than or equal to 500", input: 1000}}]),
  f.detailNaarTekst([{{loc: ["body","config","zijkant","paintstack","lagen",0,"dekking"], msg: "m", input: 2}}]),
  f.detailNaarTekst([{{loc: ["body","config","layers",0], msg: "geen plek", type: "inhoud_past_niet"}}]),
  f.detailNaarTekst([1,2,3,4,5].map((i) => ({{loc: ["body","hoogte"], msg: "fout " + i}}))),
  f.detailNaarTekst("kaal"), f.detailNaarTekst({{melding: "m", veld: "x"}}),
]));""")
    assert uit[0] == "Laag 1 > Hoogte in het blok: Input should be less than or equal to 0.06 (nu 0.1)"
    assert uit[1] == "Laag 2 > Item 3 > Aantal: Input should be less than or equal to 500 (nu 1000)"
    assert uit[2] == "Zijkant > Verflaag 1 > Dekking: m (nu 2)"
    assert uit[3] == "Laag 1: geen plek"
    assert uit[4].count("Dikte (hoogte)") == 3 and uit[4].endswith("en nog 2 fouten")
    assert uit[5] == "kaal" and uit[6] == "m"


@node
def test_begrens_haalt_oude_waarden_binnen_bereik(ui):
    """Een in localStorage bewaarde of geladen config van voor T27 (laag op 0,1 m) mag de UI niet blijven breken."""
    cfg = met(ui, hoogte=0.04, diameter=5, layers=[{"height_m": 0.1, "seed": 0, "edge_margin_mm": 3,
                                                   "items": [{**ui["wood"], "count": 1000}, {**ui["flower"], "petals": 99}]}])
    uit = js(f"""
const s = await import("{(WEB / 'staat.js').as_uri()}");
const c = {json.dumps(cfg)};
const veranderd = s.begrens(c);
console.log(JSON.stringify([veranderd, c, s.begrens(c)]));""")
    veranderd, c, tweede = uit
    assert veranderd and not tweede
    assert c["diameter"] == 0.7 and c["layers"][0]["height_m"] == 0.036
    assert c["layers"][0]["items"][0]["count"] == 60 and c["layers"][0]["items"][1]["petals"] == 24


# --- 3b. de UI valideert tegen het JSON-schema van de backend (web/js/schema.js, geen buildstap) ---

def valideer_in_node(schema: dict, configs: list[dict]) -> list[list[dict]]:
    import tempfile

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:  # te groot voor de argumentenlijst van node
        json.dump({"schema": schema, "configs": configs}, f)
    try:
        return js(f"""
const {{ valideer }} = await import("{(WEB / 'schema.js').as_uri()}");
const fs = await import("node:fs");
const {{ schema, configs }} = JSON.parse(fs.readFileSync("{f.name}", "utf8"));
console.log(JSON.stringify(configs.map((c) => valideer(schema, c))));""")
    finally:
        os.unlink(f.name)


@node
def test_client_validator_aanvaardt_alles_wat_de_backend_aanvaardt(client):
    schema = client.get("/api/schema").json()
    assert len(GEZIEN) > 50, "draai de hele module (de configs komen uit de eerdere contracttests)"
    for cfg, fouten in zip(GEZIEN, valideer_in_node(schema, GEZIEN), strict=True):
        assert fouten == [], f"de client-validator wijst een config af die de backend aanvaardt: {fouten[:2]}"


FOUTE_WAARDEN = [  # (pad naar het veld, ongeldige waarde): de backend geeft 422 en de client-validator moet dat ook zien
    (["diameter"], 5), (["diameter"], 0), (["hoogte"], 0.1), (["segmenten"], 3), (["zijkant", "type"], "emmer"),
    (["zijkant"], {"type": "paint", "color": "#fff", "kind": "gloss2"}), (["zijkant"], {"type": "paint", "color": "#fff", "dekking": 2}),
    (["onderkant"], {"type": "plate", "gap_mm": 0}), (["onderkant"], {"type": "clearcoat", "roughness": 0}),
    (["onderkant"], {"type": "paintstack", "lagen": []}), (["scene", "camera", "fov"], 200), (["render", "breedte"], 8),
    (["layers"], [{"height_m": 0.1, "items": []}]), (["layers"], [{"height_m": 0.02, "items": [{"type": "wood", "count": 1000}]}]),
    (["layers"], [{"height_m": 0.02, "items": [{"type": "flower", "petals": 99}]}]),
    (["layers"], [{"height_m": 0.02, "items": [{"type": "kristal"}]}]), (["layers"], [{"height_m": 0.02, "items": [{"type": "wood", "color": [2, 0, 0]}]}]),
    (["layers"], [{"height_m": 0.02, "items": [{"type": "wood", "kleur": "rood"}]}]), (["layers"], [{"items": []}]),
    (["epoxy", "cauchy_a"], 0.5),
]


@node
def test_client_validator_ziet_dezelfde_fouten_als_de_backend(client, ui):
    schema = client.get("/api/schema").json()
    configs = []
    for pad, waarde in FOUTE_WAARDEN:
        cfg = copy.deepcopy(ui["cfg"])
        doel = cfg
        for k in pad[:-1]:
            doel = doel[k]
        doel[pad[-1]] = waarde
        configs.append(cfg)
    uitkomst = valideer_in_node(schema, configs)
    afwijkend = []
    for (pad, waarde), cfg, fouten in zip(FOUTE_WAARDEN, configs, uitkomst, strict=True):
        r = client.post("/api/geometrie", json=cfg)
        if r.status_code != 422 or not fouten:
            afwijkend.append((pad, waarde, r.status_code, fouten))
    # kleurwaarden buiten 0..1 en de grenzen van tuple-velden kent het schema niet (field_validator): die vangt de backend
    toegestaan = [(["layers"], [{"height_m": 0.02, "items": [{"type": "wood", "color": [2, 0, 0]}]}])]
    afwijkend = [a for a in afwijkend if (a[0], a[1]) not in [(p, w) for p, w in toegestaan]]
    assert not afwijkend, afwijkend


@node
def test_limieten_volgen_het_schema(client):
    """`leidLimietenAf` kapt een UI-bereik af op een smaller schema en laat een smaller UI-bereik ongemoeid."""
    schema = client.get("/api/schema").json()
    schema["$defs"]["Paint"]["properties"]["kind"]["enum"] = ["matte", "glossy"]
    schema["properties"]["diameter"]["maximum"] = 0.5
    schema["properties"]["hoogte"]["minimum"] = 0.03
    uit = js(f"""
const s = await import("{(WEB / 'staat.js').as_uri()}");
const schema = {json.dumps(schema)};
s.leidLimietenAf(schema);
console.log(JSON.stringify([s.LIMIETEN.diameter, s.LIMIETEN.hoogte, s.LIMIETEN.aantal, s.ENUMS,
  s.toegestaan(s.VERFSOORTEN, s.ENUMS.verfsoort).map((k) => k[0])]));""")
    diameter, hoogte, aantal, enums, soorten = uit
    assert diameter["max"] == 0.5 and diameter["min"] == 0.2
    assert hoogte["min"] == 0.03 and hoogte["max"] == 0.06
    assert aantal["min"] == 1 and aantal["max"] == 60
    assert soorten == ["matte", "glossy"]


# --- 4. in de browser: gewone paden geven geen 422, een echte fout is leesbaar ---

@pytest.fixture
def live(tmp_path):
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    poort = s.getsockname()[1]
    s.close()
    app = maak_app(renderer=NepHerkomst(), cache_map=tmp_path / "cache", configs_map=tmp_path / "configs", verven_map=tmp_path / "verven")
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
def test_browser_422_leesbaar_en_ingangen_begrensd(live):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME, args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader",
                                                             "--ignore-gpu-blocklist", "--no-sandbox"])
        ctx = b.new_context(viewport={"width": 1400, "height": 1000})
        pg = ctx.new_page()
        antwoorden: list[tuple[str, int]] = []
        pg.on("response", lambda r: antwoorden.append((r.url.rsplit("/", 1)[-1], r.status)) if "/api/geometrie" in r.url else None)
        pg.goto(live)
        pg.wait_for_function("document.body.dataset.app==='klaar'", timeout=60000)

        def wacht():
            pg.wait_for_function("document.body.dataset.preview==='klaar'", timeout=30000)
            pg.wait_for_timeout(300)
            pg.wait_for_function("document.body.dataset.preview==='klaar'")

        def veld(label, nr=0):
            return pg.locator("label.veld", has_text=label).locator("input[type=number]").nth(nr)

        # 1. "+ laag" en een bloem erbij: geen 422 (voor T27 gaf dit hoogte_m 0,1 > 0,06)
        pg.click("text=+ laag >> nth=0")
        pg.click("text=+ bloem")
        wacht()
        assert pg.inner_text("#meldingen") == ""
        assert pg.evaluate("window.carbonne.cfg().layers[0].height_m") == 0.02
        assert all(st == 200 for _, st in antwoorden[-2:]), antwoorden

        # 2. een getal buiten het bereik intypen wordt begrensd, geen 422
        veld("Diameter").fill("5000")
        veld("Aantal").fill("1000")
        wacht()
        assert pg.evaluate("window.carbonne.cfg().diameter") == 0.7
        assert pg.evaluate("window.carbonne.cfg().layers[0].items[0].count") == 60
        assert pg.inner_text("#meldingen") == ""

        # 3. een inhoud die fysiek niet past: de melding noemt de laag en de reden
        veld("Diameter").fill("200")
        veld("Aantal").fill("60")
        veld("Straal (min)").fill("40")
        veld("Straal (max)").fill("40")
        pg.wait_for_function("document.querySelector('#meldingen').textContent.includes('te vol')", timeout=30000)
        tekst = pg.inner_text("#meldingen")
        assert tekst.startswith("Preview: Laag 1: geen plek voor alle items in laag op 20.0 mm") and "422" not in tekst
        assert "[object" not in tekst and "{" not in tekst
        if BEELDEN:
            pg.locator("#meldingen").scroll_into_view_if_needed()
            pg.screenshot(path=str(IMG / "T27-foutmelding.png"), clip={"x": 0, "y": 0, "width": 1400, "height": 420})

        # 4. een render-aanvraag met dezelfde fout geeft dezelfde leesbare tekst
        pg.click("#hq-start")
        pg.wait_for_function("document.querySelector('#hq-status').textContent.includes('Render niet gestart')", timeout=30000)
        assert "Laag 1: geen plek" in pg.inner_text("#hq-status")

        # 5. oude bewaarde config met laag op 0,1 m wordt bij het laden binnen het bereik gebracht
        pg.evaluate("""() => { const c = window.carbonne.cfg(); return window.carbonne.laad({ ...c, hoogte: 0.04, diameter: 0.35,
          layers: [{ height_m: 0.1, seed: 0, edge_margin_mm: 3, items: [{ type: 'wood', count: 3, color: [0.4, 0.3, 0.1], radius_mm: [8, 14], thickness_mm: 3, irregularity: 0.1 }] }] }); }""")
        wacht()
        assert pg.evaluate("window.carbonne.cfg().layers[0].height_m") == 0.036
        assert pg.inner_text("#meldingen") == ""

        # 6. de UI controleert de config tegen het schema vóór verzenden: geen request, wel de veldnaam
        n = len(antwoorden)
        pg.evaluate("() => { window.carbonne.cfg().layers[0].items[0].count = 1000; window.carbonne.ververs(); }")
        pg.wait_for_function("document.querySelector('#meldingen').textContent.includes('Aantal')", timeout=30000)
        assert pg.inner_text("#meldingen") == "Preview: Laag 1 > Item 1 > Aantal: moet hoogstens 500 zijn (nu 1000)"
        assert len(antwoorden) == n
        pg.click("#hq-start")
        pg.wait_for_function("document.querySelector('#hq-status').textContent.includes('Aantal')")
        assert pg.inner_text("#hq-status") == "Render niet gestart: Laag 1 > Item 1 > Aantal: moet hoogstens 500 zijn (nu 1000)"
        b.close()
