// Standaardwaarden en vertaling van de UI-staat naar de aanvraag voor de backend.
import { veldGrenzen } from "./schema.ts";
import type { SchemaKnoop } from "./schema.ts";
import type { EpoxyMaterial, Flower, Layer, Legs, Paint, SceneConfig, TableConfig, WoodSlice } from "./types/config.ts";

/** Alle velden verplicht (diep): zo ziet de UI een volledige config; de schema-types maken ze optioneel omdat ze een standaard hebben. */
type Vol<T> = T extends readonly unknown[] ? { [K in keyof T]: Vol<T[K]> } : T extends object ? { [K in keyof T]-?: Vol<T[K]> } : T;
/** De config zoals de UI hem bewerkt; afgeleid van het Pydantic-schema (`npm run types`). Kleuren mogen hex of een RGB-drietal zijn. */
type ScenePlus = "omgeving_radiantie" | "vloer_albedo" | "vloer_grootte" | "vloer_lijn_albedo" | "vloer_rastercel";
type EpoxyPlus = "scattering_coeff" | "scattering_g";
export type Cfg = Omit<Vol<TableConfig>, "epoxy" | "scene" | "top_roughness"> & Pick<TableConfig, "top_roughness"> & {
  // de velden die de UI niet zet blijven optioneel: de backend vult de standaardwaarde in
  epoxy: Omit<Vol<EpoxyMaterial>, EpoxyPlus> & Pick<EpoxyMaterial, EpoxyPlus>;
  scene: Omit<Vol<SceneConfig>, ScenePlus> & Pick<SceneConfig, ScenePlus>;
};
/** Kleur in een config: '#rrggbb' of tekst ('RAL 9005') uit de UI, of een lineair RGB-drietal uit de backend. */
export type CfgKleur = string | [number, number, number];
export type Afwerking = Cfg["zijkant"] | Cfg["onderkant"];
export type VerfLaag = Vol<Paint>;
export type Laag = Vol<Layer>;
export type Item = Vol<WoodSlice> | Vol<Flower>;
export type Poten = Vol<Legs>;
export type Camera = Cfg["scene"]["camera"];
export type Kwaliteit = "concept" | "normaal" | "hoog" | "maximaal";
export interface Opties { kwaliteit: Kwaliteit; ev: number }
export interface RenderOpties { ev: number; max_spp: number; ruisdrempel: number; spp_per_pass: number }
export interface HqAanvraag { config: Cfg; herkomst: boolean; opties: RenderOpties }
type Keuzes = readonly (readonly [string, string])[];

