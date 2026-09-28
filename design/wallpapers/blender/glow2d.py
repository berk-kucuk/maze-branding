#!/usr/bin/env python3
"""Maze Linux — soft-light wallpapers (2D). Heavily blurred light shapes on
true black, a faint maze texture caught only inside the light, and a small
mark in the lower right.

    python3 glow2d.py <out-dir>
"""
import json, os, sys, random
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
W, H = 2560, 1440
sys.path.insert(0, HERE)

def maze_mask(cell, seed):
    cols, rows = W // cell + 2, H // cell + 2
    rnd = random.Random(seed)
    seen = [[False] * cols for _ in range(rows)]
    im = Image.new("L", (W, H), 0); d = ImageDraw.Draw(im)
    stack = [(0, 0)]; seen[0][0] = True
    # draw the passages; walls are what's left
    while stack:
        c, r = stack[-1]
        nb = [(c+dc, r+dr) for dc, dr in ((1,0),(-1,0),(0,1),(0,-1))
              if 0 <= c+dc < cols and 0 <= r+dr < rows and not seen[r+dr][c+dc]]
        if not nb: stack.pop(); continue
        nc, nr = rnd.choice(nb); seen[nr][nc] = True
        d.line([(c*cell, r*cell), (nc*cell, nr*cell)], fill=255, width=2)
        stack.append((nc, nr))
    return np.asarray(im, np.float32) / 255

def blob(cx, cy, rx, ry, rot=0):
    im = Image.new("L", (W, H), 0)
    ImageDraw.Draw(im).ellipse([cx-rx, cy-ry, cx+rx, cy+ry], fill=255)
    if rot: im = im.rotate(rot, center=(cx, cy), resample=Image.BICUBIC)
    return im

def field(blobs, radius):
    acc = np.zeros((H, W, 3), np.float32)
    for (cx, cy, rx, ry, rot), col, k in blobs:
        m = np.asarray(blob(cx, cy, rx, ry, rot).filter(ImageFilter.GaussianBlur(radius)), np.float32) / 255
        acc += m[..., None] * np.array(col, np.float32) * k
    return acc

def mark_layer(size, x, y):
    d = json.load(open(os.path.join(HERE, "mark.json")))
    e = d["edges"]; span = e[-1] - e[0]; g = d["grid"]
    im = Image.new("L", (W, H), 0); dr = ImageDraw.Draw(im)
    for r in range(len(g)):
        for c in range(len(g[0])):
            if g[r][c]:
                x0 = x + (e[c] - e[0]) / span * size; x1 = x + (e[c+1] - e[0]) / span * size
                y0 = y + (e[r] - e[0]) / span * size; y1 = y + (e[r+1] - e[0]) / span * size
                dr.rectangle([x0, y0, x1 - 1, y1 - 1], fill=255)
    return np.asarray(im, np.float32) / 255

def finish(a, out):
    a = np.clip(a, 0, 1) ** 1.15 * 255          # a touch more contrast toward black
    bp = 2.0
    a = np.clip((a - bp) * 255.0 / (255.0 - bp), 0, 255)
    n = np.random.default_rng(3).normal(0, 1.6, (H, W, 1)).astype(np.float32)
    lum = a.mean(axis=2, keepdims=True) / 255
    a = np.clip(np.round(a + n * np.clip(lum * 30, 0, 1)), 0, 255).astype(np.uint8)
    Image.fromarray(a, "RGB").save(out, optimize=True)
    print(f"{os.path.basename(out)}: true-black {100 * (a.max(axis=2) == 0).mean():.0f}%")

def make(out, blobs, radius, seed, tex=0.07):
    light = field(blobs, radius)
    mz = maze_mask(64, seed)
    mz = np.asarray(Image.fromarray((mz * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.2)), np.float32) / 255
    lum = light.max(axis=2, keepdims=True)
    a = light * (1 - tex) + light * mz[..., None] * tex * 3.0
    mk = mark_layer(58, W - 150, H - 150)
    a = a * (1 - mk[..., None]) + mk[..., None] * 0.82
    finish(a, out)

if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "."
    os.makedirs(out, exist_ok=True)
    make(os.path.join(out, "maze-nebula.png"), [
        ((2050, 1500, 900, 380, -18), (0.28, 0.20, 0.95), 1.1),
        ((1500, 1600, 700, 260, -10), (0.05, 0.55, 0.85), 0.8),
        ((2400, 1150, 380, 200, -30), (0.70, 0.45, 1.00), 0.35),
    ], 220, 5)
    make(os.path.join(out, "maze-dawn.png"), [
        ((1280, 1750, 1500, 460, 0), (0.55, 0.64, 0.95), 1.0),
        ((1280, 1640, 800, 170, 0), (0.95, 0.96, 1.0), 0.9),
    ], 240, 9, tex=0.1)
    make(os.path.join(out, "maze-ember.png"), [
        ((350, -200, 1100, 520, 25), (1.00, 0.40, 0.16), 1.0),
        ((650, -120, 600, 260, 15), (1.00, 0.68, 0.38), 0.6),
    ], 230, 13)
