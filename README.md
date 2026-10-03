# Slide PDF or HTML → editable PPTX

Turn an **image-only slide PDF** — a scanned deck, or a single-image export with no
text layer — **or an HTML slide/deck export** into a **fully editable PowerPoint
`.pptx`**.

Not a tracer. Not OCR. The slide is **measured and rebuilt**: cards, pills, accent
borders and dividers come back as native PowerPoint shapes, every string comes back
as a real text box, and only the backdrop and the icons stay raster.

```
source PDF (one 3840×2160 image)  ┐
                                  ├─→  editable PPTX (native shapes + text)
source HTML slide / deck          ┘
```

Both sources converge immediately: get the slide as a raster, then measure and
rebuild it. The HTML path renders at 2× and clips to a single slide element.

---

## Why not just convert it?

A "convert to editable" button on an image-only PDF gives you one of two things:
an uneditable picture of the slide, or OCR'd text boxes scattered over a traced
bitmap. Both are useless the moment you want to change a word.

This does the other thing: it reads the pixels precisely enough to re-emit the
slide as native objects.

| | Result |
|---|---|
| Text | real text boxes, real fonts, real sizes |
| Cards / pills / borders | native rounded rectangles, gradient + alpha fills |
| Accent top borders | custom-geometry arc paths that wrap the corners |
| Dashed dividers / arrows | native connectors with custom dash patterns and arrowheads |
| Icons | transparent PNGs cut from the source at native resolution |
| Backdrop | a smooth polynomial fit — no text or icons baked in |
| Fidelity | ~6/765 mean error on the HTML fast path, ~20/765 on the raster route |
| Sources | image-only PDF (embedded raster) · HTML slide or deck |

## Install

This ships as an **Open Design** skill. The installer places it in every Open Design
namespace it finds and reports any missing Python packages.

```bash
git clone https://github.com/esignoretti/PDF-to-editable-PPTX.git
cd PDF-to-editable-PPTX
./install.sh --dry-run     # preview
./install.sh               # install
```

Restart (or refresh) Open Design, then ask:

> "Convert this slide PDF to an editable PPTX — it has no text layer."

See **[INSTALL.md](INSTALL.md)** for manual install, verification, updates and
troubleshooting.

### HTML sources

HTML gets **two** routes. Prefer the fast path; keep the raster route for decks it
can't express.

**Fast path — read the DOM.** The browser already knows every position, colour,
font size and tracking, so nothing is calibrated from pixels:

```bash
python skill/scripts/extract_dom.py deck.html --out spec.json --assets assets
python skill/scripts/dom_to_pptx.py --spec spec.json --out deck.pptx
# or both in one step:
python skill/scripts/dom_to_pptx.py --html deck.html --out deck.pptx --slide 2
```

`extract_dom` walks the slide subtree and emits an ordered spec (DOM order == paint
order): `box` (fill + alpha, linear gradient with stops and angle, border, radius),
`text` (content box, runs with exact family/size/weight/colour/tracking, align,
line-height), `svg` (rasterised to `assets/icon-N.png` at 3×) and `image`. On a
typical branded slide this lands at **~6/765 mean error** — better than the raster
route can reach, because nothing is guessed.

**Raster route — render then measure.** Use it when the spec reports warnings, or
for PDFs:

```bash
python skill/scripts/render_html.py deck.html --list-slides            # what slides exist
python skill/scripts/render_html.py deck.html --out slide.png --mode slide --slide 3
python skill/scripts/render_html.py deck.html --out slide.png          # single-slide HTML
python skill/scripts/render_html.py deck.html --out all.png --mode full  # scroll deck
python skill/scripts/render_html.py --classify somefile                # pdf | html | image
```

`--mode slide` clips the screenshot to the Nth element matching `--selector`
(default `.slide`), so it works on any deck without knowing its markup. Playwright
is used when importable (exact element clips + device scale factor); otherwise a
local Chrome/Chromium renders the viewport. `--scale 2` on a 1920×1080 viewport
gives the 3840×2160 raster the rest of the pipeline expects.

The fast path punts on — and logs in `spec.warnings` — non-identity transforms,
radial gradients, `box-shadow`, `background-image` URLs, filter/blend, `<canvas>`
and `<video>`. When the list is non-empty, run the raster route for those slides.

### Using it outside Open Design

`skill/` is a plain skill folder (`SKILL.md` + `scripts/`). It works anywhere an
agent can read files and run Python — OpenCode, Claude Code, Codex, or by hand:

