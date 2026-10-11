import * as api from "./api.js";
import { HQ } from "./hq.js";
import { lineairNaarHex } from "./kleur.js";
import { Paneel } from "./paneel.js";
import { Preview } from "./preview.js";
import { hqAanvraag, normaliseerGeladen, standaardConfig, standaardOpties } from "./staat.js";
import { Vergelijk } from "./vergelijk.js";

const $ = (id) => document.getElementById(id);
const OPSLAG = "carbonne.laatste";

function bewaarLokaal(cfg, opties) {
  try { localStorage.setItem(OPSLAG, JSON.stringify({ cfg, opties })); } catch { /* geen opslag */ }
}
function leesLokaal() {
  try { return JSON.parse(localStorage.getItem(OPSLAG)); } catch { return null; }
}

async function start() {
  const presets = await api.presets();
  const ral = Object.fromEntries(presets.ral.map((r) => [r.code, r.hex]));
  const bewaard = leesLokaal();
  let cfg = bewaard?.cfg ?? standaardConfig();
  let opties = bewaard?.opties ?? standaardOpties();
  const meld = (t, fout = false) => { $("meldingen").textContent = t; $("meldingen").classList.toggle("fout", fout); };

  const preview = new Preview($("preview-kader"), { ral, presets });
  const hq = new HQ({ kader: $("hq-kader"), img: $("hq-beeld"), leeg: $("hq-leeg"), knop: $("hq-start"), annuleer: $("hq-annuleer"),
    balk: $("hq-balk"), status: $("hq-status"), links: $("hq-links"), png: $("hq-png"), exr: $("hq-exr") },
  { bijKlaar: (r) => vergelijk.voegToe(r) });
  const vergelijk = new Vergelijk({ lijst: $("geschiedenis"), beeld: $("vergelijk-beeld"), modus: $("vergelijk-modus"),
    schuif: $("vergelijk-schuif"), schuifrij: $("schuifrij"), verschil: $("verschil") },
  { bijTerugzetten: (c, o) => laad(c, { ...opties, ev: o.ev ?? 0 }) });

  const frame = () => { for (const k of [$("preview-kader"), $("hq-kader")]) k.style.setProperty("--ar", `${cfg.render.breedte} / ${cfg.render.hoogte}`); };
  let timer = null;
  const ververs = () => {
    clearTimeout(timer);
    timer = setTimeout(async () => {
      document.body.dataset.preview = "bezig";
      try {
        await preview.update(cfg);
        meld("");
      } catch (e) { meld(`Preview: ${e.message}`, true); }
      document.body.dataset.preview = "klaar";
    }, 120);
  };
  const zetCameraPreset = async (naam) => {
    try { preview.zetCamera(await api.cameraPreset(naam, cfg.diameter, cfg.hoogte)); } catch (e) { meld(e.message, true); }
  };

  const bijWijziging = (soort) => {
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

  async function laad(nieuw, nieuweOpties = opties) {
    cfg = normaliseerGeladen(structuredClone(nieuw), (c) => lineairNaarHex(c));
    opties = { ...nieuweOpties };
    paneel.zet(cfg, opties);
    frame();
    preview.zetEv(opties.ev);
    if (cfg.scene.camera_preset) await zetCameraPreset(cfg.scene.camera_preset); else preview.zetCamera(cfg.scene.camera);
    ververs();
  }
  await laad(cfg, opties);

  // --- HQ ---
  hq.bijKnop = () => hq.start(hqAanvraag(cfg, opties, preview.getCamera()));
  hq.zetFrame(cfg.render.breedte, cfg.render.hoogte);

  // --- configs ---
  const vulLijst = async () => {
    const namen = await api.configsLijst();
    $("config-lijst").replaceChildren(...namen.map((n) => Object.assign(document.createElement("option"), { value: n, textContent: n })));
  };
  await vulLijst().catch(() => {});
  $("config-opslaan").addEventListener("click", async () => {
    const naam = $("config-naam").value.trim();
    try {
      const c = structuredClone(cfg); c.scene.camera = preview.getCamera(); c.scene.camera_preset = null;
      await api.configOpslaan(naam, c);
      await vulLijst();
      meld(`Config "${naam}" opgeslagen.`);
    } catch (e) { meld(`Opslaan mislukt: ${e.message}`, true); }
  });
  $("config-laden").addEventListener("click", async () => {
    const naam = $("config-lijst").value;
    if (!naam) return;
    try { await laad(await api.configLees(naam)); $("config-naam").value = naam; meld(`Config "${naam}" geladen.`); }
    catch (e) { meld(`Laden mislukt: ${e.message}`, true); }
  });

  window.carbonne = { cfg: () => cfg, preview, hq, vergelijk, laad, ververs };
  document.body.dataset.app = "klaar";
}

start().catch((e) => { document.getElementById("meldingen").textContent = `Opstarten mislukt: ${e.message}`; console.error(e); });
