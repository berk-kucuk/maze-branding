#!/usr/bin/env python3
"""Maze Linux wallpaper generator — 2560x1440 (16:9, 2K).

    python3 gen.py <out-dir> [name ...]

Every design is drawn at 2x and downsampled (anti-aliasing), then gets a faint
film grain so gradients do not band on 8-bit panels. Mazes are real
(recursive-backtracker, seeded), so each render is reproducible.
"""
import math, os, random, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

W, H = 2560, 1440
SS = 2                      # supersampling factor
SW, SH = W * SS, H * SS
HERE = os.path.dirname(os.path.abspath(__file__))
LOGO_PNG = os.path.join(HERE, "..", "..", "maze-branding", "usr", "share", "pixmaps", "maze-logo.png")


# ----------------------------------------------------------------- helpers
def find_logo():
    for p in (LOGO_PNG,
              os.path.join(HERE, "maze-logo.png"),
              "/run/media/berkkucukk/Backup/Projects/Maze-Linux-Source/maze-installer/maze-installer/usr/share/calamares/branding/maze/maze-logo.png"):
        if os.path.exists(p):
            return Image.open(p).convert("RGBA")
    raise SystemExit("maze-logo.png not found")

def find_mark():
    p = "/run/media/berkkucukk/Backup/Projects/Maze-Linux-Source/maze-installer/maze-installer/usr/share/calamares/branding/maze/maze-simple-logo.png"
    return Image.open(p).convert("RGBA")

def maze(cols, rows, seed, hole=None):
    """Perfect maze on a grid. hole=(c0,r0,c1,r1) is left empty (for a logo).
    Returns (h, v): h[r][c] = wall above cell (r,c) (rows+1 x cols),
    v[r][c] = wall left of cell (r,c) (rows x cols+1)."""
    rnd = random.Random(seed)
    h = np.ones((rows + 1, cols), bool)
    v = np.ones((rows, cols + 1), bool)
    inhole = lambda c, r: hole and hole[0] <= c < hole[2] and hole[1] <= r < hole[3]
    seen = np.zeros((rows, cols), bool)
    start = (0, 0)
    stack = [start]; seen[0, 0] = True
    while stack:
        c, r = stack[-1]
        nb = [(c+dc, r+dr) for dc, dr in ((1,0),(-1,0),(0,1),(0,-1))
              if 0 <= c+dc < cols and 0 <= r+dr < rows and not seen[r+dr, c+dc] and not inhole(c+dc, r+dr)]
        if not nb:
            stack.pop(); continue
        nc, nr = rnd.choice(nb)
        if nc != c: v[r, max(c, nc)] = False
        else:       h[max(r, nr), c] = False
        seen[nr, nc] = True
        stack.append((nc, nr))
    if hole:  # clear the inside of the hole, keep its border
        c0, r0, c1, r1 = hole
        h[r0+1:r1, c0:c1] = False
        v[r0:r1, c0+1:c1] = False
    return h, v

def wall_segments(h, v, x0, y0, cs):
    segs = []
    rows1, cols = h.shape
    for r in range(rows1):
        for c in range(cols):
            if h[r, c]: segs.append((x0 + c*cs, y0 + r*cs, x0 + (c+1)*cs, y0 + r*cs))
    rows, cols1 = v.shape
    for r in range(rows):
        for c in range(cols1):
            if v[r, c]: segs.append((x0 + c*cs, y0 + r*cs, x0 + c*cs, y0 + (r+1)*cs))
    return segs

def solve(h, v, start, goal):
    rows, cols = v.shape[0], h.shape[1]
    from collections import deque
    prev = {start: None}; q = deque([start])
    while q:
        c, r = q.popleft()
        if (c, r) == goal: break
        for dc, dr in ((1,0),(-1,0),(0,1),(0,-1)):
            nc, nr = c+dc, r+dr
            if not (0 <= nc < cols and 0 <= nr < rows) or (nc, nr) in prev: continue
            if dc == 1 and v[r, c+1]: continue
            if dc == -1 and v[r, c]: continue
            if dr == 1 and h[r+1, c]: continue
            if dr == -1 and h[r, c]: continue
            prev[(nc, nr)] = (c, r); q.append((nc, nr))
    path, p = [], goal
    while p is not None:
        path.append(p); p = prev.get(p)
    return path[::-1]

