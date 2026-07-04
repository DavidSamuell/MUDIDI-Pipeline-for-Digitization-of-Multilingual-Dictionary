#!/usr/bin/env bash
set -euo pipefail

# Repair Stage 2 E2E MDF lexical drift from the Stage 1 OCR transcripts that fed
# Stage 2, then optionally evaluate the repaired benchmark tree.
#
# Usage:
#   STAGE1_EXPERIMENT=gemini31pro_flat_alpha bash examples/evaluation/run_stage2_e2e_lexical_repair.sh
#   RUN_EVAL=0 STAGE1_EXPERIMENT=gemini31pro_flat_alpha bash examples/evaluation/run_stage2_e2e_lexical_repair.sh
#
# Outputs:
#   outputs/benchmark/stage-2-e2e-lexical-repair/
#   evaluations/stage2_mdf_eval_e2e_lexical_repair/

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${PROJECT_ROOT}"
export PYTHONPATH="${PROJECT_ROOT}/src:${PYTHONPATH:-}"

STAGE1_EXPERIMENT="${STAGE1_EXPERIMENT:-gemini31pro_flat_alpha}"
PRED_ROOT="${PRED_ROOT:-${PROJECT_ROOT}/outputs/benchmark/stage-2-e2e}"
REPAIRED_ROOT="${REPAIRED_ROOT:-${PROJECT_ROOT}/outputs/benchmark/stage-2-e2e-lexical-repair}"
OUTPUT_DIR="${OUTPUT_DIR:-${PROJECT_ROOT}/evaluations/stage2_mdf_eval_e2e_lexical_repair}"
AUDIT_CSV="${AUDIT_CSV:-${OUTPUT_DIR}/stage2_mdf_lexical_repair_audit.csv}"
RUN_EVAL="${RUN_EVAL:-1}"

uv run python -m mudidi.evaluation.stage2.mdf_lexical_repair \
    --pred-root "${PRED_ROOT}" \
    --output-root "${REPAIRED_ROOT}" \
    --stage1-experiment "${STAGE1_EXPERIMENT}" \
    --audit-csv "${AUDIT_CSV}"

echo "Repaired MDF root: ${REPAIRED_ROOT}"
echo "Repair audit CSV:  ${AUDIT_CSV}"

if [[ "${RUN_EVAL}" == "1" || "${RUN_EVAL}" == "true" || "${RUN_EVAL}" == "yes" ]]; then
    E2E=1 \
    PRED_ROOT="${REPAIRED_ROOT}" \
    OUTPUT_DIR="${OUTPUT_DIR}" \
    RUN_PROJECTION=0 \
        bash examples/evaluation/run_stage2_benchmark_per_lang_script_eval.sh
fi
