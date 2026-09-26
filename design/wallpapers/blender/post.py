#!/usr/bin/env python3
"""Finish a Blender render for Maze: OLED black point, grain only on lit
pixels, optional corner logo.

    python3 post.py <raw.png> <out.png> [--logo]
"""
import os, sys
import numpy as np
from PIL import Image

SRC = "/run/media/berkkucukk/Backup/Projects/Maze-Linux-Source"
LOGO = os.path.join(SRC, "maze-installer/maze-installer/usr/share/calamares/branding/maze/maze-logo.png")

def main(raw, out, logo=False):
    a = np.asarray(Image.open(raw).convert("RGB"), np.float32)
    h, w = a.shape[:2]
    # Black point: the denoiser leaves 1-2 levels of noise in unlit areas.
    # Pull them to exactly 0 so an OLED panel switches those pixels off.
    bp = 2.0
    a = np.clip((a - bp) * 255.0 / (255.0 - bp), 0, 255)
    if logo:
        lg = Image.open(LOGO).convert("RGBA")
        lw = 300; lh = int(lg.height * lw / lg.width)
        la = np.asarray(lg.resize((lw, lh), Image.LANCZOS), np.float32) / 255
        x0, y0 = w - 240 - lw // 2, h - 140 - lh // 2
        al = la[..., 3:4] * 0.9
        a[y0:y0+lh, x0:x0+lw] = a[y0:y0+lh, x0:x0+lw] * (1 - al) + la[..., :3] * 255 * al
    n = np.random.default_rng(7).normal(0, 1.3, (h, w, 1)).astype(np.float32)
    lum = a.mean(axis=2, keepdims=True) / 255
    a = a + n * np.clip(lum * 30, 0, 1)
    a = np.clip(np.round(a), 0, 255).astype(np.uint8)
    Image.fromarray(a, "RGB").save(out, optimize=True)
    print(f"{os.path.basename(out)}: {w}x{h}, true-black {100 * (a.max(axis=2) == 0).mean():.0f}%")

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], "--logo" in sys.argv)
