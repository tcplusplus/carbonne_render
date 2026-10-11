#!/usr/bin/env python3
"""Haal CC0-HDRI's en vloertexturen van Poly Haven op naar assets/ (buiten git).

Idempotent: een bestand dat er al staat met de juiste grootte en md5 wordt overgeslagen. Schrijft
assets/manifest.json met bron, licentie en makers. Gebruik: `uv run python scripts/fetch_assets.py [--assets assets]`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.request
from pathlib import Path

API = "https://api.polyhaven.com"
LICENTIE = "CC0 1.0 (Poly Haven)"
MAX_TOTAAL = 200 * 1024 * 1024  # budget uit de opdracht

# id (Poly Haven) -> rol
HDRIS = {
    "blinds": "woonkamer met raam",
    "studio_small_09": "studio met softboxen",
    "comfy_cafe": "avondlicht met lampen",
    "artist_workshop": "bewolkt daglicht door ramen",
}
VLOEREN = {
    "diagonal_parquet": "parket",
    "large_floor_tiles_02": "lichte tegel",
    "smooth_concrete_floor": "beton",
    "dirty_carpet": "tapijt",
}
RES = "2k"


def _json(pad: str) -> dict:
    req = urllib.request.Request(f"{API}{pad}", headers={"User-Agent": "carbonne-render/0.1"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def _md5(pad: Path) -> str:
    h = hashlib.md5()
    with pad.open("rb") as f:
        for blok in iter(lambda: f.read(1 << 20), b""):
            h.update(blok)
    return h.hexdigest()


def _haal(url: str, doel: Path, grootte: int, md5: str) -> str:
    if doel.exists() and doel.stat().st_size == grootte and _md5(doel) == md5:
        return "bestond al"
    doel.parent.mkdir(parents=True, exist_ok=True)
    tmp = doel.with_suffix(doel.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "carbonne-render/0.1"})
    with urllib.request.urlopen(req, timeout=120) as r, tmp.open("wb") as f:
        while blok := r.read(1 << 20):
            f.write(blok)
    if tmp.stat().st_size != grootte or _md5(tmp) != md5:
        tmp.unlink()
        raise RuntimeError(f"{doel.name}: grootte of md5 klopt niet")
    tmp.replace(doel)
    return "gedownload"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--assets", type=Path, default=Path("assets"))
    a = ap.parse_args(argv)
    manifest: dict = {"licentie": LICENTIE, "hdris": {}, "vloeren": {}}
    totaal = 0
    plan = []
    for id_, rol in HDRIS.items():
        f = _json(f"/files/{id_}")["hdri"][RES]["hdr"]
        plan.append(("hdris", id_, rol, f, a.assets / "hdri" / f"{id_}_{RES}.hdr"))
    for id_, rol in VLOEREN.items():
        f = _json(f"/files/{id_}")["Diffuse"][RES]["jpg"]
        plan.append(("vloeren", id_, rol, f, a.assets / "vloer" / f"{id_}_diff_{RES}.jpg"))
    if sum(p[3]["size"] for p in plan) > MAX_TOTAAL:
        print("Totaal boven het budget van 200 MB; stop.", file=sys.stderr)
        return 1
    for soort, id_, rol, f, doel in plan:
        status = _haal(f["url"], doel, f["size"], f["md5"])
        info = _json(f"/info/{id_}")
        totaal += f["size"]
        manifest[soort][id_] = {
            "rol": rol,
            "bestand": str(doel.relative_to(a.assets)),
            "bytes": f["size"],
            "md5": f["md5"],
            "bron": f"https://polyhaven.com/a/{id_}",
            "url": f["url"],
            "licentie": LICENTIE,
            "makers": info.get("authors", {}),
        }
        print(f"{status:12s} {soort[:-1]:6s} {id_} ({f['size'] / 1e6:.1f} MB)")
    (a.assets / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    print(f"Totaal {totaal / 1e6:.1f} MB; manifest geschreven.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
