#!/usr/bin/env python3
"""Maze Linux — generative monochrome wallpapers (2D, anti-aliased).

    python3 lines2d.py <out-dir> [topo|flow|halftone ...]

topo      topographic contour lines; the mark rises out of the terrain
flow      thousands of thin streamlines bending around the mark
halftone  Nothing-style dot matrix: the mark's glow, sampled as dots
"""
import json, math, os, sys
import numpy as np
import cairo
from PIL import Image, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
W, H = 2560, 1440
GRID = json.load(open(os.path.join(HERE, "mark.json")))


def mark_rects(size, x0, y0):
    """The mark's filled cells as (x, y, w, h) rectangles, top-left at x0,y0."""
    e = GRID["edges"]; span = e[-1] - e[0]; g = GRID["grid"]
    f = lambda v: (v - e[0]) / span * size
    return [(x0 + f(e[c]), y0 + f(e[r]), f(e[c + 1]) - f(e[c]), f(e[r + 1]) - f(e[r]))
            for r in range(len(g)) for c in range(len(g[0])) if g[r][c]]

def mark_mask(size, cx, cy, w=W, h=H):
    s = cairo.ImageSurface(cairo.FORMAT_A8, w, h); ctx = cairo.Context(s)
    for x, y, rw, rh in mark_rects(size, cx - size / 2, cy - size / 2):
        ctx.rectangle(x, y, rw, rh)
    ctx.fill()
    a = np.ndarray((h, s.get_stride()), np.uint8, s.get_data())[:, :w]
    return a.astype(np.float32) / 255

def _box(a, r, axis):
    """Float box blur of radius r along one axis (edge-clamped), via cumsum."""
    r = int(max(1, r))
    pad = [(0, 0)] * a.ndim; pad[axis] = (r + 1, r)
    c = np.cumsum(np.pad(a, pad, mode="edge"), axis=axis, dtype=np.float64)
    n = a.shape[axis]
    hi = np.take(c, np.arange(2 * r + 1, 2 * r + 1 + n), axis=axis)
    lo = np.take(c, np.arange(0, n), axis=axis)
    return ((hi - lo) / (2 * r + 1)).astype(np.float32)

def gblur(a, sigma):
    """Gaussian blur in full float precision: three box passes per axis."""
    r = max(1, int(round(sigma * 0.93)))
    for _ in range(3):
        a = _box(a, r, 0); a = _box(a, r, 1)
    return a

def smooth_noise(seed, scale, w=W, h=H):
    """Cheap smooth noise: upsampled random grid, then blurred."""
    rng = np.random.default_rng(seed)
    g = rng.random((int(h / scale) + 3, int(w / scale) + 3)).astype(np.float32)
    im = Image.fromarray(np.uint8(g * 255)).resize((w + 3 * int(scale), h + 3 * int(scale)), Image.BICUBIC)
    a = np.asarray(im, np.float32)[:h, :w] / 255
    return gblur(a, scale * 0.35)

def save(a, out):
    """a: float luminance [0,1]. OLED black point + grain only on lit pixels."""
    a = np.clip(a, 0, 1) * 255
    a = np.clip((a - 1.5) * 255 / 253.5, 0, 255)
    n = np.random.default_rng(1).normal(0, 1.1, a.shape).astype(np.float32)
    a = np.clip(np.round(a + n * np.clip(a / 255 * 30, 0, 1)), 0, 255).astype(np.uint8)
    Image.fromarray(a, "L").convert("RGB").save(out, optimize=True)
    print(f"{os.path.basename(out)}: true-black {100 * (a == 0).mean():.0f}%")

def vignette(strength=0.9, cx=0.5, cy=0.5, rx=0.75, ry=0.8):
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    d = np.sqrt(((xx / W - cx) / rx) ** 2 + ((yy / H - cy) / ry) ** 2)
    return np.clip(1 - strength * np.clip(d - 0.35, 0, None) ** 1.4, 0, 1)


# ---------------------------------------------------------------- topo
def topo(out):
    """Contour lines of a terrain whose summit is the mark. Lines are drawn as
    a distance field (constant 1.4 px width, anti-aliased) at 2x, then
    downsampled."""
    S = 2; w, h = W * S, H * S
    size, cx, cy = 300 * S, 1720 * S, 700 * S
    m = mark_mask(size, cx, cy, w, h)
    hill = gblur(m, 90 * S) * 2.2 + gblur(m, 26 * S) * 0.9 + m * 0.25
    base = smooth_noise(7, 520 * S, w, h) * 1.3 + smooth_noise(11, 220 * S, w, h) * 0.18
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    ridge = np.exp(-(((xx - cx) / (900 * S)) ** 2 + ((yy - cy) / (700 * S)) ** 2)) * 1.2
    z = base + ridge + hill
    N = 22.0
    gy, gx = np.gradient(z)
    grad = np.sqrt(gx ** 2 + gy ** 2) + 1e-6
    f = z * N
    d = np.abs(f - np.round(f)) / (grad * N)          # distance to nearest isoline, px
    width = 0.8 * S
    line = np.clip(1 - (d - width) / (0.9 * S), 0, 1)
    major = (np.round(f).astype(np.int32) % 5 == 0)
    inten = np.where(major, 0.55, 0.2)
    a = line * inten
    # the mark itself, crisp on top
    a = np.maximum(a * (1 - gblur(m, 3 * S) * 0.95), m * 0.95)
    a = np.asarray(Image.fromarray(np.uint8(np.clip(a, 0, 1) * 255)).resize((W, H), Image.LANCZOS), np.float32) / 255
    a *= vignette(1.6, 0.66, 0.5, 0.55, 0.7)
    save(a, out)


