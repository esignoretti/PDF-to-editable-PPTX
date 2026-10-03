---
name: image-pdf-to-pptx
description: |
  Convert an image-only or scanned slide PDF, or an HTML slide/deck export, into a
  fully editable PowerPoint .pptx. Rebuilds layout, fonts, colours, icons and card
  translucency as native shapes and text boxes instead of tracing or OCR. Use when a
  slide PDF has no text layer, page.get_text() returns nothing, one embedded image per
  page, or when an HTML slide must come back as editable PowerPoint.
triggers:
  - "pdf to pptx"
  - "convert pdf slide to powerpoint"
  - "html to pptx"
  - "convert html slide to powerpoint"
  - "editable pptx"
  - "image-only pdf"
  - "scanned slide pdf"
  - "pdf has no text layer"
  - "page.get_text returns nothing"
  - "make this slide editable"
  - "rebuild this slide in powerpoint"
od:
  mode: deck
  category: slides
  upstream: "local"
---

# Slide PDF or HTML → editable PPTX

## Overview

**Rebuild, don't trace.** A "convert to editable" tool that OCRs or traces vectors
gives you uneditable garbage. Instead: get the slide as a raster, measure it
precisely, then emit native PowerPoint shapes and text boxes. The *only* raster
left in the result is the backdrop and the icons.

Two sources are supported and they converge immediately:

- **PDF** — image-only / scanned / single-image export: pull the embedded raster.
- **HTML** — a slide or deck export: render it to a raster at 2x with
  `render_html`, clipping to one slide element when the deck has many.

Everything after phase 1 is source-agnostic.

Result of this method: mean per-pixel error ~20/765 against the source, every text
element within ~0.1% of its original position, and 100% of the copy as real text.

## When to use

- `page.get_text()` is empty / the PDF is one embedded image (check first, phase 1).
- The source is an HTML slide or deck and the user wants an editable `.pptx`.
- Brand slide decks (cards, pills, accent borders, custom icons, soft gradients).
- The user will edit the text/layout afterwards.

**Don't use** when the PDF has real text and vectors — convert those directly.
Don't use when a rough look-alike is acceptable.

## Pipeline

```
HTML:  extract_dom → dom_to_pptx → render & diff → nudge → ship
   PDF:   get raster → measure → calibrate fonts → extract icons
          → fit backdrop + derive card fills → build → render & diff → nudge → ship
   (HTML may also take the PDF route via render_html when the spec punts)
```

## Setup

```bash
python3 -m venv .venv && .venv/bin/pip install python-pptx Pillow numpy scipy pymupdf
```

For **HTML sources** add a renderer — either Playwright (recommended: exact
element clips) or any local Chrome/Chromium:

```bash
.venv/bin/pip install playwright && .venv/bin/playwright install chromium
# or: nothing to install if Google Chrome / Chromium / Edge is in /Applications
```

The helper modules live in this skill's `scripts/` — add it to `sys.path` (or copy
them next to your build script):

```python
import sys; sys.path.insert(0, "<skill>/scripts")
```

`measure_slide` / `calibrate_font` default to the macOS user font dir
(`~/Library/Fonts`); pass `font_dir=` elsewhere. Write **one deterministic
`build_pptx.py`** that reads `icons/meta.json` + `bg_fit.png` and re-runs in
seconds — you will iterate it 3–5 times in phase 7.

## Quick reference

| Need | Tool |
|---|---|
| Native raster + resolution | `pymupdf` `page.get_images()` / `Pixmap` |
| HTML slide/deck → raster | `render_html.render` / `--mode slide` |
| HTML slide → exact build spec | `extract_dom.extract` |
| Build a PPTX from that spec | `dom_to_pptx.build` |
| Is this a pdf, html or image? | `render_html.classify` |
| Card edges, dividers | `measure_slide.edges_col` / `edges_row` |
| Every text line's y | `measure_slide.text_rows` |
| One string's exact ink box | `measure_slide.ink_bbox` |
| Icon blobs | `measure_slide.components` |
| Font size from measured width | `measure_slide.calibrate_font` |
| Letter-spaced label size+tracking | `measure_slide.tracked_size` |
| Transparent icon PNGs | `extract_icons.extract` |
| Backdrop image + card fill gradients | `fit_background.BackgroundFit` |
| Shapes / text / top-border arcs | `pptx_helpers` |

## Phase 1 — get a raster, and do not trust the preview

```python
import pymupdf
d = pymupdf.open(pdf); page = d[0]
for img in page.get_images(full=True):          # (xref, _, w, h, ...)
    pix = pymupdf.Pixmap(d, img[0])
    if pix.n > 4: pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
    pix.save("slide_full.png")
```

**A host PDF preview or JPEG thumbnail can carry a broken colour profile.**
A navy/blue slide rendered as brown/orange in the attachment preview while the
embedded raster was navy. If you match the preview you rebuild the wrong slide.
Always inspect the extracted PNG, and sample colours from it numerically.

