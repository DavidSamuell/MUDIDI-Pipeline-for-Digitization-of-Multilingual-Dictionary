#!/usr/bin/env bash
# Build the Label Studio workspace for Coptic-English-Greek, then optionally
# provision the project on a Label Studio instance.
#
# Usage:
#   bash label-studio/examples/assemble_coptic_workspace.sh          # workspace only
#   bash label-studio/examples/assemble_coptic_workspace.sh --setup  # + create LS project

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO_ROOT"

LANGUAGE="Coptic-English-Greek"
PAGES_DIR="dataset/MUDIDI/dictionaries/${LANGUAGE}/Dictionary pages"
STAGE1_DIR="outputs/coptic-crum/stage-1"
WORKSPACES_ROOT="label-studio/workspaces"

echo "==> Assembling workspace for ${LANGUAGE} ..."
uv run python label-studio/assemble_workspace.py \
    --language "${LANGUAGE}" \
    --pages-dir "${PAGES_DIR}" \
    --stage1-dir "${STAGE1_DIR}" \
    --workspaces-root "${WORKSPACES_ROOT}"

if [[ "${1:-}" != "--setup" ]]; then
    echo ""
    echo "Workspace ready at: ${WORKSPACES_ROOT}/${LANGUAGE}"
    echo "Next: run setup.py against your Label Studio instance, e.g."
    echo "  bash label-studio/examples/run_label_studio_vm.sh   # remote VM"
    echo "  bash label-studio/examples/run_label_studio_local.sh  # local"
    exit 0
fi

if [[ -f .env ]]; then
    set -a
    # shellcheck disable=SC1091
    source .env
    set +a
fi

LS_URL="${LS_URL:-http://localhost:8080}"
export LABEL_STUDIO_TOKEN="${LABEL_STUDIO_TOKEN:-${LS_ACCESS_TOKEN:?Set LS_ACCESS_TOKEN or LABEL_STUDIO_TOKEN in .env}}"
export LABEL_STUDIO_AUTH_SCHEME="${LABEL_STUDIO_AUTH_SCHEME:-PAT}"

echo ""
echo "==> Creating Label Studio project on ${LS_URL} ..."
uv run python label-studio/setup.py \
    --samples-dir "${WORKSPACES_ROOT}" \
    --languages "${LANGUAGE}" \
    --ls-url "${LS_URL}" \
    --render-dir "label-studio/renders" \
    --storage-root "$(pwd)/label-studio/renders" \
    --connect-local-storage

echo "==> Done."
