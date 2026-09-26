#!/usr/bin/env python3
"""Maze Linux animated logos on OLED black — glitch and old-CRT.

    python3 anim.py <out-dir> [glitch|crt ...]

Writes, per animation: <name>.gif (1920x1080, seamless loop, for KDE's image
wallpaper and anywhere a GIF is wanted), <name>.mp4 and <name>.webm.
Frames are generated with numpy; ffmpeg does palette generation for the GIF.
Pixels outside the effects are exactly 0,0,0 in every frame.
"""
import os, shutil, subprocess, sys, tempfile
import numpy as np
from PIL import Image

W, H, FPS = 1920, 1080, 24
SRC = "/run/media/berkkucukk/Backup/Projects/Maze-Linux-Source"
LOGO = os.path.join(SRC, "maze-installer/maze-installer/usr/share/calamares/branding/maze/maze-logo.png")


def logo_canvas(width):
    lg = Image.open(LOGO).convert("RGBA")
    lh = int(lg.height * width / lg.width)
    lg = np.asarray(lg.resize((width, lh), Image.LANCZOS), np.float32) / 255
    c = np.zeros((H, W, 3), np.float32)
    x0, y0 = (W - width) // 2, (H - lh) // 2
    c[y0:y0+lh, x0:x0+width] = lg[..., :3] * lg[..., 3:4]
    return c

def blur(a, s):
    """Cheap separable box-blur x3 (float)."""
    if s < 1: return a
    r = int(s)
    k = np.ones(2 * r + 1, np.float32) / (2 * r + 1)
    out = a
    for _ in range(3):
        out = np.apply_along_axis(lambda v: np.convolve(v, k, "same"), 1, out) if out.ndim == 2 else \
              np.stack([np.apply_along_axis(lambda v: np.convolve(v, k, "same"), 1, out[..., i]) for i in range(3)], -1)
        out = np.apply_along_axis(lambda v: np.convolve(v, k, "same"), 0, out) if out.ndim == 2 else \
              np.stack([np.apply_along_axis(lambda v: np.convolve(v, k, "same"), 0, out[..., i]) for i in range(3)], -1)
    return out

