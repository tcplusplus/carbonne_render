"""Uitlegschetsen per afwerking: een 2D-stralendoorsnede, berekend met numpy (geen Mitsuba).

Een rechthoekige doorsnede van het blok (n = 1,530). Per grensvlak: Fresnel (gemiddelde van s en p), totale
interne reflectie, breking en diffuse terugkaatsing op verf. De lijndikte is evenredig met de energie.
Schrijft SVG's naar web/uitleg/. Draai alleen opnieuw als de fysica verandert:

    uv run python scripts/maak_uitlegschetsen.py [--uit web/uitleg]
"""

from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

N_EPOXY = 1.530
N_LUCHT = 1.0
ALBEDO = 0.75  # witte verf, zoals in de T03-beelden
BREEDTE, DIKTE = 100.0, 40.0  # blok: x in [0, BREEDTE], y in [0, DIKTE]; y omhoog
SPLEET = 3.0  # getekende luchtspleet (de echte is 0,1 mm; hier voor de leesbaarheid)
WERELD = (-12.0, 112.0, -26.0, 62.0)  # xmin, xmax, ymin, ymax
E_MIN = 0.04  # stralen met minder energie worden niet meer getekend
MAX_DIEPTE = 6
FACET_TILT = math.radians(15.0)  # matte lak: gladde facetten, normaal +-15 graden
DIFFUUS = ((-50.0, 0.25), (0.0, 0.5), (50.0, 0.25))  # vaste richtingen t.o.v. de normaal, gewicht


def kritische_hoek_graden(n1: float = N_EPOXY, n2: float = N_LUCHT) -> float:
    return math.degrees(math.asin(n2 / n1))


def fresnel(n1: float, n2: float, cos_i: float) -> tuple[float, float]:
    """Onbepolariseerde reflectie (gemiddelde van s en p) en cos van de gebroken hoek.

    Bij totale interne reflectie: (1.0, 0.0).
    """
    cos_i = abs(cos_i)
    sin_t2 = (n1 / n2) ** 2 * (1.0 - cos_i**2)
    if sin_t2 >= 1.0:
        return 1.0, 0.0
    cos_t = math.sqrt(1.0 - sin_t2)
    rs = ((n1 * cos_i - n2 * cos_t) / (n1 * cos_i + n2 * cos_t)) ** 2
    rp = ((n1 * cos_t - n2 * cos_i) / (n1 * cos_t + n2 * cos_i)) ** 2
    return 0.5 * (rs + rp), cos_t


@dataclass
class Segment:
    p0: tuple[float, float]
    p1: tuple[float, float]
    energie: float
    bundel: int


@dataclass
class Straal:
    pos: np.ndarray
    richting: np.ndarray
    energie: float
    bundel: int
    in_blok: bool
    diepte: int = 0


def _rot(v: np.ndarray, hoek: float) -> np.ndarray:
    c, s = math.cos(hoek), math.sin(hoek)
    return np.array([c * v[0] - s * v[1], s * v[0] + c * v[1]])


def _breek(d: np.ndarray, normaal: np.ndarray, n1: float, n2: float) -> tuple[np.ndarray, np.ndarray, float]:
    """Gereflecteerde en gebroken richting en reflectiefractie. `normaal` wijst naar de kant van de invallende straal
    weg (tegen d in). De gebroken richting is de nulvector bij TIR."""
    cos_i = float(np.dot(d, -normaal))
    f, cos_t = fresnel(n1, n2, cos_i)
    refl = d + 2.0 * cos_i * normaal
    if f >= 1.0:
        return refl, np.zeros(2), 1.0
    eta = n1 / n2
    trans = eta * d + (eta * cos_i - cos_t) * normaal
    return refl, trans / np.linalg.norm(trans), f


# wanden van het blok: naam -> (punt, uitwaartse normaal)
WANDEN = {
    "onder": (np.array([0.0, 0.0]), np.array([0.0, -1.0])),
    "boven": (np.array([0.0, DIKTE]), np.array([0.0, 1.0])),
    "links": (np.array([0.0, 0.0]), np.array([-1.0, 0.0])),
    "rechts": (np.array([BREEDTE, 0.0]), np.array([1.0, 0.0])),
}


@dataclass
class Opstelling:
    naam: str
    onder: str  # "kaal", "verf", "mat", "spleet" (kaal blok boven een witte plaat)
    zijkant: str  # "kaal" of "verf"

    @property
    def plaat(self) -> bool:
        return self.onder == "spleet"


