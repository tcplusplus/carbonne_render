# Omgeving

## Gekozen variant: `llvm_ad_spectral`
- Mitsuba 3.9.1, drjit, Python 3.12 (`.python-version`), uv 0.13 (geinstalleerd in `~/snap/code/264/.local/bin`;
  zet dat in je `PATH` als `uv` niet gevonden wordt).
- **CUDA werkt niet**: de Quadro P2000 (Pascal, compute capability 6.1, driver 580, OptiX-bibliotheek aanwezig)
  valt af, want Mitsuba/Dr.Jit 3.9 vraagt compute capability >= 7.5 ("compute capability of device too low").
  `cuda_ad_spectral` geeft daarom een ImportError. Dit is een harde hardwaregrens, geen driverprobleem.
- LLVM (libLLVM-18 aanwezig) werkt; `select_variant()` valt dus terug op `llvm_ad_spectral`. Daarmee is de GPU-lock
  voor renders niet nodig, maar de renders gebruiken wel alle 12 CPU-threads.
- `CARBONNE_VARIANT=<variant>` overschrijft de keuze (zonder terugval).

## Rendertijden (smoke: glazen bol, constante omgeving, path, max_depth 12)
| variant | resolutie | spp | tijd |
|---|---|---|---|
| llvm_ad_spectral | 256x256 | 64 | 0.4 s |
| llvm_ad_spectral | 512x512 | 256 | 2.9 s |
| scalar_spectral | 128x128 | 16 | 0.04 s |

Tijden zijn na de eerste JIT-compilatie (kernels worden gecachet); de allereerste run kan enkele seconden langer duren.

## Commando's
- `uv sync` - omgeving opbouwen (herhaal `uv sync --reinstall-package carbonne` als `import carbonne` faalt)
- `uv run pytest -q`, `uv run ruff check src tests`
- `uv run carbonne-smoke [--res 256 --spp 64 --out out/smoke.png]`

## Valkuilen
- Bij het laden meldt Dr.Jit een waarschuwing over de te lage compute capability; die is onschuldig.
- `mi.Bitmap(img)` dwingt de evaluatie af; meet rendertijd altijd inclusief die stap.
- Mitsuba `dielectric` kent alleen een scalaire IOR (geen dispersie); `mi.Mesh` + `set_bsdf` werkt in een scenedict. Eigen meshes: let op windingrichting (test in tests/test_t02.py).

## Omgevingen (T07)
- `uv run python scripts/fetch_assets.py` haalt HDRI's en vloeren (37,8 MB) naar `assets/` (Poly Haven API vereist een User-Agent-header, anders 403).
- `uv run python scripts/render_presets.py --res 192 --spp 512` rendert het overzicht in ~27 s (CPU). Zonder assets werken de presets met een nep-HDRI (`CARBONNE_ASSETS` wijst een andere assetmap aan).
- Mitsuba (float32) verschuift het startpunt van een straal na een botsing met ~1e-3 x max(|coordinaat|). Dunne spleten (< ~0,2 mm bij straal 0,18 m) worden daardoor overgeslagen; `effectieve_gap_mm` in `scene.py` dwingt een veilige minimale spleet af (T03). Geldt ook voor andere dunne structuren.
- `twosided`: eerste kind = voorkant (kant van de normaal, luchtkant), tweede = achterkant (epoxykant); meshnormalen wijzen naar buiten. NEE (next event estimation) dringt niet door het `dielectric`; licht in het blok komt alleen via BSDF-bemonstering, dus beelden van verf onder epoxy zijn korreliger (meer spp nodig).
- Eenstraals-BSDF-test: `tests/test_t03.py::_sample` (vectorieel, SurfaceInteraction3f met `wi`, `sh_frame`, `wavelengths`).

## Inhoud (T06)
- Mitsuba 3.9 heeft geen `difftrans`; doorschijnend dun materiaal = `principledthin` met `diff_trans` (tweezijdig; `eta` 1 schakelt de glans uit). `principledthin` kent geen `specular`-parameter.
- Inhoudsmeshes: `core/inhoud.py`, render `uv run python scripts/render_t06.py` (560 px, 640 spp, 2 beelden: 79 s CPU).
## Validatie (T04)
- `tests/test_physics.py`: minischenes met `volpath` en een homogeen medium (`sigma_t` uniform x `scale`; een rgb-waarde > 1 wordt geweigerd). Een enkel grensvlak met zwart erachter geeft direct de Fresnelreflectie; een `cube` met `interior`-medium geeft Beer-Lambert.
- Vloer op dezelfde hoogte als de onderkant van het blok (Bare of lak): door ray-epsilon lopen stralen door de vloer en zie je de omgeving erdoorheen. Zet de vloer lager (`vloer_omlaag` in `scripts/ab_experiment.py`), of gebruik een plaat.
- `uv run python scripts/ab_experiment.py --res 256 --spp 1024 --schaal 0.7` (11 varianten x 2 zaden, ~3 min op 12 threads).

