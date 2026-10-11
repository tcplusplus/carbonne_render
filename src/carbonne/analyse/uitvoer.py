"""Uitvoer van een wat-als-reeks: contactblad, grafiek en JSON. Tekent met het 5x7-lettertype uit `herkomst_cli`."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from carbonne.analyse.reeks import ReeksResultaat
from carbonne.core.herkomst_cli import _FONT, kruisje, staal_rgb8, tekst
from carbonne.render.uitvoer import png_bytes, tonemap_srgb

_FONT["°"] = np.array([[c == "#" for c in r] for r in [".##..", ".##..", ".....", ".....", ".....", ".....", "....."]])
_FONT["±"] = np.array([[c == "#" for c in r] for r in ["..#..", "..#..", "#####", "..#..", "..#..", ".....", "#####"]])
ACHTERGROND = (24, 24, 24)
PALET = [(230, 120, 60), (90, 170, 230), (120, 200, 110), (220, 190, 70), (190, 120, 220), (230, 100, 140),
         (150, 150, 150)]


def _markeer(img: np.ndarray, gebied, straal: float) -> None:
    h, w = img.shape[:2]
    if len(gebied) == 4:
        x0, y0, x1, y1 = (int(v) for v in gebied)
        for kl, d in (((0, 0, 0), 1), ((255, 255, 255), 0)):
            ya, yb, xa, xb = max(y0 - d, 0), min(y1 + d, h - 1), max(x0 - d, 0), min(x1 + d, w - 1)
            img[ya, xa : xb + 1] = kl
            img[yb, xa : xb + 1] = kl
            img[ya : yb + 1, xa] = kl
            img[ya : yb + 1, xb] = kl
    else:
        x, y = (round(v) for v in gebied)
        yy, xx = np.mgrid[0:h, 0:w]
        r2 = (xx - x) ** 2 + (yy - y) ** 2
        r = max(straal, 1.5)
        img[(r2 <= (r + 1.5) ** 2) & (r2 > r**2)] = (255, 255, 255)
        kruisje(img, x, y, int(r) + 5)


def contactblad_png(res: ReeksResultaat, ev: float = 0.0, per_rij: int = 5) -> bytes:
    """Een rij kleine renders met het gebied gemarkeerd; eronder de waarde, een kleurstaal en L*/C*/H, en ΔE."""
    n = len(res.metingen)
    if n == 0:
        raise ValueError("lege reeks")
    cw, ch, tekst_h = res.breedte, res.hoogte, 62
    kol = min(n, per_rij)
    rijen = -(-n // kol)
    uit = np.full((rijen * (ch + tekst_h), kol * cw, 3), ACHTERGROND, np.uint8)
    for i, (m, beeld) in enumerate(zip(res.metingen, res.beelden, strict=True)):
        r, k = divmod(i, kol)
        y0, x0 = r * (ch + tekst_h), k * cw
        img = tonemap_srgb(beeld, ev).copy()
        _markeer(img, res.gebied, res.straal)
        uit[y0 : y0 + ch, x0 : x0 + cw] = img
        uit[y0 : y0 + ch, x0] = ACHTERGROND  # dunne scheiding
        y = y0 + ch + 4
        tekst(uit, x0 + 6, y, m.label[: cw // 12 - 1], schaal=2)
        uit[y + 18 : y + 38, x0 + 6 : x0 + 30] = staal_rgb8(m.rgb)
        tekst(uit, x0 + 36, y + 17, f"L {m.lch[0]:.1f}  C {m.lch[1]:.1f}", schaal=1)
        tekst(uit, x0 + 36, y + 28, f"H {m.lch[2]:.0f}°  ±{m.ruis_lab:.1f}", (170, 170, 170), schaal=1)
        if r == 0 and k == 0:
            tekst(uit, x0 + 6, y + 42, "REFERENTIE", (170, 170, 170), schaal=1)
        else:
            kl = (230, 170, 80) if m.binnen_ruis else (255, 255, 255)
            tekst(uit, x0 + 6, y + 42, f"DE2000 {m.de2000:.1f}" + ("  BINNEN RUIS" if m.binnen_ruis else ""), kl,
                  schaal=1)
    return png_bytes(uit)


def _assen(p: np.ndarray, x0, y0, x1, y1, lo, hi, titel: str, fmt: str = "{:g}") -> None:
    p[y0:y1, x0] = (110, 110, 110)
    p[y1, x0 : x1 + 1] = (110, 110, 110)
    tekst(p, x0 - 4, y0 - 18, titel, schaal=1)
    for f in (0.0, 0.5, 1.0):
        y = int(y1 - f * (y1 - y0))
        p[y, x0 - 3 : x0] = (110, 110, 110)
        s = fmt.format(lo + f * (hi - lo))
        tekst(p, max(x0 - 6 - 6 * len(s), 0), y - 3, s, (170, 170, 170), schaal=1)


def grafiek_png(res: ReeksResultaat, min_aandeel_pct: float = 3.0) -> bytes:
    """Drie vlakken naast elkaar: L*, C* (met foutenbalk = standaardfout) en het aandeel (%) per herkomstcategorie
    tegenover de waarde. Is de parameter geen getal, dan staan de waarden op volgorde met hun naam onder de as."""
    ms = res.metingen
    if not ms:
        raise ValueError("lege reeks")
    getal = all(isinstance(m.waarde, (int, float)) and not isinstance(m.waarde, bool) for m in ms)
    xs = np.array([float(m.waarde) for m in ms]) if getal else np.arange(len(ms), dtype=float)
    if getal and len(ms) > 1 and xs.max() > xs.min():
        xn = (xs - xs.min()) / (xs.max() - xs.min())
    else:
        xn = np.linspace(0.1, 0.9, len(ms)) if len(ms) > 1 else np.array([0.5])
    breed, hoog, rl, rr, rb, rt = 400, 300, 56, 14, 56, 30
    namen = sorted({c.naam for m in ms for c in m.herkomst.categorieen if c.naam != "overig"})
    sterk = [nm for nm in namen if max((c.aandeel_pct for m in ms for c in m.herkomst.categorieen if c.naam == nm), default=0) >= min_aandeel_pct]
    sterk.sort(key=lambda nm: -max(c.aandeel_pct for m in ms for c in m.herkomst.categorieen if c.naam == nm))
    leg_h = 14 * len(sterk) + 8
    p = np.full((rt + hoog + rb + leg_h, 3 * breed, 3), ACHTERGROND, np.uint8)
    tekst(p, 8, 6, f"{res.parameter}  GEBIED {','.join(f'{v:g}' for v in res.gebied)}  {res.spp} SPP", schaal=1)

    def vlak(k, titel, reeksen, lo, hi, fmt="{:g}"):
        x0, x1 = k * breed + rl, (k + 1) * breed - rr
        y0, y1 = rt + 10, rt + hoog
        _assen(p, x0, y0, x1, y1, lo, hi, titel, fmt)
        for nm, ys, fouten, kl in reeksen:
            px = (x0 + xn * (x1 - x0)).astype(int)
            py = (y1 - (np.asarray(ys) - lo) / max(hi - lo, 1e-9) * (y1 - y0)).astype(int)
            for j in range(len(px) - 1):
                for t in np.linspace(0, 1, 60):
                    xx, yy = int(px[j] + t * (px[j + 1] - px[j])), int(py[j] + t * (py[j + 1] - py[j]))
                    p[yy, xx] = kl
            for j in range(len(px)):
                if fouten is not None:
                    e = int(2 * fouten[j] / max(hi - lo, 1e-9) * (y1 - y0))
                    p[max(py[j] - e, y0) : min(py[j] + e, y1) + 1, px[j]] = kl
                p[py[j] - 2 : py[j] + 3, px[j] - 2 : px[j] + 3] = kl
        for j, m in enumerate(ms):
            s = f"{float(m.waarde):g}" if getal else m.label[:9]
            if getal or len(ms) <= 6:
                tekst(p, int(x0 + xn[j] * (x1 - x0)) - 3 * len(s), y1 + 6 + (10 if j % 2 else 0), s, (170, 170, 170), schaal=1)

    def bereik(v, marge=0.1):
        lo, hi = float(np.min(v)), float(np.max(v))
        d = max(hi - lo, 1.0)
        return lo - marge * d, hi + marge * d

    L = [m.lch[0] for m in ms]
    C = [m.lch[1] for m in ms]
    # foutenbalk: de Lab-standaardfout, gelijk verdeeld (bovengrens voor L* en C* apart)
    err = [m.ruis_lab for m in ms]
    lo, hi = bereik(np.concatenate([np.array(L) - 2 * np.array(err), np.array(L) + 2 * np.array(err)]))
    vlak(0, "L* (BALK = 2 X RUIS)", [("L", L, err, PALET[0])], lo, hi, "{:.0f}")
    lo, hi = bereik(np.concatenate([np.array(C) - 2 * np.array(err), np.array(C) + 2 * np.array(err)]))
    vlak(1, "C* (BALK = 2 X RUIS)", [("C", C, err, PALET[1])], lo, hi, "{:.0f}")
    reeksen = []
    for i, nm in enumerate(sterk):
        ys = [next((c.aandeel_pct for c in m.herkomst.categorieen if c.naam == nm), 0.0) for m in ms]
        reeksen.append((nm, ys, None, PALET[i % len(PALET)]))
    vlak(2, "AANDEEL HERKOMST %", reeksen, 0.0, max(10.0, max((max(r[1]) for r in reeksen), default=10) * 1.1), "{:.0f}")
    y = rt + hoog + rb
    for i, nm in enumerate(sterk):
        kl = PALET[i % len(PALET)]
        p[y + 2 : y + 10, 2 * breed + rl : 2 * breed + rl + 14] = kl
        tekst(p, 2 * breed + rl + 22, y + 2, nm, schaal=1)
        y += 14
    return png_bytes(p)


def schrijf_reeks(res: ReeksResultaat, map_: Path, naam: str = "reeks", ev: float = 0.0) -> dict[str, Path]:
    """Schrijf `<naam>-contact.png`, `<naam>-grafiek.png` en `<naam>.json` in `map_`."""
    map_.mkdir(parents=True, exist_ok=True)
    pad = {"contact": map_ / f"{naam}-contact.png", "grafiek": map_ / f"{naam}-grafiek.png", "json": map_ / f"{naam}.json"}
    pad["contact"].write_bytes(contactblad_png(res, ev))
    pad["grafiek"].write_bytes(grafiek_png(res))
    pad["json"].write_text(json.dumps(res.naar_dict(), indent=1, default=float))
    return pad
