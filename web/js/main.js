import * as api from "./api.js";
import { HQ } from "./hq.js";
import { lineairNaarHex } from "./kleur.js";
import { Paneel } from "./paneel.js";
import { Preview } from "./preview.js";
import { HerkomstPaneel } from "./herkomst.js";
import { Reeks } from "./reeks.js";
import { koppelSelectie, zetMarkering } from "./selectie.js";
import { hqAanvraag, normaliseerGeladen, standaardConfig, standaardOpties } from "./staat.js";
import { Vergelijk } from "./vergelijk.js";
import { VerfPaneel } from "./verf.js";

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
  hq.bijKnop = () => hq.start(hqAanvraag(cfg, opties, preview.getCamera(), $("hq-herkomst").checked));
  hq.zetFrame(cfg.render.breedte, cfg.render.hoogte);

  // --- herkomst en reeks: een gekozen plek (fracties van het beeld) hoort bij beide ---
  const herkomstPaneel = new HerkomstPaneel($("herkomst"));
  const reeks = new Reeks($("reeks"), {
    haalConfig: () => hqAanvraag(cfg, opties, preview.getCamera()).config, haalEv: () => opties.ev,
    ral, bijLaad: (c) => laad(c),
  });
  let plek = null;
  const kies = (p) => { plek = p; zetMarkering($("hq-kader"), p); vergelijk.markeer(p); reeks.zetPlek(p); };
  const bron = (label, id, r) => ({ label, id, breedte: r.breedte, hoogte: r.hoogte });
  koppelSelectie($("hq-kader"), (p) => {
    kies(p);
    const l = hq.laatste;
    herkomstPaneel.toon(l?.herkomst && !hq.bezig() ? [bron("HQ", l.id, l.render)] : [], p);
  }, (e) => (e.target === $("hq-beeld") && !$("hq-beeld").hidden ? $("hq-beeld").getBoundingClientRect() : null));
  koppelSelectie($("vergelijk-beeld"), (p) => {
    kies(p);
    const { a, b } = vergelijk;
    herkomstPaneel.toon([["A", a], ["B", b]].filter(([, it]) => it?.herkomst).map(([t, it]) => bron(`${t} ${it.label}`, it.id, it.cfg.render)), p);
  }, (e) => (e.target.tagName === "IMG" ? e.target.getBoundingClientRect() : null));

  // --- verven: bibliotheek en formulier (T20) ---
  const verfPaneel = new VerfPaneel($("verven"), { bijLijst: (lijst) => paneel.zetVerven(lijst), meld });
  await verfPaneel.ververs().catch(() => {});

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

  window.carbonne = { cfg: () => cfg, preview, hq, vergelijk, laad, ververs, reeks, herkomstPaneel, verfPaneel, plek: () => plek };
  document.body.dataset.app = "klaar";
}

start().catch((e) => { document.getElementById("meldingen").textContent = `Opstarten mislukt: ${e.message}`; console.error(e); });
