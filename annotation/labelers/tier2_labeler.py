"""Tier-2 LLM labeler: tag-injection gold language span maps for same-script dicts.

For the 21 dictionaries where source and a target share a script (IPA/Latin vs
English, extended-Cyrillic vs Russian, romanization colliding with the target, or
two same-script low-resource languages), script-check cannot separate the languages.
This labeler sends the **raw** gold to ``gemini/gemini-3-flash-preview`` (the same
model and ``mudidi.llm.client`` path as the Stage 1 OCR run) and asks it to re-emit
the text wrapped in language tags, then recovers offsets deterministically
(:mod:`annotation.tier2_recovery`) into the same ``*_lang.json`` artifact the Tier-1
labeler produces.

Language seeding (PRD D-4): ``dictionary_languages.yaml`` is unreliable (e.g. Canala
carries French the yaml omits), so the seed list = yaml languages plus an optional,
hand-edited ``language_rules.yaml`` in the dictionary folder. The prompt also lets the
model introduce a tag for a language outside the seed (open vocabulary); the languages
it actually used are reported per page and the human reviewer in Label Studio is the
final backstop (D-5).

The LLM call makes a live request and needs ``GEMINI_API_KEY``; use ``--dry-run`` to
print the prompt for one page without calling the model.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tier1_labeler import (  # noqa: E402  (flat sibling import; reuse discovery)
    TIER1_DICTIONARIES,
    discover_gold_pages,
    read_languages,
    _lang_map_path,
    _page_number,
)
from tier2_recovery import recover_page_map  # noqa: E402

from mudidi.llm.client import complete_with_usage  # noqa: E402
from mudidi.schemas.language_span import META, PageLanguageMap  # noqa: E402

DEFAULT_MODEL = "gemini/gemini-3-flash-preview"
DEFAULT_MAX_TOKENS = 32000
DEFAULT_REASONING_EFFORT = "low"


def read_language_seed(dictionary_dir: str | Path) -> List[str]:
    """Return the seed language list: yaml languages + optional ``language_rules.yaml``.

    ``language_rules.yaml`` (when present) may carry a ``languages:`` list of extra
    language names the yaml metadata omits (e.g. French in Canala-English).
    """
    dictionary_dir = Path(dictionary_dir)
    source, targets = read_languages(dictionary_dir)
    seed: List[str] = [source, *targets]
    rules_path = dictionary_dir / "language_rules.yaml"
    if rules_path.is_file():
        data = yaml.safe_load(rules_path.read_text(encoding="utf-8")) or {}
        for name in data.get("languages") or []:
            if isinstance(name, str) and name.strip():
                seed.append(name.strip())
    # De-duplicate, preserving order.
    return list(dict.fromkeys(seed))


def build_prompt(raw_gold: str, seed_languages: List[str]) -> str:
    """Assemble the tag-injection instruction for one raw gold page."""
    languages = ", ".join(seed_languages)
    return (
        "You are labeling the language of every part of one OCR'd dictionary page.\n"
        "Wrap each contiguous run of text in a tag named for its language, e.g. "
        "<English>...</English>.\n\n"
        f"Languages known to appear in this dictionary: {languages}.\n"
        f"Use '{META}' for editorial markers that are not a language (entry numbers, "
        "running heads, reference markers like [NK]).\n"
        "If you clearly see a language NOT in the list above, introduce a tag named "
        "for that actual language (one word, e.g. <French>) rather than mislabeling it.\n\n"
        "ABSOLUTE RULES:\n"
        "1. Do NOT add, delete, reorder, correct, or change ANY character of the "
        "original text. Only insert <Language>...</Language> wrapper tags.\n"
        "2. Keep existing <b>...</b> and <i>...</i> typography markup exactly as it "
        "appears, as part of the wrapped text (do not treat it as a language).\n"
        "3. Preserve all whitespace and line breaks exactly.\n"
        "4. Output ONLY the tagged text, with no commentary and no code fences.\n\n"
        "PAGE TEXT:\n"
        f"{raw_gold}"
    )


def _strip_code_fence(text: str) -> str:
    """Remove a surrounding ```...``` markdown code fence if the model added one."""
    stripped = text.strip()
    if not stripped.startswith("```"):
        return text
    lines = stripped.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines)


def label_page(
    raw_gold: str,
    *,
    dictionary: str,
    page: int,
    seed_languages: List[str],
    model: str = DEFAULT_MODEL,
    reasoning_effort: str = DEFAULT_REASONING_EFFORT,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> Tuple[PageLanguageMap, List[str], float, Dict[str, Any]]:
    """Label one raw gold page via the LLM and deterministic recovery.

    Returns ``(page_map, used_languages, drift, usage)``.

    Raises:
        Tier2DriftError: if the de-tagged LLM output drifts from the gold too far.
        SpanMapError: if the recovered map fails its invariants.
    """
    prompt = build_prompt(raw_gold, seed_languages)
    text, usage = complete_with_usage(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        reasoning_effort=reasoning_effort,
        max_tokens=max_tokens,
    )
    tagged = _strip_code_fence(text)
    page_map, used, drift = recover_page_map(
        raw_gold, tagged, dictionary=dictionary, page=page
    )
    return page_map, used, drift, usage


def label_dictionary(
    dictionary_dir: str | Path,
    *,
    model: str = DEFAULT_MODEL,
    reasoning_effort: str = DEFAULT_REASONING_EFFORT,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    limit: Optional[int] = None,
) -> List[Tuple[Path, PageLanguageMap, List[str], float]]:
    """Label gold pages of a Tier-2 dictionary. Returns ``(gold_path, map, used, drift)``."""
    dictionary_dir = Path(dictionary_dir)
    dictionary = dictionary_dir.name
    seed = read_language_seed(dictionary_dir)
    pages = discover_gold_pages(dictionary_dir)
    if limit is not None:
        pages = pages[:limit]
    results: List[Tuple[Path, PageLanguageMap, List[str], float]] = []
    for gold_path in pages:
        raw_gold = gold_path.read_text(encoding="utf-8")
        page_map, used, drift, _usage = label_page(
            raw_gold,
            dictionary=dictionary,
            page=_page_number(gold_path),
            seed_languages=seed,
            model=model,
            reasoning_effort=reasoning_effort,
            max_tokens=max_tokens,
        )
        results.append((gold_path, page_map, used, drift))
    return results


def tier2_dictionaries(dictionaries_root: str | Path) -> List[str]:
    """Return dictionary folder names that are NOT Tier-1 and have language metadata."""
    root = Path(dictionaries_root)
    names: List[str] = []
    for child in sorted(root.iterdir()):
        if not child.is_dir() or child.name in TIER1_DICTIONARIES:
            continue
        if (child / "dictionary_languages.yaml").is_file():
            names.append(child.name)
    return names


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Tier-2 LLM labeler: write gold language span maps for "
        "same-script dictionaries.",
    )
    parser.add_argument(
        "--dictionaries-root",
        default="dataset/MUDIDI/dictionaries",
        help="Root holding per-dictionary folders.",
    )
    parser.add_argument(
        "--dictionary",
        action="append",
        dest="dictionaries",
        default=None,
        help="Dictionary folder name to label (repeatable). Default: all Tier-2 dicts.",
    )
    parser.add_argument("--model", default=DEFAULT_MODEL, help="litellm model string.")
    parser.add_argument(
        "--reasoning-effort",
        default=DEFAULT_REASONING_EFFORT,
        choices=("none", "low", "medium", "high"),
    )
    parser.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    parser.add_argument(
        "--limit", type=int, default=None, help="Max pages per dictionary (smoke test)."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the prompt for the first page of each dictionary; no LLM call.",
    )
    args = parser.parse_args(argv)

    root = Path(args.dictionaries_root)
    names = args.dictionaries or tier2_dictionaries(root)
    written = 0
    for name in names:
        if name in TIER1_DICTIONARIES:
            print(f"skip {name}: Tier-1 (use tier1_labeler)")
            continue
        dictionary_dir = root / name
        if not dictionary_dir.is_dir():
            print(f"skip {name}: not found under {root}")
            continue
        seed = read_language_seed(dictionary_dir)
        if args.dry_run:
            pages = discover_gold_pages(dictionary_dir)
            if not pages:
                print(f"{name}: no gold pages")
                continue
            raw = pages[0].read_text(encoding="utf-8")
            print(f"\n===== {name} (seed: {', '.join(seed)}) =====")
            print(build_prompt(raw, seed))
            continue
        print(f"\n===== {name} (seed: {', '.join(seed)}) =====")
        for gold_path, page_map, used, drift in label_dictionary(
            dictionary_dir,
            model=args.model,
            reasoning_effort=args.reasoning_effort,
            max_tokens=args.max_tokens,
            limit=args.limit,
        ):
            out_path = _lang_map_path(gold_path)
            page_map.save(out_path)
            written += 1
            extra = [lang for lang in used if lang not in seed]
            note = f"  (+discovered: {', '.join(extra)})" if extra else ""
            print(
                f"  [tier2] {name} :: page {page_map.page} "
                f"({len(page_map.spans)} spans, drift {drift:.1%}) "
                f"-> {out_path.name}{note}"
            )
    print(f"\nTier-2 labeling: {written} span map(s) written"
          f"{' (dry run)' if args.dry_run else ''}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
