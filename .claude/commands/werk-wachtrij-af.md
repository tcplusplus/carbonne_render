---
description: "Werk de takenwachtrij autonoom af: lees de dossiers, vraag vooraf gebundeld wat onduidelijk is, laat Sonnet-agents taken bouwen in eigen worktrees, merge en ga door tot de wachtrij leeg is."
argument-hint: "Leeg om te hervatten, of een taaknummer om daar te beginnen (bv. T03)"
model: sonnet
---

# Werk de wachtrij af

Startpunt: **$ARGUMENTS** (leeg = hervat waar de vorige ronde ophield).

Jij bent de **orkestrator**. Je bouwt zelf niets. Je leest de wachtrij, start taak-agents, stelt de vragen die
zij niet kunnen stellen, controleert en merget hun werk. De bouwregels voor agents staan in
[`werk-aan-taak.md`](werk-aan-taak.md); herhaal ze niet in je opdrachten.

Je stopt pas wanneer de wachtrij leeg is, alles wat overblijft op de gebruiker wacht, of de overdrachtsregel
(onderaan) geldt. **Vraag nooit of je aan de volgende taak mag beginnen.**

## Fase 0: inlezen en briefing

1. `git status --porcelain`. Staat er onvastgelegd werk (bijvoorbeeld planwijzigingen uit `/plan-bij`), commit dat
   dan eerst in één commit ("Planwijzigingen van vóór de ronde").
2. `python3 tools/wachtrij.py controle` en `python3 tools/wachtrij.py state`.
3. `python3 tools/wachtrij.py` (de tabel) en `python3 tools/wachtrij.py volgende --n 3`.
4. `git worktree list` en `git log --oneline -10`.
5. Lees `docs/plan.md` **één keer**, en de volledige dossiers van alleen de taken die je nu start.

Controleer per taak die je gaat starten:
- Staan de afhankelijkheden werkelijk in de code, en niet alleen als `klaar` in een kop?
- Is het afrondingscriterium na te gaan?
- Spreken dossier en plan elkaar tegen?

