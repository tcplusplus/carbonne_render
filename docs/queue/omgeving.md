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
