"""Render de heldere cilinder (T02): `uv run carbonne-t02 --diameter 0.35 --hoogte 0.04 --out out/t02.png`."""

from __future__ import annotations

import argparse
from pathlib import Path

import mitsuba as mi

from carbonne.core.config import TableConfig
from carbonne.core.variant import select_variant


def render_config(config: TableConfig):
    from carbonne.core.scene import build_scene

    scene = mi.load_dict(build_scene(config))
    return mi.Bitmap(mi.render(scene, spp=config.render.spp))


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--diameter", type=float, default=0.35)
    p.add_argument("--hoogte", type=float, default=0.04)
    p.add_argument("--res", type=int, default=512)
    p.add_argument("--spp", type=int, default=128)
    p.add_argument("--out", type=Path, default=Path("out/t02.png"))
    a = p.parse_args()
    print("variant:", select_variant())
    cfg = TableConfig(diameter=a.diameter, hoogte=a.hoogte)
    cfg.render.breedte, cfg.render.hoogte, cfg.render.spp = a.res, a.res * 3 // 4, a.spp
    bmp = render_config(cfg)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    bmp.convert(mi.Bitmap.PixelFormat.RGB, mi.Struct.Type.UInt8, srgb_gamma=True).write(str(a.out))
    print("->", a.out)


if __name__ == "__main__":
    main()
