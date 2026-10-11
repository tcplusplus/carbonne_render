// Reekspaneel: parameter en waarden kiezen, plek van de render gebruiken, resultaat als rij beelden + grafieken.
import * as api from "./api.ts";
import { tekstNaarHex } from "./kleur.ts";
import { h } from "./paneel.ts";
import type { Kind } from "./paneel.ts";
import { isPunt } from "./selectie.ts";
import type { Plek } from "./selectie.ts";
import { nieuweAfwerking } from "./staat.ts";
import type { Afwerking, Cfg } from "./staat.ts";
import type { ReeksMeting, ReeksParameter, ReeksStatus } from "./types/api.ts";

const EIND: readonly string[] = ["klaar", "fout", "geannuleerd"];
const SVGNS = "http://www.w3.org/2000/svg";
const getal = (v: number, d = 1) => v.toFixed(d).replace(".", ",");
const sv = (tag: string, attrs: Record<string, string | number> = {}, ...kinderen: Kind[]): SVGElement => {
  const e = document.createElementNS(SVGNS, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, String(v));
  e.append(...(kinderen as unknown as unknown[]).flat(Infinity).filter((c) => c != null) as (Node | string)[]);
  return e;
};

/** Zet `waarde` op `pad` in een kopie van de config (zoals analyse/reeks.py::zet_pad). */
// eslint-vrij: het pad is dynamisch (zoals in de backend), dus de config wordt hier ongetypeerd doorlopen
export function zetPad(cfg: Cfg, pad: string, waarde: unknown): Cfg {
  const c = structuredClone(cfg);
  const delen = pad.split(".");
  let t: any = c;
  for (const d of delen.slice(0, -1)) t = t[d];
  const sleutel = delen.at(-1)!;
  const w = waarde as { type?: string } | null | undefined;
  t[sleutel] = ["zijkant", "onderkant"].includes(pad) && w?.type ? { ...nieuweAfwerking(w.type, {}), ...w } : structuredClone(waarde);
  return c;
}

export function afwerkingLabel(w: Afwerking): string {
  const naam = ({ bare: "onbehandeld", paint: "verf", clearcoat: "matte lak", plate: "plaat" } as Record<string, string>)[w.type] ?? w.type;
  const kind = "kind" in w ? w.kind : null;
  const kleur = "color" in w ? w.color : null;
  return [naam, kind && kind !== "matte" ? kind : w.type === "paint" ? "mat" : null, kleur].filter(Boolean).join(" ");
}

export interface ReeksInstelling {
  haalConfig: () => Cfg; haalEv: () => number; plek?: Plek | null; bijLaad: (cfg: Cfg) => void; ral: Record<string, string>;
}

export class Reeks {
  root: HTMLElement;
  haalConfig: () => Cfg;
  haalEv: () => number;
  bijLaad: (cfg: Cfg) => void;
  ral: Record<string, string>;
  plek: Plek | null;
  id: string | null = null;
  basis: Cfg | null = null;
  padNu = "";
  params: ReeksParameter[] = [];
  lees: () => unknown[] = () => [];
  // de bediening wordt in bouw() gemaakt (async, na het laden van de parameters)
  sel!: HTMLSelectElement;
  waardenBox!: HTMLElement;
  breedte!: HTMLSelectElement;
  spp!: HTMLSelectElement;
  plekTekst!: HTMLElement;
  start!: HTMLButtonElement;
  stop!: HTMLButtonElement;
  balk!: HTMLProgressElement;
  status!: HTMLElement;
  uit!: HTMLElement;
  laagNr: HTMLInputElement | null = null;

  constructor(root: HTMLElement, { haalConfig, haalEv, plek, bijLaad, ral }: ReeksInstelling) {
    this.root = root;
    this.haalConfig = haalConfig;
    this.haalEv = haalEv;
    this.bijLaad = bijLaad;
    this.ral = ral;
    this.plek = plek ?? null;
    this.bouw().catch((e: Error) => root.replaceChildren(h("p", { class: "status fout" }, `Parameters niet geladen: ${e.message}`)));
  }

