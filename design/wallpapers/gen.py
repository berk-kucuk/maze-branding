#!/usr/bin/env python3
"""Maze Linux wallpapers, OLED edition — 2560x1440 (16:9, 2K).

    python3 gen.py <out-dir> [name ...]

Pipeline for every design:
  1. sharp geometry (maze walls, blocks, bokeh discs) is drawn at 2x and
     downsampled — anti-aliased edges;
  2. all optics (depth of field, bloom, frosted glass) run at final size in
     float32 (fblur.gblur), so gradients never quantise before the end;
  3. the logo goes on last, sharp;
  4. grain is added only where the image is not black: pure-black pixels stay
     0,0,0 (true OLED black), lit gradients get just enough grain to not band.
"""
import math, os, random, sys
import numpy as np
from PIL import Image, ImageDraw
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fblur import gblur, _resize

W, H = 2560, 1440
SS = 2
SW, SH = W * SS, H * SS
SRC = "/run/media/berkkucukk/Backup/Projects/Maze-Linux-Source"
LOGO = os.path.join(SRC, "maze-installer/maze-installer/usr/share/calamares/branding/maze/maze-logo.png")
MARK = os.path.join(SRC, "maze-installer/maze-installer/usr/share/calamares/branding/maze/maze-simple-logo.png")
SILVER = np.array([0.90, 0.92, 0.97], np.float32)


# ------------------------------------------------------------------ basics
def grid(w=W, h=H):
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    return x, y

def gauss2(cx, cy, sx, sy, w=W, h=H):
    x, y = grid(w, h)
    return np.exp(-(((x - cx) / sx) ** 2 + ((y - cy) / sy) ** 2))

def down(a):
    """2x canvas (uint8 or float, 2-D or RGB) -> final size float32 0..1."""
    a = np.asarray(a, np.float32)
    if a.max() > 1.5: a = a / 255
    return _resize(a, W, H)

def maze(cols, rows, seed, hole=None):
    rnd = random.Random(seed)
    h = np.ones((rows + 1, cols), bool); v = np.ones((rows, cols + 1), bool)
    inhole = lambda c, r: bool(hole) and hole[0] <= c < hole[2] and hole[1] <= r < hole[3]
    seen = np.zeros((rows, cols), bool); stack = [(0, 0)]; seen[0, 0] = True
    while stack:
        c, r = stack[-1]
        nb = [(c+dc, r+dr) for dc, dr in ((1,0),(-1,0),(0,1),(0,-1))
              if 0 <= c+dc < cols and 0 <= r+dr < rows and not seen[r+dr, c+dc] and not inhole(c+dc, r+dr)]
        if not nb: stack.pop(); continue
        nc, nr = rnd.choice(nb)
        if nc != c: v[r, max(c, nc)] = False
        else:       h[max(r, nr), c] = False
        seen[nr, nc] = True; stack.append((nc, nr))
    if hole:
        c0, r0, c1, r1 = hole
        h[r0+1:r1, c0:c1] = False; v[r0:r1, c0+1:c1] = False
    return h, v

def segments(h, v, x0, y0, cs):
    out = []
    for r in range(h.shape[0]):
        for c in range(h.shape[1]):
            if h[r, c]: out.append((x0 + c*cs, y0 + r*cs, x0 + (c+1)*cs, y0 + r*cs))
    for r in range(v.shape[0]):
        for c in range(v.shape[1]):
            if v[r, c]: out.append((x0 + c*cs, y0 + r*cs, x0 + c*cs, y0 + (r+1)*cs))
    return out

def solve(h, v, start, goal):
    from collections import deque
    rows, cols = v.shape[0], h.shape[1]
    prev = {start: None}; q = deque([start])
    while q:
        c, r = q.popleft()
        if (c, r) == goal: break
        for dc, dr in ((1,0),(-1,0),(0,1),(0,-1)):
            nc, nr = c+dc, r+dr
            if not (0 <= nc < cols and 0 <= nr < rows) or (nc, nr) in prev: continue
            if (dc == 1 and v[r, c+1]) or (dc == -1 and v[r, c]) or (dr == 1 and h[r+1, c]) or (dr == -1 and h[r, c]): continue
            prev[(nc, nr)] = (c, r); q.append((nc, nr))
    path, p = [], goal
    while p is not None: path.append(p); p = prev.get(p)
    return path[::-1]

def line_mask(segs, width):
    im = Image.new("L", (SW, SH), 0); d = ImageDraw.Draw(im)
    for s in segs: d.line(s, fill=255, width=width)
    return down(im)

