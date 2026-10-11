// Foutmeldingen van de backend (HTTP 422 van Pydantic) leesbaar maken: welk veld, wat er mis is.
const LABELS = {
  diameter: "Diameter", hoogte: "Dikte (hoogte)", segmenten: "Segmenten", height_m: "Hoogte in het blok", seed: "Seed",
  edge_margin_mm: "Randmarge", count: "Aantal", radius_mm: "Straal", petals: "Bloemblaadjes", color: "Kleur",
  thickness_mm: "Dikte schijfje", roughness: "Ruwheid", gap_mm: "Luchtspleet", dekking: "Dekking", kind: "Verftype",
  candy_base: "Ondergrond candy", fov: "Beeldhoek", breedte: "Breedte", spp: "Samples", max_depth: "Max. diepte",
  zijkant: "Zijkant", onderkant: "Onderkant", layers: "Laag", items: "Item", lagen: "Verflaag", scene: "Omgeving",
  render: "Resolutie", epoxy: "Epoxy", camera: "Camera", omgeving: "Omgeving", camera_preset: "Camera", opties: "Opties",
};
const TAGS = new Set(["wood", "flower", "bare", "paint", "paintstack", "clearcoat", "plate"]);
const TELLERS = new Set(["layers", "items", "lagen"]);

/** Pydantic-`loc` -> leesbaar pad, bv. ["body","config","layers",0,"height_m"] -> "Laag 1 > Hoogte in het blok". */
export function locNaarTekst(loc) {
  const uit = [];
  let vorige = null;
  for (const d of loc) {
    if (d === "body" || (d === "config" && vorige === "body")) { vorige = d; continue; }
    if (typeof d === "string" && TAGS.has(d) && (typeof vorige === "number" || vorige === "zijkant" || vorige === "onderkant")) { vorige = d; continue; }
    if (typeof d === "number") {
      if (TELLERS.has(vorige) && uit.length) uit[uit.length - 1] += ` ${d + 1}`;
      else uit.push(`[${d + 1}]`);
    } else uit.push(LABELS[d] ?? d);
    vorige = d;
  }
  return uit.join(" > ");
}

const toon = (v) => (v === null || typeof v === "object" ? null : String(v).length > 24 ? null : String(v));

/** `detail` van een foutantwoord (tekst, {melding}, of Pydantic-lijst) -> één leesbare regel. */
export function detailNaarTekst(d, max = 3) {
  if (Array.isArray(d)) {
    const regels = d.map((f) => {
      const veld = locNaarTekst(f.loc ?? []);
      const nu = f.input !== undefined && toon(f.input) !== null ? ` (nu ${toon(f.input)})` : "";
      return `${veld ? veld + ": " : ""}${f.msg ?? JSON.stringify(f)}${nu}`;
    });
    return regels.slice(0, max).join("; ") + (regels.length > max ? `; en nog ${regels.length - max} fouten` : "");
  }
  if (d && typeof d === "object") return d.melding ?? JSON.stringify(d);
  return String(d);
}