## Verf en kleur (T05)
- `core/kleur.py::parse_kleur` (hex/RAL naar lineair RGB), RAL-tabel `src/carbonne/data/ral_classic.csv`. `Paint(color="RAL 3020", kind="gloss")` werkt direct.
- Meting zijkant: `uv run python scripts/zijkant_meting.py` (512 px/512 spp: ~25 min op 12 threads; 192-256 px met meer spp geeft dezelfde ROI-gemiddelden en is sneller). Verftypenbeeld: `scripts/render_t05.py --spp 1024 --res 400 --schaal 0.55` (~2 min).
- `roughconductor` samplet enkele procenten onder de horizon (gewicht 0); `twosided` om een one-sided BSDF is nodig om van de epoxykant te testen.
## Renderpijplijn (T08)
- `uv run carbonne-render config.json -o out/ [--ruisdrempel 0.02 --tijdslimiet 600 --max-depth 32 --preview]`; voorbeeld-config `docs/evidence/T08-preset.json`.
- Standaard: path, max_depth 32, 16 spp per pass, drempel 0,02 (relatieve ruis), max 4096 spp.
- Tijd tot drempel 0,02 voor de zwaarste preset (verf onder epoxy, 12 threads): 480x270 110 s, **1280x720 753 s**; tijd is evenredig met het aantal pixels. Meet convergentie op ~320x180 en schaal.
- Cache in `cache/<hash>/` (beeld.exr, beeld.npz, beeld.png, meta.json); de hash bevat een hash van `core/` en `render/`.
- Mitsuba `aov`-integrator zet AOV-kanalen vooraan; de pijplijn neemt kanalen 0-2 aan als RGB.

