#!/usr/bin/env bash
# Start local Label Studio and provision workspace projects.
#
# Prerequisites:
#   - Assembled workspace under label-studio/workspaces/<Lang>/
#   - LS_ACCESS_TOKEN in .env
#
# Usage:
#   bash label-studio/examples/run_label_studio_local.sh
#   bash label-studio/examples/run_label_studio_local.sh Coptic-English-Greek

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO_ROOT"

if [[ -f .env ]]; then
    set -a
    # shellcheck disable=SC1091
    source .env
    set +a
fi

LANGUAGE="${1:-Coptic-English-Greek}"
WORKSPACES_ROOT="label-studio/workspaces"
RENDER_DIR="label-studio/renders"

export LABEL_STUDIO_TOKEN="${LS_ACCESS_TOKEN:?Set LS_ACCESS_TOKEN in .env}"
export LABEL_STUDIO_AUTH_SCHEME="PAT"

LABEL_STUDIO_LOCAL_FILES_SERVING_ENABLED=true \
LABEL_STUDIO_LOCAL_FILES_DOCUMENT_ROOT="$(pwd)/${RENDER_DIR}" \
uv run --python .venv-label-studio/bin/python label-studio start --port 8080 &

LS_PID=$!
cleanup() { kill "$LS_PID" 2>/dev/null || true; }
trap cleanup EXIT INT TERM

sleep 5

uv run python label-studio/setup.py \
    --samples-dir "${WORKSPACES_ROOT}" \
    --languages "${LANGUAGE}" \
    --render-dir "${RENDER_DIR}" \
    --storage-root "$(pwd)/${RENDER_DIR}" \
    --connect-local-storage

echo "Label Studio running at http://localhost:8080 — Ctrl-C to stop."
wait "$LS_PID"
