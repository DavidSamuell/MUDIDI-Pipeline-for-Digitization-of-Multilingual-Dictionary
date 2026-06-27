#!/usr/bin/env bash
#
# Run the gold language span-map labelers over the dictionaries and write
# *_lang.json under annotation/outputs/<dictionary>/.
#
#   Tier 1 — deterministic script-check (no LLM)  -> the script-distinct dicts
#   Tier 2 — LLM tag-injection (gemini)           -> the same-script dicts
#
# Usage:
#   bash annotation/examples/run_labeler.sh
#   INPUT_DIR=/path/to/dictionaries bash annotation/examples/run_labeler.sh
#   TIER=2 bash annotation/examples/run_labeler.sh
#
set -euo pipefail
cd "$(dirname "$0")/../.."   # repo root, so paths below are repo-relative

# ----------------------------------------------------------------------------
# Config — edit these.
# ----------------------------------------------------------------------------
# Where the per-dictionary folders live (each has a "Stage 1 Gold OCR/" subtree).
INPUT_DIR="${INPUT_DIR:-dataset/MUDIDI/dictionaries}"

# Where *_lang.json maps are written (one subfolder per dictionary).
OUTPUT_ROOT="${OUTPUT_ROOT:-annotation/outputs}"

# Which tier(s) to run: 1, 2, or all.
TIER="${TIER:-all}"

# Tier-2 LLM model (same litellm path as the Stage 1 OCR run).
MODEL="${MODEL:-gemini/gemini-3-flash-preview}"

# Existing *_lang.json maps are skipped by default. Set OVERWRITE=1 to re-label them.
OVERWRITE="${OVERWRITE:-0}"

# Languages (dictionary folder names) to process. Leave EMPTY to process ALL.
# Each name must match a folder under INPUT_DIR, e.g. "Canala-English".
DICTIONARIES=(
  # "Canala-English"
  # "Chepang-English"
)
# ----------------------------------------------------------------------------

# Build shared arg lists. Keeping the fixed args first means the arrays are never
# empty, so "${arr[@]}" is safe under `set -u` even on macOS bash 3.2.
tier1_args=( --dictionaries-root "$INPUT_DIR" --output-root "$OUTPUT_ROOT" )
tier2_args=( --dictionaries-root "$INPUT_DIR" --output-root "$OUTPUT_ROOT"
             --model "$MODEL" )
[ "$OVERWRITE" = "1" ] && tier2_args+=( --overwrite )
if [ "${#DICTIONARIES[@]}" -gt 0 ]; then
  for d in "${DICTIONARIES[@]}"; do
    [ -n "$d" ] || continue
    tier1_args+=( --dictionary "$d" )
    tier2_args+=( --dictionary "$d" )
  done
  echo "Processing dictionaries: ${DICTIONARIES[*]}"
else
  echo "Processing ALL dictionaries (all mode)"
fi
echo "Input : $INPUT_DIR"
echo "Output: $OUTPUT_ROOT/<dictionary>/page_<N>_lang.json"
echo

if [ "$TIER" = "1" ] || [ "$TIER" = "all" ]; then
  echo ">>> Tier-1 (script-check, deterministic)"
  uv run python annotation/labelers/tier1_labeler.py "${tier1_args[@]}"
  echo
fi

if [ "$TIER" = "2" ] || [ "$TIER" = "all" ]; then
  echo ">>> Tier-2 (LLM tag-injection, model=$MODEL)"
  uv run python annotation/labelers/tier2_labeler.py "${tier2_args[@]}"
fi
