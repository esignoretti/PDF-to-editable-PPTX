"""Extract an exact build spec from an HTML slide's DOM + computed CSS.

This is the HTML *fast path*. The raster route (`render_html` -> measure ->
calibrate) works on anything but has to guess fonts, sizes and colours back out
of pixels. When the source is HTML, the browser already knows all of it, so read
it instead:

    extract_dom.py deck.html --out spec.json --assets assets/
    extract_dom.py deck.html --out spec.json --slide 2 --list-slides

Emits one ordered node list (DOM order == paint order) with:

    box    rounded rectangle: fill (solid or linear gradient), border, radius
    text   runs with exact family / size / weight / colour / tracking / align
    svg    inline <svg> rasterised to assets/icon-N.png at 3x
    image  <img>, inlined as assets/img-N.png when it is a data: URI

Punts (logged to spec["warnings"]): non-identity transforms, radial gradients,
box-shadow, background-image URLs, filter/blend effects, <canvas>, <video>.
Run the raster route for decks that lean on those.
"""
import argparse
import base64
import json
import os
import sys

DEFAULT_SELECTOR = ".slide"
DEFAULT_WIDTH = 1920
DEFAULT_HEIGHT = 1080
DEFAULT_WAIT_MS = 700
SVG_SCALE = 3

