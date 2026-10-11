// Paneel Verven (T20): bibliotheek, formulier "nieuwe verf" met live vertaling, en de ChatGPT-brug.
import * as api from "./api.ts";
import { lineairNaarHex } from "./kleur.ts";
import { h } from "./paneel.ts";
import type { SchemaKnoop } from "./schema.ts";
import type { ApiFout } from "./api.ts";
import type { VerfLijstItem, VerfVertaling } from "./types/api.ts";
import type { VerfEigenschappen } from "./types/verf.ts";

const GLANSTERMEN = ["mat", "zijdemat", "zijdeglans", "satijn", "glans", "hoogglans"];
const BRON_TEKST: Record<string, string> = { standaard: "standaard", model: "model" };
// Groepering van de velden uit GET /api/verven/schema.
const GROEPEN: readonly (readonly [string, readonly string[]])[] = [
  ["Identiteit", ["merk", "product", "kleurnaam"]],
  ["Kleur", ["kleurcode", "hex"]],
  ["Glans", ["glansgraad", "glans_gu_60"]],
  ["Effect", ["effect", "transparant", "ondergrond_candy"]],
  ["Bron", ["bron_url", "opmerking"]],
];
/** Waarden van het formulier: alles tekst, behalve het vinkje; een leeg veld is "". */
export type Formulier = Record<string, string | boolean>;
const LEEG = (): Formulier => ({ merk: "", product: "", kleurnaam: "", kleurcode: "", hex: "", glansgraad: "", glans_gu_60: "",
  effect: "geen", transparant: false, ondergrond_candy: "", bron_url: "", opmerking: "" });

/** Formulierwaarden -> aanvraag voor de API: lege velden vervallen. */
export function naarAanvraag(w: Formulier): Partial<VerfEigenschappen> {
  const o: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(w)) {
    if (k === "transparant") { o[k] = !!v; continue; }
    if (v === "" || v == null) continue;
    o[k] = k === "glans_gu_60" ? Number(v) : v;
  }
  return o as Partial<VerfEigenschappen>;
}

/** Fout van de API -> {melding, veld}; kent het eigen formaat van uit-tekst en de lijst van pydantic. */
export function foutInfo(e: Pick<ApiFout, "message" | "detail">): { melding: string; veld: string | null } {
  const d = e.detail;
  if (d && typeof d === "object" && !Array.isArray(d)) {
    const o = d as { melding?: string; veld?: string };
    return { melding: o.melding ?? String(e.message), veld: o.veld ?? null };
  }
  if (Array.isArray(d) && d.length) {
    const loc: (string | number)[] = d[0].loc ?? [];
    const veld = loc.length > 1 ? String(loc[loc.length - 1]) : null;
    return { melding: `${veld ? veld + ": " : ""}${d[0].msg}`, veld };
  }
  return { melding: typeof d === "string" ? d : e.message, veld: null };
}

type Veld = HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement;

export class VerfPaneel {
  root: HTMLElement;
  bijLijst: (lijst: VerfLijstItem[]) => void;
  meld: (tekst: string, fout?: boolean) => void;
  lijst: VerfLijstItem[] = [];
  schema: SchemaKnoop | null = null;
  w: Formulier = LEEG();
  debounce: ReturnType<typeof setTimeout> | undefined;
  volgnr = 0;
  gekozen: string | null = null;
  bewerkSlug: string | null = null;
  velden: Record<string, Veld> = {};
  laatste: VerfVertaling | null = null;
  // het formulier wordt in bouw() en bouwFormulier() gemaakt
  lijstEl!: HTMLElement;
  detailEl!: HTMLElement;
  formEl!: HTMLElement;
  vertalingEl!: HTMLElement;
  foutEl!: HTMLElement;
  antwoordEl!: HTMLTextAreaElement;
  vraagEl!: HTMLTextAreaElement;
  bewaarEl!: HTMLButtonElement;
  bewaarMeldEl!: HTMLElement;

