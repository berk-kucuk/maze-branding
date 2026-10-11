#!/usr/bin/env python3
"""Maze Linux — OLED static wallpapers, procedural (no Blender needed).

    python3 oled.py <out-dir> [--scale 0.5] [name ...]

Designs: prism, flow, trace, field, signal, dawn — shipped as Maze-Prism,
Maze-Flow, … in maze-branding (2560x1440).

The Maze mark is rebuilt as vector geometry from ../blender/mark.json (15x15
wall grid + the real, uneven column edges), so it is razor sharp at any size
and every effect below is driven by its exact signed distance field.

OLED rules for every design:
  * the background is 0,0,0 — not "near black";
  * all lighting runs in float32 and is quantised once, at the end;
  * grain is added only where the image is lit, so black stays black.
"""
import json, math, os, sys
import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from fblur import gblur  # noqa: E402

BRANDING = os.path.normpath(os.path.join(HERE, "../../../maze-branding"))
LOGO = os.path.join(BRANDING, "usr/share/pixmaps/maze-logo.png")

W0, H0 = 2560, 1440
W, H, K = W0, H0, 1.0           # K: px scale relative to 2560x1440

_M = json.load(open(os.path.join(HERE, "../blender/mark.json")))
GRID = np.array(_M["grid"], bool)
EDGE = np.array(_M["edges"], np.float32)
E0, E1 = float(EDGE[0]), float(EDGE[-1])
MC, MS = (E0 + E1) / 2, (E1 - E0)          # mark centre / size in mark units


# ------------------------------------------------------------------ geometry
def _rects(val):
    """Cells equal to val merged into rectangles (mark units)."""
    n = GRID.shape[0]
    runs = []
    for r in range(n):
        c = 0
        while c < n:
            if GRID[r, c] == val:
                c0 = c
                while c < n and GRID[r, c] == val: c += 1
                runs.append([r, r + 1, c0, c])
            else:
                c += 1
    merged = []
    for run in runs:                          # stack identical vertical runs
        for m in merged:
            if m[1] == run[0] and m[2] == run[2] and m[3] == run[3]:
                m[1] = run[1]; break
        else:
            merged.append(run)
    return [(EDGE[c0], EDGE[r0], EDGE[c1], EDGE[r1]) for r0, r1, c0, c1 in merged]

WALLS, HOLES = _rects(True), _rects(False)


def frame(cx, cy, size, rot=0.0):
    """Pixel grid -> mark-unit coords (u, v) and the px-per-unit factor."""
    y, x = np.mgrid[0:H, 0:W].astype(np.float32)
    x, y = x - cx, y - cy
    if rot:
        c, s = math.cos(rot), math.sin(rot)
        x, y = c * x + s * y, -s * x + c * y
    k = MS / size
    return x * k + MC, y * k + MC, 1.0 / k


def _rect_dist(u, v, r):
    x0, y0, x1, y1 = r
    dx = np.maximum(np.maximum(x0 - u, u - x1), 0)
    dy = np.maximum(np.maximum(y0 - v, v - y1), 0)
    return np.sqrt(dx * dx + dy * dy)


def mark_sdf(cx, cy, size, rot=0.0):
    """Exact signed distance to the mark in px (<0 inside the walls)."""
    u, v, ppu = frame(cx, cy, size, rot)
    return sdf_uv(u, v) * ppu


def sdf_uv(u, v):
    """Signed distance to the mark at mark-unit coords (any array shape)."""
    dout = np.full(u.shape, 1e9, np.float32)
    for r in WALLS: dout = np.minimum(dout, _rect_dist(u, v, r))
    din = np.minimum(np.minimum(u - E0, E1 - u), np.minimum(v - E0, E1 - v))
    din = np.maximum(din, 0)
    for r in HOLES: din = np.minimum(din, _rect_dist(u, v, r))
    return np.where(dout > 0, dout, -din)


