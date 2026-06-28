# Stimson Dictionary Run: Gemini Pro vs Flash Cost and Speed Analysis

Report date: 2026-06-22  
Dataset: *Stimson 1964 — Dictionnaire* (pages 41–611, 571 dictionary pages)  
Pipeline: MUDIDI two-stage LLM extraction (`--stage2-reasoning high`, prompt caching enabled)

## Executive summary

We ran the full MUDIDI pipeline on the Stimson dictionary using **Gemini 3.5 Flash** for Stage 1 and a mixed Stage 2 configuration: **Gemini 3.1 Pro** for pages 41–137, then **Gemini 3.5 Flash** for pages 138–611. The expectation was that Flash would be substantially cheaper and faster at scale.

**Finding:** Stage 2 Pro and Flash ended up **comparable in both cost and wall-clock time** (~$0.14–0.16/page, ~73 s/page). Switching from Pro to Flash saved only **~$1.34** over 97 Pro pages (~9% per page), not the large savings implied by the “Flash” product tier name.

The main reason is **token consumption**, not list-price ignorance:

1. **Prompt caching** makes input cheap for both models (~85% of the Stage 2 prompt is cached on warm runs).
2. **Flash generates far more reasoning tokens** under `--stage2-reasoning high` — on a controlled 10-page A/B rerun, Flash averaged **11,763 reasoning tokens/page vs 7,204 for Pro** (+63%), while visible response output was the same (~1,040 tokens/page).
3. **Gemini 3.x Flash vs Pro pricing is closer** than older generations (~33% premium per token, not 5–10×).

**Recommendation:** Use **Flash for Stage 1** and either model for Stage 2; default to **Flash for Stage 2** at scale unless quality evaluation shows a Pro advantage. The cost/speed gap is small; quality should drive the choice.

---

## Experiment setup

### Full run (571 pages)

| Setting | Value |
|---------|--------|
| Pages processed | 571 (PDF pages 41–611) |
| Stage 1 model | `gemini/gemini-3.5-flash` |
| Stage 2 Pass 1 | Multi-sample parse-rules discovery → `parse-rules.json` |
| Stage 2 Pass 2 (pages 41–137) | `gemini/gemini-3.1-pro-preview` |
| Stage 2 Pass 2 (pages 138–611) | `gemini/gemini-3.5-flash` |
| Reasoning | `--stage2-reasoning high` |
| Concurrency | `--batch-size 5` |
| Prompt caching | `--prompt-cache auto` (default) |

### Spot-check A/B (10 pages, measured reasoning split)

To validate reasoning vs response token logging, we reran **the same 10 pages** through Stage 2 only on both models, reusing Stage-1 transcripts and parse-rules from the full run.

| Setting | Value |
|---------|--------|
| Pages | 100, 150, 200, 250, 300, 350, 400, 450, 500, 550 |
| Stage | `2-pass-2` only (no Stage 1 rerun) |
| Models | Pro: `gemini/gemini-3.1-pro-preview` · Flash: `gemini/gemini-3.5-flash` |
| Script | `examples/benchmark/run_stimson_reasoning_spotcheck.sh` |
| Outputs | `outputs/stimson-reasoning-spotcheck-pro/` · `outputs/stimson-reasoning-spotcheck-flash/` |

Usage is recorded per page in `*_usage.json` with `reasoning_tokens` and `response_text_tokens` extracted from Gemini `completion_tokens_details` via litellm (`src/mudidi/llm/client.py` → `_extract_usage()`).

---

## Total cost and time (full run)

| Stage | Model | Pages | Cost | LLM time (summed) |
|-------|--------|------:|-----:|------------------:|
| Stage 1 | Flash | 571 | $11.46 | ~2.5 h |
| Stage 2 | Pro (41–137) | 97 | $15.17 | ~1.8 h |
| Stage 2 | Flash (138–611) | 474 | $67.57 | ~9.6 h |
| **Total** | | **571** | **~$94** | **~13.8 h** |

With `--batch-size 5`, active wall-clock time is roughly **total LLM time ÷ 5 ≈ 2.8–3 h** for an uninterrupted run (excluding rate-limit pauses and reruns).

---

## Stage 2: Pro vs Flash head-to-head

### Cost per page (full run)

| Model | Pages | Avg cost/page | Median cost/page |
|-------|------:|--------------:|-----------------:|
| **Pro** (warm cache) | 85+ | **$0.147** | ~$0.15 |
| **Flash** | 474 | **$0.143** | ~$0.14 |

**Pro premium:** ~**9%** more per page. Over 97 Pro pages, total extra spend vs Flash pricing ≈ **$1.34**.

### Speed per page (full run)

