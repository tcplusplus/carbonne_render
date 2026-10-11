"""T05 (vervolgmeting uit T04-1): kleur van de rode zijkant gemeten VANAF DE ZIJKANT en vlak langs de rand.

Gebruik: uv run python scripts/zijkant_meting.py [--res 512] [--spp 512] [--out out/t05-zijkant]

T04 mat alleen van boven in het midden van het bovenvlak, waar licht dat door totale interne reflectie (TIR) in
het blok gevangen zit niet uit kan. Hier kijkt de camera schuin (35 graden boven de horizon) of op ooghoogte
(12 graden), en meten we per variant in kleine meetgebieden (ROI's):
  mantel      de rode zijkant zelf (voor), midden
  rand_voor   bovenvlak, 8 mm achter de voorrand (je kijkt door het vlak naar binnen)
  rand_achter bovenvlak, 8 mm voor de achterrand
  midden      bovenvlak, midden
Onderkanten: contact (verf in contact), plaat (met luchtspleet), lak (kleurloze matte lak), bare (onbehandeld),
elk met een zwarte en een witte ondergrond. Per variant ook de referentie met onbehandelde zijkant, zodat
zichtbaar wordt wat de rode zijkant toevoegt. Constante witte omgeving, zelfde zaden voor alle varianten.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import mitsuba as mi
import numpy as np

from carbonne.core.config import Bare, CameraConfig, MatteClearCoat, Paint, PlateBelow, TableConfig
from carbonne.core.scene import PLAAT_DIKTE, build_scene, effectieve_gap_mm
from carbonne.core.variant import select_variant

ZWART = (0.03, 0.03, 0.03)
WIT = (0.9, 0.9, 0.9)
ROOD = (0.75, 0.04, 0.04)
D, H = 0.35, 0.04
R = D / 2
ZADEN = (3, 11)
M_Y = np.array([0.2126, 0.7152, 0.0722])

CAMERAS = {
    "schuin35": 35.0,  # graden boven de horizon
    "ooghoogte12": 12.0,
}
ROIS = {  # naam -> wereldpunt (x=0, y, z); z>0 is de voorkant
    "mantel": (0.0, H / 2, R),
    "rand_voor": (0.0, H, R - 0.008),
    "midden": (0.0, H, 0.0),
    "rand_achter": (0.0, H, -R + 0.008),
}


def camera(elev_deg: float, afstand: float = 0.75) -> CameraConfig:
    e = np.radians(elev_deg)
    doel = np.array([0.0, H / 2, 0.0])
    pos = doel + afstand * np.array([0.0, np.sin(e), np.cos(e)])
    return CameraConfig(positie=tuple(pos), doel=tuple(doel), fov=38.0)


def pixel_rij(cam: CameraConfig, p: tuple[float, float, float], res_x: int, res_y: int) -> tuple[int, int]:
    """Beeldpositie (kolom, rij) van een wereldpunt met x=0 (dan is alleen de verticale schaal relevant)."""
    o, t = np.array(cam.positie), np.array(cam.doel)
    f = (t - o) / np.linalg.norm(t - o)
    up = np.cross(np.cross(f, [0, 1, 0]), f)
    up /= np.linalg.norm(up)
    d = np.array(p) - o
    schaal = (res_x / 2) / np.tan(np.radians(cam.fov) / 2)
    return res_x // 2, round(res_y / 2 - (d @ up) / (d @ f) * schaal)


# (code, onderkant-factory(kleur)); de ondergrond (vloer) is zwart of wit
ONDERKANTEN = {
    "contact": lambda k: Paint(color=k),
    "plaat": lambda k: PlateBelow(color=k, gap_mm=0.1),
    "lak": lambda k: MatteClearCoat(),
    "bare": lambda k: Bare(),
}


def maak_config(zijkant, onderkant, vloer, cam, res, spp) -> TableConfig:
    c = TableConfig(diameter=D, hoogte=H, zijkant=zijkant, onderkant=onderkant)
    c.scene.camera = cam
    c.scene.vloer_albedo = c.scene.vloer_lijn_albedo = vloer
    c.render.breedte, c.render.hoogte, c.render.spp = res, res * 3 // 4, spp
    return c


def render(cfg: TableConfig, zaad: int, spp: int) -> np.ndarray:
    sd = build_scene(cfg)
    if not isinstance(cfg.onderkant, PlateBelow):  # vloer net zo diep als bij een plaat (ray-epsilon, zie T04)
        y = -(effectieve_gap_mm(cfg, 0.1) / 1000.0 + PLAAT_DIKTE)
        sd["floor"]["to_world"] = (
            mi.ScalarTransform4f().translate([0, y, 0]).rotate([1, 0, 0], -90).scale(cfg.scene.vloer_grootte / 2)
        )
    return np.array(mi.render(mi.load_dict(sd), spp=spp, seed=zaad))[..., :3]


def meet(img: np.ndarray, cam: CameraConfig, half: int = 3) -> dict:
    h, w = img.shape[:2]
    uit = {}
    for naam, p in ROIS.items():
        x, y = pixel_rij(cam, p, w, h)
        rgb = img[y - half : y + half + 1, x - half : x + half + 1].mean(axis=(0, 1))
        uit[naam] = rgb
    return uit


def run(res: int, spp: int, out: Path) -> list[dict]:
    rijen = []
    for camnaam, elev in CAMERAS.items():
        cam = camera(elev)
        for onder, maker in ONDERKANTEN.items():
            for tint, kleur in (("zwart", ZWART), ("wit", WIT)):
                for zijde, zijkant in (("rood", Paint(color=ROOD)), ("bare", Bare())):
                    vloer = kleur if onder in ("lak", "bare") else ZWART
                    cfg = maak_config(zijkant, maker(kleur), vloer, cam, res, spp)
                    imgs = [render(cfg, z, spp) for z in ZADEN]
                    metingen = [meet(i, cam) for i in imgs]
                    rij = {"camera": camnaam, "onderkant": onder, "ondergrond": tint, "zijkant": zijde}
                    for naam in ROIS:
                        a = np.mean([m[naam] for m in metingen], axis=0)
                        ruis = float(np.abs(metingen[0][naam] - metingen[1][naam]).mean() / 2)
                        rij[naam] = {
                            "lum": round(float(M_Y @ a), 5),
                            "rood": round(float(a[0] / a.sum()), 4),
                            "ruis": round(ruis, 5),
                        }
                    rijen.append(rij)
                    print(rij, flush=True)
                    if zijde == "rood" and tint == "wit" and onder == "contact":  # beeld om de ROI's te controleren
                        _markeer(imgs[0], cam, out.with_name(f"{out.name}-{camnaam}.png"))
    return rijen


def _markeer(img: np.ndarray, cam: CameraConfig, pad: Path, half: int = 3) -> None:
    img = img.copy()
    h, w = img.shape[:2]
    for p in ROIS.values():
        x, y = pixel_rij(cam, p, w, h)
        img[y - half - 1 : y + half + 2, x - half - 1 : x + half + 2] = [0, 1, 0]
        img[y - half : y + half + 1, x - half : x + half + 1] = img[y, x] * 0 + [0, 0, 0]
    pad.parent.mkdir(parents=True, exist_ok=True)
    mi.Bitmap(img.astype(np.float32)).convert(mi.Bitmap.PixelFormat.RGB, mi.Struct.Type.UInt8, srgb_gamma=True).write(str(pad))


def tabel(rijen: list[dict]) -> str:
    regels = []
    for camnaam in CAMERAS:
        regels += [
            f"### Camera {camnaam}",
            "",
            "| onderkant | ondergrond | zijkant | " + " | ".join(f"{r} lum / rood" for r in ROIS) + " |",
            "|---|---|---|" + "---|" * len(ROIS),
        ]
        for r in rijen:
            if r["camera"] != camnaam:
                continue
            cellen = " | ".join(f"{r[n]['lum']:.4f} / {r[n]['rood']:.3f}" for n in ROIS)
            regels.append(f"| {r['onderkant']} | {r['ondergrond']} | {r['zijkant']} | {cellen} |")
        regels.append("")
    return "\n".join(regels)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--res", type=int, default=512)
    p.add_argument("--spp", type=int, default=512)
    p.add_argument("--out", type=Path, default=Path("out/t05-zijkant"))
    a = p.parse_args()
    select_variant()
    rijen = run(a.res, a.spp, a.out)
    a.out.with_suffix(".json").write_text(json.dumps(rijen, indent=1))
    t = tabel(rijen)
    a.out.with_suffix(".md").write_text(t)
    print(t)


if __name__ == "__main__":
    main()
