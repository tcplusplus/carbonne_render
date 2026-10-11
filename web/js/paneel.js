// Instellingenpaneel: bouwt de invoervelden en meldt wijzigingen via `bijWijziging(soort)`.
import { KWALITEIT, RESOLUTIES, nieuweAfwerking, nieuwItem, nieuweLaag } from "./staat.js";
import * as api from "./api.js";
import { hexNaarLineair, lineairNaarHex, tekstNaarHex, waardeNaarHex } from "./kleur.js";

export function h(tag, attrs = {}, ...kinderen) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") e.className = v;
    else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else if (k === "value" || k === "checked" || k === "disabled") e[k] = v;
    else if (v !== false && v != null) e.setAttribute(k, v === true ? "" : v);
  }
  e.append(...kinderen.flat().filter((c) => c != null && c !== false));
  return e;
}

/** Geavanceerde instellingen: standaard ingeklapt, zodat de zijbalk kort blijft. */
const geavanceerd = (...inhoud) => h("details", { class: "geavanceerd" }, h("summary", {}, "geavanceerd"), ...inhoud);

const CAMERA_NAMEN = { kamer: "kamer (zicht op de ruimte)", boven: "van boven", schuin30: "schuin 30 graden", schuin60: "schuin 60 graden",
  zittend: "zittend (oog 1,10 m)", staand: "staand (oog 1,65 m)" };

const veld = (label, ...inhoud) => h("label", { class: "veld" }, h("span", { class: "lbl" }, label), ...inhoud);

export class Paneel {
  constructor(root, { cfg, opties, presets, ral, bijWijziging, bijCameraPreset }) {
    Object.assign(this, { root, cfg, opties, presets, ral, bijWijziging, bijCameraPreset });
    this.verven = [];     // bibliotheek [{slug, naam, staal}] (T20)
    this.bibModus = {};   // sleutel -> true zodra "Uit bibliotheek..." gekozen is
    this.bouw();
  }

  zetVerven(lijst) { this.verven = lijst; this.bouw(); }

  /** Zet de instellingen van een bibliotheekverf in een afwerking (verf of plaat); daarna zijn ze nog aan te passen. */
  async kiesBibliotheek(sleutel, slug) {
    const f = this.cfg[sleutel];
    if (!slug) { if (f.type === "paint") f.bibliotheek_id = null; this.bouw(); return; }
    const p = (await api.verfLees(slug)).vertaling.paint;
    f.color = lineairNaarHex(p.color);
    f.kind = p.kind;
    f.roughness = p.roughness ?? null;
    f.candy_base = p.candy_base;
    if (f.type === "paint") f.bibliotheek_id = slug;   // een plaat kent het veld niet
    this.bouw();
    this.wijzig("materiaal");
  }

  zet(cfg, opties) {
    this.bibModus = {};
    this.cfg = cfg;
    if (opties) this.opties = opties;
    this.bouw();
  }

  wijzig(soort) { this.bijWijziging(soort); }

  num(label, get, set, { min, max, step = 1, schaal = 1, eenheid = "", slider = true, soort = "geometrie" } = {}) {
    const wrap = h("span", { class: "num" });
    const nr = h("input", { type: "number", min: min * schaal, max: max * schaal, step, value: +(get() * schaal).toFixed(4) });
    const rg = slider ? h("input", { type: "range", min: min * schaal, max: max * schaal, step, value: get() * schaal }) : null;
    const toepas = (bron) => {
      const w = parseFloat(bron.value);
      if (Number.isNaN(w)) return;
      set(w / schaal);
      if (bron === nr && rg) rg.value = w; else nr.value = w;
      this.wijzig(soort);
    };
    nr.addEventListener("input", () => toepas(nr));
    rg?.addEventListener("input", () => toepas(rg));
    wrap.append(...[rg, nr, h("span", { class: "eenheid" }, eenheid)].filter(Boolean));
    return veld(label, wrap);
  }

  sel(label, keuzes, get, set, soort = "materiaal", herbouw = false) {
    const s = h("select", { onchange: () => { set(s.value); if (herbouw) this.bouw(); this.wijzig(soort); } },
      keuzes.map(([w, t]) => h("option", { value: w, selected: String(w) === String(get()) }, t)));
    return veld(label, s);
  }

