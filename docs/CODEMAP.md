# MUDIDI Codemap

Generated: 2026-06-22
Repo head: `8bf0605 feat(llm): enhance parse rules handling with usage tracking`

## Purpose

MUDIDI is a Python package and CLI for dictionary OCR and MDF extraction. It supports:

- Stage 1 transcription from page images/PDF pages into flat text or column TSV.
- Stage 2 MDF generation in two passes: parse-rule discovery, then per-page Toolbox MDF.
- Benchmark and inference modes.
- Multiple OCR/VLM backends and evaluation suites for Stage 1 and Stage 2.

## Runtime Shape

- Package root: `src/mudidi/`
- CLI executable: `mudidi = mudidi.cli.main:main`
- Main user command: `mudidi run`
- Evaluation commands: `mudidi eval stage1`, `mudidi eval stage2`
- Project runner: use `uv run`, not bare `python`/`pip`.
- Prompt bundle: `assets/PROMPT.json`, packaged into `mudidi/assets/PROMPT.json`.

## Primary Flow

1. `src/mudidi/cli/main.py`
   - Builds the top-level CLI.
   - Dispatches `run` and `eval` subcommands.

2. `src/mudidi/cli/run.py`
   - Defines the public `mudidi run` argument surface.
   - Validates PDF page arguments.
   - Configures prompt files.
   - Adapts modern CLI args into the legacy extraction driver.

3. `src/mudidi/cli/extract.py`
   - Main extraction driver.
   - Materializes page inputs from snippets or source PDFs.
   - Collects intro/alphabet/OCR-hint context.
   - Builds strategy objects.
   - Writes run config, manifests, usage summaries, Stage 1 outputs, Stage 2 outputs.
   - Handles benchmark vs inference layouts.

4. `src/mudidi/extraction/llm_two_stage.py`
   - Default full LLM strategy.
   - Stage 1: structured transcription.
   - Stage 2 Pass 1: parse-rule/MDF marker discovery.
   - Stage 2 Pass 2: direct MDF generation.
   - Tracks per-stage token/cost/elapsed usage.

5. `src/mudidi/llm/client.py`
   - Central litellm wrapper.
   - Applies provider-specific API key lookup, reasoning controls, retry/backoff, prompt cache keys, temperature handling, structured responses, and usage extraction.

6. `src/mudidi/llm/pass_1.py`
   - Discovers, loads, or reuses parse rules and field cheatsheets.
   - Supports single-page and multi-sample Pass 1.

7. `src/mudidi/llm/pass_2.py`
   - Builds Stage 2 direct-MDF prompts.
   - Handles toolbox file/media parts, neighbor context, prompt caching boundaries, and MDF extraction calls.

## Major Directories

### `src/mudidi/cli/`

Command-line entry points and command adapters.

- `main.py`: top-level command dispatch.
- `run.py`: public `mudidi run` interface.
- `extract.py`: full extraction orchestration.
- `evaluate_stage1.py`: Stage 1 benchmark CLI.
- `evaluate_stage2_mdf.py`: Stage 2 MDF benchmark CLI.
- `model_args.py`: shared model argument parsing and forwarding.

### `src/mudidi/config/`

Run configuration and output layout.

- `run_config.py`: `RunConfig`, stage parsing, stage helper predicates.
- `output_paths.py`: output layout helpers for Stage 1 and Stage 2 paths.
- `prompt_cache.py`: prompt/media cache configuration.

### `src/mudidi/extraction/`

Extraction strategy layer.

- `base.py`: `ExtractionStrategy` interface.
- `llm_two_stage.py`: default two-stage LLM pipeline.
- `vlm_ocr.py`: Stage 1-only VLM/OCR batch runner.
- `sample_entry.py`: sample-entry validation and benchmark preflight.

### `src/mudidi/llm/`

LLM prompt assembly and provider client code.

- `client.py`: litellm completion wrapper, retries, provider settings, usage.
- `pass_1.py`: parse-rule and cheatsheet discovery/loading.
- `pass_2.py`: direct MDF prompt construction and extraction.
- `prompt_store.py`: prompt JSON loading and rendering.
- `prompts.py`: Stage 1 prompt fragments and neighbor context helpers.
- `prompt_mode.py`: prompt ID selection by prompt mode.

### `src/mudidi/ocr/`

OCR backend abstractions, adapters, Mathpix conversion, and VLM runners.

- `base.py`: `OCRBackend` interface.
- `mathpix.py`, `mathpix_convert.py`: Mathpix integration.
- `adapters/`: converts backend outputs into flat Stage 1 text.
- `vlm/`: VLM OCR runner specs, page materialization, and local server managers.

### `src/mudidi/evaluation/stage1/`

Stage 1 flat transcription evaluation.

- `flat_evaluator.py`: `FlatStage1Evaluator`.
- `alignment.py`, `quick_match.py`: line alignment and fuzzy matching.
- `character_quality.py`: character metrics.
- `markup_quality.py`, `tag_parser.py`, `normalize_typography.py`: tag/typography evaluation.
- `read_order.py`: read-order metrics.
- `stage1_eval_cache.py`: content-fingerprint cache.
- `stage1_reports.py`: report writing.

