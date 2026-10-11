/* GEGENEREERD door `npm run types` uit het Pydantic-schema (core/config.py, core/verf.py). Niet met de hand wijzigen. */

/**
 * m; 0,35 of 0,50, maar vrij getal toegestaan
 */
export type Diameter = number;
export type AbsorptieNm = number[];
export type AbsorptiePerM = number[];
export type CauchyA = number;
/**
 * um^2
 */
export type CauchyB = number;
/**
 * 1/m; 0 = geen verstrooiing
 */
export type ScatteringCoeff = number;
/**
 * asymmetrie van Henyey-Greenstein; 0 = isotroop
 */
export type ScatteringG = number;
/**
 * m
 */
export type Hoogte = number;
/**
 * minimale afstand tot de rand van het blok
 */
export type EdgeMarginMm = number;
export type HeightM = number;
/**
 * @minItems 3
 * @maxItems 3
 */
export type Color = [number, number, number];
/**
 * aantal exemplaren van dit item in de laag
 */
export type Count = number;
/**
 * relatieve afwijking van de ronde omtrek
 */
export type Irregularity = number;
/**
 * straal van het schijfje, (min, max)
 *
 * @minItems 2
 * @maxItems 2
 */
export type RadiusMm = [number, number];
export type ThicknessMm = number;
export type Type = "wood";
/**
 * @minItems 3
 * @maxItems 3
 */
export type Color1 = [number, number, number];
/**
 * aantal exemplaren van dit item in de laag
 */
export type Count1 = number;
/**
 * hoeveel de blaadjes aan de top omhoog buigen
 */
export type CupMm = number;
export type Petals = number;
/**
 * lengte van de blaadjes, (min, max)
 *
 * @minItems 2
 * @maxItems 2
 */
export type RadiusMm1 = [number, number];
/**
 * maximale willekeurige kanteling
 */
export type TiltDeg = number;
/**
 * fractie van het licht dat doorgelaten wordt
 */
export type Translucency = number;
export type Type1 = "flower";
export type Items = (WoodSlice | Flower)[];
export type Seed = number;
/**
 * gietlagen met inhoud (T06)
 */
export type Layers = Layer[];
export type Onderkant = Bare | Paint | PaintStack | MatteClearCoat | PlateBelow;
export type Type2 = "bare";
/**
 * slug in data/verven/ (alleen herkomst, geen invloed op de render)
 */
export type BibliotheekId = string | null;
/**
 * ondergrond van candy: metallic of white
 */
export type CandyBase = "metallic" | "white";
/**
 * albedo, lineair RGB 0..1; invoer ook '#rrggbb' of 'RAL 9005'
 *
 * @minItems 3
 * @maxItems 3
 */
export type Color2 = [number, number, number];
/**
 * 0..1; 1 = ondoorzichtig, < 1 = doorschijnend (alleen matte/glossy)
 */
export type Dekking = number;
export type Kind = "matte" | "glossy" | "metallic" | "candy";
/**
 * GGX alpha van de glans; None = standaard per soort
 */
export type Roughness = number | null;
export type Type3 = "paint";
/**
 * van binnen (epoxy) naar buiten (lucht)
 */
export type Lagen = Paint[];
export type Type4 = "paintstack";
/**
 * GGX alpha
 */
export type Roughness1 = number;
export type Type5 = "clearcoat";
export type CandyBase1 = "metallic" | "white";
/**
 * albedo van de plaat, lineair RGB 0..1
 *
 * @minItems 3
 * @maxItems 3
 */
export type Color3 = [number, number, number];
export type GapMm = number;
export type Kind1 = "matte" | "glossy" | "metallic" | "candy";
/**
 * GGX alpha van de glans; None = standaard per soort
 */
export type Roughness2 = number | null;
export type Type6 = "plate";
export type Aantal = number;
/**
 * diameter (rond) of zijde (vierkant)
 */
export type AfmetingMm = number;
/**
 * lengte van de poot = hoogte van het blok boven de vloer minus de blokdikte
 */
export type HoogteM = number;
export type Metaal = "geborsteld" | "gepoetst" | "zwart";
/**
 * afstand van de buitenkant van de poot tot de rand van het blok
 */
export type RandMm = number;
export type Vorm = "rond" | "vierkant";
export type Breedte = number;
export type Hoogte1 = number;
export type MaxDepth = number;
export type Spp = number;
/**
 * @minItems 3
 * @maxItems 3
 */
