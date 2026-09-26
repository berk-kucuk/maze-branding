import numpy as np
from PIL import Image

def _box1d(a, r, axis):
    if r < 1: return a
    n = a.shape[axis]
    pad = [(0, 0)] * a.ndim; pad[axis] = (r + 1, r)
    p = np.pad(a, pad, mode="edge")
    c = np.cumsum(p, axis=axis, dtype=np.float64)
    hi = np.take(c, np.arange(2*r + 1, 2*r + 1 + n), axis=axis)
    lo = np.take(c, np.arange(0, n), axis=axis)
    return ((hi - lo) / (2*r + 1)).astype(np.float32)

def gblur(a, sigma):
    """Float Gaussian blur (3x box approximation). a: (H,W) or (H,W,C)."""
    if sigma <= 0.3: return a
    scale = 1
    while sigma / scale > 24 and min(a.shape[:2]) / (scale*2) > 64:
        scale *= 2
    src = a
    if scale > 1:
        h, w = a.shape[:2]
        src = _resize(a, w // scale, h // scale)
    s = sigma / scale
    r = max(1, int(round((np.sqrt(12 * s * s / 3 + 1) - 1) / 2)))
    out = src
    for _ in range(3):
        out = _box1d(out, r, 0); out = _box1d(out, r, 1)
    if scale > 1:
        out = _resize(out, a.shape[1], a.shape[0])
    return out

def _resize(a, w, h):
    if a.ndim == 2:
        return np.asarray(Image.fromarray(a.astype(np.float32), "F").resize((w, h), Image.BILINEAR), np.float32)
    return np.stack([_resize(a[..., i], w, h) for i in range(a.shape[2])], -1)
