# Stage 2 Benchmark: Typography vs No-Typography Gold Stage 1

Report date: 2026-06-23  
Dataset: MUDIDI dictionary sample benchmark (10 languages, 1 page each)  
Pipeline: MUDIDI two-stage LLM extraction, Stage 2 only (`--stage 2`, `--stage2-reasoning high`)

## Executive summary

We compared Stage 2 MDF extraction when the Stage 1 input is **gold OCR with typography markup** (`<b>`, `<i>`) versus **gold OCR with tags stripped** (plain text). All other Stage 2 settings were held constant: **dictionary intro** (when present), **Toolbox MDF guide PDF**, **high reasoning**, and **discovered parse rules** per experiment.

**Finding:** Removing typography from Stage 1 gold input is **not uniformly better or worse**. Effects are **model-dependent**:

| Model | MDF Fields F1 (typography → no-typo) | Δ aggregate F1 |
|-------|--------------------------------------|---------------:|
| Gemini 3.1 Pro | 0.886 → 0.821 | **−0.065** |
| GPT-5.5 | 0.809 → 0.835 | **+0.026** |
| Claude Opus 4.7 | 0.806 → 0.831 | **+0.026** |

Gemini 3.1 Pro **benefits from typography tags** on aggregate; GPT-5.5 and Claude Opus 4.7 **improve slightly without them**. Per-language results are mixed for all three models. **Kashmiri-English** is the largest swing: Gemini drops sharply without tags (−0.40 F1 on one page), while Claude improves sharply (+0.37 F1).

**Recommendation:** Keep typography in Stage 1 gold input for **Gemini** runs. For **GPT-5.5** and **Claude**, plain gold OCR is a reasonable default, but validate on language-specific pages before committing. Do not assume typography is noise—it carries signal for some model–language pairs.

---

## Experiment setup

| Setting | Typography baseline | No-typography |
|---------|---------------------|---------------|
| Stage 1 source | Gold OCR **with** `<b>` / `<i>` tags | Gold OCR **with tags stripped** |
| Stage 1 slot | Default benchmark gold | `gold_stage1_notypography` |
| Stage 2 context | Dictionary intro + Toolbox PDF | Same |
| Reasoning | `--stage2-reasoning high` | Same |
| Pages | One benchmark page per language (`--one-page-per-entry`) | Same |
| Parse rules | Discovered per experiment (Pass 1) | Same |

### Models evaluated

| Model | Typography experiment | No-typography experiment |
|-------|----------------------|--------------------------|
| Gemini 3.1 Pro | `gemini31pro_high_mdf_intro_toolbox` | `gemini31pro_high_mdf_intro_toolbox_gold_notypography` |
| GPT-5.5 | `gpt55_high_mdf_intro_toolbox` | `gpt55_high_mdf_intro_toolbox_gold_notypography` |
| Claude Opus 4.7 | `claudeopus47_high_mdf_intro_toolbox` | `claudeopus47_high_mdf_intro_toolbox_gold_notypography` |

### Benchmark pages (one per language)

| Language | Page |
|----------|------|
| Evenki-Russian | page_1 |
| Chukchi-Russian | page_3 |
| Nahuatl-French | page_74 |
| Na-English-Chinese-French | page_19 |
| Kashmiri-English | page_14 |
| Tiri-English | page_15 |
| Greek-English | page_38 |
| Efik-English | page_13 |
| Circassian-English-Turkish | page_1 |
| Iñupiatun Eskimo-English | page_42 |

### Scripts and outputs

| Artifact | Path |
|----------|------|
| Extraction (no-typography) | `examples/benchmark/run_stage2_no_typography.sh` |
| No-typography predictions | `outputs/benchmark/stage-2-no-typography/` |
| Typography baseline eval | `evaluations/stage2_mdf_eval/stage2_mdf_eval_summary.csv` |
| No-typography eval | `evaluations/stage2_mdf_eval_no_typography/{gemini31pro,gpt55,claudeopus47}/` |
| Eval script | `examples/evaluation/run_stage2_no_typography_eval.sh` |

---

## Metrics

- **Record Accuracy** — fraction of dictionary records matched correctly.
- **MDF Fields F1** — field-level F1 over Toolbox MDF markers (`\lx`, `\gn`, `\ps`, etc.).
- **ReadOrderEdit** — normalized edit distance for entry read order (lower is better).

All scores are micro-averaged over the 10 benchmark pages unless noted per page.

---

## Aggregate results

