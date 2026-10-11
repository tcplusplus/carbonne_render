"""T04: A/B-experiment. Zwart geverfd versus zwarte plaat met luchtspleet, met en zonder gekleurde zijkant.

Gebruik: uv run python scripts/ab_experiment.py [--res 320] [--spp 1024] [--out docs/evidence/img/T04-ab.png]

Vaste camera (steil van boven), constante witte omgeving, zwarte vloer, hetzelfde zaad en aantal samples voor elke
variant. Gemeten wordt in een vast ROI in het midden van het bovenvlak (ver van de rand). Elke variant wordt met
twee zaden gerenderd; het verschil geeft de ruis van de ROI-meting.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import mitsuba as mi
import numpy as np

from carbonne.core.config import Bare, CameraConfig, MatteClearCoat, Paint, PlateBelow, TableConfig
from carbonne.core.scene import build_scene
from carbonne.core.variant import select_variant

ZWART = (0.03, 0.03, 0.03)
ROOD = (0.75, 0.04, 0.04)
WIT = (0.9, 0.9, 0.9)
SPLEET_MM = 0.1  # wordt door effectieve_gap_mm verhoogd tot de veilige minimale spleet
ROI_HALF = 0.06  # halve breedte van het ROI als fractie van de beeldbreedte
ZADEN = (3, 11)

# (code, omschrijving, zijkant, onderkant)
VARIANTEN = [
    ("0", "referentie: zijkant onbehandeld, onder onbehandeld", Bare(), Bare()),
    ("A1", "onder zwart geverfd, zijkant onbehandeld", Bare(), Paint(color=ZWART)),
    ("A2", "zwarte plaat met luchtspleet, zijkant onbehandeld", Bare(), PlateBelow(color=ZWART, gap_mm=SPLEET_MM)),
    ("B1", "onder zwart geverfd, zijkant rood", Paint(color=ROOD), Paint(color=ZWART)),
    ("B2", "zwarte plaat met luchtspleet, zijkant rood", Paint(color=ROOD), PlateBelow(color=ZWART, gap_mm=SPLEET_MM)),
    ("C", "onder kleurloze matte lak (zwarte vloer), zijkant onbehandeld", Bare(), MatteClearCoat()),
    ("C-rood", "onder kleurloze matte lak (zwarte vloer), zijkant rood", Paint(color=ROOD), MatteClearCoat()),
    # aanvulling: lichte onderkant, zodat er veel licht in het blok zit dat de zijkant kan bereiken
    ("W1", "onder wit geverfd, zijkant onbehandeld", Bare(), Paint(color=WIT)),
    ("W2", "witte plaat met luchtspleet, zijkant onbehandeld", Bare(), PlateBelow(color=WIT, gap_mm=SPLEET_MM)),
    ("WB1", "onder wit geverfd, zijkant rood", Paint(color=ROOD), Paint(color=WIT)),
    ("WB2", "witte plaat met luchtspleet, zijkant rood", Paint(color=ROOD), PlateBelow(color=WIT, gap_mm=SPLEET_MM)),
]
OFFSETS = (0.0, 0.1, 0.2, 0.25)  # ROI-middens, als fractie van de beeldbreedte zijwaarts van het midden (rand op ~0,32)

M_RGB_XYZ = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]])


def maak_config(zijkant, onderkant, res: int, spp: int) -> TableConfig:
    cfg = TableConfig(zijkant=zijkant, onderkant=onderkant)
    cfg.scene.camera = CameraConfig(positie=(0.0, 0.75, 0.2), doel=(0.0, 0.04, 0.0), fov=40.0)
    cfg.scene.vloer_albedo = ZWART
    cfg.scene.vloer_lijn_albedo = ZWART
    cfg.render.breedte, cfg.render.hoogte, cfg.render.spp = res, res * 3 // 4, spp
    return cfg


def roi(img: np.ndarray, offset: float = 0.0) -> np.ndarray:
    """Gemiddelde lineaire RGB in het ROI: vierkant rond het beeldmidden (= midden van het bovenvlak),
    eventueel `offset` x beeldbreedte zijwaarts."""
    h, w = img.shape[:2]
    a = max(2, round(ROI_HALF * w))
    cx = w // 2 + round(offset * w)
    return img[h // 2 - a : h // 2 + a, cx - a : cx + a, :3].mean(axis=(0, 1))


def vloer_omlaag(sc: dict, cfg: TableConfig) -> None:
    """Zet de vloer even diep als bij een plaat met spleet (A2/B2). Bij onderkant Bare/lak valt de vloer anders
    samen met het onderste vlak van het blok, en Mitsuba's ray-epsilon laat stralen dan door de vloer heen
    in de witte omgeving erachter lopen (de 'zwarte vloer' is dan niet zwart)."""
    from carbonne.core.scene import PLAAT_DIKTE, effectieve_gap_mm

    y = -(effectieve_gap_mm(cfg, SPLEET_MM) / 1000.0 + PLAAT_DIKTE)
    g = cfg.scene.vloer_grootte / 2
    sc["floor"]["to_world"] = mi.ScalarTransform4f().translate([0, y, 0]).rotate([1, 0, 0], -90).scale(g)


def luminantie(rgb: np.ndarray) -> float:
    return float(M_RGB_XYZ[1] @ rgb)


def chromaticiteit(rgb: np.ndarray) -> tuple[float, float]:
    x, y, z = M_RGB_XYZ @ rgb
    return float(x / (x + y + z)), float(y / (x + y + z))


def run(res: int, spp: int, codes: tuple[str, ...] | None = None, zaden: tuple[int, ...] = ZADEN):
    rijen, beelden = [], []
    for code, omschrijving, z, o in VARIANTEN:
        if codes is not None and code not in codes:
            continue
        cfg = maak_config(z, o, res, spp)
        sd = build_scene(cfg)
        if not isinstance(o, PlateBelow):
            vloer_omlaag(sd, cfg)
        scene = mi.load_dict(sd)
        imgs = [np.array(mi.render(scene, spp=spp, seed=s))[..., :3] for s in zaden]
        rgbs = [roi(i) for i in imgs]
        rgb = np.mean(rgbs, axis=0)
        ruis = np.abs(rgbs[0] - rgbs[1]) / 2 if len(rgbs) > 1 else 0 * rgb  # ruwe maat voor de standaardfout van het gemiddelde van 2 zaden
        x, y = chromaticiteit(rgb)
        profiel = [np.mean([roi(i, f) for i in imgs], axis=0) for f in OFFSETS]
        rijen.append(
            {
                "rood_profiel": [round(float(q[0] / q.sum()), 4) for q in profiel],
                "lum_profiel": [round(luminantie(q), 4) for q in profiel],
                "code": code,
                "omschrijving": omschrijving,
                "rgb": rgb.round(5).tolist(),
                "luminantie": round(luminantie(rgb), 5),
                "ruis_luminantie": round(float(M_RGB_XYZ[1] @ ruis), 5),
                "x": round(x, 4),
                "y": round(y, 4),
                "rood_aandeel": round(float(rgb[0] / rgb.sum()), 4),
            }
        )
        beelden.append(imgs[0])
        print(rijen[-1], flush=True)
    return rijen, beelden


def tabel(rijen: list[dict]) -> str:
    ref = {r["code"]: r for r in rijen}
    regels = [
        "| code | variant | R | G | B | luminantie | +- ruis | x | y | rood-aandeel |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rijen:
        regels.append(
            f"| {r['code']} | {r['omschrijving']} | {r['rgb'][0]:.4f} | {r['rgb'][1]:.4f} | {r['rgb'][2]:.4f} | "
            f"{r['luminantie']:.4f} | {r['ruis_luminantie']:.4f} | {r['x']:.4f} | {r['y']:.4f} | {r['rood_aandeel']:.4f} |"
        )

    def verhouding(a: str, b: str) -> str:
        return f"{ref[b]['luminantie'] / ref[a]['luminantie']:.3f}"

    def dxy(a: str, b: str) -> str:
        return f"{np.hypot(ref[b]['x'] - ref[a]['x'], ref[b]['y'] - ref[a]['y']):.4f}"

    regels += [
        "",
        f"- Luminantie A2/A1 (plaat t.o.v. verf, zijkant onbehandeld): {verhouding('A1', 'A2')}",
        f"- Luminantie B2/B1 (plaat t.o.v. verf, zijkant rood): {verhouding('B1', 'B2')}",
        "- Chromaticiteitsverschuiving door de rode zijkant, afstand in xy: "
        + f"verf B1 t.o.v. A1: {dxy('A1', 'B1')}; plaat B2 t.o.v. A2: {dxy('A2', 'B2')}",
        "- Rood-aandeel R/(R+G+B): "
        + ", ".join(f"{c} {ref[c]['rood_aandeel']}" for c in ("A1", "B1", "A2", "B2")),
        "- Rood-aandeel langs het bovenvlak (ROI-midden 0 / 0,1 / 0,2 / 0,25 beeldbreedte van het midden; rand op ~0,32):",
        *[f"  - {r['code']}: {r['rood_profiel']} (luminantie {r['lum_profiel']})" for r in rijen],
        "- Matte lak (C) tussen verf en plaat, luminantie: "
        + ", ".join(f"{c} {ref[c]['luminantie']:.4f}" for c in ("A1", "C", "A2")),
    ]
    return "\n".join(regels)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--res", type=int, default=320)
    p.add_argument("--spp", type=int, default=1024)
    p.add_argument("--schaal", type=float, default=1.0, help="verklein het rasterbeeld (bestandsgrootte)")
    p.add_argument("--out", type=Path, default=Path("out/t04-ab.png"))
    a = p.parse_args()
    print("variant:", select_variant())
    rijen, beelden = run(a.res, a.spp)
    tekst = tabel(rijen)
    print(tekst)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.with_suffix(".json").write_text(json.dumps(rijen, indent=1, ensure_ascii=False))
    a.out.with_suffix(".md").write_text(tekst + "\n")
    # raster: 8 per rij; ROI als wit kader is niet getekend (vast midden)
    leeg = np.zeros_like(beelden[0])
    rij = [np.concatenate(beelden[i : i + 4] + [leeg] * max(0, i + 4 - len(beelden)), axis=1) for i in range(0, len(beelden), 4)]
    raster = mi.Bitmap(np.concatenate(rij, axis=0).astype(np.float32))
    if a.schaal != 1.0:
        raster = raster.resample([int(raster.width() * a.schaal), int(raster.height() * a.schaal)])
    raster.convert(
        mi.Bitmap.PixelFormat.RGB, mi.Struct.Type.UInt8, srgb_gamma=True
    ).write(str(a.out))
    print("->", a.out)


if __name__ == "__main__":
    main()