  zetPlek(p: Plek | null) {
    this.plek = p;
    if (this.plekTekst) this.plekTekst.textContent = this.plekLabel();
  }

  plekLabel() {
    const p = this.plek;
    if (!p) return "geen plek gekozen";
    const f = (v: number) => getal(v * 100, 0);
    return isPunt(p) ? `punt ${f(p.x0)} %, ${f(p.y0)} %` : `gebied ${f(p.x0)}-${f(p.x1)} %, ${f(p.y0)}-${f(p.y1)} %`;
  }

  async bouw() {
    this.params = await api.reeksParameters();
    this.sel = h("select", { "data-rol": "parameter", onchange: () => this.bouwWaarden() },
      this.params.map((p) => h("option", { value: p.pad }, `${p.pad} - ${p.omschrijving}`)));
    this.waardenBox = h("div", { class: "waarden" });
    this.breedte = h("select", { "data-rol": "breedte" }, [192, 256, 384].map((b) => h("option", { value: b, selected: b === 256 }, `${b} px`)));
    this.spp = h("select", { "data-rol": "spp" }, [128, 256, 512, 1024].map((b) => h("option", { value: b, selected: b === 256 }, `${b} spp`)));
    this.plekTekst = h("span", { class: "getallen", "data-rol": "plek" }, this.plekLabel());
    this.start = h("button", { class: "primair", "data-rol": "reeks-start", onclick: () => this.begin() }, "Start reeks");
    this.stop = h("button", { disabled: true, onclick: () => this.annuleer() }, "Annuleer");
    this.balk = h("progress", { value: 0, max: 1 });
    this.status = h("span", { class: "status", "aria-live": "polite" });
    this.uit = h("div", { class: "reeks-uit" });
    this.root.replaceChildren(
      h("div", { class: "reeks-bediening" },
        h("label", { class: "veld" }, h("span", { class: "lbl" }, "Parameter"), this.sel),
        this.waardenBox,
        h("div", { class: "rij" }, h("span", { class: "lbl" }, "Plek"), this.plekTekst,
          h("label", {}, "beeld ", this.breedte), h("label", {}, this.spp)),
        h("div", { class: "rij" }, this.start, this.stop, this.balk, this.status)),
      this.uit);
    this.bouwWaarden();
  }

  get param(): ReeksParameter { return this.params.find((p) => p.pad === this.sel.value)!; }

  bouwWaarden() {
    const p = this.param;
    this.lees = () => [];
    const vk = (w: unknown, tekst: string, aan = true) => {
      const i = h("input", { type: "checkbox", checked: aan });
      return { i, w, el: h("label", { class: "vink" }, i, tekst) };
    };
    const lijstKeuze = (items: any[], tekst: (w: any) => string) => {
      const rijen = items.map((w, n) => vk(w, tekst(w), n < 6));
      this.lees = () => rijen.filter((r) => r.i.checked).map((r) => r.w);
      return h("div", { class: "keuzes" }, rijen.map((r) => r.el));
    };
    let inhoud: HTMLElement;
    if (p.type === "getal") {
      const v = p.voorbeelden;
      const lo = Math.min(...v), hi = Math.max(...v);
      const van = h("input", { type: "number", value: lo, min: p.min ?? "", max: p.max ?? "", step: "any" });
      const tot = h("input", { type: "number", value: hi, min: p.min ?? "", max: p.max ?? "", step: "any" });
      const stap = h("input", { type: "number", value: +((hi - lo) / 4 || 1).toPrecision(3), min: 0, step: "any" });
      this.lees = () => {
        const a = parseFloat(van.value), b = parseFloat(tot.value), s = parseFloat(stap.value);
        if ([a, b, s].some(Number.isNaN) || s <= 0 || b < a) return [];
        const uit = [];
        for (let x = a, n = 0; x <= b + s * 1e-9 && n < 24; x += s, n++) uit.push(+x.toPrecision(8));
        return uit;
      };
      inhoud = h("div", { class: "rij" }, h("label", {}, "van ", van), h("label", {}, "tot ", tot), h("label", {}, "stap ", stap),
        h("span", { class: "eenheid" }, p.eenheid ?? ""));
    } else if (p.type === "afwerking") inhoud = lijstKeuze(p.voorbeelden, afwerkingLabel);
    else if (p.type === "keuze") inhoud = lijstKeuze(p.voorbeelden, String);
    else if (p.type === "waar/onwaar") inhoud = lijstKeuze([false, true], (w) => (w ? "aan" : "uit"));
    else if (p.type === "kleur") inhoud = this.kleurLijst(p.voorbeelden);
    else inhoud = h("p", { class: "status fout" }, `onbekend type ${p.type}`);
    this.laagNr = null;
    const extra = [];
    if (p.patroon) {
      this.laagNr = h("input", { type: "number", min: 0, step: 1, value: 0 });
      extra.push(h("label", {}, "laag ", this.laagNr));
    }
    this.waardenBox.replaceChildren(h("div", { class: "rij" }, h("span", { class: "lbl" }, "Waarden"), ...extra), inhoud);
  }

