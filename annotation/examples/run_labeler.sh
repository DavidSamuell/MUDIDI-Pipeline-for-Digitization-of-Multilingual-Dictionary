#!/usr/bin/env bash
#
# Run the gold language span-map labelers over the dictionaries and write
# *_lang.json under annotation/outputs/<dictionary>/.
#
#   Tier 1 — deterministic script-check (no LLM)  -> the script-distinct dicts
#   Tier 2 — LLM tag-injection (gemini)           -> the same-script dicts
#
# Edit the variables below, then run:
#   bash annotation/examples/run_labeler.sh
#
set -euo pipefail
cd "$(dirname "$0")/../.."   # repo root, so paths below are repo-relative

# ----------------------------------------------------------------------------
# Config — edit these directly.
# ----------------------------------------------------------------------------
# Where the per-dictionary folders live (each has a "Stage 1 Gold OCR/" subtree).
INPUT_DIR="dataset/MUDIDI/dictionaries"

# Where *_lang.json maps are written (one subfolder per dictionary).
OUTPUT_ROOT="annotation/outputs"

# Which tier(s) to run: 1, 2, or all.
TIER="2"

# Tier-2 LLM model (same litellm path as the Stage 1 OCR run).
MODEL="gemini/gemini-3.1-pro-preview"

# Reasoning effort for Tier-2 LLM calls: none, low, medium, high.
REASONING_EFFORT="high"

# Max character drift tolerated between LLM output and gold (0.0–1.0).
# Recovery always uses original gold characters; drift only affects language
# attribution accuracy. Pages above this are flagged for manual labeling.
DRIFT_GATE=0.02

# Sampling temperature (0.0–1.0). Ignored for Gemini 3+ and GPT-5 (locked to 1.0).
TEMPERATURE=0.2

# Concurrent page workers per dictionary (1 = sequential). Uses a thread pool
# over separate litellm.completion calls; the rate-limit pause is shared.
BATCH_SIZE=5

# Set to 1 to re-label pages that already have a *_lang.json (default: skip them).
OVERWRITE=1

# Dictionary folder names to process. Leave empty to process ALL.
# Each name must match a folder under INPUT_DIR, e.g. "Canala-English".
DICTIONARIES=(
  "Circassian-English-Turkish"
)
# ----------------------------------------------------------------------------

# Build shared arg lists. Keeping the fixed args first means the arrays are never
# empty, so "${arr[@]}" is safe under `set -u` even on macOS bash 3.2.
tier1_args=( --dictionaries-root "$INPUT_DIR" --output-root "$OUTPUT_ROOT" )
tier2_args=( --dictionaries-root "$INPUT_DIR" --output-root "$OUTPUT_ROOT"
             --model "$MODEL" --reasoning-effort "$REASONING_EFFORT"
             --temperature "$TEMPERATURE" --max-drift "$DRIFT_GATE"
             --batch-size "$BATCH_SIZE" )
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
  echo ">>> Tier-2 (LLM tag-injection, model=$MODEL, effort=$REASONING_EFFORT, batch=$BATCH_SIZE)"
  uv run python annotation/labelers/tier2_labeler.py "${tier2_args[@]}"
fi
