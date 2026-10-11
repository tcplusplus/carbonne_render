"""Configuratiemodel: het hele tafeltje en de scene in een JSON-serialiseerbaar pydantic-model."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

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
VerfSoort = Literal["matte", "glossy", "metallic", "candy"]  # alleen "matte" is gebouwd (T05 volgt)


class Bare(_Model):
    """Onbehandeld: glad diëlektrisch grensvlak epoxy/lucht (met TIR)."""

    type: Literal["bare"] = "bare"


class Paint(_Model):
    """Ondoorzichtige verf in optisch contact met de epoxy (geen Fresnel-grensvlak aan de binnenkant)."""

    type: Literal["paint"] = "paint"
    color: RGB = Field((0.5, 0.5, 0.5), description="albedo, lineair RGB 0..1")
    kind: VerfSoort = "matte"

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

    @field_validator("color")
    @classmethod
    def _kleur(cls, v: RGB) -> RGB:
        if any(not 0.0 <= x <= 1.0 for x in v):
            raise ValueError("kleur moet binnen 0..1 liggen")
        return v


ZijkantFinish = Annotated[Bare | Paint | MatteClearCoat, Field(discriminator="type")]
OnderkantFinish = Annotated[Bare | Paint | MatteClearCoat | PlateBelow, Field(discriminator="type")]
EdgeFinish = Bare | Paint | MatteClearCoat | PlateBelow


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
    scene: SceneConfig = Field(default_factory=SceneConfig)
    render: RenderSettings = Field(default_factory=RenderSettings)
