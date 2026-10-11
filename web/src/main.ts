import "../css/app.css";
import * as api from "./api.ts";
import { HQ } from "./hq.ts";
import { lineairNaarHex } from "./kleur.ts";
import { Paneel } from "./paneel.ts";
import type { Wijziging } from "./paneel.ts";
import { Preview } from "./preview.ts";
import { HerkomstPaneel } from "./herkomst.ts";
import { Reeks } from "./reeks.ts";
import { koppelSelectie, zetMarkering } from "./selectie.ts";
import type { Cfg, Opties } from "./staat.ts";
import type { SchemaKnoop } from "./schema.ts";
import type { Plek } from "./selectie.ts";
import type { KlareRender } from "./hq.ts";
import { begrens, hqAanvraag, leidLimietenAf, normaliseerGeladen, standaardConfig, standaardOpties } from "./staat.ts";
import { valideer } from "./schema.ts";
import { detailNaarTekst } from "./fout.ts";
import { Vergelijk } from "./vergelijk.ts";
import { VerfPaneel } from "./verf.ts";

/** Element met dit id; het type zegt wat index.html daar neerzet. */
const $ = <T extends HTMLElement = HTMLElement>(id: string): T => document.getElementById(id) as T;
const OPSLAG = "carbonne.laatste";

function bewaarLokaal(cfg: Cfg, opties: Opties) {
  try { localStorage.setItem(OPSLAG, JSON.stringify({ cfg, opties })); } catch { /* geen opslag */ }
}
function leesLokaal(): { cfg: Cfg; opties: Opties } | null {
  try { return JSON.parse(localStorage.getItem(OPSLAG) ?? "null"); } catch { return null; }
}

