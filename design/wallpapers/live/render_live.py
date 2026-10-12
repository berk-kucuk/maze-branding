#!/usr/bin/env python3
"""Render the live2d.py designs as seamless video loops and install them into
the maze-branding payload as KPackage wallpapers, ready for Maze Wallpaper.

    python3 render_live.py [name ...] [--size 1920x1080] [--fps 30] [--jobs N]

Why video: the com.mazelinux.wallpaper plugin plays H.264 through Qt
Multimedia, which the GPU decodes (VA-API/NVDEC) for almost no CPU, and the
plugin pauses it whenever a window covers the desktop. A GIF is decoded on the
CPU and held in memory frame by frame; built-in QML scenes no longer exist.

Each package:
    usr/share/wallpapers/Maze-<Name>/metadata.json        author "Maze Linux"
    usr/share/wallpapers/Maze-<Name>/contents/images/1920x1080.mp4
    usr/share/wallpapers/Maze-<Name>/contents/screenshot.png
The poster lives outside images/ so the app's package scan picks the video.
"""
import argparse, json, os, subprocess, sys, time
from multiprocessing import Pool

HERE = os.path.dirname(os.path.abspath(__file__))
PAYLOAD = os.path.normpath(os.path.join(HERE, "..", "..", "..", "maze-branding", "usr", "share", "wallpapers"))

ap = argparse.ArgumentParser()
ap.add_argument("names", nargs="*")
ap.add_argument("--size", default="1920x1080")
ap.add_argument("--fps", type=int, default=30)
ap.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) - 2))
ap.add_argument("--crf", type=int, default=20)
args = ap.parse_args()

os.environ["MAZE_LIVE_SIZE"] = args.size
sys.path.insert(0, HERE)
import live2d as L   # reads MAZE_LIVE_SIZE at import

_job = None

def render(i):
    fn, cycles, frames = _job
    t = (i * cycles / frames) % 1.0
    return L.finish(fn(t)).tobytes()

def init(name, cycles, frames):
    global _job
    _job = (L.DESIGNS[name][0], cycles, frames)


# Designs that also ship as a still: the still owns Maze-<Name>, the video
# moves to Maze-<Name>-Live.
HAS_STILL = {"dust"}


def build(name):
    secs, cycles, title = L.LOOPS[name]
    frames = int(round(secs * cycles * args.fps))
    pkg_id = f"Maze-{title}-Live" if name in HAS_STILL else f"Maze-{title}"
    pkg = os.path.join(PAYLOAD, pkg_id)
    img_dir = os.path.join(pkg, "contents", "images")
    os.makedirs(img_dir, exist_ok=True)
    out = os.path.join(img_dir, f"{L.W}x{L.H}.mp4")
    tmp = out + ".part.mp4"
    ff = subprocess.Popen([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{L.W}x{L.H}", "-r", str(args.fps), "-i", "-",
        "-vf", "scale=out_color_matrix=bt709:out_range=tv,format=yuv420p",
        "-c:v", "libx264", "-preset", "slow", "-crf", str(args.crf),
        "-profile:v", "high", "-level", "4.1", "-x264-params", "aq-mode=3",
        "-maxrate", "10M", "-bufsize", "20M", "-g", str(args.fps * 4),
        "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "tv",
        "-an", "-movflags", "+faststart", tmp], stdin=subprocess.PIPE)
    t0 = time.time()
    first = None
    with Pool(args.jobs, initializer=init, initargs=(name, cycles, frames)) as pool:
        for i, buf in enumerate(pool.imap(render, range(frames), chunksize=2)):
            if first is None: first = buf
            ff.stdin.write(buf)
            if i % 60 == 0:
                print(f"  {name}: {i}/{frames}", flush=True)
    ff.stdin.close()
    if ff.wait() != 0:
        raise SystemExit(f"ffmpeg failed for {name}")
    os.replace(tmp, out)
    from PIL import Image
    Image.frombytes("RGB", (L.W, L.H), first).save(os.path.join(pkg, "contents", "screenshot.png"), optimize=True)
    with open(os.path.join(pkg, "metadata.json"), "w") as f:
        json.dump({"KPlugin": {"Authors": [{"Name": "Maze Linux"}], "Id": pkg_id,
                               "License": "CC-BY-SA-4.0", "Name": f"Maze {title} (live)"}}, f, indent=4)
        f.write("\n")
    mb = os.path.getsize(out) / 1e6
    print(f"{name}: {frames} frames ({secs * cycles:g}s), {mb:.1f} MB, {time.time() - t0:.0f}s -> {out}", flush=True)


if __name__ == "__main__":
    for n in args.names or list(L.LOOPS):
        build(n)
