#!/usr/bin/env bash
# Export submitted OCR post-edits from Label Studio into the MUDIDI dataset gold tree.
#
# Default (--tsv): write column *_stage1_GOLD.tsv and regenerate *_stage1_GOLD_flat.txt.
# Use --flat for recent single-body projects (flat transcript in one Label Studio box).
#
# Always dry-run first:
#   bash label-studio/examples/run_sync_label_studio.sh --vm --dry-run
#
# Legacy column projects (most VM dictionaries):
#   bash label-studio/examples/run_sync_label_studio.sh --vm --dry-run Thai-Russian
#   bash label-studio/examples/run_sync_label_studio.sh --vm Thai-Russian
#
# Recent flat-body projects:
#   bash label-studio/examples/run_sync_label_studio.sh --vm --flat --dry-run Hindi-Russian

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO_ROOT"

if [[ -f .env ]]; then
    set -a
    # shellcheck disable=SC1091
    source .env
    set +a
fi

LS_URL="${LS_URL:-http://localhost:8080}"
LS_TOKEN="${LS_ACCESS_TOKEN:-${LABEL_STUDIO_TOKEN:-}}"
LS_AUTH_SCHEME="${LABEL_STUDIO_AUTH_SCHEME:-PAT}"
DATASET_DIR="${DATASET_DIR:-dataset/MUDIDI/dictionaries}"
GOLD_FORMAT="tsv"

DRY_RUN=0
USE_VM=0
LANGUAGES=()

for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=1 ;;
        --flat) GOLD_FORMAT="flat" ;;
        --tsv) GOLD_FORMAT="tsv" ;;
        --vm)
            USE_VM=1
            LS_URL="http://216.158.235.114:8080"
            LS_TOKEN="${VM_LS_TOKEN:-}"
            LS_AUTH_SCHEME="${VM_LS_AUTH_SCHEME:-PAT}"
            ;;
        *)
            LANGUAGES+=("$arg")
            ;;
    esac
done

if [[ -z "$LS_TOKEN" ]]; then
    echo "Set LS_ACCESS_TOKEN (local) or VM_LS_TOKEN (--vm) in .env" >&2
    exit 1
fi

ARGS=(
    --dataset-dir "$DATASET_DIR"
    --gold-format "$GOLD_FORMAT"
    --ls-url "$LS_URL"
    --ls-token "$LS_TOKEN"
    --ls-auth-scheme "$LS_AUTH_SCHEME"
)

if [[ "$DRY_RUN" -eq 1 ]]; then
    ARGS+=(--dry-run)
fi

if ((${#LANGUAGES[@]} > 0)); then
    ARGS+=(--languages "${LANGUAGES[@]}")
fi

uv run python label-studio/sync_from_label_studio.py "${ARGS[@]}"