Geometry: `page.rect` 960×540 → 16:9 → build at **13.333 × 7.5 in**. A 3840 px
wide raster therefore maps **1 px = 0.25 pt** (use this for font sizes).

### HTML sources

Render the slide — do not try to parse the DOM into shapes.

```bash
python scripts/render_html.py deck.html --list-slides                 # what slides exist
python scripts/render_html.py deck.html --out slide.png --mode slide --slide 3
python scripts/render_html.py deck.html --out slide.png               # single-slide HTML
python scripts/render_html.py deck.html --out all.png --mode full     # scroll deck
python scripts/render_html.py --classify somefile                     # pdf | html | image
```

- `--mode slide` clips the screenshot to the Nth element matching `--selector`
  (default `.slide`). That is the deck-agnostic way to pull one slide out of a
  multi-slide document — no knowledge of the deck's own markup required.
- `--scale 2` on a 1920×1080 viewport yields the 3840×2160 raster the rest of the
  pipeline expects. `--scale 1` halves the file size at some accuracy cost.
- Playwright is used when importable (exact element clips + device scale factor);
  otherwise a local Chrome/Chromium headless binary renders the viewport.
- Render at the deck's own aspect ratio. If the HTML slide is not 16:9, build the
  PPTX at the matching slide size rather than forcing 13.333 × 7.5 in.
- Let webfonts settle before capturing (`--wait`, default 700 ms) or you will
  measure a fallback face and calibrate the wrong sizes.

### HTML fast path — read the DOM instead of measuring

For an HTML source the browser already knows every position, colour, font size and
tracking, so skip phases 2-4 entirely:

```bash
python scripts/extract_dom.py deck.html --out spec.json --assets assets
python scripts/dom_to_pptx.py --spec spec.json --out deck.pptx
# or both in one step:
python scripts/dom_to_pptx.py --html deck.html --out deck.pptx --slide 2
```

`extract_dom` walks the slide subtree and emits an **ordered spec** (DOM order ==
paint order):

| kind | carries |
|---|---|
| `box` | border box, solid fill + alpha, linear gradient (stops + angle), border, radius |
| `text` | **content** box, runs with exact family / size / weight / colour / tracking, align, line-height |
| `svg` | box + inline `<svg>` rasterised to `assets/icon-N.png` at 3x |
| `image` | box + `<img>` |

`dom_to_pptx` maps CSS px → slide percent and pt and emits native shapes. Then
verify exactly as in phase 7.

**Prefer it** for any HTML source. **Fall back to the raster route** when
`spec.warnings` is non-empty — the spec punts on non-identity transforms, radial
gradients, `box-shadow`, `background-image` URLs, filter/blend and canvas/video.

Three things that bite, in order:

- Text nodes carry the **content box** (border box minus border and padding). Use
  the border box instead and padded text — pills, buttons, cards — drops to the
  top-left.
- Single-line text is emitted with **wrapping off**. Let it wrap and a font that
  renders a hair wider than the browser's breaks "SaaS" into "Saa / s".
- `font-weight >= 600` maps to bold. For the exact SemiBold face, rewrite the
  family to `<Family> SemiBold` in the spec.

## Phase 2 — measure

Work in **percent of slide** everywhere; feed those numbers straight to
`pptx_helpers`.

1. Pick a column that runs through the cards but avoids text/icons → `edges_col`
   gives every card top/bottom and row divider.
2. Pick a clean row → `edges_row` gives every card left/right edge.
3. `text_rows` in each content column gives every line band → ink centres.
4. `ink_bbox` per string gives the width used for font calibration.
5. `components` (colour masks) gives icon, dash and accent positions.

## Phase 3 — calibrate fonts

Never guess sizes. Measure ink width, then find the font size whose advance width
matches:

```python
pt, _ = calibrate_font("Fully managed", "SourceSans3-Regular.ttf", 261)   # -> 10.5
size_pt, track_pt = tracked_size("PROS", "SourceSans3-Semibold.ttf", 69, 17, 4)
```

Uppercase labels are letter-spaced: derive the size from **cap height** and the
tracking from the leftover width (`tracked_size`), then set OOXML `spc` in pt.

Use exact family names including the weight variant (`Source Sans 3 Semibold`,
`Titillium Web`). Set `a:latin` explicitly on every run.

## Phase 4 — icons

```python
extract(img, {"cloud": [17.85,19.25,23.30,25.00],
              "glyph": [9.55,12.75,87.55,93.00,"white"]}, "icons")
contact_sheet("icons")          # always eyeball the sheet before building
```

Alpha is keyed off brightness (`bright`), one channel (`white`), or a channel
difference (`green`). Icons are line art on a dark ground, so the original
anti-aliasing survives. Boxes are generous — the tool trims to real ink and
writes `icons/meta.json` with the trimmed boxes.

