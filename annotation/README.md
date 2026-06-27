# annotation/ — gold language span-map labeling

This workspace **produces** the per-page language span maps (`*_lang.json`,
`PageLanguageMap`) that the package evaluation consumes. The evaluation itself
lives in the package (`src/mudidi/evaluation/stage1/` +
`src/mudidi/schemas/language_span.py`), not here — `annotation/` is the labeling
process only. Dependency direction is **annotation → mudidi** (never the reverse).

## Layout

| Path | What |
|------|------|
| `labelers/` | The two-tier gold labelers (the deliverable). |
| `labelers/script_check.py` | Unicode script classifier (`classify_token`) — the Tier-1 primitive. |
| `labelers/tier1_labeler.py` | Tier-1 deterministic script-check labeler (9 script-distinct dicts). |
| `labelers/tier2_recovery.py` | Tier-2 tag-injection → validated `PageLanguageMap` (offset recovery, drift gate). |
| `labelers/tier2_labeler.py` | Tier-2 LLM labeler (21 same-script dicts; `gemini/gemini-3-flash-preview`). |
| `label_studio/` | Label Studio NER bridge. |
| `label_studio/label_studio_ner.py` | `PageLanguageMap` ⇄ Label Studio NER task import/export. |
| `label_studio/span_schema.py` | Compat shim re-exporting `mudidi.schemas.language_span` for flat imports. |
| `spikes/` | Exploratory only — not part of the pipeline. |
| `spikes/lid_spike.py` | LID-vs-script-check coverage spike (needs `lingua`). |
| `docs/` | Write-ups and decisions (no code). |
| `docs/mapping.md` | Manual 30-dictionary script/language map. |
| `docs/routing.md` | Tier-1 vs Tier-2 routing decision (9 / 21). |
| `docs/SPIKE_FINDINGS.md` | LID spike conclusions. |
| `tests/` | Unit tests; `conftest.py` puts `labelers/` and `label_studio/` on `sys.path`. |

The labeler modules use **flat sibling imports** (`from script_check import ...`)
resolved via `sys.path.insert(parent)`, so co-dependent modules stay in the same
subfolder. Tests resolve the same flat names through `tests/conftest.py`.

## Common commands

```bash
# Tier-1 (deterministic) — write span maps for the script-distinct dicts
uv run python annotation/labelers/tier1_labeler.py

# Tier-2 (LLM) — all same-script dicts, or one via --dictionary; --dry-run prints the prompt
uv run python annotation/labelers/tier2_labeler.py
uv run python annotation/labelers/tier2_labeler.py --dictionary Canala-English --limit 1

# Tests (not in the default pytest testpaths — point pytest at this dir)
uv run pytest annotation/tests/
```
