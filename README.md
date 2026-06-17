# MUDIDI: A pipeline for Digitization of Multilingual Dictionary

Digitize scanned multi-lingual dictionary pages into structured lexicon records using LLMs.

MUDIDI runs a two-stage pipeline:

1. **Stage 1 — transcription** — faithful OCR of each page (Unicode, diacritics, bold/italic markup).
2. **Stage 2 — MDF export** — parse the transcript into [SIL Toolbox MDF](https://software.sil.org/toolbox/) records.

This README focuses on **running the pipeline on a new dictionary**. Benchmark and paper-reproduction instructions are at the bottom.

---

## Prerequisites

Install the tools below **before** cloning the repo. MUDIDI uses [uv](https://docs.astral.sh/uv/) to create a project virtualenv (`.venv/`) and install locked Python dependencies — you do not need to run `pip install` yourself.

### Supported platforms

| Platform    | Support                                                                                                                                                                                |
| ----------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Linux**   | Fully supported — primary development and HPC target.                                                                                                                                  |
| **macOS**   | Fully supported — same workflow as Linux.                                                                                                                                              |
| **Windows** | Use **[WSL2](https://learn.microsoft.com/en-us/windows/wsl/install)** (Ubuntu recommended), then follow the **Linux** steps below. Native Windows (PowerShell / cmd) is not supported. |

**Windows users:** install WSL2, open an Ubuntu terminal, and treat your machine as Linux for everything in this README — prerequisites, install, `uv sync`, bash scripts under `examples/`, and `pdftk`. No separate Windows commands are required.

Minimal WSL setup (run once in **PowerShell as Administrator** on Windows):

```powershell
wsl --install -d Ubuntu
```

Restart if prompted, launch **Ubuntu** from the Start menu, then continue with the Linux instructions below. Clone the repo inside your WSL home directory (e.g. `~/MUDIDI`) or under `/mnt/c/...` if you prefer files on the Windows drive — both work; WSL home is usually faster for Python tooling.

### Git

Required to clone the repository.

| Platform        | Install                                                                                                                   |
| --------------- | ------------------------------------------------------------------------------------------------------------------------- |
| **Linux / WSL** | `sudo apt install git` (Debian/Ubuntu), `sudo dnf install git` (Fedora/RHEL), or your distro’s package manager            |
| **macOS**       | [Xcode Command Line Tools](https://developer.apple.com/xcode/resources/) (`xcode-select --install`) or `brew install git` |

### uv

Required. uv manages Python and project dependencies.

| Platform        | Install                                                                   |
| --------------- | ------------------------------------------------------------------------- |
| **Linux / WSL** | `curl -LsSf https://astral.sh/uv/install.sh \| sh`                        |
| **macOS**       | `curl -LsSf https://astral.sh/uv/install.sh \| sh` — or `brew install uv` |

After installing, open a **new** terminal and confirm:

```bash
uv --version
```

**Python 3.10+** is required (`pyproject.toml`). You usually do not need to install Python separately — on first `uv sync`, uv uses a suitable interpreter on your `PATH` or downloads one automatically.

You also need **network access** for the first `uv sync` (packages are downloaded into uv’s cache, then installed into `.venv/`).

### pdftk (conditional)

**Only required when `--pages` points to a PDF file** — MUDIDI uses pdftk to split multi-page PDFs into single-page inputs. If you use a **snippets directory** of per-page images (`.png`, `.jpg`, …), you can skip pdftk.

Install pdftk and ensure `pdftk` is on your `PATH`:

| Platform                        | Install                       |
| ------------------------------- | ----------------------------- |
| **Linux / WSL** (Debian/Ubuntu) | `sudo apt install pdftk-java` |
| **Linux** (Fedora/RHEL)         | `sudo dnf install pdftk-java` |
| **macOS**                       | `brew install pdftk-java`     |

Verify:

```bash
pdftk --version
```

---

## Install

Same steps on **Linux, WSL, and macOS**:

```bash
git clone <repo-url> && cd MUDIDI
uv sync
cp .env.example .env   # add at least one LLM provider key (see below)
```

After `uv sync`, the `mudidi` command is installed in the project virtualenv. Use either:

```bash
uv run mudidi run --help          # recommended — no need to activate the venv
# or:
source .venv/bin/activate
mudidi run --help
```

### API keys (`.env`)

Copy [`.env.example`](.env.example) to `.env` and set only the keys for backends you use. MUDIDI uses **litellm ≥ 1.87** (GPT‑5.5 `reasoning_effort`, OpenAI SDK 2.x) and passes the matching key based on the model string (see [Model strings](#model-strings-model)). Label Studio is optional and uses a [separate venv](docs/uv.md) because it pins `openai` 1.x.

| Key                   | Used for                                                         |
| --------------------- | ---------------------------------------------------------------- |
| `GEMINI_API_KEY`      | Gemini (`gemini/...` or `google/...`)                            |
| `OPEN_ROUTER_API_KEY` | Models prefixed with `openrouter/` (GPT, Claude, Qwen, …)        |
| `OPENAI_API_KEY`      | Direct OpenAI (`openai/...` or ids containing `gpt` / `openai`)  |
| `ANTHROPIC_API_KEY`   | Direct Anthropic (`anthropic/...` or ids containing `claude`)    |

---

## Prepare your dictionary folder

You can supply pages in either of two ways. For **large jobs** (full scanned dictionaries), **Option A — single source PDF** is the default and recommended workflow: one file, page ranges on the CLI, and pdftk splits pages internally. **Option B — snippets directory** is a good alternative when you already have per-page images or a small page set.

### Option A — single source PDF (recommended for large jobs)

Pass the full scanned dictionary PDF on `--pages` and list which **1-based PDF page numbers** to process. Dictionary entries and introduction can both come from the same file — use `--dict-pages` for entry pages and `--intro-pages` for front matter. MUDIDI splits each page internally with **pdftk** (must be installed and on `PATH`).

```
my-dictionary/
    evenki-russian.pdf         # full scan — passed on --pages
    alphabet.txt               # optional — source-script character inventory
    dictionary_languages.yaml  # optional — Pass 1 hint (see below; pass with --dictionary-languages)
    output/                    # typical --output-dir
```

| Flag                     | Required | Page spec examples                     |
| ------------------------ | -------- | -------------------------------------- |
| `--pages dictionary.pdf` | yes      | path to the scan                       |
| `--dict-pages`           | yes      | `97-123`, `1,3,5`, `97-123, 179-182`   |
| `--intro-pages`          | no       | `1-5`, `1,2,4` (same PDF as `--pages`) |

Do **not** pass `--intro` when using a PDF — introduction pages are selected with `--intro-pages` from the same file.

Split pages are cached under `{output_dir}/.rendered_snippets/split/` (dictionary) and `{output_dir}/.rendered_intro/split/` (introduction) as `page_{N}.pdf`. Re-runs reuse cached splits unless you pass `--overwrite`.

**Neighbor context (inference only):** Stage 1 and Stage 2 can attach the **previous and next dictionary page** when they exist in the **same run’s page list** — here, only pages listed in `--dict-pages` (in numeric order). Pages outside that spec are never sent as neighbors (e.g. processing `53,77` does not pull page 54 or 76). Introduction pages from `--intro-pages` are separate and are **not** used as neighbor context for dictionary pages.

**pdftk:** required for this workflow — see [pdftk (conditional)](#pdftk-conditional) under Prerequisites.

### Option B — snippets directory (alternative: smaller jobs, pre-split pages)

Place inputs in a working directory (layout is flexible; paths are passed on the CLI):

```
my-dictionary/
    snippets/                  # required — page images or PDFs (page_1.png, page_2.pdf, …)
    introduction/              # optional — front matter for Stage 2 Pass 1
    dictionary_languages.yaml  # optional — Pass 1 hint (see below; pass with --dictionary-languages)
    alphabet.txt               # optional — source-script character inventory
```

**`snippets/`** — one file per dictionary page. Supported: `.png`, `.jpg`, `.jpeg`, `.webp`, `.pdf`. Pages are processed in numeric order (`page_1`, `page_2`, …, `page_10`).

**Neighbor context (inference only):** Previous/next context uses only files **present in `snippets/`** (sorted by page stem). If you omit `page_54.png`, page 53 has no “next” neighbor in the run even if it exists in the full book scan elsewhere. Files outside `snippets/` are never loaded as neighbors.

**`introduction/`** — front matter for **Stage 2 Pass 1** (parse-rules discovery): abbreviations, entry structure, and which MDF markers the dictionary uses. Pass 2 uses the cached `parse-rules.json`, not the intro images again.

**`dictionary_languages.yaml`** — optional hint for Pass 1 when passed via `--dictionary-languages`. See [dictionary_languages.yaml](#dictionary_languagesyaml) below.

**`alphabet.txt`** — character list or legend for the vernacular script. Improves Stage 1 accuracy on rare glyphs.

### `dictionary_languages.yaml`

This .yaml provide the LLM with context of the source and target languages to help steer the selection of gloss markers (gn vs ge, etc), as well as general layout to influence a better entry structure description in the the `parse-rules`. This file is completely optional --- in most cases the LLM is smart enough to infer this information during `Stage-2` inference. When enabled, it is loaded at startup and summarized as a short hint in the **Stage 2 Pass 1** user prompt (`{config_hint}`: layout, source language, target languages). Pass 2 then follows the discovered **`parse-rules.json`**, not the YAML directly.

**When it is used (Pass 1 only)**

| Mode                                            | Behavior                                                                                                                                                 |
| ----------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Inference** (default)                         | **Opt-in:** Pass `--dictionary-languages PATH` to enable the hint. If omitted, Pass 1 runs without layout/language config from YAML (no auto-discovery). |
| **Benchmark** (`--benchmark` / `--samples-dir`) | Auto-loads `{entry}/dictionary_languages.yaml` per sample when the flag is omitted. Pass `--dictionary-languages PATH` to override with a specific file. |

Example (inference, PDF workflow):

```bash
uv run mudidi run \
  --pages my-dictionary/evenki-russian.pdf \
  --dict-pages 97-123 \
  --dictionary-languages my-dictionary/dictionary_languages.yaml \
  --output-dir my-dictionary/output \
  ...
```

**What to put inside** — required fields:

| Field     | Meaning                                                                                                                                                                                                                 |
| --------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `layout`  | Short label for how entries are arranged on the page. **Any string is accepted** — the list below is only a set of **recommended** names, not a closed vocabulary. Use your own term if it fits your dictionary better. |
| `source`  | Headword / vernacular language (`language` only — e.g. `Evenki`, `Circassian`).                                                                                                                                         |
| `targets` | Gloss / translation languages (`language` per target). One or more entries.                                                                                                                                             |

Optional:

| Field                | Meaning                                                                                                                                                          |
| -------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `layout-description` | Free-text explanation of what your `layout` means for **this** dictionary. Included in the Pass 1 hint when set; especially useful with a custom `layout` label. |

**Recommended `layout` labels** (pick the closest match, or invent your own and explain it in `layout-description`):

| Value               | Typical dictionary shape                                                                             | Example `layout-description`                                                                       |
| ------------------- | ---------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------- |
| `inline_bilingual`  | One vernacular headword with one gloss language in the same entry block.                             | Headword in bold on the left; Russian gloss continues on the same line after the lemma.            |
| `column_bilingual`  | Headword and gloss in **separate columns** (two-language column layout).                             | Vernacular lemmas in the center column; English glosses in the right column only.                  |
| `inline_trilingual` | Several target languages **mixed inside one entry block** (multiple glosses or scripts on one line). | Each sense line lists English, then Chinese, then French glosses in that order after the headword. |
| `column_trilingual` | Headwords and glosses in **separate columns** (three or more language tiers).                        | Circassian headwords in the center column; English left, Turkish right.                            |

Pass 1 still sees introduction images and the sample page; the YAML hint only steers marker and rule discovery. Pass 2 uses `parse-rules.json`, not the YAML directly.

You only need human-readable `language` names — no short `code` field. Legacy YAML files that still include `code` are accepted; that field is ignored on load.

**Minimal bilingual example** (Evenki → Russian):

```yaml
layout: inline_bilingual
layout-description: Headword in bold; Russian gloss on the same line after the lemma.
source:
  language: Evenki
targets:
  - language: Russian
```

**Column trilingual example** (headword in center column, glosses left/right):

```yaml
layout: column_trilingual
layout-description: Circassian lemmas in the center column; English glosses left, Turkish right.
source:
  language: Circassian
  column_id: center
targets:
  - language: English
    column_id: left
  - language: Turkish
    column_id: right
```

**Custom layout label** (any string + description):

```yaml
layout: reverse_alphabet_appendix
layout-description: Main body uses two-column headword/gloss layout; appendix pages are single-column index entries without gloss lines.
source:
  language: Evenki
targets:
  - language: Russian
```

---

## Quick start — full pipeline

Run Stage 1 and Stage 2 in one command. Stage 2 automatically reads Stage 1 output from the same run.

**Option A — `--pages` points to a single PDF** (recommended for large jobs; same file for dict + intro; requires `pdftk`):

```bash
uv run mudidi run \
  --pages my-dictionary/evenki-russian.pdf \
  --dict-pages 97-123 \
  --intro-pages 1-5 \
  --alphabet my-dictionary/alphabet.txt \
  --parse-rules-page page_97 \
  --output-dir my-dictionary/output \
  --stage all \
  --strategy two_stage \
  --stage1-mode flat \
  --stage-1-model gemini/gemini-3-flash-preview \
  --model gemini/gemini-3.1-pro-preview \
  --stage2-reasoning medium
```

After PDF split, stems are `page_{N}` where `N` is the **PDF page number** from `--dict-pages` (e.g. `--parse-rules-page page_97` for PDF page 97).

To enable the optional Pass 1 language/layout hint, add `--dictionary-languages my-dictionary/dictionary_languages.yaml`.

**Option B — `--pages` points to a directory** (alternative: pre-split page images or small jobs):

```bash
uv run mudidi run \
  --pages my-dictionary/snippets \
  --intro my-dictionary/introduction \
  --alphabet my-dictionary/alphabet.txt \
  --parse-rules-page page_97 \
  --output-dir my-dictionary/output \
  --stage all \
  --strategy two_stage \
  --stage1-mode flat \
  --stage-1-model gemini/gemini-3-flash-preview \
  --model gemini/gemini-3.1-pro-preview \
  --stage2-reasoning medium
```

`--parse-rules-page` selects which snippet(s) Stage 2 **Pass 1** uses for parse-rules discovery (default: first page in `--pages`). Stems must match files in `snippets/` (e.g. `page_97.png` → `page_97`). Pass 1 runs **once** per `--output-dir`; the result is cached as `parse-rules.json` and **reused on the next run** unless you pass `--overwrite` or delete that file.

Non-contiguous PDF pages (Option A only):

```bash
uv run mudidi run \
  --pages my-dictionary/evenki-russian.pdf \
  --dict-pages 19,83,162 \
  --output-dir my-dictionary/output \
  --stage 1 \
  --stage1-mode flat \
  --model gemini/gemini-3-flash-preview
```

### Parse rules discovery (`--parse-rules-page`, `--parse-rules-file`)

Stage 2 **Pass 1** discovers MDF markers and entry-structure rules, then writes `{output_dir}/parse-rules.json`. Pass 2 reuses that file on every page — it is **not** re-run per page.

**Resume (discovery runs):** If `{output_dir}/parse-rules.json` already exists from a prior run, the next command **loads that cache** and skips Pass 1 LLM — even if you change `--parse-rules-page` or `--intro`. To re-discover from new samples, pass **`--overwrite`** or delete `{output_dir}/parse-rules.json` first.

| Flag                                        | When to use                                                                                                                                                               |
| ------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `--parse-rules-page STEM`                   | Pick sample page(s) from the **same `--pages` input** (directory or PDF-split stems). Default: first page.                                                                |
| `--parse-rules-page A,B` or repeat the flag | **Two or more** samples → one Pass 1 call with the multi-sample prompt (`stage_2_pass_2_multi`). Use when sections differ (main body vs appendix).                        |
| `--parse-rules-file PATH`                   | Skip Pass 1 LLM entirely — load your hand-edited `parse-rules.json`. Always reads **your** file, even if `{output_dir}/parse-rules.json` already exists from a prior run. |

Works in **both** snippets-directory mode and PDF mode — stems always refer to files produced from `--pages`, not arbitrary paths.

**Multi-sample (heterogeneous dictionary):**

```bash
uv run mudidi run \
  --pages my-dictionary/snippets \
  --intro my-dictionary/introduction \
  --parse-rules-page page_50,page_200 \
  --output-dir my-dictionary/output \
  --stage all \
  --stage1-mode flat \
  --stage-1-model gemini/gemini-3-flash-preview \
  --model gemini/gemini-3.1-pro-preview \
  --stage2-reasoning medium
```

**Curated rules (skip Pass 1 LLM):**

```bash
uv run mudidi run \
  --pages my-dictionary/snippets \
  --parse-rules-file my-dictionary/parse-rules.json \
  --output-dir my-dictionary/output \
  --stage 2 \
  --stage1-source predictions \
  --model gemini/gemini-3.1-pro-preview \
  --stage2-reasoning medium
```

With `--stage all`, MUDIDI transcribes sample page(s) first if their Stage 1 output is not already present, then runs Pass 1 discovery before bulk Pass 2.

### Stage 1 only

**Directory:**

```bash
uv run mudidi run \
  --pages my-dictionary/snippets \
  --alphabet my-dictionary/alphabet.txt \
  --output-dir my-dictionary/output \
  --stage 1 \
  --strategy two_stage \
  --stage1-mode flat \
  --model gemini/gemini-3-flash-preview
```

**PDF:**

```bash
uv run mudidi run \
  --pages my-dictionary/evenki-russian.pdf \
  --dict-pages 97-123 \
  --output-dir my-dictionary/output \
  --stage 1 \
  --strategy two_stage \
  --stage1-mode flat \
  --model gemini/gemini-3-flash-preview
```

### Stage 2 only (reuse existing Stage 1 output)

Use the **same `--pages` path** as the Stage 1 run so output stems line up.

**Directory:**

```bash
uv run mudidi run \
  --pages my-dictionary/snippets \
  --intro my-dictionary/introduction \
  --parse-rules-page page_97 \
  --output-dir my-dictionary/output \
  --stage 2 \
  --strategy two_stage \
  --stage1-source predictions \
  --model gemini/gemini-3.1-pro-preview \
  --stage2-reasoning medium
```

**PDF:**

```bash
uv run mudidi run \
  --pages my-dictionary/evenki-russian.pdf \
  --dict-pages 97-123 \
  --intro-pages 1-5 \
  --parse-rules-page page_97 \
  --output-dir my-dictionary/output \
  --stage 2 \
  --strategy two_stage \
  --stage1-source predictions \
  --model gemini/gemini-3.1-pro-preview \
  --stage2-reasoning medium
```

Stage 2 reads Stage 1 predictions from `{output_dir}/stage-1/{page}/` — column TSV if present, otherwise flat text (`--stage1-input auto`, default).

---

## What you get — output layout

All artifacts land under `--output-dir`:

```
output/
├── parse-rules.json               # Stage 2 Pass 1: MDF markers + entry rules (once per dictionary; review before large Pass 2 runs)
├── stage-1/
│   └── page_1/
│       ├── page_1_stage1_flat.txt     # flat mode (one line per visible row)
│       ├── page_1_stage1.tsv          # column mode (column_id × line_number × text)
│       ├── page_1_stage1_raw.json     # raw LLM structured response
│       └── page_1_stage1_input.json   # request snapshot (for debugging)
└── stage-2/
    └── page_1/
        ├── page_1.mdf.txt             # Toolbox MDF records for this page
        ├── page_1_stage2_raw.txt      # raw LLM MDF response
        ├── page_1_stage2_input.json   # request snapshot
        └── page_1_usage.json          # token counts / estimated cost
```

Re-running the same command **skips pages that already have output** (resume). Pass `--overwrite` to force re-processing.

---

## CLI commands

| Command                  | Purpose                                               |
| ------------------------ | ----------------------------------------------------- |
| `mudidi run`             | Run Stage 1, Stage 2, or both on your dictionary      |
| `mudidi eval stage1`     | Evaluate Stage 1 against gold transcripts (benchmark) |
| `mudidi eval stage2`     | Evaluate Stage 2 MDF against gold (benchmark)         |
| `mudidi-eval-flat`       | Same as `mudidi eval stage1` (standalone script)      |
| `mudidi-eval-stage2-mdf` | Same as `mudidi eval stage2` (standalone script)      |

Get full flag lists:

```bash
uv run mudidi run --help
```

Model and tuning flags (`--model`, `--stage-1-model`, `--stage-2-pass-1-model`, `--stage-2-pass-2-model`, `--stage1-mode`, `--overwrite`, etc.) are registered on `mudidi run` — see [Model selection](#model-selection) above.

```bash
# directory input
uv run mudidi run \
  --pages my-dictionary/snippets \
  --parse-rules-page page_97 \
  --output-dir my-dictionary/output \
  --stage-1-model gemini/gemini-3-flash-preview \
  --model gemini/gemini-3.1-pro-preview \
  --stage1-mode flat \
  --stage2-reasoning medium \
  --overwrite

# PDF input
uv run mudidi run \
  --pages my-dictionary/evenki-russian.pdf \
  --dict-pages 97-123 \
  --parse-rules-page page_97 \
  --output-dir my-dictionary/output \
  --stage-1-model gemini/gemini-3-flash-preview \
  --model gemini/gemini-3.1-pro-preview \
  --stage1-mode flat \
  --stage2-reasoning medium \
  --overwrite
```

---

## `mudidi run` arguments

### Required (inference mode)

| Flag                | Description                                                                                                  |
| ------------------- | ------------------------------------------------------------------------------------------------------------ |
| `--pages PATH`      | Snippets directory **or** a single source PDF                                                                |
| `--output-dir PATH` | Where to write `stage-1/` and `stage-2/` results                                                             |
| `--dict-pages SPEC` | **Required when `--pages` is a PDF.** 1-based dictionary page numbers: `1-10`, `1,3,5`, or `97-123, 179-182` |

### Common optional flags

| Flag                                 | Default                 | Description                                                                                                                                                                               |
| ------------------------------------ | ----------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `--stage {1,2,all,2-pass-1,2-pass-2}` | `all`                   | Run Stage 1 only, Stage 2 (Pass 1 + Pass 2), both, Pass 1 only, or Pass 2 only (needs cached `parse-rules.json`) |
| `--intro PATH`                       | —                       | Introduction directory or text/image file (snippets-directory mode only)                                                                                                                  |
| `--intro-pages SPEC`                 | —                       | When `--pages` is a PDF: intro pages from the **same PDF** (same syntax as `--dict-pages`)                                                                                                |
| `--alphabet PATH`                    | —                       | Alphabet file (`.txt`/`.md`) or image                                                                                                                                                     |
| `--ocr-text PATH`                    | — (off)                 | Enable OCR hints from a per-page hint directory (`.md`/`.docx`/`.txt`, one file per snippet stem). Off by default; benchmark ablations showed limited benefit |
| `--prompts-file PATH`                | bundled `PROMPT.json`   | Custom prompts; edits reload on next LLM call                                                                                                                                             |
| `--parse-rules-page STEM`            | first page in `--pages` | Pass 1 sample page stem(s). Must exist under `--pages` (snippets dir or PDF split). Repeat the flag or comma-separate (`page_50,page_200`). **Two or more** → multi-sample Pass 1 prompt. |
| `--parse-rules-file PATH`            | —                       | Load curated `parse-rules.json`; skip Pass 1 LLM discovery. **Always** reads your file (overrides any existing `{output_dir}/parse-rules.json`) and refreshes the output copy.            |
| `--dictionary-languages PATH`        | —                       | Optional `dictionary_languages.yaml` for Stage 2 Pass 1 (layout + source/target hint). Inference: opt-in only. Benchmark: auto-loads per-entry YAML when omitted.                         |
| `--parse-rules-gold`                 | off                     | Benchmark: load gold `parse-rules.json` from `outputs/stage-2-gold/` (skips Pass 1 LLM)                                                                                                   |
| `--stage1-source {gold,predictions}` | `predictions`           | Stage 2 input source (inference uses predictions)                                                                                                                                         |

### Model selection

Use **`--model`** to set the same litellm model string for every step (Stage 1, Stage 2 Pass 1 parse-rules discovery, Stage 2 Pass 2 MDF extraction). Override individual steps when you want different models or reasoning budgets.

#### Model strings (`--model`)

Every model flag (`--model`, `--stage-1-model`, `--stage-2-pass-1-model`, `--stage-2-pass-2-model`) accepts a **[litellm](https://docs.litellm.ai/docs/providers) model id**. MUDIDI calls `litellm.completion` with that string unchanged; the **prefix** (or recognizable substrings in the id) selects the provider and which API key from `.env` is injected.

| Route | Example `--model` values | API key |
| ----- | ------------------------ | ------- |
| **Gemini (direct)** | `gemini/gemini-3-flash-preview`, `gemini/gemini-3.1-pro-preview` | `GEMINI_API_KEY` |
| **OpenRouter** | `openrouter/openai/gpt-5.5`, `openrouter/anthropic/claude-opus-4.7`, `openrouter/qwen/qwen3-vl-235b-a22b-instruct` | `OPEN_ROUTER_API_KEY` |
| **OpenAI (direct)** | `openai/gpt-4o`, `gpt-4o` (use the [current API model id](https://platform.openai.com/docs/models) from OpenAI) | `OPENAI_API_KEY` |
| **Anthropic (direct)** | `anthropic/claude-sonnet-4-20250514`, `claude-3-5-sonnet-20241022` (use the [current API model id](https://docs.anthropic.com/en/docs/about-claude/models) from Anthropic) | `ANTHROPIC_API_KEY` |

**OpenRouter vs direct:** Prefix the model with `openrouter/` when you want a single OpenRouter key and MUDIDI’s OpenRouter routing (provider order, retries, optional `OPENROUTER_MAX_TOKENS`, reasoning via `extra_body`). Omit `openrouter/` and use `openai/...` or `anthropic/...` (or bare API ids) when you call OpenAI or Anthropic with your own account keys.

**Vision:** Stage 1 and Stage 2 send page images (and sometimes PDFs). Use vision-capable models (Gemini flash/pro, GPT-4o-class, Claude Sonnet/Opus, Qwen-VL, etc.).

**PDF input:** When `--pages` is a PDF, Gemini can receive inline PDF data; other families have pages rasterized to PNG before the LLM call.

**Reasoning flags** (`--stage1-reasoning`, `--stage2-reasoning`): behaviour is provider-specific. Gemini 3+ maps effort via litellm `reasoning_effort` (`none` → `low`; thinking cannot be fully disabled). OpenRouter GPT‑5 / Claude Opus / `*-thinking` models use OpenRouter’s `reasoning` object (`none` → `enabled: false` on Stage 1). **Direct** `openai/gpt-5*`, `o1`/`o3`/`o4`, and `anthropic/claude-opus*` / `claude-4*` ids receive the same effort values via litellm `reasoning_effort` (including Stage 1 `none` where the API supports it). Older direct models (e.g. `gpt-4o`) ignore these flags.

```bash
# Gemini (default path in this repo)
--model gemini/gemini-3-flash-preview

# OpenRouter — one key, many hosts
--model openrouter/openai/gpt-5.5
--stage-2-pass-2-model openrouter/anthropic/claude-opus-4.7

# Direct OpenAI / Anthropic — no openrouter/ prefix
--model openai/gpt-4o
--model anthropic/claude-sonnet-4-20250514
```

For any litellm-supported provider, use that provider’s documented id format. See [`examples/`](examples/) for runnable inference and evaluation scripts.

**Typical inference setup:** Gemini 3 Flash for Stage 1 transcription, Gemini 3.1 Pro for both Stage 2 passes, with `--stage2-reasoning medium`:

```bash
--stage-1-model gemini/gemini-3-flash-preview \
--model gemini/gemini-3.1-pro-preview \
--stage2-reasoning medium
```

| Flag                     | Applies to                                    | Default                         |
| ------------------------ | --------------------------------------------- | ------------------------------- |
| `--model`                | All steps when no step-specific flag is set   | `gemini/gemini-3-flash-preview` |
| `--stage-1-model`        | Stage 1 page transcription                    | `--model`                       |
| `--stage-2-pass-1-model` | Stage 2 Pass 1 (`parse-rules.json` discovery) | `--model`                       |
| `--stage-2-pass-2-model` | Stage 2 Pass 2 (per-page MDF)                 | `--model`                       |

Examples:

```bash
# Recommended: Flash for Stage 1 OCR, Pro for Stage 2 (Pass 1 + Pass 2)
uv run mudidi run \
  --pages my-dictionary/snippets \
  --output-dir my-dictionary/output \
  --stage-1-model gemini/gemini-3-flash-preview \
  --model gemini/gemini-3.1-pro-preview \
  --stage2-reasoning medium

# Same model everywhere
uv run mudidi run \
  --pages my-dictionary/snippets \
  --output-dir my-dictionary/output \
  --model gemini/gemini-3-flash-preview

# Full per-step control (different model per pass)
uv run mudidi run \
  --pages my-dictionary/evenki-russian.pdf \
  --dict-pages 97-123 \
  --output-dir my-dictionary/output \
  --stage-1-model gemini/gemini-3-flash-preview \
  --stage-2-pass-1-model gemini/gemini-3.1-pro-preview \
  --stage-2-pass-2-model openrouter/openai/gpt-5.5 \
  --stage2-reasoning medium
```

### Other strategy and tuning flags

| Flag                                        | Default     | Description                                                                                                                                                                                                                                                                                       |
| ------------------------------------------- | ----------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `--strategy`                                | `two_stage` | `two_stage` (LLM) or `vlm_ocr` (specialised VLM backends)                                                                                                                                                                                                                                         |
| `--stage1-mode {column,flat}`               | `column`    | Stage 1 output format — see [Stage 1 output formats](#stage-1-output-formats-flat-vs-column); use **`flat`** for benchmarking and **`column`** for production ready inference.                                                                                                                    |
| `--stage1-reasoning {none,low,medium,high}` | `low`       | Stage 1 reasoning effort                                                                                                                                                                                                                                                                          |
| `--stage2-reasoning {low,medium,high}`      | `low`       | Stage 2 reasoning effort                                                                                                                                                                                                                                                                          |
| `--temperature`                             | `0.1`       | Sampling temperature for all LLM steps. **GPT-5** models only accept `1.0` — MUDIDI clamps automatically (use `--temperature 1` to avoid the warning).                                                                                                                                              |
| `--toolbox-pdf PATH`                        | —           | Optional: attach a SIL Toolbox MDF reference PDF during **Stage 2 Pass 2 only**. Full manual: [`assets/Pages from ToolboxReferenceManual.pdf`](assets/Pages%20from%20ToolboxReferenceManual.pdf) (~65 pages). Expensive at scale — see [Parse rules vs toolbox PDF](#parse-rules-vs-toolbox-pdf). |
| `--prompt-cache {auto,off}`                 | `auto`      | Use litellm/provider prompt caching for cacheable static prompt blocks when supported. Pass `off` to remove cache-control markers.                                                                                                                         |
| `--media-reference {auto,inline,file-uri}`  | `auto`      | How reusable PDFs are attached. `auto` prefers litellm file parts/remote URI references when supported and falls back safely; `inline` uses base64 payloads; `file-uri` prefers URI/file-style parts with inline fallback for local files.                 |
| `--prompt-cache-key KEY`                    | —           | Optional stable cache-key prefix for providers with cache routing hints (notably direct OpenAI models).                                                                                                                                                   |
| `--stage-1-guides PATH`                     | —           | Extra rules appended to Stage 1 prompt                                                                                                                                                                                                                                                            |
| `--no-stage1-typography`                    | off         | Inference only: plain Stage 1 transcripts without `<b>`/`<i>` markup instructions                                                                                                                                                                                                                 |
| `--stage-2-guides PATH`                     | —           | Extra rules appended to Stage 2 prompt                                                                                                                                                                                                                                                            |
| `--overwrite`                               | off         | Re-process pages even if output exists; also **re-runs Pass 1 LLM discovery** when `{output_dir}/parse-rules.json` already exists                                                                                                                                                                 |
| `--limit N`                                 | —           | Process at most N pages                                                                                                                                                                                                                                                                           |
| `--no-alphabet`                             | off         | Skip alphabet hint                                                                                                                                                                                                                                                                                |
| `--no-intro`                                | off         | Skip introduction for Stage 2 Pass 1 (field discovery)                                                                                                                                                                                                                                            |

### Stage 1 output formats: flat vs column

Both modes run the same Stage 1 OCR job (faithful transcription, no entry parsing). They differ only in **how the model serialises** the page and **which file Stage 2 reads**.

|                        | **Column** (`--stage1-mode column`)                                              | **Flat** (`--stage1-mode flat`)                                           |
| ---------------------- | -------------------------------------------------------------------------------- | ------------------------------------------------------------------------- |
| **Output file**        | `{page}_stage1.tsv`                                                              | `{page}_stage1_flat.txt`                                                  |
| **Structure**          | Tab-separated table: `column_id`, `line_number`, `text`                          | Plain text: one physical printed line per row                             |
| **Multi-column pages** | Preserves which column each line came from (`left`, `center`, `right`, `single`) | Collapses to a single ordered line list (left→right reading order)        |
| **Header / footer**    | Rows with `column_id` = `header` or `footer`                                     | Same lines, but without column metadata                                   |
| **Typical use**        | Benchmark gold, Label Studio pre-annotation, trilingual layouts                  | **Default for new inference runs** — simpler for Stage 2 and human review |

**Column TSV** — each visible line is one row; body lines are tagged by column:

```tsv
column_id	line_number	text
header		Carolinian-English Dictionary
single	1	<b>akkáyi</b> A-¹, KKÁYI, -A³ (or akkayú) <i>vt caus.</i> To hurry someone…
single	2	go faster. Related <b>kkáy</b>.
footer		51
```

On a **trilingual** page, `column_id` distinguishes gloss columns (e.g. English `left`, headword `center`, Turkish `right`). Stage 2 can use that layout hint when assigning fields.

**Flat text** — the same content without the table wrapper; header lines first, then body lines in reading order, then footer:

```text
Carolinian-English Dictionary
<b>akkáyi</b> A-¹, KKÁYI, -A³ (or akkayú) <i>vt caus.</i> To hurry someone…
go faster. Related <b>kkáy</b>.
51
```

Flat mode asks the model for structured JSON (`header` / `lines` / `footer` lists) internally, then writes the joined plain-text file above.

**Stage 2 input:** `--stage1-input auto` (default) prefers column TSV when both exist, otherwise flat. For a flat-only pipeline, pass `--stage1-mode flat` on Stage 1 and optionally `--stage1-input flat` on Stage 2.

### Inference-specific behaviour

- **Neighbor page context** — only in **inference** mode (not `--benchmark`). For each page, MUDIDI may attach the **previous** and/or **next** page image plus that neighbor’s Stage 1 transcript if it was already produced earlier in the **same** command. Neighbors are drawn only from the run’s input page list:
  - **Option A (PDF):** pages in `--dict-pages` only (sorted by page number). No context from pages you did not list, and no context from `--intro-pages`.
  - **Option B (directory):** files in the `--pages` snippets directory only. No context from pages missing from that folder.
  - First page in the list has no previous neighbor; last has no next. Non-contiguous specs (e.g. `53,77`) mean page 53 has no next and page 77 has no previous **within the run**.
  - Output still belongs to the **current** page only; neighbors are disambiguation context for hyphenation and cross-page entries.
- **Stage chaining** — with `--stage all`, Stage 2 reads Stage 1 predictions from `--output-dir` automatically.
- **Prompts** — inference uses `*_inference` prompt variants in `assets/PROMPT.json` (see [Customising prompts](#customising-prompts)).

---

## Pipeline overview

```
snippets/ + alphabet
        │
        ▼
┌─────────────────────────┐
│ Stage 1 — transcription │  →  stage-1/{page}/{page}_stage1_flat.txt
└───────────┬─────────────┘
            │
 intro + Pass 1 cheat sheet
            ▼
┌─────────────────────────┐
│ Stage 2 — MDF export    │  →  stage-2/{page}/{page}.mdf.txt
│  Pass 1: parse rules    │      parse-rules.json
│  Pass 2: per-page MDF   │
└─────────────────────────┘
```

**Stage 1** transcribes every visible line on the page image. Use `--stage1-mode flat` for the standard plain-text transcript; use `column` when you need per-column layout preserved (see [Stage 1 output formats](#stage-1-output-formats-flat-vs-column)).

**Stage 2 Pass 1** runs **once** per `--output-dir`: reads the introduction + one or more sample pages selected by `--parse-rules-page` (+ optional `--dictionary-languages` hint) and writes `parse-rules.json`. With a single sample, the user prompt is `stage_2_pass_2`; with two or more samples, `stage_2_pass_2_multi`. Alternatively, pass `--parse-rules-file` to load rules you edited by hand.

**Stage 2 Pass 2** runs per page: copies characters verbatim from the Stage 1 transcript and assigns MDF markers using `parse-rules.json` (introduction is not re-attached).

### Parse rules vs toolbox PDF

Stage 2 Pass 1 writes **`parse-rules.json`** once per dictionary run — a compact cheat sheet of which MDF markers this dictionary uses, one-line descriptions, and entry-structure rules (homographs, senses, subentries, gloss lines). Pass 2 injects that file into every page prompt as the `{field_block}`; it is **not** re-discovered per page.

**Choosing Pass 1 samples:** Pick a `--parse-rules-page` stem that represents typical body entries (not front matter). For dictionaries whose layout changes mid-book (appendix, reverse index, botanical names), pass **multiple** samples so Pass 1 can merge conventions in one shot, then review `{output_dir}/parse-rules.json` before a large Pass 2 run.

The repository includes the full SIL Toolbox MDF reference excerpt at [`assets/Pages from ToolboxReferenceManual.pdf`](assets/Pages%20from%20ToolboxReferenceManual.pdf) (~65 pages). Pass it with `--toolbox-pdf` during **Pass 2 only**. That can help when marker conventions are ambiguous, but the manual is still part of every Pass 2 request. With `--prompt-cache auto`, MUDIDI places the stable Pass 2 prefix (system instructions, `parse-rules.json` field block, stage-2 guides, and toolbox reference) behind a litellm cache-control boundary where the provider supports it. Cache hits and discounts still depend on the provider, model, token minimums, and TTL.

`--media-reference auto` uses litellm PDF/file content blocks for document-capable providers and remote URIs when the supplied path is already a URL or cloud URI (for example `https://...` or `gs://...`). Local PDFs fall back to base64 `file_data`, so this is provider-compatible but not a universal permanent file-upload cache. If the model cannot read PDFs through litellm, MUDIDI falls back to the built-in MDF marker text reference instead of attaching the PDF.

**Best practice for full-dictionary inference:**

1. Run Stage 2 Pass 1 once (with representative `--parse-rules-page` sample(s) and good introduction input). Use multiple samples when sections differ, e.g. `--parse-rules-page page_50 --parse-rules-page page_200`.
2. Open `{output_dir}/parse-rules.json` and **review it** — fix marker descriptions, add missing markers, tighten structure rules for this script and language pair. Or supply a hand-edited file with `--parse-rules-file`.
3. Re-run Pass 2 (`--stage 2-pass-2`) **without** `--toolbox-pdf` when possible, relying on your curated `parse-rules.json`. Pass 1 is skipped on resume when the file already exists (unless you pass `--overwrite`).
4. Spot-check a few `stage-2/{page}/{page}.mdf.txt` outputs; edit `parse-rules.json` again if needed, then re-run failed pages with `--overwrite`.

For most production runs, a well-edited `parse-rules.json` is the cost-effective substitute for attaching the toolbox manual on every page.

**If you still want `--toolbox-pdf`, trim the manual first.** After Pass 1, note which markers appear in `parse-rules.json` (e.g. `\lx`, `\gn`, `\sn`, `\ps`), then extract only the relevant pages from the full PDF into a smaller file and point `--toolbox-pdf` at that subset. Any PDF path works — you do not need the full 65 pages on every call.

```bash
# Example: keep manual pages 1–12 (adjust to the sections you need)
pdftk "assets/Pages from ToolboxReferenceManual.pdf" cat 1-12 output my-dictionary/toolbox-subset.pdf

uv run mudidi run \
  --pages my-dictionary/snippets \
  --parse-rules-file my-dictionary/parse-rules.json \
  --output-dir my-dictionary/output \
  --stage 2 \
  --toolbox-pdf my-dictionary/toolbox-subset.pdf \
  --stage1-mode flat \
  --model gemini/gemini-3.1-pro-preview \
  --stage2-reasoning medium
```

Reserve the full manual for small pilots or when Pass 2 quality still gaps after parse-rules curation and a trimmed PDF.

Further detail: [`docs/stage_1_methodology.md`](docs/stage_1_methodology.md), [`docs/stage_2_methodology.md`](docs/stage_2_methodology.md).

---

## Customising prompts

Templates live in [`assets/PROMPT.json`](assets/PROMPT.json) (also bundled as `mudidi/assets/PROMPT.json` in the package). The Python code **loads** these strings, **fills** `{placeholders}` with runtime data, and **concatenates** several entries into each LLM call. You do not pick a single “master prompt” — each pipeline step assembles its own system + user message.

### File shape

Each top-level key is a **prompt id** (for example `stage_1_user_alphabet`). The value has:

| Field         | Role                                                                                                                    |
| ------------- | ----------------------------------------------------------------------------------------------------------------------- |
| `description` | **Documentation only** — when this prompt is used (benchmark vs inference, which pipeline step). Not sent to the model. |
| `prompt`      | Template text sent to the model (may contain `{name}` placeholders).                                                    |
| `variables`   | **Documentation only** — placeholder cheat sheet for editors.                                                           |

#### About `variables`

The `variables` list is a **cheat sheet for humans** editing `PROMPT.json`. It records which `{placeholders}` appear in `prompt`, what they mean, and optional XML wrapper tags (for example `<alphabet>`). The runtime only uses whatever you put in `prompt`; it does not read `variables` when calling the LLM.

When you change a prompt, **update `variables` yourself** so the file stays accurate — add, rename, or remove entries as needed. Missing or stale `variables` entries will not break a run; they only make the file harder to maintain.

Placeholders use Python `str.format` syntax. Literal braces in the prompt must be doubled (`{{` / `}}`), as in the JSON example inside `stage_2_pass_2`.

Assembly code: Stage 1 — [`prompts.py`](src/mudidi/llm/prompts.py), [`llm_two_stage.py`](src/mudidi/extraction/llm_two_stage.py); Stage 2 Pass 1 — [`pass_1.py`](src/mudidi/llm/pass_1.py); Stage 2 Pass 2 — [`pass_2.py`](src/mudidi/llm/pass_2.py).

### Example: full messages sent to the model

Below is what actually gets passed to the LLM API after templates are loaded, placeholders filled, and blocks concatenated. Ellipsis (`…`) marks text shortened for readability; images are noted instead of base64 data URLs.

Typical **inference** run: `--stage1-mode flat`, alphabet + OCR hints on, introduction included in Stage 2.

---

#### Stage 1 — one call per dictionary page

Two messages: **system** (one prompt id) and **user** (text + images).

**`role: system`** — from `stage_1_system_inference` (placeholders filled):

```
You are a precise OCR transcription system specialising in historical and minority-language dictionaries.

Your task is faithful OCR only — do NOT parse dictionary entries or assign fields.

Output structure:
- `header`: page-level lines at the very top …
- `lines`: every visible BODY line in reading order …
- `footer`: page-level lines at the very bottom …

You may receive <ocr_reference>...</ocr_reference> from a standard OCR engine …

Rules for every line in header, lines, and footer:
- Preserve ALL diacritics …
- Wrap bold text in <b>...</b> and italic text in <i>...</i> when confident.
…
- Hyphenated wraps: when a word breaks across two printed lines with a trailing hyphen,
  emit TWO separate strings (e.g. "intelligi-" then "ble, adj. clear").

Page boundary rules:
- Output only content that belongs to the CURRENT page.
- INCLUDE entries that START on the current page even if they continue onto the next page.
- EXCLUDE entries that STARTED on the previous page and only continue on the current page.
- Neighbor pages are context for disambiguation only; do not transcribe their full text into the current page output.

<previous_page>
page: page_2
Use this page only for entry-boundary context.
<transcript>
… Stage 1 text for page_2 if already processed …
</transcript>
</previous_page>

<next_page>
(none)
</next_page>
```

**`role: user`** — text part is three `PROMPT.json` blocks joined with blank lines (`stage_1_user()`), then images appended:

```
<alphabet>
а
б
в
… contents of alphabet.txt …
</alphabet>

The <alphabet> is a reference guide to the list of characters in the script …
Rules:
1. Prefer <alphabet> matches over visually similar characters …
…

<ocr_reference>
… optional Mathpix / OCR engine text for this page …
</ocr_reference>

The OCR reference above may contain errors but can help you identify ambiguous character shapes.

Now transcribe every line of text from the dictionary page image exactly as it appears. Preserve all diacritics and special characters.

USER DEFINED GUIDELINES
… only if --stage-1-guides PATH was passed …
```

**`role: user`** — vision parts after that text (order matters):

1. `[image]` previous page (`page_2.png`) — inference only, if listed in `--dict-pages` or present in the snippets directory
2. `[image]` next page — inference only, under the same scope as above
3. `[image]` alphabet scan — if an alphabet image file exists
4. `[image]` **current page** (`page_3.png`) — always

The model must return structured JSON (`header` / `lines` / `footer`), which is saved as flat text for Stage 2.

---

#### Stage 2 Pass 1 — one call per dictionary (field map)

Two messages. Output is JSON → `parse-rules.json` → rendered as `{field_block}` in Pass 2.

- **One sample** (`--parse-rules-page page_97` or default first page): user text from `stage_2_pass_2` + intro images + one sample image.
- **Multiple samples** (`--parse-rules-page page_50,page_200`): user text from `stage_2_pass_2_multi` with several `<sample_transcription page="…">` blocks + intro images + one image per sample (same order).

Pass 1 always uses the sample stem(s) you name via `--parse-rules-page` from the current `--pages` input — not whichever page happens to be processed first in the Pass 2 loop.

**`role: system`** — `stage_2_pass_1` with `{mdf_marker_reference}` replaced by the entire `mdf_marker_reference` prompt (~thousands of words; abbreviated here):

```
You analyse dictionary front matter and a sample page to list which SIL Toolbox MDF
markers this dictionary uses and how entries are structured.

Output a single JSON object — NOT a full typography map. For each marker that appears
in this dictionary, give a one-line description (role + language tier). Add structure
rules for entry boundaries (homographs, senses, subentries, gloss lines).

Use MDF marker codes from the reference below. Pick gloss/usage/definition tiers to
match the dictionary's target languages (e=English, n=national, r=regional, v=vernacular).
Do NOT assign English-tier markers (ge, de, ue) when the dictionary has no English target.

MDF marker vocabulary (SIL Toolbox — assign ONLY markers whose content appears on
THIS dictionary's intro + sample page; …):

── Entry structure … ──
  lx   Lexeme / headword. Record marker; one per lexical entry …
  hm   Homonym number. …
…
  nt   Compiler notes by domain …; bracketed if printed.
```

**`role: user`** — text from `stage_2_pass_2`, then images:

```
Study this dictionary and return a marker cheat sheet JSON object.

Inputs:
1. Introduction pages (images below).
2. One sample dictionary page (image + flat transcription).

3. Language roles: layout=two_column, source=Evenki, targets=[Russian].

Return JSON with this shape:
{
  "dictionary_name": "short name",
  "markers": [
    {"marker": "lx", "description": "headword / lexeme (vernacular lemma)"},
    …
  ],
  "rules": [
    "Separate homograph mains: two \\lx blocks with same lemma, each with \\hm N.",
    …
  ],
  "abbreviations": {"мн.": "plural"}
}

Include ONLY markers that appear on the sample page or are defined in the intro.
…
Return JSON only — no markdown fences.

<sample_transcription>
A
<b>а̄́вда</b>  I. <i>v.</i> swell, rise …
… full Stage 1 flat text for the parse-rules sample page (e.g. page_1) …
</sample_transcription>
```

**`role: user`** — vision parts after that text:

1. `[image]` each file in `introduction/` (in order)
2. `[image]` sample dictionary page (same page as `<sample_transcription>`)

---

#### Stage 2 Pass 2 — one call per dictionary page (MDF export)

Two messages. Output is raw MDF text (Toolbox record blocks).

**`role: system`** — from `stage_2_direct_mdf_system_inference`:

```
You digitize dictionary pages into SIL Toolbox MDF (Multi-Dictionary Formatter) text.

The flat transcription is the Stage-1 OCR text for this page. Copy every vernacular and gloss
character from it exactly — do NOT re-read, correct, normalise, or substitute letters
from the page image. Use the page image and field map (from Pass 1) only to decide entry boundaries,
field roles, and MDF marker assignment.

Output ONLY MDF text — no JSON, no markdown fences, no commentary.
Use one blank line between lexicon records (between main entry blocks).

Allowed changes (structure only — never alter alphabet/characters):
  - Strip typography markup (<b>, <i>) when emitting MDF lines …
  - Rejoin hyphenated line breaks from the transcription when forming headwords/glosses.
  …

Do NOT invent entries or text spans absent from the transcription.

Page boundary rules:
- Output only content that belongs to the CURRENT page.
…
```

**`role: user`** — text from `stage_2_direct_mdf_user_inference` (all placeholders filled):

```
Dictionary page extraction.

Inputs:
1. Stage-1 OCR transcription (bold = <b>…</b>, italic = <i>…</i>) or column TSV
   (column_id, line_number, text). Treat this as authoritative for all characters.
2. Photo of the dictionary page (image below) — layout and field-boundary reference only.

4. Attached SIL Toolbox MDF Reference Manual (PDF) — marker reference.
… line only present when --toolbox-pdf is set and the model accepts PDF vision …

MDF markers for Evenki-Russian (use these exactly):

\lx   headword / lexeme (vernacular lemma)
\gn   Russian gloss / translation
\sn   sense number
…

Rules:
- Separate homograph mains: two \lx blocks with same lemma, each with \hm N.
- Numbered senses: one \lx, then \sn 1, \gn …, \sn 2, \gn …
…

Parse every dictionary entry on the page into MDF text using the field map above.
Copy headword and gloss characters verbatim from the transcription except for the
structural normalisations listed in the system prompt.

<transcription>
A
<b>а̄́вда</b>  I. <i>v.</i> swell, rise …
… Stage 1 flat text for **this** page (e.g. page_3) …
</transcription>

USER DEFINED GUIDELINES
… only if --stage-2-guides PATH was passed …

Page boundary rules:
- Output only content that belongs to the CURRENT page.
…

<previous_page>
page: page_2
Use this page only for entry-boundary context.
<transcript>
… Stage 1 text for page_2 …
</transcript>
</previous_page>

<next_page>
page: page_4
Use this page only for entry-boundary context.
<transcript>
… Stage 1 text for page_4 if already processed …
</transcript>
</next_page>
```

The **`MDF markers for …`** block is not in `PROMPT.json` — it is built at runtime from Pass 1’s `parse-rules.json` (`format_prompt_block()`). In Pass 2, MUDIDI sends this block in a static user message before the page-specific transcript and images so providers can cache it when `--prompt-cache auto` is active.

**`role: user`** — vision parts after that text:

1. `[image]` previous page — inference only, if in the run’s page list
2. `[image]` next page — inference only, if in the run’s page list
3. `[image]` **current page**
4. `[file]` Toolbox PDF — only when `--toolbox-pdf` is set and the model reads PDFs through litellm (cacheable static context when provider support is available; see [Parse rules vs toolbox PDF](#parse-rules-vs-toolbox-pdf)); otherwise the manual text is inlined via `stage_2_toolbox_text_section` inside the static text block above

Introduction images are **not** sent in Pass 2; conventions are captured in the Pass 1 `parse-rules.json` rendered as `{field_block}` above.

---

### Prompt id quick reference

| Step                           | System prompt id                                   | User text built from                                                                                 |
| ------------------------------ | -------------------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| Stage 1 (default)              | `stage_1_system_{benchmark\|inference}`            | `stage_1_user_alphabet`? + `stage_1_user_ocr_reference`? + `stage_1_user_closing` + guides           |
| Stage 1 column                 | `stage_1_column_system`                            | same user blocks                                                                                     |
| Stage 2 Pass 1 (single sample) | `stage_2_pass_1` (+ nested `mdf_marker_reference`) | `stage_2_pass_2`                                                                                     |
| Stage 2 Pass 1 (multi sample)  | `stage_2_pass_1` (+ nested `mdf_marker_reference`) | `stage_2_pass_2_multi`                                                                               |
| Stage 2 Pass 2                 | `stage_2_direct_mdf_system_{benchmark\|inference}` | Static user message with `{field_block}` + `{toolbox_section}` + guides; dynamic user message with `{transcription}` + neighbors |

### Benchmark vs inference variants

Some steps use a **base id** plus a mode suffix. [`prompt_id_for_mode()`](src/mudidi/llm/prompt_mode.py) picks `base_benchmark` or `base_inference` when both exist; otherwise it falls back to the unsuffixed id.

| Base id                     | Suffixed variants          |
| --------------------------- | -------------------------- |
| `stage_1_system`            | `_benchmark`, `_inference` |
| `stage_2_direct_mdf_system` | `_benchmark`, `_inference` |
| `stage_2_direct_mdf_user`   | `_benchmark`, `_inference` |

Pass 1 prompts (`stage_2_pass_1`, `stage_2_pass_2`, `stage_2_pass_2_multi`) and Stage 1 user blocks (alphabet, OCR, closing) are **shared** across modes.

### Using a custom prompts file

```bash
cp assets/PROMPT.json my-prompts.json
# edit my-prompts.json — keep prompt ids the code expects, or update Python callers
uv run mudidi run \
  --pages my-dictionary/snippets \
  --parse-rules-page page_97 \
  --output-dir my-dictionary/output \
  --prompts-file my-prompts.json \
  --strategy two_stage \
  --stage1-mode flat
```

The store reloads when the file modification time changes (next LLM call). If you rename prompt ids, update the matching strings in `prompts.py`, `pass_1.py`, and `pass_2.py` (or `prompt_id_for_mode` bases).

---

## Tooling notes

- Use **`uv sync`** and **`uv run`** (or activate `.venv` first). This ensures dependencies and console scripts resolve correctly.
- LLM calls go through litellm; provider keys are inferred from the model string.
- **`pdftk`** is required when `--pages` is a PDF file (page splitting). Snippets-directory workflows do not need it.
- Specialised VLM backends (`--strategy vlm_ocr`) require separate model venvs — see [`docs/uv.md`](docs/uv.md#specialised-vlm-venvs). Most new-dictionary workflows use `--strategy two_stage` with a general LLM.

---

## Benchmark mode (evaluation)

The sections below describe how to run models against the MUDIDI **gold benchmark** — not needed for digitizing a new dictionary. Runnable walkthroughs: [`examples/README.md`](examples/README.md).

### Benchmark vs inference

|               | Inference (default)                                                                                                | Benchmark (`--benchmark`)              |
| ------------- | ------------------------------------------------------------------------------------------------------------------ | -------------------------------------- |
| Purpose       | Digitize your dictionary                                                                                           | Evaluate models against gold labels    |
| Inputs        | `--pages`, `--output-dir`                                                                                          | `--samples-dir` + samples tree layout  |
| Stage 2 input | Stage 1 predictions                                                                                                | Gold transcripts (default)             |
| Page context  | Previous/next **only among pages in this run** (see [Inference-specific behaviour](#inference-specific-behaviour)) | Independent pages (no neighbors)       |
| Output layout | `{output_dir}/stage-1/`, `stage-2/`                                                                                | `{lang}/outputs/stage-1/{experiment}/` |

### Examples (HF dataset layout)

Download the gated dataset to `dataset/mudidi/`, then:

```bash
bash examples/inference/run_directory_mode.sh
bash examples/evaluation/run_stage1_eval.sh
bash examples/evaluation/run_stage2_eval.sh
```

See [`examples/README.md`](examples/README.md) for PDF mode, environment overrides, and model flags.

### Dataset layout (Hugging Face release)

```
dataset/mudidi/dictionaries/<Source-Target>/
    Dictionary pages/          # snippet images or PDFs
    Introduction/              # optional preface pages
    Alphabet list/alphabet.txt
    dictionary_languages.yaml
    Stage 1 Gold OCR/          # human gold (evaluation)
    Stage 2 MDF file/          # MDF gold (10 dictionaries)
    Stage 2 Gold Cheat Sheet/  # parse-rules gold (10 dictionaries)
```

Manifests: `dataset/mudidi/manifest/pages.jsonl`, `dictionaries.jsonl`.

The legacy internal layout (`assets/dictionaries/samples/` with `snippets/` and `outputs/stage-1-gold/`) is used for paper-scale sweeps and is not required for the public examples.

### Dataset

The benchmark covers **30 public-domain bilingual dictionaries**. Gold data and manifests: [`dataset/mudidi/`](dataset/mudidi/) (also on [Hugging Face](https://huggingface.co/datasets/DavidSamuell/mudidi) as a gated dataset — request access before download). See [`dataset/mudidi/README.md`](dataset/mudidi/README.md).

### Paper results

Submission-time benchmark numbers are frozen in [`evaluations/`](evaluations/). Multi-model ablation sweeps from the paper are not maintained in public `examples/`.

---

## Documentation

| Doc                                                                        | Topic                       |
| -------------------------------------------------------------------------- | --------------------------- |
| [`docs/architecture.md`](docs/architecture.md)                             | Module map and data flow    |
| [`docs/stage_1_methodology.md`](docs/stage_1_methodology.md)               | Stage 1 pipeline detail     |
| [`docs/stage_2_methodology.md`](docs/stage_2_methodology.md)               | Pass 1 + Pass 2 design      |
| [`docs/mdf_field_reference.md`](docs/mdf_field_reference.md)               | SIL Toolbox MDF markers     |
| [`docs/stage_1_evaluation_metrics.md`](docs/stage_1_evaluation_metrics.md) | Benchmark metrics (Stage 1) |
| [`docs/stage_2_evaluation_metrics.md`](docs/stage_2_evaluation_metrics.md) | Benchmark metrics (Stage 2) |

---

## Citation

```bibtex
@misc{mudidi2026,
  title         = {{MUDIDI: A Two-Stage Framework for Multilingual Dictionary Digitization with Language Models}},
  author        = {Setiawan, David and Khishigsuren, Temuulen and Agarwal, Milind and Pit, Pagnarith and Mahmudi, Aso and Vylomova, Ekaterina},
  year          = {2026},
  eprint        = {2606.09435},
  archivePrefix = {arXiv},
  primaryClass  = {cs.CL},
  doi           = {10.48550/arXiv.2606.09435},
  url           = {https://arxiv.org/abs/2606.09435},
  note          = {Submitted to EMNLP 2026}
}
```
