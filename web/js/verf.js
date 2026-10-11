// Paneel Verven (T20): bibliotheek, formulier "nieuwe verf" met live vertaling, en de ChatGPT-brug.
import * as api from "./api.js";
import { lineairNaarHex } from "./kleur.js";
import { h } from "./paneel.js";

const GLANSTERMEN = ["mat", "zijdemat", "zijdeglans", "satijn", "glans", "hoogglans"];
const BRON_TEKST = { standaard: "standaard", model: "model" };
// Groepering van de velden uit GET /api/verven/schema.
const GROEPEN = [
  ["Identiteit", ["merk", "product", "kleurnaam"]],
  ["Kleur", ["kleurcode", "hex"]],
  ["Glans", ["glansgraad", "glans_gu_60"]],
  ["Effect", ["effect", "transparant", "ondergrond_candy"]],
  ["Bron", ["bron_url", "opmerking"]],
];
const LEEG = () => ({ merk: "", product: "", kleurnaam: "", kleurcode: "", hex: "", glansgraad: "", glans_gu_60: "",
  effect: "geen", transparant: false, ondergrond_candy: "", bron_url: "", opmerking: "" });

/** Formulierwaarden -> aanvraag voor de API: lege velden vervallen. */
export function naarAanvraag(w) {
  const o = {};
  for (const [k, v] of Object.entries(w)) {
    if (k === "transparant") { o[k] = !!v; continue; }
    if (v === "" || v == null) continue;
    o[k] = k === "glans_gu_60" ? Number(v) : v;
  }
  return o;
}

/** Fout van de API -> {melding, veld}; kent het eigen formaat van uit-tekst en de lijst van pydantic. */
export function foutInfo(e) {
  const d = e.detail;
  if (d && typeof d === "object" && !Array.isArray(d)) return { melding: d.melding ?? String(e.message), veld: d.veld ?? null };
  if (Array.isArray(d) && d.length) {
    const loc = d[0].loc ?? [];
    const veld = loc.length > 1 ? String(loc[loc.length - 1]) : null;
    return { melding: `${veld ? veld + ": " : ""}${d[0].msg}`, veld };
  }
  return { melding: typeof d === "string" ? d : e.message, veld: null };
}

export class VerfPaneel {
  constructor(root, { bijLijst, meld }) {
    Object.assign(this, { root, bijLijst, meld, lijst: [], schema: null, w: LEEG(), debounce: null, volgnr: 0, open: false, gekozen: null, velden: {} });
    this.bouw();
  }

  async ververs() {
    this.lijst = await api.verfLijst();
    this.bijLijst(this.lijst);
    this.bouwLijst();
  }

  // --- opbouw ---
  bouw() {
    this.lijstEl = h("div", { class: "verf-lijst", "data-rol": "verf-lijst" });
    this.detailEl = h("div", { class: "verf-detail", "data-rol": "verf-detail" });
    this.formEl = h("div", { class: "verf-formulier", hidden: true, "data-rol": "verf-formulier" });
    this.root.replaceChildren(
      h("div", { class: "verf-kolom" },
        h("div", { class: "rij" }, h("button", { class: "primair", "data-rol": "nieuwe-verf", onclick: () => this.nieuw() }, "Nieuwe verf")),
        this.lijstEl, this.detailEl),
      this.formEl);
    this.bouwLijst();
  }

  bouwLijst() {
    this.lijstEl.replaceChildren(...(this.lijst.length ? this.lijst.map((v) => h("button", {
      class: "verf-item" + (v.slug === this.gekozen ? " gekozen" : ""), "data-slug": v.slug, onclick: () => this.toonDetail(v.slug),
    }, h("span", { class: "staal", style: `background:${v.staal}` }), h("span", { class: "naam" }, v.naam)))
      : [h("p", { class: "hint" }, "De bibliotheek is nog leeg.")]));
  }