JS = r"""
(slide) => {
  const sr = slide.getBoundingClientRect();
  const SW = sr.width, SH = sr.height;
  const nodes = [];
  const warnings = [];

  function col(c) {
    if (!c || c === 'transparent') return null;
    const m = c.match(/rgba?\(([^)]+)\)/);
    if (!m) return null;
    const p = m[1].split(',').map(s => parseFloat(s.trim()));
    const a = p.length > 3 ? p[3] : 1;
    if (a === 0) return null;
    const h = ((1 << 24) + (Math.round(p[0]) << 16) + (Math.round(p[1]) << 8) + Math.round(p[2]))
      .toString(16).slice(1).toUpperCase();
    return { hex: h, a: a };
  }

  function innerArgs(s, openIdx) {
    let depth = 0;
    for (let i = openIdx; i < s.length; i++) {
      if (s[i] === '(') depth++;
      else if (s[i] === ')') { depth--; if (depth === 0) return s.slice(openIdx + 1, i); }
    }
    return null;
  }

  function gradient(bg) {
    if (!bg || bg === 'none') return null;
    const lin = bg.match(/linear-gradient\(/);
    if (lin) {
      const inner = innerArgs(bg, lin.index + lin[0].length - 1);
      const parts = (inner || '').split(/,(?![^(]*\))/).map(s => s.trim());
      let ang = 180;
      if (/^-?[\d.]+deg/.test(parts[0])) ang = parseFloat(parts.shift());
      else if (/^to\s/.test(parts[0])) { warnings.push('named gradient direction punted to 180deg'); parts.shift(); }
      const stops = [];
      parts.forEach((p, i) => {
        const mm = p.match(/(rgba?\([^)]+\)|#[0-9a-fA-F]{3,8})\s*([\d.]+%)?/);
        if (!mm) return;
        const c = col(mm[1]);
        if (!c) return;
        const pos = mm[2] ? parseFloat(mm[2]) : (parts.length === 1 ? 0 : (i / (parts.length - 1)) * 100);
        stops.push({ pos: pos, hex: c.hex, a: c.a });
      });
      if (stops.length >= 2) return { type: 'linear', css_angle: ang, stops: stops };
    }
    if (/radial-gradient/.test(bg)) { warnings.push('radial-gradient left to the raster route'); return { type: 'radial' }; }
    if (/url\(/.test(bg)) { warnings.push('background-image url left to the raster route'); return { type: 'image' }; }
    return null;
  }

  function styleOf(el) {
    const cs = getComputedStyle(el);
    const fs = parseFloat(cs.fontSize) || 16;
    const c = col(cs.color) || { hex: '000000', a: 1 };
    return {
      family: (cs.fontFamily || '').split(',')[0].replace(/["']/g, '').trim(),
      size_px: fs,
      weight: parseInt(cs.fontWeight, 10) || 400,
      italic: cs.fontStyle === 'italic',
      color: c.hex,
      alpha: c.a,
      letter_spacing_px: cs.letterSpacing === 'normal' ? 0 : (parseFloat(cs.letterSpacing) || 0),
      line_height_px: cs.lineHeight === 'normal' ? fs * 1.2 : parseFloat(cs.lineHeight),
      align: cs.textAlign,
      transform: cs.textTransform
    };
  }

  function runsOf(el) {
    const runs = [];
    (function walk(node, styleEl) {
      for (const child of node.childNodes) {
        if (child.nodeType === 3) {
          const t = child.textContent.replace(/\s+/g, ' ');
          if (t.trim() !== '') runs.push({ text: t, style: styleOf(styleEl) });
        } else if (child.nodeType === 1) {
          const cs = getComputedStyle(child);
          if (cs.display === 'none' || cs.visibility === 'hidden') continue;
          const d = cs.display;
          if (d.indexOf('inline') === 0 && d !== 'inline-block' && d !== 'inline-flex' && d !== 'inline-grid') {
            walk(child, child);
          }
        }
      }
    })(el, el);
    return runs;
  }

  function visible(el) {
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden') return false;
    if (parseFloat(cs.opacity) === 0) return false;
    if (cs.transform && cs.transform !== 'none') warnings.push('transform on <' + el.tagName.toLowerCase() + '> ignored');
    return true;
  }

  function boxOf(el) {
    const r = el.getBoundingClientRect();
    return {
      x: +(r.left - sr.left).toFixed(2), y: +(r.top - sr.top).toFixed(2),
      w: +r.width.toFixed(2), h: +r.height.toFixed(2)
    };
  }

  function contentBoxOf(el) {
    const cs = getComputedStyle(el);
    const r = el.getBoundingClientRect();
    const f = (v) => parseFloat(v) || 0;
    const pl = f(cs.paddingLeft), pr = f(cs.paddingRight);
    const ptop = f(cs.paddingTop), pb = f(cs.paddingBottom);
    const bl = f(cs.borderLeftWidth), br = f(cs.borderRightWidth);
    const bt = f(cs.borderTopWidth), bb = f(cs.borderBottomWidth);
    return {
      x: +(r.left - sr.left + bl + pl).toFixed(2),
      y: +(r.top - sr.top + bt + ptop).toFixed(2),
      w: +Math.max(0, r.width - bl - br - pl - pr).toFixed(2),
      h: +Math.max(0, r.height - bt - bb - ptop - pb).toFixed(2)
    };
  }

  function walk(el) {
    for (const child of el.children) {
      if (!visible(child)) continue;
      const tag = child.tagName.toLowerCase();
      const cs = getComputedStyle(child);
      const box = boxOf(child);

      if (tag === 'svg') {
        const idx = nodes.length;
        nodes.push({ kind: 'svg', box: box });
        child.setAttribute('data-od-idx', String(idx));
        continue;
      }
      if (tag === 'img') {
        const idx = nodes.length;
        nodes.push({ kind: 'image', box: box });
        child.setAttribute('data-od-idx', String(idx));
        continue;
      }
      if (tag === 'canvas' || tag === 'video' || tag === 'iframe') {
        warnings.push('<' + tag + '> left to the raster route');
        continue;
      }

      const bgc = col(cs.backgroundColor);
      const grad = gradient(cs.backgroundImage);
      const bw = ['Top', 'Right', 'Bottom', 'Left'].map(s => parseFloat(cs['border' + s + 'Width']) || 0);
      const bc = col(cs.borderTopColor);
      const hasBox = (bgc && bgc.a > 0.01) || (grad && grad.type === 'linear') || bw.some(v => v > 0);

      if (hasBox) {
        if (cs.boxShadow && cs.boxShadow !== 'none') warnings.push('box-shadow ignored');
        nodes.push({
          kind: 'box', box: box,
          fill: bgc ? { hex: bgc.hex, a: bgc.a } : null,
          gradient: grad,
          border: bw.some(v => v > 0)
            ? { w: Math.max.apply(null, bw), hex: bc ? bc.hex : '000000', a: bc ? bc.a : 1 }
            : null,
          radius_px: parseFloat(cs.borderTopLeftRadius) || 0,
          opacity: parseFloat(cs.opacity)
        });
      }

      const runs = runsOf(child);
      if (runs.length) {
        nodes.push({
          kind: 'text', box: contentBoxOf(child), runs: runs,
          align: cs.textAlign,
          line_height_px: runs[0].style.line_height_px,
          white_space: cs.whiteSpace
        });
      }

      walk(child);
    }
  }

  const rootCs = getComputedStyle(slide);
  const bg = col(rootCs.backgroundColor);
  const bgg = gradient(rootCs.backgroundImage);
  walk(slide);

  return {
    slide: { w: SW, h: SH, background: bg ? { hex: bg.hex, a: bg.a } : null, gradient: bgg },
    nodes: nodes,
    warnings: warnings
  };
}
"""