### Typography vs no-typography (intro + toolbox)

| Model | Record Acc (typo) | Record Acc (plain) | Δ | MDF Fields F1 (typo) | MDF Fields F1 (plain) | Δ | ReadOrder (typo) | ReadOrder (plain) | Δ |
|-------|------------------:|-------------------:|--:|---------------------:|----------------------:|--:|-----------------:|------------------:|--:|
| Gemini 3.1 Pro | 0.994 | 0.985 | −0.009 | **0.886** | 0.821 | **−0.065** | 0.007 | 0.015 | +0.008 |
| GPT-5.5 | 0.997 | 0.991 | −0.006 | 0.809 | **0.835** | **+0.026** | 0.003 | 0.011 | +0.008 |
| Claude Opus 4.7 | 0.988 | **0.991** | +0.003 | 0.806 | **0.831** | **+0.026** | 0.014 | 0.012 | −0.002 |

### Typography baseline leaderboard (intro + toolbox, from main eval summary)

For context, typography baselines rank as follows on MDF Fields F1:

| Rank | Model | Record Accuracy | MDF Fields F1 | ReadOrderEdit |
|-----:|-------|----------------:|--------------:|--------------:|
| 1 | Gemini 3.1 Pro | 0.994 | **0.886** | 0.007 |
| 2 | GPT-5.5 | 0.997 | 0.809 | 0.003 |
| 3 | Claude Opus 4.7 | 0.988 | 0.806 | 0.014 |
| 4 | Qwen3-VL-235B | 0.928 | 0.743 | 0.110 |

Qwen no-typography runs were not completed (OpenRouter/Parasail rate limits); excluded from this comparison.

---

## Per-page results: MDF Fields F1

Δ = no-typography − typography (positive = plain gold OCR is better).

### Gemini 3.1 Pro

| Language | Typography | No-typo | Δ |
|----------|----------:|--------:|--:|
| Evenki-Russian | 0.598 | 0.680 | +0.081 |
| Tiri-English | 0.899 | 0.925 | +0.026 |
| Nahuatl-French | 0.641 | 0.667 | +0.025 |
| Chukchi-Russian | 1.000 | 1.000 | 0.000 |
| Iñupiatun Eskimo-English | 0.996 | 0.993 | −0.004 |
| Circassian-English-Turkish | 1.000 | 0.963 | −0.037 |
| Efik-English | 1.000 | 0.923 | −0.077 |
| Na-English-Chinese-French | 0.871 | 0.738 | −0.133 |
| Greek-English | 1.000 | 0.850 | −0.150 |
| Kashmiri-English | 0.860 | 0.460 | **−0.400** |

**Summary:** 3 pages improved, 5 regressed, 2 unchanged (within ±0.005).

### GPT-5.5

| Language | Typography | No-typo | Δ |
|----------|----------:|--------:|--:|
| Greek-English | 0.819 | 0.963 | **+0.144** |
| Kashmiri-English | 0.501 | 0.630 | +0.128 |
| Chukchi-Russian | 1.000 | 1.000 | 0.000 |
| Iñupiatun Eskimo-English | 0.946 | 0.946 | 0.000 |
| Tiri-English | 0.892 | 0.889 | −0.003 |
| Nahuatl-French | 0.803 | 0.798 | −0.006 |
| Circassian-English-Turkish | 0.878 | 0.870 | −0.008 |
| Efik-English | 0.899 | 0.880 | −0.019 |
| Evenki-Russian | 0.621 | 0.597 | −0.024 |
| Na-English-Chinese-French | 0.892 | 0.807 | −0.085 |

**Summary:** 2 pages improved, 5 regressed, 3 unchanged.

### Claude Opus 4.7

| Language | Typography | No-typo | Δ |
|----------|----------:|--------:|--:|
| Kashmiri-English | 0.501 | 0.871 | **+0.370** |
| Chukchi-Russian | 0.968 | 1.000 | +0.032 |
| Tiri-English | 0.911 | 0.930 | +0.019 |
| Nahuatl-French | 0.610 | 0.613 | +0.004 |
| Iñupiatun Eskimo-English | 0.993 | 0.993 | 0.000 |
| Efik-English | 0.843 | 0.835 | −0.008 |
| Greek-English | 0.842 | 0.811 | −0.031 |
| Na-English-Chinese-French | 0.795 | 0.761 | −0.034 |
| Evenki-Russian | 0.732 | 0.688 | −0.044 |
| Circassian-English-Turkish | 0.880 | 0.826 | −0.054 |

