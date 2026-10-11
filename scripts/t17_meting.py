"""T17: hoeveel gevangen licht van de rode zijkant wordt zichtbaar bij verstrooiing in de epoxy of een ruw bovenvlak?

Gebruik: uv run python scripts/t17_meting.py [--res 160] [--spp 512] [--out out/t17] [--figuur docs/evidence/img/T17-verstrooiing.png]

Zelfde opstelling en meetgebieden (ROI's) als scripts/zijkant_meting.py (T05): rode zijkant, witte omgeving, camera van
boven (85 graden) en schuin (35 graden). Onderkanten: contact (witte verf in contact), plaat (witte plaat met
luchtspleet), bare (onbehandeld). Reeksen: verstrooiingscoefficient (1/m) en bovenvlakruwheid (GGX-alpha), plus de
combinatie. Rapporteert per ROI het rood-aandeel R/(R+G+B) (neutraal = 0,333), de luminantie, de ruis en de renderduur.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import mitsuba as mi
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import zijkant_meting as zm

from carbonne.core.config import Bare, Paint, PlateBelow, TableConfig
from carbonne.core.variant import select_variant

CAMERAS = {"boven": 85.0, "schuin35": 35.0}
WIT = (0.9, 0.9, 0.9)
ONDER = {
    "contact": lambda: Paint(color=WIT),
    "plaat": lambda: PlateBelow(color=WIT, gap_mm=0.1),
    "bare": lambda: Bare(),
}
# (naam, verstrooiing 1/m, g, bovenvlakruwheid)
REEKS = [
    ("s0", 0.0, 0.0, 0.0),
    ("s1", 1.0, 0.0, 0.0),
    ("s2", 2.0, 0.0, 0.0),
    ("s5", 5.0, 0.0, 0.0),
    ("s20", 20.0, 0.0, 0.0),
    ("s100", 100.0, 0.0, 0.0),
    ("s20_g0.7", 20.0, 0.7, 0.0),
    ("r0.02", 0.0, 0.0, 0.02),
    ("r0.05", 0.0, 0.0, 0.05),
    ("s20_r0.05", 20.0, 0.0, 0.05),
]


def maak(onder: str, s: float, g: float, ruw: float, cam, res: int, spp: int, depth: int) -> TableConfig:
    c = zm.maak_config(Paint(color=zm.ROOD), ONDER[onder](), zm.ZWART, cam, res, spp)
    c.epoxy.scattering_coeff, c.epoxy.scattering_g, c.top_roughness = s, g, ruw
    c.render.max_depth = depth
    return c


def render(cfg: TableConfig, zaad: int, spp: int) -> tuple[np.ndarray, float]:
    from carbonne.core.scene import PLAAT_DIKTE, build_scene, effectieve_gap_mm

    sd = build_scene(cfg)
    if not isinstance(cfg.onderkant, PlateBelow):  # vloer net zo diep als bij een plaat (ray-epsilon, zie T04)
        y = -(effectieve_gap_mm(cfg, 0.1) / 1000.0 + PLAAT_DIKTE)
        sd["floor"]["to_world"] = (
            mi.ScalarTransform4f().translate([0, y, 0]).rotate([1, 0, 0], -90).scale(cfg.scene.vloer_grootte / 2)
        )
    t = time.perf_counter()
    img = np.array(mi.render(mi.load_dict(sd), spp=spp, seed=zaad))[..., :3]
    return img, time.perf_counter() - t


def run(res: int, spp: int, depth: int, reeks, onderkanten, figuur_dir: Path | None) -> list[dict]:
    rijen = []
    for camnaam, elev in CAMERAS.items():
        cam = zm.camera(elev)
        for onder in onderkanten:
            for naam, s, g, ruw in reeks:
                cfg = maak(onder, s, g, ruw, cam, res, spp, depth)
                uit = [render(cfg, z, spp) for z in zm.ZADEN]
                imgs = [u[0] for u in uit]
                metingen = [zm.meet(i, cam) for i in imgs]
                rij = {"camera": camnaam, "onderkant": onder, "variant": naam, "s": s, "g": g, "ruw": ruw,
                       "tijd_s": round(float(np.mean([u[1] for u in uit])), 2)}
                for roi in zm.ROIS:
                    a = np.mean([m[roi] for m in metingen], axis=0)
                    ruis = float(np.abs(metingen[0][roi] - metingen[1][roi]).mean() / 2)
                    rij[roi] = {"lum": round(float(zm.M_Y @ a), 5), "rood": round(float(a[0] / a.sum()), 4),
                                "ruis": round(ruis, 5)}
                rijen.append(rij)
                print(json.dumps(rij), flush=True)
                if figuur_dir is not None:
                    figuur_dir.mkdir(parents=True, exist_ok=True)
                    np.save(figuur_dir / f"{camnaam}-{onder}-{naam}.npy", ((imgs[0] + imgs[1]) / 2).astype(np.float32))
    return rijen


def tabel(rijen: list[dict]) -> str:
    regels = []
    for cam in CAMERAS:
        for onder in ONDER:
            sel = [r for r in rijen if r["camera"] == cam and r["onderkant"] == onder]
            if not sel:
                continue
            regels += [f"### {onder}, camera {cam}", "",
                       "| variant | " + " | ".join(f"{r} rood (lum, ruis)" for r in zm.ROIS) + " | s/beeld |",
                       "|---|" + "---|" * (len(zm.ROIS) + 1)]
            for r in sel:
                cel = " | ".join(f"{r[n]['rood']:.3f} ({r[n]['lum']:.3f}, {r[n]['ruis']:.4f})" for n in zm.ROIS)
                regels.append(f"| {r['variant']} | {cel} | {r['tijd_s']} |")
            regels.append("")
    return "\n".join(regels)


def figuur(dir_: Path, pad: Path, onder: str, varianten: list[str]) -> None:
    """Raster: rijen = camera (boven, schuin), kolommen = varianten; sRGB, 8 bit."""
    rijen = []
    for cam in CAMERAS:
        rijen.append(np.concatenate([np.load(dir_ / f"{cam}-{onder}-{v}.npy") for v in varianten], axis=1))
    img = np.concatenate(rijen, axis=0)
    h, w = img.shape[0] // 2 * 2, img.shape[1] // 2 * 2
    img = img[:h, :w].reshape(h // 2, 2, w // 2, 2, 3).mean(axis=(1, 3))  # 2x2-middeling: kleiner PNG, minder ruis
    pad.parent.mkdir(parents=True, exist_ok=True)
    mi.Bitmap(img).convert(mi.Bitmap.PixelFormat.RGB, mi.Struct.Type.UInt8, srgb_gamma=True).write(str(pad))


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--res", type=int, default=160)
    p.add_argument("--spp", type=int, default=512)
    p.add_argument("--max-depth", type=int, default=64)
    p.add_argument("--out", type=Path, default=Path("out/t17"))
    p.add_argument("--onder", nargs="+", default=list(ONDER))
    p.add_argument("--varianten", nargs="+", default=[r[0] for r in REEKS if r[0] not in ("s1", "s2")])
    p.add_argument("--figuur", type=Path, default=None)
    p.add_argument("--figuur-onder", default="plaat")
    p.add_argument("--figuur-varianten", nargs="+", default=["s0", "s5", "s20"])
    a = p.parse_args()
    select_variant()
    reeks = [r for r in REEKS if r[0] in a.varianten]
    rijen = run(a.res, a.spp, a.max_depth, reeks, a.onder, a.out)
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "metingen.json").write_text(json.dumps(rijen, indent=1))
    t = tabel(rijen)
    (a.out / "metingen.md").write_text(t)
    print(t)
    if a.figuur:
        figuur(a.out, a.figuur, a.figuur_onder, a.figuur_varianten)


if __name__ == "__main__":
    main()
