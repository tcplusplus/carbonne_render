// Standaardwaarden en vertaling van de UI-staat naar de aanvraag voor de backend.
import { veldGrenzen } from "./schema.js";

export const standaardConfig = () => ({
  diameter: 0.35,
  hoogte: 0.04,
  segmenten: 128,
  epoxy: { cauchy_a: 1.517, cauchy_b: 0.0045, absorptie_nm: [400, 700], absorptie_per_m: [0, 0] },
  zijkant: { type: "bare" },
  onderkant: { type: "bare" },
  layers: [],
  poten: null,
  scene: { omgeving: "woonkamer", camera_preset: "kamer", spot: false,
           camera: { positie: [0, 0.55, 0.62], doel: [0, 0.02, 0], fov: 40 } },
  render: { breedte: 960, hoogte: 540, spp: 64, max_depth: 24 },
});

export const standaardOpties = () => ({ kwaliteit: "normaal", ev: 0 });

// kwaliteit -> RenderOpties (zie render/pipeline.py): doel-ruis en bovengrens aan samples
export const KWALITEIT = {
  concept: { naam: "Concept (snel, ruiziger)", max_spp: 64, ruisdrempel: 0.05 },
  normaal: { naam: "Normaal", max_spp: 512, ruisdrempel: 0.02 },
  hoog: { naam: "Hoog", max_spp: 2048, ruisdrempel: 0.01 },
  maximaal: { naam: "Maximaal (langzaam)", max_spp: 4096, ruisdrempel: 0.005 },
};

export const RESOLUTIES = [[640, 360], [960, 540], [1280, 720], [1920, 1080]];

/** De bereiken van de invoervelden in het paneel (UI-eenheden van de config: m, mm, aantal). `schema` wijst de
 * velden in GET /api/schema aan waarbinnen ze moeten blijven (afgedwongen door tests/test_t27.py). */
export const LIMIETEN = {
  diameter: { min: 0.2, max: 0.7, schema: [["TableConfig", "diameter"]] },
  hoogte: { min: 0.02, max: 0.06, schema: [["TableConfig", "hoogte"]] },
  laagHoogte: { min: 0.004, max: 0.058, schema: [["Layer", "height_m"]] },
  seed: { min: 0, max: 999, schema: [["Layer", "seed"]] },
  aantal: { min: 1, max: 60, schema: [["WoodSlice", "count"], ["Flower", "count"]] },
  straal: { min: 2, max: 40, schema: [["WoodSlice", "radius_mm"], ["Flower", "radius_mm"]] },
  bloemblaadjes: { min: 1, max: 24, schema: [["Flower", "petals"]] },
  ruwheid: { min: 0, max: 1, naarNull: true, schema: [["Paint", "roughness"], ["PlateBelow", "roughness"]] },
  lakRuwheid: { min: 0.01, max: 1, schema: [["MatteClearCoat", "roughness"]] },
  spleet: { min: 0.01, max: 5, schema: [["PlateBelow", "gap_mm"]] },
  dekking: { min: 0, max: 1, schema: [["Paint", "dekking"]] },
  verflagen: { min: 1, max: 8, schema: [["PaintStack", "lagen"]] }, // aantal lagen in een stapel
  // T26: poten. De UI-grenzen zijn zo gekozen dat elke combinatie past in het kleinste blok (diameter 0,2 m): 6 vierkante
  // poten van 30 mm op 40 mm van de rand raken elkaar niet (zie Legs.poten_overlappen en tests/test_t26.py).
  potenAantal: { min: 3, max: 6, schema: [["Legs", "aantal"]] },
  potenAfmeting: { min: 6, max: 30, schema: [["Legs", "afmeting_mm"]] },
  potenRand: { min: 0, max: 40, schema: [["Legs", "rand_mm"]] },
  potenHoogte: { min: 0.05, max: 0.8, schema: [["Legs", "hoogte_m"]] },
};
export const POTEN_VORMEN = [["rond", "rond"], ["vierkant", "vierkant"]];
export const POTEN_METALEN = [["geborsteld", "geborsteld aluminium"], ["gepoetst", "gepoetst chroom"], ["zwart", "zwart gepoederlakt"]];
/** Standaardpoten: vier ronde, geborstelde poten (zelfde als `Legs()` in core/config.py). */
export const nieuwePoten = (aantal = 4) => ({ aantal, vorm: "rond", afmeting_mm: 25, rand_mm: 30, hoogte_m: 0.41, metaal: "geborsteld" });
/** Soorten verf uit het schema (GET /api/schema); gevuld door `leidLimietenAf`. Leeg = nog niet geladen. */
export const ENUMS = { verfsoort: null, candyBasis: null };
export const VERFSOORTEN = [["matte", "mat"], ["glossy", "glanzend"], ["metallic", "metallic"], ["candy", "candy"]];
export const CANDY_BASIS = [["metallic", "metallic"], ["white", "wit"]];
/** Beperk een lijst keuzes tot wat het schema toestaat (zonder schema: alles). */
export const toegestaan = (keuzes, enumLijst) => (enumLijst ? keuzes.filter(([w]) => enumLijst.includes(w)) : keuzes);

/** Het schema is leidend: elk UI-bereik wordt afgekapt op wat het schema toestaat (de UI mag smaller zijn, nooit breder),
 * en keuzelijsten volgen het enum uit het schema. Aanroepen na het laden van GET /api/schema, vóór het paneel bouwt. */
