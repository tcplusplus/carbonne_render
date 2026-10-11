// Instellingenpaneel: bouwt de invoervelden en meldt wijzigingen via `bijWijziging(soort)`.
import { CANDY_BASIS, ENUMS, KWALITEIT, POTEN_METALEN, POTEN_VORMEN, nieuwePoten, LIMIETEN as L, RESOLUTIES, VERFSOORTEN, begrens, toegestaan, laagBereik, nieuweAfwerking, nieuwItem, nieuweLaag } from "./staat.ts";
import * as api from "./api.ts";
import type { Afwerking, Cfg, CfgKleur, Item, Laag, Kwaliteit, Opties, VerfLaag } from "./staat.ts";
import type { Presets } from "./types/api.ts";
import { hexNaarLineair, lineairNaarHex, tekstNaarHex, waardeNaarHex } from "./kleur.ts";

/** Kind van een element: knoop, tekst, getal, of een (geneste) lijst daarvan; `null`/`false` vallen weg. */
export type Kind = Node | string | number | false | null | undefined | readonly Kind[];
/** Attributen: `class`, `onclick`-achtige handlers, de properties value/checked/disabled, en gewone attributen. */
// eslint-vrij: de waarden zijn per attribuut verschillend (tekst, getal, boolean, handler)
export type Attrs = Record<string, any>;

export function h<K extends keyof HTMLElementTagNameMap>(tag: K, attrs: Attrs = {}, ...kinderen: Kind[]): HTMLElementTagNameMap[K] {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") e.className = v;
    else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else if (k === "value" || k === "checked" || k === "disabled") (e as any)[k] = v;
    else if (v !== false && v != null) e.setAttribute(k, v === true ? "" : v);
  }
  e.append(...(kinderen as unknown as unknown[]).flat(Infinity).filter((c) => c != null && c !== false) as (Node | string)[]);
  return e;
}

/** Geavanceerde instellingen: standaard ingeklapt, zodat de zijbalk kort blijft. */
const geavanceerd = (...inhoud: Kind[]) => h("details", { class: "geavanceerd" }, h("summary", {}, "geavanceerd"), ...inhoud);

const CAMERA_NAMEN: Record<string, string> = { kamer: "kamer (zicht op de ruimte)", boven: "van boven", schuin30: "schuin 30 graden", schuin60: "schuin 60 graden",
  zittend: "zittend (oog 1,10 m)", staand: "staand (oog 1,65 m)" };

const veld = (label: string, ...inhoud: Kind[]) => h("label", { class: "veld" }, h("span", { class: "lbl" }, label), ...inhoud);

export type Wijziging = "frame" | "ev" | "geometrie" | "materiaal" | "omgeving" | "camera" | "opties" | "geen";
export type Sleutel = "zijkant" | "onderkant";
type Keuzes = readonly (readonly [string, string])[];
export interface NumOpties { min: number; max: number; step?: number; schaal?: number; eenheid?: string; slider?: boolean; soort?: Wijziging }
export interface PaneelInstelling {
  cfg: Cfg; opties: Opties; presets: Presets; ral: Record<string, string>;
  bijWijziging: (soort: Wijziging) => void; bijCameraPreset: (naam: string) => void;
}

export class Paneel {
  root: HTMLElement;
  cfg: Cfg;
  opties: Opties;
  presets: Presets;
  ral: Record<string, string>;
  bijWijziging: (soort: Wijziging) => void;
  bijCameraPreset: (naam: string) => void;
  verven: { slug: string; naam: string }[] = [];     // bibliotheek (T20)
  bibModus: Record<string, boolean> = {};            // sleutel -> true zodra "Uit bibliotheek..." gekozen is

  constructor(root: HTMLElement, { cfg, opties, presets, ral, bijWijziging, bijCameraPreset }: PaneelInstelling) {
    this.root = root;
    this.cfg = cfg;
    this.opties = opties;
    this.presets = presets;
    this.ral = ral;
    this.bijWijziging = bijWijziging;
    this.bijCameraPreset = bijCameraPreset;
    this.bouw();
  }