## Webbackend (T09)
- Start: `uv run carbonne-app start` (127.0.0.1:8011, serveert ook `web/`; `--port N` als 8011 bezet is). Opslag: `configs/` (benoemde configs), `cache/` (render- en HDRI-cache), `out/server/` (losse EXR's).
- API: `GET /api/schema|presets|camera/{naam}|hdri/{omgeving}`, `POST /api/geometrie` (mesh blok + inhoud voor three.js), `POST /api/render` (202 + id), `GET|DELETE /api/render/{id}`, `WS /api/render/{id}` (momentopnamen met `png_base64`, sluit bij klaar/fout/geannuleerd), `GET /api/render/{id}/result.png|.exr`, `GET /api/configs[/naam]`, `POST /api/configs`.
- `maak_app(renderer=..., cache_map=..., configs_map=..., web_map=...)` voor tests; een nep-renderer heeft de signatuur van `carbonne.render.render`. `uv run pytest tests/test_t09.py -q` (2 s, incl. een echte render van 64x48).
- Valkuil: poort 8000 is op deze machine bezet door een ander programma, daarom is de standaard 8011; `ss -ltnp | grep 8011`.
- 1k-HDRI's: RGBE `.hdr` (1024x512, blokgemiddelde van de 2k-bron), in `cache/hdri/`.

## Webfrontend (T10)
- Interface op `http://127.0.0.1:8011/` (standaardpoort sinds T10; 8000 is door een ander programma bezet). Zie `docs/gebruik.md`.
- three.js r170 is gevendored in `web/vendor/three/` (module, OrbitControls, RGBELoader), via een importmap; geen buildstap, geen CDN.
- Playwright (dev-afhankelijkheid) gebruikt het systeem-Chrome: `p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist", "--no-sandbox"])`; er is geen GPU nodig voor WebGL (software). `uv run python scripts/maak_ui_screenshot.py` maakt de bewijsbeelden (ca. 70 s, twee HQ-renders van 640x360 op Normaal: 19 s en 41 s).
- `uv run pytest tests/test_t10.py -q` (ca. 15 s) start een echte server met een nep-renderer en loopt de hele UI door in Chrome; hij slaat zichzelf over als `/usr/bin/google-chrome` ontbreekt.
- Valkuil: in three.js komen transparante objecten (`transparent: true`) niet in de transmissie-pass; inhoud binnen het transmissieve blok moet dus ondoorzichtig zijn om zichtbaar te blijven. Verf op de onderkant moet `DoubleSide` zijn (normalen wijzen omlaag).
- `POST /api/geometrie` geeft sinds T10 per inhoudsitem ook `kleur` (lineair RGB, met de variatie per exemplaar), zodat de preview dezelfde albedo gebruikt.
## Herkomst-integrator (T13)
- `carbonne-herkomst config.json --punt x,y [--straal --max-spp --ev --json -o]`; in code `herkomst_opties(config)` en `herkomst_van(resultaat, gebied)`. De pijplijn registreert hem bij `integrator="herkomst"`.
- **~2x trager dan `path`** (320x180, 64 spp, 6 items: 0,6 s tegen 1,2 s). Geheugen 0,4 GB (320x180), 0,9 GB (640x360); 52 filmkanalen.
- Valkuil: in een Python-integrator met `dr.while_loop` moet de **sampler in de lusstatus**, anders herhalen de toevalsgetallen elke iteratie en is het beeld 1-23 % te donker.
- Spectrale AOV's: deel door `mi.pdf_rgb_spectrum(wl)` voor `mi.spectrum_to_srgb(spec, wl, active)`, anders ~375x te klein.
- Filmkanaalvolgorde bij een Python-integrator: eerst RGB, dan de AOV's (`aov_names()`).
- Shape-id's: `dr.gather` op een tabel met de 1-gebaseerde instantie-id; BSDF-klassenamen zijn `smoothdielectric`, `roughdielectric`, `twosided`, `smoothdiffuse` (niet `dielectric`).
- Bij Bare/verf valt de vloer (y=0) in float32 samen met de onderkant (vloer-lek).

## Wat-als-reeks (T14)
- `uv run carbonne-reeks config.json --param hoogte --waarden 0.02,0.03 --punt 128,72 [--breedte 256 --spp 1024 -o out/reeks]` (ook `--rechthoek x0,y0,x1,y1`); waarden voor objecten/kleuren als JSON-lijst. In code: `carbonne.analyse.reeks.reeks`, `zet_pad`; uitvoer in `carbonne.analyse.uitvoer`.
- Per waarde 2 renders (zaad en zaad+1, halve spp) via de pijplijn en cache; 256x144 met 1024 spp totaal: ~14 s per waarde (herkomst, 12 threads), 2e run uit cache ~1 s. `uv run python scripts/maak_t14_evidence.py` (~2 min).
- Geen matplotlib/PIL: grafieken en tekst met het 5x7-lettertype uit `herkomst_cli` (tekens `°` en `±` toegevoegd in `analyse/uitvoer.py`).

## API herkomst en reeksen (T15)
- `POST /api/render` heeft `herkomst: true` (naast `config` en `opties`): de job gebruikt de herkomst-integrator. `GET /api/render/{id}/herkomst?x=&y=&r=` of `?x0=&y0=&x1=&y1=` (pixels van het resultaatbeeld) geeft JSON met `categorieen` (aandeel, `hex`, `hex_per_pad`, Lab), totaal `hex`/`lab`, `kerngetallen`; 409 bij een render zonder herkomst of nog niet klaar, 422 bij een ongeldig gebied. `GET /api/render/{id}/herkomst.npz` is het ruwe resultaat (`beeld` (h, w, 55), `kanaalnamen`).
- `GET /api/reeks/parameters` (lijst uit `carbonne.analyse.parameters.PARAMETERS`; een test controleert dat elk voorbeeld door `zet_pad` komt), `POST /api/reeks` (202; pad en waarden worden vooraf gevalideerd, 422 bij fout), `GET|DELETE /api/reeks/{id}`, `WS /api/reeks/{id}` (voortgang `{klaar, van, label}` per waarde), `GET /api/reeks/{id}/beeld/{n}.png|contact.png|grafiek.png`. Reeksen delen de ene werkthread met de renders; ze renderen via `JobManager.renderer` (dus ook met een nep-renderer te testen) en de servercache. Een geannuleerde reeks houdt de al afgeronde metingen.
- Nieuwe parameters (bv. door T17) horen ook in `analyse/parameters.py`. Tests: `uv run pytest tests/test_t15.py -q` (~6 s incl. een echte herkomst-render van 64x48).

## Herkomst en reeks in de UI (T16)
- `uv run python scripts/maak_t16_evidence.py` (ca. 4,5 min): echte renders met herkomst (640x360 Normaal: 55-88 s), A/B-klik en reeks; schrijft `docs/evidence/img/T16-*.png`.
- Een reeks met 5 afwerkingen op 256 px / 256 spp duurt ca. 1 min. Reeksbeelden die binnen de ruis vallen worden grijs (CSS `grayscale`), dat is geen render-fout.
- `uv run pytest tests/test_t16.py -q` (ca. 20 s, headless Chrome met nep-herkomstrenderer uit test_t15).
