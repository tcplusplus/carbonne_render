# Gebruik

## Starten
```
export PATH=$HOME/snap/code/264/.local/bin:$PATH   # alleen op deze machine, zodat `uv` gevonden wordt
uv sync
uv run carbonne-app start --port 8011               # 8011 is de standaard; 8000 is hier door een ander programma bezet
```
Open daarna <http://127.0.0.1:8011/>. De server luistert alleen op 127.0.0.1 en serveert de interface (`web/`) en
de API. Stoppen: Ctrl+C. Geen buildstap: de interface is gewone ES-modules; three.js staat in `web/vendor/three/`
(versie r170), dus er is geen internet nodig. Hij werkt in een moderne browser met WebGL.

Opslag: benoemde configs in `configs/`, rendercache en 1k-HDRI's in `cache/`, losse EXR's in `out/server/`.

## De pagina
Links het **paneel** met alle instellingen, midden-boven de **preview** (links) en de **HQ-render** (rechts), eronder
het **vergelijkpaneel**. Elke wijziging in het paneel werkt de preview direct bij (kort na het loslaten).

**De preview is een benadering.** Ze toont vorm, kleuren, inhoud en camera, maar de belichting, het licht dat door de
epoxy loopt en de reflecties zijn een snelle schets (three.js). De HQ-render rekent het licht wel fysisch uit; de
inkleuring van het tafeltje (bijvoorbeeld wat verf in contact met epoxy doet) moet je daar beoordelen.

### Paneel
- **Tafeltje**: diameter (200 tot 700 mm), dikte (20 tot 60 mm) en de brekingsindex van de epoxy (Cauchy-A; B blijft
  0,0045 um^2).
- **Zijkant en onderkant**: type (onbehandeld, verf, matte kleurloze lak; onderkant ook: plaat met luchtspleet). Bij
  verf kies je het verftype (mat, glanzend, metallic, candy) en de kleur met de kleurkiezer, als hex (`#b22222`) of
  als RAL Classic (`RAL 5010`; het tekstveld geeft suggesties). Een rode rand betekent: ongeldige invoer, de laatste
  geldige kleur blijft actief. Ruwheid (GGX alpha) leeg laten (0) geeft de standaard van het verftype. Rechts onder
  de keuze staat de **uitlegschets** (doorsnede met stralen, uit `web/uitleg/`) van de gekozen afwerking.
- **Inhoud (lagen)**: "+ laag" voegt een gietlaag toe op een hoogte in het blok; per laag houtschijfjes en bloemen met
  aantal, kleur en straal. "Seed" bepaalt de (reproduceerbare) plaatsing. Past de inhoud niet, dan staat er een
  melding rechtsboven en blijft de vorige preview staan.
- **Omgeving en camera**: omgeving (HDRI + vloer, of een witte constante omgeving), camerapreset (boven, schuin30,
  schuin60, zittend, staand) of "vrij" zodra je zelf draait, en een extra spot boven het tafeltje.
  In de preview: slepen draait, scrollen zoomt, rechtermuisknop schuift.
- **Belichting en kwaliteit**: EV (stops; werkt direct op de preview en op de PNG van de HQ-render), resolutie
  (de preview krijgt dezelfde beeldverhouding) en kwaliteit (Concept, Normaal, Hoog, Maximaal: de doelruis en de
  bovengrens aan samples). Meer samples betekent minder ruis en een langere render; de tijd schaalt met het aantal
  pixels en samples (zie `docs/queue/omgeving.md`).
- **Configuraties**: "Opslaan" bewaart de huidige config onder een naam (letters, cijfers, `_` en `-`), inclusief
  de huidige camera; "Laden" haalt hem terug. De laatste staat onthoudt de browser zelf ook.

### HQ-render
- **Render HQ** stuurt de config met de **huidige camera van de preview** naar de server. Het beeld bouwt
  progressief op (pass voor pass), met een voortgangsbalk, het aantal samples, de ruis en de verstreken tijd.
  Er draait een render tegelijk; een tweede aanvraag wacht in de rij van de server.
- **Annuleer** stopt de lopende render; het laatste tussenbeeld blijft staan.
- Na afloop: **PNG** en **EXR** (lineair, alle kanalen) om te bewaren. Een identieke render komt direct uit de cache.

### Vergelijken
Elke afgeronde render komt in de geschiedenis (de laatste 8, met samples en tijd). Per render:
**A** en **B** kiezen de twee beelden die je vergelijkt, **Terug** zet de instellingen van die render terug in het
paneel. Weergave: **schuifbalk** (links A, rechts B) of **naast elkaar**. Onder het beeld staat welke instellingen
verschillen tussen A en B. De geschiedenis leeft in de pagina: herladen wist hem (configs blijven bewaard).

## Screenshot maken
`uv run python scripts/maak_ui_screenshot.py [--url ...]` start (zo nodig) een server, drijft Chrome headless aan met
Playwright en schrijft de bewijsbeelden naar `docs/evidence/img/T10-*.png`. Playwright staat als dev-afhankelijkheid
in het uv-project en gebruikt `/usr/bin/google-chrome`; er wordt geen browser gedownload.