def _wand_treffer(pos: np.ndarray, d: np.ndarray) -> tuple[float, str] | None:
    """Dichtstbijzijnde wand van het blok die de straal vanaf `pos` raakt (binnen de wandgrenzen)."""
    best: tuple[float, str] | None = None
    for naam, (p, nrm) in WANDEN.items():
        denom = float(np.dot(d, nrm))
        if abs(denom) < 1e-12:
            continue
        t = float(np.dot(p - pos, nrm)) / denom
        if t <= 1e-7:
            continue
        q = pos + t * d
        if naam in ("onder", "boven"):
            ok = -1e-9 <= q[0] <= BREEDTE + 1e-9
        else:
            ok = -1e-9 <= q[1] <= DIKTE + 1e-9
        if ok and (best is None or t < best[0]):
            best = (t, naam)
    return best


def _tot_rand(pos: np.ndarray, d: np.ndarray) -> float:
    """Afstand tot de rand van de wereld."""
    xmin, xmax, ymin, ymax = WERELD
    ts = []
    if d[0] > 1e-12:
        ts.append((xmax - pos[0]) / d[0])
    elif d[0] < -1e-12:
        ts.append((xmin - pos[0]) / d[0])
    if d[1] > 1e-12:
        ts.append((ymax - pos[1]) / d[1])
    elif d[1] < -1e-12:
        ts.append((ymin - pos[1]) / d[1])
    return min(ts)


def _diffuus(pos: np.ndarray, normaal_in: np.ndarray, e: float, st: Straal, uit: list[Straal], in_blok: bool) -> None:
    for hoek_graden, w in DIFFUUS:
        d = _rot(normaal_in, math.radians(hoek_graden))
        uit.append(Straal(pos + 1e-6 * d, d, ALBEDO * e * w, st.bundel, in_blok, st.diepte + 1))


def trace(opst: Opstelling, starts: list[Straal]) -> list[Segment]:
    segmenten: list[Segment] = []
    wachtrij = list(starts)
    plaat_y = -SPLEET
    while wachtrij:
        st = wachtrij.pop()
        if st.energie < E_MIN or st.diepte > MAX_DIEPTE:
            continue
        d = st.richting
        treffer = _wand_treffer(st.pos, d)
        t_rand = _tot_rand(st.pos, d)
        t_plaat = None
        if opst.plaat and not st.in_blok and d[1] < -1e-9:
            tp = (plaat_y - st.pos[1]) / d[1]
            xp = st.pos[0] + tp * d[0]
            if tp > 1e-7 and 0.0 <= xp <= BREEDTE:
                t_plaat = tp
        # eerste gebeurtenis: wand, plaat of de rand van de wereld
        kandidaten = [(t_rand, "rand")]
        if treffer is not None:
            # een straal in de lucht raakt een wand alleen van buiten; binnen alleen van binnen
            nrm = WANDEN[treffer[1]][1]
            if (float(np.dot(d, nrm)) > 0) == st.in_blok:
                kandidaten.append((treffer[0], treffer[1]))
        if t_plaat is not None:
            kandidaten.append((t_plaat, "plaat"))
        t, wat = min(kandidaten, key=lambda k: k[0])
        q = st.pos + t * d
        segmenten.append(Segment((float(st.pos[0]), float(st.pos[1])), (float(q[0]), float(q[1])), st.energie, st.bundel))
        if wat == "rand":
            continue
        if wat == "plaat":
            _diffuus(q, np.array([0.0, 1.0]), st.energie, st, wachtrij, in_blok=False)
            continue

        nrm_uit = WANDEN[wat][1]
        soort = opst.onder if wat == "onder" else (opst.zijkant if wat in ("links", "rechts") else "kaal")
        if soort == "spleet":
            soort = "kaal"
        if soort == "verf":
            # verf in optisch contact (binnen) of gewoon geverfd oppervlak (buiten): diffuus, geen grensvlak
            nrm_in = -nrm_uit
            _diffuus(q, nrm_in if st.in_blok else nrm_uit, st.energie, st, wachtrij, st.in_blok)
            continue
        n1, n2 = (N_EPOXY, N_LUCHT) if st.in_blok else (N_LUCHT, N_EPOXY)
        # normaal die tegen de invallende straal in wijst
        nrm = -nrm_uit if st.in_blok else nrm_uit
        if soort == "mat":
            facetten = [(-FACET_TILT, 0.25), (0.0, 0.5), (FACET_TILT, 0.25)]
        else:
            facetten = [(0.0, 1.0)]
        for tilt, w in facetten:
            nf = _rot(nrm, tilt)
            if float(np.dot(d, -nf)) <= 1e-6:
                nf = nrm
            refl, trans, f = _breek(d, nf, n1, n2)
            e = st.energie * w
            wachtrij.append(Straal(q + 1e-6 * refl, refl, e * f, st.bundel, st.in_blok, st.diepte + 1))
            if f < 1.0:
                wachtrij.append(Straal(q + 1e-6 * trans, trans, e * (1.0 - f), st.bundel, not st.in_blok, st.diepte + 1))
    return segmenten


