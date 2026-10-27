#!/usr/bin/env bash
# Run once per clone to activate the openapi.json -> branded PDF auto-rebuild
# hooks (post-commit and post-merge). Safe to re-run.
set -euo pipefail
REPO_ROOT="$(git rev-parse --show-toplevel)"
for hook in post-commit post-merge; do
  ln -sf "../../scripts/git-hooks/$hook" "$REPO_ROOT/.git/hooks/$hook"
  chmod +x "$REPO_ROOT/scripts/git-hooks/$hook" "$REPO_ROOT/scripts/git-hooks/rebuild_openapi_pdfs.sh"
done
echo "Installed post-commit/post-merge hooks -- they rebuild skills/ubiquity-onboarding/dist/*.pdf whenever skills/ubiquity-onboarding/references/openapi.json changes."
