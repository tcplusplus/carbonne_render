"""Configuratiemodel: het hele tafeltje en de scene in een JSON-serialiseerbaar pydantic-model."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from carbonne.core.kleur import als_kleur

NA_D_NM = 589.3  # natrium-D-lijn, referentiegolflengte voor n_d


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class EpoxyMaterial(_Model):
    """Kleurloze epoxy. n(lambda) = A + B / lambda^2 (Cauchy, lambda in micrometer)."""

    cauchy_a: float = Field(1.517, gt=1.0, lt=3.0)
    cauchy_b: float = Field(0.0045, ge=0.0, le=0.1, description="um^2")
    # absorptiecoefficient (1/m) op een rij golflengten (nm); standaard ~0 (kleurloos)
    absorptie_nm: list[float] = Field(default_factory=lambda: [400.0, 700.0])
    absorptie_per_m: list[float] = Field(default_factory=lambda: [0.0, 0.0])
    # T17: verstrooiing in het volume (microbelletjes, stof). Vereenvoudigd model, geen gemeten materiaal:
    # een homogeen medium met een golflengte-onafhankelijke verstrooiingscoefficient en een Henyey-Greenstein-
    # fasefunctie (g = 0 is isotroop). De enkelvoudige-verstrooiingsalbedo volgt uit absorptie en verstrooiing.
    scattering_coeff: float = Field(0.0, ge=0.0, le=1e4, description="1/m; 0 = geen verstrooiing")
    scattering_g: float = Field(0.0, gt=-1.0, lt=1.0, description="asymmetrie van Henyey-Greenstein; 0 = isotroop")

    @property
    def heeft_medium(self) -> bool:
        """Is er volumetransport nodig (absorptie of verstrooiing in de epoxy)? Zo niet, dan is de scene
        identiek aan die van voor T17 (path-integrator, geen medium)."""
        return self.scattering_coeff > 0 or any(a > 0 for a in self.absorptie_per_m)

    @field_validator("absorptie_per_m")
    @classmethod
    def _niet_negatief(cls, v: list[float]) -> list[float]:
        if any(x < 0 for x in v):
            raise ValueError("absorptiecoefficient moet >= 0 zijn")
        return v

    def model_post_init(self, _ctx) -> None:
        if len(self.absorptie_nm) != len(self.absorptie_per_m) or not self.absorptie_nm:
            raise ValueError("absorptie_nm en absorptie_per_m moeten even lang en niet leeg zijn")

    def ior(self, golflengte_nm: float = NA_D_NM) -> float:
        """Brekingsindex bij de gegeven golflengte (Cauchy)."""
        return self.cauchy_a + self.cauchy_b / (golflengte_nm / 1000.0) ** 2

    @property
    def n_d(self) -> float:
        return self.ior(NA_D_NM)


RGB = tuple[float, float, float]
VerfSoort = Literal["matte", "glossy", "metallic", "candy"]  # "gloss" wordt als alias van "glossy" geaccepteerd
CandyBasis = Literal["metallic", "white"]


def _soort(v):
    return "glossy" if v == "gloss" else v


class Bare(_Model):
    """Onbehandeld: glad diëlektrisch grensvlak epoxy/lucht (met TIR)."""

    type: Literal["bare"] = "bare"


class Paint(_Model):
    """Ondoorzichtige verf in optisch contact met de epoxy (geen Fresnel-grensvlak aan de binnenkant)."""

    type: Literal["paint"] = "paint"
    color: RGB = Field((0.5, 0.5, 0.5), description="albedo, lineair RGB 0..1; invoer ook '#rrggbb' of 'RAL 9005'")
    kind: VerfSoort = "matte"
    roughness: float | None = Field(None, gt=0.0, le=1.0, description="GGX alpha van de glans; None = standaard per soort")
    candy_base: CandyBasis = Field("metallic", description="ondergrond van candy: metallic of white")
    # T18: welke verf uit de bibliotheek gekozen werd. Alleen een herinnering; de render gebruikt altijd de
    # instellingen in deze config zelf, zodat een config reproduceerbaar blijft.
    bibliotheek_id: str | None = Field(None, description="slug in data/verven/ (alleen herkomst, geen invloed op de render)")

    @field_validator("kind", mode="before")
    @classmethod
    def _alias(cls, v):
        return _soort(v)

    @field_validator("color", mode="before")
    @classmethod
    def _tekst(cls, v):
        return als_kleur(v)

    @field_validator("color")
    @classmethod
    def _kleur(cls, v: RGB) -> RGB:
        if any(not 0.0 <= x <= 1.0 for x in v):
            raise ValueError("kleur moet binnen 0..1 liggen")
        return v


class MatteClearCoat(_Model):
    """Kleurloze matte lak: ruw diëlektrisch grensvlak (GGX) epoxy/lucht.

    Standaardruwheid alpha = 0,3: een gespoten matte lak heeft microruwheid in de orde van enkele tienden van
    een micrometer met glansmeting 5-15 GU; GGX-alpha 0,3 geeft een duidelijk gespreide, maar nog herkenbare
    reflectie. Zeer ruw (alpha > 0,5) maakt het oppervlak vrijwel Lambertiaans.
    """

    type: Literal["clearcoat"] = "clearcoat"
    roughness: float = Field(0.3, gt=0.0, le=1.0, description="GGX alpha")


class PlateBelow(_Model):
    """Losse plaat onder het blok met een luchtspleet; het blok zelf blijft onbehandeld (alleen onderkant)."""

    type: Literal["plate"] = "plate"
    color: RGB = Field((0.5, 0.5, 0.5), description="albedo van de plaat, lineair RGB 0..1")
    gap_mm: float = Field(0.1, gt=0.0, le=50.0)
    kind: VerfSoort = "matte"
    roughness: float | None = Field(None, gt=0.0, le=1.0, description="GGX alpha van de glans; None = standaard per soort")
    candy_base: CandyBasis = "metallic"

    @field_validator("kind", mode="before")
    @classmethod
    def _alias(cls, v):
        return _soort(v)

    @field_validator("color", mode="before")
    @classmethod
    def _tekst(cls, v):
        return als_kleur(v)

    @field_validator("color")
    @classmethod
    def _kleur(cls, v: RGB) -> RGB:
        if any(not 0.0 <= x <= 1.0 for x in v):
            raise ValueError("kleur moet binnen 0..1 liggen")
        return v


ZijkantFinish = Annotated[Bare | Paint | MatteClearCoat, Field(discriminator="type")]
OnderkantFinish = Annotated[Bare | Paint | MatteClearCoat | PlateBelow, Field(discriminator="type")]
EdgeFinish = Bare | Paint | MatteClearCoat | PlateBelow


class _Item(_Model):
    count: int = Field(1, ge=1, le=500, description="aantal exemplaren van dit item in de laag")


class WoodSlice(_Item):
    """Onregelmatig houtschijfje: plat, diffuus, met een houtkleur. Elk exemplaar krijgt een eigen straal,
    omtrek en een lichte helderheidsvariatie (via de seed van de laag)."""

    type: Literal["wood"] = "wood"
    color: RGB = (0.45, 0.28, 0.13)
    radius_mm: tuple[float, float] = Field((8.0, 14.0), description="straal van het schijfje, (min, max)")
    thickness_mm: float = Field(3.0, gt=0.0, le=20.0)
    irregularity: float = Field(0.12, ge=0.0, le=0.4, description="relatieve afwijking van de ronde omtrek")

    @field_validator("color")
    @classmethod
    def _kleur(cls, v: RGB) -> RGB:
        if any(not 0.0 <= x <= 1.0 for x in v):
            raise ValueError("kleur moet binnen 0..1 liggen")
        return v

    @field_validator("radius_mm")
    @classmethod
    def _bereik(cls, v: tuple[float, float]) -> tuple[float, float]:
        if not 0 < v[0] <= v[1]:
            raise ValueError("radius_mm moet (min, max) zijn met 0 < min <= max")
        return v


class Flower(_Item):
    """Eenvoudige bloem: een rozet van gebogen, dunne blaadjes, licht doorschijnend (Disney thin: diffuse
    reflectie plus diffuse transmissie). `petals=1` geeft een los bloemblaadje."""

    type: Literal["flower"] = "flower"
    color: RGB = (0.9, 0.3, 0.45)
    petals: int = Field(6, ge=1, le=24)
    radius_mm: tuple[float, float] = Field((8.0, 12.0), description="lengte van de blaadjes, (min, max)")
    cup_mm: float = Field(2.5, ge=0.0, le=20.0, description="hoeveel de blaadjes aan de top omhoog buigen")
    tilt_deg: float = Field(15.0, ge=0.0, le=90.0, description="maximale willekeurige kanteling")
    translucency: float = Field(0.4, ge=0.0, le=1.0, description="fractie van het licht dat doorgelaten wordt")

    @field_validator("color")
    @classmethod
    def _kleur(cls, v: RGB) -> RGB:
        if any(not 0.0 <= x <= 1.0 for x in v):
            raise ValueError("kleur moet binnen 0..1 liggen")
        return v

    @field_validator("radius_mm")
    @classmethod
    def _bereik(cls, v: tuple[float, float]) -> tuple[float, float]:
        if not 0 < v[0] <= v[1]:
            raise ValueError("radius_mm moet (min, max) zijn met 0 < min <= max")
        return v


Item = Annotated[WoodSlice | Flower, Field(discriminator="type")]


class Layer(_Model):
    """Een gietlaag: inhoud die op `height_m` boven de onderkant van het blok zweeft (hoogte van het
    middenvlak van de items). Plaatsing is willekeurig maar reproduceerbaar via `seed`."""

    height_m: float = Field(gt=0.0, le=0.06)
    items: list[Item] = Field(default_factory=list)
    seed: int = 0
    edge_margin_mm: float = Field(3.0, ge=0.0, le=50.0, description="minimale afstand tot de rand van het blok")


class CameraConfig(_Model):
    positie: tuple[float, float, float] = (0.0, 0.55, 0.62)
    doel: tuple[float, float, float] = (0.0, 0.02, 0.0)
    fov: float = Field(40.0, gt=1.0, lt=120.0, description="graden, horizontaal")


class SceneConfig(_Model):
    camera: CameraConfig = Field(default_factory=CameraConfig)
    omgeving_radiantie: tuple[float, float, float] = (1.0, 1.0, 1.0)  # constante omgeving (RGB)
    vloer_grootte: float = Field(2.0, gt=0.0, description="zijde van de vierkante vloer, m")
    vloer_rastercel: float = Field(0.05, gt=0.0, description="cel van het rasterpatroon, m")
    vloer_albedo: tuple[float, float, float] = (0.75, 0.75, 0.72)
    vloer_lijn_albedo: tuple[float, float, float] = (0.03, 0.03, 0.03)
    # T07: naam uit environments.OMGEVINGEN (HDRI + vloer); None = constante omgeving met raster
    omgeving: str | None = None
    camera_preset: str | None = None  # boven, schuin30, schuin60, zittend, staand; overschrijft `camera`
    spot: bool = False  # extra spot boven het tafeltje (los te combineren met een HDRI)


class RenderSettings(_Model):
    breedte: int = Field(512, ge=16, le=8192)
    hoogte: int = Field(384, ge=16, le=8192)
    spp: int = Field(64, ge=1)
    max_depth: int = Field(24, ge=1, le=256)


class TableConfig(_Model):
    diameter: float = Field(0.35, gt=0.0, le=2.0, description="m; 0,35 of 0,50, maar vrij getal toegestaan")
    hoogte: float = Field(0.04, ge=0.02, le=0.06, description="m")
    segmenten: int = Field(128, ge=8, le=2048, description="aantal segmenten van de mantel")
    epoxy: EpoxyMaterial = Field(default_factory=EpoxyMaterial)
    zijkant: ZijkantFinish = Field(default_factory=Bare)
    onderkant: OnderkantFinish = Field(default_factory=Bare)
    top_roughness: float = Field(
        0.0, ge=0.0, le=0.5, description="T17: GGX-alpha van het bovenvlak; 0 = glad (roughdielectric vanaf > 0)"
    )
    layers: list[Layer] = Field(default_factory=list, description="gietlagen met inhoud (T06)")
    scene: SceneConfig = Field(default_factory=SceneConfig)
    render: RenderSettings = Field(default_factory=RenderSettings)
