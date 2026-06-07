"""
Generate the CogPrint PWA icon set: an indigo tile with a stylised neural
network (nodes + synapses), echoing the project's brain/neural theme.

Rendered at 4x and downscaled for smooth anti-aliased edges. Run with:
    python frontend/scripts/gen_icons.py
Outputs into frontend/public/.
"""
import math
import os

from PIL import Image, ImageDraw

OUT = os.path.join(os.path.dirname(__file__), "..", "public")
os.makedirs(OUT, exist_ok=True)

INDIGO = (79, 70, 229)       # brand-600 #4f46e5
INDIGO_DK = (67, 56, 202)    # brand-700 #4338ca
WHITE = (255, 255, 255)
LIGHT = (224, 231, 255)      # brand-100


def _bg(d, size, radius_frac, pad):
    """Rounded-rect (or full-bleed) indigo background with a soft vertical shade."""
    # vertical gradient
    for y in range(size):
        t = y / size
        r = int(INDIGO[0] * (1 - t) + INDIGO_DK[0] * t)
        g = int(INDIGO[1] * (1 - t) + INDIGO_DK[1] * t)
        b = int(INDIGO[2] * (1 - t) + INDIGO_DK[2] * t)
        d.line([(0, y), (size, y)], fill=(r, g, b))


def _network(d, size, cx, cy, scale):
    """Draw a small neural network glyph centred at (cx, cy)."""
    R = size * scale  # overall radius of the layout
    # node layout (unit circle-ish, brain-shaped spread), (x, y, node_radius_factor)
    nodes = [
        (-0.62, -0.20, 1.0),
        (-0.20, -0.62, 0.85),
        (0.28, -0.50, 0.9),
        (0.60, -0.05, 1.0),
        (0.30, 0.50, 0.9),
        (-0.25, 0.58, 0.85),
        (-0.05, 0.02, 1.25),   # hub
        (0.05, -0.18, 0.7),
    ]
    pts = [(cx + x * R, cy + y * R) for (x, y, _) in nodes]
    edges = [(6, 0), (6, 1), (6, 2), (6, 3), (6, 4), (6, 5),
             (0, 1), (1, 2), (2, 3), (3, 4), (4, 5), (5, 0), (6, 7)]
    lw = max(2, int(size * 0.012))
    for a, b in edges:
        d.line([pts[a], pts[b]], fill=LIGHT, width=lw)
    for (x, y, nf), p in zip(nodes, pts):
        nr = size * 0.045 * nf
        col = WHITE if nf >= 1.0 else LIGHT
        d.ellipse([p[0] - nr, p[1] - nr, p[0] + nr, p[1] + nr], fill=col)


def make(size, path, maskable=False, rounded=True):
    SS = 4
    S = size * SS
    img = Image.new("RGB", (S, S), INDIGO)
    d = ImageDraw.Draw(img)
    _bg(d, S, 0.22, 0)
    # maskable icons must keep content inside the central ~80% safe zone
    scale = 0.30 if maskable else 0.38
    _network(d, S, S / 2, S / 2, scale)
    img = img.resize((size, size), Image.LANCZOS)
    if rounded and not maskable:
        # apply rounded-corner alpha mask for the standard icon
        mask = Image.new("L", (size, size), 0)
        md = ImageDraw.Draw(mask)
        md.rounded_rectangle([0, 0, size - 1, size - 1], radius=int(size * 0.22), fill=255)
        out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        out.paste(img, (0, 0), mask)
        out.save(path)
    else:
        img.save(path)
    print("wrote", os.path.relpath(path))


make(192, os.path.join(OUT, "pwa-192x192.png"))
make(512, os.path.join(OUT, "pwa-512x512.png"))
make(512, os.path.join(OUT, "pwa-maskable-512x512.png"), maskable=True, rounded=False)
make(180, os.path.join(OUT, "apple-touch-icon.png"))
make(32, os.path.join(OUT, "favicon-32x32.png"))
print("done")