def box_sdf(cx, cy, half, rot=0.0, rad=0.0):
    y, x = np.mgrid[0:H, 0:W].astype(np.float32)
    x, y = x - cx, y - cy
    if rot:
        c, s = math.cos(rot), math.sin(rot)
        x, y = c * x + s * y, -s * x + c * y
    qx, qy = np.abs(x) - half + rad, np.abs(y) - half + rad
    out = np.sqrt(np.maximum(qx, 0) ** 2 + np.maximum(qy, 0) ** 2)
    return out + np.minimum(np.maximum(qx, qy), 0) - rad


def cover(d, aa=0.75):
    """Anti-aliased coverage of an sdf (inside < 0)."""
    return np.clip(0.5 - d / (2 * aa), 0, 1)


def ss(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


# ------------------------------------------------------------------ finishing
def logo_layer(width, cx, cy, opacity=1.0):
    lg = Image.open(LOGO).convert("RGBA")
    width = int(width * K)
    lh = int(lg.height * width / lg.width)
    a = np.asarray(lg.resize((width, lh), Image.LANCZOS), np.float32) / 255
    return a, int(cx - width / 2), int(cy - lh / 2), opacity


def paste(rgb, layer):
    a, x0, y0, op = layer
    h, w = a.shape[:2]
    al = a[..., 3:4] * op
    rgb[y0:y0 + h, x0:x0 + w] = rgb[y0:y0 + h, x0:x0 + w] * (1 - al) + a[..., :3] * al
    return rgb


def bloom(img, amount=1.0, thr=0.2, sigmas=((4, 0.5), (16, 0.35), (60, 0.25))):
    lum = img.max(axis=2)
    hi = np.clip(lum - thr, 0, None) / (1 - thr)
    hi = img * (hi / np.maximum(lum, 1e-4))[..., None]
    return sum(gblur(hi, s * K) * k for s, k in sigmas) * amount


def tonemap(rgb):
    """Soft shoulder: keeps highlights from clipping to flat white."""
    return rgb / (1 + np.maximum(rgb - 0.8, 0) * 1.2)


def finish(rgb, name, out, grain=1.3):
    rgb = np.clip(rgb, 0, 1)
    a = rgb * 255
    n = np.random.default_rng(7).normal(0, grain, (H, W, 1)).astype(np.float32)
    lum = a.mean(axis=2, keepdims=True) / 255
    a = a + n * np.clip(lum * 30, 0, 1)
    a = np.clip(np.round(a), 0, 255).astype(np.uint8)
    path = os.path.join(out, f"{name}.png")
    Image.fromarray(a, "RGB").save(path, optimize=True)
    blk = (a.max(axis=2) == 0).mean() * 100
    print(f"wrote {path}  {W}x{H}  true-black {blk:.0f}%")


def rgb(*c): return np.array(c, np.float32)


# ================================================================== designs
def wl_rgb(t):
    """t in 0..1 across the visible spectrum (red..violet) -> linear RGB."""
    h = t * 0.76 * 6
    c = np.clip([abs(h - 3) - 1, 2 - abs(h - 2), 2 - abs(h - 4)], 0, 1)
    return (np.asarray(c, np.float32) ** 1.4)


def seg_dist(xx, yy, p0, p1):
    px, py = xx - p0[0], yy - p0[1]
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    L2 = dx * dx + dy * dy
    t = np.clip((px * dx + py * dy) / L2, 0, 1)
    return np.hypot(px - t * dx, py - t * dy), t


def d_prism(out):
    """A single white beam enters the glass mark and leaves as a spectrum."""
    S = 0.30 * H
    cx, cy = W * 0.44, H * 0.48
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    d = mark_sdf(cx, cy, S)
    # glass body: bright hairline edges, faint body
    edge = np.exp(-(d / (0.9 * K)) ** 2)
    body = cover(d) * 0.05
    entry = (cx - S / 2, cy + 0.04 * S)
    exitp = (cx + S / 2, cy - 0.02 * S)
    img = np.zeros((H, W, 3), np.float32)
    dist, t = seg_dist(xx, yy, (-0.05 * W, cy + 0.38 * S), entry)
    img += (np.exp(-(dist / (1.4 * K)) ** 2) * 1.6 + np.exp(-dist / (9 * K)) * 0.22)[..., None] * rgb(1, 1, 1) \
        * (0.35 + 0.65 * t)[..., None]
    # internal path through the glass
    dist, _ = seg_dist(xx, yy, entry, exitp)
    img += (np.exp(-(dist / (2.5 * K)) ** 2) * 0.6 * cover(d))[..., None] * rgb(1, 1, 1)
    # dispersed fan
    N = 64
    ax, ay = xx - exitp[0], yy - exitp[1]
    rr = np.hypot(ax, ay)
    th = np.arctan2(ay, ax)
    spec = np.zeros_like(img)
    for i in range(N):
        tt = i / (N - 1)
        a0 = math.radians(-2.0 + 13.0 * tt)
        w = math.radians(0.11) + rr * 0
        g = np.exp(-((th - a0) / (math.radians(0.16) + 2.2 * K / np.maximum(rr, 1))) ** 2)
        spec += g[..., None] * wl_rgb(tt)
    spec *= (ax > 0)[..., None] * (1 / N * 7) * (np.exp(-rr / (0.45 * W)) * ss(0, 40 * K, rr))[..., None]
    img += spec * (1 - cover(d))[..., None]
    img += (edge * 0.55 + body)[..., None] * rgb(0.92, 0.95, 1)
    # flare where the light leaves the glass
    re = np.hypot(xx - exitp[0], yy - exitp[1])
    img += (np.exp(-(re / (5 * K)) ** 2) * 1.2 + np.exp(-re / (40 * K)) * 0.12)[..., None] * rgb(1, 0.98, 0.95)
    img += bloom(img, 0.4, 0.35)
    img = tonemap(img)
    img = paste(img, logo_layer(200, W - 210 * K, H - 105 * K, 0.7))
    finish(img, "maze-prism", out)


def d_flow(out):
    """Laminar streamlines parting around the mark like air around a body."""
    S = 0.26 * H
    cx, cy = W * 0.5, H * 0.5
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    R = S * 0.62
    db = box_sdf(cx, cy, S / 2 + 0.07 * S, rad=0.25 * S)
    r = R + np.maximum(db, 0)
    psi = (yy - cy) * (1 - (R / r) ** 2)
    gy, gx = np.gradient(psi)
    gm = np.hypot(gx, gy) + 1e-6
    sp = 22.0 * K
    f = psi / sp
    fr = np.abs(f - np.round(f)) * sp / gm
    idx = np.round(f).astype(int)
    lw = 0.55 * K
    line = np.clip(1 - fr / (lw + 0.6 * K), 0, 1) ** 1.5
    major = (idx % 6 == 0)
    inten = np.where(major, 0.5, 0.17)
    fade = np.exp(-((yy - cy) / (0.62 * H)) ** 4) * (0.35 + 0.65 * np.exp(-((xx - cx) / (0.55 * W)) ** 2))
    line = line * inten * fade * (db > 0.004 * S)
    img = line[..., None] * rgb(0.82, 0.86, 0.95)
    # one accent filament just above the body
    acc = (idx == -3) & ~major
    img += (np.clip(1 - fr / (1.1 * K), 0, 1) * acc * fade)[..., None] * rgb(0.35, 0.6, 1.0) * 0.9
    d = mark_sdf(cx, cy, S)
    img = img * (1 - cover(d))[..., None] + cover(d)[..., None] * rgb(0.95, 0.96, 1.0)
    img += bloom(img, 0.3, 0.5)
    img = tonemap(img)
    img = paste(img, logo_layer(190, W / 2, H * 0.90, 0.6))
    finish(img, "maze-flow", out)


def iso_lines(f, gm, lw=0.55, minsp=3.0, step=1.0):
    """Anti-aliased iso-lines of f at every integer; gm = |grad f| (per px).
    Lines whose on-screen spacing drops under minsp px fade out instead of
    turning into moire."""
    fr = np.abs(f - np.round(f)) / gm
    line = np.clip(1 - fr / (lw * K + 0.6 * K), 0, 1) ** 1.5
    spacing = step / gm
    return line * ss(minsp * K * 0.6, minsp * K * 1.6, spacing), np.round(f).astype(int)


def cell_c(i): return float(EDGE[i] + EDGE[i + 1]) / 2


def solve_mark(start, goal):
    from collections import deque
    n = GRID.shape[0]
    prev = {start: None}; q = deque([start])
    while q:
        r, c = q.popleft()
        if (r, c) == goal: break
        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nr, nc = r + dr, c + dc
            if 0 <= nr < n and 0 <= nc < n and not GRID[nr, nc] and (nr, nc) not in prev:
                prev[(nr, nc)] = (r, c); q.append((nr, nc))
    path, p = [], goal
    while p is not None: path.append(p); p = prev[p]
    path = path[::-1]
    pts = [path[0]]                               # keep corners only
    for i in range(1, len(path) - 1):
        a, b, c = path[i - 1], path[i], path[i + 1]
        if (b[0] - a[0], b[1] - a[1]) != (c[0] - b[0], c[1] - b[1]): pts.append(b)
    pts.append(path[-1])
    return [(cell_c(c), cell_c(r)) for r, c in pts]


def d_trace(out):
    """One ray of light runs the longest corridor of the mark; the
    walls it passes are lit by it, the rest of the maze stays a hairline."""
    S = 0.46 * H
    cx, cy = W * 0.5, H * 0.47
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    d = mark_sdf(cx, cy, S)
    pts = solve_mark((1, 10), (6, 3))      # the longest corridor run
    P = [(cx + (u - MC) / MS * S, cy + (v - MC) / MS * S) for u, v in pts]
    seglen = [math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(P, P[1:])]
    total = sum(seglen)
    dp = np.full((H, W), 1e9, np.float32)
    prog = np.zeros((H, W), np.float32)
    acc = 0.0
    for (a, b), L in zip(zip(P, P[1:]), seglen):
        dd, t = seg_dist(xx, yy, a, b)
        m = dd < dp
        dp = np.where(m, dd, dp)
        prog = np.where(m, (acc + t * L) / total, prog)
        acc += L
    grow = 0.25 + 0.75 * prog ** 1.6
    beam = (np.exp(-(dp / (1.1 * K)) ** 2) * 1.5 + np.exp(-dp / (7 * K)) * 0.28) * grow
    tint = rgb(0.80, 0.92, 1.0)
    img = beam[..., None] * tint
    # walls: hairline, lit by the nearby beam
    near = np.exp(-dp / (0.13 * S))
    edge = np.exp(-(d / (0.9 * K)) ** 2)
    img += (edge * (0.16 + 1.0 * near * grow) + cover(d) * 0.018)[..., None] * rgb(0.88, 0.92, 1.0)
    # the head of the ray
    hx, hy = P[-1]
    rh = np.hypot(xx - hx, yy - hy)
    img += (np.exp(-(rh / (3.0 * K)) ** 2) * 2.0 + np.exp(-rh / (18 * K)) * 0.25)[..., None] * rgb(1, 1, 1)
    # the spark where it starts
    sx, sy = P[0]
    rs = np.hypot(xx - sx, yy - sy)
    img += (np.exp(-(rs / (2.0 * K)) ** 2) * 0.6)[..., None] * tint
    img += bloom(img, 0.45, 0.35)
    img = tonemap(img)
    img = paste(img, logo_layer(190, W / 2, H * 0.89, 0.65))
    finish(img, "maze-trace", out)


def d_field(out):
    """The mark as a magnet: dipole field lines leave its top, loop wide
    around it and return to its base."""
    S = 0.20 * H
    cx, cy = W * 0.5, H * 0.5
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    x, y = xx - cx, (yy - cy) * 1.0
    r = np.sqrt(x * x + y * y) + 1e-3
    psi = (x * x) / r ** 3 * S                     # r = L sin^2(theta)
    f = np.log(psi + 1e-9) / 0.115
    gy, gx = np.gradient(f)
    gm = np.hypot(gx, gy) + 1e-6
    line, idx = iso_lines(f, gm, minsp=7.0)
    line *= ss(0.05 * S, 0.45 * S, np.abs(x))         # no bundle on the axis
    major = (idx % 5 == 0)
    inten = np.where(major, 0.55, 0.2)
    keep = ss(0.0, 0.08 * S, box_sdf(cx, cy, S * 0.62, rad=0.1 * S))
    fade = np.exp(-(r / (0.62 * W)) ** 2)
    img = (line * inten * keep * fade)[..., None] * rgb(0.82, 0.87, 0.97)
    # one accent field line, either side
    acc = (idx == 5) & ~major
    img += (line * acc * keep * fade * 0.9)[..., None] * rgb(0.35, 0.62, 1.0)
    d = mark_sdf(cx, cy, S)
    img = img * (1 - cover(d))[..., None] + cover(d)[..., None] * rgb(0.95, 0.96, 1.0)
    img += bloom(img, 0.3, 0.5)
    img = tonemap(img)
    img = paste(img, logo_layer(190, W / 2, H * 0.91, 0.6))
    finish(img, "maze-field", out)


def d_signal(out):
    """A stack of signal lines; where they cross the mark they rise into it —
    the mark read like a waveform (hidden-line, back to front)."""
    SSf = 2
    N = 92
    Wc = W * SSf
    xs = np.linspace(0, W, Wc // 2).astype(np.float32)
    y0, y1 = 0.24 * H, 0.86 * H
    Sx = 0.40 * H                                  # mark width on the plane
    rng = np.random.default_rng(5)
    rows = np.linspace(0, 1, N)
    # plane rows covered by the mark
    r0, r1 = 0.24, 0.76
    amp = 0.045 * H
    im = Image.new("L", (Wc, H * SSf), 0)
    dr = ImageDraw.Draw(im)
    nz_x = np.linspace(0, 1, 400)
    for i in range(N):
        t = rows[i]
        ys = y0 + (y1 - y0) * (t ** 1.18)
        v = (t - r0) / (r1 - r0) * MS + E0
        u = (xs - W / 2) / Sx * MS + MC
        dd = sdf_uv(u, np.full_like(u, v)) * (Sx / MS)
        bev = 0.012 * Sx
        hgt = ss(-bev, bev, -dd)
        hill = np.exp(-((xs - W / 2) / (0.42 * W)) ** 2) * np.exp(-((t - 0.5) / 0.32) ** 2)
        wig = np.interp(xs / W, nz_x, np.convolve(rng.normal(0, 1, 400), np.ones(9) / 9, "same"))
        h = hgt * amp + hill * 0.010 * H + wig * 0.0010 * H * (0.3 + hill)
        py = (ys - h) * SSf
        px = xs * SSf
        poly = list(zip(px, py)) + [(Wc, H * SSf), (0, H * SSf)]
        dr.polygon(poly, fill=0)
        bright = int(255 * (0.04 + 0.96 * t ** 1.1))
        dr.line(list(zip(px, py)), fill=bright, width=max(1, int(1.1 * K * SSf)))
    a = np.asarray(im.resize((W, H), Image.LANCZOS), np.float32) / 255
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    fade = ss(0.0, 0.22 * W, xx) * ss(0.0, 0.22 * W, W - xx)
    a *= 0.75 * fade
    img = a[..., None] * rgb(0.84, 0.88, 0.97)
    img += bloom(img, 0.25, 0.4)
    img = tonemap(img)
    img = paste(img, logo_layer(190, W / 2, H * 0.12, 0.65))
    finish(img, "maze-signal", out)


def d_dawn(out):
    """Orbital sunrise: the limb of a dark world, a thin lit atmosphere and
    the sun about to clear the horizon."""
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    R = 2.2 * W
    pcx, pcy = W * 0.5, 0.70 * H + R
    r = np.hypot(xx - pcx, yy - pcy)
    d = r - R                                    # >0: sky, <0: planet
    ang = np.arctan2(xx - pcx, -(yy - pcy))      # 0 at the top of the limb
    sun = np.exp(-(ang / 0.075) ** 2)            # light concentrated at top
    sunw = np.exp(-(ang / 0.22) ** 2)
    up = np.maximum(d, 0)
    atm = (np.exp(-up / (2.0 * K)) * (0.35 + 1.4 * sun)
           + np.exp(-up / (14 * K)) * (0.10 + 0.6 * sunw)
           + np.exp(-up / (70 * K)) * (0.02 + 0.22 * sunw)
           + np.exp(-up / (260 * K)) * 0.06 * sunw) * (d > 0)
    hot = np.exp(-up / (14 * K))
    col = (rgb(0.98, 0.97, 1.0) * hot[..., None]
           + rgb(0.22, 0.45, 1.0) * (1 - hot)[..., None])
    img = atm[..., None] * col
    # night side: a thin scattered rim just inside the limb, then black
    dn = np.maximum(-d, 0)
    img += ((np.exp(-dn / (1.2 * K)) * (0.25 + 0.9 * sun) + np.exp(-dn / (10 * K)) * 0.10 * sunw) * (d <= 0))[..., None] * rgb(0.55, 0.7, 1.0)
    # the sun, just under the horizon: a hot bead + anamorphic streak
    sx, sy = W * 0.5, 0.70 * H - 1.5 * K
    rs = np.hypot(xx - sx, yy - sy)
    img += (np.exp(-(rs / (4 * K)) ** 2) * 2.4 + np.exp(-rs / (40 * K)) * 0.35)[..., None] * rgb(1, 0.96, 0.9)
    img += (np.exp(-((yy - sy) / (1.0 * K)) ** 2) * np.exp(-np.abs(xx - sx) / (0.16 * W)) * 0.35)[..., None] * rgb(0.7, 0.82, 1.0)
    # a few faint stars, kept clear of the glow
    rng = np.random.default_rng(21)
    st = np.zeros((H, W), np.float32)
    n = int(260 * K * K)
    ix = (rng.random(n) * W).astype(int); iy = (rng.random(n) * H * 0.62).astype(int)
    np.add.at(st, (iy, ix), rng.pareto(2.5, n) * 0.25 + 0.15)
    img += (gblur(st, 0.6 * K) * 4 * (1 - sunw * np.exp(-up / (300 * K))) * (d > 0))[..., None] * rgb(0.85, 0.9, 1)
    img += bloom(img, 0.35, 0.4)
    img = tonemap(img)
    img = paste(img, logo_layer(260, W / 2, H * 0.40, 0.92))
    finish(img, "maze-dawn", out)


DESIGNS = {
    "prism": d_prism, "flow": d_flow, "trace": d_trace,
    "field": d_field, "signal": d_signal, "dawn": d_dawn,
}

if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        sys.exit(__doc__)
    out = args.pop(0)
    if args[:1] == ["--scale"]:
        K = float(args[1]); args = args[2:]
        W, H = int(W0 * K), int(H0 * K)
    os.makedirs(out, exist_ok=True)
    for name in (args or DESIGNS):
        DESIGNS[name](out)
