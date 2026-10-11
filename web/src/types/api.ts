// Vorm van de antwoorden van de backend (src/carbonne/server/app.py). De config zelf komt uit het gegenereerde
// ./config.ts; dit zijn de antwoorden die geen Pydantic-schema in /api/schema hebben.
import type { VerfEigenschappen } from "./verf.ts";

export interface Ral { code: string; hex: string; naam: string }
export interface OmgevingPreset {
  naam: string; omschrijving: string; vloer: { albedo: [number, number, number] }; rotatie: number; schaal: number;
  spot?: { hoogte: number; intensiteit: number; kegelhoek: number } | null;
}
export interface Presets { ral: Ral[]; omgevingen: OmgevingPreset[]; camera_presets: string[]; tafel_hoogte: number }

export interface CameraInstelling { positie: [number, number, number]; doel: [number, number, number]; fov: number }

export interface MeshData { posities: number[]; normalen: number[]; indices: number[] }
export interface InhoudMesh extends MeshData { soort: "wood" | "flower"; kleur?: number[] | null }
export interface Geometrie {
  diameter: number; vlakken: { boven: MeshData; mantel: MeshData; onder: MeshData };
  inhoud: InhoudMesh[]; poten?: MeshData[]; vloer_y?: number | null;
}

export type RenderStatus = "wachtend" | "bezig" | "klaar" | "fout" | "geannuleerd";
export interface RenderResultaat { spp: number; ruis: number | null; tijd_s: number; uit_cache: boolean; reden: string }
export interface RenderBericht {
  status: RenderStatus; png_base64?: string;
  voortgang?: { spp: number; max_spp: number; ruis: number | null; tijd_s: number } | null;
  resultaat?: RenderResultaat; fout?: string;
}

export interface HerkomstCategorie { naam: string; aandeel_pct: number; hex: string; hex_per_pad: string }
export interface Herkomst {
  hex: string; lab: [number, number, number]; categorieen: HerkomstCategorie[];
  kerngetallen?: { n_tir: number; n_fresnel: number; aandeel_tir_pct: number; weg_epoxy_cm: number } | null;
}
/** Plek op het resultaatbeeld, in pixels: punt `{x, y, r}` of rechthoek. */
export type HerkomstGebied = { x: number; y: number; r: number } | { x0: number; y0: number; x1: number; y1: number };

export interface ReeksParameter {
  pad: string; omschrijving: string; type: string; voorbeelden: any[]; min?: number | null; max?: number | null; eenheid?: string | null; patroon?: boolean;
}
export interface ReeksMeting {
  waarde: unknown; label: string; lch: [number, number, number]; hex: string; de2000: number; binnen_ruis: boolean;
  herkomst: { categorieen: HerkomstCategorie[] };
}
export interface ReeksStatus {
  status: RenderStatus; metingen_klaar?: number; voortgang?: { klaar: number; label?: string } | null; fout?: string;
  resultaat?: { parameter: string; metingen: ReeksMeting[] }; urls: { beelden: string[] };
}
export interface ReeksAanvraag {
  config: unknown; parameter: string; waarden: unknown[]; gebied: number[]; straal: number; breedte: number; spp: number; ev: number;
}

export interface VerfLijstItem { slug: string; naam: string; staal: string }
export interface VerfVertaling {
  paint: { color: [number, number, number]; kind: "matte" | "glossy" | "metallic" | "candy"; roughness: number | null; candy_base: "metallic" | "white" };
  waarschuwingen: string[]; uitleg: { veld: string; waarde: string; bron: string; regel: string }[];
}
export interface VerfItem { slug: string; eigenschappen: VerfEigenschappen; vertaling: VerfVertaling; datum: string }
