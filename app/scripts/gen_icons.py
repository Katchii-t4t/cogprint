"""
Generate the CogPrint *consumer app* PWA icon set: a dark ink tile with a
stylised neural network in cyan (matching the app's dark/neural theme — this is
deliberately different from the research platform's indigo icons).

Rendered at 4x and downscaled for smooth anti-aliased edges. Run with:
    python app/scripts/gen_icons.py
Outputs into app/public/.
"""
import os

from PIL import Image, ImageDraw

OUT = os.path.join(os.path.dirname(__file__), "..", "public")
os.makedirs(OUT, exist_ok=True)

INK = (8, 12, 24)          # ink-900 #080c18
INK_DK = (4, 8, 16)        # ink-950 #040810
NEURAL = (34, 211, 238)    # neural #22d3ee
GLOW = (103, 232, 249)     # neural-glow #67e8f9


def _bg(d, size):
    """Dark vertical gradient background."""
    for y in range(size):
        t = y / size
        r = int(INK[0] * (1 - t) + INK_DK[0] * t)
        g = int(INK[1] * (1 - t) + INK_DK[1] * t)
        b = int(INK[2] * (1 - t) + INK_DK[2] * t)
        d.line([(0, y), (size, y)], fill=(r, g, b))


def _network(d, size, cx, cy, scale):
    """Draw a small neural network glyph centred at (cx, cy)."""
    R = size * scale
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
        d.line([pts[a], pts[b]], fill=NEURAL, width=lw)
    for (x, y, nf), p in zip(nodes, pts):
        nr = size * 0.045 * nf
        col = GLOW if nf >= 1.0 else NEURAL
        d.ellipse([p[0] - nr, p[1] - nr, p[0] + nr, p[1] + nr], fill=col)


def make(size, path, maskable=False, rounded=True):
    SS = 4
    S = size * SS
    img = Image.new("RGB", (S, S), INK)
    d = ImageDraw.Draw(img)
    _bg(d, S)
    scale = 0.30 if maskable else 0.38
    _network(d, S, S / 2, S / 2, scale)
    img = img.resize((size, size), Image.LANCZOS)
    if rounded and not maskable:
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