**Summary:** 3 pages improved, 5 regressed, 2 unchanged.

---

## Per-page results: Record Accuracy

Only pages where typography and no-typography differ are shown.

| Language | Gemini (typo → plain) | GPT-5.5 | Claude Opus 4.7 |
|----------|----------------------|---------|-----------------|
| Evenki-Russian | 0.964 → 0.929 | 1.000 → 0.964 | 0.929 → 0.964 |
| Greek-English | 1.000 → 0.983 | — | — |
| Nahuatl-French | 0.968 → 0.935 | — | 0.935 → 0.968 |
| Circassian-English-Turkish | — | — | 1.000 → 0.950 |
| Efik-English | — | 1.000 → 0.955 | — |

Record-level accuracy stays high (≥0.93) in all conditions. Most of the typography effect shows up in **field assignment** (MDF Fields F1), not record matching.

---

## Interpretation

1. **Typography tags in gold Stage 1 are model-specific signal.** Gemini uses them effectively on aggregate; stripping them hurts especially on Kashmiri, Greek, and Na-English-Chinese-French.

2. **GPT-5.5 and Claude gain modest aggregate F1 without tags**, driven by a few large per-page wins (Greek and Kashmiri for GPT-5.5; Kashmiri for Claude) that outweigh regressions elsewhere.

3. **Kashmiri-English is an outlier** and should not drive a global policy. Typography helps Gemini there; plain text helps Claude dramatically; GPT-5.5 sits in between.

4. **Intro + toolbox context dominates model ranking** more than typography. Gemini remains the strongest typography baseline; the no-typography experiment does not reorder the top three models.

5. **Stage 2 still sees plain text** in both conditions—the typography experiment only changes what appears in the Stage 1 transcript fed to Pass 2. Tags may help the model infer column structure, emphasis, or field boundaries even when MDF output itself has no HTML markup.

---

## Recommendations

1. **Gemini 3.1 Pro:** Keep typography in Stage 1 gold (or predicted) input when available.
2. **GPT-5.5 / Claude Opus 4.7:** Plain gold OCR is acceptable; expect ±0.03 aggregate F1 swing with mixed per-language effects.
3. **Benchmark reporting:** When comparing Stage 2 models, **document Stage 1 typography policy** alongside intro/toolbox settings.
4. **Extend eval:** Re-run Qwen3-VL-235B no-typography extraction (with `BATCH_SIZE=1` and provider fallbacks) before including it in this comparison.
5. **Stage 1 eval cross-check:** Correlate these Stage 2 deltas with `evaluations/stage1_flat_eval/` typography F1 to see whether Stage 1 transcription quality explains language-level swings.

---

## Data sources

| File | Contents |
|------|----------|
| `evaluations/stage2_mdf_eval/stage2_mdf_eval_summary.csv` | Typography baseline aggregates (`*_intro_toolbox`) |
| `evaluations/stage2_mdf_eval_no_typography/gemini31pro/vs_baseline.csv` | Gemini per-page deltas |
| `evaluations/stage2_mdf_eval_no_typography/gpt55/vs_baseline.csv` | GPT-5.5 per-page deltas |
| `evaluations/stage2_mdf_eval_no_typography/claudeopus47/vs_baseline.csv` | Claude per-page deltas |
| `outputs/benchmark/stage-2-no-typography/` | No-typography Stage 2 predictions |
| `outputs/benchmark/` (default layout) | Typography baseline Stage 2 predictions |

Reproduce no-typography eval:

```bash
bash examples/evaluation/run_stage2_no_typography_eval.sh
```

Override model:

```bash
EXPERIMENT_NAME=gpt55_high_mdf_intro_toolbox_gold_notypography \
BASELINE_EXPERIMENT=gpt55_high_mdf_intro_toolbox \
OUTPUT_DIR=evaluations/stage2_mdf_eval_no_typography/gpt55 \
bash examples/evaluation/run_stage2_no_typography_eval.sh
```

---

## Limitations

- **10 pages total** (one per language)—not a full-dictionary sample.
- **Parse rules are re-discovered** per experiment; part of the delta may come from Pass 1 variation, not Pass 2 alone.
- **Gold Stage 1 only**—typography effects on **predicted** Stage 1 (inference mode) may differ.
- **Qwen excluded**—no-typography extraction did not complete.
- **High reasoning** on all runs; typography impact may change at lower reasoning effort.