export function leidLimietenAf(schema) {
  for (const l of Object.values(LIMIETEN)) {
    for (const [model, veld] of l.schema) {
      const g = veldGrenzen(schema, model, veld);
      if (g.min !== undefined && !(g.exclusiefMin && l.naarNull) && l.min < g.min) l.min = g.min;
      if (g.max !== undefined && l.max > g.max) l.max = g.max;
    }
  }
  ENUMS.verfsoort = veldGrenzen(schema, "Paint", "kind").enum ?? null;
  ENUMS.candyBasis = veldGrenzen(schema, "Paint", "candy_base").enum ?? null;
}

/** Marge (m) tussen een gietlaag en boven- of onderkant van het blok: ruim genoeg voor een houtschijfje (3 mm dik) en een gewone bloem. */
export const LAAG_MARGE = 0.004;

const klem = (w, l) => Math.min(Math.max(w, l.min), l.max);
/** Toegestane hoogte van een laag in een blok van `blokHoogte` m. */
const rond = (x) => Math.round(x * 1e6) / 1e6; // 0,04 - 0,004 geeft anders 0,036000000000000004
export const laagBereik = (blokHoogte) => ({ min: LIMIETEN.laagHoogte.min, max: rond(Math.max(LIMIETEN.laagHoogte.min, Math.min(LIMIETEN.laagHoogte.max, blokHoogte - LAAG_MARGE))) });

/** Houd een (bewaarde of geladen) config binnen de bereiken die de backend aanvaardt. Geeft true als er iets veranderde. */
export function begrens(cfg) {
  let veranderd = false;
  const zet = (o, k, l) => { if (typeof o[k] === "number") { const w = klem(o[k], l); if (w !== o[k]) { o[k] = w; veranderd = true; } } };
  zet(cfg, "diameter", LIMIETEN.diameter);
  zet(cfg, "hoogte", LIMIETEN.hoogte);
  for (const laag of cfg.layers ?? []) {
    zet(laag, "height_m", laagBereik(cfg.hoogte));
    for (const it of laag.items ?? []) {
      zet(it, "count", LIMIETEN.aantal);
      if (typeof it.count === "number" && !Number.isInteger(it.count)) { it.count = Math.round(it.count); veranderd = true; }
      if (Array.isArray(it.radius_mm)) it.radius_mm.forEach((_, i) => zet(it.radius_mm, i, LIMIETEN.straal));
      if (it.type === "flower") zet(it, "petals", LIMIETEN.bloemblaadjes);
    }
  }
  if (cfg.poten) {
    zet(cfg.poten, "aantal", LIMIETEN.potenAantal);
    if (!Number.isInteger(cfg.poten.aantal)) { cfg.poten.aantal = Math.round(cfg.poten.aantal); veranderd = true; }
    zet(cfg.poten, "afmeting_mm", LIMIETEN.potenAfmeting);
    zet(cfg.poten, "rand_mm", LIMIETEN.potenRand);
    zet(cfg.poten, "hoogte_m", LIMIETEN.potenHoogte);
  }
  return veranderd;
}

export function nieuweAfwerking(type, vorige = {}, onderkant = false) {
  const kleur = vorige.color ?? "#b22222";
  switch (type) {
    case "paint": return { type, color: kleur, kind: vorige.kind ?? "glossy", roughness: null, candy_base: "metallic" };
    case "paintstack": return { type, lagen: vorige.type === "paintstack" ? vorige.lagen
      : [{ type: "paint", color: kleur, kind: "matte", roughness: null, candy_base: "metallic", dekking: 1 }] };
    case "clearcoat": return { type, roughness: 0.3 };
    case "plate": return { type, color: kleur, gap_mm: 0.1, kind: vorige.kind ?? "matte", roughness: null, candy_base: "metallic" };
    default: return { type: "bare" };
  }
}

export function nieuwItem(type) {
  return type === "flower"
    ? { type, count: 6, color: [0.9, 0.3, 0.45], petals: 6, radius_mm: [8, 12], cup_mm: 2.5, tilt_deg: 15, translucency: 0.4 }
    : { type: "wood", count: 8, color: [0.45, 0.28, 0.13], radius_mm: [8, 14], thickness_mm: 3, irregularity: 0.12 };
}
/** Nieuwe gietlaag halverwege een blok van `blokHoogte` m (op 0,5 mm afgerond, binnen de toegestane hoogte). */
export function nieuweLaag(blokHoogte) {
  const b = laagBereik(blokHoogte);
  const hoogte = Math.min(Math.max(Math.round((blokHoogte / 2) * 2000) / 2000, b.min), b.max);
  return { height_m: hoogte, items: [nieuwItem("wood")], seed: 0, edge_margin_mm: 3 };
}

/** De aanvraag voor POST /api/render: de huidige previewcamera gaat mee; presetnaam vervalt. */
export function hqAanvraag(cfg, opties, camera, herkomst = false) {
  const config = structuredClone(cfg);
  config.scene.camera = camera;
  config.scene.camera_preset = null;
  const k = KWALITEIT[opties.kwaliteit];
  return { config, herkomst, opties: { ev: opties.ev, max_spp: k.max_spp, ruisdrempel: k.ruisdrempel, spp_per_pass: 16 } };
}

/** Een geladen config bevat lineaire kleurdrietallen voor verf; de UI bewerkt ze als hex. */
export function normaliseerGeladen(cfg, kleurNaarHex) {
  for (const f of [cfg.zijkant, cfg.onderkant, ...(cfg.zijkant.lagen ?? []), ...(cfg.onderkant.lagen ?? [])])
    if (f.color && Array.isArray(f.color)) f.color = kleurNaarHex(f.color);
  return cfg;
}