async function start() {
  const presets = await api.presets();
  const schema: SchemaKnoop | null = await api.schema().catch(() => null); // zonder schema valt de UI terug op de eigen bereiken en de backend-controle
  if (schema) leidLimietenAf(schema);
  /** Controle van de config tegen het schema vóór verzenden; geeft een leesbare tekst of null. */
  const schemaFouten = (config: Cfg): string | null => {
    const f = schema ? valideer(schema, config) : [];
    return f.length ? detailNaarTekst(f) : null;
  };
  const ral: Record<string, string> = Object.fromEntries(presets.ral.map((r) => [r.code, r.hex]));
  const bewaard = leesLokaal();
  let cfg: Cfg = bewaard?.cfg ?? standaardConfig();
  let opties: Opties = bewaard?.opties ?? standaardOpties();
  const meld = (t: string, fout = false) => { $("meldingen").textContent = t; $("meldingen").classList.toggle("fout", fout); };

  const preview = new Preview($("preview-kader"), { ral, presets });
  const hq = new HQ({ kader: $("hq-kader"), img: $("hq-beeld"), leeg: $("hq-leeg"), knop: $("hq-start"), annuleer: $("hq-annuleer"),
    balk: $("hq-balk"), status: $("hq-status"), links: $("hq-links"), png: $("hq-png"), exr: $("hq-exr") },
  { bijKlaar: (r: KlareRender) => vergelijk.voegToe(r) });
  const vergelijk = new Vergelijk({ lijst: $("geschiedenis"), beeld: $("vergelijk-beeld"), modus: $("vergelijk-modus"),
    schuif: $("vergelijk-schuif"), schuifrij: $("schuifrij"), verschil: $("verschil") },
  { bijTerugzetten: (c, o) => laad(c, { ...opties, ev: o.ev ?? 0 }) });

  const frame = () => { for (const k of [$("preview-kader"), $("hq-kader")]) k.style.setProperty("--ar", `${cfg.render.breedte} / ${cfg.render.hoogte}`); };
  let timer: ReturnType<typeof setTimeout> | undefined;
  const ververs = () => {
    clearTimeout(timer);
    timer = setTimeout(async () => {
      document.body.dataset.preview = "bezig";
      try {
        const fouten = schemaFouten(cfg);
        if (fouten) throw new Error(fouten);
        await preview.update(cfg);
        meld("");
      } catch (e) { meld(`Preview: ${(e as Error).message}`, true); }
      document.body.dataset.preview = "klaar";
    }, 120);
  };
  const zetCameraPreset = async (naam: string) => {
    try { preview.zetCamera(await api.cameraPreset(naam, cfg.diameter, cfg.hoogte, cfg.poten?.hoogte_m)); } catch (e) { meld((e as Error).message, true); }
  };

  const bijWijziging = (soort: Wijziging) => {
    bewaarLokaal(cfg, opties);
    if (soort === "frame") { frame(); preview.pasMaatAan(); hq.zetFrame(cfg.render.breedte, cfg.render.hoogte); }
    if (soort === "ev") preview.zetEv(opties.ev);
    if (["geometrie", "materiaal", "omgeving"].includes(soort)) ververs();
    if (soort === "geometrie" && cfg.scene.camera_preset) zetCameraPreset(cfg.scene.camera_preset);
  };
  const paneel = new Paneel($("paneel"), { cfg, opties, presets, ral, bijWijziging, bijCameraPreset: zetCameraPreset });
  preview.bijVrijeCamera = () => {
    if (cfg.scene.camera_preset) { cfg.scene.camera_preset = null; paneel.bouw(); }
  };

  async function laad(nieuw: Cfg, nieuweOpties: Opties = opties) {
    cfg = normaliseerGeladen(structuredClone(nieuw), (c) => lineairNaarHex(c));
    begrens(cfg); // een oude bewaarde of geladen config kan waarden buiten het huidige bereik hebben (zou een 422 geven)
    opties = { ...nieuweOpties };
    paneel.zet(cfg, opties);
    frame();
    preview.zetEv(opties.ev);
    if (cfg.scene.camera_preset) await zetCameraPreset(cfg.scene.camera_preset); else preview.zetCamera(cfg.scene.camera);
    ververs();
  }
  await laad(cfg, opties);

  // --- HQ ---
  hq.bijKnop = () => {
    const aanvraag = hqAanvraag(cfg, opties, preview.getCamera(), $<HTMLInputElement>("hq-herkomst").checked);
    const fouten = schemaFouten(aanvraag.config);
    if (fouten) hq.melding(`Render niet gestart: ${fouten}`, true); else hq.start(aanvraag);
  };
  hq.zetFrame(cfg.render.breedte, cfg.render.hoogte);

  // --- herkomst en reeks: een gekozen plek (fracties van het beeld) hoort bij beide ---
  const herkomstPaneel = new HerkomstPaneel($("herkomst"));
  const reeks = new Reeks($("reeks"), {
    haalConfig: () => hqAanvraag(cfg, opties, preview.getCamera()).config, haalEv: () => opties.ev,
    ral, bijLaad: (c) => laad(c),
  });
  let plek: Plek | null = null;
  const kies = (p: Plek) => { plek = p; zetMarkering($("hq-kader"), p); vergelijk.markeer(p); reeks.zetPlek(p); };
  const bron = (label: string, id: string, r: { breedte: number; hoogte: number }) => ({ label, id, breedte: r.breedte, hoogte: r.hoogte });
  koppelSelectie($("hq-kader"), (p) => {
    kies(p);
    const l = hq.laatste;
    herkomstPaneel.toon(l?.herkomst && !hq.bezig() ? [bron("HQ", l.id, l.render)] : [], p);
  }, (e) => (e.target === $("hq-beeld") && !$("hq-beeld").hidden ? $("hq-beeld").getBoundingClientRect() : null));
  koppelSelectie($("vergelijk-beeld"), (p) => {
    kies(p);
    const { a, b } = vergelijk;
    herkomstPaneel.toon(([["A", a], ["B", b]] as const).flatMap(([t, it]) => (it?.herkomst ? [bron(`${t} ${it.label}`, it.id, it.cfg.render)] : [])), p);
  }, (e) => ((e.target as HTMLElement).tagName === "IMG" ? (e.target as HTMLElement).getBoundingClientRect() : null));

  // --- verven: bibliotheek en formulier (T20) ---
  const verfPaneel = new VerfPaneel($("verven"), { bijLijst: (lijst) => paneel.zetVerven(lijst), meld });
  await verfPaneel.ververs().catch(() => {});

  // --- configs ---
  const vulLijst = async () => {
    const namen = await api.configsLijst();
    $<HTMLSelectElement>("config-lijst").replaceChildren(...namen.map((n) => Object.assign(document.createElement("option"), { value: n, textContent: n })));
  };
  await vulLijst().catch(() => {});
  $("config-opslaan").addEventListener("click", async () => {
    const naam = $<HTMLInputElement>("config-naam").value.trim();
    try {
      const c = structuredClone(cfg); c.scene.camera = preview.getCamera(); c.scene.camera_preset = null;
      await api.configOpslaan(naam, c);
      await vulLijst();
      meld(`Config "${naam}" opgeslagen.`);
    } catch (e) { meld(`Opslaan mislukt: ${(e as Error).message}`, true); }
  });
  $("config-laden").addEventListener("click", async () => {
    const naam = $<HTMLSelectElement>("config-lijst").value;
    if (!naam) return;
    try { await laad(await api.configLees(naam)); $<HTMLInputElement>("config-naam").value = naam; meld(`Config "${naam}" geladen.`); }
    catch (e) { meld(`Laden mislukt: ${(e as Error).message}`, true); }
  });

  (window as unknown as { carbonne: unknown }).carbonne = { schemaFouten, cfg: () => cfg, preview, hq, vergelijk, laad, ververs, reeks, herkomstPaneel, verfPaneel, plek: () => plek };
  document.body.dataset.app = "klaar";
}

start().catch((e: Error) => { $("meldingen").textContent = `Opstarten mislukt: ${e.message}`; console.error(e); });