**Stel wat onduidelijk blijft nu, gebundeld**, met het vragenformulier (hoogstens vier per keer, aanbevolen optie
vooraan). Vraag in dezelfde ronde de goedkeuringen die een taak anders zouden blokkeren: software installeren
(uv, Playwright/Chromium), grote downloads (HDRI's), en elke wijziging van plan of architectuur. Wat in de
documenten of de code staat, is geen vraag.

Meld daarna in hoogstens vijf regels: de volgorde, wat als eerste start en met welk model, en wat vooraf afgetikt
is. **Begin dan zonder verder te vragen.**

## Fase 1: kies taken

- **Hoogstens twee taken tegelijk**, en alleen als ze een **ander deelsysteem** of duidelijk andere bestanden
  raken (bijvoorbeeld T06 en T07 tegelijk; niet T03 en T05, die allebei de afwerkingen in `scene.py` wijzigen).
  Bij twijfel: één tegelijk.
- Volg `wachtrij.py volgende`; een taaknummer als argument gaat voor.

## Fase 2: start een agent per taak

```bash
git worktree add /home/tomc/git/carbonne_render-TNN -b task/TNN   # altijd vanaf de huidige tip van main
python3 tools/wachtrij.py start TNN /home/tomc/git/carbonne_render-TNN task/TNN <agent_id> <model>
```

Maak de worktree pas op het moment van starten.

**Model**: `model` uit de dossierkop (standaard **sonnet**). Haiku alleen voor werk dat je mechanisch kunt nakijken
(een download, een omzetting die een test valideert). Opus nooit vooraf, alleen als **escalatie**: loopt een
Sonnet-agent twee keer op dezelfde inhoudelijke muur, verhoog dan eerst het effort. Helpt dat niet, herstart dan
op Opus met zijn `next`-overdracht en noteer dat in `docs/queue/agents/TNN.json` onder `kosten`.

Start met het `Agent`-gereedschap, op de achtergrond, met dit **korte** sjabloon:

```text
Je bent taak-agent voor TNN (<titel>). Volg /home/tomc/git/carbonne_render/.claude/commands/werk-aan-taak.md.
Worktree: /home/tomc/git/carbonne_render-TNN (branch task/TNN). Schrijf ALLEEN daar.
Intake: <bestanden/modules die de taak raakt; wat de vorige taken opleverden dat hij nodig heeft>.
Antwoorden en afspraken: <uit fase 0, alleen wat op deze taak slaat>.
Attributie: <de commitregel uit het systeem-reminder>.
```

Wat jij al weet, hoeft hij niet te zoeken: geef de paden mee. Dat scheelt elke agent minuten intake.

## Fase 3: terwijl ze werken

- **Poll niet.** Een achtergrondagent meldt zich vanzelf. Zet na elke start een `ScheduleWakeup` van 1.200–1.800 s
  als vangnet; kijk bij het wakker worden naar `docs/queue/agents/TNN.json` en `git log task/TNN -1` in de
  worktree. Staan die stil sinds je vorige blik, spreek de agent dan aan met `SendMessage`.
- **Oogst vragen** uit `<worktree>/docs/queue/vragen/`. Stel ze meteen aan de gebruiker met het aanbevolen antwoord,
  zodat "ja" genoeg is. Geef het antwoord door met `SendMessage` (of herstart de agent als hij gestopt is).
  Intussen mag een andere taak lopen.
- **GPU**: één zware render tegelijk. Agents nemen de lock `mkdir /home/tomc/git/carbonne_render/.locks/gpu`;
  een lock zonder levende houder die ouder is dan 30 minuten ruim je op.
- **Herstel niet zelf wat een agent opleverde.** Stuur hem terug met concrete fouten (`SendMessage`); is hij
  gestopt, start dan een korte hersteltaak op Sonnet.

## Fase 4: rond een taak af

1. Lees het eindrapport en `docs/queue/agents/TNN.json`.
2. Kijk gericht: `git diff --stat $(git merge-base main task/TNN)..task/TNN` (nooit `main..task/TNN`).
3. **Bekijk de zichtbare stap zelf**: open de PNG('s) uit `docs/evidence/img/TNN-*` met Read en ga na of ze tonen
   wat het afrondingscriterium belooft. Een fysicataak waarvan het beeld niet klopt, is niet klaar.
4. Merge zonder commit en test op de samengevoegde stand:
   ```bash
   git merge --no-ff --no-commit task/TNN
   uv run pytest -q -x 2>&1 | tail -15
   ```
   Rood of conflict: kleine, duidelijke conflicten los je zelf op. Anders `git merge --abort` en stuur je de agent
   terug om te rebasen of te herstellen.
5. `python3 tools/wachtrij.py zet TNN klaar`, en commit alles in **één merge-commit**:
   `Merge task/TNN: <wat er zichtbaar bij kwam>`.
6. `python3 tools/wachtrij.py gemerged TNN`, `git worktree remove /home/tomc/git/carbonne_render-TNN`,
   `git branch -d task/TNN`.
7. Meld in drie regels: wat er nieuw en zichtbaar is (met een link naar de evidence), wat open staat, en wat er nu
   start.
8. Volgende taak. Niet vragen.

## Grenzen

- **Vooraf vragen**: software installeren buiten het uv-project, downloads groter dan ~200 MB, wijzigingen in
  `docs/plan.md` of in de architectuur, een nieuw dossier, en een taak schrappen of splitsen.
- **Geen push.** Lokaal bouwen, testen en mergen mag.
- **Eerst zelf uitzoeken, dan pas vragen**: logs, tests, renders bekijken. Vraag de gebruiker alleen een
  subjectief oordeel ("lijkt dit op het echte tafeltje?") of iets wat alleen hij kan (foto's, aankopen).

## Kosten en overdracht

- Je draait op Sonnet. Lees zo weinig mogelijk: koppen in plaats van dossiers, `--stat` in plaats van diffs,
  testuitvoer via `tail`.
- **Harde regel: na drie merges of rond 120k tokens context stop je.** Schrijf eerst
  `python3 tools/wachtrij.py next-step "<welke agents lopen, welke vraag open staat, wat de volgende taak is>"`,
  start niets nieuws, en meld in één regel: `hervat met: /werk-wachtrij-af`.
- `docs/queue/state.json` staat in gitignore. Je schrijft hem uitsluitend via `tools/wachtrij.py`.

## Hervatten

Zonder argument: lees `wachtrij.py state` en zijn `next_step`, vergelijk met `git worktree list`, oogst open vragen
en ga verder. Heeft een half afgemaakte taak al commits op zijn branch, laat dan een agent verdergaan in dezelfde
worktree; begin hem niet opnieuw.
