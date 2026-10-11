// Dunne laag om de backend-API (src/carbonne/server/app.py).
import { detailNaarTekst } from "./fout.ts";
import type { Cfg, RenderOpties } from "./staat.ts";
import type { SchemaKnoop } from "./schema.ts";
import type { CameraInstelling, Geometrie, Herkomst, HerkomstGebied, Presets, RenderBericht, ReeksAanvraag, ReeksParameter, ReeksStatus,
  VerfItem, VerfLijstItem, VerfVertaling } from "./types/api.ts";
import type { VerfEigenschappen } from "./types/verf.ts";

/** Fout van een API-aanroep: HTTP-status en het `detail` van het antwoord (tekst, object of Pydantic-lijst). */
export interface ApiFout extends Error { status: number; detail: unknown }

async function j<T>(url: string, opt?: RequestInit): Promise<T> {
  const r = await fetch(url, opt);
  if (!r.ok) {
    let t = r.statusText, d: unknown = null;
    try {
      d = ((await r.json()) as { detail?: unknown }).detail;
      t = typeof d === "string" ? d : detailNaarTekst(d);
    } catch { /* geen JSON */ }
    throw Object.assign(new Error(r.status === 422 ? t : `${r.status}: ${t}`), { status: r.status, detail: d }) satisfies ApiFout;
  }
  return r.json() as Promise<T>;
}
const post = <T>(url: string, body: unknown) => j<T>(url, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });

export const presets = () => j<Presets>("/api/presets");
export const schema = () => j<SchemaKnoop>("/api/schema");
export const geometrie = (config: Cfg) => post<Geometrie>("/api/geometrie", config);
export const cameraPreset = (naam: string, d: number, h: number, pootHoogte: number | null = null) =>
  j<CameraInstelling>(`/api/camera/${naam}?diameter=${d}&hoogte=${h}${pootHoogte == null ? "" : `&poot_hoogte=${pootHoogte}`}`);
export const startRender = (config: Cfg, opties: RenderOpties, herkomst = false) => post<{ id: string }>("/api/render", { config, opties, herkomst });
export const renderStatus = (id: string) => j<RenderBericht>(`/api/render/${id}`);
export const annuleerRender = (id: string) => j<unknown>(`/api/render/${id}`, { method: "DELETE" });
export const configsLijst = () => j<string[]>("/api/configs");
export const configLees = (naam: string) => j<Cfg>(`/api/configs/${encodeURIComponent(naam)}`);
export const configOpslaan = (naam: string, config: Cfg) => post<unknown>("/api/configs", { naam, config });
export const hdriUrl = (omgeving: string) => `/api/hdri/${omgeving}`;
export const resultaatUrl = (id: string, soort = "png") => `/api/render/${id}/result.${soort}`;

/** WebSocket met momentopnamen; `bijBericht(m)`, `bijSluiten()`. Geeft {sluit}. */
export function volgRender(id: string, bijBericht: (m: RenderBericht) => void, bijSluiten: () => void): { sluit: () => void } {
  const ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/api/render/${id}`);
  ws.onmessage = (e) => bijBericht(JSON.parse(e.data as string) as RenderBericht);
  ws.onclose = () => bijSluiten();
  return { sluit: () => ws.close() };
}

/** Herkomst van de kleur in een punt `{x, y, r}` of rechthoek `{x0, y0, x1, y1}` (pixels van het resultaatbeeld). */
export const herkomst = (id: string, g: HerkomstGebied) => j<Herkomst>(`/api/render/${id}/herkomst?` + new URLSearchParams(Object.entries(g).map(([k, v]) => [k, String(v)] as [string, string])));

export const reeksParameters = () => j<ReeksParameter[]>("/api/reeks/parameters");
export const startReeks = (aanvraag: ReeksAanvraag) => post<{ id: string }>("/api/reeks", aanvraag);
export const reeksStatus = (id: string) => j<ReeksStatus>(`/api/reeks/${id}`);
export const annuleerReeks = (id: string) => j<unknown>(`/api/reeks/${id}`, { method: "DELETE" });

/** WebSocket van een reeks; `bijBericht(m)` bij elke wijziging, `bijSluiten()` aan het eind. */
export function volgReeks(id: string, bijBericht: (m: ReeksStatus) => void, bijSluiten: () => void): { sluit: () => void } {
  const ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/api/reeks/${id}`);
  ws.onmessage = (e) => bijBericht(JSON.parse(e.data as string) as ReeksStatus);
  ws.onclose = () => bijSluiten();
  return { sluit: () => ws.close() };
}

// verven (T19)
export const verfSchema = () => j<SchemaKnoop>("/api/verven/schema");
export const verfVertaal = (e: Partial<VerfEigenschappen>) => post<VerfVertaling>("/api/verven/vertaal", e);
export const verfVraag = (merk: string, product: string, kleur: string) => j<{ vraag: string }>("/api/verven/chatgpt-vraag?" + new URLSearchParams({ merk, product, kleur }));
export const verfUitTekst = (tekst: string) => post<{ eigenschappen: VerfEigenschappen; vertaling: VerfVertaling }>("/api/verven/uit-tekst", { tekst });
export const verfLijst = () => j<VerfLijstItem[]>("/api/verven");
export const verfLees = (slug: string) => j<VerfItem>(`/api/verven/${encodeURIComponent(slug)}`);
export const verfBewaar = (e: Partial<VerfEigenschappen>, overschrijf = false) => post<{ slug: string }>(`/api/verven?overschrijf=${overschrijf ? 1 : 0}`, e);
export const verfVerwijder = (slug: string) => j<unknown>(`/api/verven/${encodeURIComponent(slug)}`, { method: "DELETE" });
