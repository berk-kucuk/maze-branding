#!/usr/bin/env python3
"""Maze Linux — graphic monochrome wallpapers (2D, vector-drawn with cairo).

    python3 graphic2d.py <out-dir> [blueprint|ascii|ridges|isometric ...]

blueprint  the mark as a brand construction sheet: grid, circles, dimensions
ascii      the mark emerging from a field of monospace characters
ridges     stacked horizontal lines that rise over the mark (hidden-line relief)
isometric  the mark as an isometric block drawn in white line, on a dot floor
"""
import json, math, os, sys
import numpy as np
import cairo
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lines2d import mark_rects, mark_mask, gblur, smooth_noise, GRID, W, H

SANS = "Inter"
MONO = "Hack"


def new_surface():
    s = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H); ctx = cairo.Context(s)
    ctx.set_source_rgb(0, 0, 0); ctx.paint()
    return s, ctx

def save(s, out):
    a = np.ndarray((H, s.get_stride() // 4, 4), np.uint8, s.get_data())[:, :W, 1].astype(np.float32)
    a = np.clip((a - 1.5) * 255 / 253.5, 0, 255)
    n = np.random.default_rng(1).normal(0, 1.0, a.shape).astype(np.float32)
    a = np.clip(np.round(a + n * np.clip(a / 255 * 30, 0, 1)), 0, 255).astype(np.uint8)
    Image.fromarray(a, "L").convert("RGB").save(out, optimize=True)
    print(f"{os.path.basename(out)}: true-black {100 * (a == 0).mean():.0f}%")

def text(ctx, s, x, y, size, alpha=0.6, font=SANS, weight=cairo.FONT_WEIGHT_NORMAL, spacing=0.0, anchor="left"):
    ctx.select_font_face(font, cairo.FONT_SLANT_NORMAL, weight)
    ctx.set_font_size(size)
    ctx.set_source_rgba(1, 1, 1, alpha)
    if spacing == 0:
        ext = ctx.text_extents(s)
        if anchor == "right": x -= ext.x_advance
        elif anchor == "center": x -= ext.x_advance / 2
        ctx.move_to(x, y); ctx.show_text(s)
        return
    widths = [ctx.text_extents(ch).x_advance + spacing for ch in s]
    total = sum(widths) - spacing
    if anchor == "right": x -= total
    elif anchor == "center": x -= total / 2
    for ch, wch in zip(s, widths):
        ctx.move_to(x, y); ctx.show_text(ch); x += wch

def fill_mark(ctx, size, x0, y0, alpha=1.0):
    ctx.set_source_rgba(1, 1, 1, alpha)
    for x, y, rw, rh in mark_rects(size, x0, y0):
        ctx.rectangle(x, y, rw, rh)
    ctx.fill()


# ---------------------------------------------------------------- blueprint
def blueprint(out):
    s, ctx = new_surface()
    size = 440; cx, cy = 1720, 720
    x0, y0 = cx - size / 2, cy - size / 2
    e = GRID["edges"]; span = e[-1] - e[0]
    # background grid, fading out from the mark
    for step, al in ((40, 0.045), (200, 0.08)):
        for x in np.arange(cx % step, W, step):
            f = math.exp(-((x - cx) / 1300) ** 2)
            ctx.set_source_rgba(1, 1, 1, al * f); ctx.set_line_width(1)
            ctx.move_to(x + 0.5, 0); ctx.line_to(x + 0.5, H); ctx.stroke()
        for y in np.arange(cy % step, H, step):
            f = math.exp(-((y - cy) / 900) ** 2)
            ctx.set_source_rgba(1, 1, 1, al * f)
            ctx.move_to(0, y + 0.5); ctx.line_to(W, y + 0.5); ctx.stroke()
    # construction: the mark's own grid lines extended past the box
    ctx.set_line_width(1)
    for v in e:
        p = (v - e[0]) / span * size
        ctx.set_source_rgba(1, 1, 1, 0.13)
        ctx.move_to(x0 + p + 0.5, y0 - 90); ctx.line_to(x0 + p + 0.5, y0 + size + 90); ctx.stroke()
        ctx.move_to(x0 - 90, y0 + p + 0.5); ctx.line_to(x0 + size + 90, y0 + p + 0.5); ctx.stroke()
    # circles and diagonals
    ctx.set_source_rgba(1, 1, 1, 0.22)
    for r in (size / 2, size / 2 * math.sqrt(2), size * 0.2):
        ctx.arc(cx, cy, r, 0, 2 * math.pi); ctx.stroke()
    ctx.set_dash([6, 6])
    ctx.move_to(x0 - 60, y0 - 60); ctx.line_to(x0 + size + 60, y0 + size + 60); ctx.stroke()
    ctx.move_to(x0 + size + 60, y0 - 60); ctx.line_to(x0 - 60, y0 + size + 60); ctx.stroke()
    ctx.set_dash([])
    # the mark
    fill_mark(ctx, size, x0, y0, 0.95)
    # dimension lines
    def dim_h(xa, xb, y, label):
        ctx.set_source_rgba(1, 1, 1, 0.5); ctx.set_line_width(1)
        ctx.move_to(xa, y); ctx.line_to(xb, y); ctx.stroke()
        for xx in (xa, xb):
            ctx.move_to(xx, y - 8); ctx.line_to(xx, y + 8); ctx.stroke()
        text(ctx, label, (xa + xb) / 2, y - 14, 15, 0.7, MONO, anchor="center")
    def dim_v(ya, yb, x, label):
        ctx.set_source_rgba(1, 1, 1, 0.5); ctx.set_line_width(1)
        ctx.move_to(x, ya); ctx.line_to(x, yb); ctx.stroke()
        for yy in (ya, yb):
            ctx.move_to(x - 8, yy); ctx.line_to(x + 8, yy); ctx.stroke()
        ctx.save(); ctx.translate(x + 26, (ya + yb) / 2); ctx.rotate(math.pi / 2)
        text(ctx, label, 0, 0, 15, 0.7, MONO, anchor="center"); ctx.restore()
    dim_h(x0, x0 + size, y0 + size + 130, "15 u")
    dim_v(y0, y0 + size, x0 + size + 130, "15 u")
    unit = (e[1] - e[0]) / span * size
    dim_h(x0, x0 + unit, y0 - 120, "1 u")
    # corner crop marks
    ctx.set_source_rgba(1, 1, 1, 0.45)
    for (px, py, dx, dy) in ((120, 120, 1, 1), (W - 120, 120, -1, 1), (120, H - 120, 1, -1), (W - 120, H - 120, -1, -1)):
        ctx.move_to(px, py); ctx.line_to(px + 36 * dx, py); ctx.stroke()
        ctx.move_to(px, py); ctx.line_to(px, py + 36 * dy); ctx.stroke()
    # type
    text(ctx, "MAZE LINUX", 180, 214, 34, 0.95, SANS, cairo.FONT_WEIGHT_BOLD, spacing=6)
    text(ctx, "MARK — CONSTRUCTION", 180, 254, 15, 0.55, MONO, spacing=2)
    for i, line in enumerate(("GRID        15 × 15", "RATIO       1 : 1", "STROKE      1 u", "CLEARANCE   2 u")):
        text(ctx, line, 180, H - 290 + i * 30, 15, 0.5, MONO)
    text(ctx, "01", W - 180, 214, 15, 0.5, MONO, anchor="right")
    save(s, out)


# ---------------------------------------------------------------- ascii
def ascii_(out):
    s, ctx = new_surface()
    fs = 15
    ctx.select_font_face(MONO, cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL); ctx.set_font_size(fs)
    cw = ctx.text_extents("M").x_advance; ch = fs * 1.22
    size, cx, cy = 480, 1280, 700
    m = mark_mask(size, cx, cy)
    glow = gblur(m, 220); glow /= glow.max()
    nz = smooth_noise(4, 90)
    field = np.clip(gblur(m, 2) * 1.0, 0, 1)
    ramp = " .:-=+*#%@"
    rng = np.random.default_rng(2)
    cols, rows = int(W / cw), int(H / ch)
    ox = (W - cols * cw) / 2
    for r in range(rows):
        y = (r + 0.8) * ch
        for c in range(cols):
            x = ox + c * cw
            px, py = int(min(W - 1, x + cw / 2)), int(min(H - 1, y - fs * 0.35))
            v = field[py, px]
            if v > 0.5:
                chs = "@#%&$"[rng.integers(5)]; al = 0.95
            else:
                g = glow[py, px] * (0.55 + 0.9 * (nz[py, px] - 0.5))
                if g < 0.08 or rng.random() > 0.05 + g * 0.45: continue
                idx = int(np.clip(g * 1.2, 0, 0.99) * 5) + 1          # only the light end of the ramp
                chs = ramp[min(idx, len(ramp) - 1)]; al = min(0.4, 0.08 + g * 0.35)
            ctx.set_source_rgba(1, 1, 1, al)
            ctx.move_to(x, y); ctx.show_text(chs)
    text(ctx, "maze@linux", 120, H - 110, 17, 0.75, MONO)
    text(ctx, "~ $ ", 232, H - 110, 17, 0.45, MONO)
    ctx.set_source_rgba(1, 1, 1, 0.75); ctx.rectangle(270, H - 124, 9, 18); ctx.fill()
    save(s, out)


# ---------------------------------------------------------------- ridges
def ridges(out):
    """Unknown-Pleasures style: lines drawn back to front, each one filled black
    underneath so nearer lines hide farther ones."""
    s, ctx = new_surface()
    size, cx, cy = 400, 1280, 760
    m = mark_mask(size, cx, cy)
    plateau = gblur(m, 3)
    nz = smooth_noise(12, 60) - 0.5
    near = np.clip(gblur(m, 50) / gblur(m, 50).max() * 2.5, 0, 1)
    x0, x1 = 360, W - 360
    xs = np.arange(x0, x1 + 1, 3)
    spacing = 8
    y_top, y_bot = 330, 1180
    ctx.set_line_join(cairo.LINE_JOIN_ROUND)
    for yb in np.arange(y_top, y_bot, spacing):
        env = np.exp(-((xs - cx) / 620.0) ** 2)                 # lines calm toward the ends
        ys = []
        for x, en in zip(xs, env):
            iy = int(min(H - 1, max(0, yb)))
            lift = plateau[iy, int(x)] * 46 + nz[iy, int(x)] * 42 * en * (1 - near[iy, int(x)])
            ys.append(yb - max(0.0, lift))
        ctx.move_to(xs[0], ys[0])
        for x, y in zip(xs[1:], ys[1:]): ctx.line_to(x, y)
        path = ctx.copy_path()
        ctx.line_to(xs[-1], H); ctx.line_to(xs[0], H); ctx.close_path()
        ctx.set_source_rgb(0, 0, 0); ctx.fill()
        ctx.append_path(path)
        depth = (yb - y_top) / (y_bot - y_top)
        ctx.set_source_rgba(1, 1, 1, 0.3 + 0.6 * depth); ctx.set_line_width(1.3)
        ctx.stroke()
    text(ctx, "MAZE LINUX", W / 2, 1300, 22, 0.8, SANS, cairo.FONT_WEIGHT_BOLD, spacing=8, anchor="center")
    save(s, out)


# ---------------------------------------------------------------- isometric
def isometric(out):
    """The mark extruded into an isometric block, drawn as white edges on black
    faces (painter's order), sitting on a floor of dots."""
    s, ctx = new_surface()
    g = GRID["grid"]; e = GRID["edges"]; span = e[-1] - e[0]
    U = 36.0                                   # one grid unit in px
    Z = 2.2 * U                                # block height
    cx, cy = 1560, 860
    c30, s30 = math.cos(math.radians(30)), math.sin(math.radians(30))
    def P(x, y, z):                            # grid coords -> screen
        return (cx + (x - y) * c30 * U, cy + (x + y) * s30 * U - z)
    n = len(g)
    ev = [(v - e[0]) / span * n for v in e]    # the mark's real (uneven) edges in grid units
    # floor dots
    for i in range(-18, n + 19):
        for j in range(-18, n + 19):
            px, py = P(i, j, 0)
            d = math.hypot(i - n / 2, j - n / 2)
            al = 0.4 * math.exp(-(d / 14) ** 2)
            if al < 0.02: continue
            ctx.set_source_rgba(1, 1, 1, al); ctx.arc(px, py, 1.6, 0, 2 * math.pi); ctx.fill()
    filled = lambda r, c: 0 <= r < n and 0 <= c < n and g[r][c]
    cells = sorted(((r, c) for r in range(n) for c in range(n) if g[r][c]), key=lambda rc: rc[0] + rc[1])
    ctx.set_line_width(1.5); ctx.set_line_join(cairo.LINE_JOIN_MITER)
    def poly(pts, fill, edges):
        ctx.move_to(*pts[0])
        for p in pts[1:]: ctx.line_to(*p)
        ctx.close_path(); ctx.set_source_rgb(*fill); ctx.fill()
        ctx.set_source_rgba(1, 1, 1, 0.9)
        for a, b in edges:
            ctx.move_to(*pts[a]); ctx.line_to(*pts[b]); ctx.stroke()
    for r, c in cells:
        xa, xb, ya, yb = ev[c], ev[c + 1], ev[r], ev[r + 1]
        # visible side faces: +y (front-left) and +x (front-right), only where open
        if not filled(r + 1, c):
            pts = [P(xa, yb, 0), P(xb, yb, 0), P(xb, yb, Z), P(xa, yb, Z)]
            poly(pts, (0.02, 0.02, 0.02), [(0, 1)] + ([(0, 3)] if not filled(r, c - 1) else []))
        if not filled(r, c + 1):
            pts = [P(xb, ya, 0), P(xb, yb, 0), P(xb, yb, Z), P(xb, ya, Z)]
            poly(pts, (0.05, 0.05, 0.05), [(0, 1)] + ([(1, 2)] if not filled(r + 1, c) else []))
        top = [P(xa, ya, Z), P(xb, ya, Z), P(xb, yb, Z), P(xa, yb, Z)]
        edges = []
        if not filled(r - 1, c): edges.append((0, 1))
        if not filled(r, c + 1): edges.append((1, 2))
        if not filled(r + 1, c): edges.append((2, 3))
        if not filled(r, c - 1): edges.append((3, 0))
        poly(top, (0.0, 0.0, 0.0), edges)
    text(ctx, "MAZE LINUX", 180, H - 200, 30, 0.95, SANS, cairo.FONT_WEIGHT_BOLD, spacing=6)
    text(ctx, "ISO / 30°", 180, H - 162, 15, 0.5, MONO, spacing=2)
    save(s, out)


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "."
    os.makedirs(out, exist_ok=True)
    table = {"blueprint": blueprint, "ascii": ascii_, "ridges": ridges, "isometric": isometric}
    for n in (sys.argv[2:] or list(table)):
        table[n](os.path.join(out, f"maze-{n}.png"))