export const standaardConfig = (): Cfg => ({
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

export const standaardOpties = (): Opties => ({ kwaliteit: "normaal", ev: 0 });

// kwaliteit -> RenderOpties (zie render/pipeline.py): doel-ruis en bovengrens aan samples
export const KWALITEIT: Record<Kwaliteit, { naam: string; max_spp: number; ruisdrempel: number }> = {
  concept: { naam: "Concept (snel, ruiziger)", max_spp: 64, ruisdrempel: 0.05 },
  normaal: { naam: "Normaal", max_spp: 512, ruisdrempel: 0.02 },
  hoog: { naam: "Hoog", max_spp: 2048, ruisdrempel: 0.01 },
  maximaal: { naam: "Maximaal (langzaam)", max_spp: 4096, ruisdrempel: 0.005 },
};

export const RESOLUTIES: readonly (readonly [number, number])[] = [[640, 360], [960, 540], [1280, 720], [1920, 1080]];

/** De bereiken van de invoervelden in het paneel (UI-eenheden van de config: m, mm, aantal). `schema` wijst de
 * velden in GET /api/schema aan waarbinnen ze moeten blijven (afgedwongen door tests/test_t27.py). */
export interface Limiet { min: number; max: number; naarNull?: boolean; schema: readonly (readonly [string, string])[] }
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
} satisfies Record<string, Limiet>;
export const POTEN_VORMEN: Keuzes = [["rond", "rond"], ["vierkant", "vierkant"]];
export const POTEN_METALEN: Keuzes = [["geborsteld", "geborsteld aluminium"], ["gepoetst", "gepoetst chroom"], ["zwart", "zwart gepoederlakt"]];
/** Standaardpoten: vier ronde, geborstelde poten (zelfde als `Legs()` in core/config.py). */
export const nieuwePoten = (aantal = 4): Poten => ({ aantal, vorm: "rond", afmeting_mm: 25, rand_mm: 30, hoogte_m: 0.41, metaal: "geborsteld" });
/** Soorten verf uit het schema (GET /api/schema); gevuld door `leidLimietenAf`. Leeg = nog niet geladen. */
export const ENUMS: { verfsoort: unknown[] | null; candyBasis: unknown[] | null } = { verfsoort: null, candyBasis: null };
export const VERFSOORTEN: Keuzes = [["matte", "mat"], ["glossy", "glanzend"], ["metallic", "metallic"], ["candy", "candy"]];
export const CANDY_BASIS: Keuzes = [["metallic", "metallic"], ["white", "wit"]];
/** Beperk een lijst keuzes tot wat het schema toestaat (zonder schema: alles). */
export const toegestaan = (keuzes: Keuzes, enumLijst: unknown[] | null): Keuzes => (enumLijst ? keuzes.filter(([w]) => enumLijst.includes(w)) : keuzes);

/** Het schema is leidend: elk UI-bereik wordt afgekapt op wat het schema toestaat (de UI mag smaller zijn, nooit breder),
 * en keuzelijsten volgen het enum uit het schema. Aanroepen na het laden van GET /api/schema, vóór het paneel bouwt. */
export function leidLimietenAf(schema: SchemaKnoop): void {
  for (const l of Object.values<Limiet>(LIMIETEN)) {
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

const klem = (w: number, l: { min: number; max: number }): number => Math.min(Math.max(w, l.min), l.max);
/** Toegestane hoogte van een laag in een blok van `blokHoogte` m. */
const rond = (x: number): number => Math.round(x * 1e6) / 1e6; // 0,04 - 0,004 geeft anders 0,036000000000000004
export const laagBereik = (blokHoogte: number): { min: number; max: number } => ({ min: LIMIETEN.laagHoogte.min, max: rond(Math.max(LIMIETEN.laagHoogte.min, Math.min(LIMIETEN.laagHoogte.max, blokHoogte - LAAG_MARGE))) });

/** Houd een (bewaarde of geladen) config binnen de bereiken die de backend aanvaardt. Geeft true als er iets veranderde. */
export function begrens(cfg: Cfg): boolean {
  let veranderd = false;
  const zet = <T extends object>(o: T, k: keyof T, l: { min: number; max: number }): void => {
    const nu = o[k];
    if (typeof nu === "number") { const w = klem(nu, l); if (w !== nu) { (o[k] as number) = w; veranderd = true; } }
  };
  zet(cfg, "diameter", LIMIETEN.diameter);
  zet(cfg, "hoogte", LIMIETEN.hoogte);
  for (const laag of cfg.layers ?? []) {
    zet(laag, "height_m", laagBereik(cfg.hoogte));
    for (const it of laag.items ?? []) {
      zet(it, "count", LIMIETEN.aantal);
      if (typeof it.count === "number" && !Number.isInteger(it.count)) { it.count = Math.round(it.count); veranderd = true; }
      if (Array.isArray(it.radius_mm)) it.radius_mm.forEach((_, i) => zet(it.radius_mm, i as 0 | 1, LIMIETEN.straal));
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

/** Wat `nieuweAfwerking` van de vorige afwerking overneemt (kleur, soort, lagen). */
export interface VorigeAfwerking { type?: string; color?: CfgKleur; kind?: string; lagen?: VerfLaag[] }

export function nieuweAfwerking(type: string, vorige: VorigeAfwerking = {}): Afwerking {
  const kleur = vorige.color ?? "#b22222";
  const soort = (vorige.kind ?? "glossy") as VerfLaag["kind"];
  const plaatSoort = (vorige.kind ?? "matte") as VerfLaag["kind"];
  switch (type) {
    case "paint": return { type, color: kleur, kind: soort, roughness: null, candy_base: "metallic", dekking: 1, bibliotheek_id: null };
    case "paintstack": return { type, lagen: vorige.type === "paintstack" && vorige.lagen ? vorige.lagen
      : [{ type: "paint", color: kleur, kind: "matte", roughness: null, candy_base: "metallic", dekking: 1, bibliotheek_id: null }] };
    case "clearcoat": return { type, roughness: 0.3 };
    case "plate": return { type, color: kleur, gap_mm: 0.1, kind: plaatSoort, roughness: null, candy_base: "metallic" };
    default: return { type: "bare" };
  }
}

export function nieuwItem(type: "wood"): Vol<WoodSlice>;
export function nieuwItem(type: "flower"): Vol<Flower>;
export function nieuwItem(type: string): Item;
export function nieuwItem(type: string): Item {
  return type === "flower"
    ? { type, count: 6, color: [0.9, 0.3, 0.45], petals: 6, radius_mm: [8, 12], cup_mm: 2.5, tilt_deg: 15, translucency: 0.4 }
    : { type: "wood", count: 8, color: [0.45, 0.28, 0.13], radius_mm: [8, 14], thickness_mm: 3, irregularity: 0.12 };
}
/** Nieuwe gietlaag halverwege een blok van `blokHoogte` m (op 0,5 mm afgerond, binnen de toegestane hoogte). */
export function nieuweLaag(blokHoogte: number): Laag {
  const b = laagBereik(blokHoogte);
  const hoogte = Math.min(Math.max(Math.round((blokHoogte / 2) * 2000) / 2000, b.min), b.max);
  return { height_m: hoogte, items: [nieuwItem("wood")], seed: 0, edge_margin_mm: 3 };
}

/** De aanvraag voor POST /api/render: de huidige previewcamera gaat mee; presetnaam vervalt. */
export function hqAanvraag(cfg: Cfg, opties: Opties, camera: Camera, herkomst = false): HqAanvraag {
  const config = structuredClone(cfg);
  config.scene.camera = camera;
  config.scene.camera_preset = null;
  const k = KWALITEIT[opties.kwaliteit];
  return { config, herkomst, opties: { ev: opties.ev, max_spp: k.max_spp, ruisdrempel: k.ruisdrempel, spp_per_pass: 16 } };
}

/** Een geladen config bevat lineaire kleurdrietallen voor verf; de UI bewerkt ze als hex. */
export function normaliseerGeladen(cfg: Cfg, kleurNaarHex: (c: readonly number[]) => string): Cfg {
  const lagen = (a: Afwerking): Afwerking[] => (a.type === "paintstack" ? a.lagen : []);
  for (const f of [cfg.zijkant, cfg.onderkant, ...lagen(cfg.zijkant), ...lagen(cfg.onderkant)])
    if ("color" in f && Array.isArray(f.color)) f.color = kleurNaarHex(f.color);
  return cfg;
}
