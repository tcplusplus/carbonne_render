"""`carbonne-kalibreer`: kalibratie met een gsm-foto.

  raster  foto.jpg -o raster.png                  coordinatenraster over de foto, om de gebieden af te lezen
  meet    foto.jpg gebieden.json                  gemeten verfkleur(en) uit papier + staal
  vergelijk config.json foto.jpg gebieden.json    render maken en per gebied vergelijken met de foto (dE2000)

`gebieden.json`: {"papier_albedo": 0.85, "papier_foto": [x0,y0,x1,y1], "papier_render": [x0,y0,x1,y1],
 "staal": [{"verf": "zijkant", "foto": [..]}], "gebieden": [{"naam": "zijkant", "foto": [..], "render": [..],
 "verf": "zijkant"}]}. Alle gebieden zijn pixels in het eigen beeld (foto of render).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

from carbonne.core.config import Paint, TableConfig
from carbonne.kalibratie import kern


def zet_verfkleur(config: TableConfig, verf: str, rgb) -> TableConfig:
    """Overschrijf de kleur van `zijkant` of `onderkant` (moet een verf zijn); de soort blijft."""
    oud = getattr(config, verf)
    if not isinstance(oud, Paint):
        raise ValueError(f"{verf} is geen verf ({oud.type}); de gemeten kleur kan alleen op een verf")  # noqa: TRY004
    return config.model_copy(update={verf: oud.model_copy(update={"color": tuple(rgb)})})


def render_lineair(config: TableConfig, papier_albedo: float, spp: int, ruisdrempel: float, on_msg=None) -> np.ndarray:
    """Render met de vloer als papierreferentie (vloer_albedo = papieralbedo). Geeft lineaire RGB (h, w, 3)."""
    from carbonne.render.pipeline import RenderOpties, render

    sc = config.scene.model_copy(update={"vloer_albedo": (papier_albedo,) * 3})
    cfg = config.model_copy(update={"scene": sc})
    res = render(cfg, RenderOpties(max_spp=spp, ruisdrempel=ruisdrempel))
    if on_msg:
        on_msg(f"render: {res.spp} spp, ruis {res.ruis}, {res.tijd_s:.1f} s ({res.reden})")
    return res.beeld[..., :3].astype(np.float64)


def kalibreer(config: TableConfig, foto_lin: np.ndarray, plan: dict, spp: int = 256, ruisdrempel: float = 0.02,
              render_lin: np.ndarray | None = None, on_msg=None) -> dict:
    """Hele keten: gemeten verfkleur(en) in de config zetten, renderen, normaliseren, vergelijken, bijstellen.

    Resultaat: {"config" (met gemeten kleuren), "config_bijgesteld", "gemeten", "verschillen", "foto_norm",
    "render_norm"}. `render_lin` mag een al gemaakte render zijn (tests)."""
    albedo = float(plan.get("papier_albedo", kern.PAPIER_ALBEDO))
    gemeten = {}
    for s in plan.get("staal", []):
        m = kern.meet_verfkleur(foto_lin, tuple(plan["papier_foto"]), tuple(s["foto"]), albedo)
        gemeten[s["verf"]] = m
        config = zet_verfkleur(config, s["verf"], m["rgb"])
    if render_lin is None:
        render_lin = render_lineair(config, albedo, spp, ruisdrempel, on_msg)
    foto_n = kern.normaliseer(foto_lin, tuple(plan["papier_foto"]), albedo)
    render_n = kern.normaliseer(render_lin, tuple(plan["papier_render"]), albedo)
    verschillen = kern.vergelijk(foto_n, render_n, plan["gebieden"])
    bij = config
    for v in verschillen:
        if v.verf and isinstance(getattr(bij, v.verf), Paint):
            nieuw = kern.bijgestelde_verf(getattr(bij, v.verf).color, v.rgb_foto, v.rgb_render)
            bij = zet_verfkleur(bij, v.verf, nieuw)
    return {"config": config, "config_bijgesteld": bij, "gemeten": gemeten, "verschillen": verschillen,
            "foto_norm": foto_n, "render_norm": render_n, "render_lin": render_lin}


def _lees_png(pad: Path) -> np.ndarray:
    return (kern.lineair_naar_srgb_arr(kern.laad_foto(pad)) * 255).round().astype(np.uint8)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="carbonne-kalibreer", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("raster")
    r.add_argument("foto", type=Path)
    r.add_argument("-o", "--uit", type=Path, default=Path("out/kalibratie/raster.png"))
    r.add_argument("--stap", type=int, default=50)
    m = sub.add_parser("meet")
    m.add_argument("foto", type=Path)
    m.add_argument("gebieden", type=Path)
    v = sub.add_parser("vergelijk")
    v.add_argument("config", type=Path)
    v.add_argument("foto", type=Path)
    v.add_argument("gebieden", type=Path)
    v.add_argument("-o", "--uit", type=Path, default=Path("out/kalibratie"))
    v.add_argument("--spp", type=int, default=256)
    v.add_argument("--ruisdrempel", type=float, default=0.02)
    a = ap.parse_args(argv)

    try:
        if a.cmd == "raster":
            beeld = kern.raster_beeld(_lees_png(a.foto), a.stap)
            a.uit.parent.mkdir(parents=True, exist_ok=True)
            a.uit.write_bytes(kern.foto_naar_png(beeld))
            print(a.uit)
            return 0
        foto = kern.laad_foto(a.foto)
        plan = json.loads(a.gebieden.read_text())
        albedo = float(plan.get("papier_albedo", kern.PAPIER_ALBEDO))
        if a.cmd == "meet":
            for s in plan["staal"]:
                mm = kern.meet_verfkleur(foto, tuple(plan["papier_foto"]), tuple(s["foto"]), albedo)
                print(f"{s['verf']:10} {mm['hex']}  lineair {tuple(round(c, 4) for c in mm['rgb'])}"
                      + ("  (afgekapt: staal helderder dan papier)" if mm["afgekapt"] else ""))
            return 0
        config = TableConfig.model_validate(json.loads(a.config.read_text()))
        res = kalibreer(config, foto, plan, a.spp, a.ruisdrempel, on_msg=lambda t: print(t, file=sys.stderr))
    except (ValueError, KeyError, OSError) as e:
        print(f"fout: {e}", file=sys.stderr)
        return 2
    a.uit.mkdir(parents=True, exist_ok=True)
    for verf, mm in res["gemeten"].items():
        print(f"gemeten {verf}: {mm['hex']}")
    for x in res["verschillen"]:
        print(x.tekst())
    (a.uit / "config-gemeten.json").write_text(res["config"].model_dump_json(indent=1))
    (a.uit / "config-bijgesteld.json").write_text(res["config_bijgesteld"].model_dump_json(indent=1))
    beeld = kern.vergelijkingsbeeld(res["foto_norm"], res["render_norm"], plan["gebieden"], res["verschillen"])
    (a.uit / "vergelijking.png").write_bytes(kern.foto_naar_png(beeld))
    print(a.uit / "vergelijking.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