  /** Kleurveld: picker + tekst (hex of, met `ral`, een RAL-code). get/set werken met '#rrggbb' of tekst. */
  kleur(label, get, set, { ral = false, soort = "materiaal" } = {}) {
    const hex = () => waardeNaarHex(get(), this.ral);
    const picker = h("input", { type: "color", value: hex() });
    const tekst = h("input", { type: "text", class: "kleurtekst", value: typeof get() === "string" ? get() : hex(),
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

  afwerking(titel, sleutel, types, schets) {
    const f = this.cfg[sleutel];
    const bibAan = f.type === "paint" && (this.bibModus[sleutel] || !!f.bibliotheek_id);
    const keuze = this.sel("Type", [...types, ["bibliotheek", "uit bibliotheek..."]], () => (bibAan ? "bibliotheek" : f.type), (t) => {
      this.bibModus[sleutel] = t === "bibliotheek";
      this.cfg[sleutel] = nieuweAfwerking(t === "bibliotheek" ? "paint" : t, f);
    }, "materiaal", true);
    const velden = [];
    if (bibAan || f.type === "plate") {
      const huidig = f.type === "paint" ? (f.bibliotheek_id ?? "") : "";
      velden.push(this.sel("Uit bibliotheek...", [["", this.verven.length ? "(eigen instellingen)" : "(bibliotheek is leeg)"],
        ...this.verven.map((v) => [v.slug, v.naam])], () => huidig, (v) => { this.kiesBibliotheek(sleutel, v); }, "geen"));
    }
    if (f.type === "paint" || f.type === "plate") {
      velden.push(this.kleur("Kleur", () => f.color, (v) => { f.color = v; }, { ral: true }));
      velden.push(this.sel("Verftype", [["matte", "mat"], ["glossy", "glanzend"], ["metallic", "metallic"], ["candy", "candy"]],
        () => f.kind, (v) => { f.kind = v; }, "materiaal", true));
      if (f.kind === "candy") velden.push(this.sel("Ondergrond candy", [["metallic", "metallic"], ["white", "wit"]], () => f.candy_base, (v) => { f.candy_base = v; }));
      velden.push(geavanceerd(this.num("Ruwheid (alpha, 0 = standaard)", () => f.roughness ?? 0, (v) => { f.roughness = v > 0 ? v : null; },
        { min: 0, max: 1, step: 0.01, soort: "materiaal" })));
    }
    if (f.type === "clearcoat") velden.push(this.num("Ruwheid (alpha)", () => f.roughness, (v) => { f.roughness = Math.max(v, 0.01); }, { min: 0.01, max: 1, step: 0.01, soort: "materiaal" }));
    if (f.type === "plate") velden.push(this.num("Luchtspleet", () => f.gap_mm, (v) => { f.gap_mm = Math.max(v, 0.01); }, { min: 0.01, max: 5, step: 0.01, eenheid: "mm", soort: "materiaal" }));
    const s = schets(f);
    return h("details", { open: true }, h("summary", {}, titel), keuze, ...velden,
      s ? h("figure", { class: "schets" }, h("img", { src: `uitleg/${s[0]}`, alt: s[1] }), h("figcaption", {}, s[1])) : null);
  }

  lagen() {
    const c = this.cfg;
    const lijst = c.layers.map((laag, li) => h("div", { class: "laag" },
      h("div", { class: "laagkop" }, h("b", {}, `Laag ${li + 1}`),
        h("button", { class: "klein", onclick: () => { c.layers.splice(li, 1); this.bouw(); this.wijzig("geometrie"); } }, "Verwijder")),
      this.num("Hoogte in het blok", () => laag.height_m, (v) => { laag.height_m = Math.min(Math.max(v, 0.001), Math.min(0.06, c.hoogte - 0.002)); },
        { min: 0.002, max: 0.058, step: 0.5, schaal: 1000, eenheid: "mm" }),
      geavanceerd(this.num("Seed (willekeurige plaatsing)", () => laag.seed, (v) => { laag.seed = Math.round(v); }, { min: 0, max: 999, slider: false })),
      laag.items.map((it, ii) => this.item(laag, it, ii)),
      h("div", { class: "rij" },
        h("button", { class: "klein", onclick: () => { laag.items.push(nieuwItem("wood")); this.bouw(); this.wijzig("geometrie"); } }, "+ houtschijfje"),
        h("button", { class: "klein", onclick: () => { laag.items.push(nieuwItem("flower")); this.bouw(); this.wijzig("geometrie"); } }, "+ bloem"))));
    return h("details", { open: true }, h("summary", {}, "Inhoud (lagen)"), lijst,
      h("button", { onclick: () => { c.layers.push(nieuweLaag(c.hoogte * 1000 / 2)); this.bouw(); this.wijzig("geometrie"); } }, "+ laag"));
  }

  item(laag, it, ii) {
    const kleur = this.kleur(it.type === "wood" ? "Hout" : "Bloem", () => lineairNaarHex(it.color), (v) => { it.color = hexNaarLineair(v); }, { soort: "geometrie" });
    return h("div", { class: "item" },
      h("div", { class: "laagkop" }, h("span", {}, it.type === "wood" ? "Houtschijfje" : "Bloem"),
        h("button", { class: "klein", onclick: () => { laag.items.splice(ii, 1); this.bouw(); this.wijzig("geometrie"); } }, "x")),
      this.num("Aantal", () => it.count, (v) => { it.count = Math.max(1, Math.round(v)); }, { min: 1, max: 60, slider: true }),
      kleur,
      this.num("Straal (min)", () => it.radius_mm[0], (v) => { it.radius_mm = [Math.min(v, it.radius_mm[1]), it.radius_mm[1]]; }, { min: 2, max: 40, step: 0.5, eenheid: "mm" }),
      this.num("Straal (max)", () => it.radius_mm[1], (v) => { it.radius_mm = [it.radius_mm[0], Math.max(v, it.radius_mm[0])]; }, { min: 2, max: 40, step: 0.5, eenheid: "mm" }),
      it.type === "flower" ? this.num("Bloemblaadjes", () => it.petals, (v) => { it.petals = Math.round(v); }, { min: 1, max: 24 }) : null);
  }

  bouw() {
    const c = this.cfg, o = this.opties, p = this.presets;
    const afwSchets = {
      onderkant: (f) => ({ bare: ["onbehandeld.svg", "Doorsnede: onbehandeld, lichtgeleider met totale terugkaatsing"],
        paint: ["verf-in-contact.svg", "Doorsnede: verf in optisch contact, diffuse terugkaatsing"],
        clearcoat: ["matte-lak.svg", "Doorsnede: kleurloze matte lak breekt de totale terugkaatsing"],
        plate: ["plaat-luchtspleet.svg", "Doorsnede: plaat met luchtspleet"] })[f.type],
      zijkant: (f) => (f.type === "paint" ? ["zijkant-geverfd-luchtspleet.svg", "Doorsnede: geverfde zijkant met luchtspleet onderaan"] : null),
    };
    const lijst = h("datalist", { id: "ral-lijst" }, p.ral.map((r) => h("option", { value: `RAL ${r.code}` }, r.naam)));
    const camKeuzes = [["vrij", "vrij (eigen draaiing)"], ...p.camera_presets.map((n) => [n, CAMERA_NAMEN[n] ?? n])];
    const res = RESOLUTIES.map(([b, hh]) => [`${b}x${hh}`, `${b} x ${hh}`]);
    const resHuidig = `${c.render.breedte}x${c.render.hoogte}`;
    if (!res.some(([k]) => k === resHuidig)) res.push([resHuidig, `${c.render.breedte} x ${c.render.hoogte}`]);
    this.root.replaceChildren(lijst,
      h("details", { open: true }, h("summary", {}, "Tafeltje"),
        this.num("Diameter", () => c.diameter, (v) => { c.diameter = v; }, { min: 0.2, max: 0.7, step: 5, schaal: 1000, eenheid: "mm" }),
        this.num("Dikte (hoogte)", () => c.hoogte, (v) => { c.hoogte = v; }, { min: 0.02, max: 0.06, step: 1, schaal: 1000, eenheid: "mm" })),
      this.afwerking("Zijkant (rand van het blok)", "zijkant", [["bare", "onbehandeld"], ["paint", "verf"], ["clearcoat", "matte lak"]], afwSchets.zijkant),
      this.afwerking("Onderkant (onder het blok)", "onderkant", [["bare", "onbehandeld"], ["paint", "verf"], ["clearcoat", "matte lak"], ["plate", "plaat met luchtspleet"]], afwSchets.onderkant),
      this.lagen(),
      h("details", { open: true }, h("summary", {}, "Omgeving en camera"),
        this.sel("Omgeving", [["", "geen (witte constante omgeving)"], ...p.omgevingen.map((x) => [x.naam, `${x.naam} - ${x.omschrijving}`])],
          () => c.scene.omgeving ?? "", (v) => { c.scene.omgeving = v || null; }, "omgeving"),
        this.sel("Camera", camKeuzes, () => c.scene.camera_preset ?? "vrij", (v) => { c.scene.camera_preset = v === "vrij" ? null : v; if (v !== "vrij") this.bijCameraPreset(v); }, "camera"),
        geavanceerd(h("label", { class: "veld" }, h("span", { class: "lbl" }, "Extra spot boven het tafeltje"),
          h("input", { type: "checkbox", checked: !!c.scene.spot, onchange: (e) => { c.scene.spot = e.target.checked; this.wijzig("omgeving"); } })))),
      h("details", { open: true }, h("summary", {}, "Belichting en kwaliteit"),
        this.num("Belichting (EV)", () => o.ev, (v) => { o.ev = v; }, { min: -4, max: 4, step: 0.1, eenheid: "stops", soort: "ev" }),
        this.sel("Resolutie", res, () => resHuidig, (v) => { const [b, hh] = v.split("x").map(Number); c.render.breedte = b; c.render.hoogte = hh; }, "frame"),
        this.sel("Kwaliteit", Object.entries(KWALITEIT).map(([k, v]) => [k, v.naam]), () => o.kwaliteit, (v) => { o.kwaliteit = v; }, "opties")));
  }
}
