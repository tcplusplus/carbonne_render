# Carbonne render — plan

Een persoonlijk hulpmiddel dat **voorspelt** hoe een rond epoxy bijzettafeltje van
[Carbonne](https://shop.carbonne.be/) eruit zal zien, fysisch zo accuraat mogelijk. De gebruiker kiest de
afwerking van zijkant en onderkant, de inhoud, de dikte, de omgeving en de kijkhoek. Hij stelt de belichting
in met een realtime preview en vraagt daarna een spectrale render in hoge kwaliteit aan.

Dit document is de bron voor de taakdossiers in [`tasks/`](tasks/). Wijzig je het plan, werk dan ook de
geraakte dossiers bij (zie `/plan-bij`).

## 1. Het object

| Eigenschap | Waarde |
|---|---|
| Vorm | Massieve cilinder in epoxy, altijd rond |
| Diameter | 35 cm of 50 cm |
| Hoogte (dikte) | 2 tot 6 cm, in te stellen per cm (of fijner) |
| Epoxy | **Kleurloos**, heel helder. Geen pigment, geen mica. |
| Bovenvlak | Gegoten, niet gepolijst, maar optisch glad en helder |
| Zijkant | Onbehandeld **of** geverfd |
| Onderkant | Onbehandeld, geverfd, **mat gespoten met kleurloze lak**, of met een losse plaat eronder |
| Verftypes | Mat, glanzend, metallic, candy (transparant gekleurd); per vlak te kiezen |
| Inhoud | Hout of gedroogde bloemen, **zwevend in gietlagen**; eenvoudige vormen volstaan |
| Poten | Metaal; **voorlopig niet** in de render |

## 2. De fysica die het hulpmiddel moet tonen

Omdat de epoxy kleurloos is, komt bijna alle kleur uit de optica: hoe licht via verf, randen en inhoud
terug naar het oog geraakt. Elke implementatiekeuze moet deze effecten correct laten ontstaan; ze worden
**niet** nagebootst met trucs.

1. **Breking en Fresnel-reflectie** aan het bovenvlak: n ≈ 1,50–1,55. Mitsuba 3.9.1 ondersteunt geen dispersie in `dielectric`, dus de scène gebruikt een vaste IOR van 1,530 bij 589 nm; dispersie (Cauchy, staat in `EpoxyMaterial`) is een bekende beperking (n ≈ 1,54 bij 400 nm tegen 1,52 bij 700 nm).
   Bij loodrechte inval wordt ongeveer 4 % teruggekaatst.
2. **Totale interne reflectie (TIR)**: van binnen naar lucht vanaf de kritische hoek, arcsin(1/n) ≈ 41–42°.
3. **Verf in optisch contact**: het bindmiddel van de verf heeft ongeveer dezelfde index als de epoxy, dus er is
   bijna geen grensvlak en geen TIR. Licht valt rechtstreeks op de pigmentlaag (diffuus, met het albedo van de
   verf). Van buiten gezien is diezelfde verf een gewoon geverfd oppervlak in lucht.
4. **Plaat eronder met luchtspleet**: het grensvlak epoxy-lucht blijft bestaan. Schuin licht wordt dus volledig
   teruggekaatst en het blok werkt als **lichtgeleider**. Daardoor verspreidt de kleur van de zijkant zich over
   het hele vlak. Dat is het verschil dat in de praktijk al is waargenomen ("zwart geverfd ≠ zwarte plaat eronder").
5. **Kleurloze matte lak**: een ruw diëlektrisch grensvlak (epoxy → lak → lucht). Het verstrooit het licht en
   breekt de TIR gedeeltelijk, wat een tussenvorm van 3 en 4 geeft.
6. **Lichte eigen absorptie of vergeling** van de epoxy volgens Beer-Lambert: standaard bijna nul, maar
   instelbaar. Bij lange weglengtes, zoals langs de diameter, kan ze zichtbaar worden.
7. **Inhoud** die het licht absorbeert, verstrooit en schaduw werpt binnen het blok.

**Geen ruisonderdrukking (denoiser) op een render die voor voorspelling dient.** Een HQ-render convergeert
echt; de preview mag benaderend zijn.

## 3. Architectuur

```text
           browser (localhost)
   ┌──────────────────────────────────────┐
   │ three.js realtime preview (benadering)│  camera, belichting, vorm instellen
   │ instellingenpaneel                    │
   │ HQ-render paneel (progressief)  A|B   │
   └───────────────▲──────────────────────┘
                   │ HTTP + WebSocket (JSON-config, PNG-frames)
   ┌───────────────┴──────────────────────┐
   │ FastAPI-backend (Python, uv)          │
   │  TableConfig (pydantic) ──► scene dict│
   │  render-wachtrij, cache op config-hash│
   └───────────────▲──────────────────────┘
                   │
   ┌───────────────┴──────────────────────┐
   │ carbonne.core: Mitsuba 3, spectraal   │
   │ (cuda_ad_spectral als het kan,        │
   │  anders llvm_ad_spectral)             │
   └───────────────────────────────────────┘
```

- **Eén configuratiemodel** (`TableConfig`) beschrijft het hele tafeltje en de scène. De Mitsuba-scène en
  de three.js-preview worden er allebei uit afgeleid; ze krijgen nooit elk een eigen waarheid.
- **Pakketindeling**: `src/carbonne/core/` (fysica en scène-opbouw), `src/carbonne/render/` (renderpijplijn),
  `src/carbonne/server/` (FastAPI), `web/` (frontend, zonder buildstap: ES-modules en three.js via importmap),
  `assets/` (gedownloade HDRI's en texturen, niet in git, ophaalbaar met een script), `tests/`.
- **Eenheden**: meter in de scène, golflengte in nm. Python ≥ 3.12; pin een versie waarvoor Mitsuba-wheels
  bestaan (de systeem-Python is 3.14).
- **Hardware**: Quadro P2000 (4 GB, Pascal), Xeon E-2176M (12 threads), 30 GB RAM, Linux.

## 4. Verificatie van de fysica

Een mooie render bewijst niets. Elke taak die fysica raakt levert minstens één **meetbare** controle:

- analytische gevallen (Fresnel-reflectie bij loodrechte inval, kritische hoek, Beer-Lambert-transmissie) vergeleken
  met wat de renderer teruggeeft, met tolerantie;
- **A/B-renders** met dezelfde ruiszaad en hetzelfde aantal samples, waarin het verschil in de verwachte richting
  gaat, gemeten als gemiddelde luminantie in een vast gebied;
- de agent **bekijkt zijn eigen renders** (het Read-gereedschap toont PNG's) voordat hij iets "klaar" noemt.

Bewijs komt in `docs/evidence/TNN.md` met kleine PNG's in `docs/evidence/img/` (hoogstens ~300 kB per beeld).

## 5. Stappen

| Taak | Titel | Hangt af van |
|---|---|---|
| [T01](tasks/T01.md) | Projectskelet, uv en Mitsuba-variant | — |
| [T02](tasks/T02.md) | Configuratiemodel en scène-opbouw van de cilinder | T01 |
| [T03](tasks/T03.md) | Randafwerkingen: verf in contact, matte lak, plaat met luchtspleet | T02 |
| [T04](tasks/T04.md) | Fysische validatie: analytische tests en het A/B-experiment | T03 |
| [T05](tasks/T05.md) | Verftypes en kleurinvoer (hex, RAL) | T03 |
| [T06](tasks/T06.md) | Inhoud in gietlagen (hout, bloemen als eenvoudige vormen) | T02 |
| [T07](tasks/T07.md) | Omgevingen: HDRI-interieurs, vloeren, camerapresets | T02 |
| [T08](tasks/T08.md) | HQ-renderpijplijn: convergentie, cache, uitvoer | T04 |
| [T09](tasks/T09.md) | Webbackend (FastAPI) | T08 |
| [T10](tasks/T10.md) | Webfrontend met realtime preview en HQ-paneel | T09, T07 |
| [T11](tasks/T11.md) | 2D-stralendoorsnede: zie waar het licht heen gaat | T03 |
| [T12](tasks/T12.md) | Kalibratie met een gsm-foto (gratis) | T10 |

Later, nog niet als dossier: metalen poten, een webinterface buiten de laptop, andere vormen.

## 6. Werkwijze

- `/werk-wachtrij-af` is de orkestrator (Sonnet). Hij start per taak een Sonnet-agent in een eigen worktree,
  merget het resultaat en gaat door tot de wachtrij leeg is.
- `/werk-aan-taak` bevat de regels voor die taak-agent.
- `/plan-bij` wijzigt het plan en de dossiers, zonder te bouwen, bijvoorbeeld vanuit een aparte sessie.
- `python3 tools/wachtrij.py` toont de stand. `python3 tools/wachtrij.py volgende` geeft de eerstvolgende
  uitvoerbare taak.
