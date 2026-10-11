# Gebruik

## Starten
```
export PATH=$HOME/snap/code/264/.local/bin:$PATH   # alleen op deze machine, zodat `uv` gevonden wordt
uv sync
uv run carbonne-app start --port 8011               # 8011 is de standaard; 8000 is hier door een ander programma bezet
```
Open daarna <http://127.0.0.1:8011/>. De server luistert alleen op 127.0.0.1 en serveert de interface (`web/dist/`) en
de API. Stoppen: Ctrl+C. De interface is TypeScript (Vite, geen framework) en de **gebouwde versie `web/dist/` staat
in git**, dus voor gewoon gebruik is `uv run carbonne-app start` genoeg: geen Node en geen internet nodig. three.js
zit in de bundel (uit npm). Hij werkt in een moderne browser met WebGL.

### Frontend ontwikkelen (alleen als je `web/src/` wijzigt)
Vereist Node (getest met v24) en npm. Eenmalig `npm install` (zet alles in `node_modules/`, dat niet in git staat).
- `npm run build`: genereert de types, draait `tsc --noEmit` en schrijft `web/dist/`. **Commit `web/dist/` mee**;
  `tests/test_t28.py` faalt als `web/dist/` achterloopt op de bronnen.
- `npm run dev`: Vite-ontwikkelserver met herladen op <http://127.0.0.1:5173/>; hij stuurt `/api` door naar de
  backend op poort 8011 (start die apart met `uv run carbonne-app start`).
- `npm run types`: schrijft het Pydantic-schema (`scripts/schema_dump.py`) naar `web/src/types/*.schema.json` en
  genereert daaruit `web/src/types/config.ts` en `verf.ts` (`scripts/maak-types.mjs`, json-schema-to-typescript). Draai dit
  na elke wijziging in `core/config.py` of `core/verf.py`; de test controleert dat de bestanden bij elkaar passen.
- `npm run typecheck`: alleen `tsc --noEmit` (strikt). Een verkeerde waarde, zoals `count: "veel"`, compileert niet.
- Broncode: `web/src/*.ts` (de oude modules van `web/js/`), stijl `web/css/app.css`, uitlegschetsen `web/public/uitleg/`,
  handgeschreven API-types `web/src/types/api.ts`.

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
  de keuze staat de **uitlegschets** (doorsnede met stralen, uit `web/public/uitleg/`) van de gekozen afwerking.
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

### Verven (bibliotheek en nieuwe verf)
Het paneel **Verven** (onder de preview) bevat de bibliotheek en het formulier voor een nieuwe verf. Een verf uit de
echte wereld krijg je er ook met een gratis ChatGPT in:
1. Klik op **Nieuwe verf** en vul merk, product en kleur in (kleurnaam of RAL-code).
2. Klik op **Vraag voor ChatGPT kopiëren** en plak de vraag in ChatGPT. Lukt het klembord niet, dan verschijnt de vraag
   in een tekstvak om zelf te kopiëren.
3. Plak het antwoord van ChatGPT in het veld **Antwoord van ChatGPT** (het wordt meteen ingelezen; of klik op
   "Antwoord inlezen"). Het formulier vult zich. Klopt er iets niet, dan staat de fout bovenaan en is het veld rood.
4. Controleer de velden en de **vertaling** rechts: soort verf, ruwheid en kleur, met per instelling waar ze vandaan
   komt, en gele waarschuwingen voor wat de app niet nabootst (bijvoorbeeld parelmoer, glitter, fluo). Je kan alle
   velden ook met de hand invullen; de vertaling volgt live. Klik op **Bewaar in bibliotheek**.

Een bewaarde verf kies je bij zijkant, onderkant of plaat: kies als type **uit bibliotheek...** (bij de plaat staat de
keuze "Uit bibliotheek..." er al) en kies de verf. De instellingen worden overgenomen en blijven daarna aanpasbaar.
Klik in de bibliotheek op een verf voor de details en de bron-URL, of op Bewerk of Verwijder.

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

### Herkomst (klik op de render)
Zet **met herkomst** aan voor je op **Render HQ** drukt (de render duurt ongeveer twee keer zo lang). Klik daarna op de
afgewerkte render voor een punt, of sleep voor een rechthoek; de gekozen plek staat als kruisje of kader op het beeld.
Het paneel **Herkomst** toont een gestapelde balk met per bron de kleur van het licht dat via die bron kwam
(zijkant, onderkant, zijkant + onderkant, inhoud, vloer, glans/omgeving, overig), het percentage, de kleur van de
bijdrage en daaronder de kerngetallen: gemiddeld aantal interne reflecties, aandeel met totale terugkaatsing (TIR) en
de weglengte in de epoxy. Klik je in de A/B-vergelijking op een van de beelden, dan staat de herkomst van A en B
naast elkaar (alleen van renders die met herkomst gemaakt zijn). Er wordt niets opnieuw gerenderd.

### Reeks (wat-als)
Het paneel **Reeks** laat je een parameter variëren en het effect op een plek meten. Kies de parameter, de waarden
(een bereik met een stap voor getallen, vinkjes voor afwerkingen en keuzes, kleurkiezers voor kleuren) en klik eerst
de plek aan op de HQ-render of de vergelijking. **Start reeks** rendert elke waarde (kleiner beeld, tweemaal het
aantal samples voor de ruisschatting); elke waarde verschijnt zodra die klaar is als beeld met staal, L\*, C\*, h en
ΔE ten opzichte van de eerste waarde. Een waarde waarvan het verschil binnen de ruis valt, is grijs. Daaronder staan de
grafieken van L\* en C\* en van de herkomstaandelen tegenover de waarde. Een beeld aanklikken laadt die config in de
preview en het paneel.

## Screenshot maken
`uv run python scripts/maak_ui_screenshot.py [--url ...]` start (zo nodig) een server, drijft Chrome headless aan met
Playwright en schrijft de bewijsbeelden naar `docs/evidence/img/T10-*.png`. Playwright staat als dev-afhankelijkheid
in het uv-project en gebruikt `/usr/bin/google-chrome`; er wordt geen browser gedownload.