def _as_url(target):
    if "://" in target:
        return target
    from urllib.parse import quote
    return "file://" + quote(os.path.abspath(target))


def extract(target, out_json, assets_dir="assets", selector=DEFAULT_SELECTOR, index=0,
            width=DEFAULT_WIDTH, height=DEFAULT_HEIGHT, wait_ms=DEFAULT_WAIT_MS):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise SystemExit(
            "extract_dom needs Playwright (the raster route does not):\n"
            "  pip install playwright && playwright install chromium")

    url = _as_url(target)
    os.makedirs(assets_dir, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": width, "height": height},
                                device_scale_factor=SVG_SCALE)
        page.goto(url, wait_until="load")
        page.wait_for_timeout(wait_ms)

        slides = page.query_selector_all(selector)
        if not slides:
            browser.close()
            raise SystemExit("no element matched %r in %s" % (selector, url))
        if index >= len(slides):
            browser.close()
            raise SystemExit("slide %d requested but only %d matched %r" % (index, len(slides), selector))
        slide = slides[index]

        spec = slide.evaluate(JS)
        spec["source"] = {"target": os.path.abspath(target) if "://" not in target else target,
                          "selector": selector, "index": index}

        for i, node in enumerate(spec["nodes"]):
            if node["kind"] not in ("svg", "image"):
                continue
            el = page.query_selector('%s [data-od-idx="%d"]' % (selector, i))
            if el is None:
                spec["warnings"].append("asset %d not found for screenshot" % i)
                continue
            name = ("icon-%d.png" if node["kind"] == "svg" else "img-%d.png") % i
            path = os.path.join(assets_dir, name)
            el.screenshot(path=path)
            node["asset"] = os.path.relpath(path, os.path.dirname(os.path.abspath(out_json)))
        browser.close()

    spec["warnings"] = sorted(set(spec["warnings"]))
    with open(out_json, "w") as fh:
        json.dump(spec, fh, indent=1)
    return spec


def list_slides(target, selector=DEFAULT_SELECTOR, width=DEFAULT_WIDTH,
                height=DEFAULT_HEIGHT, wait_ms=DEFAULT_WAIT_MS):
    from playwright.sync_api import sync_playwright
    url = _as_url(target)
    out = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": width, "height": height})
        page.goto(url, wait_until="load")
        page.wait_for_timeout(wait_ms)
        for i, node in enumerate(page.query_selector_all(selector)):
            info = node.evaluate("el => ({tag: el.tagName.toLowerCase(), id: el.id || null,"
                                 " classes: (el.className || '').toString() || null})")
            info["index"] = i
            info["box"] = node.bounding_box()
            out.append(info)
        browser.close()
    return out


def _main():
    ap = argparse.ArgumentParser(description="Extract an exact build spec from an HTML slide DOM.")
    ap.add_argument("target", nargs="?", help="HTML file path or URL")
    ap.add_argument("--out", "-o", default="spec.json")
    ap.add_argument("--assets", default="assets")
    ap.add_argument("--selector", default=DEFAULT_SELECTOR)
    ap.add_argument("--slide", type=int, default=0)
    ap.add_argument("--width", type=int, default=DEFAULT_WIDTH)
    ap.add_argument("--height", type=int, default=DEFAULT_HEIGHT)
    ap.add_argument("--wait", type=int, default=DEFAULT_WAIT_MS, dest="wait_ms")
    ap.add_argument("--list-slides", action="store_true")
    args = ap.parse_args()

    if not args.target:
        ap.error("target is required")
    if args.list_slides:
        print(json.dumps(list_slides(args.target, args.selector, args.width,
                                     args.height, args.wait_ms), indent=2))
        return 0
    spec = extract(args.target, args.out, args.assets, args.selector, args.slide,
                   args.width, args.height, args.wait_ms)
    kinds = {}
    for n in spec["nodes"]:
        kinds[n["kind"]] = kinds.get(n["kind"], 0) + 1
    print("slide %.0fx%.0f  nodes: %s" % (spec["slide"]["w"], spec["slide"]["h"], kinds))
    if spec["warnings"]:
        print("warnings:")
        for w in spec["warnings"]:
            print("  -", w)
    print("wrote", args.out, "assets ->", args.assets)
    return 0


if __name__ == "__main__":
    sys.exit(_main())
