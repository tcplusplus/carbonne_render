# Kalibratie met een gsm-foto

Doel: nagaan hoe goed de render klopt met een echt tafeltje, en de verfkleur bijstellen op basis van een meting.
Het kost niets: een gsm, een wit A4 en een verfstaal.

## Fotoprotocol
1. **Licht**: indirect daglicht, bij een raam maar niet in de zon; geen lamp aan, geen gekleurde muur vlak naast het
   tafeltje. Zelfde licht voor alle foto's van een sessie.
2. **Opstelling**: tafeltje op een vlakke, neutrale ondergrond (vloer of tafel). Een **wit A4 (kopieerpapier) plat
   op dezelfde ondergrond**, direct naast het tafeltje, niet in de schaduw ervan.
3. **Hoek**: kies een camerapreset (`schuin30` = 30 graden boven het blad, afstand 0,9 m; `boven` = recht van boven)
   en fotografeer zo. Het hoeft niet exact; de gebieden worden apart aangewezen.
4. **Verfstaal**: het blad of staal met **dezelfde verf** (dezelfde lagen en kleur als de zijkant) plat naast het
   papier, in dezelfde foto of een tweede foto direct erna. Geen flits, geen reflectie van het raam in het staal.
5. **Camera**: vergrendel belichting en witbalans (lang tikken), geen HDR, geen "nachtmodus", geen filters. Gebruik
   waar mogelijk de **pro-modus** of **RAW/DNG**; exporteer RAW naar JPEG/PNG met een neutrale sRGB-curve (geen
   automatische verbetering). Het papier mag niet overbelicht zijn (geen kanaal op 255) en niet bijna zwart.
6. Bestandsformaat: JPEG of PNG, 8 bit. (DNG/HEIC worden niet gelezen; zet ze eerst om.)

## Hulpmiddel: `carbonne-kalibreer`
1. **Gebieden aanwijzen**: `uv run carbonne-kalibreer raster foto.jpg -o raster.png` tekent een coordinatenraster over
   de foto. Lees er de pixelrechthoeken `x0,y0,x1,y1` af voor het papier, het staal en de gebieden (zijkant, blad).
   Neem rechthoeken ruim binnen het vlak (geen randen, geen glans, geen schaduw).
2. **gebieden.json** (alle gebieden in pixels van het eigen beeld, dus foto en render apart):
   ```json
   {"papier_albedo": 0.85, "papier_foto": [255,195,310,232], "papier_render": [255,195,310,232],
    "staal": [{"verf": "zijkant", "foto": [8,8,48,40]}],
    "gebieden": [{"naam": "zijkant", "foto": [110,168,210,182], "render": [110,168,210,182], "verf": "zijkant"}]}
   ```
   `papier_render` is een stukje vloer in de render naast het tafeltje (de vloer krijgt automatisch het
   papieralbedo, zodat foto en render hetzelfde witreferentievlak hebben).
3. **Verfkleur meten**: `uv run carbonne-kalibreer meet foto.jpg gebieden.json` geeft per verf de gemeten hex en de
   lineaire RGB. De foto wordt per kanaal zo geschaald dat het papier albedo 0,85 krijgt (witbalans en belichting in
   een stap, in lineair licht); het staal heeft dan direct zijn albedo. Die kleur overschrijft de RAL-benadering.
4. **Vergelijken**: `uv run carbonne-kalibreer vergelijk config.json foto.jpg gebieden.json -o out/kalibratie`
   zet de gemeten kleur in de config, rendert, normaliseert foto en render op hun papier en toont per gebied
   dE2000, dL (lichter/donkerder), dC (verzadigder) en dh (tint). Uitvoer: `vergelijking.png`, `config-gemeten.json`
   en `config-bijgesteld.json` (verfkleur per kanaal geschaald met foto/render; render opnieuw en herhaal tot het
   verschil klein is).
5. De `config-*.json` kun je in de app laden; de kleur van de verf staat dan op de gemeten waarde.

## Hoe lees je dE2000?
Onder ongeveer 1 is een verschil niet te zien, 2 tot 3 zie je naast elkaar, boven 5 is het duidelijk een andere
kleur. Een render van 256 spp heeft zelf al ruis van ongeveer 0,1 tot 0,3 dE.

## Beperkingen (wees er eerlijk over)
- Een gsm doet **tonemapping** (S-curve, lokaal contrast, HDR, kleurverbetering). De normalisatie op het papier
  herstelt alleen een lineaire afwijking (lichtkleur en belichting), geen niet-lineaire curve. In de synthetische
  test met een zachte S-curve blijft er ongeveer 1 dE over (`docs/evidence/T12.md`); echte gsm's kunnen meer doen.
  Pro-modus/RAW verkleint dit.
- Het papier is niet perfect wit (albedo 0,80 tot 0,90, vaak met optische witmakers die blauw reflecteren). Geef
  `papier_albedo` op als je dat weet; een fout van 5 % daarin verschuift alle gemeten kleuren 5 % in helderheid.
- Het staal moet in hetzelfde licht liggen als het papier en vlak zijn. Een glanzend staal toont reflecties; gebruik
  daarvoor het diffuse deel (kijk haaks erop, niet met het raam in beeld).
- De gemeten kleur is een RGB-albedo; de render maakt daar in spectrale modus een gladde spectrum van. Een echte
  verf kan onder ander licht afwijken (metamerie); dat meet dit hulpmiddel niet.
- Het scherm waarop je de foto bekijkt speelt geen rol: alle berekeningen gaan op de pixelwaarden.
