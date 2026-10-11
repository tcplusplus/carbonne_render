#!/usr/bin/env python3
"""T08: teken de convergentiecurve (t08-curve.json uit t08_convergentie.py) als SVG, log-log.
Gebruik: python scripts/t08_curve_svg.py out/t08-curve.json docs/evidence/img/T08-convergentie.svg"""

import json
import math
import sys

rijen = json.load(open(sys.argv[1]))
W, H, L, R, T, B = 640, 380, 70, 20, 40, 55
xs = [r["spp"] for r in rijen]
x0, x1 = math.log10(min(xs)), math.log10(max(xs))
y0, y1 = math.log10(0.015), math.log10(0.15)


def px(v):
    return L + (math.log10(v) - x0) / (x1 - x0) * (W - L - R)


def py(v):
    return H - B - (math.log10(v) - y0) / (y1 - y0) * (H - T - B)


def lijn(sleutel, kleur, extra=""):
    pts = " ".join(f"{px(r['spp']):.1f},{py(r[sleutel]):.1f}" for r in rijen)
    return f'<polyline points="{pts}" fill="none" stroke="{kleur}" stroke-width="2" {extra}/>'


o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" font-family="sans-serif" font-size="12">',
     f'<rect width="{W}" height="{H}" fill="white"/>',
     f'<text x="{L}" y="22" font-size="14" font-weight="bold">Ruis tegenover samples per pixel (320x180, 12 threads)</text>']
for v in (0.02, 0.03, 0.05, 0.1):
    o.append(f'<line x1="{L}" x2="{W - R}" y1="{py(v):.1f}" y2="{py(v):.1f}" stroke="#ddd"/>'
             f'<text x="{L - 6}" y="{py(v) + 4:.1f}" text-anchor="end">{v}</text>')
for v in (64, 128, 256, 512, 1024, 2048):
    o.append(f'<line y1="{T}" y2="{H - B}" x1="{px(v):.1f}" x2="{px(v):.1f}" stroke="#ddd"/>'
             f'<text x="{px(v):.1f}" y="{H - B + 16}" text-anchor="middle">{v}</text>')
# tijd-as: ongeveer 26,4 ms per spp-pass-eenheid; toon als tweede label
tps = rijen[-1]["tijd_s"] / rijen[-1]["spp"]
for v in (64, 256, 1024):
    o.append(f'<text x="{px(v):.1f}" y="{H - B + 30}" text-anchor="middle" fill="#666">{v * tps:.0f} s</text>')
o += [lijn("echt", "#c0392b"), lijn("schatting", "#2471a3", 'stroke-dasharray="6 3"'),
      f'<text x="{(L + W - R) / 2}" y="{H - 8}" text-anchor="middle">samples per pixel (onder: tijd)</text>',
      f'<text x="{W - R - 6}" y="{T + 14}" text-anchor="end" fill="#c0392b">werkelijke fout (tegen referentie 8192 spp)</text>',
      f'<text x="{W - R - 6}" y="{T + 30}" text-anchor="end" fill="#2471a3">schatting uit twee helften (pijplijn)</text>',
      f'<text transform="translate(16 {(T + H - B) / 2}) rotate(-90)" text-anchor="middle">relatieve ruis</text>',
      "</svg>"]
open(sys.argv[2], "w").write("\n".join(o))