### `src/mudidi/evaluation/stage2/`

Stage 2 MDF evaluation.

- `mdf_evaluator.py`: `MdfEvaluator`.
- `mdf_parser.py`: MDF field/record parser.
- `mdf_align.py`: record and line alignment.
- `mdf_marker_equiv.py`: marker equivalence lookup.
- `mdf_metrics.py`: metric data models.
- `mdf_similarity.py`: value similarity.

### `src/mudidi/schemas/`

Pydantic and domain schemas.

- `entry.py`: dictionary entries, pages, and transcription response schemas.
- `field_map.py`: field-map prompt schema.
- `field_cheatsheet.py`: marker cheatsheet schema.
- `dictionary_languages.py`: source/target language config.
- `ocr_result.py`: OCR page/block/line/bounding-box schemas.
- `entry_numbers.py`: entry number normalization.

### `src/mudidi/utils/`

Shared IO, PDF, text, context, MDF, and language helpers.

- `pdf_split.py`, `pdf_render.py`: PDF page extraction/rendering.
- `page_context.py`: neighbor-page text/image context.
- `stage1_input.py`: Stage 1 transcript path resolution and loading.
- `stage2_direct_mdf_io.py`: Stage 2 MDF output writing and comparison logging.
- `stage2_page_selection.py`: Stage 2 page listing/sorting/selection.
- `parse_rules_pages.py`: Pass 1 sample-page selection.
- `dictionary_languages.py`: infer/write/load dictionary language config.
- `image.py`: image/file content parts for LLM calls.
- `mdf_export.py`, `mdf_compare.py`: MDF normalization, export, validation, comparison.
- `io.py`, `text.py`: generic file/text helpers.

## Data And Output Concepts

- Inference mode expects page inputs and an output directory.
- Benchmark mode expects sample layouts or benchmark page inputs.
- Stage 1 can emit:
  - `flat`: `.txt`, default for inference.
  - `column`: `.tsv`, used where column structure matters.
- Stage 2 stores:
  - `parse-rules.json`
  - parse-rule usage metadata
  - per-page MDF text
  - run manifests/config/usage summaries.
- `--stage` controls `1`, `2`, `all`, `2-pass-1`, or `2-pass-2`.
- `--parse-rules-file` skips Pass 1 discovery and loads existing rules.
- `--prompt-cache auto` applies provider prompt caching where supported.

## External Integrations

- `litellm`: all LLM provider calls.
- Gemini/OpenRouter/OpenAI/Anthropic: selected by model names and environment keys.
- PyMuPDF/Pillow: PDF and image handling.
- `pdftk`: required for splitting selected PDF pages.
- Mathpix: optional OCR conversion.
- PaddleOCR / GLM / MinerU: OCR/VLM backend paths.

## Tests

Test root: `tests/`

Focused coverage currently includes:

- CLI model args and run-stage config.
- Prompt cache config.
- LLM client retry/reasoning/prompt-caching behavior.
- Pass 1 multi-sample behavior.
- Stage 1 typography prompting.
- Dictionary language utilities.
- Page context and parse-rule page selection.
- PDF rendering helpers.

Run with:

```bash
uv sync --extra dev
uv run pytest
```

Integration tests require:

```bash
MUDIDI_LLM_INTEGRATION=1
```

## Files To Open First

- For CLI behavior: `src/mudidi/cli/run.py`, then `src/mudidi/cli/extract.py`.
- For extraction behavior: `src/mudidi/extraction/llm_two_stage.py`.
- For provider/API behavior: `src/mudidi/llm/client.py`.
- For Stage 2 prompts: `src/mudidi/llm/pass_1.py`, `src/mudidi/llm/pass_2.py`.
- For schemas: `src/mudidi/schemas/entry.py`, `src/mudidi/schemas/field_cheatsheet.py`.
- For benchmark metrics: `src/mudidi/evaluation/stage1/flat_evaluator.py`, `src/mudidi/evaluation/stage2/mdf_evaluator.py`.
- For output layout: `src/mudidi/config/output_paths.py`, `src/mudidi/config/run_config.py`.

## Current High-Level Architecture

```text
mudidi CLI
  |
  +-- run.py
  |    validates public args and forwards to extract.py
  |
  +-- extract.py
       materializes inputs, config, manifests, strategy
       |
       +-- TwoStageLLMExtraction
       |    |
       |    +-- Stage 1 prompt/schema -> llm.client.complete_structured
       |    +-- Pass 1 parse-rule discovery -> llm.pass_1
       |    +-- Pass 2 direct MDF -> llm.pass_2
       |
       +-- VLM OCR strategy
            |
            +-- ocr.vlm.runner + backend specs
```

## Notes For Future Changes

- Add new extraction backends by subclassing `ExtractionStrategy`.
- Keep prompt templates in `assets/PROMPT.json` and assembly in `llm/`.
- Keep domain models in `schemas/`.
- Validate user-facing options at CLI/config boundaries.
- Preserve `uv run` workflows.
- Treat live LLM tests as integration tests only.
