"""Inhoud in gietlagen (T06): houtschijfjes en bloemen als eenvoudige parametrische meshes.

De items liggen volledig in de epoxy. Het blok is in Mitsuba een gesloten dielectric-oppervlak; binnenin is geen
medium gedefinieerd, dus een straal die een item raakt, raakt het direct (alleen het epoxy/lucht-grensvlak
buiten telt als Fresnel). Een ondoorzichtig diffuus item heeft dus geen extra Fresnel nodig; items zijn
`twosided` omdat Mitsuba's `diffuse` anders alleen de normaalkant weerkaatst.

Plaatsing: willekeurig, reproduceerbaar via `Layer.seed`; geen overlap (begrenzende cirkels in het horizontale
vlak, alleen tussen items waarvan de hoogtebereiken overlappen) en minimale afstand tot de rand.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from carbonne.core.config import Flower, Layer, TableConfig, WoodSlice

ITEM_GAP_M = 1e-3  # minimale tussenruimte tussen items
VERTICALE_MARGE_M = 1e-3  # items blijven minstens zoveel van boven- en onderkant (ray-epsilon, zie scene.py)
MAX_POGINGEN = 2000


@dataclass
class Item:
    """Een gegenereerd item, gecentreerd rond de x/z-oorsprong; `v` (N,3), `n` (N,3), `f` (M,3)."""

    soort: str
    v: np.ndarray
    n: np.ndarray
    f: np.ndarray
    bsdf: dict
    x: float = 0.0
    z: float = 0.0
    y: float = 0.0

    @property
    def straal(self) -> float:
        return float(np.hypot(self.v[:, 0], self.v[:, 2]).max())

    @property
    def y_bereik(self) -> tuple[float, float]:
        return float(self.v[:, 1].min() + self.y), float(self.v[:, 1].max() + self.y)

    def posities(self) -> np.ndarray:
        return self.v + np.array([self.x, self.y, self.z])


def _samenvoegen(delen: list[tuple[np.ndarray, np.ndarray, np.ndarray]]):
    v, n, f, o = [], [], [], 0
    for dv, dn, df in delen:
        v.append(dv), n.append(dn), f.append(np.asarray(df) + o)
        o += len(dv)
    return np.concatenate(v), np.concatenate(n), np.concatenate(f)


def _vertex_normalen(v: np.ndarray, f: np.ndarray) -> np.ndarray:
    fn = np.cross(v[f[:, 1]] - v[f[:, 0]], v[f[:, 2]] - v[f[:, 0]])
    n = np.zeros_like(v)
    for k in range(3):
        np.add.at(n, f[:, k], fn)
    return n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)


def _rotatie(yaw: float, kantel: float, as_hoek: float) -> np.ndarray:
    """Kanteling `kantel` om een horizontale as (richting `as_hoek`), daarna draaiing `yaw` om y."""
    a = np.array([np.cos(as_hoek), 0.0, np.sin(as_hoek)])
    k = np.array([[0, -a[2], a[1]], [a[2], 0, -a[0]], [-a[1], a[0], 0]])
    r_kantel = np.eye(3) + np.sin(kantel) * k + (1 - np.cos(kantel)) * k @ k
    c, s = np.cos(yaw), np.sin(yaw)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]]) @ r_kantel


def houtschijf_mesh(straal: float, dikte: float, onregelmatig: float, rng: np.random.Generator, segmenten: int = 32):
    """Platte schijf met onregelmatige (stervormige) omtrek; middenvlak op y = 0."""
    hoek = 2 * np.pi * np.arange(segmenten) / segmenten
    prof = np.ones(segmenten)
    for h in (2, 3, 5):
        prof += onregelmatig / h * rng.uniform(0.3, 1.0) * np.cos(h * hoek + rng.uniform(0, 2 * np.pi))
    ring = np.stack([straal * prof * np.cos(hoek), np.zeros(segmenten), straal * prof * np.sin(hoek)], axis=1)
    k = np.arange(segmenten)
    k1 = (k + 1) % segmenten
    h2 = dikte / 2
    boven = np.concatenate([[[0, h2, 0]], ring + [0, h2, 0]])
    onder = np.concatenate([[[0, -h2, 0]], ring - [0, h2, 0]])
    fb = np.stack([np.zeros(segmenten, int), 1 + k1, 1 + k], axis=1)
    fo = fb[:, ::-1]
    mantel = np.concatenate([ring + [0, -h2, 0], ring + [0, h2, 0]])
    fm = np.concatenate(
        [np.stack([k, segmenten + k1, k1], axis=1), np.stack([k, segmenten + k, segmenten + k1], axis=1)]
    )
    delen = []
    for dv, df in ((boven, fb), (onder, fo), (mantel, fm)):
        delen.append((dv, np.zeros_like(dv), df))
    v, _, f = _samenvoegen(delen)
    # ruwe vlaknormalen per deel zijn niet nodig voor twosided; geef gladde vertexnormalen mee
    return v, _vertex_normalen(v, f), f


def blaadje_mesh(lengte: float, breedte: float, welving: float, nu: int = 8, nv: int = 7):
    """Eén bloemblaadje langs +x vanaf de oorsprong; de top buigt `welving` omhoog (+y), kwadratisch."""
    u = np.linspace(0, 1, nu)
    w = np.linspace(-1, 1, nv)
    uu, ww = np.meshgrid(u, w, indexing="ij")
    breedteprofiel = np.sin(np.pi * np.clip(uu, 0, 1) ** 0.7) * 0.5 * breedte
    # dwarsbuiging: de zijranden buigen iets omhoog, zodat het blaadje niet vlak is
    x = uu * lengte
    z = ww * breedteprofiel
    y = welving * uu**2 + 0.15 * welving * ww**2 * (breedteprofiel / (0.5 * breedte + 1e-12))
    v = np.stack([x, y, z], axis=-1).reshape(-1, 3)
    idx = np.arange(nu * nv).reshape(nu, nv)
    a, b, c, d = idx[:-1, :-1], idx[1:, :-1], idx[1:, 1:], idx[:-1, 1:]
    f = np.concatenate([np.stack([a, b, c], -1).reshape(-1, 3), np.stack([a, c, d], -1).reshape(-1, 3)])
    f = f[np.linalg.norm(np.cross(v[f[:, 1]] - v[f[:, 0]], v[f[:, 2]] - v[f[:, 0]]), axis=1) > 1e-12]
    return v, _vertex_normalen(v, f), f


def bloem_mesh(spec: Flower, rng: np.random.Generator):
    """Rozet van `petals` blaadjes rond de y-as, willekeurig gekanteld; zwaartepunt op de oorsprong."""
    lengte = rng.uniform(*spec.radius_mm) * 1e-3
    n = spec.petals
    breedte = min(lengte * 0.9, 2 * np.pi * lengte * 0.12 * 6 / n) if n > 1 else lengte * 0.7
    delen = []
    for i in range(n):
        v, nn, f = blaadje_mesh(lengte * rng.uniform(0.92, 1.08), breedte * rng.uniform(0.9, 1.1), spec.cup_mm * 1e-3)
        if n == 1:
            ph = 0.0
        else:
            ph = 2 * np.pi * i / n + rng.uniform(-0.05, 0.05)
        c, s = np.cos(ph), np.sin(ph)
        r = np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])
        delen.append((v @ r.T, nn @ r.T, f))
    v, nn, f = _samenvoegen(delen)
    rot = _rotatie(
        rng.uniform(0, 2 * np.pi), np.radians(spec.tilt_deg) * np.sqrt(rng.uniform()), rng.uniform(0, 2 * np.pi)
    )
    v = v @ rot.T
    v = v - 0.5 * (v.min(axis=0) + v.max(axis=0)) * np.array([1.0, 1.0, 1.0])  # bounding box naar de oorsprong
    return v, nn @ rot.T, f


def _diffuus(kleur) -> dict:
    return {"type": "diffuse", "reflectance": {"type": "rgb", "value": [float(x) for x in kleur]}}


def _hout_bsdf(kleur) -> dict:
    return {"type": "twosided", "bsdf": _diffuus(kleur)}


def _bloem_bsdf(kleur, doorlaat: float) -> dict:
    """Dun, licht doorschijnend blaadje: `principledthin` (Disney thin) is tweezijdig en kent diffuse
    transmissie (`diff_trans`: 0 = alles diffuus teruggekaatst, 1 = alles diffuus doorgelaten). Mitsuba 3.9 heeft
    geen aparte `difftrans`-plugin. `eta` 1 schakelt de spiegelglans uit: een blaadje in epoxy (n ~ 1,5) heeft bijna geen indexcontrast."""
    return {
        "type": "principledthin",
        "base_color": {"type": "rgb", "value": [float(x) for x in kleur]},
        "roughness": 1.0,
        "eta": 1.0,  # geen spiegelende glans: een blaadje in epoxy heeft nauwelijks indexcontrast
        "diff_trans": float(doorlaat),
    }


def genereer_items(laag: Layer, rng: np.random.Generator) -> list[Item]:
    items: list[Item] = []
    for spec in laag.items:
        for _ in range(spec.count):
            if isinstance(spec, WoodSlice):
                kleur = np.clip(np.array(spec.color) * rng.uniform(0.8, 1.2), 0, 1)
                r = rng.uniform(*spec.radius_mm) * 1e-3
                v, n, f = houtschijf_mesh(r, spec.thickness_mm * 1e-3, spec.irregularity, rng)
                items.append(Item("wood", v, n, f, _hout_bsdf(kleur)))
            else:
                kleur = np.clip(np.array(spec.color) * rng.uniform(0.9, 1.1), 0, 1)
                v, n, f = bloem_mesh(spec, rng)
                items.append(Item("flower", v, n, f, _bloem_bsdf(kleur, spec.translucency)))
    return items


def plaats_laag(config: TableConfig, laag: Layer, bestaand: list[Item] | None = None) -> list[Item]:
    """Genereer en plaats de items van één laag (zaad = `laag.seed`). `bestaand`: al geplaatste items uit andere
    lagen; items met overlappend hoogtebereik mogen elkaar horizontaal niet raken. Gooit ValueError als het niet past."""
    rng = np.random.default_rng(laag.seed)
    items = genereer_items(laag, rng)
    items.sort(key=lambda i: -i.straal)  # grootste eerst: hogere kans dat alles past
    R = config.diameter / 2
    marge = laag.edge_margin_mm * 1e-3
    geplaatst: list[Item] = list(bestaand or [])
    mijn: list[Item] = []
    for it in items:
        it.y = laag.height_m
        lo, hi = it.y_bereik
        if lo < VERTICALE_MARGE_M or hi > config.hoogte - VERTICALE_MARGE_M:
            raise ValueError(
                f"item ({it.soort}) steekt buiten het blok: y {lo * 1e3:.1f}..{hi * 1e3:.1f} mm, "
                f"toegestaan {VERTICALE_MARGE_M * 1e3:.1f}..{(config.hoogte - VERTICALE_MARGE_M) * 1e3:.1f} mm"
            )
        ruimte = R - marge - it.straal
        if ruimte < 0:
            raise ValueError(f"item ({it.soort}, straal {it.straal * 1e3:.1f} mm) past niet in het blok")
        for _ in range(MAX_POGINGEN):
            rr, th = ruimte * np.sqrt(rng.uniform()), rng.uniform(0, 2 * np.pi)
            it.x, it.z = rr * np.cos(th), rr * np.sin(th)
            ok = True
            for o in geplaatst:
                olo, ohi = o.y_bereik
                if hi + ITEM_GAP_M < olo or lo - ITEM_GAP_M > ohi:
                    continue
                if np.hypot(it.x - o.x, it.z - o.z) < it.straal + o.straal + ITEM_GAP_M:
                    ok = False
                    break
            if ok:
                break
        else:
            raise ValueError(f"geen plek voor alle items in laag op {laag.height_m * 1e3:.1f} mm (te vol)")
        geplaatst.append(it)
        mijn.append(it)
    return mijn


def plaats_alles(config: TableConfig) -> list[list[Item]]:
    """Plaats alle lagen (in volgorde); geeft per laag de geplaatste items."""
    totaal: list[Item] = []
    uit = []
    for laag in config.layers:
        its = plaats_laag(config, laag, totaal)
        totaal += its
        uit.append(its)
    return uit


def inhoud_meshes(config: TableConfig) -> dict:
    """Mitsuba-meshes (naam -> mi.Mesh) voor alle items; de Mitsuba-variant moet gezet zijn."""
    from carbonne.core.scene import _mesh

    out = {}
    for li, its in enumerate(plaats_alles(config)):
        for ii, it in enumerate(its):
            out[f"inhoud_{li}_{ii}_{it.soort}"] = _mesh(
                f"inhoud_{li}_{ii}", {"v": it.posities(), "n": it.n, "f": it.f}, it.bsdf
            )
    return out
