// Geschiedenis van de laatste N HQ-renders en een A/B-vergelijking (schuifbalk of naast elkaar).
import { h } from "./paneel.ts";
import { zetMarkering } from "./selectie.ts";
import type { Plek } from "./selectie.ts";
import type { Cfg, Opties, RenderOpties } from "./staat.ts";
import type { KlareRender } from "./hq.ts";
import type { RenderResultaat } from "./types/api.ts";

const N = 8;

type Plat = Record<string, unknown>;
function plat(o: unknown, pad = "", uit: Plat = {}): Plat {
  if (o !== null && typeof o === "object") for (const [k, v] of Object.entries(o)) plat(v, pad ? `${pad}.${k}` : k, uit);
  else uit[pad] = o;
  return uit;
}

/** Lijst van verschillen tussen twee configs, bv. "zijkant.color: #ff0000 -> #00ff00". */
export function verschillen(a: unknown, b: unknown): string[] {
  const pa = plat(a), pb = plat(b), uit: string[] = [];
  for (const k of new Set([...Object.keys(pa), ...Object.keys(pb)])) {
    if (k.startsWith("scene.camera.")) continue; // camera-afrondingen zijn ruis
    if (JSON.stringify(pa[k]) !== JSON.stringify(pb[k])) uit.push(`${k}: ${pa[k] ?? "-"} → ${pb[k] ?? "-"}`);
  }
  return uit;
}

/** Een bewaarde HQ-render in de geschiedenis. */
export interface GeschiedenisItem {
  nr: number; id: string; herkomst: boolean; url: string; cfg: Cfg; opties: RenderOpties; resultaat: RenderResultaat; label: string; tijd: string;
}
export interface VergelijkDom {
  lijst: HTMLElement; beeld: HTMLElement; modus: HTMLSelectElement; schuif: HTMLInputElement; schuifrij: HTMLElement; verschil: HTMLElement;
}

export class Vergelijk {
  dom: VergelijkDom;
  bijTerugzetten: (cfg: Cfg, opties: Partial<Opties> & { ev?: number }) => void;
  lijst: GeschiedenisItem[] = [];
  a: GeschiedenisItem | null = null;
  b: GeschiedenisItem | null = null;
  modus = "schuif";
  teller = 0;
  plek: Plek | null = null;
  bovenste: HTMLElement | null = null;

  constructor(dom: VergelijkDom, { bijTerugzetten }: { bijTerugzetten: Vergelijk["bijTerugzetten"] }) {
    this.dom = dom;
    this.bijTerugzetten = bijTerugzetten;
    dom.modus.addEventListener("change", () => { this.modus = dom.modus.value; this.teken(); });
    dom.schuif.addEventListener("input", () => this.pasSchuifToe());
    this.teken();
  }

  voegToe(r: KlareRender) {
    const nr = ++this.teller;
    const item = { nr, id: r.id, herkomst: r.herkomst, url: URL.createObjectURL(r.blob), cfg: r.aanvraag.config, opties: r.aanvraag.opties, resultaat: r.resultaat,
      label: `#${nr}`, tijd: new Date().toLocaleTimeString("nl-NL") };
    this.lijst.unshift(item);
    while (this.lijst.length > N) { const o = this.lijst.pop()!; URL.revokeObjectURL(o.url); if (this.a === o) this.a = null; if (this.b === o) this.b = null; }
    if (!this.a) this.a = item; else if (!this.b || this.b === this.a) this.b = item; else { this.a = this.b; this.b = item; }
    this.teken();
  }

  /** Zet de markering van de gekozen plek (fracties) op de getoonde beelden. */
  markeer(plek: Plek | null) {
    this.plek = plek;
    const d = this.dom.beeld;
    for (const k of d.querySelectorAll<HTMLElement>(".wikkel, .vergelijk-beeld.schuif")) zetMarkering(k, plek);
    if (d.classList.contains("schuif")) zetMarkering(d, plek);
  }

  pasSchuifToe() {
    this.bovenste?.style.setProperty("clip-path", `inset(0 ${100 - Number(this.dom.schuif.value)}% 0 0)`);
  }

  teken() {
    const d = this.dom;
    d.lijst.replaceChildren(...this.lijst.map((it) => h("figure", { class: "thumb" + (it === this.a ? " is-a" : "") + (it === this.b ? " is-b" : "") },
      h("img", { src: it.url, alt: it.label }),
      h("figcaption", {}, `${it.label} ${it.tijd}`, h("br"), `${it.resultaat.spp} spp, ${it.resultaat.tijd_s.toFixed(0)} s`),
      h("div", { class: "rij" },
        h("button", { class: "klein", onclick: () => { this.a = it; this.teken(); } }, "A"),
        h("button", { class: "klein", onclick: () => { this.b = it; this.teken(); } }, "B"),
        h("button", { class: "klein", title: "Zet de instellingen van deze render terug", onclick: () => this.bijTerugzetten(it.cfg, it.opties) }, "Terug")))));
    if (!this.lijst.length) d.lijst.append(h("p", { class: "hint" }, "Nog geen HQ-renders. Elke afgeronde render komt hier (de laatste " + N + ")."));
    const { a, b } = this;
    d.beeld.replaceChildren();
    d.verschil.textContent = "";
    d.schuifrij.hidden = this.modus !== "schuif";
    if (!a || !b) { d.beeld.append(h("p", { class: "hint" }, "Kies twee renders met A en B om ze te vergelijken.")); return; }
    d.beeld.style.setProperty("--ar", `${a.cfg.render.breedte} / ${a.cfg.render.hoogte}`);
    d.beeld.className = "vergelijk-beeld " + this.modus;
    if (this.modus === "schuif") {
      const onder = h("img", { src: b.url, alt: "B" }); // rechts zichtbaar
      const boven = h("img", { src: a.url, alt: "A", class: "boven" }); // links zichtbaar, tot de schuifbalk
      this.bovenste = boven;
      d.beeld.append(onder, boven, h("span", { class: "tag tag-b" }, "B"), h("span", { class: "tag tag-a" }, "A"));
      this.pasSchuifToe();
    } else {
      d.beeld.append(h("figure", {}, h("div", { class: "wikkel" }, h("img", { src: a.url, alt: "A", draggable: "false" })), h("figcaption", {}, `A ${a.label}`)),
        h("figure", {}, h("div", { class: "wikkel" }, h("img", { src: b.url, alt: "B", draggable: "false" })), h("figcaption", {}, `B ${b.label}`)));
    }
    const v = verschillen(a.cfg, b.cfg);
    const ev = a.opties.ev !== b.opties.ev ? [`ev: ${a.opties.ev} → ${b.opties.ev}`] : [];
    this.markeer(this.plek);
    d.verschil.textContent = [...v, ...ev].length ? "Verschillen A → B: " + [...v, ...ev].join("; ") : "A en B hebben dezelfde instellingen.";
  }
}
