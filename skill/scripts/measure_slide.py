"""Measure geometry, colour and text metrics from a slide raster.

Everything is reported in PERCENT of the slide so it can be fed straight into
pptx_helpers.  Designed for a 3840x2160 render of a 16:9 slide, but any size
works because all outputs are percentages.

Typical loop
------------
    from measure_slide import load, edges_row, edges_col, text_rows, ink_bbox, calibrate_font
    a, W, H = load("slide_full.png")
    print(edges_col(a, 45, 10, 97))     # horizontal card edges down one clean column
    print(edges_row(a, 20, 0, 100))     # vertical card edges across one clean row
    print(text_rows(a, 19.5, 45, 14, 83))   # text line bands -> ink centres
    print(ink_bbox(a, 20, 40, 23.0, 25.4))  # exact ink box for one string
    print(calibrate_font("Fully managed", "SourceSans3-Regular.ttf", 261))  # -> pt
"""
import json
import os

import numpy as np
from PIL import Image, ImageFont

FONT_DIR = os.environ.get("OD_FONT_DIR") or os.path.expanduser("~/Library/Fonts")


# --------------------------------------------------------------------------- #
def load(path):
    a = np.asarray(Image.open(path).convert("RGB")).astype(int)
    return a, a.shape[1], a.shape[0]


def hexs(c):
    return "#%02x%02x%02x" % tuple(int(v) for v in c)


def avg_color(a, x0, x1, y0, y1):
    H, W, _ = a.shape
    reg = a[int(y0 / 100 * H):int(y1 / 100 * H), int(x0 / 100 * W):int(x1 / 100 * W)]
    return tuple(int(v) for v in reg.reshape(-1, 3).mean(axis=0))


# --------------------------------------------------------------------------- #
# edges (card / panel / divider boundaries)
# --------------------------------------------------------------------------- #
def edges_col(a, xp, y0, y1, thr=14):
    """Scan a column, return [(y%, '#hex'), ...] wherever colour jumps."""
    H, W, _ = a.shape
    x = int(xp / 100 * W)
    out, prev = [], None
    for y in range(int(y0 / 100 * H), int(y1 / 100 * H)):
        c = tuple(a[y, x])
        if prev is None or sum(abs(c[i] - prev[i]) for i in range(3)) > thr:
            out.append((round(y / H * 100, 2), hexs(c)))
        prev = c
    return out


def edges_row(a, yp, x0, x1, thr=14):
    H, W, _ = a.shape
    y = int(yp / 100 * H)
    out, prev = [], None
    for x in range(int(x0 / 100 * W), int(x1 / 100 * W)):
        c = tuple(a[y, x])
        if prev is None or sum(abs(c[i] - prev[i]) for i in range(3)) > thr:
            out.append((round(x / W * 100, 2), hexs(c)))
        prev = c
    return out


# --------------------------------------------------------------------------- #
# text line bands (fast way to get every row's ink centre)
# --------------------------------------------------------------------------- #
def text_rows(a, x0, x1, y0, y1, thr=140, min_px=2):
    """Return [(y0%, y1%, height%), ...] of bright-text bands in a region."""
    H, W, _ = a.shape
    X0, X1 = int(x0 / 100 * W), int(x1 / 100 * W)
    Y0, Y1 = int(y0 / 100 * H), int(y1 / 100 * H)
    reg = a[Y0:Y1, X0:X1].max(axis=2)
    rows = (reg > thr).sum(axis=1)
    runs, inr, st = [], False, 0
    for i, v in enumerate(rows):
        y = (Y0 + i) / H * 100
        if v > min_px and not inr:
            st, inr = y, True
        if v <= min_px and inr:
            runs.append((round(st, 2), round(y, 2), round(y - st, 2)))
            inr = False
    if inr:
        runs.append((round(st, 2), round((Y0 + len(rows)) / H * 100, 2), 0))
    return runs


# --------------------------------------------------------------------------- #
# exact ink box for one string (use after text_rows)
# --------------------------------------------------------------------------- #
def mask_bright(a, thr=115):
    return a.max(axis=2) > thr


def mask_white(a, thr=150):
    return (a[:, :, 0] > thr) & (a[:, :, 1] > thr) & (a[:, :, 2] > thr)


def mask_muted(a):
    """Grey-ish secondary text (neither white nor background)."""
    R, G, B = a[:, :, 0], a[:, :, 1], a[:, :, 2]
    return (R > 95) & (R < 215) & (G > 95) & (B > 95) & (abs(R - B) < 50) & (abs(R - G) < 35)


def mask_blue(a, d=45, floor=110):
    return (a[:, :, 2] > a[:, :, 0] + d) & (a[:, :, 2] > floor)