  async toonDetail(slug) {
    this.gekozen = slug;
    this.bouwLijst();
    try {
      const it = await api.verfLees(slug);
      const e = it.eigenschappen, p = it.vertaling.paint;
      const rij = (k, v) => (v == null || v === "" ? null : [h("dt", {}, k), h("dd", {}, String(v))]);
      this.detailEl.replaceChildren(h("div", { class: "verf-kaart" },
        h("h3", {}, h("span", { class: "staal groot", style: `background:${lineairNaarHex(p.color)}` }), " ", e.merk ?? "", " ", e.product ?? "", " ", e.kleurnaam ?? ""),
        h("dl", { class: "kern" },
          rij("Kleurcode", e.kleurcode), rij("Hex", e.hex), rij("Glans", [e.glansgraad, e.glans_gu_60 != null ? `${e.glans_gu_60} GU` : null].filter(Boolean).join(", ")),
          rij("Effect", e.effect), rij("Soort in de app", p.kind), rij("Ruwheid (alpha)", p.roughness), rij("Opmerking", e.opmerking), rij("Bewaard op", it.datum),
          e.bron_url ? [h("dt", {}, "Bron"), h("dd", {}, /^https?:\/\//i.test(e.bron_url)
            ? h("a", { href: e.bron_url, target: "_blank", rel: "noopener noreferrer" }, e.bron_url) : e.bron_url)] : null),
        it.vertaling.waarschuwingen.map((t) => h("p", { class: "waarschuwing" }, t)),
        h("div", { class: "rij" },
          h("button", { class: "klein", "data-rol": "verf-bewerk", onclick: () => this.nieuw(e, slug) }, "Bewerk"),
          h("button", { class: "klein", "data-rol": "verf-verwijder", onclick: () => this.verwijder(slug) }, "Verwijder"))));
    } catch (er) { this.meld(`Verf laden mislukt: ${er.message}`, true); }
  }

  async verwijder(slug) {
    if (!confirm(`Verf "${slug}" uit de bibliotheek verwijderen?`)) return;
    try {
      await api.verfVerwijder(slug);
      this.gekozen = null; this.detailEl.replaceChildren();
      await this.ververs();
    } catch (er) { this.meld(`Verwijderen mislukt: ${er.message}`, true); }
  }

  // --- formulier ---
  async nieuw(eigenschappen = null, slug = null) {
    this.schema ??= await api.verfSchema().catch(() => null);
    this.bewerkSlug = slug;
    this.w = { ...LEEG(), ...Object.fromEntries(Object.entries(eigenschappen ?? {}).map(([k, v]) => [k, v ?? LEEG()[k]])) };
    this.bouwFormulier();
    this.formEl.hidden = false;
    this.vertaal(0);
  }

  eigenschap(k) { return this.schema?.properties?.[k] ?? {}; }

