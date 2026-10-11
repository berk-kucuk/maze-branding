#!/usr/bin/env python3
"""Maze Linux — live wallpaper candidates (Maze Wallpaper / com.mazelinux.wallpaper).

    python3 live2d.py <out-dir> [name ...] [--preview]

Every design is a pure function of t in [0, 1): frame(0) == frame(1), so the
still shown for review and the seamless video loop come from the same code.
All motion uses integer cycles per loop for that reason.

pulse     the mark sends square ripples outward, like a heartbeat
rain      LED-panel digital rain; the mark is lit cells inside the stream
orbit     tilted orbits with comets passing behind and in front of the mark
scan      halftone dot field; a light bar sweeps across and reveals the mark
depth     endless zoom through nested mark outlines
wave      mirrored audio bars, the mark sitting in the quiet centre
dust      the mark made of particles, its right edge drifting away as dust
neon      the mark as a glowing tube sign, reflected on a black floor
stars     the mark as a constellation in a night sky
caustics  water light dancing on the floor, brightest inside the mark
weave     Truchet tiles turning in a wave that starts at the mark
radar     a radar sweep lights up a maze around the mark
"""
import math, os, sys
import numpy as np
import cairo
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "blender"))
from lines2d import mark_rects, gblur, smooth_noise, GRID

PREVIEW = "--preview" in sys.argv
W, H = (1280, 720) if PREVIEW else tuple(int(v) for v in os.environ.get("MAZE_LIVE_SIZE", "2560x1440").split("x"))
K = W / 2560
SANS, MONO = "Inter", "Hack"
TAU = 2 * math.pi
WHITE = (1.0, 1.0, 1.0)


# ------------------------------------------------------------------ helpers
def layer(draw, w=None, h=None):
    """Run draw(ctx) on an A8 surface; ink with set_source_rgba(0,0,0,alpha)."""
    w = w or W; h = h or H
    s = cairo.ImageSurface(cairo.FORMAT_A8, w, h); c = cairo.Context(s)
    c.set_source_rgba(0, 0, 0, 1)
    draw(c)
    s.flush()
    return np.ndarray((h, s.get_stride()), np.uint8, s.get_data())[:, :w].astype(np.float32) / 255

def mark_path(c, size, cx, cy, rot=0.0):
    c.save(); c.translate(cx, cy); c.rotate(rot)
    for x, y, rw, rh in mark_rects(size, -size / 2, -size / 2):
        c.rectangle(x, y, rw, rh)
    c.restore()

def markm(size, cx, cy, rot=0.0, w=None, h=None):
    return layer(lambda c: (mark_path(c, size, cx, cy, rot), c.fill()), w, h)

def tube(m, sigma, width=0.22):
    """A line of even width along the edge of a mask."""
    b = gblur(m, max(0.8, sigma))
    return np.exp(-((b - 0.5) / width) ** 2) * (b > 0.02)

def rrect(c, x, y, w, h, r):
    c.new_sub_path()
    c.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    c.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    c.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    c.arc(x + r, y + r, r, math.pi, 1.5 * math.pi)
    c.close_path()

def wordmark(c, x, y, size, alpha=0.85, spacing=0.55, anchor="center",
             weight=cairo.FONT_WEIGHT_BOLD, text="MAZE LINUX", font=SANS):
    c.select_font_face(font, cairo.FONT_SLANT_NORMAL, weight); c.set_font_size(size)
    adv = [c.text_extents(ch).x_advance for ch in text]
    tw = sum(adv) + spacing * size * (len(text) - 1)
    x0 = x - tw / 2 if anchor == "center" else (x - tw if anchor == "right" else x)
    c.set_source_rgba(0, 0, 0, alpha)
    for ch, a in zip(text, adv):
        c.move_to(x0, y); c.show_text(ch); x0 += a + spacing * size
    return tw

def add(img, m, col=WHITE, k=1.0):
    img += m[..., None] * (np.asarray(col, np.float32) * k)

def bloom(img, sigma, k):
    for ch in range(3):
        img[..., ch] += gblur(img[..., ch], sigma) * k

def brand(img, x=None, y=None, size=20, alpha=0.8, plate=False, **kw):
    """The 'MAZE LINUX' wordmark; plate darkens what is behind it first."""
    x = W / 2 if x is None else x
    y = H - 96 * K if y is None else y
    wm = layer(lambda c: wordmark(c, x, y, size * K, alpha, **kw))
    if plate:
        p = gblur(np.clip(gblur(wm, 10 * K) * 40, 0, 1), 14 * K)
        img *= (1 - p[..., None] * 0.92)
    add(img, wm)

