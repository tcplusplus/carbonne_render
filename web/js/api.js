// Dunne laag om de backend-API (src/carbonne/server/app.py).
async function j(url, opt) {
  const r = await fetch(url, opt);
  if (!r.ok) {
    let t = r.statusText;
    try {
      const d = (await r.json()).detail;
      t = typeof d === "string" ? d : JSON.stringify(d);
    } catch { /* geen JSON */ }
    throw new Error(`${r.status}: ${t}`);
  }
  return r.json();
}
const post = (url, body) => j(url, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });

export const presets = () => j("/api/presets");
export const geometrie = (config) => post("/api/geometrie", config);
export const cameraPreset = (naam, d, h) => j(`/api/camera/${naam}?diameter=${d}&hoogte=${h}`);
export const startRender = (config, opties) => post("/api/render", { config, opties });
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
