// Herkomstpaneel: gestapelde balk met stalen, percentages en kerngetallen per bron (een render, of A en B).
import { herkomst as haalHerkomst } from "./api.js";
import { h } from "./paneel.js";
import { plekNaarPixels } from "./selectie.js";

const getal = (v, d = 1) => v.toFixed(d).replace(".", ",");

export function herkomstKolom(titel, d) {
  const cats = d.categorieen.filter((c) => c.aandeel_pct >= 0.05);
  const [L, a, b] = d.lab;
  const k = d.kerngetallen;
  return h("div", { class: "hk" },
    h("div", { class: "hk-kop" },
      h("b", {}, titel),
      h("span", { class: "staal groot", style: `background:${d.hex}`, title: d.hex }),
      h("span", { class: "getallen" }, d.hex, ` L* ${getal(L)} a* ${getal(a)} b* ${getal(b)}`)),
    h("div", { class: "balk", role: "img", "aria-label": "herkomst" },
      cats.map((c) => h("span", { class: "seg", style: `flex:${c.aandeel_pct} 1 0;background:${c.hex_per_pad}`, title: `${c.naam} ${getal(c.aandeel_pct)} %` },
        c.aandeel_pct >= 9 ? `${getal(c.aandeel_pct, 0)} %` : ""))),
    h("table", { class: "hk-tabel" },
      h("thead", {}, h("tr", {}, h("th", {}), h("th", {}), h("th", { class: "r" }, "%"), h("th", {}, "bijdrage"), h("th", {}, "per pad"))),
      h("tbody", {}, cats.map((c) => h("tr", {},
        h("td", {}, h("span", { class: "staal", style: `background:${c.hex_per_pad}` })),
        h("td", {}, c.naam),
        h("td", { class: "r" }, getal(c.aandeel_pct)),
        h("td", {}, h("span", { class: "staal", style: `background:${c.hex}`, title: c.hex })),
        h("td", { class: "getallen" }, c.hex_per_pad))))),
    k ? h("dl", { class: "kern" },
      h("dt", {}, "interne reflecties"), h("dd", {}, getal(k.n_tir + k.n_fresnel, 2)),
      h("dt", {}, "met TIR"), h("dd", {}, `${getal(k.aandeel_tir_pct)} %`),
      h("dt", {}, "weg in epoxy"), h("dd", {}, `${getal(k.weg_epoxy_cm)} cm`)) : null);
}

export class HerkomstPaneel {
  constructor(root) { this.root = root; this.leeg(); }

  leeg(tekst = "-") { this.root.replaceChildren(h("p", { class: "hint" }, tekst)); }

  /** `bronnen`: [{label, id, breedte, hoogte}]; `plek`: fracties. */
  async toon(bronnen, plek) {
    if (!bronnen.length) { this.leeg("geen herkomst bij deze render"); return; }
    const volgnr = (this.volgnr = (this.volgnr ?? 0) + 1);
    const kolommen = await Promise.all(bronnen.map(async (b) => {
      try { return herkomstKolom(b.label, await haalHerkomst(b.id, plekNaarPixels(plek, b.breedte, b.hoogte))); }
      catch (e) { return h("div", { class: "hk" }, h("b", {}, b.label), h("p", { class: "status fout" }, e.message)); }
    }));
    if (volgnr === this.volgnr) this.root.replaceChildren(h("div", { class: "hk-rij" }, kolommen));
  }
}
