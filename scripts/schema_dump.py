"""Schrijft de JSON-schema's van de API naar web/src/types/ (invoer voor `npm run types`).

Dezelfde schema's als GET /api/schema en GET /api/verven/schema."""

from __future__ import annotations

import json
from pathlib import Path

from carbonne.core.config import TableConfig
from carbonne.core.verf import VerfEigenschappen

UIT = Path(__file__).resolve().parents[1] / "web" / "src" / "types"


def schema_tekst(model) -> str:
    return json.dumps(model.model_json_schema(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main() -> None:
    UIT.mkdir(parents=True, exist_ok=True)
    (UIT / "config.schema.json").write_text(schema_tekst(TableConfig), encoding="utf-8")
    (UIT / "verf.schema.json").write_text(schema_tekst(VerfEigenschappen), encoding="utf-8")


if __name__ == "__main__":
    main()
