"""Render an HTML slide or deck to a high-resolution PNG.

Once a slide exists as a raster, the rest of this skill is source-agnostic: the
same measure -> rebuild pipeline that handles an image-only PDF handles an HTML
export. This module is the only HTML-specific piece.

    render_html.py deck.html --out slide.png
    render_html.py deck.html --out s3.png --slide 3          # clip to the 3rd .slide
    render_html.py deck.html --out all.png --mode full       # full-page (scroll deck)
    render_html.py deck.html --list-slides                   # how many .slide elements
    render_html.py --classify somefile                       # pdf | html | image

Renderer preference: Playwright's Chromium (exact element clips + device scale
factor), then a local Chrome/Chromium headless binary.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys

DEFAULT_WIDTH = 1920
DEFAULT_HEIGHT = 1080
DEFAULT_SCALE = 2
DEFAULT_SELECTOR = ".slide"
DEFAULT_WAIT_MS = 700

CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
    "google-chrome",
    "chromium",
]


def classify(path):
    """pdf | html | image, from the file's extension and magic bytes."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        return "pdf"
    if ext in (".html", ".htm", ".xhtml"):
        return "html"
    if ext in (".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".bmp"):
        return "image"
    try:
        with open(path, "rb") as fh:
            head = fh.read(1024)
    except OSError:
        return "unknown"
    if head[:5] == b"%PDF-":
        return "pdf"
    if head[:4] in (b"\x89PNG", b"\xff\xd8\xff\xe0", b"\xff\xd8\xff\xe1", b"RIFF"):
        return "image"
    low = head.lower()
    if b"<html" in low or b"<!doctype html" in low or b"<body" in low:
        return "html"
    return "unknown"


def find_chrome():
    for cand in CHROME_CANDIDATES:
        if os.path.sep in cand:
            if os.path.exists(cand):
                return cand
        else:
            found = shutil.which(cand)
            if found:
                return found
    return None


def _as_url(target):
    if "://" in target:
        return target
    path = os.path.abspath(target)
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    from urllib.parse import quote
    return "file://" + quote(path)


def _render_playwright(url, out, width, height, scale, mode, selector, index, wait_ms):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(
            viewport={"width": width, "height": height},
            device_scale_factor=scale,
        )
        page.goto(url, wait_until="load")
        page.wait_for_timeout(wait_ms)
        if mode == "slide":
            nodes = page.query_selector_all(selector)
            if not nodes:
                browser.close()
                raise SystemExit("no element matched %r in %s" % (selector, url))
            if index >= len(nodes):
                browser.close()
                raise SystemExit("slide %d requested but only %d matched %r"
                                 % (index, len(nodes), selector))
            node = nodes[index]
            node.scroll_into_view_if_needed()
            page.wait_for_timeout(120)
            node.screenshot(path=out)
        elif mode == "full":
            page.screenshot(path=out, full_page=True)
        else:
            page.screenshot(path=out)
        browser.close()
    return out


def _render_chrome(chrome, url, out, width, height, scale, mode):
    if mode == "slide":
        raise SystemExit("--slide needs Playwright (element clips); install it with "
                         "'pip install playwright && playwright install chromium'")
    args = [
        chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars",
        "--no-first-run", "--no-default-browser-check",
        "--force-device-scale-factor=%s" % scale,
        "--window-size=%d,%d" % (width, height),
        "--screenshot=%s" % os.path.abspath(out),
    ]
    if mode == "full":
        args.append("--run-all-compositor-stages-before-draw")
    args.append(url)
    subprocess.run(args, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if not os.path.exists(out):
        raise SystemExit("chrome produced no screenshot")
    return out


def render(target, out, width=DEFAULT_WIDTH, height=DEFAULT_HEIGHT, scale=DEFAULT_SCALE,
           mode="viewport", selector=DEFAULT_SELECTOR, index=0, wait_ms=DEFAULT_WAIT_MS,
           renderer="auto"):
    """Render `target` (html path or URL) to `out` PNG. Returns (path, renderer_used)."""
    url = _as_url(target)
    if renderer in ("auto", "playwright"):
        try:
            _render_playwright(url, out, width, height, scale, mode, selector, index, wait_ms)
            return out, "playwright"
        except ImportError:
            if renderer == "playwright":
                raise SystemExit("Playwright is not installed for this interpreter")
    chrome = find_chrome()
    if not chrome:
        raise SystemExit("no renderer found: install Playwright chromium, or Chrome/Chromium")
    _render_chrome(chrome, url, out, width, height, scale, mode)
    return out, "chrome"


def list_slides(target, selector=DEFAULT_SELECTOR, width=DEFAULT_WIDTH,
                height=DEFAULT_HEIGHT, wait_ms=DEFAULT_WAIT_MS):
    """Return [{index, tag, id, classes, box}] for every element matching selector."""
    from playwright.sync_api import sync_playwright

    url = _as_url(target)
    out = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": width, "height": height})
        page.goto(url, wait_until="load")
        page.wait_for_timeout(wait_ms)
        nodes = page.query_selector_all(selector)
        for i, node in enumerate(nodes):
            info = node.evaluate(
                "el => ({tag: el.tagName.toLowerCase(), id: el.id || null,"
                " classes: el.className || null})")
            info["index"] = i
            info["box"] = node.bounding_box()
            out.append(info)
        browser.close()
    return out


def _main():
    ap = argparse.ArgumentParser(description="Render HTML slides to PNG for the "
                                             "image-pdf-to-pptx pipeline.")
    ap.add_argument("target", nargs="?", help="HTML file path or URL")
    ap.add_argument("--out", "-o", help="output PNG path")
    ap.add_argument("--width", type=int, default=DEFAULT_WIDTH)
    ap.add_argument("--height", type=int, default=DEFAULT_HEIGHT)
    ap.add_argument("--scale", type=int, default=DEFAULT_SCALE,
                    help="device scale factor (2 -> 1920x1080 becomes 3840x2160)")
    ap.add_argument("--mode", choices=["viewport", "slide", "full"], default="viewport")
    ap.add_argument("--selector", default=DEFAULT_SELECTOR)
    ap.add_argument("--slide", type=int, default=0, help="0-based index for --mode slide")
    ap.add_argument("--wait", type=int, default=DEFAULT_WAIT_MS, dest="wait_ms")
    ap.add_argument("--renderer", choices=["auto", "playwright", "chrome"], default="auto")
    ap.add_argument("--list-slides", action="store_true")
    ap.add_argument("--classify", action="store_true")
    args = ap.parse_args()

    if not args.target:
        ap.error("target is required")
    if args.classify:
        print(classify(args.target))
        return 0
    if args.list_slides:
        print(json.dumps(list_slides(args.target, args.selector, args.width,
                                     args.height, args.wait_ms), indent=2))
        return 0
    if not args.out:
        ap.error("--out is required")
    path, used = render(args.target, args.out, args.width, args.height, args.scale,
                        args.mode, args.selector, args.slide, args.wait_ms, args.renderer)
    print("rendered %s with %s" % (path, used))
    return 0


if __name__ == "__main__":
    sys.exit(_main())
