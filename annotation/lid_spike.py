"""Spike: how far does script-check get us, and where must LID step in?

Runs the Tier-2 first two stages (script-check -> binary target-vs-residual LID)
over three representative gold pages and reports:

  1. Script-check coverage  -- % of tokens resolved by Unicode script alone.
  2. Residual LID behaviour  -- of the leftover same-script tokens, how many a
     language identifier confidently calls a TARGET language (real English /
     French / Russian) vs leaves as SOURCE, at a few confidence thresholds.

We have no per-token gold labels yet, so this measures *coverage and behaviour*,
not precision/recall -- enough to decide which dictionaries the cheap pipeline
can carry and which need the LLM. Eyeball the printed residual verdicts: TARGET
spans should read as real target-language words; SOURCE spans should be romanized
headwords / function words.

Run:  uv run python annotation/lid_spike.py
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).resolve().parent))
from script_check import ScriptConfig, TokenCategory, classify_token  # noqa: E402

from lingua import Language, LanguageDetectorBuilder  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DICT = ROOT / "dataset" / "MUDIDI" / "dictionaries"

TAG_RE = re.compile(r"<!--.*?-->|</?[a-zA-Z][^>]*>")  # strip <b>/<i> + HTML comments
THRESHOLDS = (0.0, 0.50, 0.70)  # 0.0 == argmax


@dataclass
class Case:
    name: str
    page: Path
    cfg: ScriptConfig
    targets: List[Language]
    decoys: List[Language]


CASES = [
    Case(
        name="Canala-English (IPA source, French embedded)",
        page=DICT / "Canala-English/Stage 1 Gold OCR/page_12/page_12_stage1_GOLD_flat.txt",
        cfg=ScriptConfig(target_scripts={"latin"}, source_is_ipa=True),
        targets=[Language.ENGLISH, Language.FRENCH],
        decoys=[Language.ITALIAN, Language.SPANISH, Language.LATIN, Language.GERMAN],
    ),
    Case(
        name="Chukchi-Russian (ext-Cyrillic source vs Russian)",
        page=DICT / "Chukchi-Russian/Stage 1 Gold OCR/page_48/page_48_stage1_GOLD_flat.txt",
        cfg=ScriptConfig(target_scripts={"cyrillic"}, source_is_cyrillic_ext=True),
        targets=[Language.RUSSIAN],
        decoys=[Language.UKRAINIAN, Language.BULGARIAN, Language.SERBIAN,
                Language.MACEDONIAN, Language.ENGLISH],
    ),
    Case(
        name="Na-English-Chinese-French (4-way; Han split by script)",
        page=DICT / "Na-English-Chinese-French/Stage 1 Gold OCR/page_186/page_186_stage1_GOLD_flat.txt",
        cfg=ScriptConfig(
            target_scripts={"latin"},
            source_is_ipa=True,
            distinct_targets={"han": "Chinese"},
        ),
        targets=[Language.ENGLISH, Language.FRENCH],
        decoys=[Language.ITALIAN, Language.SPANISH, Language.LATIN, Language.GERMAN],
    ),
]


def load_tokens(page: Path) -> List[str]:
    text = TAG_RE.sub(" ", page.read_text(encoding="utf-8"))
    return [t for t in text.split() if t.strip()]


def lid_verdict(detector, text: str, targets: List[Language]):
    confs = detector.compute_language_confidence_values(text)
    if not confs:
        return None, 0.0, {thr: False for thr in THRESHOLDS}
    top = confs[0]
    is_target = {
        thr: (top.language in targets and top.value >= thr) for thr in THRESHOLDS
    }
    return top.language, round(top.value, 3), is_target


def runs_of_residual(labelled):
    runs, cur = [], []
    for tok, lab in labelled:
        if lab.category == TokenCategory.RESIDUAL:
            cur.append(tok)
        elif cur:
            runs.append(" ".join(cur))
            cur = []
    if cur:
        runs.append(" ".join(cur))
    return runs


def report(case: Case) -> None:
    print("=" * 78)
    print(case.name)
    print("=" * 78)
    tokens = load_tokens(case.page)
    labelled = [(t, classify_token(t, case.cfg)) for t in tokens]

    counts = {c: 0 for c in TokenCategory}
    for _, lab in labelled:
        counts[lab.category] += 1
    n = len(tokens)
    resolved = counts[TokenCategory.SOURCE] + counts[TokenCategory.DISTINCT_TARGET]
    print(f"\ntokens: {n}")
    print(f"  script-check SOURCE      : {counts[TokenCategory.SOURCE]:4d}")
    print(f"  script-check TARGET(Han) : {counts[TokenCategory.DISTINCT_TARGET]:4d}")
    print(f"  punctuation/digits       : {counts[TokenCategory.PUNCT]:4d}")
    print(f"  RESIDUAL (needs LID)     : {counts[TokenCategory.RESIDUAL]:4d}")
    non_punct = n - counts[TokenCategory.PUNCT]
    if non_punct:
        print(f"  -> script-check resolves {resolved}/{non_punct} "
              f"({100*resolved/non_punct:.1f}%) of non-punct tokens deterministically")

    detector = (
        LanguageDetectorBuilder
        .from_languages(*case.targets, *case.decoys)
        .build()
    )

    residual_tokens = [t for t, lab in labelled if lab.category == TokenCategory.RESIDUAL]

    tok_target = {thr: 0 for thr in THRESHOLDS}
    examples = []
    for tok in residual_tokens:
        lang, conf, is_t = lid_verdict(detector, tok, case.targets)
        for thr in THRESHOLDS:
            tok_target[thr] += int(is_t[thr])
        examples.append((tok, lang.name if lang else "?", conf, is_t[0.5]))

    print(f"\nResidual LID (token-level, {len(residual_tokens)} tokens):")
    for thr in THRESHOLDS:
        tgt = tok_target[thr]
        src = len(residual_tokens) - tgt
        lbl = "argmax" if thr == 0.0 else f">={thr}"
        print(f"  tau {lbl:>7}:  TARGET={tgt:4d}   SOURCE(residual)={src:4d}")

    runs = runs_of_residual(labelled)
    run_target = 0
    for run in runs:
        _, _, is_t = lid_verdict(detector, run, case.targets)
        run_target += int(is_t[0.5])
    print(f"\nResidual LID (segment-level, {len(runs)} runs, tau>=0.5):"
          f"  TARGET={run_target}   SOURCE={len(runs)-run_target}")

    print("\n  sample residual tokens (token, lid_top, conf, target@0.5):")
    for tok, lang, conf, is_t in examples[:24]:
        flag = "TARGET" if is_t else "source"
        print(f"    {tok[:22]:22s} {lang:9s} {conf:>5}  -> {flag}")
    print()


def main() -> None:
    for case in CASES:
        if not case.page.is_file():
            print(f"!! missing gold page: {case.page}")
            continue
        report(case)


if __name__ == "__main__":
    main()
