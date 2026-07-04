# Agentic Verifier-Rewriter Plan

## Goal

Add an optional bounded verifier-rewriter loop after Stage 1 and/or Stage 2. The
loop should reduce page-level hallucinations and layout mistakes without turning
the pipeline into an open-ended agent. Each stage remains page-local: Stage 1 is
verified and finalized before Stage 2 consumes it, and Stage 2 is verified and
finalized immediately after its MDF output is produced.

## Non-Goals

- Do not replace the existing Stage 1 OCR or Stage 2 MDF prompts.
- Do not wait until a whole dictionary finishes before judging pages.
- Do not let an evaluator loop indefinitely.
- Do not depend on LangChain or another broad agent framework for the first
  version.

## CLI Surface

Recommended flags:

```bash
--stage1-agentic
--stage2-agentic
--agentic-max-iterations 2
--agentic-evaluator-model MODEL
--agentic-rewriter-model MODEL
--agentic-reasoning {none,low,medium,high}
--agentic-min-retry-confidence 0.55
--agentic-max-rewrite-delta-ratio 0.75
--agentic-max-patches-per-attempt 16
--no-agentic-verifier-patches
--no-agentic-concrete-retry-gate
```

Defaults:

- Agentic mode is off unless `--stage1-agentic` or `--stage2-agentic` is set.
- `--agentic-max-iterations` counts rewrite attempts after the initial output.
- Evaluator model defaults to the stage model.
- Rewriter model defaults to the stage model.
- Agentic reasoning defaults to `low`.
- Retry decisions below `--agentic-min-retry-confidence` are kept as audit
  findings but do not trigger a rewrite.
- Retry issues must include concrete localized evidence by default. The verifier
  should provide `line_index`, `current_text`, and `expected_text` whenever it
  can locate an exact edit.
- Exact verifier patches are applied before calling the rewriter when every
  issue has an unambiguous `current_text` -> `expected_text` replacement.
- Patch-heavy retry rounds above `--agentic-max-patches-per-attempt` are
  rejected before they can rewrite the page; this is a guard against broad,
  overconfident verifier batches.
- Rewrites whose normalized text delta exceeds
  `--agentic-max-rewrite-delta-ratio` are rejected and saved for audit.

## Stage 1 Flow

```text
page image + alphabet/OCR/page context
  -> normal Stage 1 OCR
  -> Stage 1 verifier JSON
  -> optional Stage 1 correction prompt
  -> final Stage 1 artifact
  -> Stage 2 consumes final Stage 1
```

The Stage 1 verifier receives:

- page image
- previous Stage 1 output
- alphabet text/image when available
- OCR hint when available
- page context when inference mode is active

The Stage 1 rewriter receives:

- page image
- previous Stage 1 output
- verifier JSON
- alphabet/OCR hints when available

The rewriter returns the same structured schema as the original Stage 1 mode:
flat JSON for flat mode, column JSON for column mode, with plain/typography
variant preserved.

## Stage 2 Flow

```text
final Stage 1 transcript
  -> normal Stage 2 MDF extraction
  -> Stage 2 verifier JSON
  -> optional Stage 2 correction prompt
  -> final Stage 2 MDF artifact
```

The Stage 2 verifier receives:

- final Stage 1 transcript used for the page
- previous MDF output
- parse rules / field map
- dictionary language/layout metadata when available

The Stage 2 rewriter receives:

- final Stage 1 transcript
- previous MDF output
- verifier JSON
- parse rules / field map

The rewriter returns corrected MDF text only.

## Verifier Schema

All verifier calls should return structured JSON:

```json
{
  "decision": "accept",
  "confidence": 0.93,
  "issues": [
    {
      "type": "reading_order_error",
      "severity": "high",
      "evidence": "The output transcribed all English entries before Circassian/Turkish tiers.",
      "suggested_fix": "Read aligned language columns row by row with | separators."
    }
  ],
  "retry_instruction": "Correct the reading order while preserving visible characters."
}
```

Valid decisions:

- `accept`: keep the current output.
- `retry`: run one correction attempt if budget remains.
- `reject`: stop the loop and keep the safest current output, with audit metadata.

## Stop Criteria

Stop when any of the following happens:

- verifier returns `accept`
- verifier returns `reject`
- rewrite budget is exhausted
- rewriter output is unchanged after normalization
- the same issue signature repeats
- verifier retry confidence is below the configured threshold
- verifier retry lacks concrete localized evidence
- rewriter output changes too much of the previous attempt
- verifier response is malformed after structured-output retry handling

The loop should fail closed: if the agentic verifier/rewriter fails after the
normal stage output exists, keep the normal output and write an audit decision
instead of failing the whole page by default.

## Artifacts

For a page-level output base, write attempts under:

```text
<page-dir>/agentic/
  stage1/
    attempt_0_output.txt
    attempt_0_verifier.json
    attempt_1_output.txt
    attempt_1_verifier.json
    attempt_1_rejected_output.txt
    final_decision.json
  stage2/
    attempt_0_output.mdf.txt
    attempt_0_verifier.json
    attempt_1_output.mdf.txt
    attempt_1_verifier.json
    attempt_1_rejected_output.mdf.txt
    final_decision.json
```

`attempt_0_output.*` is the normal stage output before correction. The main
Stage 1/Stage 2 artifact path should contain the final accepted or budget-limited
output.
`attempt_N_rejected_output.*` appears only when the destructive-rewrite guard
rejects a correction attempt.

## Evaluation Plan

Start with Stage 2 because it has stronger deterministic checks:

- MDF syntax validity
- marker sanity
- grounding against Stage 1 transcript
- lexical drift audit
- existing Stage 2 overall and per language-script evaluation

Then test Stage 1 on known layout failures, especially
`Circassian-English-Turkish`, where aligned language tiers can be mistaken for
independent columns.

Report:

- baseline score
- agentic score
- number of pages retried
- number of pages changed
- accept/retry/reject counts
- average extra cost and latency
- examples where the loop helped and where it hurt