  constructor(root: HTMLElement, { bijLijst, meld }: { bijLijst: VerfPaneel["bijLijst"]; meld: VerfPaneel["meld"] }) {
    this.root = root;
    this.bijLijst = bijLijst;
    this.meld = meld;
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

  async toonDetail(slug: string) {
    this.gekozen = slug;
    this.bouwLijst();
    try {
      const it = await api.verfLees(slug);
      const e = it.eigenschappen, p = it.vertaling.paint;
      const rij = (k: string, v: unknown) => (v == null || v === "" ? null : [h("dt", {}, k), h("dd", {}, String(v))]);
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
    } catch (er) { this.meld(`Verf laden mislukt: ${(er as Error).message}`, true); }
  }

  async verwijder(slug: string) {
    if (!confirm(`Verf "${slug}" uit de bibliotheek verwijderen?`)) return;
    try {
      await api.verfVerwijder(slug);
      this.gekozen = null; this.detailEl.replaceChildren();
      await this.ververs();
    } catch (er) { this.meld(`Verwijderen mislukt: ${(er as Error).message}`, true); }
  }

  // --- formulier ---
  async nieuw(eigenschappen: Partial<VerfEigenschappen> | null = null, slug: string | null = null) {
    this.schema ??= await api.verfSchema().catch(() => null);
    this.bewerkSlug = slug;
    this.w = { ...LEEG(), ...Object.fromEntries(Object.entries(eigenschappen ?? {}).map(([k, v]) => [k, v ?? LEEG()[k]])) } as Formulier;
    this.bouwFormulier();
    this.formEl.hidden = false;
    this.vertaal(0);
  }

  eigenschap(k: string): SchemaKnoop { return this.schema?.properties?.[k] ?? {}; }

  invoer(k: string) {
    const sch = this.eigenschap(k);
    const bij = () => { this.w[k] = el instanceof HTMLInputElement && el.type === "checkbox" ? el.checked : el.value; this.wisFout(); this.vertaal(); };
    let el: Veld;
    if (k === "effect") {
      const opties = (this.schema?.["$defs"]?.Effect?.enum as string[] | undefined) ?? ["geen", "metallic", "chroom", "candy", "parelmoer", "glitter", "fluo"];
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
      el = h("textarea", { rows: 2, spellcheck: "false" }); el.value = String(this.w[k]);
    } else {
      el = h("input", { type: "text", value: this.w[k], spellcheck: "false", placeholder: k === "hex" ? "#rrggbb" : k === "kleurcode" ? "RAL 3020" : "" });
    }
    el.dataset.veld = k;
    el.addEventListener(el.tagName === "SELECT" || (el instanceof HTMLInputElement && el.type === "checkbox") ? "change" : "input", bij);
    this.velden[k] = el;
    const wrap = h("label", { class: "veld", title: sch.description ?? "" }, h("span", { class: "lbl" }, k.replaceAll("_", " ")), el);
    if (k === "hex") {
      const picker = h("input", { type: "color", value: /^#[0-9a-f]{6}$/i.test(String(this.w.hex)) ? String(this.w.hex) : "#808080" });
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

  vulFormulier(e: Partial<VerfEigenschappen>) {
    this.w = { ...LEEG(), ...Object.fromEntries(Object.entries(e).map(([k, v]) => [k, v ?? LEEG()[k]])) } as Formulier;
    for (const [k, el] of Object.entries(this.velden)) {
      if (el instanceof HTMLInputElement && el.type === "checkbox") el.checked = !!this.w[k]; else el.value = String(this.w[k] ?? "");
    }
    const p = this.formEl.querySelector<HTMLInputElement>('input[type=color]');
    if (p && /^#[0-9a-f]{6}$/i.test(String(this.w.hex))) p.value = String(this.w.hex);
  }

  wisFout() {
    this.foutEl.hidden = true;
    for (const el of Object.values(this.velden)) el.classList.remove("ongeldig");
  }

  toonFout(melding: string, veld: string | null) {
    this.foutEl.textContent = melding;
    this.foutEl.hidden = false;
    const el = veld ? this.velden[veld] : undefined;
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
        const { melding, veld } = foutInfo(e as ApiFout);
        this.vertalingEl.replaceChildren(h("p", { class: "hint" }, `Nog niet te vertalen: ${melding}`));
        this.laatste = null;
        if (veld && this.velden[veld] && this.w[veld]) this.velden[veld].classList.add("ongeldig");
      }
    }, wacht);
  }

  toonVertaling(v: VerfVertaling) {
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
    const melding = this.formEl.querySelector<HTMLElement>('[data-rol=kopieer-melding]')!;
    const kleur = [this.w.kleurnaam, this.w.kleurcode].filter(Boolean).join(" ") || String(this.w.hex || "");
    try {
      const { vraag } = await api.verfVraag(String(this.w.merk ?? ""), String(this.w.product ?? ""), kleur);
      this.vraagEl.value = vraag;
      try {
        await navigator.clipboard.writeText(vraag);
        melding.textContent = "Gekopieerd. Plak de vraag in ChatGPT.";
      } catch {
        this.vraagEl.hidden = false; this.vraagEl.select();
        melding.textContent = "Kopiëren naar het klembord lukte niet; selecteer de tekst hieronder en kopieer zelf (Ctrl+C).";
      }
    } catch (e) { melding.textContent = `Vraag ophalen mislukt: ${(e as Error).message}`; }
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
      const { melding, veld } = foutInfo(e as ApiFout);
      this.toonFout(melding, veld);
    }
  }

  // --- bewaren ---
  async bewaar(overschrijf: boolean) {
    this.bewaarMeldEl.replaceChildren();
    this.wisFout();
    try {
      const it = await api.verfBewaar(naarAanvraag(this.w), overschrijf || !!this.bewerkSlug);
      this.bewaarMeldEl.textContent = `Bewaard als "${it.slug}".`;
      this.bewerkSlug = it.slug;
      await this.ververs();
      await this.toonDetail(it.slug);
    } catch (e) {
      if ((e as ApiFout).status === 409) {
        this.bewaarMeldEl.replaceChildren("Deze verf staat al in de bibliotheek. ",
          h("button", { class: "klein", "data-rol": "verf-overschrijf", onclick: () => this.bewaar(true) }, "Overschrijven"));
      } else {
        const { melding, veld } = foutInfo(e as ApiFout);
        this.toonFout(melding, veld);
      }
    }
  }
}
