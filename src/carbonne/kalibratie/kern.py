"""Kalibratie met een gsm-foto (T12).

Idee: een foto bevat een onbekende lichtkleur en belichting, en de gsm past tonemapping toe. Een wit A4 naast het
tafeltje, op dezelfde ondergrond en in hetzelfde licht, is de referentie. We normaliseren per kleurkanaal zo dat het
papier de bekende albedo `PAPIER_ALBEDO` krijgt (witbalans + belichting in een stap, in lineair licht). Een verfstaal
dat naast het papier ligt krijgt dan direct zijn albedo: de **gemeten verfkleur**. De render wordt op dezelfde manier
genormaliseerd op een vlak met bekende albedo (de vloer, met `vloer_albedo` = papieralbedo), zodat foto en render in
dezelfde eenheid staan en per gebied vergeleken kunnen worden (CIEDE2000).

Beperking (eerlijk): een enkele versterking per kanaal herstelt alleen een lineaire afwijking. Tonemapping van de gsm
(S-curve, lokaal contrast, HDR) is niet-lineair en blijft als restfout over; zie docs/kalibratie.md.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from carbonne.analyse.reeks import delta_e2000, lch
from carbonne.core.herkomst import lineair_naar_lab
from carbonne.core.kleur import lineair_naar_srgb
from carbonne.render.uitvoer import png_bytes, tonemap_srgb

PAPIER_ALBEDO = 0.85  # typisch kopieerpapier (80 g/m2), diffuus; door de gebruiker te overschrijven
ROI = tuple[int, int, int, int]  # x0, y0, x1, y1 in pixels (x1, y1 exclusief)


# ---------------------------------------------------------------------------------------------------------------
# Laden en normaliseren


def srgb_naar_lineair_arr(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, np.float64)
    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)


def lineair_naar_srgb_arr(x: np.ndarray) -> np.ndarray:
    x = np.clip(np.asarray(x, np.float64), 0.0, 1.0)
    return np.where(x <= 0.0031308, 12.92 * x, 1.055 * np.power(x, 1 / 2.4) - 0.055)


def laad_foto(pad) -> np.ndarray:
    """PNG/JPEG (8 bit, sRGB) -> lineair RGB (h, w, 3), float64. Leest via Mitsuba's Bitmap (geen extra bibliotheek).
    RAW/DNG wordt niet gelezen: exporteer eerst naar JPEG/PNG met een neutrale sRGB-curve (zie docs/kalibratie.md)."""
    import mitsuba as mi

    from carbonne.core.variant import select_variant

    select_variant()
    bmp = mi.Bitmap(str(pad))
    # srgb_gamma=False: Mitsuba decodeert de sRGB-curve van 8-bit bestanden zelf; de uitkomst is dus al lineair
    bmp = bmp.convert(mi.Bitmap.PixelFormat.RGB, mi.Struct.Type.Float32, srgb_gamma=False)
    return np.array(bmp, dtype=np.float64)[..., :3]


def parse_hex(h: str) -> tuple[float, float, float]:
    """`#rrggbb` -> lineair RGB."""
    from carbonne.core.kleur import hex_naar_lineair

    return hex_naar_lineair(h)


def klem_roi(img: np.ndarray, roi: ROI) -> ROI:
    h, w = img.shape[:2]
    x0, y0, x1, y1 = (int(v) for v in roi)
    x0, x1 = sorted((max(0, min(w, x0)), max(0, min(w, x1))))
    y0, y1 = sorted((max(0, min(h, y0)), max(0, min(h, y1))))
    if x1 - x0 < 1 or y1 - y0 < 1:
        raise ValueError(f"gebied {roi} ligt buiten het beeld ({w}x{h}) of is leeg")
    return x0, y0, x1, y1


def roi_gemiddelde(img: np.ndarray, roi: ROI) -> np.ndarray:
    """Gemiddelde lineaire RGB in een gebied."""
    x0, y0, x1, y1 = klem_roi(img, roi)
    return img[y0:y1, x0:x1, :3].reshape(-1, 3).mean(axis=0)


def normaliseer(img: np.ndarray, papier_roi: ROI, papier_albedo: float = PAPIER_ALBEDO) -> np.ndarray:
    """Per kanaal vermenigvuldigen zodat het gemiddelde in `papier_roi` gelijk wordt aan `papier_albedo`."""
    p = roi_gemiddelde(img, papier_roi)
    if np.any(p <= 1e-4):
        raise ValueError("het papiergebied is (bijna) zwart; klik op het witte papier")
    if np.any(p > 0.98):
        raise ValueError("het papier is overbelicht (een kanaal staat op het maximum); fotografeer donkerder")
    return img[..., :3] * (papier_albedo / p)


def rgb_naar_hex(lin) -> str:
    return "#" + "".join(f"{round(lineair_naar_srgb(float(min(max(c, 0.0), 1.0))) * 255):02x}" for c in lin)


def meet_verfkleur(foto: np.ndarray, papier_roi: ROI, staal_roi: ROI, papier_albedo: float = PAPIER_ALBEDO) -> dict:
    """De gemeten verfkleur (albedo, lineair RGB) uit een foto met papier en verfstaal."""
    norm = normaliseer(foto, papier_roi, papier_albedo)
    ruw = roi_gemiddelde(norm, staal_roi)
    rgb = np.clip(ruw, 0.0, 1.0)
    x0, y0, x1, y1 = klem_roi(norm, staal_roi)
    sd = norm[y0:y1, x0:x1].reshape(-1, 3).std(axis=0)
    return {"rgb": tuple(float(c) for c in rgb), "hex": rgb_naar_hex(rgb), "afgekapt": bool(np.any(ruw > 1.0)),
            "spreiding_in_staal": tuple(float(s) for s in sd)}


# ---------------------------------------------------------------------------------------------------------------
# Vergelijken


@dataclass
class Verschil:
    naam: str
    rgb_foto: tuple[float, float, float]
    rgb_render: tuple[float, float, float]
    de2000: float
    d_l: float  # L*foto - L*render (positief: foto lichter)
    d_c: float  # C*foto - C*render (positief: foto verzadigder)
    d_h: float  # hoek foto - render in graden, -180..180
    verf: str | None = None  # "zijkant" | "onderkant": welke verf dit gebied bepaalt

    def tekst(self) -> str:
        return (f"{self.naam:14} dE2000 {self.de2000:5.2f}  dL {self.d_l:+6.1f}  dC {self.d_c:+6.1f}  "
                f"dh {self.d_h:+6.1f}  foto {rgb_naar_hex(self.rgb_foto)} render {rgb_naar_hex(self.rgb_render)}")


def vergelijk(foto_norm: np.ndarray, render_norm: np.ndarray, gebieden: list[dict]) -> list[Verschil]:
    """`gebieden`: [{"naam", "foto": ROI, "render": ROI, "verf": optioneel}]. Beide beelden zijn genormaliseerd."""
    uit = []
    for g in gebieden:
        f = roi_gemiddelde(foto_norm, tuple(g["foto"]))
        r = roi_gemiddelde(render_norm, tuple(g["render"]))
        lf, lr = lineair_naar_lab(f), lineair_naar_lab(r)
        cf, cr = lch(lf), lch(lr)
        dh = (cf[2] - cr[2] + 180.0) % 360.0 - 180.0
        uit.append(Verschil(g["naam"], tuple(float(v) for v in f), tuple(float(v) for v in r),
                            delta_e2000(lr, lf), cf[0] - cr[0], cf[1] - cr[1], dh, g.get("verf")))
    return uit


def bijgestelde_verf(oud_rgb, foto_rgb, render_rgb) -> tuple[float, float, float]:
    """Eerste-orde bijstelling: de verfalbedo per kanaal schalen met foto/render (de render is bij benadering
    lineair in de albedo). Eventueel herhalen met een nieuwe render (zie `carbonne-kalibreer bijstellen`)."""
    f, r, o = (np.asarray(v, float) for v in (foto_rgb, render_rgb, oud_rgb))
    return tuple(float(c) for c in np.clip(o * f / np.maximum(r, 1e-4), 0.0, 1.0))


# ---------------------------------------------------------------------------------------------------------------
# Synthetische foto (voor tests en voor de evidence)


def synthetische_foto(render_lin: np.ndarray, versterking=(1.0, 1.0, 1.0), ev: float = 0.0, s_curve: float = 0.0,
                      vlakken: dict[ROI, tuple[float, float, float]] | None = None) -> np.ndarray:
    """Maak van een lineaire render een nep-gsmfoto: kleurafwijking (versterking per kanaal), belichting, een zachte
    S-curve (tonemapping van de gsm, `s_curve` 0..1) en 8-bit sRGB-codering. `vlakken`: ROI -> lineaire albedo,
    ingetekend als verfstaal onder hetzelfde licht als het papier (staal = albedo x lichtniveau van het papier)."""
    img = render_lin[..., :3].astype(np.float64).copy()
    for roi, alb in (vlakken or {}).items():
        x0, y0, x1, y1 = roi
        img[y0:y1, x0:x1] = np.asarray(alb) * 1.0
    img = img * np.asarray(versterking) * 2.0**ev
    x = np.clip(img, 0.0, 1.0)
    x = (1 - s_curve) * x + s_curve * (x * x * (3 - 2 * x))
    return tonemap_srgb(x)


def foto_naar_png(img8: np.ndarray) -> bytes:
    return png_bytes(img8)


# ---------------------------------------------------------------------------------------------------------------
# Beeld met cijfers (zonder lettertypebibliotheek: een 3x5-cijferlettertype)

_GLYF = {
    "0": "111101101101111", "1": "010110010010111", "2": "111001111100111", "3": "111001111001111",
    "4": "101101111001001", "5": "111100111001111", "6": "111100111101111", "7": "111001001001001",
    "8": "111101111101111", "9": "111101111001111", ".": "000000000000010", "-": "000000111000000",
    "+": "000010111010000", " ": "0" * 15, "x": "000101010101000", "d": "001001111101111",
}


def teken_tekst(img8: np.ndarray, tekst: str, x: int, y: int, schaal: int = 3, kleur=(255, 255, 255),
                achter=(0, 0, 0)) -> None:
    """Tekent cijfers/tekens in het beeld (in place), met een donkere achtergrond voor leesbaarheid."""
    h, w = img8.shape[:2]
    breedte = len(tekst) * 4 * schaal + schaal
    x0, y0, x1, y1 = max(0, x - schaal), max(0, y - schaal), min(w, x + breedte), min(h, y + 6 * schaal)
    if x1 <= x0 or y1 <= y0:
        return
    img8[y0:y1, x0:x1] = achter
    for i, ch in enumerate(tekst.lower()):
        bits = _GLYF.get(ch, _GLYF[" "])
        for k, b in enumerate(bits):
            if b == "1":
                px, py = x + (i * 4 + k % 3) * schaal, y + (k // 3) * schaal
                img8[max(0, py):max(0, min(h, py + schaal)), max(0, px):max(0, min(w, px + schaal))] = kleur


def teken_kader(img8: np.ndarray, roi: ROI, kleur=(255, 220, 0), dikte: int = 2) -> None:
    x0, y0, x1, y1 = klem_roi(img8, roi)
    for d in range(dikte):
        img8[y0 + d : y0 + d + 1, x0:x1] = kleur
        img8[max(y1 - 1 - d, 0) : y1 - d, x0:x1] = kleur
        img8[y0:y1, x0 + d : x0 + d + 1] = kleur
        img8[y0:y1, max(x1 - 1 - d, 0) : x1 - d] = kleur


def raster_beeld(img8: np.ndarray, stap: int = 50) -> np.ndarray:
    """Beeld met een coordinatenraster, om de pixelcoordinaten van papier, staal en gebieden af te lezen."""
    uit = img8.copy()
    h, w = uit.shape[:2]
    for x in range(0, w, stap):
        uit[:, x : x + 1] = (uit[:, x : x + 1] * 0.5 + np.array([128, 128, 0]) * 0.5).astype(np.uint8)
        teken_tekst(uit, str(x), x + 2, 2, 2)
    for y in range(0, h, stap):
        uit[y : y + 1] = (uit[y : y + 1] * 0.5 + np.array([128, 128, 0]) * 0.5).astype(np.uint8)
        teken_tekst(uit, str(y), 2, y + 2, 2)
    return uit


def _schaal_naar_hoogte(img8: np.ndarray, hoogte: int) -> tuple[np.ndarray, float]:
    f = hoogte / img8.shape[0]
    w = max(1, round(img8.shape[1] * f))
    yi = np.minimum((np.arange(hoogte) / f).astype(int), img8.shape[0] - 1)
    xi = np.minimum((np.arange(w) / f).astype(int), img8.shape[1] - 1)
    return img8[yi][:, xi], f


def vergelijkingsbeeld(foto_norm: np.ndarray, render_norm: np.ndarray, gebieden: list[dict],
                       verschillen: list[Verschil], hoogte: int = 300) -> np.ndarray:
    """Foto en render naast elkaar (beide genormaliseerd op het papier) met de gebieden omkaderd, en eronder per
    gebied twee vlakjes (foto links, render rechts) met de dE2000 als getal."""
    fo, rn = tonemap_srgb(foto_norm), tonemap_srgb(render_norm)
    delen = []
    for beeld, sleutel in ((fo, "foto"), (rn, "render")):
        kopie = beeld.copy()
        for i, g in enumerate(gebieden):
            teken_kader(kopie, tuple(g[sleutel]))
        s, f = _schaal_naar_hoogte(kopie, hoogte)
        for i, g in enumerate(gebieden):
            x0, y0, _, _ = klem_roi(kopie, tuple(g[sleutel]))
            teken_tekst(s, str(i + 1), round(x0 * f) + 2, round(y0 * f) + 2, 2, (255, 220, 0))
        delen.append(s)
    breedte = delen[0].shape[1] + 8 + delen[1].shape[1]
    top = np.full((hoogte, breedte, 3), 40, np.uint8)
    top[:, : delen[0].shape[1]] = delen[0]
    top[:, delen[0].shape[1] + 8 :] = delen[1]
    rij_h = 40
    onder = np.full((rij_h * max(len(verschillen), 1) + 4, breedte, 3), 40, np.uint8)
    for i, v in enumerate(verschillen):
        y = 2 + i * rij_h
        onder[y : y + rij_h - 4, 40:140] = tonemap_srgb(np.array([[v.rgb_foto]]))[0]
        onder[y : y + rij_h - 4, 140:240] = tonemap_srgb(np.array([[v.rgb_render]]))[0]
        teken_tekst(onder, str(i + 1), 12, y + 8, 3, (255, 220, 0))
        teken_tekst(onder, f"{v.de2000:.1f}", 256, y + 8, 3)
    return np.concatenate([top, onder], axis=0)

