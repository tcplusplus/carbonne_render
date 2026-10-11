/* GEGENEREERD door `npm run types` uit het Pydantic-schema (core/config.py, core/verf.py). Niet met de hand wijzigen. */

export type BronUrl = string | null;
export type Effect = "geen" | "metallic" | "chroom" | "candy" | "parelmoer" | "glitter" | "fluo";
/**
 * gloss units bij 60 graden (technisch fiche)
 */
export type GlansGu60 = number | null;
/**
 * mat, zijdemat, zijdeglans, satijn, glans, hoogglans (ook Engels)
 */
export type Glansgraad = string | null;
/**
 * #rrggbb (sRGB-weergave van de kleur)
 */
export type Hex = string | null;
/**
 * RAL-code ('RAL 3020') of hex; een merkcode alleen samen met `hex`
 */
export type Kleurcode = string | null;
export type Kleurnaam = string | null;
export type Merk = string | null;
export type OndergrondCandy = ("metallic" | "white") | null;
export type Opmerking = string | null;
export type Product = string | null;
export type Transparant = boolean;

/**
 * Eigenschappen van het product, zoals op het blik of het technische fiche staan.
 */
export interface VerfEigenschappen {
  bron_url?: BronUrl;
  effect?: Effect;
  glans_gu_60?: GlansGu60;
  glansgraad?: Glansgraad;
  hex?: Hex;
  kleurcode?: Kleurcode;
  kleurnaam?: Kleurnaam;
  merk?: Merk;
  ondergrond_candy?: OndergrondCandy;
  opmerking?: Opmerking;
  product?: Product;
  transparant?: Transparant;
}
