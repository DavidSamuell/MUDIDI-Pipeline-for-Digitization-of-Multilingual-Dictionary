#!/usr/bin/env bash
set -euo pipefail

# End-to-end Stage 2 benchmark: predicted Stage 1 OCR → Stage 2 MDF.
#
# Requires migrated Stage 1 benchmark outputs under outputs/benchmark/stage-1/
# (see scripts/migrate_legacy_outputs.py) or a fresh Stage 1 benchmark run.
# Stage 1 predictions are copied from the benchmark tree into this output root,
# then Stage 2 runs with --stage1-source predictions (never gold OCR).
#
# Usage:
#   STAGE1_EXPERIMENT=gemini31pro_flat_alpha bash examples/benchmark/run_stage2_e2e.sh
#   STAGE1_EXPERIMENT=gemini31pro_flat_noalpha bash examples/benchmark/run_stage2_e2e.sh --overwrite
#
# Outputs:
#   outputs/benchmark/stage-2-e2e/<language>/stage-2/<experiment>_from_<STAGE1_EXPERIMENT>/
#
# Evaluate:
#   bash examples/evaluation/run_stage2_e2e_eval.sh

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${PROJECT_ROOT}"
export PYTHONPATH="${PROJECT_ROOT}/src:${PYTHONPATH:-}"

SAMPLES_DIR="${SAMPLES_DIR:-${PROJECT_ROOT}/dataset/MUDIDI/dictionaries}"
STAGE1_PRED_ROOT="${STAGE1_PRED_ROOT:-${PROJECT_ROOT}/outputs/benchmark/stage-1}"
DATASET_DIR="${DATASET_DIR:-${PROJECT_ROOT}/dataset/MUDIDI/dictionaries}"
OUTPUT_ROOT="${OUTPUT_ROOT:-${PROJECT_ROOT}/outputs/benchmark/stage-2-e2e}"
STAGE1_EXPERIMENT="${STAGE1_EXPERIMENT:-}"
STAGE2_EXPERIMENT_SUFFIX="${STAGE2_EXPERIMENT_SUFFIX:-}"
STAGE2_REASONING="${STAGE2_REASONING:-high}"
TOOLBOX_PDF="${TOOLBOX_PDF:-assets/Pages from ToolboxReferenceManual.pdf}"
EXTRACT_EXTRA_ARGS=("$@")

if [[ -z "${STAGE1_EXPERIMENT}" ]]; then
    echo "ERROR: set STAGE1_EXPERIMENT to a Stage 1 experiment name (e.g. gemini31pro_flat_alpha)." >&2
    exit 1
fi

if [[ -z "${STAGE2_EXPERIMENT_SUFFIX}" ]]; then
    STAGE2_EXPERIMENT_SUFFIX="from_${STAGE1_EXPERIMENT}"
fi

LANGUAGES=(
    Evenki-Russian
    Chukchi-Russian
    Nahuatl-French
    Na-English-Chinese-French
    Kashmiri-English
    Tiri-English
    Greek-English
    Efik-English
    Circassian-English-Turkish
    "Iñupiatun Eskimo-English"
)

GEMINI_PRO_MODEL="gemini/gemini-3.1-pro-preview"
GPT55_MODEL="openrouter/openai/gpt-5.5"
CLAUDE_OPUS47_MODEL="openrouter/anthropic/claude-opus-4.7"
QWEN3_VL_MODEL="openrouter/qwen/qwen3-vl-235b-a22b-instruct"

find_intro_path() {
    local entry_dir="$1"
    local candidate
    for candidate in \
        "${entry_dir}/introduction" \
        "${entry_dir}/Introduction" \
        "${entry_dir}/intro" \
        "${entry_dir}/Intro" \
        "${entry_dir}/preface" \
        "${entry_dir}/Preface"; do
        if [[ -e "${candidate}" ]]; then
            echo "${candidate}"
            return 0
        fi
    done
    return 1
}