  kleurLijst(start: string[]) {
    const box = h("div", { class: "kleuren" });
    const rijen: { picker: HTMLInputElement; tekst: HTMLInputElement; el: HTMLElement }[] = [];
    const voeg = (w: string) => {
      const picker = h("input", { type: "color", value: tekstNaarHex(w, this.ral) ?? "#808080" });
      const tekst = h("input", { type: "text", class: "kleurtekst", value: w, spellcheck: "false" });
      picker.addEventListener("input", () => { tekst.value = picker.value; tekst.classList.remove("ongeldig"); });
      tekst.addEventListener("input", () => {
        const ok = tekstNaarHex(tekst.value, this.ral);
        tekst.classList.toggle("ongeldig", !ok);
        if (ok) picker.value = ok;
      });
      const r = { picker, tekst, el: null as unknown as HTMLElement };
      r.el = h("span", { class: "kleurveld" }, picker, tekst, h("button", { class: "klein", onclick: () => { rijen.splice(rijen.indexOf(r), 1); r.el.remove(); } }, "x"));
      rijen.push(r);
      box.append(r.el);
    };
    start.forEach(voeg);
    this.lees = () => rijen.map((r) => r.tekst.value.trim()).filter((t) => tekstNaarHex(t, this.ral))
      .map((t) => (/^(ral\s*)?\d{4}$/i.test(t) ? `RAL ${t.replace(/\D/g, "")}` : tekstNaarHex(t, this.ral)));
    return h("div", {}, box, h("button", { class: "klein", onclick: () => voeg("#808080") }, "+ kleur"));
  }

  pad() {
    const p = this.param;
    return p.patroon ? p.pad.replace(/\.n\./, `.${Math.max(0, parseInt(this.laagNr?.value ?? "0", 10) || 0)}.`) : p.pad;
  }

  melding(t: string, fout = false) { this.status.textContent = t; this.status.classList.toggle("fout", fout); }

  async begin() {
    if (this.id) return;
    if (!this.plek) { this.melding("kies eerst een plek op de render", true); return; }
    const waarden = this.lees();
    if (!waarden.length) { this.melding("geen geldige waarden", true); return; }
    const config = this.haalConfig();
    const bw = parseInt(this.breedte.value, 10);
    const bh = Math.round(bw * config.render.hoogte / config.render.breedte);
    const p = this.plek;
    const gebied = isPunt(p) ? [+(p.x0 * bw).toFixed(1), +(p.y0 * bh).toFixed(1)]
      : [Math.floor(p.x0 * bw), Math.floor(p.y0 * bh), Math.max(Math.floor(p.x0 * bw) + 1, Math.ceil(p.x1 * bw)), Math.max(Math.floor(p.y0 * bh) + 1, Math.ceil(p.y1 * bh))];
    this.start.disabled = true;
    this.stop.disabled = false;
    this.balk.value = 0;
    this.uit.replaceChildren();
    this.melding("Aanvraag verstuurd...");
    this.basis = config;
    this.padNu = this.pad();
    try {
      const { id } = await api.startReeks({ config, parameter: this.padNu, waarden, gebied, straal: Math.max(1.5, +(bw / 128).toFixed(1)),
        breedte: bw, spp: parseInt(this.spp.value, 10), ev: this.haalEv() });
      this.id = id;
    } catch (e) { this.melding((e as Error).message, true); this.reset(); return; }
    this.volg(this.id!, waarden.length);
  }