  zetVerven(lijst: { slug: string; naam: string }[]) { this.verven = lijst; this.bouw(); }

  /** Zet de instellingen van een bibliotheekverf in een afwerking (verf of plaat); daarna zijn ze nog aan te passen. */
  async kiesBibliotheek(sleutel: Sleutel, slug: string) {
    const f = this.cfg[sleutel];
    if (!slug) { if (f.type === "paint") f.bibliotheek_id = null; this.bouw(); return; }
    const p = (await api.verfLees(slug)).vertaling.paint;
    if (f.type !== "paint" && f.type !== "plate") return; // alleen verf en plaat hebben deze velden
    f.color = lineairNaarHex(p.color);
    f.kind = p.kind;
    f.roughness = p.roughness ?? null;
    f.candy_base = p.candy_base;
    if (f.type === "paint") f.bibliotheek_id = slug;   // een plaat kent het veld niet
    this.bouw();
    this.wijzig("materiaal");
  }

  zet(cfg: Cfg, opties?: Opties) {
    this.bibModus = {};
    this.cfg = cfg;
    if (opties) this.opties = opties;
    this.bouw();
  }

  wijzig(soort: Wijziging) { this.bijWijziging(soort); }

  /** Getalveld (slider + invoer). De waarde blijft binnen [min, max]: de backend wijst alles daarbuiten af (422). */
  num(label: string, get: () => number, set: (v: number) => void, { min, max, step = 1, schaal = 1, eenheid = "", slider = true, soort = "geometrie" }: NumOpties) {
    const wrap = h("span", { class: "num" });
    const nr = h("input", { type: "number", min: min * schaal, max: max * schaal, step, value: +(get() * schaal).toFixed(4) });
    const rg = slider ? h("input", { type: "range", min: min * schaal, max: max * schaal, step, value: get() * schaal }) : null;
    const toepas = (bron: HTMLInputElement) => {
      const ruw = parseFloat(bron.value);
      if (Number.isNaN(ruw)) return;
      const w = Math.min(Math.max(ruw, min * schaal), max * schaal);
      nr.classList.toggle("ongeldig", w !== ruw);
      set(w / schaal);
      if (rg) rg.value = String(w);
      if (bron === rg) nr.value = String(w);
      this.wijzig(soort);
    };
    nr.addEventListener("input", () => toepas(nr));
    nr.addEventListener("change", () => { nr.value = String(+Math.min(Math.max(parseFloat(nr.value) || 0, min * schaal), max * schaal).toFixed(4)); nr.classList.remove("ongeldig"); });
    rg?.addEventListener("input", () => toepas(rg));
    wrap.append(...[rg, nr, h("span", { class: "eenheid" }, eenheid)].filter((x): x is HTMLElement => !!x));
    return veld(label, wrap);
  }

  sel(label: string, keuzes: Keuzes, get: () => string, set: (v: string) => void, soort: Wijziging = "materiaal", herbouw = false) {
    const s = h("select", { onchange: () => { set(s.value); if (herbouw) this.bouw(); this.wijzig(soort); } },
      keuzes.map(([w, t]) => h("option", { value: w, selected: String(w) === String(get()) }, t)));
    return veld(label, s);
  }