```python
import sys; sys.path.insert(0, "skill/scripts")
from pptx_helpers import roundrect, text, top_border
from measure_slide import load, edges_col, text_rows, ink_bbox, calibrate_font
from fit_background import BackgroundFit
from extract_icons import extract, contact_sheet
```

## Triggers

`pdf to pptx` · `convert pdf slide to powerpoint` · `html to pptx` ·
`convert html slide to powerpoint` · `editable pptx` · `image-only pdf` ·
`scanned slide pdf` · `pdf has no text layer` · `page.get_text returns nothing` ·
`make this slide editable` · `rebuild this slide in powerpoint`

## How it works

```
get a raster (PDF embed, or render HTML) → measure → calibrate fonts
   → extract icons → fit backdrop + derive card fills → build
   → render & diff → nudge → ship
```

1. **Get a raster.** For a PDF, extract the embedded image at native resolution — the
   host PDF preview can carry a broken colour profile, so colours are sampled from the
   extracted pixels, never from a thumbnail. For HTML, render it at 2× with
   `render_html`.
2. **Measure** every card edge, divider, text line and icon in percent of slide.
3. **Calibrate** font sizes by fitting the real font's advance width to the measured
   ink width. Letter-spaced labels are split into cap-height size + tracking.
4. **Extract icons** as transparent PNGs by alpha-keying off brightness.
5. **Fit the backdrop** with a degree-6 polynomial over the pixels the cards don't
   cover, then derive each card's translucent fill gradient from its own interior.
6. **Build** native shapes and text boxes in the correct z-order.
7. **Verify** by rendering the PPTX back at source resolution, diffing it, measuring
   ink boxes in both images, and nudging until it matches.

The full method, including the failure modes it avoids, is in
[`skill/SKILL.md`](skill/SKILL.md).

## Repo layout

```
PDF-to-editable-PPTX/
├── install.sh                 installer / uninstaller for Open Design
├── INSTALL.md                 detailed install, verify, troubleshoot
├── README.md
├── LICENSE
├── skill/
│   ├── SKILL.md               the technique: pipeline, gotchas, red flags
│   └── scripts/
│       ├── render_html.py     HTML slide/deck → high-resolution PNG
│       ├── extract_dom.py     HTML slide DOM + computed CSS → exact build spec
│       ├── dom_to_pptx.py     that spec → PPTX (the HTML fast path)
│       ├── pptx_helpers.py    fills, gradients + alpha, custom-dash lines,
│       │                      rounded rects, text boxes, accent top borders
│       ├── measure_slide.py   edge / text-line / ink measurement, colour masks,
│       │                      font-size calibration
│       ├── fit_background.py  polynomial backdrop fit + card-fill gradients
│       └── extract_icons.py   alpha-keyed transparent icon PNGs
└── plugin/
    └── open-design.json       manifest for the Open Design registry route
```

## Requirements

- **Python 3.10+** with `python-pptx`, `Pillow`, `numpy`, `scipy`, `pymupdf`
  ```bash
  python3 -m venv .venv
  .venv/bin/pip install python-pptx Pillow numpy scipy pymupdf
  ```
- For **HTML sources**: Playwright, required by the DOM fast path and used by the
  raster route when present
  ```bash
  .venv/bin/pip install playwright && .venv/bin/playwright install chromium
  ```
  The raster route alone can instead fall back to any local Google Chrome /
  Chromium / Edge, which needs no extra install.
- **macOS** for the Open Design installer path (skill directories live under
  `~/Library/Application Support/Open Design/…`). The skill itself is portable.
- Optional, for the verification step: **LibreOffice** (`soffice`).

## Limitations

- **Fonts must be installed where the PPTX is opened.** The decks this was built
  against use *Titillium Web* and *Source Sans 3* (both free, Google Fonts).
  Without them PowerPoint substitutes and line widths shift.
- The backdrop and icons stay raster. That is deliberate — it is what keeps the
  fidelity high.
- Built for **single-slide or few-slide brand decks**, not 200-page documents.
- The HTML fast path covers the common CSS vocabulary (solid and linear-gradient
  fills, borders, radii, text runs, inline SVG). Decks that lean on transforms,
  radial gradients, box-shadows or blend modes want the raster route. If the HTML
  slide is not 16:9, build the PPTX at the matching slide size.
- `plugin/open-design.json` follows Open Design's `plugin.v1.json` schema but has
  not been validated by their `od plugin validate` tooling, which is not part of
  the shipped CLI.

## License

MIT — see [LICENSE](LICENSE).