  volg(id: string, n: number) {
    let klaar = false, gezien = -1;
    const verwerk = async (m: ReeksStatus) => {
      const v = m.voortgang;
      this.balk.max = n;
      this.balk.value = m.metingen_klaar ?? v?.klaar ?? 0;
      this.melding(m.status === "wachtend" ? "In de wachtrij..." : `${m.metingen_klaar ?? 0} / ${n}${v?.label ? ` (${v.label})` : ""}`);
      const nu = (m.metingen_klaar ?? 0) + (EIND.includes(m.status) ? 1000 : 0);
      if (nu !== gezien) {
        gezien = nu;
        if ((m.metingen_klaar ?? 0) > 0) await this.toonResultaat(id);
      }
      if (EIND.includes(m.status) && !klaar) {
        klaar = true;
        this.melding(m.status === "klaar" ? `Klaar: ${n} waarden` : m.status === "geannuleerd" ? `Geannuleerd na ${m.metingen_klaar ?? 0} waarden` : `Fout: ${m.fout}`, m.status === "fout");
        this.reset();
      }
    };
    const poll = async () => {
      while (!klaar) {
        await new Promise((r) => setTimeout(r, 1000));
        try { await verwerk(await api.reeksStatus(id)); } catch { this.melding("Verbinding met de server weg", true); return; }
      }
    };
    api.volgReeks(id, verwerk, () => { if (!klaar) poll(); });
  }

  reset() { this.id = null; this.start.disabled = false; this.stop.disabled = true; }

  async annuleer() {
    if (!this.id) return;
    this.stop.disabled = true;
    try { await api.annuleerReeks(this.id); } catch (e) { this.melding((e as Error).message, true); }
  }

  async toonResultaat(id: string) {
    const s = await api.reeksStatus(id);
    if (!s.resultaat || id !== (this.id ?? id)) return;
    const r = s.resultaat;
    const metingen = r.metingen;
    const rij = h("div", { class: "reeks-rij" }, metingen.map((m, i) => {
      const [L, C, hh] = m.lch;
      return h("figure", { class: "reeks-item" + (i > 0 && m.binnen_ruis ? " ruis" : ""), "data-waarde": i, tabindex: 0, role: "button",
        title: "Laad deze waarde in de preview", onclick: () => this.laadWaarde(r.parameter, m.waarde) },
      h("img", { src: s.urls.beelden[i], alt: m.label }),
      h("figcaption", {}, h("b", {}, m.label),
        h("div", { class: "rij" }, h("span", { class: "staal", style: `background:${m.hex}`, title: m.hex }),
          h("span", { class: "getallen" }, `L* ${getal(L)} C* ${getal(C)} h ${getal(hh, 0)}°`)),
        h("span", { class: "getallen" }, i === 0 ? "referentie" : `ΔE ${getal(m.de2000)}${m.binnen_ruis ? " ruis" : ""}`)));
    }));
    this.uit.replaceChildren(rij, grafieken(metingen));
  }

  laadWaarde(pad: string, waarde: unknown) { if (this.basis) this.bijLaad(zetPad(this.basis, pad, waarde)); }
}

