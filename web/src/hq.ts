// HQ-paneel: start een Mitsuba-render via de backend en toont het beeld progressief (WebSocket).
import { annuleerRender, renderStatus, resultaatUrl, startRender, volgRender } from "./api.ts";
import type { Cfg, HqAanvraag } from "./staat.ts";
import type { RenderBericht, RenderResultaat } from "./types/api.ts";

const EIND: readonly string[] = ["klaar", "fout", "geannuleerd"];

/** De elementen die het HQ-paneel bedient. */
export interface HqDom {
  kader: HTMLElement; img: HTMLImageElement; leeg: HTMLElement; knop: HTMLButtonElement; annuleer: HTMLButtonElement;
  balk: HTMLProgressElement; status: HTMLElement; links: HTMLElement; png: HTMLAnchorElement; exr: HTMLAnchorElement;
}
/** Een afgeronde render zoals de vergelijking hem krijgt. */
export interface KlareRender { id: string; blob: Blob; resultaat: RenderResultaat; aanvraag: HqAanvraag; herkomst: boolean }

export class HQ {
  dom: HqDom;
  bijKlaar: (r: KlareRender) => void;
  /** Wordt door de app gezet: wat er bij een klik op "Render HQ" gebeurt. */
  bijKnop?: () => void;
  id: string | null = null;
  aanvraag?: HqAanvraag;
  laatste: { id: string; herkomst: boolean; render: Cfg["render"] } | null = null;

  constructor(dom: HqDom, { bijKlaar }: { bijKlaar: (r: KlareRender) => void }) {
    this.dom = dom;
    this.bijKlaar = bijKlaar;
    dom.knop.addEventListener("click", () => this.bijKnop?.());
    dom.annuleer.addEventListener("click", () => this.annuleer());
  }

  zetFrame(b: number, h: number) { this.dom.kader.style.setProperty("--ar", `${b} / ${h}`); }

  bezig() { return this.id !== null; }

  melding(tekst: string, fout = false) {
    this.dom.status.textContent = tekst;
    this.dom.status.classList.toggle("fout", fout);
  }

  async start(aanvraag: HqAanvraag) {
    if (this.bezig()) return;
    this.aanvraag = aanvraag;
    this.laatste = null;
    this.dom.knop.disabled = true;
    this.dom.annuleer.disabled = false;
    this.dom.balk.value = 0;
    this.dom.links.hidden = true;
    this.melding("Aanvraag verstuurd...");
    try {
      const { id } = await startRender(aanvraag.config, aanvraag.opties, aanvraag.herkomst);
      this.id = id;
    } catch (e) {
      this.melding(`Render niet gestart: ${(e as Error).message}`, true);
      this.reset();
      return;
    }
    this.volg(this.id!);
  }

  volg(id: string) {
    let klaar = false;
    const verwerk = (m: RenderBericht) => {
      if (m.png_base64) this.dom.img.src = "data:image/png;base64," + m.png_base64;
      this.dom.img.hidden = false;
      this.dom.leeg.hidden = true;
      const v = m.voortgang;
      if (v) {
        this.dom.balk.max = v.max_spp;
        this.dom.balk.value = v.spp;
        const ruis = v.ruis == null ? "ruis nog onbekend" : `ruis ${(v.ruis * 100).toFixed(1)} %`;
        this.melding(`${m.status}: ${v.spp} / ${v.max_spp} samples, ${ruis}, ${v.tijd_s.toFixed(1)} s`);
      } else this.melding(m.status === "wachtend" ? "In de wachtrij..." : m.status);
      if (EIND.includes(m.status) && !klaar) { klaar = true; this.eind(m); }
    };
    const poll = async () => { // terugval als de socket wegvalt zonder eindstatus
      while (!klaar) {
        await new Promise((r) => setTimeout(r, 1000));
        try { verwerk(await renderStatus(id)); } catch { this.melding("Verbinding met de server weg", true); return; }
      }
    };
    volgRender(id, verwerk, () => { if (!klaar) poll(); });
  }

  async eind(m: RenderBericht) {
    const id = this.id!;
    if (m.status === "klaar" && m.resultaat && this.aanvraag) {
      const r = m.resultaat;
      const aanvraag = this.aanvraag;
      this.laatste = { id, herkomst: !!aanvraag.herkomst, render: aanvraag.config.render };
      // eerst de render in de geschiedenis, dan pas "Klaar": wie op die melding wacht, vindt het resultaat er dan ook
      try {
        const blob = await (await fetch(resultaatUrl(id, "png"))).blob();
        this.bijKlaar({ id, blob, resultaat: r, aanvraag, herkomst: !!aanvraag.herkomst });
      } catch { /* de afbeelding blijft in het paneel staan */ }
      this.melding(`Klaar: ${r.spp} samples, ruis ${r.ruis == null ? "?" : (r.ruis * 100).toFixed(1) + " %"}, ${r.tijd_s.toFixed(1)} s` +
        (r.uit_cache ? " (uit cache)" : "") + `, reden: ${r.reden}`);
      this.dom.balk.value = this.dom.balk.max;
      this.dom.png.href = resultaatUrl(id, "png");
      this.dom.exr.href = resultaatUrl(id, "exr");
      this.dom.links.hidden = false;
    } else if (m.status === "geannuleerd") this.melding("Geannuleerd (het tussenbeeld blijft staan)");
    else this.melding(`Fout: ${m.fout}`, true);
    this.reset();
  }

  reset() {
    this.id = null;
    this.dom.knop.disabled = false;
    this.dom.annuleer.disabled = true;
  }

  async annuleer() {
    if (!this.id) return;
    this.dom.annuleer.disabled = true;
    try { await annuleerRender(this.id); } catch (e) { this.melding(`Annuleren mislukt: ${(e as Error).message}`, true); }
  }
}
