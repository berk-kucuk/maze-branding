#!/usr/bin/env python3
"""Maze Linux — animated monochrome wallpapers (seamless GIF loops).

    python3 anim2d.py <out-dir> [topoflow|halftonewave|mazetrace|assemble ...] [--preview]

Every loop is seamless: frame N would equal frame 0. Grayscale GIF, so the
256-entry palette covers every level and there is no banding.
"""
import math, os, random, sys
import numpy as np
import cairo
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lines2d as L
from lines2d import mark_rects, mark_mask, gblur, smooth_noise

PREVIEW = "--preview" in sys.argv
W, H = (1280, 720) if PREVIEW else (1920, 1080)     # same size as the existing animated set
FRAMES = 24 if PREVIEW else 60
DELAY = 80            # ms per frame -> 60 frames = 4.8 s loop
LEVELS = 24           # grey levels kept; fewer levels = much better GIF compression


def finish(a):
    """float [0,1] -> uint8 L frame with an OLED black point."""
    a = np.clip(a, 0, 1) * 255
    a = np.clip((a - 1.5) * 255 / 253.5, 0, 255)
    step = 255 / (LEVELS - 1)
    a = np.round(np.round(a / step) * step)
    return Image.fromarray(a.astype(np.uint8), "L")

def surface_to_array(s, w=None, h=None):
    w = w or W; h = h or H
    return np.ndarray((h, s.get_stride() // 4, 4), np.uint8, s.get_data())[:, :w, 1].astype(np.float32) / 255

def write_gif(frames, out):
    frames[0].save(out, save_all=True, append_images=frames[1:], duration=DELAY, loop=0,
                   optimize=False, disposal=1)
    mb = os.path.getsize(out) / 1e6
    print(f"{os.path.basename(out)}: {W}x{H}, {len(frames)} frames, {mb:.1f} MB")

def vignette(strength, cx, cy, rx, ry, w=None, h=None):
    w = w or W; h = h or H
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    d = np.sqrt(((xx / w - cx) / rx) ** 2 + ((yy / h - cy) / ry) ** 2)
    return np.clip(1 - strength * np.clip(d - 0.35, 0, None) ** 1.4, 0, 1)


# ---------------------------------------------------------------- topoflow
def topoflow(out):
    """The topo terrain, contour levels drifting outward from the summit: the
    lines appear to ripple away from the mark. Five contour steps per loop."""
    S = 2; w, h = W * S, H * S; k = W / 2560
    size, cx, cy = 300 * S * k, 1720 * S * k, 700 * S * k
    m = mark_mask(size, cx, cy, w, h)
    hill = gblur(m, 90 * S * k) * 2.2 + gblur(m, 26 * S * k) * 0.9 + m * 0.25
    base = smooth_noise(7, 520 * S * k, w, h) * 1.3 + smooth_noise(11, 220 * S * k, w, h) * 0.18
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    ridge = np.exp(-(((xx - cx) / (900 * S * k)) ** 2 + ((yy - cy) / (700 * S * k)) ** 2)) * 1.2
    z = base + ridge + hill
    N = 22.0
    gy, gx = np.gradient(z)
    grad = np.sqrt(gx ** 2 + gy ** 2) + 1e-6
    width, soft = 0.8 * S * k, 0.9 * S * k
    vig = vignette(1.6, 0.66, 0.5, 0.55, 0.7)
    mk_small = np.asarray(Image.fromarray(np.uint8(m * 255)).resize((W, H), Image.LANCZOS), np.float32) / 255
    halo = gblur(m, 3 * S * k)
    frames = []
    for i in range(FRAMES):
        t = i / FRAMES
        # shift by 5 levels per loop: every 5th level is a major line, so after
        # 5 levels the major/minor pattern is back where it started (seamless)
        f = z * N + 5 * t                               # +t: levels move downhill, i.e. outward
        d = np.abs(f - np.round(f)) / (grad * N)
        line = np.clip(1 - (d - width) / soft, 0, 1)
        lvl = np.round(f).astype(np.int32)
        major = ((lvl % 5) == 0)
        a = line * np.where(major, 0.55, 0.2) * (1 - halo * 0.95)
        a = np.asarray(Image.fromarray(np.uint8(np.clip(a, 0, 1) * 255)).resize((W, H), Image.LANCZOS), np.float32) / 255
        a = np.maximum(a * vig, mk_small * 0.95)
        frames.append(finish(a))
        print(f"\rtopoflow {i + 1}/{FRAMES}", end="", flush=True)
    print()
    write_gif(frames, out)


# ---------------------------------------------------------------- halftonewave
def halftonewave(out):
    """The halftone dot matrix with a slow radial wave travelling outward from
    the mark; the mark itself stays solid."""
    k = W / 2560
    size, cx, cy = 384 * k, 1280 * k, 700 * k
    m = mark_mask(size, cx, cy)
    core = gblur(m, 4 * k)
    near = np.clip(gblur(m, 60 * k) / gblur(m, 60 * k).max() * 3.0, 0, 1)   # 1 around the mark
    env = gblur(m, 300 * k); env /= env.max()
    pitch = 12 * k
    ys = np.arange(pitch / 2, H, pitch); xs = np.arange(pitch / 2, W, pitch)
    gy, gx = np.meshgrid(ys, xs, indexing="ij")
    r = np.sqrt((gx - cx) ** 2 + (gy - cy) ** 2) / (W * 0.5)
    iy, ix = gy.astype(int), gx.astype(int)
    core_s = core[iy, ix] / core.max(); env_s = env[iy, ix]; near_s = near[iy, ix]
    frames = []
    for i in range(FRAMES):
        t = i / FRAMES
        wave = 0.5 + 0.5 * np.cos(2 * math.pi * (r * 3.0 - t))        # 3 crests on screen
        amb = env_s * (0.18 + 0.55 * wave ** 3) * (1 - 0.75 * near_s)
        v = np.clip(np.maximum(core_s * 0.95, amb), 0, 1)
        s = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H); ctx = cairo.Context(s)
        ctx.set_source_rgb(0, 0, 0); ctx.paint()
        for (y, x, val) in zip(gy.ravel(), gx.ravel(), v.ravel()):
            if val < 0.02: continue
            rad = min(pitch * 0.48, 0.6 * k + val ** 0.8 * pitch * 0.5)
            ctx.set_source_rgba(1, 1, 1, min(1.0, 0.25 + val * 1.1))
            ctx.arc(x, y, rad, 0, 2 * math.pi); ctx.fill()
        frames.append(finish(surface_to_array(s)))
        print(f"\rhalftonewave {i + 1}/{FRAMES}", end="", flush=True)
    print()
    write_gif(frames, out)


# ---------------------------------------------------------------- mazetrace
# (maze_grid is copied from scenes.py, which cannot be imported outside Blender)
def maze_grid(cols, rows, seed, hole=None):
    rnd = random.Random(seed)
    h = [[True] * cols for _ in range(rows + 1)]
    v = [[True] * (cols + 1) for _ in range(rows)]
    inhole = lambda c, r: bool(hole) and hole[0] <= c < hole[2] and hole[1] <= r < hole[3]
    seen = [[False] * cols for _ in range(rows)]
    stack = [(0, 0)]; seen[0][0] = True
    while stack:
        c, r = stack[-1]
        nb = [(c+dc, r+dr) for dc, dr in ((1,0),(-1,0),(0,1),(0,-1))
              if 0 <= c+dc < cols and 0 <= r+dr < rows and not seen[r+dr][c+dc] and not inhole(c+dc, r+dr)]
        if not nb: stack.pop(); continue
        nc, nr = rnd.choice(nb)
        if nc != c: v[r][max(c, nc)] = False
        else: h[max(r, nr)][c] = False
        seen[nr][nc] = True; stack.append((nc, nr))
    gc, gr = 2 * cols + 1, 2 * rows + 1
    g = [[False] * gc for _ in range(gr)]
    for r in range(0, gr, 2):
        for c in range(0, gc, 2): g[r][c] = True
    for r in range(rows + 1):
        for c in range(cols):
            if h[r][c]: g[2*r][2*c+1] = True
    for r in range(rows):
        for c in range(cols + 1):
            if v[r][c]: g[2*r+1][2*c] = True
    if hole:  # empty the hole, keep its outline, open one door on each side
        c0, r0, c1, r1 = hole
        for r in range(2*r0 + 1, 2*r1):
            for c in range(2*c0 + 1, 2*c1): g[r][c] = False
        mr, mc = r0 + r1, c0 + c1
        g[mr][2*c0] = g[mr][2*c1] = g[2*r0][mc] = g[2*r1][mc] = False
    return g

def solve(g, start, goal):
    from collections import deque
    prev = {start: None}; q = deque([start])
    while q:
        c = q.popleft()
        if c == goal: break
        x, y = c
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            n = (x + dx, y + dy)
            if 0 <= n[1] < len(g) and 0 <= n[0] < len(g[0]) and not g[n[1]][n[0]] and n not in prev:
                prev[n] = c; q.append(n)
    path = []; c = goal
    while c is not None:
        path.append(c); c = prev[c]
    return path[::-1]

def mazetrace(out):
    """A faint maze covers the screen; a bright comet runs the solution from
    the left edge into the mark, its trail fading behind it."""
    k = W / 2560
    cell = 40 * k
    cols, rows = int(W / cell / 2), int(H / cell / 2)
    # hole in the middle-right for the mark
    hc, hr = 5, 5
    hx0, hy0 = int(cols * 0.66) - hc // 2, rows // 2 - hr // 2
    g = maze_grid(cols, rows, 21, hole=(hx0, hy0, hx0 + hc, hy0 + hr))
    gh, gw = len(g), len(g[0])
    ox = (W - gw * cell) / 2; oy = (H - gh * cell) / 2
    start = (0, 2 * (rows // 2) + 1)
    g[start[1]][0] = False
    goal = (2 * hx0 + hc, 2 * hy0 + hr)              # centre of the hole
    path = solve(g, start, goal)
    pts = [(ox + (x + 0.5) * cell, oy + (y + 0.5) * cell) for x, y in path]
    size = (hc * 2 - 1) * cell * 0.72
    mcx, mcy = pts[-1]
    # static layer: faint walls
    s0 = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H); c0 = cairo.Context(s0)
    c0.set_source_rgb(0, 0, 0); c0.paint()
    c0.set_line_width(1.2 * k); c0.set_line_cap(cairo.LINE_CAP_ROUND)
    for y in range(gh):
        for x in range(gw):
            if g[y][x]:
                cx_, cy_ = ox + (x + 0.5) * cell, oy + (y + 0.5) * cell
                if x + 1 < gw and g[y][x + 1]:
                    c0.move_to(cx_, cy_); c0.line_to(cx_ + cell, cy_)
                if y + 1 < gh and g[y + 1][x]:
                    c0.move_to(cx_, cy_); c0.line_to(cx_, cy_ + cell)
    c0.set_source_rgba(1, 1, 1, 0.26); c0.stroke()
    walls = surface_to_array(s0)
    vig = vignette(1.3, 0.62, 0.5, 0.6, 0.75)
    walls *= vig
    # cumulative arc length along the path
    seg = [0.0]
    for a, b in zip(pts, pts[1:]): seg.append(seg[-1] + math.dist(a, b))
    total = seg[-1]
    def at(dist):
        dist = max(0.0, min(total, dist))
        j = max(0, min(len(seg) - 2, np.searchsorted(seg, dist) - 1))
        u = (dist - seg[j]) / max(seg[j + 1] - seg[j], 1e-6)
        return (pts[j][0] + (pts[j + 1][0] - pts[j][0]) * u, pts[j][1] + (pts[j + 1][1] - pts[j][1]) * u)
    trail = total * 0.35
    run = 0.72                      # fraction of the loop spent travelling; the rest: mark glows, fades
    frames = []
    for i in range(FRAMES):
        t = i / FRAMES
        s = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H); ctx = cairo.Context(s)
        ctx.set_line_cap(cairo.LINE_CAP_ROUND); ctx.set_line_join(cairo.LINE_JOIN_ROUND)
        if t < run:
            ease = 0.5 - 0.5 * math.cos(math.pi * t / run)
            head = ease * total
            glow_mark = 0.0
        else:
            head = total + trail * (t - run) / (1 - run) * 1.2     # trail drains into the mark
            u = (t - run) / (1 - run)
            glow_mark = math.sin(math.pi * u) ** 0.6
        # trail: short segments with alpha rising toward the head
        n = 140
        for j in range(n):
            d0 = head - trail * (1 - j / n); d1 = head - trail * (1 - (j + 1) / n)
            if d1 <= 0 or d0 >= total: continue
            p0, p1 = at(d0), at(d1)
            al = (j / n) ** 2.2
            ctx.set_line_width((2.2 + 1.6 * al) * k)
            ctx.set_source_rgba(1, 1, 1, al * 0.95)
            ctx.move_to(*p0); ctx.line_to(*p1); ctx.stroke()
        if head < total:
            hx, hy = at(head)
            grd = cairo.RadialGradient(hx, hy, 0, hx, hy, 34 * k)
            grd.add_color_stop_rgba(0, 1, 1, 1, 0.9); grd.add_color_stop_rgba(1, 1, 1, 1, 0)
            ctx.set_source(grd); ctx.arc(hx, hy, 34 * k, 0, 2 * math.pi); ctx.fill()
        # the mark: always present, brightens when the comet arrives
        if glow_mark > 0:
            grd = cairo.RadialGradient(mcx, mcy, 0, mcx, mcy, size * 1.1)
            grd.add_color_stop_rgba(0, 1, 1, 1, 0.22 * glow_mark); grd.add_color_stop_rgba(1, 1, 1, 1, 0)
            ctx.set_source(grd); ctx.arc(mcx, mcy, size * 1.1, 0, 2 * math.pi); ctx.fill()
        ctx.set_source_rgba(1, 1, 1, 0.78 + 0.2 * glow_mark)
        for x, y, rw, rh in mark_rects(size, mcx - size / 2, mcy - size / 2):
            ctx.rectangle(x, y, rw, rh)
        ctx.fill()
        a = np.maximum(walls, surface_to_array(s))
        frames.append(finish(a))
        print(f"\rmazetrace {i + 1}/{FRAMES}", end="", flush=True)
    print()
    write_gif(frames, out)


# ---------------------------------------------------------------- assemble
def assemble(out):
    """Dots drift in from a loose field, lock into the mark's dot matrix, hold,
    then drift back out. Positions follow smooth per-dot curves; the loop
    closes because every dot returns to where it started."""
    k = W / 2560
    size, cx, cy = 384 * k, 1280 * k, 700 * k
    m = mark_mask(size, cx, cy)
    pitch = 12 * k
    targets = [(x, y) for y in np.arange(pitch / 2, H, pitch) for x in np.arange(pitch / 2, W, pitch)
               if m[int(y), int(x)] > 0.5]
    rng = np.random.default_rng(9)
    tgt = np.array(targets, np.float32)
    n = len(tgt)
    ang = rng.uniform(0, 2 * math.pi, n)
    rad = rng.uniform(260, 1100, n) * k
    home = tgt + np.stack([np.cos(ang) * rad * 1.6, np.sin(ang) * rad], 1)
    swirl = rng.uniform(-1.2, 1.2, n)
    phase = rng.uniform(0, 0.12, n)                  # dots arrive slightly out of step
    frames = []
    for i in range(FRAMES):
        t = i / FRAMES
        # 0 -> 1 -> 0 over the loop with a long hold at 1
        u = np.clip((0.5 - 0.5 * np.cos(2 * math.pi * (t - phase))) * 1.5 - 0.25, 0, 1)
        u = u * u * (3 - 2 * u)
        a_ = (1 - u) * swirl * 1.4
        vec = home - tgt
        rot = np.stack([vec[:, 0] * np.cos(a_) - vec[:, 1] * np.sin(a_),
                        vec[:, 0] * np.sin(a_) + vec[:, 1] * np.cos(a_)], 1)
        pos = tgt + rot * (1 - u)[:, None]
        s = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H); ctx = cairo.Context(s)
        ctx.set_source_rgb(0, 0, 0); ctx.paint()
        for (x, y), uu in zip(pos, u):
            r = (2.0 + 3.1 * uu) * k
            ctx.set_source_rgba(1, 1, 1, 0.45 + 0.52 * uu)
            ctx.arc(x, y, r, 0, 2 * math.pi); ctx.fill()
        frames.append(finish(surface_to_array(s)))
        print(f"\rassemble {i + 1}/{FRAMES}", end="", flush=True)
    print()
    write_gif(frames, out)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    out = args[0] if args else "."
    os.makedirs(out, exist_ok=True)
    for n in (args[1:] or ["topoflow", "halftonewave", "mazetrace", "assemble"]):
        globals()[n](os.path.join(out, f"maze-{n}.gif"))
