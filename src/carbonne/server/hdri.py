"""Kleine (1k) HDRI's voor de three.js-preview, als Radiance RGBE (.hdr); eenmalig gegenereerd en gecachet."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from carbonne.core.environments import OMGEVINGEN, assets_dir, synthetische_hdri

BREEDTE, HOOGTE = 1024, 512


def _verklein(img: np.ndarray, b: int, h: int) -> np.ndarray:
    """Blokgemiddelde (lineair) naar b x h; werkt ook als de bron kleiner is (dan nearest)."""
    hh, bb = img.shape[:2]
    if bb % b == 0 and hh % h == 0:
        return img.reshape(h, hh // h, b, bb // b, 3).mean(axis=(1, 3))
    yi = (np.arange(h) * hh // h)
    xi = (np.arange(b) * bb // b)
    return img[yi][:, xi]


def schrijf_rgbe(pad: Path, rgb: np.ndarray) -> None:
    rgb = np.clip(rgb.astype(np.float64), 0, None)
    m = rgb.max(axis=2)
    mant, exp = np.frexp(m)
    schaal = np.where(m > 1e-32, mant * 256.0 / np.maximum(m, 1e-32), 0.0)
    rgbe = np.zeros(rgb.shape[:2] + (4,), np.uint8)
    rgbe[..., :3] = np.clip(rgb * schaal[..., None], 0, 255).astype(np.uint8)
    rgbe[..., 3] = np.where(m > 1e-32, exp + 128, 0).astype(np.uint8)
    h, b = rgb.shape[:2]
    pad.parent.mkdir(parents=True, exist_ok=True)
    with pad.open("wb") as f:
        f.write(b"#?RADIANCE\nFORMAT=32-bit_rle_rgbe\n\n" + f"-Y {h} +X {b}\n".encode())
        f.write(rgbe.tobytes())


def lees_hdr(pad: Path) -> np.ndarray:
    import mitsuba as mi

    from carbonne.core.variant import select_variant

    select_variant()
    return np.array(mi.Bitmap(str(pad)), dtype=np.float32)[..., :3]


def hdri_1k(naam: str, cache_map: Path) -> Path:
    """Pad naar de 1k-versie van de HDRI van omgeving `naam`; maakt hem bij de eerste vraag. KeyError als onbekend."""
    om = OMGEVINGEN[naam]
    doel = cache_map / "hdri" / f"{om.hdri.naam}_1k.hdr"
    if doel.exists():
        return doel
    bron = assets_dir() / om.hdri.bestand if om.hdri.bestand else None
    img = lees_hdr(bron) if bron is not None and bron.exists() else synthetische_hdri(BREEDTE, HOOGTE)
    schrijf_rgbe(doel, _verklein(img, BREEDTE, HOOGTE) if img.shape[1] > BREEDTE else img)
    return doel