def dof(img, rmap, levels=(0, 2, 4.5, 9, 16, 28, 44)):
    """Depth of field: per-pixel blur radius rmap (in px, final size)."""
    stack = [img if s == 0 else gblur(img, s) for s in levels]
    lv = np.array(levels, np.float32)
    r = np.clip(rmap, 0, lv[-1])
    idx = np.clip(np.searchsorted(lv, r, side="right") - 1, 0, len(lv) - 2)
    t = (r - lv[idx]) / (lv[idx + 1] - lv[idx])
    if img.ndim == 3: idx, t = idx[..., None], t[..., None]
    out = np.zeros_like(img)
    for i in range(len(lv) - 1):
        m = (idx == i)
        if not m.any(): continue
        out = np.where(m, stack[i] * (1 - t) + stack[i + 1] * t, out)
    return out

def bloom(img, amount=1.0, sigmas=((6, 0.55), (24, 0.35), (80, 0.25))):
    lum = img.max(axis=2) if img.ndim == 3 else img
    hi = np.clip(lum - 0.25, 0, None) / 0.75
    add = sum(gblur(hi, s) * k for s, k in sigmas) * amount
    return add

def logo_layer(path, width, cx, cy, opacity=1.0):
    lg = Image.open(path).convert("RGBA")
    lh = int(lg.height * width / lg.width)
    lg = lg.resize((int(width), lh), Image.LANCZOS)
    a = np.asarray(lg, np.float32) / 255
    return a, int(cx - width / 2), int(cy - lh / 2), opacity

def paste(rgb, layer):
    a, x0, y0, op = layer
    h, w = a.shape[:2]
    al = a[..., 3:4] * op
    rgb[y0:y0+h, x0:x0+w] = rgb[y0:y0+h, x0:x0+w] * (1 - al) + a[..., :3] * al
    return rgb

def finish(rgb, name, out, grain=1.4):
    rgb = np.clip(rgb, 0, 1)
    a = rgb * 255
    n = np.random.default_rng(7).normal(0, grain, (H, W, 1)).astype(np.float32)
    lum = a.mean(axis=2, keepdims=True) / 255
    a = a + n * np.clip(lum * 30, 0, 1)          # black stays black
    a = np.clip(np.round(a), 0, 255).astype(np.uint8)
    Image.fromarray(a, "RGB").save(os.path.join(out, f"{name}.png"), optimize=True)
    blk = (a.max(axis=2) == 0).mean() * 100
    print(f"wrote {name}  (true-black pixels: {blk:.0f}%)")

