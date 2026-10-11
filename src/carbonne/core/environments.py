"""Omgevingen: HDRI-interieurs, vloeren, camerapresets en een optionele spot.

Het tafeltje heeft zijn onderkant op y = 0 (zie scene.py). Een preset legt de vloer op
y = hoogte - TAFEL_HOOGTE, zodat de bovenkant van het blad op ~45 cm boven de vloer zweeft (poten ontbreken nog).
`pas_omgeving_toe` werkt op het scenedict van `build_scene` en vervangt daarin env, vloer en (optioneel) camera.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from carbonne.core.config import CameraConfig, TableConfig

TAFEL_HOOGTE = 0.45  # m, bovenkant blad boven de vloer
KAMER_OOGHOOGTE = 0.80  # m boven de vloer (camerapreset "kamer")
KAMER_NEIGING = 9.0  # graden onder de horizon waarmee "kamer" kijkt; de horizon valt dan net boven het midden van het beeld
KAMER_FOV = 55.0  # horizontaal, graden
VLOER_GROOTTE = 40.0  # m; groot genoeg dat de rand nooit in beeld komt


def assets_dir() -> Path:
    """assets/ in de projectroot (of CARBONNE_ASSETS)."""
    import os

    if env := os.environ.get("CARBONNE_ASSETS"):
        return Path(env)
    return Path(__file__).resolve().parents[3] / "assets"


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Vloer(_M):
    naam: str
    bestand: str | None  # relatief aan assets/, None = effen
    tegel_m: float = Field(gt=0, description="zijde van een herhaling van de textuur, m (schatting)")
    albedo: tuple[float, float, float] = (0.5, 0.5, 0.5)  # terugval als het bestand ontbreekt


class Hdri(_M):
    naam: str
    bestand: str | None  # relatief aan assets/; None = synthetisch


class Spot(_M):
    hoogte: float = 1.0  # m boven het blad
    intensiteit: float = 30.0  # W/sr, RGB gelijk
    kegelhoek: float = 25.0  # graden (halve opening)


class Omgeving(_M):
    naam: str
    omschrijving: str
    hdri: Hdri
    rotatie: float = 0.0  # graden om de y-as
    schaal: float = 1.0  # belichtingsschaal
    vloer: Vloer
    spot: Spot | None = None


VLOEREN = {
    "parket": Vloer(naam="parket", bestand="vloer/diagonal_parquet_diff_2k.jpg", tegel_m=2.0, albedo=(0.35, 0.22, 0.12)),
    "tegel": Vloer(naam="tegel", bestand="vloer/large_floor_tiles_02_diff_2k.jpg", tegel_m=1.2, albedo=(0.7, 0.7, 0.68)),
    "beton": Vloer(naam="beton", bestand="vloer/smooth_concrete_floor_diff_2k.jpg", tegel_m=2.0, albedo=(0.4, 0.4, 0.4)),
    "tapijt": Vloer(naam="tapijt", bestand="vloer/dirty_carpet_diff_2k.jpg", tegel_m=1.0, albedo=(0.3, 0.28, 0.25)),
}

_S = Hdri  # afkorting
OMGEVINGEN: dict[str, Omgeving] = {
    o.naam: o
    for o in (
        Omgeving(
            naam="woonkamer",
            omschrijving="woonkamer met raam, parket",
            hdri=_S(naam="blinds", bestand="hdri/blinds_2k.hdr"),
            rotatie=0.0,
            vloer=VLOEREN["parket"],
        ),
        Omgeving(
            naam="studio",
            omschrijving="studio met softboxen, beton",
            hdri=_S(naam="studio_small_09", bestand="hdri/studio_small_09_2k.hdr"),
            vloer=VLOEREN["beton"],
        ),
        Omgeving(
            naam="avond",
            omschrijving="avondlicht met lampen, tapijt",
            hdri=_S(naam="comfy_cafe", bestand="hdri/comfy_cafe_2k.hdr"),
            vloer=VLOEREN["tapijt"],
        ),
        Omgeving(
            naam="bewolkt",
            omschrijving="bewolkt daglicht door ramen, lichte tegel",
            hdri=_S(naam="artist_workshop", bestand="hdri/artist_workshop_2k.hdr"),
            vloer=VLOEREN["tegel"],
        ),
        Omgeving(
            naam="spot",
            omschrijving="donkere kamer met alleen een spot boven het tafeltje, beton",
            hdri=_S(naam="donker", bestand=None),
            schaal=0.03,
            vloer=VLOEREN["beton"],
            spot=Spot(),
        ),
    )
}


def camera_preset(naam: str, diameter: float, hoogte: float) -> CameraConfig:
    """Camera voor een preset: kamer (bijna horizontaal), boven, schuin30, schuin60, zittend, staand (kijkt naar het midden van het blad)."""
    doel = (0.0, hoogte, 0.0)
    afstand = max(0.9, 2.4 * diameter)
    if naam == "boven":
        # recht van boven; 'up' ligt in het vlak, dus een iets verschoven positie om een gimbal-situatie te vermijden
        return CameraConfig(positie=(0.0, hoogte + afstand, 1e-4), doel=doel, fov=40.0)
    if naam in ("schuin30", "schuin60"):
        el = math.radians(30 if naam == "schuin30" else 60)
        return CameraConfig(
            positie=(0.0, hoogte + afstand * math.sin(el), afstand * math.cos(el)), doel=doel, fov=40.0
        )
    if naam == "zittend":  # oog op 1,10 m boven de vloer, 1,6 m van het tafeltje
        return CameraConfig(positie=(0.0, 1.10 - TAFEL_HOOGTE + hoogte, 1.6), doel=doel, fov=40.0)
    if naam == "staand":  # oog op 1,65 m boven de vloer, 1,2 m van het tafeltje
        return CameraConfig(positie=(0.0, 1.65 - TAFEL_HOOGTE + hoogte, 1.2), doel=doel, fov=40.0)
    if naam == "kamer":  # kijkt bijna horizontaal: de ruimte (HDRI) achter het tafeltje is zichtbaar, niet alleen de vloer
        afstand = max(1.0, 2.8 * diameter)
        oog = KAMER_OOGHOOGTE - TAFEL_HOOGTE + hoogte  # oog boven y = 0 (onderkant van het blok)
        return CameraConfig(
            positie=(0.0, oog, afstand), doel=(0.0, oog - afstand * math.tan(math.radians(KAMER_NEIGING)), 0.0), fov=KAMER_FOV
        )
    raise KeyError(f"onbekende camerapreset {naam!r}; kies uit {CAMERA_PRESETS}")


CAMERA_PRESETS = ("kamer", "boven", "schuin30", "schuin60", "zittend", "staand")


def synthetische_hdri(breedte: int = 256, hoogte: int = 128) -> np.ndarray:
    """Nep-HDRI (equirechthoekig, float32 RGB): lichte lucht-gradient met een felle 'raam'-vlek en een zachte softbox."""
    v = (np.arange(hoogte) + 0.5) / hoogte
    u = (np.arange(breedte) + 0.5) / breedte
    uu, vv = np.meshgrid(u, v)
    img = np.empty((hoogte, breedte, 3), np.float32)
    img[:] = (0.15 + 0.35 * (1 - vv))[..., None]
    raam = ((np.abs(uu - 0.25) < 0.05) & (np.abs(vv - 0.4) < 0.1))[..., None]
    softbox = ((np.abs(uu - 0.7) < 0.08) & (np.abs(vv - 0.25) < 0.08))[..., None]
    img = np.where(raam, 20.0, img)
    img = np.where(softbox, 8.0, img)
    return img.astype(np.float32)


def _env_dict(om: Omgeving, assets: Path) -> dict:
    import mitsuba as mi

    to_world = mi.ScalarTransform4f().rotate([0, 1, 0], om.rotatie)
    pad = assets / om.hdri.bestand if om.hdri.bestand else None
    if pad is not None and pad.exists():
        return {"type": "envmap", "filename": str(pad), "scale": om.schaal, "to_world": to_world}
    return {"type": "envmap", "bitmap": mi.Bitmap(synthetische_hdri()), "scale": om.schaal, "to_world": to_world}


def _vloer_dict(v: Vloer, y: float, assets: Path) -> dict:
    import mitsuba as mi

    pad = assets / v.bestand if v.bestand else None
    if pad is not None and pad.exists():
        refl: dict = {
            "type": "bitmap",
            "filename": str(pad),
            "raw": False,
            "wrap_mode": "repeat",
            "filter_type": "bilinear",
            "to_uv": mi.ScalarTransform4f().scale([VLOER_GROOTTE / v.tegel_m] * 2 + [1]),
        }
    else:
        refl = {"type": "rgb", "value": list(v.albedo)}
    return {
        "type": "rectangle",
        "to_world": mi.ScalarTransform4f().translate([0, y, 0]).rotate([1, 0, 0], -90).scale(VLOER_GROOTTE / 2),
        "bsdf": {"type": "diffuse", "reflectance": refl},
    }


def pas_omgeving_toe(scene: dict, config: TableConfig, assets: Path | None = None) -> dict:
    """Vervang env/vloer (en camera) in het scenedict volgens `config.scene.omgeving` / `camera_preset` / `spot`."""
    import mitsuba as mi

    sc = config.scene
    assets = assets or assets_dir()
    if sc.camera_preset is not None:
        cam = camera_preset(sc.camera_preset, config.diameter, config.hoogte)
        up = [0, 0, -1] if sc.camera_preset == "boven" else [0, 1, 0]
        scene["sensor"]["fov"] = cam.fov
        scene["sensor"]["to_world"] = mi.ScalarTransform4f().look_at(
            origin=list(cam.positie), target=list(cam.doel), up=up
        )
    if sc.omgeving is not None:
        om = OMGEVINGEN[sc.omgeving]
        scene["env"] = _env_dict(om, assets)
        scene["floor"] = _vloer_dict(om.vloer, config.hoogte - TAFEL_HOOGTE, assets)
        spot = om.spot
    else:
        spot = None
    if sc.spot or spot is not None:
        s = spot or Spot()
        y = config.hoogte + s.hoogte
        scene["spot"] = {
            "type": "spot",
            "to_world": mi.ScalarTransform4f().look_at(origin=[0, y, 0], target=[0, 0, 0], up=[0, 0, 1]),
            "intensity": {"type": "rgb", "value": [s.intensiteit] * 3},
            "cutoff_angle": s.kegelhoek,
            "beam_width": s.kegelhoek * 0.7,
        }
    return scene