def glow_of(img, sigma):
    """Bloom via downscale -> upscale (fast, soft)."""
    im = Image.fromarray(np.clip(img * 255, 0, 255).astype(np.uint8))
    f = max(2, int(sigma))
    small = im.resize((W // f, H // f), Image.BILINEAR).resize((W // (f*2), H // (f*2)), Image.BILINEAR)
    return np.asarray(small.resize((W, H), Image.BICUBIC), np.float32) / 255

def shift(a, dx, dy=0):
    out = np.zeros_like(a)
    xs, xd = (slice(max(0, -dx), W - max(0, dx)), slice(max(0, dx), W - max(0, -dx)))
    ys, yd = (slice(max(0, -dy), H - max(0, dy)), slice(max(0, dy), H - max(0, -dy)))
    out[yd, xd] = a[ys, xs]
    return out


# ------------------------------------------------------------------ glitch
def glitch_frames(n=96):
    rng = np.random.default_rng(3)
    base = logo_canvas(620)
    halo = glow_of(base, 18) * 0.35
    bursts = {range(18, 25), range(40, 43), range(62, 71), range(84, 86)}
    frames = []
    for i in range(n):
        f = base + halo
        live = any(i in b for b in bursts)
        # tiny breathing so the still parts are not dead
        f = f * (0.96 + 0.04 * np.sin(i / n * 2 * np.pi))
        if live:
            k = rng.uniform(0.4, 1.0)
            dx = int(rng.integers(8, 34) * k)
            r = shift(f[..., 0], -dx); g = f[..., 1]; b = shift(f[..., 2], dx, int(rng.integers(-3, 4)))
            f = np.stack([r, g, b], -1)
            # horizontal slices torn sideways
            for _ in range(int(rng.integers(4, 12))):
                y0 = int(rng.integers(H * 0.25, H * 0.75)); hh = int(rng.integers(4, 46))
                off = int(rng.integers(-160, 160))
                f[y0:y0+hh] = np.roll(f[y0:y0+hh], off, axis=1)
            # block corruption: copy a chunk of the logo elsewhere
            for _ in range(int(rng.integers(1, 4))):
                bw, bh = int(rng.integers(60, 260)), int(rng.integers(10, 60))
                sx, sy = int(rng.integers(W*0.3, W*0.7 - bw)), int(rng.integers(H*0.35, H*0.65 - bh))
                tx, ty = sx + int(rng.integers(-220, 220)), sy + int(rng.integers(-40, 40))
                tx = int(np.clip(tx, 0, W - bw)); ty = int(np.clip(ty, 0, H - bh))
                f[ty:ty+bh, tx:tx+bw] = np.maximum(f[ty:ty+bh, tx:tx+bw], f[sy:sy+bh, sx:sx+bw] * rng.uniform(0.6, 1.2))
            # a few bright scan lines
            for _ in range(int(rng.integers(1, 5))):
                y = int(rng.integers(H * 0.2, H * 0.8))
                x0 = int(rng.integers(0, W // 2)); x1 = x0 + int(rng.integers(200, 900))
                f[y:y+2, x0:x1] += rng.uniform(0.15, 0.5)
        frames.append(np.clip(f, 0, 1))
    return frames


# ------------------------------------------------------------------ crt
def crt_frames(n=120):
    rng = np.random.default_rng(11)
    base = logo_canvas(640)
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    # barrel distortion map (applied to the logo layer)
    nx, ny = (xx - W/2) / (W/2), (yy - H/2) / (H/2)
    r2 = nx**2 + ny**2
    k = 0.06
    sx = (nx * (1 + k * r2)) * (W/2) + W/2; sy = (ny * (1 + k * r2)) * (H/2) + H/2
    sxi = np.clip(sx, 0, W-1).astype(np.int32); syi = np.clip(sy, 0, H-1).astype(np.int32)
    inside = ((sx >= 0) & (sx < W) & (sy >= 0) & (sy < H)).astype(np.float32)
    scan = (0.62 + 0.38 * (np.sin(yy * np.pi / 2.0) ** 2))[..., None]     # 4 px scanline period
    vign = np.clip(1 - (r2 / 1.9) ** 1.6, 0, 1)[..., None]
    frames = []
    for i in range(n):
        t = i / n
        img = base.copy()
        # chromatic aberration grows towards the edges
        img = np.stack([shift(img[..., 0], -3), img[..., 1], shift(img[..., 2], 3)], -1)
        # line jitter
        if rng.random() < 0.25:
            y0 = int(rng.integers(0, H - 80)); img[y0:y0+80] = np.roll(img[y0:y0+80], int(rng.integers(-6, 7)), axis=1)
        img = img[syi, sxi] * inside[..., None]
        g = glow_of(img, 10) * 0.55 + glow_of(img, 30) * 0.25          # phosphor glow
        f = (img * scan + g) * vign
        # rolling brighter band
        band_y = ((t * 2.0) % 1.0) * (H + 300) - 150          # exactly 2 passes per loop
        band = np.exp(-((yy - band_y) / 70) ** 2)[..., None]
        f = f * (1 + 0.35 * band)
        # (no global flicker: it rewrites every lit pixel each frame and made the
        # GIF ~11 MB; the rolling band and line jitter carry the motion)
        # (no power-on effect: as a live wallpaper the loop point must be
        # invisible, and a black first frame after a lit last one is a cut)
        # static burst near the end of the loop
        # (coarse 2x2 grain: looks more like analogue snow, and a GIF can
        # still compress it — per-pixel noise made each frame ~2 MB)
        if 100 <= i < 103:
            s = rng.random((H // 2, W // 2, 1)).astype(np.float32)
            s = np.repeat(np.repeat(s, 2, 0), 2, 1) * 0.30 * vign
            f = np.clip(f * 0.6 + s * scan, 0, 1)
        frames.append(np.clip(f, 0, 1))
    return frames



# ------------------------------------------------------------------ shine
def shine_frames(n=96):
    """A metallic light sweep across the logo; starts and ends off-logo."""
    base = logo_canvas(640)
    lum = base.max(axis=2)
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    halo = glow_of(base, 16) * 0.28
    x0, x1 = (W - 640) / 2 - 500, (W + 640) / 2 + 500
    frames = []
    for i in range(n):
        ph = i / n
        # sweep occupies the first 45 % of the loop, the rest is still
        u = min(ph / 0.45, 1.0)
        e = 0.5 - 0.5 * np.cos(u * np.pi)              # ease in-out
        cx = x0 + (x1 - x0) * e
        d = (xx - cx) + (yy - H / 2) * 0.55             # diagonal band
        band = (np.exp(-(d / 55) ** 2) + 0.35 * np.exp(-(d / 160) ** 2)) * (0.0 if u >= 1.0 else 1.0)
        spec = np.repeat((lum * band * 2.2)[..., None], 3, axis=2)
        f = base * 0.72 + halo + spec
        g = glow_of(np.clip(spec, 0, 1), 10) * 0.9 + glow_of(np.clip(spec, 0, 1), 28) * 0.5
        f = f + g * np.array([0.85, 0.92, 1.0], np.float32)
        frames.append(np.clip(f, 0, 1))
    return frames


# ------------------------------------------------------------------ runner
def runner_frames(n=192, cols=28, rows=16, seed=5, runners=5):
    """Lights travelling round closed circuits of a faint maze. Each runner
    does exactly one lap per loop, so the loop has no seam."""
    import random
    from collections import deque
    rnd = random.Random(seed)
    hw = np.ones((rows + 1, cols), bool); vw = np.ones((rows, cols + 1), bool)
    seen = np.zeros((rows, cols), bool); st = [(0, 0)]; seen[0, 0] = True
    while st:
        c, r = st[-1]
        nb = [(c+dc, r+dr) for dc, dr in ((1,0),(-1,0),(0,1),(0,-1))
              if 0 <= c+dc < cols and 0 <= r+dr < rows and not seen[r+dr, c+dc]]
        if not nb: st.pop(); continue
        nc, nr = rnd.choice(nb)
        if nc != c: vw[r, max(c, nc)] = False
        else: hw[max(r, nr), c] = False
        seen[nr, nc] = True; st.append((nc, nr))
    def open_nb(c, r):
        out = []
        if c + 1 < cols and not vw[r, c+1]: out.append((c+1, r))
        if c > 0 and not vw[r, c]: out.append((c-1, r))
        if r + 1 < rows and not hw[r+1, c]: out.append((c, r+1))
        if r > 0 and not hw[r, c]: out.append((c, r-1))
        return out
    def tree_path(a, b):
        prev = {a: None}; q = deque([a])
        while q:
            x = q.popleft()
            if x == b: break
            for y in open_nb(*x):
                if y not in prev: prev[y] = x; q.append(y)
        p = [b]
        while prev[p[-1]] is not None: p.append(prev[p[-1]])
        return p[::-1]
    # carve circuits: knock out a wall between two cells whose tree path is long
    circuits = []
    tries = 0
    while len(circuits) < runners and tries < 20000:
        tries += 1
        c, r = rnd.randrange(cols - 1), rnd.randrange(rows)
        if not vw[r, c+1]: continue
        path = tree_path((c, r), (c+1, r))
        if not (26 <= len(path) <= 80): continue
        used = {x for cc in circuits for x in cc}
        if used & set(path): continue          # circuits never share a cell
        vw[r, c+1] = False
        circuits.append(path)             # path ... then the new door back to start
    print(f"runner: {len(circuits)} circuits, lengths {[len(c) for c in circuits]}")
    cs = min(W // (cols + 1), H // (rows + 1))
    ox, oy = (W - cols * cs) // 2, (H - rows * cs) // 2
    # faint walls
    from PIL import ImageDraw
    im = Image.new("L", (W, H), 0); d = ImageDraw.Draw(im)
    for r in range(rows + 1):
        for c in range(cols):
            if hw[r, c]: d.line((ox + c*cs, oy + r*cs, ox + (c+1)*cs, oy + r*cs), fill=255, width=2)
    for r in range(rows):
        for c in range(cols + 1):
            if vw[r, c]: d.line((ox + c*cs, oy + r*cs, ox + c*cs, oy + (r+1)*cs), fill=255, width=2)
    walls = np.asarray(im, np.float32) / 255
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    vign = np.clip(1 - (((xx - W/2) / (W*0.62)) ** 2 + ((yy - H/2) / (H*0.75)) ** 2), 0, 1)
    walls_l = (walls * 0.10 * vign)[..., None] * np.array([0.9, 0.92, 1.0], np.float32)
    logo = logo_canvas(420)
    def centre(cell):
        return ox + (cell[0] + 0.5) * cs, oy + (cell[1] + 0.5) * cs
    frames = []
    for i in range(n):
        lights = Image.new("L", (W, H), 0); dl = ImageDraw.Draw(lights)
        for k, path in enumerate(circuits):
            loop = path + [path[0]]
            L = len(path)
            head = ((i / n) + k / len(circuits)) % 1.0 * L       # one lap per loop
            def at(s_):
                s_ %= L; a = min(int(s_), L - 1); fr = s_ - a    # float % can return L
                (x1, y1), (x2, y2) = centre(loop[a]), centre(loop[a + 1])
                return x1 + (x2 - x1) * fr, y1 + (y2 - y1) * fr
            steps = 90                                          # continuous trail, 6 cells long
            pts = [at(head - j * 6.0 / steps) for j in range(steps + 1)]
            for j in range(steps, 0, -1):                       # tail first, head on top
                t_ = 1 - j / steps
                dl.line((pts[j], pts[j - 1]), fill=int(255 * t_ ** 1.8), width=max(1, int(1 + 5 * t_)))
            hx, hy = pts[0]
            dl.ellipse((hx - 6, hy - 6, hx + 6, hy + 6), fill=255)
        lt = np.asarray(lights, np.float32) / 255
        glow = glow_of(np.stack([lt] * 3, -1), 8) * 0.9 + glow_of(np.stack([lt] * 3, -1), 24) * 0.5
        f = walls_l + lt[..., None] * np.array([0.92, 0.96, 1.0], np.float32) + glow * np.array([0.7, 0.82, 1.0], np.float32)
        f = np.maximum(f, logo * 0.92)
        frames.append(np.clip(f, 0, 1))
    return frames


def loop_check(frames, name):
    """The seam (last->first) must look like any other frame step."""
    diffs = [np.abs(frames[i+1] - frames[i]).mean() for i in range(len(frames) - 1)]
    seam = np.abs(frames[0] - frames[-1]).mean()
    typical = float(np.percentile(diffs, 90)) if diffs else 0
    ok = seam <= max(typical * 1.25, 1e-4)
    print(f"{name}: loop seam {seam:.5f} vs 90th-pct step {typical:.5f} -> {'SEAMLESS' if ok else 'CUT!'}")
    if not ok:
        raise SystemExit(f"{name}: the loop has a visible cut")

# ------------------------------------------------------------------ output
def encode(frames, name, out):
    loop_check(frames, name)
    tmp = tempfile.mkdtemp(prefix="mazeanim-", dir=out)
    for i, f in enumerate(frames):
        Image.fromarray((f * 255 + 0.5).astype(np.uint8)).save(os.path.join(tmp, f"f{i:04d}.png"))
    pat = os.path.join(tmp, "f%04d.png")
    run = lambda *a: subprocess.run(["ffmpeg", "-v", "error", "-y", *a], check=True)
    pal = os.path.join(tmp, "pal.png")
    run("-framerate", str(FPS), "-i", pat, "-vf", "palettegen=max_colors=256:stats_mode=full:reserve_transparent=0", pal)
    run("-framerate", str(FPS), "-i", pat, "-i", pal, "-lavfi",
        "paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle", "-loop", "0", os.path.join(out, f"{name}.gif"))
    run("-framerate", str(FPS), "-i", pat, "-c:v", "libx264", "-crf", "16", "-preset", "slow",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart", os.path.join(out, f"{name}.mp4"))
    run("-framerate", str(FPS), "-i", pat, "-c:v", "libvpx-vp9", "-crf", "24", "-b:v", "0",
        "-pix_fmt", "yuv420p", os.path.join(out, f"{name}.webm"))
    # contact frames for review
    for j in (0, len(frames) // 4, len(frames) // 2, 3 * len(frames) // 4):
        shutil.copy(os.path.join(tmp, f"f{j:04d}.png"), os.path.join(out, f"{name}-frame{j:03d}.png"))
    shutil.rmtree(tmp)
    blk = np.mean([(f.max(axis=2) == 0).mean() for f in frames]) * 100
    print(f"{name}: {len(frames)} frames, avg true-black {blk:.0f}%")


if __name__ == "__main__":
    out = sys.argv[1]; os.makedirs(out, exist_ok=True)
    want = sys.argv[2:] or ["glitch", "crt", "shine", "runner"]
    if "glitch" in want: encode(glitch_frames(), "maze-glitch", out)
    if "crt" in want: encode(crt_frames(), "maze-crt", out)
    if "shine" in want: encode(shine_frames(), "maze-shine", out)
    if "runner" in want: encode(runner_frames(), "maze-runner", out)