def radial(cx, cy, rx, ry, power=1.6):
    y, x = np.mgrid[0:SH, 0:SW].astype(np.float32)
    d = np.sqrt(((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2)
    return np.clip(1 - d, 0, 1) ** power

def blur(a, r):
    im = Image.fromarray(np.clip(a * 255, 0, 255).astype(np.uint8), "L")
    return np.asarray(im.filter(ImageFilter.GaussianBlur(r)), np.float32) / 255

def mask_from_segs(segs, width):
    im = Image.new("L", (SW, SH), 0); d = ImageDraw.Draw(im)
    for s in segs: d.line(s, fill=255, width=width)
    return np.asarray(im, np.float32) / 255

def finish(rgb, name, out, grain=2.2, keep_black=False):
    """rgb: float32 (SH,SW,3) in 0..1 at supersampled size."""
    im = Image.fromarray(np.clip(rgb * 255, 0, 255).astype(np.uint8), "RGB").resize((W, H), Image.LANCZOS)
    a = np.asarray(im, np.float32)
    rng = np.random.default_rng(7)
    n = rng.normal(0, grain, (H, W, 1)).astype(np.float32)
    if keep_black:  # OLED: pixels that are black stay exactly black; grain
        lum = a.mean(axis=2, keepdims=True) / 255   # fades in with brightness
        n *= np.clip(lum * 30, 0, 1)                # so gradients still dither
    a = np.clip(a + n, 0, 255).astype(np.uint8)
    Image.fromarray(a, "RGB").save(os.path.join(out, f"{name}.png"), optimize=True)
    print("wrote", name)

def paste_logo(rgb, logo, width, cx, cy, opacity=1.0, dark=False):
    lw = int(width * SS); lh = int(logo.height * lw / logo.width)
    lg = logo.resize((lw, lh), Image.LANCZOS)
    a = np.asarray(lg, np.float32) / 255
    col = a[..., :3]; al = a[..., 3:4] * opacity
    if dark: col = 1 - col * 0.92
    x0, y0 = int(cx * SS - lw / 2), int(cy * SS - lh / 2)
    reg = rgb[y0:y0+lh, x0:x0+lw]
    rgb[y0:y0+lh, x0:x0+lw] = reg * (1 - al) + col * al
    return rgb

BG = np.array([0.035, 0.035, 0.04], np.float32)

def base(color=BG):
    return np.broadcast_to(color, (SH, SW, 3)).copy()


# ----------------------------------------------------------------- designs
def d_labyrinth(out, logo):
    cs = 64 * SS
    cols, rows = SW // cs + 1, SH // cs + 1
    hc, hr = 9, 5
    c0, r0 = cols // 2 - hc // 2, rows // 2 - hr // 2
    h, v = maze(cols, rows, 11, (c0, r0, c0 + hc, r0 + hr))
    segs = wall_segments(h, v, (SW - cols*cs) // 2, (SH - rows*cs) // 2, cs)
    m = mask_from_segs(segs, 3 * SS)
    light = radial(SW/2, SH/2, SW*0.62, SH*0.9, 1.3)
    lines = m * (0.10 + 0.55 * light)
    glow = blur(m * light, 10 * SS) * 0.35
    rgb = base() + (lines + glow)[..., None] * np.array([0.92, 0.93, 0.97], np.float32)
    rgb += radial(SW/2, SH/2, SW*0.35, SH*0.45, 2.0)[..., None] * 0.05
    rgb = paste_logo(rgb, logo, 520, W/2, H/2)
    finish(rgb, "maze-labyrinth", out)

def d_solved(out, logo):
    cs = 72 * SS
    cols, rows = SW // cs + 1, SH // cs + 1
    hc, hr = 9, 5
    c0, r0 = cols // 2 - hc // 2, rows // 2 - hr // 2
    h, v = maze(cols, rows, 23, (c0, r0, c0 + hc, r0 + hr))
    # open the hole on its left side, one door, and solve to it
    door = (c0 - 1, r0 + hr // 2)
    v[door[1], c0] = False
    x0, y0 = (SW - cols*cs) // 2, (SH - rows*cs) // 2
    segs = wall_segments(h, v, x0, y0, cs)
    path = solve(h, v, (0, rows - 2), door)
    m = mask_from_segs(segs, 3 * SS)
    lines = m * (0.07 + 0.10 * radial(SW*0.45, SH*0.6, SW*0.7, SH*0.9, 1.2))
    pim = Image.new("L", (SW, SH), 0); d = ImageDraw.Draw(pim)
    pts = [(x0 + (c+0.5)*cs, y0 + (r+0.5)*cs) for c, r in path]
    pts.insert(0, (x0 - cs, pts[0][1]))
    pts.append((x0 + (c0 + 0.6)*cs, pts[-1][1]))
    d.line(pts, fill=255, width=4 * SS, joint="curve")
    p = np.asarray(pim, np.float32) / 255
    # brighter towards the centre: the way in
    t = radial(SW/2, SH/2, SW*0.75, SH*1.1, 1.0)
    core = p * (0.12 + 0.88 * t ** 1.6)
    glow = (blur(p, 6 * SS) * 0.7 + blur(p, 22 * SS) * 0.6) * (0.15 + 0.85 * t ** 1.2)
    tint = np.array([0.80, 0.90, 1.0], np.float32)
    rgb = base() + lines[..., None] * 0.9 + glow[..., None] * tint * 0.55 + core[..., None]
    rgb += radial(SW/2, SH/2, SW*0.25, SH*0.35, 2.0)[..., None] * 0.06
    rgb = paste_logo(rgb, logo, 500, W/2, H/2)
    finish(rgb, "maze-solved", out)

def d_isometric(out, logo):
    # block grid: walls of a maze become blocks
    mc, mr = 26, 26
    h, v = maze(mc, mr, 5)
    gc, gr = 2*mc + 1, 2*mr + 1
    g = np.zeros((gr, gc), bool)
    g[0::2, 0::2] = True
    for r in range(mr + 1):
        for c in range(mc):
            if h[r, c]: g[2*r, 2*c+1] = True
    for r in range(mr):
        for c in range(mc + 1):
            if v[r, c]: g[2*r+1, 2*c] = True
    tile = 70 * SS          # iso tile width
    th = tile / 2
    bh = 46 * SS            # block height
    ox, oy = SW / 2, -tile * 7.5
    img = Image.new("RGB", (SW, SH), tuple(int(x*255) for x in BG))
    d = ImageDraw.Draw(img)
    light_c = (SW*0.40, SH*0.40)
    def shade(base_v, x, y):
        dd = math.hypot((x - light_c[0]) / (SW*0.75), (y - light_c[1]) / (SH*0.95))
        f = max(0.0, 1 - dd) ** 1.3
        k = base_v * (0.18 + 0.82 * f)
        return (int(k*236), int(k*238), int(k*246))
    for s in range(gr + gc):
        for r in range(gr):
            c = s - r
            if not (0 <= c < gc) or not g[r, c]: continue
            x = ox + (c - r) * tile / 2
            y = oy + (c + r) * th / 2
            top = [(x, y - bh), (x + tile/2, y + th/2 - bh), (x, y + th - bh), (x - tile/2, y + th/2 - bh)]
            left = [(x - tile/2, y + th/2 - bh), (x, y + th - bh), (x, y + th), (x - tile/2, y + th/2)]
            right = [(x + tile/2, y + th/2 - bh), (x, y + th - bh), (x, y + th), (x + tile/2, y + th/2)]
            d.polygon(left, fill=shade(0.42, x, y))
            d.polygon(right, fill=shade(0.24, x, y))
            d.polygon(top, fill=shade(0.95, x, y - bh))
            d.line([top[3], top[0], top[1]], fill=shade(1.0, x, y - bh), width=SS)
    rgb = np.asarray(img, np.float32) / 255
    vign = radial(SW*0.46, SH*0.45, SW*0.78, SH*1.05, 0.9)
    rgb = BG + (rgb - BG) * vign[..., None]
    rgb = paste_logo(rgb, logo, 300, W - 250, H - 150, 0.9)
    finish(rgb, "maze-isometric", out)

def d_horizon(out, logo):
    cols, rows = 60, 90
    h, v = maze(cols, rows, 42)
    segs = wall_segments(h, v, -cols/2, 0, 1.0)   # world units: x in [-30,30], z in [0,90]
    horizon = SH * 0.47
    f = SW * 0.55
    cam_h = 2.2
    im = Image.new("L", (SW, SH), 0); d = ImageDraw.Draw(im)
    for x1, z1, x2, z2 in segs:
        z1 += 1.2; z2 += 1.2
        if z1 < 1.0 and z2 < 1.0: continue
        sx1, sy1 = SW/2 + x1 * f / z1, horizon + cam_h * f / z1
        sx2, sy2 = SW/2 + x2 * f / z2, horizon + cam_h * f / z2
        zz = (z1 + z2) / 2
        fog = max(0.0, 1 - zz / 95) ** 1.1
        w = max(1, int(7 * SS / zz * 3))
        d.line((sx1, sy1, sx2, sy2), fill=int(255 * fog), width=w)
    m = np.asarray(im, np.float32) / 255
    y, x = np.mgrid[0:SH, 0:SW].astype(np.float32)
    band = np.exp(-((y - horizon) / (SH * 0.035)) ** 2) * np.exp(-((x - SW/2) / (SW * 0.42)) ** 2)
    sky = np.clip((horizon - y) / horizon, 0, 1)
    rgb = base() + (m * 0.75)[..., None] * np.array([0.9, 0.92, 0.98], np.float32)
    rgb += blur(m, 8 * SS)[..., None] * 0.25
    rgb += band[..., None] * np.array([0.55, 0.58, 0.66], np.float32)
    rgb += (np.exp(-((y - horizon) / (SH * 0.16)) ** 2) * np.exp(-((x - SW/2) / (SW*0.6)) ** 2) * 0.10)[..., None]
    rgb -= (sky ** 2 * 0.02)[..., None]
    rgb = paste_logo(rgb, logo, 460, W/2, H * 0.27)
    finish(rgb, "maze-horizon", out)

def d_monolith(out, logo, mark):
    size = int(1650 * SS)
    mk = mark.resize((size, size), Image.LANCZOS)
    a = np.asarray(mk, np.float32)[..., 3] / 255
    a = np.clip((a - 0.35) / 0.3, 0, 1)                     # crisp upscaled edges
    a = blur(a, 1.2 * SS)
    canvas = np.zeros((SH, SW), np.float32)
    ox, oy = int(SW * 0.44), int(-SH * 0.06)
    x1, y1 = min(SW, ox + size), min(SH, oy + size)
    canvas[max(0, oy):y1, ox:x1] = a[max(0, -oy):max(0, -oy) + (y1 - max(0, oy)), :x1 - ox]
    # emboss: light from top-left
    sh = np.roll(np.roll(canvas, 10 * SS, 0), 10 * SS, 1)
    hi = np.roll(np.roll(canvas, -3 * SS, 0), -3 * SS, 1)
    body = canvas * 0.075
    edge_hi = np.clip(canvas - np.roll(np.roll(canvas, 4 * SS, 0), 4 * SS, 1), 0, 1) * 0.5
    shadow = np.clip(sh - canvas, 0, 1)
    face = radial(SW*0.62, SH*0.25, SW*0.7, SH*1.1, 1.0)
    rgb = base() + (body * (0.5 + face) + edge_hi * (0.3 + 0.7*face))[..., None] * np.array([0.92, 0.93, 0.97], np.float32)
    rgb -= blur(shadow, 14 * SS)[..., None] * 0.03
    rgb += radial(SW*0.7, SH*0.35, SW*0.55, SH*0.8, 1.8)[..., None] * 0.035
    rgb = paste_logo(rgb, logo, 460, 420, H - 200)
    finish(rgb, "maze-monolith", out)

def d_aurora(out, logo):
    cs = 56 * SS
    cols, rows = SW // cs + 1, SH // cs + 1
    h, v = maze(cols, rows, 77)
    segs = wall_segments(h, v, (SW - cols*cs)//2, (SH - rows*cs)//2, cs)
    m = mask_from_segs(segs, 2 * SS)
    y, x = np.mgrid[0:SH, 0:SW].astype(np.float32)
    xn, yn = x / SW, y / SH
    ribbon1 = np.exp(-((yn - (0.32 + 0.10*np.sin(xn*5.0 + 0.6))) / 0.13) ** 2)
    ribbon2 = np.exp(-((yn - (0.62 + 0.08*np.sin(xn*3.4 + 2.1))) / 0.16) ** 2)
    teal = np.array([0.10, 0.62, 0.62], np.float32)
    violet = np.array([0.42, 0.26, 0.78], np.float32)
    aur = ribbon1[..., None] * teal * (0.25 + 0.75*xn[..., None]) + ribbon2[..., None] * violet * (1 - 0.6*xn[..., None])
    aur = np.stack([blur(aur[..., i], 40 * SS) for i in range(3)], -1) * 0.55
    rgb = base() + aur
    rgb += (m * (0.08 + 0.55 * aur.max(axis=2)))[..., None] * np.array([0.92, 0.95, 1.0], np.float32)
    rgb = paste_logo(rgb, logo, 480, W/2, H/2)
    finish(rgb, "maze-aurora", out)

def d_paper(out, logo):
    cs = 80 * SS
    cols, rows = SW // cs + 1, SH // cs + 1
    hc, hr = 8, 4
    c0, r0 = cols // 2 - hc // 2, rows // 2 - hr // 2
    h, v = maze(cols, rows, 3, (c0, r0, c0 + hc, r0 + hr))
    segs = wall_segments(h, v, (SW - cols*cs)//2, (SH - rows*cs)//2, cs)
    m = mask_from_segs(segs, 10 * SS)
    paper = np.array([0.905, 0.905, 0.915], np.float32)
    shadow = np.clip(np.roll(np.roll(blur(m, 6 * SS), 7 * SS, 0), 7 * SS, 1) - m, 0, 1)
    hi = np.clip(np.roll(np.roll(m, -2 * SS, 0), -2 * SS, 1) - np.roll(np.roll(m, 2 * SS, 0), 2 * SS, 1), 0, 1)
    light = radial(SW*0.35, SH*0.2, SW*0.9, SH*1.3, 0.7)
    rgb = base(paper) * (0.93 + 0.07 * light)[..., None]
    rgb -= shadow[..., None] * 0.16
    rgb += hi[..., None] * 0.05
    rgb = paste_logo(rgb, logo, 500, W/2, H/2, 0.95, dark=True)
    finish(rgb, "maze-paper", out, grain=1.6)

def d_oled(out, logo):
    rgb = base(np.zeros(3, np.float32))
    y, x = np.mgrid[0:SH, 0:SW].astype(np.float32)
    # one thin square ring, the mark's outline, glowing faintly
    # Gaussian fall-off: reaches true black smoothly, no visible edge.
    halo = np.exp(-(((x - SW/2) / (SW * 0.12)) ** 2 + ((y - SH/2) / (SH * 0.20)) ** 2)) * 0.06
    rgb += halo[..., None] * np.array([0.9, 0.92, 1.0], np.float32)
    rgb = paste_logo(rgb, logo, 300, W/2, H/2, 0.95)
    finish(rgb, "maze-oled", out, grain=1.6, keep_black=True)


if __name__ == "__main__":
    out = sys.argv[1]; os.makedirs(out, exist_ok=True)
    want = set(sys.argv[2:])
    logo, mark = find_logo(), find_mark()
    designs = {
        "labyrinth": lambda: d_labyrinth(out, logo),
        "solved":    lambda: d_solved(out, logo),
        "isometric": lambda: d_isometric(out, logo),
        "horizon":   lambda: d_horizon(out, logo),
        "monolith":  lambda: d_monolith(out, logo, mark),
        "aurora":    lambda: d_aurora(out, logo),
        "paper":     lambda: d_paper(out, logo),
        "oled":      lambda: d_oled(out, logo),
    }
    for k, fn in designs.items():
        if not want or k in want:
            fn()
