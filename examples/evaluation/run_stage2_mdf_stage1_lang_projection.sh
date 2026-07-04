#!/usr/bin/env bash
set -euo pipefail

# Audit gold Stage 2 MDF field-value provenance against Stage 1 lang-script spans.
#
# This does not evaluate predictions. It aligns gold Stage 2 MDF field values
# (marker codes excluded) back to gold Stage 1 flat OCR + page_<N>_lang.json and
# writes durable per-page JSON artifacts plus a detailed projection CSV. It runs
# over every dataset page that has:
#
#   dataset/MUDIDI/dictionaries/<Dictionary>/Stage 2 MDF file/page_<N>/page_<N>.mdf.txt
#   dataset/MUDIDI/dictionaries/<Dictionary>/Stage 1 Gold OCR/page_<N>/page_<N>_stage1_GOLD_flat.txt
#   dataset/MUDIDI/dictionaries/<Dictionary>/Stage 1 Gold OCR/page_<N>/page_<N>_lang.json
#
# Usage:
#   bash examples/evaluation/run_stage2_mdf_stage1_lang_projection.sh
#   OUTPUT_DIR=evaluations/tmp_projection bash examples/evaluation/run_stage2_mdf_stage1_lang_projection.sh
#
# Optional: restrict to a subset by editing LANGUAGES below.

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${PROJECT_ROOT}"
export PYTHONPATH="${PROJECT_ROOT}/src:${PYTHONPATH:-}"

DATASET_DIR="${DATASET_DIR:-${PROJECT_ROOT}/dataset/MUDIDI/dictionaries}"
OUTPUT_DIR="${OUTPUT_DIR:-${PROJECT_ROOT}/evaluations/stage2_mdf_stage1_lang_projection}"
OUTPUT_CSV="${OUTPUT_CSV:-${OUTPUT_DIR}/stage2_mdf_stage1_lang_projection.csv}"
FAIL_ON_UNMAPPED="${FAIL_ON_UNMAPPED:-1}"
WRITE_DATASET_JSON="${WRITE_DATASET_JSON:-1}"

# Leave empty to audit every dictionary discovered under DATASET_DIR.
LANGUAGES=()

mkdir -p "${OUTPUT_DIR}"

ARGS=(
    --dataset-dir "${DATASET_DIR}"
    --output-csv "${OUTPUT_CSV}"
)

if [[ "${FAIL_ON_UNMAPPED}" == "1" ]]; then
    ARGS+=(--fail-on-unmapped)
fi
if [[ "${WRITE_DATASET_JSON}" == "1" ]]; then
    ARGS+=(--write-dataset-json)
fi

if [[ "${#LANGUAGES[@]}" -gt 0 ]]; then
    for language in "${LANGUAGES[@]}"; do
        [[ -n "${language}" ]] || continue
        ARGS+=(--dictionary "${language}")
    done
fi

uv run python -m mudidi.evaluation.stage2.mdf_stage1_projection "${ARGS[@]}"

echo ""
echo "Detailed projection CSV: ${OUTPUT_CSV}"
if [[ "${WRITE_DATASET_JSON}" == "1" ]]; then
    echo "Per-page JSON files:   ${DATASET_DIR}/<Dictionary>/Stage 2 MDF file/page_<N>/page_<N>_mdf_lang_projection.json"
fi
