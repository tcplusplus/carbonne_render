// HQ-paneel: start een Mitsuba-render via de backend en toont het beeld progressief (WebSocket).
import { annuleerRender, renderStatus, resultaatUrl, startRender, volgRender } from "./api.js";

const EIND = ["klaar", "fout", "geannuleerd"];

export class HQ {
  constructor(dom, { bijKlaar }) {
    this.dom = dom;
    this.bijKlaar = bijKlaar;
    this.id = null;
    dom.knop.addEventListener("click", () => this.bijKnop?.());
    dom.annuleer.addEventListener("click", () => this.annuleer());
  }

  zetFrame(b, h) { this.dom.kader.style.setProperty("--ar", `${b} / ${h}`); }

  bezig() { return this.id !== null; }

  melding(tekst, fout = false) {
    this.dom.status.textContent = tekst;
    this.dom.status.classList.toggle("fout", fout);
  }

  async start(aanvraag) {
    if (this.bezig()) return;
    this.aanvraag = aanvraag;
    this.dom.knop.disabled = true;
    this.dom.annuleer.disabled = false;
    this.dom.balk.value = 0;
    this.dom.links.hidden = true;
    this.melding("Aanvraag verstuurd...");
    try {
      const { id } = await startRender(aanvraag.config, aanvraag.opties);
      this.id = id;
    } catch (e) {
      this.melding(`Render niet gestart: ${e.message}`, true);
      this.reset();
      return;
    }
    this.volg(this.id);
  }

  volg(id) {
    let klaar = false;
    const verwerk = (m) => {
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

  async eind(m) {
    const id = this.id;
    if (m.status === "klaar") {
      const r = m.resultaat;
      this.melding(`Klaar: ${r.spp} samples, ruis ${r.ruis == null ? "?" : (r.ruis * 100).toFixed(1) + " %"}, ${r.tijd_s.toFixed(1)} s` +
        (r.uit_cache ? " (uit cache)" : "") + `, reden: ${r.reden}`);
      this.dom.balk.value = this.dom.balk.max;
      this.dom.png.href = resultaatUrl(id, "png");
      this.dom.exr.href = resultaatUrl(id, "exr");
      this.dom.links.hidden = false;
      try {
        const blob = await (await fetch(resultaatUrl(id, "png"))).blob();
        this.bijKlaar({ id, blob, resultaat: r, aanvraag: this.aanvraag });
      } catch { /* de afbeelding blijft in het paneel staan */ }
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
    try { await annuleerRender(this.id); } catch (e) { this.melding(`Annuleren mislukt: ${e.message}`, true); }
  }
}
