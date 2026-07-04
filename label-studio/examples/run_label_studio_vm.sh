#!/usr/bin/env bash
# Populate the remote Label Studio instance on the supervisor's VM.
#
# The VM runs Label Studio from dictionary-extractor (not MUDIDI). Local Files
# root on the server: /var/www/app/dictionary-extractor/.label-studio-renders
#
# Prerequisites:
#   - SSH host Ekaterina-VM in ~/.ssh/config
#   - VM_LS_TOKEN in .env
#   - Workspace at label-studio/workspaces/<Language>/
#
# Usage:
#   bash label-studio/examples/run_label_studio_vm.sh
#   bash label-studio/examples/run_label_studio_vm.sh Hindi-Russian
#   OVERWRITE=1 bash label-studio/examples/run_label_studio_vm.sh Hindi-Russian

set -euo pipefail

cd "$(dirname "$0")/../.."

if [[ -f .env ]]; then
    set -a
    # shellcheck disable=SC1091
    source .env
    set +a
fi

LANGUAGE="${1:-Hindi-Russian}"
STORAGE_ROOT="/var/www/app/dictionary-extractor/.label-studio-renders"

export LABEL_STUDIO_TOKEN="${VM_LS_TOKEN:?Set VM_LS_TOKEN in .env}"
export LABEL_STUDIO_AUTH_SCHEME="${VM_LS_AUTH_SCHEME:-PAT}"

OVERWRITE_ARGS=()
if [[ "${OVERWRITE:-}" == "1" ]]; then
    OVERWRITE_ARGS=(--overwrite)
fi

echo "==> Ensuring render dir exists on VM (Label Studio validates before connect) ..."
ssh Ekaterina-VM mkdir -p "${STORAGE_ROOT}/${LANGUAGE}"

echo "==> Creating Label Studio project and rendering PNGs ..."
uv run python label-studio/setup.py \
    --samples-dir label-studio/workspaces \
    --languages "${LANGUAGE}" \
    --ls-url http://216.158.235.114:8080 \
    --render-dir label-studio/renders \
    --storage-root "${STORAGE_ROOT}" \
    --connect-local-storage \
    "${OVERWRITE_ARGS[@]}"

echo ""
echo "==> Rsyncing renders to VM ..."
rsync -avz --progress \
    label-studio/renders/ \
    "Ekaterina-VM:${STORAGE_ROOT}/"

echo ""
echo "==> Done. Open http://216.158.235.114:8080 to verify."
