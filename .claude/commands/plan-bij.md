---
description: "Werk het plan en de taakdossiers bij (nieuwe wensen, bevindingen, herschikking) zonder iets te bouwen; de wachtrij pikt het daarna op."
argument-hint: "Wat er moet veranderen, bv. 'voeg metalen poten toe' of 'T06 splitsen in hout en bloemen'"
---

# Werk het plan bij

Wens: **$ARGUMENTS**

Je bent de **planner**. Je wijzigt alleen `docs/plan.md` en `docs/tasks/*.md`. Je schrijft geen code en start
geen agents. `/werk-wachtrij-af` voert het plan daarna uit; schrijf dus zo dat een Sonnet-agent die koud begint
de taak zonder verdere uitleg kan bouwen.

## Werkwijze

1. Lees `docs/plan.md`, `python3 tools/wachtrij.py` (de stand) en de dossiers die de wens raakt. Kijk ook in
   `docs/evidence/` en `docs/queue/vragen/` naar bevindingen die de wens beïnvloeden.
2. Is de wens onduidelijk, of zijn er keuzes die de gebruiker moet maken: vraag het met het vragenformulier,
   één vraag tegelijk als het om echte ontwerpkeuzes gaat, met een aanbevolen optie vooraan.
3. Stel een wijziging voor in hoogstens tien regels: welke dossiers erbij komen, wijzigen, gesplitst of geschrapt
   worden, en of de volgorde verandert. Wacht op akkoord.
4. Voer uit:
   - **Nieuw dossier**: het volgende vrije nummer, met een volledige kop zoals de bestaande (`taak`, `titel`,
     `status: gepland`, `deelsysteem`, `hangt_af_van`, `model`, `afrondingscriterium`, `zichtbare_stap`,
     `laatste_meting: null`). Daarna de secties Doel, Scope, (Niet in scope), Bewijs.
   - **Een taak houdt één deelsysteem**: `kern`, `scenes`, `backend`, `frontend` of `gereedschap`. Raakt een wens
     er meer, splits hem dan met `hangt_af_van`.
   - **Elk afrondingscriterium is na te gaan** met een test, een getal of een beeld. "Werkt goed" is geen
     criterium.
   - Raakt de wens fysica: noem in de scope de meetbare controle (plan §4).
   - Een dossier met status `klaar` herschrijf je niet. Is er vervolgwerk, maak dan een nieuw dossier.
     Status `bezig`: wijzig het alleen in overleg, want er loopt een agent op.
   - Werk de tabel in `docs/plan.md` §5 bij, en §1–3 als de wens de spec of de architectuur verandert.
5. `python3 tools/wachtrij.py controle` moet `ok` geven.
6. Commit met een boodschap als `Plan: <samenvatting>`, plus de attributieregel. Push niet.
7. Meld in drie regels wat er veranderde en welke taak `wachtrij.py volgende` nu geeft.