def mask_green(a):
    return (a[:, :, 1] > a[:, :, 0] + 25) & (a[:, :, 1] > a[:, :, 2] + 15) & (a[:, :, 1] > 80)


def ink_bbox(a, x0, x1, y0, y1, mask=None, thr=115):
    """Exact ink bounding box of whatever mask fires inside the region."""
    H, W, _ = a.shape
    m = mask if mask is not None else mask_bright(a, thr)
    X0, X1 = int(x0 / 100 * W), int(x1 / 100 * W)
    Y0, Y1 = int(y0 / 100 * H), int(y1 / 100 * H)
    sub = m[Y0:Y1, X0:X1]
    ys, xs = np.where(sub)
    if len(xs) == 0:
        return None
    return (round((X0 + xs.min()) / W * 100, 2), round((X0 + xs.max()) / W * 100, 2),
            round((Y0 + ys.min()) / H * 100, 2), round((Y0 + ys.max()) / H * 100, 2),
            int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1))


# --------------------------------------------------------------------------- #
# coloured blobs (icons, dashes, accents)
# --------------------------------------------------------------------------- #
def components(a, x0, x1, y0, y1, mask_fn=None, thr=70, min_area=40):
    """Connected components inside a region -> [(area, x0%, x1%, y0%, y1%), ...]

    mask_fn: any of the mask_* helpers (they are element-wise, so passing the
    cropped region is fine), or None for "brighter than thr".
    """
    from scipy import ndimage
    H, W, _ = a.shape
    X0, X1 = int(x0 / 100 * W), int(x1 / 100 * W)
    Y0, Y1 = int(y0 / 100 * H), int(y1 / 100 * H)
    reg = a[Y0:Y1, X0:X1]
    m = (reg.max(axis=2) > thr) if mask_fn is None else mask_fn(reg)
    lab, _ = ndimage.label(m, structure=np.ones((3, 3)))
    out = []
    for i, sl in enumerate(ndimage.find_objects(lab), 1):
        area = (lab[sl] == i).sum()
        if area < min_area:
            continue
        ys, xs = sl
        out.append((int(area),
                    round((X0 + xs.start) / W * 100, 2), round((X0 + xs.stop) / W * 100, 2),
                    round((Y0 + ys.start) / H * 100, 2), round((Y0 + ys.stop) / H * 100, 2)))
    out.sort(key=lambda c: c[3])
    return out


# --------------------------------------------------------------------------- #
# font size calibration
# --------------------------------------------------------------------------- #
def calibrate_font(txt, font_file, target_px, font_dir=None):
    """Return (pt, achieved_px) for the font size whose advance width best
    matches target_px.  Convert px->pt with 0.25 (3840 px == 13.333 in).

    Calibrate against INK width and expect the fitted size to land within ~2%
    of the real one; then verify by rendering and measuring again.
    """
    font_dir = font_dir or FONT_DIR
    best = None
    for size in range(6, 200):
        f = ImageFont.truetype(os.path.join(font_dir, font_file), size)
        w = f.getlength(txt)
        if best is None or abs(w - target_px) < best[1]:
            best = (size, abs(w - target_px), w)
    return best[0] * 0.25, best[2]


def cap_height_px(font_file, size_px, font_dir=None):
    font_dir = font_dir or FONT_DIR
    f = ImageFont.truetype(os.path.join(font_dir, font_file), size_px)
    bb = f.getbbox("C")
    return bb[3] - bb[1]


def tracked_size(txt, font_file, target_px, cap_px, n_letters,
                 font_dir=None):
    """For letter-spaced uppercase labels: derive (size_pt, tracking_pt) from
    the measured cap height and total width."""
    font_dir = font_dir or FONT_DIR
    ratio = cap_height_px(font_file, 100, font_dir) / 100.0
    size = cap_px / ratio
    base = ImageFont.truetype(os.path.join(font_dir, font_file), int(round(size))).getlength(txt)
    track = (target_px - base) / max(1, n_letters - 1)
    return round(size * 0.25, 2), round(track * 0.25, 2)


# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    import sys
    img = sys.argv[1] if len(sys.argv) > 1 else "slide_full.png"
    a, W, H = load(img)
    print(json.dumps({"image": img, "size": [W, H]}, indent=1))
    print("background corners:", {k: hexs(avg_color(a, *r)) for k, r in {
        "TL": (0.3, 3, 0.3, 3), "TR": (97, 99.7, 0.3, 3),
        "BL": (0.3, 3, 97, 99.7), "BR": (97, 99.7, 97, 99.7)}.items()})
