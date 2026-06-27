#!/usr/bin/env bash
#
# Start the Label Studio dashboard for reviewing the gold language NER drafts
# (the *_lang.json maps under annotation/outputs/, imported as NER tasks).
#
# Label Studio is NOT a project dependency, so this prefers a `label-studio`
# already on your PATH and otherwise runs it ephemerally via `uvx` (uv's tool
# runner; the first run downloads it). Open http://localhost:8080 when it boots.
#
# Usage:
#   bash annotation/examples/start_label_studio.sh
#   PORT=9000 bash annotation/examples/start_label_studio.sh
#
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

HOST="${HOST:-localhost}"
PORT="${PORT:-8080}"

# Keep Label Studio's SQLite DB + uploads OUT of the repo.
export LABEL_STUDIO_BASE_DATA_DIR="${LABEL_STUDIO_BASE_DATA_DIR:-$HOME/.label-studio-mudidi}"
mkdir -p "$LABEL_STUDIO_BASE_DATA_DIR"

# Let Label Studio serve the raw gold text files from local disk (the repo) so
# tasks can reference them instead of inlining every page.
export LABEL_STUDIO_LOCAL_FILES_SERVING_ENABLED="${LABEL_STUDIO_LOCAL_FILES_SERVING_ENABLED:-true}"
export LABEL_STUDIO_LOCAL_FILES_DOCUMENT_ROOT="${LABEL_STUDIO_LOCAL_FILES_DOCUMENT_ROOT:-$REPO_ROOT}"

cat <<EOF
Starting Label Studio
  url        : http://$HOST:$PORT
  data dir   : $LABEL_STUDIO_BASE_DATA_DIR
  files root : $LABEL_STUDIO_LOCAL_FILES_DOCUMENT_ROOT

Next steps once it is open:
  1. Create (or sign in to) an account and a new project.
  2. Settings > Labeling Interface: paste the per-dictionary NER config produced by
     annotation/label_studio/label_studio_ner.build_labels_config(<languages>).
  3. Import that dictionary's NER tasks (built from annotation/outputs/<dict>/*_lang.json).
  4. After review, export with: uv run python scripts/export_label_studio_gold.py
     (reads LABEL_STUDIO_URL / LABEL_STUDIO_TOKEN).
EOF
echo

if command -v label-studio >/dev/null 2>&1; then
  exec label-studio start --host "$HOST" --port "$PORT"
else
  echo "label-studio not on PATH — launching via 'uvx label-studio' (first run downloads it)…"
  exec uvx label-studio start --host "$HOST" --port "$PORT"
fi