// ---- grafieken (SVG) ----
function grafieken(metingen: ReeksMeting[]) {
  const num = metingen.every((m) => typeof m.waarde === "number") && new Set(metingen.map((m) => m.waarde)).size > 1;
  const W = 520, H = 170, ml = 34, mr = 36, mt = 12, mb = 38;
  const xs = metingen.map((m, i) => num ? (m.waarde as number) : i);
  const lo = Math.min(...xs), hi = Math.max(...xs);
  const X = (x: number) => ml + ((x - lo) / (hi - lo || 1)) * (W - ml - mr);
  const kort = (m: ReeksMeting) => (num ? String(+(m.waarde as number).toPrecision(4)) : m.label.length > 11 ? m.label.slice(0, 10) + "…" : m.label);
  const as = (extra: SVGElement[]) => [
    sv("line", { x1: ml, y1: H - mb, x2: W - mr, y2: H - mb, class: "as" }),
    ...metingen.map((m, i) => sv("text", { x: X(xs[i]), y: H - mb + 13, class: "tik", "text-anchor": "middle" }, kort(m))), ...extra];

  // L* en C* tegenover de waarde
  const lijn = (sleutel: 0 | 1, klasse: string) => {
    const w = metingen.map((m) => m.lch[sleutel]);
    const max = Math.max(...metingen.map((m) => Math.max(m.lch[0], m.lch[1])), 1) * 1.1;
    const Y = (v: number) => H - mb - (v / max) * (H - mb - mt);
    return { w, Y, klasse, max };
  };
  const L = lijn(0, "reeks-L"), C = lijn(1, "reeks-C");
  const max = Math.max(L.max, C.max);
  const Y = (v: number) => H - mb - (v / max) * (H - mb - mt);
  const reeks = (s: number[], klasse: string, label: string) => [
    sv("polyline", { points: s.map((v, i) => `${X(xs[i])},${Y(v)}`).join(" "), class: `lijn ${klasse}` }),
    ...s.map((v, i) => sv("circle", { cx: X(xs[i]), cy: Y(v), r: 3.5, class: `punt ${klasse}${i > 0 && metingen[i].binnen_ruis ? " ruis" : ""}` },
      sv("title", {}, `${label} ${getal(v)}`))),
    sv("text", { x: X(xs.at(-1)!) + 7, y: Y(s.at(-1)!) + 4, class: `lab ${klasse}` }, label)];
  const g1 = sv("svg", { viewBox: `0 0 ${W} ${H}`, class: "grafiek", role: "img", "aria-label": "L* en C*" },
    sv("text", { x: 2, y: mt, class: "tik" }, getal(max, 0)), sv("text", { x: 2, y: H - mb, class: "tik" }, "0"),
    ...as([]), ...reeks(L.w, "reeks-L", "L*"), ...reeks(C.w, "reeks-C", "C*"));

  // herkomstaandelen (gestapeld, kleur = staal van de lichtbron)
  const namen: string[] = [];
  for (const m of metingen) for (const c of m.herkomst.categorieen) if (c.aandeel_pct >= 0.05 && !namen.includes(c.naam)) namen.push(c.naam);
  const bw = Math.min(36, ((W - ml - mr) / metingen.length) * 0.7);
  const stapel: SVGElement[] = [];
  metingen.forEach((m, i) => {
    let y = H - mb;
    for (const c of m.herkomst.categorieen) {
      if (c.aandeel_pct < 0.05) continue;
      const hh = (c.aandeel_pct / 100) * (H - mb - mt);
      y -= hh;
      stapel.push(sv("rect", { x: X(xs[i]) - bw / 2, y, width: bw, height: hh, fill: c.hex_per_pad, class: "seg" }, sv("title", {}, `${c.naam} ${getal(c.aandeel_pct)} %`)));
    }
  });
  const g2 = sv("svg", { viewBox: `0 0 ${W} ${H}`, class: "grafiek", role: "img", "aria-label": "herkomstaandelen" },
    sv("text", { x: 2, y: mt, class: "tik" }, "100"), sv("text", { x: 2, y: H - mb, class: "tik" }, "0 %"), ...as([]), ...stapel);
  const legenda = h("div", { class: "legenda" }, namen.map((n) => {
    const c = metingen.flatMap((m) => m.herkomst.categorieen).find((k) => k.naam === n);
    return h("span", {}, h("span", { class: "staal", style: `background:${c!.hex_per_pad}` }), n);
  }));
  return h("div", { class: "grafieken" }, h("div", {}, g1), h("div", {}, g2, legenda));
}
