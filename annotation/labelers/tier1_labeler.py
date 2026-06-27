"""Tier-1 script-check labeler: auto-produce gold language span maps.

For the dictionaries whose source script is *distinct* from their single target
script (Bengali/Greek/Gujarati/Khmer/Devanagari/Telugu/Georgian/Syriac/Hebrew
sources against English or Russian), :func:`classify_token` partitions every token
by script alone -- no LID, no LLM. This module walks a page's **raw** gold text,
classifies each token, and emits a validated :class:`PageLanguageMap` (the gold span
artifact the package eval consumes and the Label Studio NER bridge imports).

The map is bound to the immutable raw gold via SHA-256 (D-3 coordinate system), so
``<b>``/``</b>`` markup and punctuation are part of the labelled stream: a markup-
wrapped source headword (e.g. ``<b>᾿Αδραστος</b>``) still classifies as the source
language because its letters are the source script and the incidental Latin ``b`` of
the tag is a minority. Punctuation/digit-only tokens carry forward the previous
token's language (source at page start).

Every page is a *draft* for human review in Label Studio (PRD D-5); Tier-1 drafts
should need near-zero edits.

No third-party dependencies beyond ``pyyaml`` (already a project dependency) and the
sibling ``script_check`` / package ``mudidi.schemas`` modules.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from script_check import (  # noqa: E402  (flat sibling import)
    ScriptConfig,
    TokenCategory,
    classify_token,
)

from mudidi.schemas.language_span import (  # noqa: E402
    SPACE,
    LanguageSpan,
    PageLanguageMap,
    sha256_of,
)

RULE_SET = "script-check-v1"

# Target language -> the Unicode script bucket (per ``script_check._base_script``)
# its text occupies. Tier-1 targets are high-resource and single-script.
TARGET_SCRIPT: Dict[str, str] = {
    "English": "latin",
    "Russian": "cyrillic",
}

# The cleanly-separable dictionaries (``annotation/ mapping.md`` "Deterministic" rows):
# source script is distinct from the single target script, so script-check alone
# partitions them. A dictionary outside this set belongs to Tier-2 (M5).
TIER1_DICTIONARIES = frozenset(
    {
        "Bengalese-English",
        "Greek-English",
        "Gujarati-English",
        "Khmer-English",
        "Sanskrit-English",
        "Telugu-English",
        "Georgian-Russian",
        "Syriac-English",
        "Yiddish-English",
    }
)


class Tier1Error(ValueError):
    """Raised when a dictionary is not a valid Tier-1 (script-distinct) target."""


def read_languages(dictionary_dir: str | Path) -> Tuple[str, List[str]]:
    """Return ``(source_language, target_languages)`` from ``dictionary_languages.yaml``."""
    path = Path(dictionary_dir) / "dictionary_languages.yaml"
    if not path.is_file():
        raise Tier1Error(f"missing dictionary_languages.yaml under {dictionary_dir}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    source = data.get("source") or {}
    source_language = str(source.get("language") or "").strip()
    targets = [
        str(t["language"]).strip()
        for t in (data.get("targets") or [])
        if isinstance(t, dict) and t.get("language")
    ]
    if not source_language or not targets:
        raise Tier1Error(f"incomplete language metadata in {path}")
    return source_language, targets


def build_script_config(target_languages: List[str]) -> ScriptConfig:
    """Build the :class:`ScriptConfig` for a Tier-1 dictionary from its targets."""
    target_scripts = set()
    for language in target_languages:
        script = TARGET_SCRIPT.get(language)
        if script is None:
            raise Tier1Error(
                f"target language {language!r} has no known Tier-1 script; "
                "this dictionary is not script-separable (route to Tier-2)"
            )
        target_scripts.add(script)
    return ScriptConfig(target_scripts=target_scripts)


def _token_language(
    token: str,
    cfg: ScriptConfig,
    *,
    source_language: str,
    target_language: str,
    carry: str,
) -> str:
    """Map a token's script-check category to a concrete language label.

    ``carry`` is the previous token's language, used for punctuation/digit-only
    tokens (which have no script of their own).
    """
    label = classify_token(token, cfg)
    if label.category == TokenCategory.SOURCE:
        return source_language
    if label.category == TokenCategory.DISTINCT_TARGET:
        return label.detail  # the distinct target's language name
    if label.category == TokenCategory.RESIDUAL:
        return target_language  # residual script == the single target script
    return carry  # PUNCT: inherit the surrounding language


def _char_languages(
    raw_text: str,
    cfg: ScriptConfig,
    *,
    source_language: str,
    target_language: str,
) -> List[str]:
    """Return a per-codepoint language label array of length ``len(raw_text)``."""
    labels = [SPACE] * len(raw_text)
    carry = source_language
    index = 0
    length = len(raw_text)
    while index < length:
        if raw_text[index].isspace():
            stop = index
            while stop < length and raw_text[stop].isspace():
                stop += 1
            index = stop  # whitespace stays SPACE
            continue
        stop = index
        while stop < length and not raw_text[stop].isspace():
            stop += 1
        token = raw_text[index:stop]
        language = _token_language(
            token,
            cfg,
            source_language=source_language,
            target_language=target_language,
            carry=carry,
        )
        for k in range(index, stop):
            labels[k] = language
        carry = language
        index = stop
    return labels


def _spans_from_char_languages(labels: List[str]) -> List[LanguageSpan]:
    """Group consecutive equal labels into contiguous spans."""
    spans: List[LanguageSpan] = []
    start = 0
    for index in range(1, len(labels) + 1):
        if index == len(labels) or labels[index] != labels[start]:
            spans.append(
                LanguageSpan(start=start, end=index, language=labels[start])
            )
            start = index
    return spans


def label_page(
    raw_text: str,
    *,
    dictionary: str,
    page: int,
    source_language: str,
    target_languages: List[str],
) -> PageLanguageMap:
    """Produce a validated :class:`PageLanguageMap` for one raw gold page.

    Raises:
        Tier1Error: if ``dictionary`` is not a registered Tier-1 dictionary.
        SpanMapError: if the produced map fails its gold-binding/coverage invariants.
    """
    if dictionary not in TIER1_DICTIONARIES:
        raise Tier1Error(
            f"{dictionary!r} is not a Tier-1 (script-distinct) dictionary; "
            "route it to the Tier-2 LLM labeler (M5)"
        )
    cfg = build_script_config(target_languages)
    target_language = target_languages[0]
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
    labels = _char_languages(
        raw_text,
        cfg,
        source_language=source_language,
        target_language=target_language,
    )
    page_map = PageLanguageMap(
        dictionary=dictionary,
        page=page,
        source_text_sha=sha256_of(raw_text),
        rule_set=RULE_SET,
        labeled_via="heuristic",
        spans=_spans_from_char_languages(labels),
    ).canonical()
    page_map.validate_against(raw_text)
    return page_map


# -- batch / discovery -------------------------------------------------------------

_GOLD_GLOB = "Stage 1 Gold OCR/*/*_stage1_GOLD_flat.txt"


def _page_number(gold_path: Path) -> int:
    """Extract the integer page number from ``page_<N>_stage1_GOLD_flat.txt``."""
    name = gold_path.name
    stem = name.split("_stage1_GOLD_flat.txt")[0]  # ``page_38``
    digits = "".join(ch for ch in stem if ch.isdigit())
    return int(digits) if digits else 0


def discover_gold_pages(dictionary_dir: str | Path) -> List[Path]:
    """Return sorted gold flat-text page files for a dictionary."""
    return sorted(Path(dictionary_dir).glob(_GOLD_GLOB), key=_page_number)


def label_dictionary(dictionary_dir: str | Path) -> List[Tuple[Path, PageLanguageMap]]:
    """Label every gold page of a Tier-1 dictionary.

    Returns a list of ``(gold_path, page_map)``. Writing is left to the caller / CLI.
    """
    dictionary_dir = Path(dictionary_dir)
    dictionary = dictionary_dir.name
    source_language, target_languages = read_languages(dictionary_dir)
    results: List[Tuple[Path, PageLanguageMap]] = []
    for gold_path in discover_gold_pages(dictionary_dir):
        raw_text = gold_path.read_text(encoding="utf-8")
        page_map = label_page(
            raw_text,
            dictionary=dictionary,
            page=_page_number(gold_path),
            source_language=source_language,
            target_languages=target_languages,
        )
        results.append((gold_path, page_map))
    return results


# Span maps are written under this root, one subfolder per dictionary (matching the
# dictionary folder name in ``dataset/MUDIDI/dictionaries``), e.g.
# ``annotation/outputs/Canala-English/page_12_lang.json``. Kept out of the dataset so
# the read-only Hugging Face checkout stays clean.
OUTPUT_ROOT = Path("annotation/outputs")


def _dictionary_name(gold_path: Path) -> str:
    """Derive the dictionary folder name from a gold page path.

    Gold pages live at ``<root>/<DictName>/Stage 1 Gold OCR/<sub>/page_N_...txt``,
    so the dictionary name is the folder just above ``Stage 1 Gold OCR``.
    """
    for parent in gold_path.parents:
        if parent.parent is not None and parent.name == "Stage 1 Gold OCR":
            return parent.parent.name
    return gold_path.parent.name  # fallback (flat layout)


def _lang_map_path(gold_path: Path, output_root: str | Path = OUTPUT_ROOT) -> Path:
    """Output ``*_lang.json`` path under ``<output_root>/<dictionary>/``."""
    stem = gold_path.name.split("_stage1_GOLD_flat.txt")[0]
    return Path(output_root) / _dictionary_name(gold_path) / f"{stem}_lang.json"


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Tier-1 script-check labeler: write gold language span maps.",
    )
    parser.add_argument(
        "--dictionaries-root",
        default="dataset/MUDIDI/dictionaries",
        help="Root holding per-dictionary folders (default: dataset/MUDIDI/dictionaries).",
    )
    parser.add_argument(
        "--dictionary",
        action="append",
        dest="dictionaries",
        default=None,
        help="Dictionary folder name to label (repeatable). Default: all Tier-1 dicts.",
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
    args = parser.parse_args(argv)

    root = Path(args.dictionaries_root)
    names = args.dictionaries or sorted(TIER1_DICTIONARIES)
    written = 0
    for name in names:
        if name not in TIER1_DICTIONARIES:
            print(f"skip {name}: not a Tier-1 dictionary")
            continue
        dictionary_dir = root / name
        if not dictionary_dir.is_dir():
            print(f"skip {name}: not found under {root}")
            continue
        pairs = label_dictionary(dictionary_dir)
        for gold_path, page_map in pairs:
            out_path = _lang_map_path(gold_path, args.output_root)
            if not args.dry_run:
                out_path.parent.mkdir(parents=True, exist_ok=True)
                page_map.save(out_path)
                written += 1
            print(
                f"  [tier1] {name} :: page {page_map.page} "
                f"({len(page_map.spans)} spans) -> {out_path.name}"
            )
    print(f"\nTier-1 labeling: {written} span map(s) written"
          f"{' (dry run)' if args.dry_run else ''}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
