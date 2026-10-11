"""Uitvoer: tonemapping, PNG-codering en EXR.

Tonemapping (vast, gedocumenteerd): lineair RGB x 2^EV, daarna hard afkappen op [0, 1] en de sRGB-overdrachtsfunctie
(IEC 61966-2-1). Bewust geen filmische curve: kleuren en verhoudingen blijven meetbaar; wat boven 1 uitkomt
(zon, spiegelende highlights) clipt. De lineaire EXR is de bron van waarheid.
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

import numpy as np


def tonemap_srgb(rgb: np.ndarray, ev: float = 0.0) -> np.ndarray:
    """Lineair RGB (h, w, >=3) -> sRGB uint8 (h, w, 3)."""
    x = np.clip(rgb[..., :3].astype(np.float64) * 2.0**ev, 0.0, 1.0)
    s = np.where(x <= 0.0031308, 12.92 * x, 1.055 * np.power(x, 1 / 2.4) - 0.055)
    return np.rint(np.clip(s, 0, 1) * 255).astype(np.uint8)


def png_bytes(img8: np.ndarray) -> bytes:
    """Minimale PNG-encoder (8 bit RGB), zonder extra afhankelijkheden."""
    h, w, _ = img8.shape
    raw = np.concatenate([np.zeros((h, 1), np.uint8), img8.reshape(h, w * 3)], axis=1).tobytes()

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 6))
        + chunk(b"IEND", b"")
    )


def png_van_lineair(rgb: np.ndarray, ev: float = 0.0) -> bytes:
    return png_bytes(tonemap_srgb(rgb, ev))


def schrijf_exr(pad: Path, beeld: np.ndarray, kanaalnamen: list[str]) -> None:
    """Schrijf alle kanalen (h, w, c) als multichannel-EXR (float32)."""
    import mitsuba as mi

    bmp = mi.Bitmap(np.ascontiguousarray(beeld, dtype=np.float32), mi.Bitmap.PixelFormat.MultiChannel, channel_names=kanaalnamen)
    bmp.write(str(pad))