prepare_stage1_predictions() {
    local language="$1"
    local src="${STAGE1_PRED_ROOT}/${language}/stage-1/${STAGE1_EXPERIMENT}"
    local dest="${OUTPUT_ROOT}/${language}/stage-1/${STAGE1_EXPERIMENT}"

    if [[ ! -d "${src}" ]]; then
        echo "WARNING: ${language}: missing Stage 1 predictions at ${src}; skipping." >&2
        return 1
    fi

    mkdir -p "${dest}"
    rsync -a --delete "${src}/" "${dest}/"
    echo "Prepared ${language}: Stage 1 slot ${STAGE1_EXPERIMENT}"
}

run_stage2() {
    local model="$1"
    local experiment="$2"
    shift 2
    experiment="${experiment}_${STAGE2_EXPERIMENT_SUFFIX}"

    local language entry_dir pages_dir output_dir config_file intro_path
    local -a intro_args

    for language in "${LANGUAGES[@]}"; do
        entry_dir="${DATASET_DIR}/${language}"
        pages_dir="${entry_dir}/Dictionary pages"
        output_dir="${OUTPUT_ROOT}/${language}"
        config_file="${entry_dir}/dictionary_languages.yaml"
        intro_args=()

        if ! prepare_stage1_predictions "${language}"; then
            continue
        fi
        if [[ ! -d "${pages_dir}" ]]; then
            echo "WARNING: ${language}: missing pages dir: ${pages_dir}; skipping." >&2
            continue
        fi
        if [[ ! -f "${config_file}" ]]; then
            echo "WARNING: ${language}: missing dictionary_languages.yaml; skipping." >&2
            continue
        fi
        if intro_path="$(find_intro_path "${entry_dir}")"; then
            intro_args=(--intro "${intro_path}")
        fi

        echo ""
        echo "------------------------------------------------------------"
        echo " ${language}"
        echo " Stage 1 slot: ${STAGE1_EXPERIMENT} (predictions)"
        echo " Stage 2 slot: ${experiment}"
        echo " Output dir:   ${output_dir}"
        echo "------------------------------------------------------------"

        if ! uv run mudidi run \
            --benchmark \
            --strategy two_stage \
            --stage 2 \
            --stage-2-pass-1-model "${model}" \
            --stage-2-pass-2-model "${model}" \
            --stage2-reasoning "${STAGE2_REASONING}" \
            --pages "${pages_dir}" \
            --output-dir "${output_dir}" \
            --dictionary-languages "${config_file}" \
            "${intro_args[@]}" \
            --toolbox-pdf "${TOOLBOX_PDF}" \
            --one-page-per-entry \
            --stage1-source predictions \
            --stage1-input flat \
            --experiment-name "${STAGE1_EXPERIMENT}" \
            --stage2-experiment-name "${experiment}" \
            "$@" \
            "${EXTRACT_EXTRA_ARGS[@]}"; then
            echo "WARNING: ${language}: stage-2 experiment ${experiment} failed or was skipped; continuing." >&2
        fi
    done
}

run_stage2_matrix() {
    local model="$1"
    local slug="$2"

    run_stage2 "${model}" "${slug}_${STAGE2_REASONING}_mdf_intro_notoolbox"
    run_stage2 "${model}" "${slug}_${STAGE2_REASONING}_mdf_intro_toolbox" \
        --toolbox-pdf "${TOOLBOX_PDF}"
    run_stage2 "${model}" "${slug}_${STAGE2_REASONING}_mdf_nointro_notoolbox" \
        --no-intro
    run_stage2 "${model}" "${slug}_${STAGE2_REASONING}_mdf_nointro_toolbox" \
        --no-intro \
        --toolbox-pdf "${TOOLBOX_PDF}"
}

run_stage2_matrix "${GEMINI_PRO_MODEL}" "gemini31pro"
run_stage2_matrix "${GPT55_MODEL}" "gpt55"
run_stage2_matrix "${CLAUDE_OPUS47_MODEL}" "claudeopus47"
run_stage2_matrix "${QWEN3_VL_MODEL}" "qwen3vl235"