export type Doel = [number, number, number];
/**
 * graden, horizontaal
 */
export type Fov = number;
/**
 * @minItems 3
 * @maxItems 3
 */
export type Positie = [number, number, number];
export type CameraPreset = string | null;
export type Omgeving = string | null;
/**
 * @minItems 3
 * @maxItems 3
 */
export type OmgevingRadiantie = [number, number, number];
export type Spot = boolean;
/**
 * @minItems 3
 * @maxItems 3
 */
export type VloerAlbedo = [number, number, number];
/**
 * zijde van de vierkante vloer, m
 */
export type VloerGrootte = number;
/**
 * @minItems 3
 * @maxItems 3
 */
export type VloerLijnAlbedo = [number, number, number];
/**
 * cel van het rasterpatroon, m
 */
export type VloerRastercel = number;
/**
 * aantal segmenten van de mantel
 */
export type Segmenten = number;
/**
 * T17: GGX-alpha van het bovenvlak; 0 = glad (roughdielectric vanaf > 0)
 */
export type TopRoughness = number;
export type Zijkant = Bare | Paint | PaintStack | MatteClearCoat;

export interface TableConfig {
  diameter?: Diameter;
  epoxy?: EpoxyMaterial;
  hoogte?: Hoogte;
  layers?: Layers;
  onderkant?: Onderkant;
  /**
   * T26: metalen poten onder het blok; None = geen poten (vloer op TAFEL_HOOGTE)
   */
  poten?: Legs | null;
  render?: RenderSettings;
  scene?: SceneConfig;
  segmenten?: Segmenten;
  top_roughness?: TopRoughness;
  zijkant?: Zijkant;
}
/**
 * Kleurloze epoxy. n(lambda) = A + B / lambda^2 (Cauchy, lambda in micrometer).
 *
 * This interface was referenced by `TableConfig`'s JSON-Schema
 * via the `definition` "EpoxyMaterial".
 */
export interface EpoxyMaterial {
  absorptie_nm?: AbsorptieNm;
  absorptie_per_m?: AbsorptiePerM;
  cauchy_a?: CauchyA;
  cauchy_b?: CauchyB;
  scattering_coeff?: ScatteringCoeff;
  scattering_g?: ScatteringG;
}
/**
 * Een gietlaag: inhoud die op `height_m` boven de onderkant van het blok zweeft (hoogte van het
 * middenvlak van de items). Plaatsing is willekeurig maar reproduceerbaar via `seed`.
 *
 * This interface was referenced by `TableConfig`'s JSON-Schema
 * via the `definition` "Layer".
 */
export interface Layer {
  edge_margin_mm?: EdgeMarginMm;
  height_m: HeightM;
  items?: Items;
  seed?: Seed;
}
/**
 * Onregelmatig houtschijfje: plat, diffuus, met een houtkleur. Elk exemplaar krijgt een eigen straal,
 * omtrek en een lichte helderheidsvariatie (via de seed van de laag).
 *
 * This interface was referenced by `TableConfig`'s JSON-Schema
 * via the `definition` "WoodSlice".
 */
export interface WoodSlice {
  color?: Color | string;
  count?: Count;
  irregularity?: Irregularity;
  radius_mm?: RadiusMm;
  thickness_mm?: ThicknessMm;
  type?: Type;
}
/**
 * Eenvoudige bloem: een rozet van gebogen, dunne blaadjes, licht doorschijnend (Disney thin: diffuse
 * reflectie plus diffuse transmissie). `petals=1` geeft een los bloemblaadje.
 *
 * This interface was referenced by `TableConfig`'s JSON-Schema
 * via the `definition` "Flower".
 */
export interface Flower {
  color?: Color1 | string;
  count?: Count1;
  cup_mm?: CupMm;
  petals?: Petals;
  radius_mm?: RadiusMm1;
  tilt_deg?: TiltDeg;
  translucency?: Translucency;
  type?: Type1;
}
/**
 * Onbehandeld: glad diëlektrisch grensvlak epoxy/lucht (met TIR).
 *
 * This interface was referenced by `TableConfig`'s JSON-Schema
 * via the `definition` "Bare".
 */
