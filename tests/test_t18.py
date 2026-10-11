"""T18: verfvertaling, gesimuleerde glansmeter en verfbibliotheek."""

from __future__ import annotations

import itertools

import pytest

from carbonne.core import verfbibliotheek as bib
from carbonne.core.config import Paint
from carbonne.core.glansmeter import REFERENTIE_R, fresnel_onbepolariseerd, glossy_buitenkant, meet_gu
from carbonne.core.kleur import parse_kleur
from carbonne.core.variant import select_variant
from carbonne.core.verf import (
    GLANS_TERMEN,
    VerfEigenschappen,
    VerfFout,
    alpha_naar_gu,
    gu_naar_alpha,
    regels_versie,
    vertaal_verf,
)


def _e(**kw) -> VerfEigenschappen:
    kw.setdefault("hex", "#cc2222")
    return VerfEigenschappen(**kw)


def test_hex_en_ral():
    v = vertaal_verf(_e(hex="#336699", glansgraad="mat"))
    assert v.paint.color == pytest.approx(parse_kleur("#336699"))
    v = vertaal_verf(VerfEigenschappen(kleurcode="RAL 3020", glansgraad="hoogglans"))
    assert v.paint.color == pytest.approx(parse_kleur("RAL 3020"))
    assert any(u.veld == "color" and u.bron == "kleurcode" for u in v.uitleg)


def test_merkcode_zonder_hex_en_zonder_kleur_is_fout():
    with pytest.raises(VerfFout, match="merkcode"):
        vertaal_verf(VerfEigenschappen(kleurcode="Montana GOLD Shock Blue"))
    with pytest.raises(ValueError):
        VerfEigenschappen(glansgraad="mat")  # geen kleur: geen gok
    v = vertaal_verf(VerfEigenschappen(kleurcode="Montana GOLD Shock Blue", hex="#1f6fd1"))
    assert v.paint.color == pytest.approx(parse_kleur("#1f6fd1"))


def test_glansterm_en_gu_monotoon():
    terms = ["zijdemat", "zijdeglans", "glans", "hoogglans"]
    alphas = [vertaal_verf(_e(glansgraad=t)).paint.roughness for t in terms]
    assert all(a > b for a, b in itertools.pairwise(alphas)), alphas
    gus = [4, 10, 20, 35, 50, 70, 80, 85]
    al = [vertaal_verf(_e(glans_gu_60=g)).paint.roughness for g in gus]
    assert all(a > b for a, b in itertools.pairwise(al)), al
    # Engelse termen
    for en, nl in [("matt", "mat"), ("satin", "zijdeglans"), ("semi-gloss", "zijdeglans"), ("gloss", "glans"), ("High Gloss", "hoogglans")]:
        assert vertaal_verf(_e(glansgraad=en)).paint == vertaal_verf(_e(glansgraad=nl)).paint
    # term gebruikt het midden van zijn bereik
    lo, hi = GLANS_TERMEN["glans"]
    assert vertaal_verf(_e(glansgraad="glans")).paint.roughness == pytest.approx(vertaal_verf(_e(glans_gu_60=(lo + hi) / 2)).paint.roughness)


def test_tabel_inverse_klopt():
    for a in (0.01, 0.05, 0.1, 0.2):
        assert gu_naar_alpha(alpha_naar_gu(a))[0] == pytest.approx(a, rel=0.03)
    assert gu_naar_alpha(99.0)[1] is not None  # meer dan de lak kan: afgekapt met opmerking


def test_matte_drempel_en_standaardglans():
    assert vertaal_verf(_e(glans_gu_60=1.0)).paint.kind == "matte"
    assert vertaal_verf(_e(glans_gu_60=1.0)).paint.roughness is None
    assert vertaal_verf(_e(glans_gu_60=20)).paint.kind == "glossy"
    v = vertaal_verf(_e())
    assert any("geen glans" in w for w in v.waarschuwingen)


@pytest.mark.parametrize(
    "effect,kind,waarschuwing",
    [("metallic", "metallic", False), ("chroom", "metallic", False), ("candy", "candy", False), ("parelmoer", "metallic", True),
     ("glitter", "metallic", True), ("fluo", "glossy", True), ("geen", "glossy", False)],
)
def test_effect_geeft_kind_en_waarschuwing(effect, kind, waarschuwing):
    v = vertaal_verf(_e(effect=effect, glansgraad="glans"))
    assert v.paint.kind == kind
    assert bool(v.waarschuwingen) == waarschuwing
    if effect == "chroom":
        assert v.paint.roughness < 0.02
    assert v.uitleg[-1].veld == "binnenvlak"


def test_candy_en_transparant():
    v = vertaal_verf(_e(effect="candy", ondergrond_candy="white"))
    assert v.paint.kind == "candy" and v.paint.candy_base == "white"
    v = vertaal_verf(_e(transparant=True))
    assert v.paint.kind == "candy" and v.paint.candy_base == "metallic"
    assert v.paint.model_dump()  # geldig Paint


def test_glansmeter_referentie_100_gu():
    select_variant()
    assert REFERENTIE_R == pytest.approx(fresnel_onbepolariseerd(0.5, 1.567))
    gu = meet_gu({"type": "dielectric", "int_ior": 1.567, "ext_ior": 1.000277}, n=400_000)
    assert gu == pytest.approx(100.0, abs=2.0)


def test_glansmeter_tabel_komt_overeen_met_meting():
    select_variant()
    for alpha in (0.02, 0.1):
        assert meet_gu(glossy_buitenkant(alpha), n=500_000) == pytest.approx(alpha_naar_gu(alpha), rel=0.05)


def test_rondreis_bibliotheek(tmp_path):
    e = _e(merk="Montana", product="GOLD", kleurnaam="Shock Blue", kleurcode="Montana GOLD Shock Blue", hex="#1f6fd1",
           glansgraad="satin", bron_url="https://example.org/fiche.pdf")
    item = bib.bewaar(e, map_=tmp_path)
    assert item.slug == "montana-gold-shock-blue"
    assert item.vertaling.paint.bibliotheek_id == item.slug
    assert bib.laad(item.slug, tmp_path) == item
    assert [i.slug for i in bib.lijst(tmp_path)] == [item.slug]
    with pytest.raises(FileExistsError):
        bib.bewaar(e, map_=tmp_path)
    bib.bewaar(e, overschrijf=True, map_=tmp_path)
    bib.verwijder(item.slug, tmp_path)
    assert bib.lijst(tmp_path) == []
    with pytest.raises(KeyError):
        bib.laad(item.slug, tmp_path)


def test_opnieuw_vertalen_bij_nieuwe_regels(tmp_path):
    item = bib.bewaar(_e(merk="X", glansgraad="glans"), map_=tmp_path)
    pad = tmp_path / f"{item.slug}.json"
    oud = item.model_copy(update={"regels_versie": "oud", "vertaling": item.vertaling.model_copy(update={"paint": Paint(color=(0.1, 0.1, 0.1))})})
    pad.write_text(oud.model_dump_json(), encoding="utf-8")
    geladen = bib.laad(item.slug, tmp_path)
    assert geladen.regels_versie == regels_versie() and geladen.vertaling == item.vertaling


def test_paint_bibliotheek_id_heeft_geen_invloed_op_scene():
    from carbonne.core.config import TableConfig
    from carbonne.core.scene import afwerking_bsdf

    c = TableConfig()
    p = Paint(color=(0.2, 0.3, 0.4), kind="glossy", roughness=0.1)
    assert afwerking_bsdf(p, c) == afwerking_bsdf(p.model_copy(update={"bibliotheek_id": "x"}), c)
