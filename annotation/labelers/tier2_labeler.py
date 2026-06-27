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
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tier1_labeler import (  # noqa: E402  (flat sibling import; reuse discovery)
    OUTPUT_ROOT,
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


@dataclass
class PageResult:
    """Outcome of labeling one gold page.

    ``status`` is ``"ok"`` (``page_map`` populated, ready to write), ``"skipped"``
    (an output ``*_lang.json`` already existed and ``--skip-existing`` was set), or
    ``"failed"`` (the LLM output drifted past the gate or the map failed its
    invariants -- ``error`` carries the reason; the page is left for manual
    labeling). One failed page never aborts the batch.
    """

    gold_path: Path
    page: int
    out_path: Path
    status: str
    page_map: Optional[PageLanguageMap] = None
    used: List[str] = field(default_factory=list)
    drift: float = 0.0
    error: Optional[str] = None


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
    """Assemble the ISO-code tag-injection instruction for one raw gold page.

    The model first declares a legend of ISO 639-3 codes for every language it sees,
    then re-emits the page wrapping each run in ``<code>`` tags. Codes (short, ASCII,
    no spaces) sidestep the multi-word-name tag-parsing failures that full names like
    ``Iñupiatun Eskimo`` caused, and the legend lets recovery map codes back to names.
    """
    languages = ", ".join(seed_languages)
    return (
        "You are labeling the language of every part of one OCR'd dictionary page.\n\n"
        "STEP 1 — Identify every distinct language that appears anywhere on the page "
        "and give each its ISO 639-3 code (lowercase letters). Include languages even "
        "if they are not in the hint list below. Write them under a line that reads "
        "exactly\n"
        "LANGUAGES:\n"
        "with one entry per line in the form 'code = Language Name'.\n\n"
        "STEP 2 — Under a line that reads exactly\n"
        "TAGGED:\n"
        "re-emit the ENTIRE page text, wrapping each contiguous run in a tag named by "
        f"that language's ISO 639-3 code, e.g. <eng>...</eng>. Use <{META}>...</{META}> "
        "for editorial markers that are not a language (entry numbers, running heads, "
        "reference markers like [NK]).\n\n"
        f"Hint — languages known to appear in this dictionary: {languages}.\n\n"
        "ABSOLUTE RULES:\n"
        "1. Do NOT add, delete, reorder, correct, or change ANY character of the "
        "original text. Only insert wrapper tags.\n"
        "2. Use ONLY lowercase ISO 639-3 codes as tag names (e.g. <fra>, <rus>, "
        "<ike>); never use a language's full name as a tag.\n"
        "3. Keep existing <b>...</b> and <i>...</i> typography markup exactly as it "
        "appears, as part of the wrapped text (do not treat it as a language).\n"
        "4. Preserve all whitespace and line breaks exactly.\n"
        "5. Output ONLY the LANGUAGES: block then the TAGGED: block — no commentary "
        "and no code fences.\n\n"
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


_TAGGED_MARKER = re.compile(r"(?mi)^[ \t]*TAGGED:[ \t]*\r?\n?")
_LANGUAGES_MARKER = re.compile(r"(?mi)^[ \t]*LANGUAGES:[ \t]*\r?\n?")
_LEGEND_LINE = re.compile(r"^\s*([A-Za-z]{2,3})\s*=\s*(.+?)\s*$")


def parse_llm_output(text: str) -> Tuple[Dict[str, str], str]:
    """Split the model output into ``(code -> language legend, tagged text)``.

    The expected shape is a ``LANGUAGES:`` block of ``code = Name`` lines followed by a
    ``TAGGED:`` block holding the code-tagged page text. If the ``TAGGED:`` marker is
    absent (looser output) the whole thing is treated as the tagged text with an empty
    legend -- recovery then uses the tag names as languages directly.
    """
    stripped = _strip_code_fence(text)
    marker = _TAGGED_MARKER.search(stripped)
    if not marker:
        return {}, stripped
    legend_block = _LANGUAGES_MARKER.sub("", stripped[: marker.start()])
    tagged = stripped[marker.end():]
    code_to_language: Dict[str, str] = {}
    for line in legend_block.splitlines():
        match = _LEGEND_LINE.match(line)
        if match:
            code_to_language[match.group(1).lower()] = match.group(2).strip()
    return code_to_language, tagged


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
    code_to_language, tagged = parse_llm_output(text)
    page_map, used, drift = recover_page_map(
        raw_gold,
        tagged,
        dictionary=dictionary,
        page=page,
        code_to_language=code_to_language,
    )
    return page_map, used, drift, usage


def label_dictionary(
    dictionary_dir: str | Path,
    *,
    model: str = DEFAULT_MODEL,
    reasoning_effort: str = DEFAULT_REASONING_EFFORT,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    limit: Optional[int] = None,
    skip_existing: bool = False,
    output_root: str | Path = OUTPUT_ROOT,
) -> List[PageResult]:
    """Label gold pages of a Tier-2 dictionary, one :class:`PageResult` per page.

    A page whose LLM output drifts past the gate (:class:`Tier2DriftError`), fails
    its map invariants (``SpanMapError``), or errors mid-call is recorded as a
    ``"failed"`` result and the batch continues -- a single bad page never aborts
    the run. With ``skip_existing`` a page whose ``*_lang.json`` already exists is
    returned as ``"skipped"`` without an LLM call (cheap resume).
    """
    dictionary_dir = Path(dictionary_dir)
    dictionary = dictionary_dir.name
    seed = read_language_seed(dictionary_dir)
    pages = discover_gold_pages(dictionary_dir)
    if limit is not None:
        pages = pages[:limit]
    results: List[PageResult] = []
    for gold_path in pages:
        page = _page_number(gold_path)
        out_path = _lang_map_path(gold_path, output_root)
        if skip_existing and out_path.is_file():
            results.append(PageResult(gold_path, page, out_path, status="skipped"))
            continue
        raw_gold = gold_path.read_text(encoding="utf-8")
        try:
            page_map, used, drift, _usage = label_page(
                raw_gold,
                dictionary=dictionary,
                page=page,
                seed_languages=seed,
                model=model,
                reasoning_effort=reasoning_effort,
                max_tokens=max_tokens,
            )
        except Exception as exc:  # noqa: BLE001 -- one bad page must not abort the batch
            results.append(
                PageResult(
                    gold_path,
                    page,
                    out_path,
                    status="failed",
                    error=f"{type(exc).__name__}: {exc}",
                )
            )
            continue
        results.append(
            PageResult(
                gold_path,
                page,
                out_path,
                status="ok",
                page_map=page_map,
                used=used,
                drift=drift,
            )
        )
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
        "--output-root",
        default=str(OUTPUT_ROOT),
        help="Root for *_lang.json output, one subfolder per dictionary "
        f"(default: {OUTPUT_ROOT}).",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip pages whose *_lang.json already exists (cheap resume; no LLM call).",
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
    skipped = 0
    failures: List[Tuple[str, int, str]] = []
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
        for result in label_dictionary(
            dictionary_dir,
            model=args.model,
            reasoning_effort=args.reasoning_effort,
            max_tokens=args.max_tokens,
            limit=args.limit,
            skip_existing=args.skip_existing,
            output_root=args.output_root,
        ):
            if result.status == "skipped":
                skipped += 1
                print(f"  [skip] {name} :: page {result.page} exists "
                      f"-> {result.out_path.name}")
                continue
            if result.status == "failed":
                failures.append((name, result.page, result.error or ""))
                print(f"  [FAIL] {name} :: page {result.page}: {result.error}")
                continue
            result.out_path.parent.mkdir(parents=True, exist_ok=True)
            result.page_map.save(result.out_path)
            written += 1
            extra = [lang for lang in result.used if lang not in seed]
            note = f"  (+discovered: {', '.join(extra)})" if extra else ""
            print(
                f"  [tier2] {name} :: page {result.page_map.page} "
                f"({len(result.page_map.spans)} spans, drift {result.drift:.1%}) "
                f"-> {result.out_path.name}{note}"
            )
    summary = f"\nTier-2 labeling: {written} span map(s) written"
    if skipped:
        summary += f", {skipped} skipped (existing)"
    if failures:
        summary += f", {len(failures)} failed -> manual labeling"
    print(summary + (" (dry run)." if args.dry_run else "."))
    if failures:
        print("Pages needing manual labeling (drift/invariant gate):")
        for dict_name, page, error in failures:
            print(f"  - {dict_name} page {page}: {error}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