Icons drawn *on* a coloured fill (pill, badge, solid button) need a higher `t0`
than icons on a dark card, or the fill itself leaks into the alpha.

## Phase 5 — backdrop and card fills

A soft multi-stop gradient or corner glow cannot be expressed as a DrawingML
gradient. Recover it from the pixels the cards do **not** cover:

```python
fit = BackgroundFit("slide_full.png", cards=[...], text_cuts=[...])
fit.save("bg_fit.png")                                   # backdrop image
fit.overlay_stops(rect=(7.81,13.89,47.45,82.87), sample_x=45.2)
```

- **Exclude every non-background region** — all cards, banners, floating badges
  (a VS circle, etc.) and the big headline block. Miss one and the RMSE jumps.
- `overlay_stops` samples one content-free column and returns a 4–5 stop
  `[(pos%, '#RRGGBB', alpha%)]` gradient for that card: `C = bg + (obs-bg)/a`
  with `a` ramping 20%→55%. The card stays translucent, so it keeps following
  the backdrop horizontally.
- The backdrop raster is a *smooth fit* — no text or icons baked into it.

## Phase 6 — build

`pptx_helpers` covers fills (solid + gradient + alpha), lines (custom dash,
arrowheads), rounded rects, ovals, text boxes, and `top_border` — an open
arc-line-arc path for cards whose **top edge is an accent colour** while the
other three edges are neutral.

**Z-order is the #1 bug.** Emit in this order:

```
backdrop → card fills → card borders → accent top borders → dividers
   → icon backing squares → icon images → all text
```

Icons placed before their backing square get painted over and vanish.

Multi-line copy: split it into **one text box per measured line** at that line's
ink centre. This sidesteps all line-spacing ambiguity between renderers.

## Phase 7 — verify, then nudge

Render the PPTX back to the *source resolution* and compare numerically:

```bash
FONTCONFIG_PATH=/opt/homebrew/etc/fonts \
FONTCONFIG_FILE=/opt/homebrew/etc/fonts/fonts.conf \
soffice -env:UserInstallation=file:///tmp/loprof --headless \
  --convert-to pdf --outdir . deck.pptx
```

`FONTCONFIG_PATH`/`FONTCONFIG_FILE` are **required** or LibreOffice ignores
user-installed fonts and silently substitutes (check the PDF's font list — if you
see `LinuxLibertine` or `FrankRuhlHofshi`, the fonts were not found).

Then: rasterise at 3840 px, `mean abs diff`, and run `ink_bbox` on the **same
regions in both images**. The rendered ink centre sits low by ≈`0.026 %/pt` of
slide height (the line box is centred, not the ink) — `pptx_helpers.text` applies
that, and you correct the rest with `yc -= dy`. Two or three iterations reaches
±0.1%. Expect ~20/765 mean diff; anything above ~35 means a structural miss.

## Common mistakes

| Mistake | Fix |
|---|---|
| Matching the attached preview's colours | Extract the embedded raster; sample it |
| Guessing font sizes | `calibrate_font` against measured ink width |
| LibreOffice substituting fonts during verify | Set `FONTCONFIG_PATH`/`FONTCONFIG_FILE`; check the PDF font list |
| Icons invisible in the output | Place icon images *after* their backing squares |
| Card fills look flat/wrong | Use `overlay_stops` (translucent gradient), not a guessed solid |
| Backdrop fit has high RMSE | Exclude every non-background region, incl. floating badges |
| Text a hair too low everywhere | `yc -= dy` from a two-image ink measurement |
| Wrapped line breaks differ | One text box per source line, positioned at its ink centre |
| Weights look off | Use the real family name (`Source Sans 3 Semibold`), not `bold=True` |
| HTML deck renders the wrong slide | `--mode slide --slide N` with `--list-slides` to confirm the index |
| HTML render is 1x and blurry | Pass `--scale 2`; the pipeline wants ~3840 px wide |
| HTML text measured in the wrong face | Raise `--wait` so webfonts load before the screenshot |
| Padded text jumps to the top-left | Text nodes must use the content box, not the border box |
| Short labels wrap mid-word | Keep single-line text unwrapped |
| DOM spec reports warnings | Those slides want the raster route instead |

## Red flags — stop and re-check

- You are about to write a font size you didn't measure.
- You haven't looked at the extracted raster yourself.
- You're eyeballing alignment instead of diffing ink boxes.
- The render's font list contains a font you didn't ask for.
- One `mean abs diff` pass and you're calling it done.

## Ship

Save the `.pptx` plus a PNG preview next to it. State the source (PDF embed, HTML
render, or HTML DOM spec), the font requirement (or substitution shifts line
widths) and what stayed raster (backdrop + icons).
