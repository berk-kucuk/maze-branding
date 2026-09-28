#!/usr/bin/env python3
"""Finish a studio.py render: soft bloom, gentle vignette, OLED black point,
grain only on lit pixels.

    python3 post2.py <raw.png> <out.png> [--bloom 0.35]
"""
import os, sys
import numpy as np
from PIL import Image, ImageFilter

def blur(a, r):
    """Gaussian blur of a [0,1) float image, via 8-bit L channels scaled to use the full range."""
    s = max(float(a.max()), 1e-6)
    ch = [np.asarray(Image.fromarray(np.uint8(a[..., i] / s * 255)).filter(ImageFilter.GaussianBlur(r)), np.float32)
          for i in range(3)]
    return np.stack(ch, -1) / 255 * s

def main(raw, out, bloom=0.35):
    im = Image.open(raw)
    a = np.asarray(im, np.float32)
    a = a[..., :3] / (65535.0 if a.max() > 255 else 255.0)
    h, w = a.shape[:2]
    # bloom from highlights only, several radii for a natural falloff
    hi = np.clip(a - 0.55, 0, None).astype(np.float32)
    glow = sum(blur(hi, r * w / 2560) * k for r, k in ((6, 0.5), (24, 0.35), (80, 0.25)))
    a = a + glow * bloom
    # vignette: very light, it must not lift or tint the blacks
    yy, xx = np.mgrid[0:h, 0:w]
    d = np.sqrt(((xx - w / 2) / (w / 2)) ** 2 + ((yy - h / 2) / (h / 2)) ** 2)
    a *= (1 - 0.28 * np.clip(d - 0.55, 0, 1) ** 1.5)[..., None]
    a = np.clip(a, 0, 1) * 255
    bp = 2.0
    a = np.clip((a - bp) * 255.0 / (255.0 - bp), 0, 255)
    n = np.random.default_rng(7).normal(0, 1.2, (h, w, 1)).astype(np.float32)
    lum = a.mean(axis=2, keepdims=True) / 255
    a = a + n * np.clip(lum * 30, 0, 1)
    a = np.clip(np.round(a), 0, 255).astype(np.uint8)
    Image.fromarray(a, "RGB").save(out, optimize=True)
    print(f"{os.path.basename(out)}: {w}x{h}, true-black {100 * (a.max(axis=2) == 0).mean():.0f}%")

if __name__ == "__main__":
    b = float(sys.argv[sys.argv.index("--bloom") + 1]) if "--bloom" in sys.argv else 0.35
    main(sys.argv[1], sys.argv[2], b)
