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
- Start: `uv run carbonne-app start` (127.0.0.1:8000, serveert ook `web/`; `--port N` als 8000 bezet is). Opslag: `configs/` (benoemde configs), `cache/` (render- en HDRI-cache), `out/server/` (losse EXR's).
- API: `GET /api/schema|presets|camera/{naam}|hdri/{omgeving}`, `POST /api/geometrie` (mesh blok + inhoud voor three.js), `POST /api/render` (202 + id), `GET|DELETE /api/render/{id}`, `WS /api/render/{id}` (momentopnamen met `png_base64`, sluit bij klaar/fout/geannuleerd), `GET /api/render/{id}/result.png|.exr`, `GET /api/configs[/naam]`, `POST /api/configs`.
- `maak_app(renderer=..., cache_map=..., configs_map=..., web_map=...)` voor tests; een nep-renderer heeft de signatuur van `carbonne.render.render`. `uv run pytest tests/test_t09.py -q` (2 s, incl. een echte render van 64x48).
- Valkuil: poort 8000 kan door iets anders bezet zijn; `ss -ltnp | grep 8000`.
- 1k-HDRI's: RGBE `.hdr` (1024x512, blokgemiddelde van de 2k-bron), in `cache/hdri/`.
