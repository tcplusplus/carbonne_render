"""Rooktest: glazen bol op een vloer, constante omgeving, spectraal, naar PNG."""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import mitsuba as mi

from carbonne.core.variant import select_variant


def smoke_scene(res: int = 256, spp: int = 64) -> dict:
    return {
        "type": "scene",
        "integrator": {"type": "path", "max_depth": 12},
        "sensor": {
            "type": "perspective",
            "fov": 35,
            "to_world": mi.ScalarTransform4f().look_at(
                origin=[0, 0.6, 3.2], target=[0, 0.3, 0], up=[0, 1, 0]
            ),
            "film": {"type": "hdrfilm", "width": res, "height": res, "rfilter": {"type": "gaussian"}},
            "sampler": {"type": "independent", "sample_count": spp},
        },
        "env": {"type": "constant", "radiance": {"type": "rgb", "value": [0.8, 0.85, 0.9]}},
        "floor": {
            "type": "rectangle",
            "to_world": mi.ScalarTransform4f().rotate([1, 0, 0], -90).scale(5),
            "bsdf": {"type": "diffuse", "reflectance": {"type": "rgb", "value": [0.55, 0.45, 0.35]}},
        },
        "ball": {
            "type": "sphere",
            "center": [0, 0.5, 0],
            "radius": 0.5,
            "bsdf": {"type": "dielectric", "int_ior": "bk7", "ext_ior": "air"},
        },
    }


def render_smoke(res: int = 256, spp: int = 64):
    """Render de rooktest en geef (bitmap, seconden) terug; de variant moet al gezet zijn."""
    scene = mi.load_dict(smoke_scene(res, spp))
    t0 = time.perf_counter()
    img = mi.render(scene, spp=spp)
    bmp = mi.Bitmap(img)  # forceert evaluatie
    return bmp, time.perf_counter() - t0


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--res", type=int, default=256)
    p.add_argument("--spp", type=int, default=64)
    p.add_argument("--out", type=Path, default=Path("out/smoke.png"))
    a = p.parse_args()
    variant = select_variant()
    print(f"variant: {variant}")
    bmp, secs = render_smoke(a.res, a.spp)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    bmp.convert(mi.Bitmap.PixelFormat.RGB, mi.Struct.Type.UInt8, srgb_gamma=True).write(str(a.out))
    print(f"render: {a.res}x{a.res} @ {a.spp} spp in {secs:.2f} s -> {a.out}")


if __name__ == "__main__":
    main()
