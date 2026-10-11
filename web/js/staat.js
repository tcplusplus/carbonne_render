// Standaardwaarden en vertaling van de UI-staat naar de aanvraag voor de backend.
export const standaardConfig = () => ({
  diameter: 0.35,
  hoogte: 0.04,
  segmenten: 128,
  epoxy: { cauchy_a: 1.517, cauchy_b: 0.0045, absorptie_nm: [400, 700], absorptie_per_m: [0, 0] },
  zijkant: { type: "bare" },
  onderkant: { type: "bare" },
  layers: [],
  scene: { omgeving: "woonkamer", camera_preset: "schuin30", spot: false,
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
export const nieuweLaag = (hoogte) => ({ height_m: Math.round(hoogte * 5) / 1000, items: [nieuwItem("wood")], seed: 0, edge_margin_mm: 3 });

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