  invoer(k) {
    const sch = this.eigenschap(k);
    const bij = () => { this.w[k] = el.type === "checkbox" ? el.checked : el.value; this.wisFout(); this.vertaal(); };
    let el;
    if (k === "effect") {
      const opties = (this.schema?.["$defs"]?.Effect?.enum) ?? ["geen", "metallic", "chroom", "candy", "parelmoer", "glitter", "fluo"];
      el = h("select", {}, opties.map((o) => h("option", { value: o, selected: o === this.w[k] }, o)));
    } else if (k === "glansgraad") {
      el = h("input", { type: "text", list: "glansgraden", value: this.w[k], placeholder: "term, bv. zijdeglans" });
    } else if (k === "ondergrond_candy") {
      el = h("select", {}, [["", "(niet van toepassing)"], ["metallic", "metallic"], ["white", "wit"]].map(([v, t]) => h("option", { value: v, selected: v === this.w[k] }, t)));
    } else if (k === "transparant") {
      el = h("input", { type: "checkbox", checked: !!this.w[k] });
    } else if (k === "glans_gu_60") {
      el = h("input", { type: "number", min: 0, max: 120, step: 1, value: this.w[k], placeholder: "GU bij 60 graden" });
    } else if (k === "opmerking") {
      el = h("textarea", { rows: 2, spellcheck: "false" }); el.value = this.w[k];
    } else {
      el = h("input", { type: "text", value: this.w[k], spellcheck: "false", placeholder: k === "hex" ? "#rrggbb" : k === "kleurcode" ? "RAL 3020" : "" });
    }
    el.dataset.veld = k;
    el.addEventListener(el.tagName === "SELECT" || el.type === "checkbox" ? "change" : "input", bij);
    this.velden[k] = el;
    const wrap = h("label", { class: "veld", title: sch.description ?? "" }, h("span", { class: "lbl" }, k.replaceAll("_", " ")), el);
    if (k === "hex") {
      const picker = h("input", { type: "color", value: /^#[0-9a-f]{6}$/i.test(this.w.hex) ? this.w.hex : "#808080" });
      picker.addEventListener("input", () => { el.value = picker.value; bij(); });
      return h("label", { class: "veld", title: sch.description ?? "" }, h("span", { class: "lbl" }, "hex"), h("span", { class: "kleurveld" }, picker, el));
    }
    return wrap;
  }

  bouwFormulier() {
    this.velden = {};
    this.vertalingEl = h("div", { class: "verf-vertaling", "data-rol": "verf-vertaling", "aria-live": "polite" });
    this.foutEl = h("p", { class: "fout", "data-rol": "verf-fout", hidden: true });
    this.antwoordEl = h("textarea", { rows: 5, class: "antwoord", "data-rol": "chatgpt-antwoord", spellcheck: "false",
      placeholder: "Plak hier het antwoord van ChatGPT (een JSON-blok, een codeblok mag)." });
    this.antwoordEl.addEventListener("paste", () => setTimeout(() => this.leesAntwoord(), 0));
    this.vraagEl = h("textarea", { rows: 4, class: "antwoord", readonly: true, hidden: true, "data-rol": "chatgpt-vraag" });
    this.bewaarEl = h("button", { class: "primair", "data-rol": "verf-bewaar", onclick: () => this.bewaar(false) }, "Bewaar in bibliotheek");
    this.bewaarMeldEl = h("span", { class: "status", "data-rol": "verf-bewaar-melding" });
    const lijst = h("datalist", { id: "glansgraden" }, GLANSTERMEN.map((t) => h("option", { value: t })));
    this.formEl.replaceChildren(lijst,
      h("div", { class: "verf-links" },
        h("h3", {}, this.bewerkSlug ? "Verf bewerken" : "Nieuwe verf"),
        h("div", { class: "chatgpt-brug" },
          h("p", { class: "hint" }, "Zonder te typen: vul merk, product en kleur in, kopieer de vraag, plak hem in ChatGPT en plak het antwoord hieronder terug."),
          h("div", { class: "rij" }, h("button", { "data-rol": "kopieer-vraag", onclick: () => this.kopieerVraag() }, "Vraag voor ChatGPT kopiëren"),
            h("span", { class: "status", "data-rol": "kopieer-melding" })),
          this.vraagEl,
          h("label", { class: "lbl" }, "Antwoord van ChatGPT"), this.antwoordEl,
          h("div", { class: "rij" }, h("button", { "data-rol": "lees-antwoord", onclick: () => this.leesAntwoord() }, "Antwoord inlezen"))),
        this.foutEl,
        GROEPEN.map(([titel, sleutels]) => h("fieldset", {}, h("legend", {}, titel), sleutels.map((k) => this.invoer(k)))),
        h("div", { class: "rij" }, this.bewaarEl, h("button", { onclick: () => { this.formEl.hidden = true; } }, "Sluiten"), this.bewaarMeldEl)),
      h("div", { class: "verf-rechts" }, h("h3", {}, "Vertaling naar de app"), this.vertalingEl));
  }

  vulFormulier(e) {
    this.w = { ...LEEG(), ...Object.fromEntries(Object.entries(e).map(([k, v]) => [k, v ?? LEEG()[k]])) };
    for (const [k, el] of Object.entries(this.velden)) {
      if (el.type === "checkbox") el.checked = !!this.w[k]; else el.value = this.w[k] ?? "";
    }
    const p = this.formEl.querySelector('input[type=color]');
    if (p && /^#[0-9a-f]{6}$/i.test(this.w.hex)) p.value = this.w.hex;
  }

  wisFout() {
    this.foutEl.hidden = true;
    for (const el of Object.values(this.velden)) el.classList.remove("ongeldig");
  }

  toonFout(melding, veld) {
    this.foutEl.textContent = melding;
    this.foutEl.hidden = false;
    const el = veld && this.velden[veld];
    if (el) { el.classList.add("ongeldig"); el.scrollIntoView?.({ block: "nearest" }); }
  }

  // --- live vertaling ---
  vertaal(wacht = 300) {
    clearTimeout(this.debounce);
    const nr = ++this.volgnr;
    this.debounce = setTimeout(async () => {
      try {
        const v = await api.verfVertaal(naarAanvraag(this.w));
        if (nr !== this.volgnr) return;
        this.toonVertaling(v);
      } catch (e) {
        if (nr !== this.volgnr) return;
        const { melding, veld } = foutInfo(e);
        this.vertalingEl.replaceChildren(h("p", { class: "hint" }, `Nog niet te vertalen: ${melding}`));
        this.laatste = null;
        if (veld && this.velden[veld] && this.w[veld]) this.velden[veld].classList.add("ongeldig");
      }
    }, wacht);
  }

  toonVertaling(v) {
    this.laatste = v;
    const p = v.paint;
    this.vertalingEl.replaceChildren(
      h("div", { class: "vertaling-kop" },
        h("span", { class: "staal groot", "data-rol": "vertaling-staal", style: `background:${lineairNaarHex(p.color)}` }),
        h("span", {}, h("b", {}, p.kind), p.roughness != null ? ` · ruwheid (alpha) ${p.roughness}` : "", ` · kleur ${lineairNaarHex(p.color)}`)),
      ...v.waarschuwingen.map((t) => h("p", { class: "waarschuwing", "data-rol": "waarschuwing" }, h("b", {}, "Let op: "), t)),
      h("table", { class: "hk-tabel vertaling-tabel" },
        h("thead", {}, h("tr", {}, ["instelling", "waarde", "komt van", "regel"].map((t) => h("th", {}, t)))),
        h("tbody", {}, v.uitleg.map((u) => h("tr", {},
          h("td", {}, h("b", {}, u.veld)), h("td", {}, u.waarde), h("td", {}, h("span", { class: "chip" }, BRON_TEKST[u.bron] ?? u.bron)), h("td", { class: "hint" }, u.regel))))));
  }

  // --- ChatGPT-brug ---
  async kopieerVraag() {
    const melding = this.formEl.querySelector('[data-rol=kopieer-melding]');
    const kleur = [this.w.kleurnaam, this.w.kleurcode].filter(Boolean).join(" ") || this.w.hex || "";
    try {
      const { vraag } = await api.verfVraag(this.w.merk ?? "", this.w.product ?? "", kleur);
      this.vraagEl.value = vraag;
      try {
        await navigator.clipboard.writeText(vraag);
        melding.textContent = "Gekopieerd. Plak de vraag in ChatGPT.";
      } catch {
        this.vraagEl.hidden = false; this.vraagEl.select();
        melding.textContent = "Kopiëren naar het klembord lukte niet; selecteer de tekst hieronder en kopieer zelf (Ctrl+C).";
      }
    } catch (e) { melding.textContent = `Vraag ophalen mislukt: ${e.message}`; }
  }

  async leesAntwoord() {
    const tekst = this.antwoordEl.value.trim();
    if (!tekst) return;
    this.wisFout();
    try {
      const r = await api.verfUitTekst(tekst);
      this.vulFormulier(r.eigenschappen);
      this.volgnr++;
      this.toonVertaling(r.vertaling);
      this.meld("Antwoord ingelezen: controleer de velden en de vertaling.");
    } catch (e) {
      const { melding, veld } = foutInfo(e);
      this.toonFout(melding, veld);
    }
  }

  // --- bewaren ---
  async bewaar(overschrijf) {
    this.bewaarMeldEl.replaceChildren();
    this.wisFout();
    try {
      const it = await api.verfBewaar(naarAanvraag(this.w), overschrijf || !!this.bewerkSlug);
      this.bewaarMeldEl.textContent = `Bewaard als "${it.slug}".`;
      this.bewerkSlug = it.slug;
      await this.ververs();
      await this.toonDetail(it.slug);
    } catch (e) {
      if (e.status === 409) {
        this.bewaarMeldEl.replaceChildren("Deze verf staat al in de bibliotheek. ",
          h("button", { class: "klein", "data-rol": "verf-overschrijf", onclick: () => this.bewaar(true) }, "Overschrijven"));
      } else {
        const { melding, veld } = foutInfo(e);
        this.toonFout(melding, veld);
      }
    }
  }
}
