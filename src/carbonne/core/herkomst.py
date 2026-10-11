"""Herkomst-integrator (T13): waar komt de kleur van een pixel vandaan?

`HerkomstIntegrator` is een eigen Mitsuba-integrator die hetzelfde algoritme volgt als `path` (next-event
estimation met MIS, Russische roulette, zelfde `max_depth`), maar elk lichtpad labelt met de *bronnen* die het
raakte voordat het een lichtbron bereikte. De bijdragen worden per categorie in aparte kanalen opgeteld.

Bronnen (bitmasker, 4 bits) volgens de shape-id's van `build_scene`:
  bit 0 (1)  zijkant    `mantel`
  bit 1 (2)  onderkant  `onder` en `plaat_*`
  bit 2 (4)  inhoud     `inhoud_*`
  bit 3 (8)  vloer      `floor`
Het bovenvlak is nooit een bron.

Een vlak telt als "geraakt" zodra een straal van het pad (camerastraal of BSDF-gesampelde straal) het
snijdt, ook als het pad daarna doorgaat (dus ook bij transmissie of een BSDF-sample). De schaduwstraal van
next-event estimation raakt per definitie niets (hij moet vrij zijn), maar de bijdrage ervan hoort bij het
vlak waarvan hij vertrekt: dat vlak is al geraakt. Uitzondering: een *onbehandeld* blokvlak (glad
`dielectric`, dus Bare of de eigen onderkant onder een plaat) is geen bron; een transmissie of reflectie
daaraan zet geen bit. Een kleurloze matte lak (`roughdielectric`) telt wel als bron.

De 16 categorieen (de verzameling bronnen op het moment van de bijdrage) sluiten elkaar uit en tellen op tot de
`path`-render: categorie 0 = enkel glans en omgeving.

Kanalen (na R, G, B van de som): 16 x (R,G,B) `cat{k}_R/G/B`, dan de padstatistieken. Elk is een som over
bijdragen, gewogen met de luminantie van de bijdrage (Y van lineair sRGB); delen door de totale luminantie
geeft het gewogen gemiddelde:
  `w_tir`       aantal reflecties tegen een glad epoxy/lucht-vlak vanaf de binnenkant bij een hoek boven de
                kritische hoek (totale interne reflectie, TIR);
  `w_fresnel`   aantal reflecties tegen zo'n vlak onder de kritische hoek (gewone Fresnelreflectie);
  `w_heeft_tir` 1 als het pad minstens een keer TIR had (aandeel energie met TIR);
  `w_weg_m`     weglengte in de epoxy (m), gesommeerd over alle segmenten binnen het blok.
Een reflectie tegen een ruw diëlektrisch vlak (matte lak) wordt met dezelfde meetkundige grens (kritische
hoek op de geometrische normaal) als TIR of Fresnel geteld; het is daar een benadering.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

BRONNEN = ("zijkant", "onderkant", "inhoud", "vloer")
N_CAT = 16
STAT_NAMEN = ("w_tir", "w_fresnel", "w_heeft_tir", "w_weg_m")
LUM = (0.2126, 0.7152, 0.0722)
STANDAARD_ETA = 1.53 / 1.000277

_geregistreerd = False


def categorie_naam(k: int) -> str:
    """Leesbare naam van categorie k (bitmasker)."""
    delen = [BRONNEN[i] for i in range(4) if k >> i & 1]
    return " + ".join(delen) if delen else "glans/omgeving"


def kanaal_namen() -> list[str]:
    return [f"cat{k}_{c}" for k in range(N_CAT) for c in "RGB"] + list(STAT_NAMEN)


def bron_bits(naam: str, bsdf_type: str) -> int:
    """Bronbit(s) van een vlak uit zijn id en BSDF-klasse (`smoothdielectric`, `twosided`, ...); zie bovenaan."""
    if bsdf_type == "smoothdielectric":
        return 0  # onbehandeld blokvlak: geen bron
    if naam == "mantel":
        return 1
    if naam == "onder" or naam.startswith("plaat_"):
        return 2
    if naam.startswith("inhoud_"):
        return 4
    if naam == "floor":
        return 8
    return 0


def registreer() -> None:
    """Registreer de integrator onder de naam `herkomst` (vereist een gezette Mitsuba-variant)."""
    global _geregistreerd
    import drjit as dr
    import mitsuba as mi

    if _geregistreerd:
        return

    def mis_weight(a, b):
        a2 = dr.square(a)
        return dr.select(a > 0, a2 / dr.fma(a, a, dr.square(b)), 0.0)

    class HerkomstIntegrator(mi.SamplingIntegrator):
        def __init__(self, props: mi.Properties):
            super().__init__(props)
            self.max_depth = props.get("max_depth", 32)
            self.rr_depth = props.get("rr_depth", 5)
            self.eta_blok = props.get("eta", STANDAARD_ETA)  # n(epoxy)/n(lucht)
            self._tabellen = None

        def aov_names(self):
            return kanaal_namen()

        def to_string(self):
            return f"HerkomstIntegrator[max_depth={self.max_depth}]"

        def _maak_tabellen(self, scene):
            """Tabellen op shape-id (instance-id in het Dr.Jit-register): bronbits en 'glad diëlektrisch'."""
            shapes = list(scene.shapes())
            ids = [int(np.array(dr.reinterpret_array(mi.UInt32, mi.ShapePtr(s)))[0]) for s in shapes]
            n = max(ids) + 2
            bits = np.zeros(n, np.uint32)
            diel = np.zeros(n, np.uint32)  # 1 = blokvlak met (ruw) diëlektrisch grensvlak epoxy/lucht
            blok = np.zeros(n, np.uint32)  # 1 = boven/mantel/onder (bepaalt of een straal "in het blok" is)
            inh = np.zeros(n, np.uint32)  # 1 = inhoud (blijft binnen de epoxy)
            for s, i in zip(shapes, ids, strict=True):
                naam = s.id()
                bt = str(s.bsdf()).split("[")[0].strip().lower()
                bits[i] = bron_bits(naam, bt)
                diel[i] = bt in ("smoothdielectric", "roughdielectric")
                blok[i] = naam in ("boven", "mantel", "onder")
                inh[i] = naam.startswith("inhoud_")
            self._tabellen = tuple(mi.UInt32(t) for t in (bits, diel, blok, inh))

        def sample(self, scene, sampler, ray, medium=None, active=True):
            if self._tabellen is None:
                self._maak_tabellen(scene)
            t_bits, t_diel, t_blok, t_inh = self._tabellen
            bsdf_ctx = mi.BSDFContext()
            ray = mi.Ray3f(ray)
            wl = ray.wavelengths
            eta_blok = mi.Float(self.eta_blok)

            f = mi.Float
            u = mi.UInt32
            throughput = mi.Spectrum(1.0)
            eta = f(1.0)
            depth = u(0)
            active = mi.Bool(active)
            prev_si = dr.zeros(mi.SurfaceInteraction3f)
            prev_pdf = f(1.0)
            prev_delta = mi.Bool(True)
            mask = u(0)
            binnen = mi.Bool(False)
            n_tir, n_fres, weg = f(0.0), f(0.0), f(0.0)
            had_tir = mi.Bool(False)
            acc = [f(0.0) for _ in range(N_CAT * 3)]
            stat = [f(0.0) for _ in STAT_NAMEN]

            def bijdrage(acc, stat, c_spec, mask, n_tir, n_fres, weg, had_tir, actief):
                """Tel de (spectrale) bijdrage op bij de categorie `mask` en bij de gewogen statistieken."""
                rgb = mi.spectrum_to_srgb(c_spec / mi.pdf_rgb_spectrum(wl), wl, actief)
                rgb = dr.select(actief, rgb, 0.0)
                for k in range(N_CAT):
                    sel = mask == k
                    for c in range(3):
                        acc[k * 3 + c] += dr.select(sel, rgb[c], 0.0)
                lum = LUM[0] * rgb[0] + LUM[1] * rgb[1] + LUM[2] * rgb[2]
                stat[0] += lum * n_tir
                stat[1] += lum * n_fres
                stat[2] += lum * dr.select(had_tir, 1.0, 0.0)
                stat[3] += lum * weg
                return acc, stat

            def body(sampler, ray, throughput, eta, active, depth, prev_si, prev_pdf, prev_delta, mask, binnen,
                     n_tir, n_fres, weg, had_tir, L, acc, stat):
                si = scene.ray_intersect(ray, ray_flags=mi.RayFlags.All, coherent=(depth == 0), active=active)
                sid = dr.reinterpret_array(mi.UInt32, si.shape)
                geraakt = active & si.is_valid()
                weg = weg + dr.select(binnen & geraakt, si.t, 0.0)
                mask = mask | dr.select(geraakt, dr.gather(mi.UInt32, t_bits, sid, geraakt), u(0))

                # lichtbron geraakt door BSDF-sample (of camerastraal)
                ds = mi.DirectionSample3f(scene, si=si, ref=prev_si)
                em_pdf = scene.pdf_emitter_direction(prev_si, ds, active & ~prev_delta)
                mis_b = dr.select(prev_delta, 1.0, mis_weight(prev_pdf, em_pdf))
                le = throughput * mis_b * ds.emitter.eval(si, active)
                L = L + le
                acc, stat = bijdrage(acc, stat, le, mask, n_tir, n_fres, weg, had_tir, active)

                active_next = (depth + 1 < self.max_depth) & si.is_valid() & active
                bsdf = si.bsdf(ray)

                # next-event estimation
                active_em = active_next & mi.has_flag(bsdf.flags(), mi.BSDFFlags.Smooth)
                ds, em_weight = scene.sample_emitter_direction(si, sampler.next_2d(), True, active_em)
                active_em &= ds.pdf != 0.0
                wo = si.to_local(ds.d)
                bsdf_val, bsdf_pdf = bsdf.eval_pdf(bsdf_ctx, si, wo, active_em)
                mis_em = dr.select(ds.delta, 1.0, mis_weight(ds.pdf, bsdf_pdf))
                ne = throughput * bsdf_val * em_weight * mis_em
                L = L + ne
                acc, stat = bijdrage(acc, stat, ne, mask, n_tir, n_fres, weg, had_tir, active_em)

                # BSDF-sample
                bs, bsdf_weight = bsdf.sample(bsdf_ctx, si, sampler.next_1d(), sampler.next_2d(), active_next)
                wo_w = si.to_world(bs.wo)

                # binnen/buiten het blok, TIR en Fresnel-reflecties
                is_blok = active_next & (dr.gather(mi.UInt32, t_blok, sid, active_next) != 0)
                is_diel = is_blok & (dr.gather(mi.UInt32, t_diel, sid, active_next) != 0)
                is_inh = active_next & (dr.gather(mi.UInt32, t_inh, sid, active_next) != 0)
                cos_i = dr.abs(dr.dot(si.n, ray.d))
                naar_binnen = dr.dot(wo_w, si.n) < 0.0
                refl_binnen = is_diel & binnen & naar_binnen
                tir = refl_binnen & (eta_blok * eta_blok * (1.0 - cos_i * cos_i) > 1.0)
                n_tir = n_tir + dr.select(tir, 1.0, 0.0)
                n_fres = n_fres + dr.select(refl_binnen & ~tir, 1.0, 0.0)
                had_tir = had_tir | tir
                binnen = dr.select(is_blok, naar_binnen, dr.select(is_inh, binnen, mi.Bool(False)))

                ray = si.spawn_ray(wo_w)
                throughput = throughput * bsdf_weight
                eta = eta * bs.eta
                prev_si = si
                prev_pdf = bs.pdf
                prev_delta = ~mi.has_flag(bs.sampled_type, mi.BSDFFlags.Smooth)
                depth = dr.select(active, depth + 1, depth)

                # Russische roulette
                throughput_max = dr.max(mi.unpolarized_spectrum(throughput))
                q = dr.minimum(throughput_max * dr.square(eta), 0.99)
                perform_rr = depth > self.rr_depth
                active_next &= (~perform_rr) | (sampler.next_1d() < q)
                throughput = dr.select(perform_rr & (q > 0), throughput / dr.maximum(q, 1e-9), throughput)
                active_next &= throughput_max != 0.0
                return (sampler, ray, throughput, eta, active_next, depth, prev_si, prev_pdf, prev_delta, mask, binnen,
                        n_tir, n_fres, weg, had_tir, L, acc, stat)

            L = mi.Spectrum(0.0)
            state = (sampler, ray, throughput, eta, active, depth, prev_si, prev_pdf, prev_delta, mask, binnen, n_tir,
                     n_fres, weg, had_tir, L, acc, stat)
            out = dr.while_loop(state=state, cond=lambda *s: s[4], body=body)
            depth, L, acc, stat = out[5], out[15], out[16], out[17]
            return L, depth != 0, list(acc) + list(stat)

    mi.register_integrator("herkomst", lambda props: HerkomstIntegrator(props))
    _geregistreerd = True


# ---------------------------------------------------------------------------------------------------------------
# Analyse van een herkomst-render


def herkomst_opties(config, **kw):
    """`RenderOpties` voor de herkomst-integrator, met de brekingsindex van de epoxy uit `config` (voor TIR). Overige
    `kw` gaan naar `RenderOpties`. Geheugen: elk sample draagt ~100 floats (640x360 met 16 spp per pass: ~0,9 GB)."""
    from carbonne.render.pipeline import RenderOpties

    params = {"eta": float(config.epoxy.n_d) / 1.000277}
    params.update(kw.pop("integrator_params", {}))
    return RenderOpties(integrator="herkomst", integrator_params=params, **kw)


def lineair_naar_lab(rgb) -> tuple[float, float, float]:
    """Lineair sRGB (D65) naar CIE Lab met wit Y = 1 (radiantie 1,0 = L* 100); een bijdrage die maar een deel van
    het licht levert heeft dus een lage L*."""
    m = np.array([[0.4124564, 0.3575761, 0.1804375], [0.2126729, 0.7151522, 0.0721750],
                  [0.0193339, 0.1191920, 0.9503041]])
    xyz = m @ np.maximum(np.asarray(rgb, float), 0.0) / np.array([0.95047, 1.0, 1.08883])

    def f(t):
        return np.cbrt(t) if t > (6 / 29) ** 3 else t / (3 * (6 / 29) ** 2) + 4 / 29

    fx, fy, fz = (f(t) for t in xyz)
    return (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))


@dataclass
class CategorieAandeel:
    """Een categorie (verzameling bronnen) in een gebied."""

    naam: str
    bronnen: tuple[str, ...]  # leeg = enkel glans/omgeving; bij "overig" de samengevoegde categorieen
    aandeel_pct: float  # aandeel van de luminantie
    rgb: tuple[float, float, float]  # lineair RGB van alleen deze bijdrage (gemiddelde over het gebied)
    lab: tuple[float, float, float]  # Lab van `rgb` (wit Y = 1)
    rgb_per_pad: tuple[float, float, float]  # `rgb` / aandeel: de kleur van het licht dat via deze bron kwam
    lab_per_pad: tuple[float, float, float]
    categorie: int | None = None  # bitmasker, None bij "overig"


@dataclass
class Kerngetallen:
    """Padstatistieken, gewogen met de luminantie van de bijdrage (alle categorieen samen)."""

    n_tir: float  # gemiddeld aantal TIR-reflecties per bijdrage
    n_fresnel: float  # gemiddeld aantal Fresnel-reflecties tegen een glad epoxy/lucht-vlak van binnen
    aandeel_tir_pct: float  # aandeel van de energie dat minstens een keer TIR had
    weg_epoxy_cm: float  # gemiddelde weglengte in de epoxy


@dataclass
class Herkomst:
    gebied: tuple
    n_pixels: int
    rgb: tuple[float, float, float]  # som van alle categorieen = de gewone render
    lab: tuple[float, float, float]
    categorieen: list[CategorieAandeel] = field(default_factory=list)  # aflopend op aandeel, "overig" laatst
    kerngetallen: Kerngetallen | None = None

    def aandeel(self, *bronnen: str) -> float:
        """Aandeel (%) van de categorie met precies deze bronnen (0 als hij niet voorkomt of in 'overig' zit)."""
        gezocht = set(bronnen)
        return sum(c.aandeel_pct for c in self.categorieen if c.categorie is not None and set(c.bronnen) == gezocht)

    def bevat(self, bron: str) -> float:
        """Aandeel (%) van alle categorieen waarin `bron` voorkomt (ook die in 'overig' zijn niet meegeteld)."""
        return sum(c.aandeel_pct for c in self.categorieen if bron in c.bronnen)


def _masker(shape: tuple[int, int], gebied, straal: float) -> np.ndarray:
    h, w = shape
    if len(gebied) == 2:
        x, y = gebied
        yy, xx = np.mgrid[0:h, 0:w]
        m = (xx - x) ** 2 + (yy - y) ** 2 <= straal**2
    elif len(gebied) == 4:
        x0, y0, x1, y1 = (int(v) for v in gebied)
        m = np.zeros((h, w), bool)
        m[max(y0, 0) : y1, max(x0, 0) : x1] = True
    else:
        raise ValueError("gebied is (x, y) of (x0, y0, x1, y1)")
    if not m.any():
        raise ValueError(f"gebied {gebied} bevat geen pixels in een beeld van {w}x{h}")
    return m


def categorie_beelden(beeld: np.ndarray) -> np.ndarray:
    """(h, w, 16, 3): bijdrage per categorie uit een herkomst-beeld (kanalen 3..50)."""
    if beeld.shape[2] != 3 + N_CAT * 3 + len(STAT_NAMEN):
        raise ValueError("geen herkomst-beeld: verwacht 55 kanalen (render met integrator='herkomst')")
    return beeld[..., 3 : 3 + N_CAT * 3].reshape(*beeld.shape[:2], N_CAT, 3)


def herkomst_van(resultaat, gebied, straal: float = 2.0, drempel_pct: float = 1.0) -> Herkomst:
    """Herkomst van de kleur in een pixel (`(x, y)` met `straal` in pixels) of rechthoek `(x0, y0, x1, y1)`.

    `resultaat` is een RenderResultaat van de herkomst-integrator of het beeld zelf. Het aandeel is het aandeel in
    de luminantie (Y); categorieen onder `drempel_pct` worden samengevoegd tot "overig"."""
    beeld = np.asarray(getattr(resultaat, "beeld", resultaat), dtype=np.float64)
    cats = categorie_beelden(beeld)
    m = _masker(beeld.shape[:2], gebied, straal)
    per_cat = cats[m].mean(axis=0)  # (16, 3)
    stat = beeld[m][:, 3 + N_CAT * 3 :].mean(axis=0)
    totaal = per_cat.sum(axis=0)
    y_cat = per_cat @ np.array(LUM)
    y_tot = float(y_cat.sum())
    rijen: list[CategorieAandeel] = []
    overig: list[int] = []
    for k in range(N_CAT):
        pct = 100.0 * y_cat[k] / y_tot if y_tot > 0 else 0.0
        if pct <= 0.0:
            continue
        if pct < drempel_pct:
            overig.append(k)
            continue
        rijen.append(_rij(categorie_naam(k), tuple(BRONNEN[i] for i in range(4) if k >> i & 1), pct, per_cat[k],
                          k))
    rijen.sort(key=lambda r: -r.aandeel_pct)
    if overig:
        pct = 100.0 * float(y_cat[overig].sum()) / y_tot
        bronnen = tuple(sorted({b for k in overig for b in (BRONNEN[i] for i in range(4) if k >> i & 1)}))
        rijen.append(_rij("overig", bronnen, pct, per_cat[overig].sum(axis=0), None))
    kern = Kerngetallen(
        n_tir=float(stat[0] / y_tot) if y_tot > 0 else 0.0,
        n_fresnel=float(stat[1] / y_tot) if y_tot > 0 else 0.0,
        aandeel_tir_pct=float(100.0 * stat[2] / y_tot) if y_tot > 0 else 0.0,
        weg_epoxy_cm=float(100.0 * stat[3] / y_tot) if y_tot > 0 else 0.0,
    )
    return Herkomst(tuple(gebied), int(m.sum()), tuple(float(v) for v in totaal), lineair_naar_lab(totaal), rijen,
                    kern)


def _rij(naam, bronnen, pct, rgb, k) -> CategorieAandeel:
    rgb = np.asarray(rgb, float)
    per_pad = rgb / (pct / 100.0) if pct > 0 else rgb
    return CategorieAandeel(naam, bronnen, float(pct), tuple(float(v) for v in rgb), lineair_naar_lab(rgb),
                            tuple(float(v) for v in per_pad), lineair_naar_lab(per_pad), k)
