"""Script labeler: deterministic Unicode script span maps for all dictionaries.

Assigns each codepoint a **script** label (Latin, Greek, Cyrillic, IPA, Han, …)
via :func:`script_check.assign_char_script_labels` and writes ``*_lang.json``
artifacts for Label Studio review. Labels live in ``LanguageSpan.language`` (the
schema field name is historical).

No language identification — only writing-system segmentation. The legacy LLM
language tagger (:mod:`tier2_labeler`) remains available via ``run_labeler.sh``
when ``LABELER_MODE=llm``.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from labeler_common import (  # noqa: E402
    OUTPUT_ROOT,
    _lang_map_path,
    _page_number,
    discover_gold_pages,
    list_dictionaries,
    spans_from_labels,
)
from script_check import assign_char_script_labels  # noqa: E402

from mudidi.schemas.language_span import (  # noqa: E402
    SPACE,
    PageLanguageMap,
    sha256_of,
)

RULE_SET = "script-id-v1"


def label_page(
    raw_text: str,
    *,
    dictionary: str,
    page: int,
) -> PageLanguageMap:
    """Produce a validated script span map for one raw gold page."""
    if not raw_text:
        page_map = PageLanguageMap(
            dictionary=dictionary,
            page=page,
            source_text_sha=sha256_of(raw_text),
            rule_set=RULE_SET,
            labeled_via="heuristic",
            spans=[],
        )
        page_map.validate_against(raw_text)
        return page_map
    labels = assign_char_script_labels(raw_text, space_label=SPACE)
    page_map = PageLanguageMap(
        dictionary=dictionary,
        page=page,
        source_text_sha=sha256_of(raw_text),
        rule_set=RULE_SET,
        labeled_via="heuristic",
        spans=spans_from_labels(labels),
    ).canonical()
    page_map.validate_against(raw_text)
    return page_map


def label_dictionary(dictionary_dir: str | Path) -> List[Tuple[Path, PageLanguageMap]]:
    """Label every gold page of a dictionary."""
    dictionary_dir = Path(dictionary_dir)
    dictionary = dictionary_dir.name
    results: List[Tuple[Path, PageLanguageMap]] = []
    for gold_path in discover_gold_pages(dictionary_dir):
        raw_text = gold_path.read_text(encoding="utf-8")
        page_map = label_page(
            raw_text,
            dictionary=dictionary,
            page=_page_number(gold_path),
        )
        results.append((gold_path, page_map))
    return results


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Script labeler: write gold script span maps "
        "(deterministic Unicode classification).",
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
        help="Dictionary folder name to label (repeatable). Default: all with gold pages.",
    )
    parser.add_argument(
        "--output-root",
        default=str(OUTPUT_ROOT),
        help="Root for *_lang.json output, one subfolder per dictionary "
        f"(default: {OUTPUT_ROOT}).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Classify and validate but do not write *_lang.json files.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Re-label pages even if a *_lang.json already exists.",
    )
    args = parser.parse_args(argv)

    root = Path(args.dictionaries_root)
    names = args.dictionaries or list_dictionaries(root)
    written = 0
    skipped = 0
    for name in names:
        dictionary_dir = root / name
        if not dictionary_dir.is_dir():
            print(f"skip {name}: not found under {root}")
            continue
        pages = discover_gold_pages(dictionary_dir)
        if not pages:
            print(f"skip {name}: no gold pages")
            continue
        for gold_path, page_map in label_dictionary(dictionary_dir):
            out_path = _lang_map_path(gold_path, args.output_root)
            if out_path.is_file() and not args.overwrite:
                skipped += 1
                print(
                    f"  [skip] {name} :: page {page_map.page} exists "
                    f"-> {out_path.name}"
                )
                continue
            scripts = sorted({span.language for span in page_map.spans})
            if not args.dry_run:
                out_path.parent.mkdir(parents=True, exist_ok=True)
                page_map.save(out_path)
                written += 1
            print(
                f"  [script] {name} :: page {page_map.page} "
                f"({len(page_map.spans)} spans, scripts: {', '.join(scripts)}) "
                f"-> {out_path.name}"
            )
    summary = f"\nScript labeling: {written} span map(s) written"
    if skipped:
        summary += f", {skipped} skipped (existing)"
    print(summary + (" (dry run)." if args.dry_run else "."))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