def bundel_start(hoeken_binnen: tuple[float, ...] = (20.0, 45.0, 62.0)) -> list[Straal]:
    """Drie stralen vanuit een punt linksboven in het blok (licht dat via de rand of een verstrooier binnenkomt)
    en een straal uit de lucht die via het bovenvlak binnenkomt."""
    starts = []
    p = np.array([8.0, DIKTE - 6.0])
    for i, h in enumerate(hoeken_binnen):
        r = math.radians(h)
        starts.append(Straal(p.copy(), np.array([math.sin(r), -math.cos(r)]), 1.0, i, True))
    r = math.radians(35.0)
    d = np.array([-math.sin(r), -math.cos(r)])
    top = np.array([86.0, DIKTE])
    starts.append(Straal(top - d * 20.0, d, 1.0, len(hoeken_binnen), False))
    return starts


OPSTELLINGEN = [
    Opstelling("Onderkant onbehandeld", "kaal", "kaal"),
    Opstelling("Onderkant verf in contact", "verf", "kaal"),
    Opstelling("Onderkant kleurloze matte lak", "mat", "kaal"),
    Opstelling("Plaat met luchtspleet", "spleet", "kaal"),
    Opstelling("Zijkant geverfd + luchtspleet", "spleet", "verf"),
]
BESTANDSNAMEN = ["onbehandeld", "verf-in-contact", "matte-lak", "plaat-luchtspleet", "zijkant-geverfd-luchtspleet"]
KLEUREN = ["#c2410c", "#7c3aed", "#0f766e", "#1d4ed8"]
SCHAAL = 3.6


def _px(p: tuple[float, float]) -> tuple[float, float]:
    xmin, _, _, ymax = WERELD
    return (p[0] - xmin) * SCHAAL, (ymax - p[1]) * SCHAAL


def maak_svg(opst: Opstelling) -> str:
    segs = trace(opst, bundel_start())
    xmin, xmax, ymin, ymax = WERELD
    b, h = (xmax - xmin) * SCHAAL, (ymax - ymin) * SCHAAL
    o: list[str] = [
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {b:.0f} {h:.0f}" width="{b:.0f}" height="{h:.0f}" '
            'font-family="sans-serif">'
        ),
        f"<title>{opst.naam}</title>",
        f'<rect width="{b:.0f}" height="{h:.0f}" fill="#ffffff"/>',
    ]

    def rect(x0: float, y0: float, x1: float, y1: float, vul: str, rand: str = "none") -> None:
        ax, ay = _px((x0, y1))
        bx, by = _px((x1, y0))
        o.append(f'<rect x="{ax:.1f}" y="{ay:.1f}" width="{bx - ax:.1f}" height="{by - ay:.1f}" fill="{vul}" stroke="{rand}"/>')

    rect(0, 0, BREEDTE, DIKTE, "#dbeafe", "#334155")  # epoxy
    if opst.onder == "verf":
        rect(0, -4, BREEDTE, 0, "#f8fafc", "#334155")
    if opst.onder == "mat":
        rect(0, -1.6, BREEDTE, 0, "#e2e8f0", "#64748b")
    if opst.plaat:
        rect(0, -SPLEET - 5, BREEDTE, -SPLEET, "#f8fafc", "#334155")
    if opst.zijkant == "verf":
        rect(-4, 0, 0, DIKTE, "#f8fafc", "#334155")
        rect(BREEDTE, 0, BREEDTE + 4, DIKTE, "#f8fafc", "#334155")
    for s in segs:
        (x0, y0), (x1, y1) = _px(s.p0), _px(s.p1)
        w = 0.5 + 5.5 * s.energie
        o.append(
            f'<line x1="{x0:.1f}" y1="{y0:.1f}" x2="{x1:.1f}" y2="{y1:.1f}" stroke="{KLEUREN[s.bundel]}" '
            f'stroke-width="{w:.2f}" stroke-opacity="0.85"/>'
        )
    px, py = _px((8.0, DIKTE - 6.0))
    o.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="3" fill="#0f172a"/>')
    o.append(f'<rect x="0" y="0" width="{b:.0f}" height="46" fill="#ffffff"/>')
    o.append(f'<text x="8" y="20" font-size="15" font-weight="bold" fill="#0f172a">{opst.naam}</text>')
    o.append(
        f'<text x="8" y="38" font-size="12" fill="#334155">n = {N_EPOXY:.3f} · kritische hoek '
        f"{kritische_hoek_graden():.1f}".replace(".", ",") + "°</text>"
    )
    o.append("</svg>")
    return "\n".join(o) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--uit", default=str(Path(__file__).resolve().parent.parent / "web" / "uitleg"))
    uit = Path(ap.parse_args().uit)
    uit.mkdir(parents=True, exist_ok=True)
    for opst, naam in zip(OPSTELLINGEN, BESTANDSNAMEN, strict=True):
        (uit / f"{naam}.svg").write_text(maak_svg(opst), encoding="utf-8")
        print(uit / f"{naam}.svg")


if __name__ == "__main__":
    main()