def vignette(cx=0.5, cy=0.5, rx=0.6, ry=0.7, strength=1.4):
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    d = np.sqrt(((xx / W - cx) / rx) ** 2 + ((yy / H - cy) / ry) ** 2)
    return np.clip(1 - strength * np.clip(d - 0.35, 0, None) ** 1.4, 0, 1)

def smoothstep(a, b, x):
    x = np.clip((x - a) / (b - a), 0, 1)
    return x * x * (3 - 2 * x)

def finish(img, seed=1):
    """float RGB -> uint8, with an OLED black point and grain only in the light."""
    a = np.clip(img, 0, 1) * 255
    a = np.clip((a - 1.5) * 255 / 253.5, 0, 255)
    lum = a.mean(2, keepdims=True)
    n = np.random.default_rng(seed).normal(0, 1.0, a.shape[:2]).astype(np.float32)[..., None]
    a = np.clip(np.round(a + n * np.clip(lum / 255 * 30, 0, 1)), 0, 255).astype(np.uint8)
    return Image.fromarray(a, "RGB")


# ------------------------------------------------------------------ 1 pulse
def pulse(t):
    img = np.zeros((H, W, 3), np.float32)
    cx, cy, ms = W / 2, H / 2 - 30 * K, 260 * K
    r0, D = ms * 0.64, 86 * K

    def rings(c):
        c.set_line_width(1.6 * K)
        for k in range(40):
            u = k + t; r = r0 + D * u
            if r > W: break
            a = min(1.0, u) * 0.6 * math.exp(-(r - r0) / (560 * K))
            c.set_source_rgba(0, 0, 0, a)
            rrect(c, cx - r, cy - r, 2 * r, 2 * r, r * 0.14); c.stroke()
    m = layer(rings)
    add(img, m); add(img, gblur(m, 7 * K), k=0.9)
    mk = markm(ms, cx, cy)
    beat = 0.5 + 0.5 * math.cos(TAU * t)
    add(img, mk, k=0.96)
    add(img, gblur(mk, 50 * K), k=0.28 + 0.14 * beat); add(img, gblur(mk, 180 * K), k=0.22 + 0.14 * beat)
    brand(img, y=cy + ms / 2 + 120 * K, size=22, plate=True)
    return img