| Model | Avg time/page | Median time/page |
|-------|--------------:|-----------------:|
| **Pro** | **73.3 s** | ~70 s |
| **Flash** | **72.8 s** | ~75 s |

**No meaningful speed advantage for either model.** Flash is faster per output token but writes more tokens; the totals cancel out.

### Reasoning vs response tokens (spot-check A/B, measured)

On the same 10 pages with identical Stage-1 input:

| Metric | Pro | Flash |
|--------|----:|------:|
| Avg **reasoning** tokens | **7,204** | **11,763** |
| Avg **response** tokens (visible MDF) | **1,063** | **1,040** |
| Avg completion tokens | **8,268** | **12,803** |
| Reasoning share of completion | **87%** | **92%** |
| Avg cost/page | $0.168 | $0.148 |
| Avg time/page | 77 s | 81 s |
| **Total cost (10 pages)** | **$1.68** | **$1.48** |

**Visible MDF output is the same size** (~1,040 response tokens/page). Stage 2 is not producing 7× more dictionary content than Stage 1; it bills **7× more completion tokens** because **`--stage2-reasoning high`** allocates most of the output budget to internal reasoning. Flash runs longer reasoning chains than Pro on this workload, which erases Flash’s per-token price and throughput advantage.

Example (page 400, same transcript, both models):

| Model | Reasoning | Response | Completion | Reasoning % |
|-------|----------:|---------:|-----------:|------------:|
| Pro | 11,239 | 1,438 | 12,677 | 89% |
| Flash | 14,908 | 1,426 | 16,334 | 91% |

### Throughput per token (spot-check)

Flash **is** faster at generating tokens:

| Model | Seconds per 1k completion tokens |
|-------|--------------------------------:|
| Pro | ~9.3 s |
| Flash | ~6.3 s |

But because Flash emits **~55% more** completion tokens per page on the same input, total page time ends up equal.

---

## Implications for scaling (100 dicts × 500 pages)

Estimated API cost with **Flash Stage 1 + Pro Stage 2**:

| Line item | Estimate |
|-----------|----------:|
| Stage 1 (Flash, 50k pages) | ~$1,000 |
| Stage 2 (Pro, 50k pages) | ~$7,800 |
| Pass 1 (Pro, 100 dicts) | ~$200 |
| **Total** | **~$9,000** |

Using Flash for Stage 2 instead of Pro saves only **~$600–700** (~7%) at this scale. The dominant cost driver is **Stage 2 page volume × ~$0.14–0.15/page**, not the Pro/Flash tier split.

For GCP calculator planning, use measured spot-check averages: **~1,040 response tokens** and **~7,200 reasoning tokens (Pro)** or **~11,800 reasoning tokens (Flash)** per Stage-2 page under high reasoning.

---

## Recommendations

1. **Default Stage 2 to Flash** for production runs unless benchmarks show Pro quality gains worth ~10% extra cost.
2. **Keep prompt caching enabled** (`--prompt-cache auto`); it is the largest cost lever for Stage 2.
3. **Treat `--stage2-reasoning high` as a cost knob**: reasoning tokens dominate completion billing (~87–92%). Evaluate `medium`/`low` if quality permits.
4. **Log Pass 1 usage** (`parse-rules_usage.json`) so discovery cost is visible in run totals.
5. **Do not assume “Flash = fast/cheap”** for reasoning-heavy structured extraction; measure `reasoning_tokens` vs `response_text_tokens` per page.

---

## Data sources

- `outputs/stimson-1964-dictionnaire/run_usage.json` — full-run aggregate
- `outputs/stimson-1964-dictionnaire/stage-{1,2}/page_*/page_*_usage.json` — full-run per-page usage
- `outputs/stimson-reasoning-spotcheck-pro/run_usage.json` — spot-check Pro aggregate
- `outputs/stimson-reasoning-spotcheck-flash/run_usage.json` — spot-check Flash aggregate
- `outputs/stimson-reasoning-spotcheck-{pro,flash}/stage-2/page_*/page_*_usage.json` — measured reasoning/response split
- Token extraction: `src/mudidi/llm/client.py` → `_extract_usage()` (`prompt_tokens_details` + `completion_tokens_details`)

---

## Limitations

- **10 early Pro pages** (41–50) lack `elapsed_seconds` in the full-run usage files; time averages use 87 timed Pro pages.
- **Pass 1 discovery** cost was not logged in the original full run; estimated at ~$1.50–2.00 per dictionary.
- **Full-run usage files** (571 pages) predate reasoning/response logging; the spot-check rerun provides measured splits for Pro vs Flash on 10 pages.
- Results are specific to **dictionary MDF extraction with high reasoning**; other tasks may show larger Pro/Flash gaps.
