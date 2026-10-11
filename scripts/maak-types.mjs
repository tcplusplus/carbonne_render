// Genereert web/src/types/config.ts en verf.ts uit de JSON-schema's van de API (zie scripts/schema_dump.py).
//
// Het schema wordt voor de typegeneratie op drie punten aangepast; de runtime-validatie in de UI (src/schema.ts)
// gebruikt het onaangetaste schema van GET /api/schema:
//  - `prefixItems` (JSON Schema 2020-12, Pydantic-tuples) wordt `items: [...]`, want dat kent json-schema-to-typescript;
//  - een kleurveld ("color") mag ook tekst zijn ('#rrggbb', 'RAL 9005'): de before-validator van de backend (core/config.py);
//  - min/maxItems van gewone lijsten vervallen, anders worden het unies van tupels (Paint[] in plaats van [Paint] | [Paint, Paint] ...).
import { compile } from "json-schema-to-typescript";
import { readFile, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const map = join(dirname(fileURLToPath(import.meta.url)), "..", "web", "src", "types");
const KOP = "/* GEGENEREERD door `npm run types` uit het Pydantic-schema (core/config.py, core/verf.py). Niet met de hand wijzigen. */";

function pasAan(knoop, sleutel = "") {
  if (Array.isArray(knoop)) return knoop.map((k) => pasAan(k));
  if (knoop === null || typeof knoop !== "object") return knoop;
  const uit = {};
  for (const [k, v] of Object.entries(knoop)) uit[k] = k === "properties" || k === "$defs" ? Object.fromEntries(Object.entries(v).map(([n, w]) => [n, pasAan(w, n)])) : pasAan(v, k);
  if (uit.prefixItems) {
    uit.items = uit.prefixItems;
    delete uit.prefixItems;
    uit.additionalItems = false;
  } else if (uit.type === "array" && uit.items && !Array.isArray(uit.items)) {
    delete uit.minItems;
    delete uit.maxItems;
  }
  if (sleutel === "color" && uit.type === "array") return { anyOf: [uit, { type: "string" }], ...(uit.default ? { default: uit.default } : {}) };
  return uit;
}

for (const [bron, doel, naam] of [["config.schema.json", "config.ts", "TableConfig"], ["verf.schema.json", "verf.ts", "VerfEigenschappen"]]) {
  const schema = pasAan(JSON.parse(await readFile(join(map, bron), "utf8")));
  const ts = await compile(schema, naam, {
    bannerComment: KOP, additionalProperties: false, unreachableDefinitions: true, cwd: map, style: { singleQuote: false, printWidth: 120 },
  });
  await writeFile(join(map, doel), ts);
  console.log(`${doel}: ${naam}`);
}
