// Kleuromrekening: de UI toont sRGB-hex; het model rekent met lineair RGB (zoals backend/kleur.py).
export const srgbNaarLineair = (c) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
export const lineairNaarSrgb = (c) => (c <= 0.0031308 ? 12.92 * c : 1.055 * c ** (1 / 2.4) - 0.055);

const HEX = /^#?([0-9a-f]{6})$/i;
const HEX3 = /^#?([0-9a-f]{3})$/i;

export function hexNaarLineair(hex) {
  const m = HEX.exec(hex);
  if (!m) throw new Error(`ongeldige hex ${hex}`);
  return [0, 2, 4].map((i) => srgbNaarLineair(parseInt(m[1].slice(i, i + 2), 16) / 255));
}

export function lineairNaarHex(rgb) {
  return "#" + rgb.map((c) => Math.round(255 * Math.min(1, Math.max(0, lineairNaarSrgb(c)))).toString(16).padStart(2, "0")).join("");
}

/** Tekst (#rrggbb, #rgb, "RAL 9005", "9005") -> '#rrggbb' of null als ongeldig. `ral` = {code: hex}. */
export function tekstNaarHex(tekst, ral) {
  let t = String(tekst).trim();
  const m3 = HEX3.exec(t);
  if (m3) t = "#" + [...m3[1]].map((c) => c + c).join("");
  const mr = /^(?:ral\s*)?(\d{4})$/i.exec(t);
  if (mr) return ral[mr[1]] ? "#" + ral[mr[1]].toLowerCase() : null;
  const m = HEX.exec(t);
  return m ? "#" + m[1].toLowerCase() : null;
}

/** Waarde uit een config (tekst of lineair RGB-drietal) -> '#rrggbb' voor picker en preview. */
export function waardeNaarHex(w, ral) {
  if (Array.isArray(w)) return lineairNaarHex(w);
  return tekstNaarHex(w, ral) ?? "#808080";
}
