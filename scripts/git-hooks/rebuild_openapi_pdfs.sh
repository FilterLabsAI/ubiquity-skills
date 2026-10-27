#!/usr/bin/env bash
# Shared logic for the post-commit/post-merge hooks below. Rebuilds the
# branded API PDFs whenever skills/ubiquity-onboarding/references/openapi.json
# changed in the commits that just landed, and amends/commits the regenerated
# PDFs back into the repo.
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

SPEC="skills/ubiquity-onboarding/references/openapi.json"
CONTENT="skills/ubiquity-onboarding/references/pdf-content.json"
LOGO="skills/ubiquity-onboarding/references/pdf-logo.png"
DIST="skills/ubiquity-onboarding/dist"
BUILDER_DIR="skills/openapi-branded-pdf/scripts"
VENV_DIR="$REPO_ROOT/.venv-openapi-pdf"   # gitignored, not committed

# PREV_HEAD is passed by the calling hook (empty for post-commit = parent of HEAD).
DEFAULT_PREV_HEAD="HEAD@{1}"
PREV_HEAD="${1:-$DEFAULT_PREV_HEAD}"

if ! git diff --name-only "$PREV_HEAD" HEAD -- "$SPEC" | grep -q .; then
  exit 0   # spec didn't change in this commit/merge -- nothing to do
fi

echo "[openapi-pdf-hook] $SPEC changed -- rebuilding branded PDFs"

# Need Python 3.10+ for the pinned reportlab release. Find one, reuse a
# private venv across runs so this stays fast.
PYBIN=""
for cand in python3.12 python3.11 python3.10 /opt/homebrew/bin/python3.12 /opt/homebrew/bin/python3.11; do
  if command -v "$cand" >/dev/null 2>&1; then PYBIN="$(command -v "$cand")"; break; fi
done
if [ -z "$PYBIN" ]; then
  echo "[openapi-pdf-hook] WARNING: no Python 3.10+ found -- skipping PDF rebuild. Run manually once a suitable interpreter is available." >&2
  exit 0
fi

if [ ! -x "$VENV_DIR/bin/python" ]; then
  "$PYBIN" -m venv "$VENV_DIR"
  "$VENV_DIR/bin/pip" install --quiet --upgrade pip reportlab
fi

mkdir -p "$DIST"
"$VENV_DIR/bin/python" "$BUILDER_DIR/build_api_pdf.py" \
  --spec "$SPEC" --content "$CONTENT" --mode overview --logo "$LOGO" \
  --out "$DIST/Overview.pdf"
"$VENV_DIR/bin/python" "$BUILDER_DIR/build_api_pdf.py" \
  --spec "$SPEC" --content "$CONTENT" --mode detailed --logo "$LOGO" \
  --out "$DIST/Detailed.pdf"

if ! git diff --quiet -- "$DIST"; then
  git add "$DIST"
  git commit -m "Auto-rebuild branded API PDFs (openapi.json changed)" -- "$DIST"
  echo "[openapi-pdf-hook] committed regenerated PDFs"
else
  echo "[openapi-pdf-hook] rebuild produced no diff (PDFs already current)"
fi