  /** Kleurveld: picker + tekst (hex of, met `ral`, een RAL-code). get/set werken met '#rrggbb' of tekst. */
  kleur(label: string, get: () => CfgKleur, set: (v: string) => void, { ral = false, soort = "materiaal" }: { ral?: boolean; soort?: Wijziging } = {}) {
    const hex = () => waardeNaarHex(get(), this.ral);
    const picker = h("input", { type: "color", value: hex() });
    const tekst = h("input", { type: "text", class: "kleurtekst", value: typeof get() === "string" ? (get() as string) : hex(),
      list: ral ? "ral-lijst" : null, spellcheck: "false", placeholder: ral ? "#rrggbb of RAL 9005" : "#rrggbb" });
    picker.addEventListener("input", () => { tekst.value = picker.value; tekst.classList.remove("ongeldig"); set(picker.value); this.wijzig(soort); });
    tekst.addEventListener("input", () => {
      const ok = tekstNaarHex(tekst.value, ral ? this.ral : {});
      tekst.classList.toggle("ongeldig", !ok);
      if (!ok) return;
      picker.value = ok;
      set(/^#?[0-9a-f]{3,6}$/i.test(tekst.value.trim()) ? ok : tekst.value.trim().replace(/^(\d{4})$/, "RAL $1"));
      this.wijzig(soort);
    });
    return veld(label, h("span", { class: "kleurveld" }, picker, tekst));
  }

  afwerking(titel: string, sleutel: Sleutel, types: Keuzes, schets: (f: Afwerking) => readonly [string, string] | null | undefined) {
    const f = this.cfg[sleutel];
    const bibAan = f.type === "paint" && (this.bibModus[sleutel] || !!f.bibliotheek_id);
    const keuze = this.sel("Type", [...types, ["bibliotheek", "uit bibliotheek..."] as const], () => (bibAan ? "bibliotheek" : f.type), (t) => {
      this.bibModus[sleutel] = t === "bibliotheek";
      this.cfg[sleutel] = nieuweAfwerking(t === "bibliotheek" ? "paint" : t, f) as Cfg["zijkant"]; // de zijkant kent geen plaat (de lijst biedt hem niet aan)
    }, "materiaal", true);
    const velden: Kind[] = [];
    if (bibAan || f.type === "plate") {
      const huidig = f.type === "paint" ? (f.bibliotheek_id ?? "") : "";
      velden.push(this.sel("Uit bibliotheek...", [["", this.verven.length ? "(eigen instellingen)" : "(bibliotheek is leeg)"],
        ...this.verven.map((v) => [v.slug, v.naam] as const)], () => huidig, (v) => { this.kiesBibliotheek(sleutel, v); }, "geen"));
    }
    if (f.type === "paint" || f.type === "plate") {
      velden.push(this.kleur("Kleur", () => f.color, (v) => { f.color = v; }, { ral: true }));
      velden.push(this.sel("Verftype", toegestaan(VERFSOORTEN, ENUMS.verfsoort),
        () => f.kind, (v) => { f.kind = v as VerfLaag["kind"]; }, "materiaal", true));
      if (f.kind === "candy") velden.push(this.sel("Ondergrond candy", toegestaan(CANDY_BASIS, ENUMS.candyBasis), () => f.candy_base, (v) => { f.candy_base = v as VerfLaag["candy_base"]; }));
      velden.push(geavanceerd(this.num("Ruwheid (alpha, 0 = standaard)", () => f.roughness ?? 0, (v) => { f.roughness = v > 0 ? v : null; },
        { min: L.ruwheid.min, max: L.ruwheid.max, step: 0.01, soort: "materiaal" })));
    }
    if (f.type === "paintstack") velden.push(...this.verflagen(f));
    if (f.type === "clearcoat") velden.push(this.num("Ruwheid (alpha)", () => f.roughness, (v) => { f.roughness = Math.max(v, L.lakRuwheid.min); }, { min: L.lakRuwheid.min, max: L.lakRuwheid.max, step: 0.01, soort: "materiaal" }));
    if (f.type === "plate") velden.push(this.num("Luchtspleet", () => f.gap_mm, (v) => { f.gap_mm = Math.max(v, L.spleet.min); }, { min: L.spleet.min, max: L.spleet.max, step: 0.01, eenheid: "mm", soort: "materiaal" }));
    const s = schets(f);
    return h("details", { open: true }, h("summary", {}, titel), keuze, ...velden,
      s ? h("figure", { class: "schets" }, h("img", { src: `uitleg/${s[0]}`, alt: s[1] }), h("figcaption", {}, s[1])) : null);
  }

  /** T24: lijst verflagen, van binnen (epoxy) naar buiten (lucht): kleur, type, dekking, + laag, verwijder, volgorde. */
  verflagen(f: Extract<Afwerking, { type: "paintstack" }>) {
    const nieuw = (): VerfLaag => ({ type: "paint", color: "#ffffff", kind: "matte", roughness: null, candy_base: "metallic", dekking: 1, bibliotheek_id: null });
    const ververs = () => { this.bouw(); this.wijzig("materiaal"); };
    const rijen = f.lagen.map((l, i) => h("div", { class: "laag" },
      h("div", { class: "laagkop" }, h("b", {}, i === 0 ? "Laag 1 (tegen de epoxy)" : i === f.lagen.length - 1 ? `Laag ${i + 1} (buiten)` : `Laag ${i + 1}`),
        h("span", {},
          h("button", { class: "klein", disabled: i === 0, onclick: () => { [f.lagen[i - 1], f.lagen[i]] = [f.lagen[i], f.lagen[i - 1]]; ververs(); } }, "naar binnen"),
          h("button", { class: "klein", disabled: i === f.lagen.length - 1, onclick: () => { [f.lagen[i + 1], f.lagen[i]] = [f.lagen[i], f.lagen[i + 1]]; ververs(); } }, "naar buiten"),
          h("button", { class: "klein", disabled: f.lagen.length < 2, onclick: () => { f.lagen.splice(i, 1); ververs(); } }, "Verwijder"))),
      this.kleur("Kleur", () => l.color, (v) => { l.color = v; }, { ral: true }),
      this.sel("Verftype", toegestaan(VERFSOORTEN, ENUMS.verfsoort), () => l.kind, (v) => { l.kind = v as VerfLaag["kind"]; if (v === "metallic" || v === "candy") l.dekking = 1; }, "materiaal", true),
      l.kind === "matte" || l.kind === "glossy"
        ? this.num("Dekking (1 = ondoorzichtig)", () => l.dekking, (v) => { l.dekking = Math.min(Math.max(v, 0), 1); }, { min: L.dekking.min, max: L.dekking.max, step: 0.05, soort: "materiaal" })
        : null));
    return [...rijen, h("button", { class: "klein", disabled: f.lagen.length >= L.verflagen.max, onclick: () => { f.lagen.push(nieuw()); ververs(); } }, "+ laag")];
  }

  lagen() {
    const c = this.cfg;
    const lijst = c.layers.map((laag, li) => h("div", { class: "laag" },
      h("div", { class: "laagkop" }, h("b", {}, `Laag ${li + 1}`),
        h("button", { class: "klein", onclick: () => { c.layers.splice(li, 1); this.bouw(); this.wijzig("geometrie"); } }, "Verwijder")),
      this.num("Hoogte in het blok", () => laag.height_m, (v) => { laag.height_m = Math.min(Math.max(v, laagBereik(c.hoogte).min), laagBereik(c.hoogte).max); },
        { min: laagBereik(c.hoogte).min, max: laagBereik(c.hoogte).max, step: 0.5, schaal: 1000, eenheid: "mm" }),
      geavanceerd(this.num("Seed (willekeurige plaatsing)", () => laag.seed, (v) => { laag.seed = Math.round(v); }, { min: L.seed.min, max: L.seed.max, slider: false })),
      laag.items.map((it, ii) => this.item(laag, it, ii)),
      h("div", { class: "rij" },
        h("button", { class: "klein", onclick: () => { laag.items.push(nieuwItem("wood")); this.bouw(); this.wijzig("geometrie"); } }, "+ houtschijfje"),
        h("button", { class: "klein", onclick: () => { laag.items.push(nieuwItem("flower")); this.bouw(); this.wijzig("geometrie"); } }, "+ bloem"))));
    return h("details", { open: true }, h("summary", {}, "Inhoud (lagen)"), lijst,
      h("button", { onclick: () => { c.layers.push(nieuweLaag(c.hoogte)); this.bouw(); this.wijzig("geometrie"); } }, "+ laag"));
  }

  item(laag: Laag, it: Item, ii: number) {
    const kleur = this.kleur(it.type === "wood" ? "Hout" : "Bloem", () => (typeof it.color === "string" ? it.color : lineairNaarHex(it.color)), (v) => { it.color = hexNaarLineair(v); }, { soort: "geometrie" });
    return h("div", { class: "item" },
      h("div", { class: "laagkop" }, h("span", {}, it.type === "wood" ? "Houtschijfje" : "Bloem"),
        h("button", { class: "klein", onclick: () => { laag.items.splice(ii, 1); this.bouw(); this.wijzig("geometrie"); } }, "x")),
      this.num("Aantal", () => it.count, (v) => { it.count = Math.max(1, Math.round(v)); }, { min: L.aantal.min, max: L.aantal.max, slider: true }),
      kleur,
      this.num("Straal (min)", () => it.radius_mm[0], (v) => { it.radius_mm = [Math.min(v, it.radius_mm[1]), it.radius_mm[1]]; }, { min: L.straal.min, max: L.straal.max, step: 0.5, eenheid: "mm" }),
      this.num("Straal (max)", () => it.radius_mm[1], (v) => { it.radius_mm = [it.radius_mm[0], Math.max(v, it.radius_mm[0])]; }, { min: L.straal.min, max: L.straal.max, step: 0.5, eenheid: "mm" }),
      it.type === "flower" ? this.num("Bloemblaadjes", () => it.petals, (v) => { it.petals = Math.round(v); }, { min: L.bloemblaadjes.min, max: L.bloemblaadjes.max }) : null);
  }

  /** T26: metalen poten onder het blok; "geen" = geen poten (de vloer ligt dan op 45 cm onder het blad). */
  poten() {
    const c = this.cfg, p = c.poten;
    const aantal = this.sel("Aantal poten", [["0", "geen poten"], ...[3, 4, 5, 6].map((n) => [String(n), `${n} poten`] as const)],
      () => String(p?.aantal ?? 0), (v) => { c.poten = +v === 0 ? null : { ...(c.poten ?? nieuwePoten()), aantal: +v }; }, "geometrie", true);
    const g = "geometrie" as const;
    return h("details", { open: true }, h("summary", {}, "Poten"), aantal, ...(p ? [
      this.sel("Vorm", POTEN_VORMEN, () => p.vorm, (v) => { p.vorm = v as typeof p.vorm; }, g),
      this.sel("Metaal", POTEN_METALEN, () => p.metaal, (v) => { p.metaal = v as typeof p.metaal; }, "materiaal"),
      this.num(p.vorm === "rond" ? "Diameter poot" : "Zijde poot", () => p.afmeting_mm, (v) => { p.afmeting_mm = v; }, { min: L.potenAfmeting.min, max: L.potenAfmeting.max, step: 1, eenheid: "mm", soort: g }),
      this.num("Afstand tot de rand", () => p.rand_mm, (v) => { p.rand_mm = v; }, { min: L.potenRand.min, max: L.potenRand.max, step: 1, eenheid: "mm", soort: g }),
      this.num("Lengte poot", () => p.hoogte_m, (v) => { p.hoogte_m = v; }, { min: L.potenHoogte.min, max: L.potenHoogte.max, step: 10, schaal: 1000, eenheid: "mm", soort: g })] : []));
  }

  bouw() {
    const c = this.cfg, o = this.opties, p = this.presets;
    const afwSchets: Record<Sleutel, (f: Afwerking) => readonly [string, string] | null | undefined> = {
      onderkant: (f) => ({ bare: ["onbehandeld.svg", "Doorsnede: onbehandeld, lichtgeleider met totale terugkaatsing"],
        paint: ["verf-in-contact.svg", "Doorsnede: verf in optisch contact, diffuse terugkaatsing"],
        clearcoat: ["matte-lak.svg", "Doorsnede: kleurloze matte lak breekt de totale terugkaatsing"],
        plate: ["plaat-luchtspleet.svg", "Doorsnede: plaat met luchtspleet"] } as Record<string, readonly [string, string]>)[f.type],
      zijkant: (f) => (f.type === "paint" ? ["zijkant-geverfd-luchtspleet.svg", "Doorsnede: geverfde zijkant met luchtspleet onderaan"] : null),
    };
    const lijst = h("datalist", { id: "ral-lijst" }, p.ral.map((r) => h("option", { value: `RAL ${r.code}` }, r.naam)));
    const camKeuzes: Keuzes = [["vrij", "vrij (eigen draaiing)"], ...p.camera_presets.map((n) => [n, CAMERA_NAMEN[n] ?? n] as const)];
    const res: [string, string][] = RESOLUTIES.map(([b, hh]) => [`${b}x${hh}`, `${b} x ${hh}`] as [string, string]);
    const resHuidig = `${c.render.breedte}x${c.render.hoogte}`;
    if (!res.some(([k]) => k === resHuidig)) res.push([resHuidig, `${c.render.breedte} x ${c.render.hoogte}`]);
    this.root.replaceChildren(lijst,
      h("details", { open: true }, h("summary", {}, "Tafeltje"),
        this.num("Diameter", () => c.diameter, (v) => { c.diameter = v; }, { min: L.diameter.min, max: L.diameter.max, step: 5, schaal: 1000, eenheid: "mm" }),
        this.num("Dikte (hoogte)", () => c.hoogte, (v) => { c.hoogte = v; if (begrens(c)) this.bouw(); }, { min: L.hoogte.min, max: L.hoogte.max, step: 1, schaal: 1000, eenheid: "mm" })),
      this.afwerking("Zijkant (rand van het blok)", "zijkant", [["bare", "onbehandeld"], ["paint", "verf"], ["paintstack", "gestapelde verf"], ["clearcoat", "matte lak"]], afwSchets.zijkant),
      this.afwerking("Onderkant (onder het blok)", "onderkant", [["bare", "onbehandeld"], ["paint", "verf"], ["paintstack", "gestapelde verf"], ["clearcoat", "matte lak"], ["plate", "plaat met luchtspleet"]], afwSchets.onderkant),
      this.lagen(),
      this.poten(),
      h("details", { open: true }, h("summary", {}, "Omgeving en camera"),
        this.sel("Omgeving", [["", "geen (witte constante omgeving)"], ...p.omgevingen.map((x) => [x.naam, `${x.naam} - ${x.omschrijving}`] as const)],
          () => c.scene.omgeving ?? "", (v) => { c.scene.omgeving = v || null; }, "omgeving"),
        this.sel("Camera", camKeuzes, () => c.scene.camera_preset ?? "vrij", (v) => { c.scene.camera_preset = v === "vrij" ? null : v; if (v !== "vrij") this.bijCameraPreset(v); }, "camera"),
        geavanceerd(h("label", { class: "veld" }, h("span", { class: "lbl" }, "Extra spot boven het tafeltje"),
          h("input", { type: "checkbox", checked: !!c.scene.spot, onchange: (e: Event) => { c.scene.spot = (e.target as HTMLInputElement).checked; this.wijzig("omgeving"); } })))),
      h("details", { open: true }, h("summary", {}, "Belichting en kwaliteit"),
        this.num("Belichting (EV)", () => o.ev, (v) => { o.ev = v; }, { min: -4, max: 4, step: 0.1, eenheid: "stops", soort: "ev" }),
        this.sel("Resolutie", res, () => resHuidig, (v) => { const [b, hh] = v.split("x").map(Number) as [number, number]; c.render.breedte = b; c.render.hoogte = hh; }, "frame"),
        this.sel("Kwaliteit", Object.entries(KWALITEIT).map(([k, v]) => [k, v.naam] as const), () => o.kwaliteit, (v) => { o.kwaliteit = v as Kwaliteit; }, "opties")));
  }
}
