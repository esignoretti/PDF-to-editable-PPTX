"""Cut icons out of a slide raster as transparent PNGs.

Icons in these decks are line art drawn in an accent colour on a dark card, so
a soft alpha keyed off brightness (or off one channel) recovers them cleanly
and keeps the original anti-aliasing.

Usage
-----
    python extract_icons.py slide_full.png spec.json icons/

spec.json
---------
    {
      "cloud":   [17.85, 19.25, 23.30, 25.00],
      "glyph":   [9.55, 12.75, 87.55, 93.00, "white"],
      "server":  [54.35, 55.90, 17.00, 19.30, "bright"]
    }

Box = [x0, x1, y0, y1] in PERCENT (generous; the tool trims to the real ink).
Optional 5th element = mode:
    "bright" (default)  alpha from max(R,G,B)  -> icons on a dark ground
    "white"             alpha from R           -> white glyph on a coloured ground
    "green"             alpha from G - B       -> green mark on a blue ground

A JSON meta file (icons/meta.json) with the trimmed boxes is written next to the
PNGs; feed it straight to pptx_helpers.picture().
"""
import json
import os
import sys

import numpy as np
from PIL import Image

MODES = {
    # name: (channel extractor, t0, t1)
    "bright": (lambda s: s.max(axis=2).astype(float), 60.0, 130.0),
    "white":  (lambda s: s[:, :, 0].astype(float), 70.0, 200.0),
    "green":  (lambda s: (s[:, :, 1] - s[:, :, 2]).astype(float), 10.0, 60.0),
}


def extract(img_path, spec, out_dir, white_color=(255, 255, 255)):
    a = np.asarray(Image.open(img_path).convert("RGB")).astype(int)
    H, W, _ = a.shape
    os.makedirs(out_dir, exist_ok=True)
    meta = {}
    for name, box in spec.items():
        x0, x1, y0, y1 = box[:4]
        mode = box[4] if len(box) > 4 else "bright"
        fn, t0, t1 = MODES[mode]
        X0, X1 = int(x0 / 100 * W), int(x1 / 100 * W)
        Y0, Y1 = int(y0 / 100 * H), int(y1 / 100 * H)
        sub = a[Y0:Y1, X0:X1]
        alpha = np.clip((fn(sub) - t0) / (t1 - t0), 0, 1)
        ys, xs = np.where(alpha > 0.15)
        if len(ys) == 0:
            print("  EMPTY", name)
            continue
        ay0, ay1, ax0, ax1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
        col = sub
        if mode == "white":
            col = np.zeros_like(sub)
            col[:, :, 0], col[:, :, 1], col[:, :, 2] = white_color
        rgba = np.dstack([col[ay0:ay1, ax0:ax1].astype(np.uint8),
                          (alpha[ay0:ay1, ax0:ax1] * 255).astype(np.uint8)])
        Image.fromarray(rgba, "RGBA").save(os.path.join(out_dir, name + ".png"))
        meta[name] = {
            "x0": round((X0 + ax0) / W * 100, 3), "x1": round((X0 + ax1) / W * 100, 3),
            "y0": round((Y0 + ay0) / H * 100, 3), "y1": round((Y0 + ay1) / H * 100, 3),
            "w": round((ax1 - ax0) / W * 100, 3), "h": round((ay1 - ay0) / H * 100, 3)}
    with open(os.path.join(out_dir, "meta.json"), "w") as f:
        json.dump(meta, f, indent=1)
    print("extracted %d icons -> %s" % (len(meta), out_dir))
    return meta


def contact_sheet(out_dir, path="icons_sheet.png", cell=120, bg=(17, 27, 46)):
    """Visual check: paste every icon on a card-coloured ground with labels."""
    from PIL import ImageDraw
    files = sorted(f for f in os.listdir(out_dir) if f.endswith(".png") and f != "meta.json")
    cols = 8
    rows = (len(files) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell, rows * cell), bg)
    d = ImageDraw.Draw(sheet)
    for i, f in enumerate(files):
        im = Image.open(os.path.join(out_dir, f)).convert("RGBA")
        im.thumbnail((cell - 16, cell - 28))
        x, y = (i % cols) * cell + 8, (i // cols) * cell + 18
        sheet.paste(im, (x, y), im)
        d.text((x, y - 12), f[:-4], fill=(150, 190, 240))
    sheet.save(path)
    return path


if __name__ == "__main__":
    img, spec_path, out = sys.argv[1], sys.argv[2], sys.argv[3]
    meta = extract(img, json.load(open(spec_path)), out)
    print(contact_sheet(out))
