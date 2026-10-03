# Install

## Quick start (Open Design)

```bash
git clone https://github.com/esignoretti/PDF-to-editable-PPTX.git
cd PDF-to-editable-PPTX
./install.sh --dry-run     # preview, writes nothing
./install.sh               # install
```

Then **restart Open Design** (or refresh its skill list) and ask for something like:

> "Convert this slide PDF to an editable PPTX — it has no text layer."

## What the installer does

It copies `skill/SKILL.md` and `skill/scripts/` into the user skills directory of
every Open Design namespace it finds:

```
~/Library/Application Support/Open Design/namespaces/<namespace>/data/skills/image-pdf-to-pptx/
```

Options:

| Flag | Effect |
|---|---|
| `--namespace release-stable` | install into one namespace only |
| `--dry-run` | print the actions, write nothing |
| `--check` | only report Python dependency status |
| `--uninstall` | remove the skill from the selected namespace(s) |
| `-h`, `--help` | usage |

It is idempotent — re-running updates the skill in place.

## Manual install

```bash
DEST="$HOME/Library/Application Support/Open Design/namespaces/release-stable/data/skills/image-pdf-to-pptx"
mkdir -p "$DEST"
cp skill/SKILL.md "$DEST/"
cp -R skill/scripts "$DEST/"
```

Adjust `release-stable` if you run a different channel. Namespace directories live
under `~/Library/Application Support/Open Design/namespaces/`.

## Dependencies

The skill runs Python, so these must be importable by whatever interpreter the agent
uses:

```bash
python3 -m venv ~/.od-skills/image-pdf-to-pptx/.venv
~/.od-skills/image-pdf-to-pptx/.venv/bin/pip install python-pptx Pillow numpy scipy pymupdf
```

Check what is missing at any time:

```bash
./install.sh --check
```

For **HTML sources**, a renderer. Playwright gives exact element clips:

```bash
~/.od-skills/image-pdf-to-pptx/.venv/bin/pip install playwright
~/.od-skills/image-pdf-to-pptx/.venv/bin/playwright install chromium
```

or rely on a local Google Chrome / Chromium / Edge, which needs no extra install.

Optional, only for the skill's self-verification step: **LibreOffice** (`soffice`).
The skill renders its own PPTX back to an image and diffs it against the source, and
it needs `FONTCONFIG_PATH` set so LibreOffice does not silently substitute fonts.

## Verify it loaded

1. The folder `image-pdf-to-pptx` should exist under
   `…/namespaces/<ns>/data/skills/`.
2. `SKILL.md` must start with a `---` frontmatter block containing `name:`,
   `description:` and `triggers:`.
3. After a restart the skill appears with your other skills, and the triggers above
   activate it.

## Update

```bash
cd PDF-to-editable-PPTX
git pull
./install.sh
```

## Uninstall

```bash
./install.sh --uninstall
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| `Open Design data not found` | Launch Open Design once, then re-run the installer |
| Skill not listed after install | Restart Open Design; confirm the folder sits under `…/namespaces/<ns>/data/skills/` |
| `ModuleNotFoundError: pptx` / `fitz` | Install the Python deps in the interpreter the agent uses; run `./install.sh --check` |
| Output fonts look substituted | Install *Titillium Web* and *Source Sans 3*; for verification set `FONTCONFIG_PATH=/opt/homebrew/etc/fonts` |
| Skill installed but never triggers | Ask explicitly: "convert this slide PDF to an editable PPTX" |
| HTML deck renders the wrong slide | `render_html.py deck.html --list-slides` then `--mode slide --slide N` |
| HTML render is blurry / wrong scale | Pass `--scale 2`; the pipeline wants ~3840 px wide |
| Wrong colours reproduced | You are matching a broken PDF thumbnail; the skill samples the extracted raster — check the source PDF really has one embedded image |

## Using it without Open Design

`skill/` is a plain skill folder. Point any agent that can read files and run Python
at it, or drive the helpers directly:

```python
import sys; sys.path.insert(0, "skill/scripts")
from pptx_helpers import roundrect, text, top_border
from measure_slide import load, edges_col, text_rows, ink_bbox, calibrate_font
from fit_background import BackgroundFit
from extract_icons import extract, contact_sheet
```

Set `OD_FONT_DIR` if your fonts are not in `~/Library/Fonts`.
