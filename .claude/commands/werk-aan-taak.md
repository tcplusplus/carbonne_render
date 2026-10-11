---
description: "Bouw één taak uit docs/tasks/ als taak-agent in een eigen worktree: gericht lezen, testen, de fysica aantonen met beelden en getallen, overdracht bijhouden."
argument-hint: "Taaknummer, worktreepad en branch, bv. T03 /home/tomc/git/carbonne_render-T03 task/T03"
---

# Werk aan één taak

Opdracht: **$ARGUMENTS**

Je bouwt één taak in **jouw worktree** op **jouw branch**. Je kunt de gebruiker niets rechtstreeks vragen; dat
doet de orkestrator via jouw vraagbestanden (zie onder).

## Begin goedkoop

Je begint koud en betaalt voor elk document dat je leest. Lees in deze volgorde en stop zodra je genoeg weet:

1. Het intakepakket uit je opdracht.
2. Je dossier `docs/tasks/TNN.md`, helemaal. Van de dossiers waarvan je afhangt: alleen de kop.
3. `docs/plan.md` §2 (fysica) en §3 (architectuur). Lees de rest alleen als je het nodig hebt.
4. `docs/queue/omgeving.md`, als die bestaat: de Mitsuba-variant, de commando's en de rendertijden.
5. De code die je raakt. Zoek gericht met grep; lees een bestand één keer helemaal in plaats van in stukjes.

Bestaat er al een `docs/queue/agents/TNN.json` met `next`, dan ben je een hervatting: begin daar.

## Bouwen

- Werk alleen onder je worktree. Raak `/home/tomc/git/carbonne_render` niet aan, behalve `.locks/`.
- Eén keer `uv sync` in de worktree. Draai alles via `uv run ...`.
- Volg de stijl die er al staat. Gebruik type hints en kleine modules. De publieke functies staan in het dossier;
  verzin geen andere namen voor wat daar al benoemd is.
- **Fysica gaat voor mooi.** Bootst iets een effect na in plaats van het uit de fysica te laten volgen, dan is dat
  fout. Weet je niet hoe Mitsuba iets doet, zoek het dan op in de documentatie of de bron (`uv run python -c
  "import mitsuba; print(mitsuba.__file__)"`), of schrijf een minitest. Gok niet.
- **Werk in grote stappen**: onafhankelijke acties in één beurt, shellcommando's combineren, nieuwe bestanden in één
  Write. Elke stap stuurt je hele context opnieuw mee.
- **Testen**: tussendoor alleen de tests die je raakt (`uv run pytest tests/test_x.py -q`); de volledige suite één
  keer bij de afronding (`uv run pytest -q 2>&1 | tail -20`). Maak een test nooit groen door hem af te zwakken.
- **Renders**: houd testrenders klein (≤ 256 px, weinig spp). Neem voor een render die langer duurt dan ongeveer
  een minuut de GPU-lock: `mkdir /home/tomc/git/carbonne_render/.locks/gpu` (lukt dat niet, doe dan ander werk en
  probeer later opnieuw), en na afloop altijd `rmdir`. Lange runs start je met `timeout`.
- **Bekijk je eigen beelden** met het Read-gereedschap voordat je een conclusie trekt. Wat je niet zelf gezien
  hebt, noem je niet goed.
- Wacht nooit met `sleep` op een achtergrondproces; gebruik `Monitor` met een tijdsgrens, of doe intussen ander werk.

## Commits

Commit klein en vaak, minstens elk kwartier en vóór de volledige suite, ook als niet alles groen is (zeg dat dan
in de boodschap). Eindig elke boodschap met de attributieregel uit je opdracht. Push niet, merge niet, raak `main`
niet aan. Rond af met een schone worktree (`git status --porcelain` leeg). Grote binaire bestanden (HDRI's, EXR's,
caches) komen niet in git; controleer `.gitignore`.

## Vragen en blokkades

Moet de gebruiker iets beslissen, wijkt je werk af van het plan of de architectuur, of wordt een actie geweigerd
(rechten, installatie): schrijf dan `docs/queue/vragen/TNN-n.md` met
- de vraag in één zin;
- waarom het nu belangrijk is;
- de opties;
- het **aanbevolen antwoord**.

Commit, werk `agents/TNN.json` bij, rapporteer en **stop**. Zoek geen omweg en verzin geen antwoord. Kun je zonder
het antwoord nog aan iets anders binnen je taak werken, doe dat dan eerst.

## Wat je oplevert

1. **De code en tests** volgens het dossier.
2. **`docs/evidence/TNN.md`**: het oordeel bovenaan (gehaald of niet, en waarom), de zichtbare stap, de beelden
   (`docs/evidence/img/TNN-*.png`, ≤ ~300 kB per beeld), de getallen van de metingen, wat **niet** getest is, en
   bekende beperkingen. Schrijf het zo dat de gebruiker het zonder fysicakennis kan lezen.
3. **`docs/queue/agents/TNN.json`**: `{"taak", "status", "nu", "gedaan", "next", "tests", "kosten"}`. Werk hem bij
   bij elke mijlpaal en minstens elk kwartier, en commit hem mee. `next` is een overdracht voor wie na een
   onderbreking verdergaat: per stap het bestand en de functie, en welke test rood is en waarom.
4. Nieuwe kennis over de omgeving (variant, tijden, valkuilen) gaat naar `docs/queue/omgeving.md`.

De **status in je dossierkop wijzig je niet**; dat doet de orkestrator bij de merge.

## Rapporteer kort

Taak, oordeel (af, of geblokkeerd op wat), wat er gebouwd is, welke tests gedraaid zijn met de uitslag, de
zichtbare stap (pad naar het beeld), en wat open blijft.
