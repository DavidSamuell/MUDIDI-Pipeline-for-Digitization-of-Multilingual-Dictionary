# MUDIDI

Digitize scanned bilingual dictionary pages into structured lexicon records using LLMs.

MUDIDI runs a two-stage pipeline:

1. **Stage 1 — transcription** — faithful OCR of each page (Unicode, diacritics, bold/italic markup).
2. **Stage 2 — MDF export** — parse the transcript into [SIL Toolbox MDF](https://software.sil.org/toolbox/) records.

This README focuses on **running the pipeline on a new dictionary**. Benchmark and paper-reproduction instructions are at the bottom.

---

## Prerequisites

Install the tools below **before** cloning the repo. MUDIDI uses [uv](https://docs.astral.sh/uv/) to create a project virtualenv (`.venv/`) and install locked Python dependencies — you do not need to run `pip install` yourself.

### Supported platforms

| Platform | Support |
|----------|---------|
| **Linux** | Fully supported — primary development and HPC target. |
| **macOS** | Fully supported — same workflow as Linux. |
| **Windows** | Use **[WSL2](https://learn.microsoft.com/en-us/windows/wsl/install)** (Ubuntu recommended), then follow the **Linux** steps below. Native Windows (PowerShell / cmd) is not supported. |

**Windows users:** install WSL2, open an Ubuntu terminal, and treat your machine as Linux for everything in this README — prerequisites, install, `uv sync`, bash scripts under `examples/`, and `pdftk`. No separate Windows commands are required.

Minimal WSL setup (run once in **PowerShell as Administrator** on Windows):

```powershell
wsl --install -d Ubuntu
```

Restart if prompted, launch **Ubuntu** from the Start menu, then continue with the Linux instructions below. Clone the repo inside your WSL home directory (e.g. `~/MUDIDI`) or under `/mnt/c/...` if you prefer files on the Windows drive — both work; WSL home is usually faster for Python tooling.

### Git

Required to clone the repository.

| Platform | Install |
|----------|---------|
| **Linux / WSL** | `sudo apt install git` (Debian/Ubuntu), `sudo dnf install git` (Fedora/RHEL), or your distro’s package manager |
| **macOS** | [Xcode Command Line Tools](https://developer.apple.com/xcode/resources/) (`xcode-select --install`) or `brew install git` |

### uv

Required. uv manages Python and project dependencies.

| Platform | Install |
|----------|---------|
| **Linux / WSL** | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| **macOS** | `curl -LsSf https://astral.sh/uv/install.sh \| sh` — or `brew install uv` |

After installing, open a **new** terminal and confirm:

```bash
uv --version
```

**Python 3.10+** is required (`pyproject.toml`). You usually do not need to install Python separately — on first `uv sync`, uv uses a suitable interpreter on your `PATH` or downloads one automatically.

You also need **network access** for the first `uv sync` (packages are downloaded into uv’s cache, then installed into `.venv/`).

### pdftk (conditional)

**Only required when `--pages` points to a PDF file** — MUDIDI uses pdftk to split multi-page PDFs into single-page inputs. If you use a **snippets directory** of per-page images (`.png`, `.jpg`, …), you can skip pdftk.

Install pdftk and ensure `pdftk` is on your `PATH`:

| Platform | Install |
|----------|---------|
| **Linux / WSL** (Debian/Ubuntu) | `sudo apt install pdftk-java` |
| **Linux** (Fedora/RHEL) | `sudo dnf install pdftk-java` |
| **macOS** | `brew install pdftk-java` |

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

| Key | Used for |
|-----|----------|
| `GEMINI_API_KEY` | Gemini models (`gemini/...`) |
| `OPEN_ROUTER_API_KEY` | GPT, Claude, Qwen via OpenRouter (`openrouter/...`) |

Models are routed through [litellm](https://github.com/BerriAI/litellm). The model string selects the provider (e.g. `gemini/gemini-3-flash-preview`, `openrouter/openai/gpt-5.5`).

---

## Prepare your dictionary folder

You can supply pages in either of two ways:

### Option A — snippets directory (recommended for large jobs)

Place inputs in a working directory (layout is flexible; paths are passed on the CLI):

```
my-dictionary/
    snippets/                  # required — page images or PDFs (page_1.png, page_2.pdf, …)
    introduction/              # optional — front matter for Stage 2 Pass 1
    dictionary_languages.yaml  # optional — source/target roles (see below)
    alphabet.txt               # optional — source-script character inventory
```

**`snippets/`** — one file per dictionary page. Supported: `.png`, `.jpg`, `.jpeg`, `.webp`, `.pdf`. Pages are processed in numeric order (`page_1`, `page_2`, …, `page_10`).

**`introduction/`** — front matter for **Stage 2 Pass 1** (parse-rules discovery): abbreviations, entry structure, and which MDF markers the dictionary uses. Pass 2 uses the cached `parse-rules.json`, not the intro images again.

**`dictionary_languages.yaml`** — optional hint for Pass 1: which language is the headword source, which are gloss targets, and a coarse page-layout label. See [dictionary_languages.yaml](#dictionary_languagesyaml) below.

**`alphabet.txt`** — character list or legend for the vernacular script. Improves Stage 1 accuracy on rare glyphs.

### `dictionary_languages.yaml`

This file is **not** sent to the LLM verbatim. It is loaded at startup and summarized as a short hint in the **Stage 2 Pass 1** user prompt (`{config_hint}`: layout, source language, target languages). Pass 2 then follows the discovered **`parse-rules.json`**, not the YAML directly.

**Where to put it**

| Run | Path |
|-----|------|
| Inference (`--pages my-dictionary/snippets`) | `my-dictionary/dictionary_languages.yaml` (same folder that contains `snippets/`) |
| Benchmark (`--samples-dir …/samples`) | `assets/dictionaries/samples/<Lang-Pair>/dictionary_languages.yaml` |

**What to put inside** — required fields:

| Field | Meaning |
|-------|---------|
| `layout` | One of MUDIDI’s three supported layout labels (see below). Pick the **closest match** to your dictionary — you do not need to use this wording in your intro or paper. |
| `source` | Headword / vernacular language (`language` only — use the name that fits your dictionary, e.g. `Evenki`, `Circassian`). |
| `targets` | Gloss / translation languages (`language` per target). One or more entries. |


**`layout` values (examples, not a closed world)** — MUDIDI only understands these three strings today:

| Value | Typical dictionary shape |
|-------|---------------------------|
| `bilingual` | One vernacular headword with one gloss language per entry (most two-language dictionaries). |
| `inline_trilingual` | Several target languages mixed **inside the same entry block** (e.g. multiple glosses or scripts on one line). |
| `column_trilingual` | Headwords and glosses in **separate columns** (e.g. vernacular center, English left, Turkish right). |

If none fits well, choose the nearest option and rely on clear `language` names in `source` / `targets`; Pass 1 also sees your introduction and sample page.

You only need human-readable `language` names — no short `code` field. Legacy YAML files that still include `code` are accepted; that field is ignored on load.

**Minimal bilingual example** (Evenki → Russian):

```yaml
layout: bilingual
source:
  language: Evenki
targets:
  - language: Russian
```

**Column trilingual example** (headword in center column, glosses left/right):

```yaml
layout: column_trilingual
source:
  language: Circassian
  column_id: center
targets:
  - language: English
    column_id: left
  - language: Turkish
    column_id: right
```

### Option B — single source PDF

Pass the full scanned dictionary PDF on `--pages` and list which **1-based PDF page numbers** to process. Dictionary entries and introduction can both come from the same file — use `--dict-pages` for entry pages and `--intro-pages` for front matter. MUDIDI splits each page internally with **pdftk** (must be installed and on `PATH`).

| Flag | Required | Page spec examples |
|------|----------|-------------------|
| `--pages dictionary.pdf` | yes | path to the scan |
| `--dict-pages` | yes | `97-123`, `1,3,5`, `97-123, 179-182` |
| `--intro-pages` | no | `1-5`, `1,2,4` (same PDF as `--pages`) |

Do **not** pass `--intro` when using a PDF — introduction pages are selected with `--intro-pages` from the same file.

Split pages are cached under `{output_dir}/.rendered_snippets/split/` (dictionary) and `{output_dir}/.rendered_intro/split/` (introduction) as `page_{N}.pdf`. Re-runs reuse cached splits unless you pass `--overwrite`.

**pdftk:** required for this workflow — see [pdftk (conditional)](#pdftk-conditional) under Prerequisites.

---

## Quick start — full pipeline

Run Stage 1 and Stage 2 in one command. Stage 2 automatically reads Stage 1 output from the same run.

**Option A — `--pages` points to a directory** (one image/PDF per page):

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

Place `dictionary_languages.yaml` in `my-dictionary/` (parent of `snippets/`). MUDIDI loads it automatically when you run the command above.

`--parse-rules-page` selects which snippet(s) Stage 2 **Pass 1** uses for parse-rules discovery (default: first page in `--pages`). Stems must match files in `snippets/` (e.g. `page_97.png` → `page_97`). Pass 1 runs **once** per `--output-dir`; the result is cached as `parse-rules.json` and **reused on the next run** unless you pass `--overwrite` or delete that file.

**Option B — `--pages` points to a single PDF** (same file for dict + intro; requires `pdftk`):

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

Non-contiguous PDF pages (Option B only):

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

| Flag | When to use |
|------|-------------|
| `--parse-rules-page STEM` | Pick sample page(s) from the **same `--pages` input** (directory or PDF-split stems). Default: first page. |
| `--parse-rules-page A,B` or repeat the flag | **Two or more** samples → one Pass 1 call with the multi-sample prompt (`stage_2_pass_2_multi`). Use when sections differ (main body vs appendix). |
| `--parse-rules-file PATH` | Skip Pass 1 LLM entirely — load your hand-edited `parse-rules.json`. Always reads **your** file, even if `{output_dir}/parse-rules.json` already exists from a prior run. |

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

Stage 2 reads `{output_dir}/stage-1/{page}/{page}_stage1_flat.txt` by default in inference mode.

---

## What you get — output layout

All artifacts land under `--output-dir`:

```
output/
├── parse-rules.json               # Stage 2 Pass 1: MDF markers + entry rules (once per dictionary; review before large Pass 2 runs)
├── stage-1/
│   └── page_1/
│       ├── page_1_stage1_flat.txt     # Stage 1 transcript (one line per visible row)
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

| Command | Purpose |
|---------|---------|
| `mudidi run` | Run Stage 1, Stage 2, or both on your dictionary |
| `mudidi eval stage1` | Evaluate Stage 1 against gold transcripts (benchmark) |
| `mudidi eval stage2` | Evaluate Stage 2 MDF against gold (benchmark) |
| `mudidi-eval-flat` | Same as `mudidi eval stage1` (standalone script) |
| `mudidi-eval-stage2-mdf` | Same as `mudidi eval stage2` (standalone script) |

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

| Flag | Description |
|------|-------------|
| `--pages PATH` | Snippets directory **or** a single source PDF |
| `--output-dir PATH` | Where to write `stage-1/` and `stage-2/` results |
| `--dict-pages SPEC` | **Required when `--pages` is a PDF.** 1-based dictionary page numbers: `1-10`, `1,3,5`, or `97-123, 179-182` |

### Common optional flags

| Flag | Default | Description |
|------|---------|-------------|
| `--stage {1,2,all}` | `all` | Run transcription only, MDF only, or both |
| `--intro PATH` | — | Introduction directory or text/image file (snippets-directory mode only) |
| `--intro-pages SPEC` | — | When `--pages` is a PDF: intro pages from the **same PDF** (same syntax as `--dict-pages`) |
| `--alphabet PATH` | — | Alphabet file (`.txt`/`.md`) or image |
| `--ocr-text PATH` | — | Optional OCR hint directory (`.md`/`.docx`/`.txt` per page). Benchmark ablation showed limited benefit — omit unless experimenting |
| `--prompts-file PATH` | bundled `PROMPT.json` | Custom prompts; edits reload on next LLM call |
| `--parse-rules-page STEM` | first page in `--pages` | Pass 1 sample page stem(s). Must exist under `--pages` (snippets dir or PDF split). Repeat the flag or comma-separate (`page_50,page_200`). **Two or more** → multi-sample Pass 1 prompt. |
| `--parse-rules-file PATH` | — | Load curated `parse-rules.json`; skip Pass 1 LLM discovery. **Always** reads your file (overrides any existing `{output_dir}/parse-rules.json`) and refreshes the output copy. |
| `--parse-rules-gold` | off | Benchmark: load gold `parse-rules.json` from `outputs/stage-2-gold/` (skips Pass 1 LLM) |
| `--stage1-source {gold,predictions}` | `predictions` | Stage 2 input source (inference uses predictions) |

### Model selection

Use **`--model`** to set the same litellm model string for every step (Stage 1, Stage 2 Pass 1 parse-rules discovery, Stage 2 Pass 2 MDF extraction). Override individual steps when you want different models or reasoning budgets.

**Typical inference setup:** Gemini 3 Flash for Stage 1 transcription, Gemini 3.1 Pro for both Stage 2 passes, with `--stage2-reasoning medium`:

```bash
--stage-1-model gemini/gemini-3-flash-preview \
--model gemini/gemini-3.1-pro-preview \
--stage2-reasoning medium
```

| Flag | Applies to | Default |
|------|------------|---------|
| `--model` | All steps when no step-specific flag is set | `gemini/gemini-3-flash-preview` |
| `--stage-1-model` | Stage 1 page transcription | `--model` |
| `--stage-2-pass-1-model` | Stage 2 Pass 1 (`parse-rules.json` discovery) | `--model` |
| `--stage-2-pass-2-model` | Stage 2 Pass 2 (per-page MDF) | `--model` |

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

| Flag | Default | Description |
|------|---------|-------------|
| `--strategy` | `two_stage` | `two_stage` (LLM) or `vlm_ocr` (specialised VLM backends) |
| `--stage1-mode {column,flat}` | `column` | Stage 1 output format; use **`flat`** for new dictionaries |
| `--stage1-reasoning {none,low,medium,high}` | `low` | Stage 1 reasoning effort |
| `--stage2-reasoning {low,medium,high}` | `low` | Stage 2 reasoning effort |
| `--toolbox-pdf PATH` | — | Optional: attach a SIL Toolbox MDF reference PDF during **Stage 2 Pass 2 only**. Full manual: [`assets/Pages from ToolboxReferenceManual.pdf`](assets/Pages%20from%20ToolboxReferenceManual.pdf) (~65 pages). Expensive at scale — see [Parse rules vs toolbox PDF](#parse-rules-vs-toolbox-pdf). |
| `--stage-1-guides PATH` | — | Extra rules appended to Stage 1 prompt |
| `--stage-2-guides PATH` | — | Extra rules appended to Stage 2 prompt |
| `--overwrite` | off | Re-process pages even if output exists; also **re-runs Pass 1 LLM discovery** when `{output_dir}/parse-rules.json` already exists |
| `--limit N` | — | Process at most N pages |
| `--no-alphabet` | off | Skip alphabet hint |
| `--no-ocr-hint` | off | Skip OCR hint |
| `--no-intro` | off | Skip introduction for Stage 2 Pass 1 (field discovery) |

### Inference-specific behaviour

- **Neighbor page context** — in inference mode, each page receives previous/next page images (and prior transcripts when available) so the model can handle entries that span page breaks. Output still belongs to the current page only.
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

**Stage 1** transcribes every visible line on the page image. Use `--stage1-mode flat` for the standard one-line-per-row format.

**Stage 2 Pass 1** runs **once** per `--output-dir`: reads the introduction + one or more sample pages selected by `--parse-rules-page` (+ optional `dictionary_languages.yaml` hint) and writes `parse-rules.json`. With a single sample, the user prompt is `stage_2_pass_2`; with two or more samples, `stage_2_pass_2_multi`. Alternatively, pass `--parse-rules-file` to load rules you edited by hand.

**Stage 2 Pass 2** runs per page: copies characters verbatim from the Stage 1 transcript and assigns MDF markers using `parse-rules.json` (introduction is not re-attached).

### Parse rules vs toolbox PDF

Stage 2 Pass 1 writes **`parse-rules.json`** once per dictionary run — a compact cheat sheet of which MDF markers this dictionary uses, one-line descriptions, and entry-structure rules (homographs, senses, subentries, gloss lines). Pass 2 injects that file into every page prompt as the `{field_block}`; it is **not** re-discovered per page.

**Choosing Pass 1 samples:** Pick a `--parse-rules-page` stem that represents typical body entries (not front matter). For dictionaries whose layout changes mid-book (appendix, reverse index, botanical names), pass **multiple** samples so Pass 1 can merge conventions in one shot, then review `{output_dir}/parse-rules.json` before a large Pass 2 run.

The repository includes the full SIL Toolbox MDF reference excerpt at [`assets/Pages from ToolboxReferenceManual.pdf`](assets/Pages%20from%20ToolboxReferenceManual.pdf) (~65 pages). Pass it with `--toolbox-pdf` during **Pass 2 only**. That can help when marker conventions are ambiguous, but on Gemini the PDF is included in **every Pass 2 API call**, so cost scales with dictionary size × manual size.

**Best practice for full-dictionary inference:**

1. Run Stage 2 Pass 1 once (with representative `--parse-rules-page` sample(s) and good introduction input). Use multiple samples when sections differ, e.g. `--parse-rules-page page_50 --parse-rules-page page_200`.
2. Open `{output_dir}/parse-rules.json` and **review it** — fix marker descriptions, add missing markers, tighten structure rules for this script and language pair. Or supply a hand-edited file with `--parse-rules-file`.
3. Re-run Pass 2 (`--stage 2`) **without** `--toolbox-pdf`, relying on your curated `parse-rules.json`. Pass 1 is skipped on resume when the file already exists (unless you pass `--overwrite`).
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

| Field | Role |
|-------|------|
| `description` | **Documentation only** — when this prompt is used (benchmark vs inference, which pipeline step). Not sent to the model. |
| `prompt` | Template text sent to the model (may contain `{name}` placeholders). |
| `variables` | **Documentation only** — placeholder cheat sheet for editors. |

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

1. `[image]` previous page (`page_2.png`) — inference only, if it exists  
2. `[image]` next page — inference only, if it exists  
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

The **`MDF markers for …`** block is not in `PROMPT.json` — it is built at runtime from Pass 1’s `parse-rules.json` (`format_prompt_block()`).

**`role: user`** — vision parts after that text:

1. `[image]` previous page — inference only  
2. `[image]` next page — inference only  
3. `[image]` **current page**  
4. `[image]` Toolbox PDF — only when `--toolbox-pdf` is set and the model reads PDFs (expensive at scale; see [Parse rules vs toolbox PDF](#parse-rules-vs-toolbox-pdf)); otherwise the manual text is inlined via `stage_2_toolbox_text_section` inside the text block above  

Introduction images are **not** sent in Pass 2; conventions are captured in the Pass 1 `parse-rules.json` rendered as `{field_block}` above.

---

### Prompt id quick reference

| Step | System prompt id | User text built from |
|------|------------------|----------------------|
| Stage 1 (default) | `stage_1_system_{benchmark\|inference}` | `stage_1_user_alphabet`? + `stage_1_user_ocr_reference`? + `stage_1_user_closing` + guides |
| Stage 1 column | `stage_1_column_system` | same user blocks |
| Stage 2 Pass 1 (single sample) | `stage_2_pass_1` (+ nested `mdf_marker_reference`) | `stage_2_pass_2` |
| Stage 2 Pass 1 (multi sample) | `stage_2_pass_1` (+ nested `mdf_marker_reference`) | `stage_2_pass_2_multi` |
| Stage 2 Pass 2 | `stage_2_direct_mdf_system_{benchmark\|inference}` | `stage_2_direct_mdf_user_{benchmark\|inference}` + `{field_block}` + `{toolbox_section}` + neighbors |

### Benchmark vs inference variants

Some steps use a **base id** plus a mode suffix. [`resolve_prompt_id()`](src/mudidi/llm/prompt_mode.py) picks `base_benchmark` or `base_inference` when both exist; otherwise it falls back to the unsuffixed id.

| Base id | Suffixed variants |
|---------|-------------------|
| `stage_1_system` | `_benchmark`, `_inference` |
| `stage_2_direct_mdf_system` | `_benchmark`, `_inference` |
| `stage_2_direct_mdf_user` | `_benchmark`, `_inference` |

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

The store reloads when the file modification time changes (next LLM call). If you rename prompt ids, update the matching strings in `prompts.py`, `pass_1.py`, and `pass_2.py` (or `resolve_prompt_id` bases).

---

## Tooling notes

- Use **`uv sync`** and **`uv run`** (or activate `.venv` first). This ensures dependencies and console scripts resolve correctly.
- LLM calls go through litellm; provider keys are inferred from the model string.
- **`pdftk`** is required when `--pages` is a PDF file (page splitting). Snippets-directory workflows do not need it.
- Specialised VLM backends (`--strategy vlm_ocr`) require separate model venvs — see [`examples/helper/install_models_venv.sh`](examples/helper/install_models_venv.sh). Most new-dictionary workflows use `--strategy two_stage` with a general LLM.

---

## Benchmark mode (paper / evaluation)

The sections below are for reproducing the MUDIDI benchmark on the 30-dictionary evaluation set — not needed for digitizing a new dictionary.

### Benchmark vs inference

| | Inference (default) | Benchmark (`--benchmark`) |
|--|---------------------|---------------------------|
| Purpose | Digitize your dictionary | Evaluate models against gold labels |
| Inputs | `--pages`, `--output-dir` | `--samples-dir` + samples tree layout |
| Stage 2 input | Stage 1 predictions | Gold transcripts (default) |
| Page context | Previous/next pages | Independent pages |
| Output layout | `{output_dir}/stage-1/`, `stage-2/` | `{lang}/outputs/stage-1/{experiment}/` |

### Benchmark quick start

```bash
uv run mudidi run --benchmark \
  --samples-dir assets/dictionaries/samples \
  --languages Evenki-Russian \
  --experiment-name gemini31pro_flat_alpha \
  --stage 1 \
  --strategy two_stage \
  --stage1-mode flat \
  --model gemini/gemini-3-flash-preview
```

Paper sweeps:

```bash
bash examples/stage-1/run_stage1_extraction.sh
bash examples/stage-2/run_stage2_extraction.sh
bash examples/evaluation/run_stage1_eval_flat.sh
bash examples/evaluation/run_stage2_eval_mdf.sh
```

### Benchmark sample layout

```
assets/dictionaries/samples/<Source-Target>/
    snippets/
    introduction/
    alphabet.txt
    dictionary_languages.yaml
    outputs/                     # populated by the pipeline
        stage-1-gold/            # human gold (evaluation only)
        stage-2-gold/            # gold parse-rules.json (legacy name: field_cheatsheet.json)
        stage-1/<experiment>/
        stage-2/<experiment>/      # includes parse-rules.json per experiment
```

### Dataset

The benchmark covers **30 public-domain bilingual dictionaries**. Gold data and manifests: [`dataset/mudidi/`](dataset/mudidi/). See [`dataset/mudidi/README.md`](dataset/mudidi/README.md).

### Reproducing paper tables

| Paper artifact | Command |
|----------------|---------|
| Table 2 — Stage 1 alphabet ablation | `examples/stage-1/run_stage1_extraction.sh` + `examples/evaluation/run_stage1_eval_flat.sh` |
| Table 3 — Stage 1 OCR-hint ablation | `examples/stage-1/run_stage1_per_lang_best_flat_alpha_ocr.sh` + eval script |
| Table 4 — Stage 2 MDF aggregate | `examples/stage-2/run_stage2_extraction.sh` + `examples/evaluation/run_stage2_eval_mdf.sh` |
| Table 5 — Stage 2 gold cheat-sheet | `examples/stage-2/run_stage2_gold_cheatsheet.sh` + eval script |

Frozen evaluation outputs: [`evaluations/`](evaluations/).

---

## Documentation

| Doc | Topic |
|-----|-------|
| [`docs/architecture.md`](docs/architecture.md) | Module map and data flow |
| [`docs/stage_1_methodology.md`](docs/stage_1_methodology.md) | Stage 1 pipeline detail |
| [`docs/stage_2_methodology.md`](docs/stage_2_methodology.md) | Pass 1 + Pass 2 design |
| [`docs/mdf_field_reference.md`](docs/mdf_field_reference.md) | SIL Toolbox MDF markers |
| [`docs/stage_1_evaluation_metrics.md`](docs/stage_1_evaluation_metrics.md) | Benchmark metrics (Stage 1) |
| [`docs/stage_2_evaluation_metrics.md`](docs/stage_2_evaluation_metrics.md) | Benchmark metrics (Stage 2) |

---

## Citation

```bibtex
@inproceedings{mudidi2026,
  title  = {MUDIDI: A Two-Stage Framework for Multilingual Dictionary Digitization with Language Models},
  author = {Anonymous},
  year   = {2026},
  note   = {Under review}
}
```