# ---------------------------------------------------------------- flow
def flow(out):
    """Streamlines of a field that runs diagonally and bends around the mark."""
    size, cx, cy = 280, 1760, 720
    m = mark_mask(size, cx, cy)
    pot = gblur(m, 110) * 3.0 + gblur(m, 40)
    py, px = np.gradient(pot)
    nz = smooth_noise(3, 520) - 0.5
    ny, nx = np.gradient(nz)
    base = np.array([1.0, -0.28]); base /= np.linalg.norm(base)
    # velocity: base flow, deflected tangentially around the mark, gently meandering
    vx = base[0] - py * 60 - ny * 380
    vy = base[1] + px * 60 + nx * 380
    mag = np.sqrt(vx ** 2 + vy ** 2) + 1e-6
    vx /= mag; vy /= mag
    s = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H); ctx = cairo.Context(s)
    ctx.set_source_rgb(0, 0, 0); ctx.paint()
    ctx.set_line_cap(cairo.LINE_CAP_ROUND)
    rng = np.random.default_rng(5)
    bright = np.exp(-(((np.mgrid[0:H, 0:W][1] - cx) / 1300.0) ** 2 + ((np.mgrid[0:H, 0:W][0] - cy) / 800.0) ** 2))
    for k in range(1500):
        x, y = rng.uniform(-200, W), rng.uniform(0, H + 400)
        pts = []
        for _ in range(420):
            ix, iy = int(x), int(y)
            if not (0 <= ix < W and 0 <= iy < H):
                if pts: break
                x += 3 * base[0]; y += 3 * base[1]; continue
            if m[iy, ix] > 0.0 or pot[iy, ix] > 0.55: break
            pts.append((x, y))
            x += vx[iy, ix] * 3.0; y += vy[iy, ix] * 3.0
        if len(pts) < 20: continue
        b = float(bright[int(pts[len(pts) // 2][1]), int(pts[len(pts) // 2][0])])
        ctx.set_line_width(rng.uniform(0.5, 1.1))
        # fade in and out along the line
        n = len(pts)
        for i in range(0, n - 1, 6):
            t = i / n
            al = math.sin(math.pi * t) * (0.02 + 0.6 * b ** 1.5) * rng.uniform(0.6, 1.0)
            ctx.set_source_rgba(1, 1, 1, al)
            ctx.move_to(*pts[i]);
            for p in pts[i + 1:i + 7]: ctx.line_to(*p)
            ctx.stroke()
    ctx.set_source_rgba(1, 1, 1, 0.96)
    for x, y, rw, rh in mark_rects(size, cx - size / 2, cy - size / 2):
        ctx.rectangle(x, y, rw, rh)
    ctx.fill()
    a = np.ndarray((H, s.get_stride() // 4, 4), np.uint8, s.get_data())[:, :W, 1].astype(np.float32) / 255
    save(a, out)


# ---------------------------------------------------------------- halftone
def halftone(out):
    """A dot matrix whose dot sizes sample a soft glow around the mark; the
    mark itself is the densest region. Pure Nothing-OS geometry."""
    size, cx, cy = 384, 1280, 700
    m = mark_mask(size, cx, cy)
    field = gblur(m, 6) * 0.85 + gblur(m, 70) * 0.9 + gblur(m, 300) * 1.6
    field /= field.max()
    s = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H); ctx = cairo.Context(s)
    ctx.set_source_rgb(0, 0, 0); ctx.paint()
    pitch = 12
    for y in range(pitch // 2, H, pitch):
        for x in range(pitch // 2, W, pitch):
            v = float(field[y, x])
            if v < 0.02: continue
            r = min(pitch * 0.48, 0.6 + v ** 0.8 * pitch * 0.5)
            ctx.set_source_rgba(1, 1, 1, min(1.0, 0.25 + v * 1.1))
            ctx.arc(x, y, r, 0, 2 * math.pi); ctx.fill()
    a = np.ndarray((H, s.get_stride() // 4, 4), np.uint8, s.get_data())[:, :W, 1].astype(np.float32) / 255
    save(a, out)


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "."
    os.makedirs(out, exist_ok=True)
    which = sys.argv[2:] or ["topo", "flow", "halftone"]
    for n in which:
        globals()[n](os.path.join(out, f"maze-{n}.png"))