export interface Bare {
  type?: Type2;
}
/**
 * Ondoorzichtige verf in optisch contact met de epoxy (geen Fresnel-grensvlak aan de binnenkant).
 *
 * This interface was referenced by `TableConfig`'s JSON-Schema
 * via the `definition` "Paint".
 */
export interface Paint {
  bibliotheek_id?: BibliotheekId;
  candy_base?: CandyBase;
  color?: Color2 | string;
  dekking?: Dekking;
  kind?: Kind;
  roughness?: Roughness;
  type?: Type3;
}
/**
 * T24: gestapelde verflagen op een vlak, van binnen (tegen de epoxy) naar buiten (naar de lucht).
 *
 * Elke laag is een `Paint` met een eigen `dekking`. Een doorschijnende laag laat de laag eronder zichtbaar;
 * het effectieve beeld volgt uit Kubelka-Munk (`carbonne.core.lagen`). Een stapel van een ondoorzichtige laag
 * is bit-identiek aan die `Paint` zelf.
 *
 * This interface was referenced by `TableConfig`'s JSON-Schema
 * via the `definition` "PaintStack".
 */
export interface PaintStack {
  lagen: Lagen;
  type?: Type4;
}
/**
 * Kleurloze matte lak: ruw diëlektrisch grensvlak (GGX) epoxy/lucht.
 *
 * Standaardruwheid alpha = 0,3: een gespoten matte lak heeft microruwheid in de orde van enkele tienden van
 * een micrometer met glansmeting 5-15 GU; GGX-alpha 0,3 geeft een duidelijk gespreide, maar nog herkenbare
 * reflectie. Zeer ruw (alpha > 0,5) maakt het oppervlak vrijwel Lambertiaans.
 *
 * This interface was referenced by `TableConfig`'s JSON-Schema
 * via the `definition` "MatteClearCoat".
 */
export interface MatteClearCoat {
  roughness?: Roughness1;
  type?: Type5;
}
/**
 * Losse plaat onder het blok met een luchtspleet; het blok zelf blijft onbehandeld (alleen onderkant).
 *
 * This interface was referenced by `TableConfig`'s JSON-Schema
 * via the `definition` "PlateBelow".
 */
export interface PlateBelow {
  candy_base?: CandyBase1;
  color?: Color3 | string;
  gap_mm?: GapMm;
  kind?: Kind1;
  roughness?: Roughness2;
  type?: Type6;
}
/**
 * T26: metalen poten onder het blok (alleen als `TableConfig.poten` gezet is; standaard geen poten).
 *
 * Plaatsing: `aantal` poten gelijkmatig op een cirkel, de buitenkant van elke poot op `rand_mm` van de rand van
 * het blok. De poot hangt `hoogte_m` onder het blok (de vloer ligt daar). Metaal: geborsteld = aluminium (ruw),
 * gepoetst = chroom (bijna glad), zwart = gepoederlakt (zwart pigment onder een dielectrische lak).
 *
 * This interface was referenced by `TableConfig`'s JSON-Schema
 * via the `definition` "Legs".
 */
export interface Legs {
  aantal?: Aantal;
  afmeting_mm?: AfmetingMm;
  hoogte_m?: HoogteM;
  metaal?: Metaal;
  rand_mm?: RandMm;
  vorm?: Vorm;
}
/**
 * This interface was referenced by `TableConfig`'s JSON-Schema
 * via the `definition` "RenderSettings".
 */
export interface RenderSettings {
  breedte?: Breedte;
  hoogte?: Hoogte1;
  max_depth?: MaxDepth;
  spp?: Spp;
}
/**
 * This interface was referenced by `TableConfig`'s JSON-Schema
 * via the `definition` "SceneConfig".
 */
export interface SceneConfig {
  camera?: CameraConfig;
  camera_preset?: CameraPreset;
  omgeving?: Omgeving;
  omgeving_radiantie?: OmgevingRadiantie;
  spot?: Spot;
  vloer_albedo?: VloerAlbedo;
  vloer_grootte?: VloerGrootte;
  vloer_lijn_albedo?: VloerLijnAlbedo;
  vloer_rastercel?: VloerRastercel;
}
/**
 * This interface was referenced by `TableConfig`'s JSON-Schema
 * via the `definition` "CameraConfig".
 */
export interface CameraConfig {
  doel?: Doel;
  fov?: Fov;
  positie?: Positie;
}
