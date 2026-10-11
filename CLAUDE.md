# carbonne_render

Een persoonlijk hulpmiddel dat fysisch accuraat voorspelt hoe een rond, kleurloos epoxy bijzettafeltje eruitziet,
afhankelijk van de verf op zijkant en onderkant, de inhoud, de dikte en de omgeving. Python + uv, Mitsuba 3
(spectraal), FastAPI-backend en een three.js-preview in de browser.

- Plan, spec en fysica: [`docs/plan.md`](docs/plan.md). Taken: [`docs/tasks/`](docs/tasks/), met de stand via
  `python3 tools/wachtrij.py`.
- Werkwijze: `/werk-wachtrij-af` (orkestrator), `/werk-aan-taak` (taak-agent), `/plan-bij` (plan wijzigen).
- Omgeving, Mitsuba-variant en rendertijden: `docs/queue/omgeving.md` (zodra T01 klaar is).
- Documentatie en commits in het Nederlands.
- Fysica gaat voor mooi: effecten moeten uit het model volgen en meetbaar aangetoond worden (plan §4).
