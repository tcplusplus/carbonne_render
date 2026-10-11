"""T28: frontend in TypeScript (Vite). Types komen uit het Pydantic-schema, tsc is schoon, en web/dist is actueel.

Deze tests vragen `npm install` (node_modules); zonder node of node_modules worden ze overgeslagen."""

from __future__ import annotations

import filecmp
import importlib.util
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TYPES = ROOT / "web" / "src" / "types"
TSC = ROOT / "node_modules" / ".bin" / "tsc"
VITE = ROOT / "node_modules" / ".bin" / "vite"

npm = pytest.mark.skipif(shutil.which("node") is None or not TSC.exists(), reason="node of node_modules ontbreekt (npm install)")


def _schema_dump():
    spec = importlib.util.spec_from_file_location("schema_dump", ROOT / "scripts" / "schema_dump.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_schemabestanden_lopen_niet_achter_op_de_backend():
    """web/src/types/*.schema.json is wat `npm run types` uit core/config.py en core/verf.py haalt."""
    from carbonne.core.config import TableConfig
    from carbonne.core.verf import VerfEigenschappen

    dump = _schema_dump()
    assert (TYPES / "config.schema.json").read_text(encoding="utf-8") == dump.schema_tekst(TableConfig)
    assert (TYPES / "verf.schema.json").read_text(encoding="utf-8") == dump.schema_tekst(VerfEigenschappen)
    assert json.loads(dump.schema_tekst(TableConfig)) == TableConfig.model_json_schema()  # ook wat GET /api/schema geeft


@npm
def test_gegenereerde_types_horen_bij_het_schema(tmp_path):
    """Draai de generator op een kopie en vergelijk met de ingecheckte config.ts en verf.ts."""
    (tmp_path / "scripts").mkdir()
    shutil.copy(ROOT / "scripts" / "maak-types.mjs", tmp_path / "scripts")
    kopie = tmp_path / "web" / "src" / "types"
    kopie.mkdir(parents=True)
    for naam in ("config.schema.json", "verf.schema.json"):
        shutil.copy(TYPES / naam, kopie)
    (tmp_path / "node_modules").symlink_to(ROOT / "node_modules")
    (tmp_path / "package.json").write_text('{"type": "module"}')
    subprocess.run(["node", "scripts/maak-types.mjs"], cwd=tmp_path, check=True, capture_output=True, text=True)
    for naam in ("config.ts", "verf.ts"):
        assert (kopie / naam).read_text() == (TYPES / naam).read_text(), f"{naam} loopt achter: draai `npm run types`"


@npm
def test_tsc_noemit_is_schoon():
    uit = subprocess.run([str(TSC), "--noEmit"], cwd=ROOT, capture_output=True, text=True)
    assert uit.returncode == 0, uit.stdout + uit.stderr


def _tsc_op(bron: str, tmp_path: Path) -> subprocess.CompletedProcess:
    (tmp_path / "controle.ts").write_text(bron)
    (tmp_path / "tsconfig.json").write_text(json.dumps({"extends": str(ROOT / "tsconfig.json"), "include": ["controle.ts"],
                                                         "compilerOptions": {"types": [], "typeRoots": []}}))
    return subprocess.run([str(TSC), "--noEmit", "-p", str(tmp_path / "tsconfig.json")], capture_output=True, text=True)


@npm
def test_verkeerd_type_in_de_config_compileert_niet(tmp_path):
    """Het doel van T28: `count: "veel"` (of een onbekend verftype) wordt aan de frontendkant afgekeurd."""
    def kop(*namen: str) -> str:
        return f'import type {{ {", ".join(namen)} }} from "{(TYPES / "config.ts").as_posix()}";\n'

    goed = _tsc_op(kop('WoodSlice', 'Paint', 'TableConfig') + 'const a: WoodSlice = { type: "wood", count: 3 };\nconst b: Paint = { kind: "glossy" };\nconst c: TableConfig = { diameter: 0.4 };\n'
                   "export { a, b, c };\n", tmp_path)
    assert goed.returncode == 0, goed.stdout
    fout = _tsc_op(kop('WoodSlice') + 'export const a: WoodSlice = { type: "wood", count: "veel" };\n', tmp_path)
    assert fout.returncode != 0 and "TS2322" in fout.stdout and "string" in fout.stdout, fout.stdout
    fout = _tsc_op(kop('Paint') + 'export const b: Paint = { kind: "doorzichtig" };\n', tmp_path)
    assert fout.returncode != 0 and "doorzichtig" in fout.stdout, fout.stdout
    fout = _tsc_op(kop('TableConfig') + 'export const c: TableConfig = { diameter: 0.4, onbekend: 1 };\n', tmp_path)
    assert fout.returncode != 0 and "TS2353" in fout.stdout, fout.stdout


@npm
def test_dist_is_actueel(tmp_path):
    """web/dist staat in git en moet bij de bronnen horen: een verse build geeft dezelfde bestanden (inhoudshash in de naam)."""
    uit = tmp_path / "dist"
    r = subprocess.run([str(VITE), "build", "--outDir", str(uit), "--emptyOutDir"], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    dist = ROOT / "web" / "dist"
    nieuw = sorted(p.relative_to(uit) for p in uit.rglob("*") if p.is_file())
    oud = sorted(p.relative_to(dist) for p in dist.rglob("*") if p.is_file())
    assert nieuw == oud, "web/dist loopt achter op de bronnen: draai `npm run build`"
    assert not filecmp.cmpfiles(uit, dist, [str(p) for p in nieuw], shallow=False)[1]