# ------------------------------------------------------------------ 2 rain
def rain(t):
    cell = max(4, int(round(22 * K)))
    cols, rows = W // cell + 1, H // cell + 1
    rng = np.random.default_rng(3)
    v = rng.integers(1, 4, cols); p = rng.random(cols)
    L = rng.integers(8, 34, cols).astype(np.float32); P = rows + 40
    r = np.arange(rows)[:, None]
    head = ((p + v * t) % 1) * P
    d = head[None, :] - r
    tr = np.where((d >= 0) & (d < L[None, :]), np.clip(1 - d / L[None, :], 0, 1) ** 1.6, 0).astype(np.float32)
    hd = ((d >= 0) & (d < 1)).astype(np.float32)
    msz = 36 * cell
    mk = markm(msz, (cols // 2) * cell, (rows // 2) * cell, w=cols * cell, h=rows * cell)
    mc = mk[cell // 2::cell, cell // 2::cell][:rows, :cols] > 0.5
    val = 0.03 + tr * 0.5 + hd * 0.45
    val = np.where(mc, 0.62 + tr * 0.38, val)
    g = max(1, int(round(4 * K)))
    sprite = np.zeros((cell, cell), np.float32); sprite[g:cell - g, g:cell - g] = 1
    lum = np.kron(val, sprite)[:H, :W]
    img = np.zeros((H, W, 3), np.float32)
    add(img, lum)
    bloom(img, 10 * K, 0.5); bloom(img, 60 * K, 0.25)
    brand(img, size=20, plate=True)
    return img


# ------------------------------------------------------------------ 3 orbit
def orbit(t):
    cx, cy, ms = W / 2, H / 2 - 20 * K, 230 * K
    rings = [(430, 0.30, -16, 3, 1), (580, 0.25, 11, 4, 1), (760, 0.21, -27, 2, -1),
             (960, 0.31, 21, 5, 1), (1200, 0.19, -7, 3, -1)]
    rng = np.random.default_rng(5)

    def pt(a, e, rot, ph):
        x, y = a * math.cos(ph), a * e * math.sin(ph)
        cr, sr = math.cos(rot), math.sin(rot)
        return cx + x * cr - y * sr, cy + x * sr + y * cr

    def draw(front):
        def f(c):
            c.set_line_cap(cairo.LINE_CAP_ROUND)
            for a, e, rd, n, m in rings:
                a *= K; rot = math.radians(rd)
                c.set_line_width(1.3 * K); c.set_source_rgba(0, 0, 0, 0.2 if front else 0.12)
                on = False
                for i in range(721):
                    ph = i / 720 * TAU
                    if (math.sin(ph) > 0) == front:
                        x, y = pt(a, e, rot, ph)
                        c.line_to(x, y) if on else c.move_to(x, y); on = True
                    elif on:
                        c.stroke(); on = False
                if on: c.stroke()
                ph0 = rng.random(n) * TAU
                for j in range(n):
                    head = ph0[j] + TAU * m * t
                    for s in range(48):
                        ph = head - m * s * 0.011
                        if (math.sin(ph) > 0) != front: continue
                        x, y = pt(a, e, rot, ph)
                        al = (1 - s / 48) ** 2 * (1.0 if front else 0.45)
                        c.set_source_rgba(0, 0, 0, al)
                        c.arc(x, y, 2.6 * K * (1 - s / 70), 0, TAU); c.fill()
        return f

    rng = np.random.default_rng(5); back = layer(draw(False))
    rng = np.random.default_rng(5); front = layer(draw(True))
    plate = gblur(layer(lambda c: (rrect(c, cx - ms * 0.62, cy - ms * 0.62, ms * 1.24, ms * 1.24, 20 * K), c.fill())), 18 * K)
    img = np.zeros((H, W, 3), np.float32)
    add(img, back * (1 - plate)); add(img, gblur(back, 5 * K) * (1 - plate), k=0.8)
    mk = markm(ms, cx, cy)
    add(img, mk, k=0.95); add(img, gblur(mk, 60 * K), k=0.3); add(img, gblur(mk, 220 * K), k=0.25)
    add(img, front); add(img, gblur(front, 6 * K), k=1.2)
    brand(img, size=20, plate=True)
    return img


# ------------------------------------------------------------------ 4 scan
def scan(t):
    sp = 18 * K
    xs = np.arange(sp / 2, W, sp); ys = np.arange(sp / 2, H, sp)
    X, Y = np.meshgrid(xs, ys)
    mk = gblur(markm(560 * K, W / 2, H / 2 - 20 * K), 5 * K)
    ghost = mk[np.clip(Y.astype(int), 0, H - 1), np.clip(X.astype(int), 0, W - 1)]
    xb = -300 * K + t * (W + 2600 * K)
    g = np.exp(-((X - xb) / (110 * K)) ** 2)
    trail = np.where(X < xb, np.exp(-(xb - X) / (520 * K)), 0)
    I = np.clip(0.05 + 0.12 * ghost + (g + 0.55 * trail) * (0.2 + 0.8 * ghost), 0, 1)

    def dots(c):
        for x, y, i in zip(X.ravel(), Y.ravel(), I.ravel()):
            c.set_source_rgba(0, 0, 0, 0.45 + 0.55 * i)
            c.arc(x, y, sp * 0.46 * math.sqrt(i), 0, TAU); c.fill()
    img = np.zeros((H, W, 3), np.float32)
    add(img, layer(dots))
    beam = layer(lambda c: (c.set_source_rgba(0, 0, 0, 0.7), c.rectangle(xb - 1 * K, 0, 2 * K, H), c.fill()))
    add(img, beam); add(img, gblur(beam, 30 * K), k=1.5); add(img, gblur(beam, 140 * K), k=1.0)
    bloom(img, 8 * K, 0.35)
    brand(img, size=20, plate=True)
    return img


# ------------------------------------------------------------------ 5 depth
def depth(t):
    cx, cy = W / 2, H / 2
    q, smin = 1.6, 26 * K
    N = int(math.ceil(math.log(W * 2.4 / smin) / math.log(q)))
    img = np.zeros((H, W, 3), np.float32)
    for k in range(N):
        s = smin * q ** (k + t)
        u = math.log(s / smin) / math.log(q ** N)
        a = math.sin(math.pi * u ** 0.8) ** 2.2
        if a < 0.01: continue
        m = markm(s, cx, cy, (k + t) * math.radians(4))
        add(img, tube(m, s * 0.0016 + 0.7 * K, 0.2), k=a * 0.6)
        add(img, m, k=a * 0.02)
    c0 = np.zeros((H, W), np.float32); c0[int(cy), int(cx)] = 1
    bloom(img, 6 * K, 0.4)
    add(img, gblur(c0, 160 * K) / gblur(c0, 160 * K).max(), k=0.12)
    brand(img, size=20, plate=True)
    return img


# ------------------------------------------------------------------ 6 wave
def wave(t):
    cx, cy, ms = W / 2, H / 2 - 30 * K, 220 * K
    nb, gap = 168, 250 * K
    rng = np.random.default_rng(9)
    ph = rng.random((4,)) * TAU; jm = rng.integers(1, 4, nb); jp = rng.random(nb) * TAU

    def bars(c):
        for i in range(nb):
            x = (i + 0.5) * W / nb; dx = abs(x - cx)
            env = float(smoothstep(gap, gap + 220 * K, dx)) * math.exp(-((dx - gap) / (1100 * K)) ** 2)
            if env < 0.01: continue
            s = (0.5 + 0.5 * (0.45 * math.sin(TAU * (3 * x / W + t) + ph[0])
                              + 0.3 * math.sin(TAU * (7 * x / W - 2 * t) + ph[1])
                              + 0.25 * math.sin(TAU * (13 * x / W + 3 * t) + ph[2])))
            s = 0.75 * s + 0.25 * (0.5 + 0.5 * math.sin(TAU * jm[i] * t + jp[i]))
            h = env * (0.12 + 0.88 * s) * 360 * K + 3 * K
            bw = W / nb * 0.38
            gr = cairo.LinearGradient(0, cy - h, 0, cy + h)
            gr.add_color_stop_rgba(0, 0, 0, 0, 0.25); gr.add_color_stop_rgba(0.5, 0, 0, 0, 0.95)
            gr.add_color_stop_rgba(1, 0, 0, 0, 0.25)
            c.set_source(gr); rrect(c, x - bw / 2, cy - h, bw, 2 * h, bw / 2); c.fill()
    m = layer(bars)
    img = np.zeros((H, W, 3), np.float32)
    add(img, m, k=0.85); add(img, gblur(m, 14 * K), k=0.5)
    mk = markm(ms, cx, cy)
    add(img, mk, k=0.96); add(img, gblur(mk, 50 * K), k=0.3)
    brand(img, y=cy + ms / 2 + 70 * K, size=22)
    return img


# ------------------------------------------------------------------ 7 dust
def dust(t):
    cx, cy, ms = W / 2, H * 0.46, 560 * K
    rng = np.random.default_rng(11)
    mk = markm(ms, cx, cy)
    yy, xx = np.nonzero(mk > 0.5)
    n1 = int(110000 * K * K * 4) if PREVIEW else 110000
    idx = rng.integers(0, len(xx), n1)
    x0 = xx[idx] + rng.random(n1); y0 = yy[idx] + rng.random(n1)
    amp = (1.5 + 4 * rng.random(n1)) * K; ph = rng.random(n1) * TAU
    x = x0 + amp * np.cos(TAU * t + ph); y = y0 + amp * np.sin(TAU * t + ph)
    al = np.full(n1, 1.0, np.float32)
    u = np.clip((x0 - (cx - ms / 2)) / ms, 0, 1)
    blow = rng.random(n1) < (u ** 2.2) * 0.55
    fr = (t + rng.random(n1)) % 1
    r1, r2 = rng.random(n1), rng.random(n1) - 0.5
    x = np.where(blow, x + fr ** 1.5 * (350 + 1000 * r1) * K, x)
    y = np.where(blow, y - fr * 160 * r2 * K * 2 + np.sin(TAU * fr * 2 + ph) * 30 * K * fr, y)
    al = np.where(blow, (1 - fr) ** 1.4, al)
    n2 = 7000
    ax, ay = rng.random(n2) * W, rng.random(n2) * H
    aa = (30 + 60 * rng.random(n2)) * K; ap = rng.random(n2) * TAU
    ax = ax + aa * np.cos(TAU * t + ap); ay = ay + aa * 0.6 * np.sin(TAU * t + ap)
    X = np.concatenate([x, ax]); Y = np.concatenate([y, ay])
    A = np.concatenate([al, 0.12 + 0.25 * rng.random(n2)])
    ok = (X >= 0) & (X < W - 1) & (Y >= 0) & (Y < H - 1)
    acc = np.zeros((H, W), np.float32)
    np.add.at(acc, (Y[ok].astype(int), X[ok].astype(int)), A[ok])
    lum = np.clip(acc * 0.75, 0, 1)
    img = np.zeros((H, W, 3), np.float32)
    add(img, lum); add(img, gblur(lum, 1.2 * K), k=0.5)
    add(img, gblur(mk, 120 * K), k=0.12)
    brand(img, y=cy + ms / 2 + 90 * K, size=22)
    return img


# ------------------------------------------------------------------ 8 neon
def neon(t):
    cx, cy, ms = W / 2, H * 0.40, 380 * K
    ty = cy + ms / 2 + 120 * K
    hum = 1 - 0.035 * (0.5 + 0.5 * math.sin(TAU * 9 * t))
    core = tube(markm(ms, cx, cy), 2.4 * K, 0.22)
    txt = layer(lambda c: wordmark(c, cx, ty, 52 * K, 1.0, 0.42, weight=cairo.FONT_WEIGHT_NORMAL))
    fl = 1.0
    for a, b in ((0.620, 0.628), (0.640, 0.652), (0.665, 0.670)):
        if a <= t < b: fl = 0.18
    core = core + tube(txt, 1.2 * K, 0.26) * 0.9 * fl
    glow = (0.62, 0.84, 1.0)
    img = np.zeros((H, W, 3), np.float32)
    add(img, core, k=hum)
    add(img, gblur(core, 5 * K), glow, 1.1 * hum)
    add(img, gblur(core, 22 * K), glow, 0.75 * hum)
    add(img, gblur(core, 90 * K), glow, 0.45 * hum)
    yf = int(ty + 70 * K)
    n = H - yf
    refl = img[yf - 1 - np.arange(n)][:, :, :].copy()
    for ch in range(3):
        refl[..., ch] = gblur(refl[..., ch], 9 * K)
    fade = (0.22 * np.exp(-np.arange(n) / (240 * K)))[:, None, None]
    img[yf:] += refl * fade
    floor = np.exp(-((np.arange(H) - yf) / (3 * K)) ** 2)[:, None] * np.exp(-((np.arange(W) - cx) / (700 * K)) ** 2)[None, :]
    add(img, floor.astype(np.float32), glow, 0.08)
    img *= vignette(0.5, 0.45, 0.7, 0.8, 1.2)[..., None]
    return img


# ------------------------------------------------------------------ 9 stars
def stars(t):
    rng = np.random.default_rng(13)
    img = np.zeros((H, W, 3), np.float32)
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    d = (xx * 0.42 - yy + H * 0.15) / math.hypot(0.42, 1)
    band = np.exp(-(d / (260 * K)) ** 2)
    neb = band * (0.35 + smooth_noise(4, 160 * K, W, H) * 0.9) * smooth_noise(6, 60 * K, W, H)
    add(img, neb.astype(np.float32), (0.75, 0.82, 1.0), 0.09)
    n = 2600
    sx, sy = rng.random(n) * W, rng.random(n) * H
    bx = rng.random(2200) * W; by = (bx * 0.42 + H * 0.15) + rng.normal(0, 200 * K, 2200)
    sx, sy = np.concatenate([sx, bx]), np.concatenate([sy, by])
    mag = rng.random(len(sx)) ** 7
    tw = 0.7 + 0.3 * np.sin(TAU * rng.integers(1, 4, len(sx)) * t + rng.random(len(sx)) * TAU)
    temp = rng.random(len(sx))

    def starfield(warm):
        def f(c):
            for x, y, m, w, tp in zip(sx, sy, mag, tw, temp):
                if (tp > 0.6) != warm: continue
                c.set_source_rgba(0, 0, 0, min(1, 0.25 + m * 0.9) * w)
                c.arc(x, y, (0.6 + m * 2.2) * K, 0, TAU); c.fill()
        return f
    for warm, col in ((False, (0.82, 0.9, 1.0)), (True, (1.0, 0.94, 0.86))):
        m = layer(starfield(warm)); add(img, m, col); add(img, gblur(m, 3 * K), col, 0.8)

    # constellation along the mark's wall centre lines
    g = GRID["grid"]; e = GRID["edges"]; span = e[-1] - e[0]
    ms, mcx, mcy, rot = 560 * K, W * 0.62, H * 0.45, math.radians(-9)
    cr, srt = math.cos(rot), math.sin(rot)
    def P(r, c):
        u = ((e[c] + e[c + 1]) / 2 - e[0]) / span - 0.5
        v = ((e[r] + e[r + 1]) / 2 - e[0]) / span - 0.5
        return mcx + (u * cr - v * srt) * ms, mcy + (u * srt + v * cr) * ms
    R, C = len(g), len(g[0])
    on = lambda r, c: 0 <= r < R and 0 <= c < C and g[r][c]
    nodes = []
    for r in range(R):
        for c in range(C):
            if not g[r][c]: continue
            h = on(r, c - 1) + on(r, c + 1); v = on(r - 1, c) + on(r + 1, c)
            if not ((h == 2 and v == 0) or (v == 2 and h == 0)):
                nodes.append((r, c))
    def lines(c):
        c.set_line_width(1.5 * K); c.set_source_rgba(0, 0, 0, 0.45)
        for r in range(R):
            for cc in range(C):
                if not g[r][cc]: continue
                if on(r, cc + 1): c.move_to(*P(r, cc)); c.line_to(*P(r, cc + 1)); c.stroke()
                if on(r + 1, cc): c.move_to(*P(r, cc)); c.line_to(*P(r + 1, cc)); c.stroke()
    ln = layer(lines)
    sd = ((xx - (mcx - ms * 0.75)) + (yy - (mcy - ms * 0.75))) / (ms * 3.0)
    ln = ln * (0.7 + 1.3 * np.exp(-((sd - (-0.4 + 1.8 * t)) / 0.07) ** 2))
    add(img, ln, (0.8, 0.88, 1.0)); add(img, gblur(ln, 6 * K), (0.6, 0.75, 1.0), 0.6)
    tw2 = rng.random(len(nodes)) * TAU
    def cstars(c):
        for (r, cc), p in zip(nodes, tw2):
            x, y = P(r, cc); w = 0.75 + 0.25 * math.sin(TAU * t * 2 + p)
            c.set_source_rgba(0, 0, 0, w); c.arc(x, y, 4.2 * K, 0, TAU); c.fill()
            c.set_line_width(0.8 * K); c.set_source_rgba(0, 0, 0, 0.35 * w)
            L = 16 * K * w
            c.move_to(x - L, y); c.line_to(x + L, y); c.move_to(x, y - L); c.line_to(x, y + L); c.stroke()
    cs = layer(cstars)
    add(img, cs); add(img, gblur(cs, 6 * K), (0.75, 0.85, 1.0), 1.2); add(img, gblur(cs, 30 * K), (0.6, 0.75, 1.0), 0.5)
    lx, ly = P(R - 1, C - 1)
    lab = layer(lambda c: (wordmark(c, lx + 30 * K, ly + 70 * K, 22 * K, 0.9, 0.6, "left"),
                           wordmark(c, lx + 30 * K, ly + 104 * K, 14 * K, 0.5, 0.3, "left",
                                    cairo.FONT_WEIGHT_NORMAL, "α LABYRINTHUS · 15×15", MONO)))
    add(img, lab)
    return img


# ------------------------------------------------------------------ 10 caustics
def caustics(t):
    s = 1
    w2, h2 = W // s, H // s
    yy, xx = np.mgrid[0:h2, 0:w2].astype(np.float32)
    uv = np.stack([xx / h2, yy / h2]) * 2.4
    p = np.mod(uv * TAU, TAU) - 250.0
    ix, iy = p[0].copy(), p[1].copy()
    c = np.ones_like(ix); inten = 0.005
    ks = [1, 1, 2, 1, 2]
    for n in range(5):
        tt = TAU * t * ks[n] + n * 1.7
        nx = p[0] + np.cos(tt - ix) + np.sin(tt + iy)
        ny = p[1] + np.sin(tt - iy) + np.cos(tt + ix)
        ix, iy = nx, ny
        c += 1.0 / np.sqrt((p[0] / (np.sin(ix + tt) / inten)) ** 2 + (p[1] / (np.cos(iy + tt) / inten)) ** 2)
    c /= 5
    c = 1.17 - np.power(c, 1.4)
    light = np.clip(np.abs(c) ** 7 * 1.3, 0, 1).astype(np.float32)
    light = np.asarray(Image.fromarray(np.uint8(np.clip(light, 0, 1) * 255)).resize((W, H), Image.BICUBIC), np.float32) / 255
    cx, cy, ms = W / 2, H / 2 - 20 * K, 520 * K
    mk = gblur(markm(ms, cx, cy), 2 * K)
    lum = light * (0.2 + 0.95 * mk) + mk * 0.1
    img = np.zeros((H, W, 3), np.float32)
    add(img, lum.astype(np.float32), (0.86, 0.94, 1.0))
    bloom(img, 10 * K, 0.35)
    img *= vignette(0.5, 0.5, 0.62, 0.75, 1.6)[..., None]
    brand(img, size=20, plate=True)
    return img


# ------------------------------------------------------------------ 11 weave
def weave(t):
    cell = 80 * K
    cols, rows = int(math.ceil(W / cell)) + 1, int(math.ceil(H / cell)) + 1
    ox, oy = (W - cols * cell) / 2, (H - rows * cell) / 2
    rng = np.random.default_rng(17)
    o = rng.integers(0, 2, (rows, cols))
    cx, cy = W / 2, H / 2
    ms = 4 * cell; clear = ms / 2 + cell * 0.6
    maxd = math.hypot(W / 2, H / 2)
    bright = np.zeros((rows, cols))

    def tiles(c):
        c.set_line_cap(cairo.LINE_CAP_ROUND); c.set_line_width(3 * K)
        for r in range(rows):
            for k in range(cols):
                x, y = ox + (k + 0.5) * cell, oy + (r + 0.5) * cell
                if abs(x - cx) < clear and abs(y - cy) < clear: continue
                dn = math.hypot(x - cx, y - cy) / maxd
                ph = (t - dn * 0.8) % 1
                turn = float(smoothstep(0, 0.22, ph))
                b = 0.2 + 0.75 * math.sin(math.pi * min(1, ph / 0.22)) * (ph < 0.22)
                c.save(); c.translate(x, y); c.rotate(o[r, k] * math.pi / 2 + turn * math.pi)
                c.set_source_rgba(0, 0, 0, b)
                h = cell / 2
                c.arc(-h, -h, h, 0, math.pi / 2); c.stroke()
                c.arc(h, h, h, math.pi, 1.5 * math.pi); c.stroke()
                c.restore()
    m = layer(tiles)
    img = np.zeros((H, W, 3), np.float32)
    add(img, m); add(img, gblur(m, 8 * K), k=0.6)
    mk = markm(ms, cx, cy)
    add(img, mk, k=0.96); add(img, gblur(mk, 60 * K), k=0.3)
    brand(img, y=cy + clear - 18 * K, size=16)
    img *= vignette(0.5, 0.5, 0.7, 0.8, 1.0)[..., None]
    return img


# ------------------------------------------------------------------ 12 radar
def radar(t):
    cx, cy = W / 2, H / 2
    cell = 60 * K
    cols, rows = int(W / cell) + 2, int(H / cell) + 2
    ox, oy = cx - cols * cell / 2, cy - rows * cell / 2
    rng = np.random.default_rng(19)
    # depth-first maze
    seen = np.zeros((rows, cols), bool); walls = set()
    for r in range(rows):
        for c in range(cols):
            walls.add(("h", r, c)); walls.add(("v", r, c))
    stack = [(rows // 2, cols // 2)]; seen[stack[0]] = True
    while stack:
        r, c = stack[-1]
        nb = [(r + dr, c + dc) for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1))
              if 0 <= r + dr < rows and 0 <= c + dc < cols and not seen[r + dr, c + dc]]
        if not nb: stack.pop(); continue
        nr, nc = nb[rng.integers(len(nb))]
        if nr != r: walls.discard(("h", max(r, nr), c))
        else: walls.discard(("v", r, max(c, nc)))
        seen[nr, nc] = True; stack.append((nr, nc))

    def mz(ctx):
        ctx.set_line_width(2.4 * K); ctx.set_line_cap(cairo.LINE_CAP_SQUARE)
        for kind, r, c in walls:
            x, y = ox + c * cell, oy + r * cell
            ctx.move_to(x, y); ctx.line_to(x + cell, y) if kind == "h" else ctx.line_to(x, y + cell)
        ctx.stroke()
    wl = layer(mz)
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    rr = np.hypot(xx - cx, yy - cy)
    wl *= smoothstep(250 * K, 300 * K, rr)
    th = TAU * t - math.pi / 2
    lag = np.mod(th - np.arctan2(yy - cy, xx - cx), TAU)
    glow = np.exp(-lag / 1.0)
    lit = wl * (0.06 + 0.92 * glow)
    wedge = np.exp(-lag / 0.28) * 0.09 * smoothstep(250 * K, 320 * K, rr) * np.exp(-rr / (1400 * K))

    def hud(c):
        c.set_line_width(1.1 * K)
        for R in (300, 520, 760, 1000, 1260):
            c.set_source_rgba(0, 0, 0, 0.16); c.arc(cx, cy, R * K, 0, TAU); c.stroke()
        for i in range(120):
            a = i / 120 * TAU; L = (14 if i % 10 == 0 else 6) * K
            c.set_source_rgba(0, 0, 0, 0.4 if i % 10 == 0 else 0.22)
            c.move_to(cx + math.cos(a) * 300 * K, cy + math.sin(a) * 300 * K)
            c.line_to(cx + math.cos(a) * (300 * K + L), cy + math.sin(a) * (300 * K + L)); c.stroke()
        c.set_source_rgba(0, 0, 0, 0.85); c.set_line_width(1.6 * K)
        c.move_to(cx + math.cos(th) * 300 * K, cy + math.sin(th) * 300 * K)
        c.line_to(cx + math.cos(th) * W, cy + math.sin(th) * W); c.stroke()
    hd = layer(hud)
    img = np.zeros((H, W, 3), np.float32)
    add(img, lit); add(img, gblur(lit, 5 * K), k=0.8)
    add(img, wedge.astype(np.float32))
    add(img, hd); add(img, gblur(hd, 8 * K), k=0.6)
    ms = 190 * K
    mk = markm(ms, cx, cy - 25 * K)
    add(img, mk, k=0.96); add(img, gblur(mk, 50 * K), k=0.3)
    brand(img, y=cy + ms / 2 + 50 * K, size=18)
    return img


# name: (seconds per cycle, cycles per video file, display name)
LOOPS = {
    "pulse": (2.5, 5, "Pulse"), "rain": (12, 1, "Rain"), "orbit": (20, 1, "Orbit"),
    "scan": (9, 2, "Scan"), "depth": (4, 4, "Depth"), "wave": (6, 2, "Wave"),
    "dust": (10, 1, "Dust"), "neon": (10, 1, "Neon"),
    "caustics": (16, 1, "Caustics"), "weave": (8, 2, "Weave"), "radar": (6, 2, "Radar"),
}

DESIGNS = {  # name: (frame function, t used for the review still)
    "pulse": (pulse, 0.35), "rain": (rain, 0.3), "orbit": (orbit, 0.1), "scan": (scan, 0.58),
    "depth": (depth, 0.4), "wave": (wave, 0.2), "dust": (dust, 0.5), "neon": (neon, 0.0),
    "stars": (stars, 0.0), "caustics": (caustics, 0.3), "weave": (weave, 0.32), "radar": (radar, 0.16),
}


def contact_sheet(out_dir, names):
    tw, th, cols = 640, 360, 3
    rows = (len(names) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * tw + (cols + 1) * 16, rows * (th + 44) + 16), (18, 18, 18))
    d = ImageDraw.Draw(sheet)
    try: font = ImageFont.truetype("/usr/share/fonts/inter/InterVariable.ttf", 20)
    except OSError: font = None
    for i, n in enumerate(names):
        im = Image.open(os.path.join(out_dir, f"maze-live-{n}.png")).resize((tw, th), Image.LANCZOS)
        x = 16 + (i % cols) * (tw + 16); y = 16 + (i // cols) * (th + 44)
        sheet.paste(im, (x, y))
        d.text((x, y + th + 8), f"{i + 1:02d}  Maze {n.capitalize()}", fill=(220, 220, 220), font=font)
    sheet.save(os.path.join(out_dir, "onizleme-live.jpg"), quality=90)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    out = args[0] if args else "."
    names = args[1:] or list(DESIGNS)
    os.makedirs(out, exist_ok=True)
    import time
    for n in names:
        t0 = time.time()
        fn, ts = DESIGNS[n]
        finish(fn(ts)).save(os.path.join(out, f"maze-live-{n}.png"), optimize=True)
        print(f"{n}: {time.time() - t0:.1f}s")
    if not args[1:]:
        contact_sheet(out, names)