def vignette(power=1.0, cx=W/2, cy=H/2, rx=W*0.75, ry=H*0.95):
    x, y = grid()
    d = np.sqrt(((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2)
    return np.clip(1 - d, 0, 1) ** power


# ------------------------------------------------------------------ designs
def d_depth(out):
    """Isometric maze in tilt-shift: a sharp band, everything else melts."""
    mc, mr = 30, 30
    h, v = maze(mc, mr, 5)
    gc, gr = 2*mc + 1, 2*mr + 1
    g = np.zeros((gr, gc), bool); g[0::2, 0::2] = True
    for r in range(mr + 1):
        for c in range(mc):
            if h[r, c]: g[2*r, 2*c+1] = True
    for r in range(mr):
        for c in range(mc + 1):
            if v[r, c]: g[2*r+1, 2*c] = True
    tile, bh = 78 * SS, 52 * SS
    th = tile / 2
    ox, oy = SW * 0.50, -tile * 9.0
    img = Image.new("RGB", (SW, SH), (0, 0, 0)); d = ImageDraw.Draw(img)
    L = (SW * 0.47, SH * 0.52)
    def sh(k, x, y):
        f = math.exp(-(((x - L[0]) / (SW*0.34)) ** 2 + ((y - L[1]) / (SH*0.40)) ** 2))
        v_ = k * (0.03 + 0.97 * f)
        return (int(v_*232), int(v_*236), int(v_*248))
    for s in range(gr + gc):
        for r in range(gr):
            c = s - r
            if not (0 <= c < gc) or not g[r, c]: continue
            x = ox + (c - r) * tile / 2; y = oy + (c + r) * th / 2
            top = [(x, y - bh), (x + tile/2, y + th/2 - bh), (x, y + th - bh), (x - tile/2, y + th/2 - bh)]
            left = [(x - tile/2, y + th/2 - bh), (x, y + th - bh), (x, y + th), (x - tile/2, y + th/2)]
            right = [(x + tile/2, y + th/2 - bh), (x, y + th - bh), (x, y + th), (x + tile/2, y + th/2)]
            d.polygon(left, fill=sh(0.30, x, y)); d.polygon(right, fill=sh(0.14, x, y))
            d.polygon(top, fill=sh(0.62, x, y - bh))
            d.line([top[3], top[0], top[1]], fill=sh(1.0, x, y - bh), width=2 * SS)
    rgb = down(img)
    x, y = grid()
    focus = H * 0.54
    rmap = (np.abs(y - focus) / (H * 0.5)) ** 1.35 * 44
    rgb = dof(rgb, rmap)
    rgb = rgb + bloom(rgb, 0.35)[..., None] * SILVER
    rgb *= vignette(0.8, W*0.48, H*0.52, W*0.78, H*0.92)[..., None]
    rgb = paste(rgb, logo_layer(LOGO, 300, W - 240, H - 140, 0.92))
    finish(rgb, "maze-depth", out)

def d_bokeh(out):
    """Out-of-focus lights over a lost-in-blur maze."""
    rnd = random.Random(9)
    cs = 90
    h, v = maze(W // cs + 2, H // cs + 2, 31)
    m = line_mask(segments(h, v, -cs * SS // 2, -cs * SS // 2, cs * SS), 3 * SS)
    base = gblur(m, 7) * 0.22 * gauss2(W*0.66, H*0.40, W*0.42, H*0.55)
    disc = np.zeros((SH, SW), np.float32)
    x2, y2 = grid(SW, SH)
    lights = []
    for _ in range(46):
        t = rnd.random()
        cx = W * (0.30 + 0.70 * t) + rnd.gauss(0, W * 0.07)
        cy = H * (0.95 - 0.85 * t) + rnd.gauss(0, H * 0.12)
        r = rnd.choice([rnd.uniform(18, 40), rnd.uniform(40, 90), rnd.uniform(90, 150)])
        lights.append((cx, cy, r, rnd.uniform(0.05, 0.20)))
    for cx, cy, r, b in lights:
        cx2, cy2, r2 = cx * SS, cy * SS, r * SS
        x0, x1 = int(max(0, cx2 - r2 - 4)), int(min(SW, cx2 + r2 + 4))
        y0, y1 = int(max(0, cy2 - r2 - 4)), int(min(SH, cy2 + r2 + 4))
        if x1 <= x0 or y1 <= y0: continue
        dd = np.sqrt((x2[y0:y1, x0:x1] - cx2) ** 2 + (y2[y0:y1, x0:x1] - cy2) ** 2) / r2
        body = np.clip((1 - dd) * r2 / 6.0, 0, 1)            # soft edge
        rim = np.exp(-((dd - 0.93) / 0.05) ** 2) * 0.18       # faint lens rim
        disc[y0:y1, x0:x1] += (body * (0.85 + 0.15 * dd) + rim) * b
    disc = gblur(down(disc), 2.5)
    rgb = base[..., None] * SILVER + disc[..., None] * np.array([0.86, 0.90, 1.0], np.float32)
    rgb = rgb + bloom(rgb, 0.35)[..., None] * SILVER
    rgb = paste(rgb, logo_layer(LOGO, 440, W * 0.30, H * 0.50))
    finish(rgb, "maze-bokeh", out)

def d_glass(out):
    """A frosted-glass tile floating over a glowing maze."""
    cs = 70
    h, v = maze(W // cs + 2, H // cs + 2, 17)
    m = line_mask(segments(h, v, 0, 0, cs * SS), 3 * SS)
    light = gauss2(W*0.62, H*0.46, W*0.30, H*0.42) + 0.6 * gauss2(W*0.18, H*0.9, W*0.18, H*0.25)
    scene = m * (0.05 + 0.85 * light)
    scene = scene[..., None] * SILVER
    blobs = (gauss2(W*0.70, H*0.36, W*0.07, H*0.12) * 0.55 + gauss2(W*0.53, H*0.64, W*0.08, H*0.10) * 0.40
             + gauss2(W*0.66, H*0.72, W*0.04, H*0.06) * 0.35)
    scene = scene + blobs[..., None] * np.array([0.80, 0.86, 1.0], np.float32)
    scene = scene + bloom(scene, 0.8)[..., None] * SILVER
    # glass tile
    gw, gh, rad = 760, 760, 64
    gx, gy = int(W * 0.62 - gw / 2), int(H * 0.5 - gh / 2)
    tile = Image.new("L", (SW, SH), 0)
    ImageDraw.Draw(tile).rounded_rectangle((gx*SS, gy*SS, (gx+gw)*SS, (gy+gh)*SS), radius=rad*SS, fill=255)
    tm = down(tile)
    frosted = gblur(scene, 34) * 1.35 + 0.045
    shadow = gblur(np.roll(tm, 24, 0), 40) * 0.55
    rgb = scene * (1 - shadow[..., None])
    rgb = rgb * (1 - tm[..., None]) + frosted * tm[..., None]
    # rim light: top-left edge brighter
    edge = np.clip(tm - np.roll(np.roll(tm, 2, 0), 2, 1), 0, 1)
    x, y = grid()
    rimk = np.clip(1.2 - ((x - gx) / gw + (y - gy) / gh) * 0.6, 0.2, 1)
    rgb += (edge * rimk * 0.85)[..., None]
    rgb *= vignette(0.6, W*0.55, H*0.5, W*0.85, H*1.0)[..., None]
    rgb = paste(rgb, logo_layer(LOGO, 540, gx + gw / 2, gy + gh / 2, 0.95))
    finish(rgb, "maze-glass", out)

def neon_mark(size):
    mk = Image.open(MARK).convert("RGBA").resize((size * SS, size * SS), Image.LANCZOS)
    a = np.asarray(mk, np.float32)[..., 3] / 255
    a = np.clip((a - 0.35) / 0.3, 0, 1)
    er = a.copy()
    for dx, dy in ((4,0),(-4,0),(0,4),(0,-4),(3,3),(-3,-3),(3,-3),(-3,3)):
        er = np.minimum(er, np.roll(np.roll(a, dy * SS, 0), dx * SS, 1))
    return np.clip(a - er, 0, 1)                        # outline at 2x

def d_neon(out):
    """The Maze mark as light tubes, blooming into black."""
    size = 1330
    o2 = neon_mark(size)
    canvas = np.zeros((SH, SW), np.float32)
    ox, oy = int(W * 0.50) * SS, int(H * 0.08) * SS
    x1, y1 = min(SW, ox + o2.shape[1]), min(SH, oy + o2.shape[0])
    canvas[max(0, oy):y1, ox:x1] = o2[max(0, -oy):max(0, -oy) + y1 - max(0, oy), :x1 - ox]
    core = down(canvas)
    x, y = grid()
    rmap = np.clip((x - W * 0.62) / (W * 0.38), 0, 1) ** 1.4 * 20   # far edge softens
    core = dof(core, rmap, (0, 2, 5, 10, 20))
    glow = gblur(core, 5) * 0.9 + gblur(core, 22) * 0.7 + gblur(core, 90) * 0.55
    rgb = np.clip(core * 1.6, 0, 1)[..., None] * np.array([0.97, 0.98, 1.0], np.float32) + glow[..., None] * np.array([0.72, 0.80, 1.0], np.float32) * 0.7
    rgb = paste(rgb, logo_layer(LOGO, 440, W * 0.22, H * 0.74, 0.95))
    finish(rgb, "maze-neon", out)

def d_horizon(out):
    """A maze floor running to a lit horizon, with real depth of field."""
    cols, rows = 70, 110
    h, v = maze(cols, rows, 42)
    horizon, f, cam = H * 0.50, W * 0.55, 2.1
    im = Image.new("L", (SW, SH), 0); d = ImageDraw.Draw(im)
    for x1, z1, x2, z2 in segments(h, v, -cols / 2, 0, 1.0):
        z1 += 1.0; z2 += 1.0
        zz = (z1 + z2) / 2
        fog = max(0.0, 1 - zz / 110) ** 1.2
        w_ = max(1, int(SS * 9 / zz * 2.2))
        d.line(((SW/2 + x1*f*SS/z1), (horizon + cam*f/z1)*SS, (SW/2 + x2*f*SS/z2), (horizon + cam*f/z2)*SS),
               fill=int(255 * fog), width=w_)
    m = down(im)
    x, y = grid()
    # focus a third of the way into the floor; near and far both soften
    yf = horizon + (H - horizon) * 0.30
    below = np.clip((y - yf) / (H - yf), 0, 1); above = np.clip((yf - y) / (yf - horizon + 1), 0, 1)
    rmap = np.where(y > yf, below ** 1.5 * 34, above ** 1.2 * 12)
    rmap = np.where(y < horizon, 14, rmap)
    m = dof(m, rmap)
    band = np.exp(-((y - horizon) / (H * 0.03)) ** 2) * np.exp(-((x - W/2) / (W * 0.40)) ** 2)
    haze = np.exp(-((y - horizon) / (H * 0.14)) ** 2) * np.exp(-((x - W/2) / (W * 0.55)) ** 2)
    rgb = m[..., None] * SILVER * 1.25
    rgb = rgb + band[..., None] * np.array([0.34, 0.38, 0.46], np.float32) + haze[..., None] * 0.05
    rgb = rgb + bloom(rgb, 0.3)[..., None] * SILVER
    rgb = paste(rgb, logo_layer(LOGO, 440, W / 2, H * 0.27))
    finish(rgb, "maze-horizon", out)

def d_path(out):
    """The way through: one glowing path, the rest of the maze out of focus."""
    cs = 76
    cols, rows = W // cs + 1, H // cs + 1
    hc, hr = 9, 5
    c0, r0 = cols // 2 - hc // 2, rows // 2 - hr // 2
    h, v = maze(cols, rows, 23, (c0, r0, c0 + hc, r0 + hr))
    door = (c0 - 1, r0 + hr // 2); v[door[1], c0] = False
    x0, y0 = (W - cols * cs) // 2, (H - rows * cs) // 2
    m = line_mask(segments(h, v, x0 * SS, y0 * SS, cs * SS), 3 * SS)
    path = solve(h, v, (0, rows - 2), door)
    pim = Image.new("L", (SW, SH), 0)
    pts = [((x0 + (c + .5) * cs) * SS, (y0 + (r + .5) * cs) * SS) for c, r in path]
    pts.insert(0, ((x0 - cs) * SS, pts[0][1])); pts.append(((x0 + (c0 + .6) * cs) * SS, pts[-1][1]))
    ImageDraw.Draw(pim).line(pts, fill=255, width=4 * SS, joint="curve")
    p = down(pim)
    t = gauss2(W/2, H/2, W*0.36, H*0.48)
    rmap = (1 - gauss2(W/2, H/2, W*0.30, H*0.40)) * 22
    walls = dof(m * (0.05 + 0.20 * t), rmap)
    pth = dof(p * (0.20 + 0.80 * t), rmap * 0.6)
    rgb = walls[..., None] * SILVER + pth[..., None] * np.array([0.92, 0.96, 1.0], np.float32)
    rgb = rgb + (gblur(pth, 8) * 0.8 + gblur(pth, 30) * 0.6)[..., None] * np.array([0.70, 0.82, 1.0], np.float32) * 0.6
    rgb = paste(rgb, logo_layer(LOGO, 480, W / 2, H / 2))
    finish(rgb, "maze-path", out)

def d_aurora(out):
    """Mostly black; two coloured light leaks bleed in from the corners."""
    cs = 64
    h, v = maze(W // cs + 2, H // cs + 2, 77)
    m = line_mask(segments(h, v, 0, 0, cs * SS), 2 * SS)
    teal = np.array([0.08, 0.62, 0.64], np.float32)
    violet = np.array([0.45, 0.24, 0.85], np.float32)
    l1 = gauss2(W * 0.95, H * 1.05, W * 0.38, H * 0.55)
    l2 = gauss2(W * 0.02, H * 0.95, W * 0.30, H * 0.45)
    l1 = np.clip(l1 - 0.03, 0, None) / 0.97; l2 = np.clip(l2 - 0.03, 0, None) / 0.97
    light = l1[..., None] * teal * 0.75 + l2[..., None] * violet * 0.65
    walls = gblur(m, 1.6)
    rgb = light * 0.55 + walls[..., None] * light * 1.8
    rgb = rgb + bloom(rgb, 0.4)[..., None] * 0.5
    rgb = paste(rgb, logo_layer(LOGO, 460, W / 2, H / 2))
    finish(rgb, "maze-aurora", out)

def d_oled(out):
    """Pure black, the logo, and the faintest breath of light."""
    halo = gauss2(W/2, H/2, W*0.12, H*0.20) * 0.06
    rgb = halo[..., None] * np.array([0.9, 0.92, 1.0], np.float32)
    rgb = paste(rgb, logo_layer(LOGO, 300, W / 2, H / 2, 0.95))
    finish(rgb, "maze-oled", out, grain=1.6)


DESIGNS = {"depth": d_depth, "bokeh": d_bokeh, "glass": d_glass, "neon": d_neon,
           "horizon": d_horizon, "path": d_path, "aurora": d_aurora, "oled": d_oled}

if __name__ == "__main__":
    out = sys.argv[1]; os.makedirs(out, exist_ok=True)
    want = sys.argv[2:] or list(DESIGNS)
    for k in want:
        DESIGNS[k](out)
