// Minimale JSON-schema-validator voor het schema van GET /api/schema (Pydantic v2), zonder buildstap of bibliotheek.
// Ondersteunt alleen wat dat schema gebruikt: $ref, anyOf, oneOf met discriminator, type, enum, const,
// minimum/maximum (ook exclusief), minItems/maxItems, prefixItems, items, properties, required en
// additionalProperties:false. Een onbekend trefwoord wordt genegeerd; de backend blijft de laatste scheidsrechter.
// Uitvoer heeft de vorm van Pydantic-fouten ({loc, msg, input, type}), zodat fout.js ze op dezelfde manier toont.

const verwijs = (schema, r) => r.slice(2).split("/").reduce((o, k) => o[k], schema);
const soortVan = (w) => (w === null ? "null" : Array.isArray(w) ? "array" : typeof w);
const isType = (t, w) => (t === "integer" ? Number.isInteger(w) : t === "number" ? typeof w === "number" && Number.isFinite(w) : soortVan(w) === t);
const NL = { object: "een object", array: "een lijst", string: "tekst", integer: "een geheel getal", number: "een getal", boolean: "ja of nee", null: "leeg" };

/** Eigen uitzondering: een kleurveld mag tekst zijn ('#rrggbb', 'RAL 9005'); de backend vertaalt dat zelf (before-validator). */
const kleurTekst = (loc, w) => typeof w === "string" && loc[loc.length - 1] === "color";

export function valideer(schema, waarde, knoop = schema, loc = [], uit = []) {
  const fout = (type, msg) => uit.push({ type, loc: [...loc], msg, input: waarde });
  if (knoop.$ref) return valideer(schema, waarde, verwijs(schema, knoop.$ref), loc, uit);
  if (knoop.anyOf || knoop.oneOf) {
    const takken = (knoop.anyOf ?? knoop.oneOf).map((t) => (t.$ref ? verwijs(schema, t.$ref) : t));
    if (knoop.discriminator && waarde && typeof waarde === "object") {
      const naam = knoop.discriminator.propertyName, sleutel = waarde[naam];
      const ref = knoop.discriminator.mapping?.[sleutel];
      if (!ref) { uit.push({ type: "union_tag_invalid", loc: [...loc, naam], msg: `moet een van ${Object.keys(knoop.discriminator.mapping).join(", ")} zijn`, input: sleutel }); return uit; }
      return valideer(schema, waarde, verwijs(schema, ref), loc, uit);
    }
    const passend = takken.find((t) => t.type && isType(t.type, waarde)) ?? takken.find((t) => !t.type);
    if (passend) return valideer(schema, waarde, passend, loc, uit);
    fout("type", `moet ${takken.map((t) => NL[t.type] ?? t.type).join(" of ")} zijn`);
    return uit;
  }
  if (knoop.const !== undefined && waarde !== knoop.const) fout("const", `moet ${JSON.stringify(knoop.const)} zijn`);
  if (knoop.enum && !knoop.enum.includes(waarde)) { fout("enum", `moet een van ${knoop.enum.join(", ")} zijn`); return uit; }
  if (knoop.type) {
    if (!isType(knoop.type, waarde)) {
      if (!(knoop.type === "array" && kleurTekst(loc, waarde))) fout("type", `moet ${NL[knoop.type] ?? knoop.type} zijn`);
      return uit;
    }
  }
  if (typeof waarde === "number") {
    if (knoop.minimum !== undefined && waarde < knoop.minimum) fout("greater_than_equal", `moet minstens ${knoop.minimum} zijn`);
    if (knoop.exclusiveMinimum !== undefined && waarde <= knoop.exclusiveMinimum) fout("greater_than", `moet groter dan ${knoop.exclusiveMinimum} zijn`);
    if (knoop.maximum !== undefined && waarde > knoop.maximum) fout("less_than_equal", `moet hoogstens ${knoop.maximum} zijn`);
    if (knoop.exclusiveMaximum !== undefined && waarde >= knoop.exclusiveMaximum) fout("less_than", `moet kleiner dan ${knoop.exclusiveMaximum} zijn`);
  }
  if (Array.isArray(waarde)) {
    if (knoop.minItems !== undefined && waarde.length < knoop.minItems) fout("too_short", `moet minstens ${knoop.minItems} elementen hebben`);
    if (knoop.maxItems !== undefined && waarde.length > knoop.maxItems) fout("too_long", `mag hoogstens ${knoop.maxItems} elementen hebben`);
    waarde.forEach((w, i) => {
      const t = knoop.prefixItems?.[i] ?? knoop.items;
      if (t) valideer(schema, w, t, [...loc, i], uit);
    });
  }
  if (waarde && typeof waarde === "object" && !Array.isArray(waarde)) {
    const eig = knoop.properties ?? {};
    for (const k of knoop.required ?? []) if (!(k in waarde)) uit.push({ type: "missing", loc: [...loc, k], msg: "is verplicht", input: undefined });
    for (const [k, w] of Object.entries(waarde)) {
      if (eig[k]) valideer(schema, w, eig[k], [...loc, k], uit);
      else if (knoop.additionalProperties === false) uit.push({ type: "extra_forbidden", loc: [...loc, k], msg: "veld bestaat niet", input: w });
    }
  }
  return uit;
}

/** Grenzen van `veld` in model `model` (naam uit $defs, of "TableConfig" voor de top): {min, max, enum, exclusiefMin}. */
export function veldGrenzen(schema, model, veld) {
  const m = schema.$defs?.[model] ?? schema;
  const g = {};
  const loop = (s) => {
    if (s.$ref) s = verwijs(schema, s.$ref);
    const tuple = !!s.prefixItems;
    for (const [k, naar] of [["minimum", "min"], ["exclusiveMinimum", "min"], ["minItems", "min"], ["maximum", "max"], ["exclusiveMaximum", "max"], ["maxItems", "max"]]) {
      if (s[k] === undefined || (tuple && /Items$/.test(k))) continue;
      g[naar] = s[k];
      if (k === "exclusiveMinimum") g.exclusiefMin = true;
    }
    if (s.enum) g.enum = s.enum;
    for (const a of s.anyOf ?? []) if (a.type !== "null") loop(a);
  };
  if (m.properties?.[veld]) loop(m.properties[veld]);
  return g;
}
