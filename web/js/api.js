// Dunne laag om de backend-API (src/carbonne/server/app.py).
import { detailNaarTekst } from "./fout.js";

async function j(url, opt) {
  const r = await fetch(url, opt);
  if (!r.ok) {
    let t = r.statusText, d = null;
    try {
      d = (await r.json()).detail;
      t = typeof d === "string" ? d : detailNaarTekst(d);
    } catch { /* geen JSON */ }
    throw Object.assign(new Error(r.status === 422 ? t : `${r.status}: ${t}`), { status: r.status, detail: d });
  }
  return r.json();
}
const post = (url, body) => j(url, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });

export const presets = () => j("/api/presets");
export const schema = () => j("/api/schema");
export const geometrie = (config) => post("/api/geometrie", config);
export const cameraPreset = (naam, d, h, pootHoogte = null) =>
  j(`/api/camera/${naam}?diameter=${d}&hoogte=${h}${pootHoogte == null ? "" : `&poot_hoogte=${pootHoogte}`}`);
export const startRender = (config, opties, herkomst = false) => post("/api/render", { config, opties, herkomst });
export const renderStatus = (id) => j(`/api/render/${id}`);
export const annuleerRender = (id) => j(`/api/render/${id}`, { method: "DELETE" });
export const configsLijst = () => j("/api/configs");
export const configLees = (naam) => j(`/api/configs/${encodeURIComponent(naam)}`);
export const configOpslaan = (naam, config) => post("/api/configs", { naam, config });
export const hdriUrl = (omgeving) => `/api/hdri/${omgeving}`;
export const resultaatUrl = (id, soort = "png") => `/api/render/${id}/result.${soort}`;

/** WebSocket met momentopnamen; `bijBericht(m)`, `bijSluiten()`. Geeft {sluit}. */
export function volgRender(id, bijBericht, bijSluiten) {
  const ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/api/render/${id}`);
  ws.onmessage = (e) => bijBericht(JSON.parse(e.data));
  ws.onclose = () => bijSluiten();
  return { sluit: () => ws.close() };
}

/** Herkomst van de kleur in een punt `{x, y, r}` of rechthoek `{x0, y0, x1, y1}` (pixels van het resultaatbeeld). */
export const herkomst = (id, g) => j(`/api/render/${id}/herkomst?` + new URLSearchParams(Object.entries(g).map(([k, v]) => [k, String(v)])));

export const reeksParameters = () => j("/api/reeks/parameters");
export const startReeks = (aanvraag) => post("/api/reeks", aanvraag);
export const reeksStatus = (id) => j(`/api/reeks/${id}`);
export const annuleerReeks = (id) => j(`/api/reeks/${id}`, { method: "DELETE" });

/** WebSocket van een reeks; `bijBericht(m)` bij elke wijziging, `bijSluiten()` aan het eind. */
export function volgReeks(id, bijBericht, bijSluiten) {
  const ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/api/reeks/${id}`);
  ws.onmessage = (e) => bijBericht(JSON.parse(e.data));
  ws.onclose = () => bijSluiten();
  return { sluit: () => ws.close() };
}

// verven (T19)
export const verfSchema = () => j("/api/verven/schema");
export const verfVertaal = (e) => post("/api/verven/vertaal", e);
export const verfVraag = (merk, product, kleur) => j("/api/verven/chatgpt-vraag?" + new URLSearchParams({ merk, product, kleur }));
export const verfUitTekst = (tekst) => post("/api/verven/uit-tekst", { tekst });
export const verfLijst = () => j("/api/verven");
export const verfLees = (slug) => j(`/api/verven/${encodeURIComponent(slug)}`);
export const verfBewaar = (e, overschrijf = false) => post(`/api/verven?overschrijf=${overschrijf ? 1 : 0}`, e);
export const verfVerwijder = (slug) => j(`/api/verven/${encodeURIComponent(slug)}`, { method: "DELETE" });
