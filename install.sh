#!/usr/bin/env bash
# Install the "image-pdf-to-pptx" skill into Open Design.
#
#   ./install.sh                 install into every Open Design namespace found
#   ./install.sh --namespace release-stable
#   ./install.sh --dry-run       show what would happen, change nothing
#   ./install.sh --check         only check Python dependencies
#   ./install.sh --uninstall     remove the skill
#
set -eu

SKILL_NAME="image-pdf-to-pptx"
APP_ROOT="$HOME/Library/Application Support/Open Design"
NAMESPACES_DIR="$APP_ROOT/namespaces"

NAMESPACE=""
DRY_RUN=0
CHECK_ONLY=0
DO_UNINSTALL=0

usage() {
  cat <<'EOF'
Install the "image-pdf-to-pptx" skill into Open Design.

Usage: ./install.sh [options]

Options:
  --namespace NAME   Only install into this namespace (e.g. release-stable).
                     Default: every namespace found under
                     "~/Library/Application Support/Open Design/namespaces".
  --dry-run          Print the actions without writing anything.
  --check            Only report Python dependency status, then exit.
  --uninstall        Remove the skill from the selected namespace(s).
  -h, --help         Show this help.

After installing, restart (or refresh) Open Design so it rescans its skill
directories, then ask for something like "convert this slide PDF to an
editable PPTX".
EOF
}

die() { printf 'error: %s\n' "$1" >&2; exit 1; }

while [ $# -gt 0 ]; do
  case "$1" in
    --namespace) [ $# -ge 2 ] || die "--namespace needs a value"; NAMESPACE="$2"; shift 2 ;;
    --dry-run)   DRY_RUN=1; shift ;;
    --check)     CHECK_ONLY=1; shift ;;
    --uninstall) DO_UNINSTALL=1; shift ;;
    -h|--help)   usage; exit 0 ;;
    *)           printf 'unknown option: %s\n\n' "$1" >&2; usage; exit 2 ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SRC="$SCRIPT_DIR/skill"

check_python() {
  printf '\nPython dependency check (needed when the skill actually runs)\n'
  if ! command -v python3 >/dev/null 2>&1; then
    printf '  python3      MISSING - install Python 3.10+ first\n'
    return 0
  fi
  printf '  python3      %s\n' "$(python3 -c 'import sys;print(".".join(map(str,sys.version_info[:3])))' 2>/dev/null || echo present)"
  for mod in pptx PIL numpy scipy fitz; do
    if python3 -c "import $mod" >/dev/null 2>&1; then
      printf '  %-12s ok\n' "$mod"
    else
      printf '  %-12s MISSING\n' "$mod"
    fi
  done
  printf '\n  Fix any MISSING with:\n'
  printf '    python3 -m venv ~/.od-skills/image-pdf-to-pptx/.venv\n'
  printf '    ~/.od-skills/image-pdf-to-pptx/.venv/bin/pip install python-pptx Pillow numpy scipy pymupdf\n'

  printf '\nHTML source support (optional - only needed for .html slides)\n'
  if python3 -c "import playwright" >/dev/null 2>&1; then
    printf '  playwright   ok (exact element clips)\n'
  else
    printf '  playwright   MISSING - falls back to a local Chrome/Chromium\n'
  fi
  if [ -x "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" ]; then
    printf '  chrome       ok\n'
  else
    printf '  chrome       not found in /Applications\n'
  fi
}

check_python

if [ "$CHECK_ONLY" -eq 1 ]; then
  exit 0
fi

if [ "$DO_UNINSTALL" -eq 0 ]; then
  [ -f "$SRC/SKILL.md" ] || die "skill payload not found at $SRC/SKILL.md"
  [ -d "$SRC/scripts" ] || die "skill scripts not found at $SRC/scripts"
fi

[ -d "$NAMESPACES_DIR" ] || die "Open Design data not found at:
  $NAMESPACES_DIR
Run the Open Design app once, then re-run this installer."

TARGETS=""
if [ -n "$NAMESPACE" ]; then
  TARGETS="$NAMESPACES_DIR/$NAMESPACE/data/skills"
else
  for ns in "$NAMESPACES_DIR"/*; do
    [ -d "$ns/data" ] || continue
    TARGETS="$TARGETS
$ns/data/skills"
  done
fi

[ -n "$TARGETS" ] || die "no Open Design namespaces with a data directory were found under:
  $NAMESPACES_DIR"

if [ "$DRY_RUN" -eq 1 ]; then
  printf '\nDRY RUN - nothing will be written\n'
fi

if [ "$DO_UNINSTALL" -eq 1 ]; then
  printf '\nUninstalling %s\n' "$SKILL_NAME"
else
  printf '\nInstalling %s\n' "$SKILL_NAME"
fi

printf '%s\n' "$TARGETS" | while IFS= read -r target; do
  [ -n "$target" ] || continue
  dest="$target/$SKILL_NAME"
  if [ "$DO_UNINSTALL" -eq 1 ]; then
    if [ -d "$dest" ]; then
      printf '  remove  %s\n' "$dest"
      [ "$DRY_RUN" -eq 1 ] || rm -rf "$dest"
    else
      printf '  absent  %s\n' "$dest"
    fi
    continue
  fi
  printf '  install %s\n' "$dest"
  if [ "$DRY_RUN" -eq 1 ]; then
    continue
  fi
  mkdir -p "$dest"
  cp "$SRC/SKILL.md" "$dest/SKILL.md"
  rm -rf "$dest/scripts"
  cp -R "$SRC/scripts" "$dest/scripts"
  find "$dest" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
done

if [ "$DRY_RUN" -eq 1 ]; then
  printf '\nDry run complete. Re-run without --dry-run to apply.\n'
  exit 0
fi

if [ "$DO_UNINSTALL" -eq 1 ]; then
  printf '\nRemoved. Restart Open Design to refresh its skill list.\n'
  exit 0
fi

cat <<'EOF'

Installed.

Next steps
  1. Restart Open Design (or refresh its skill list).
  2. Ask for something like:
       "convert this slide PDF to an editable PPTX"
     Triggers: pdf to pptx / editable pptx / image-only pdf / scanned slide pdf /
               pdf has no text layer / make this slide editable
  3. The skill needs Python packages (python-pptx, Pillow, numpy, scipy, pymupdf)
     in whatever interpreter runs it. See the dependency check above.

Uninstall with: ./install.sh --uninstall
EOF
