"""Project gold Stage 2 MDF field values onto Stage 1 lang-script spans.

This module answers a gold-side provenance question:

    Which Stage 1 language-script span(s) did each gold MDF field *value* come from?

MDF marker codes such as ``\\lx`` and ``\\ge`` are intentionally not part of the
projection. Marker correctness is scored separately by :mod:`mdf_evaluator`.
"""

from __future__ import annotations

import argparse
import csv
import logging
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

from mudidi.evaluation.stage1.per_language_quality import collapsed_clean_text
from mudidi.evaluation.stage1.language_projection import project_clean_languages
from mudidi.evaluation.stage1.tag_parser import strip_tags
from mudidi.evaluation.stage2.mdf_parser import MdfRecord, parse_mdf
from mudidi.schemas.language_span import META, SPACE, PageLanguageMap
logger = logging.getLogger(__name__)

_WHITESPACE_RE = re.compile(r"\s+")
_TAG_RE = re.compile(r"</?[bi]>", re.IGNORECASE)
_STRUCTURAL_MARKERS = {"sn"}
_STRUCTURAL_VALUE_RE = re.compile(r"^[0-9ivxlcdmIVXLCDM.() -]+$")


@dataclass(frozen=True)
class Stage1TextProjection:
    """Stage 1 searchable text plus one lang-script label per character."""

    text: str
    languages: tuple[str, ...]


@dataclass(frozen=True)
class MdfValueProjection:
    """Projection result for one gold MDF field value."""

    dictionary: str
    page_id: str
    record_index: int
    line_index: int
    marker: str
    value: str
    normalized_value: str
    status: str
    start: int | None = None
    end: int | None = None
    primary_language: str = ""
    language_counts: dict[str, int] = field(default_factory=dict)
    source_ranges: tuple[tuple[int, int], ...] = ()

    @property
    def mapped(self) -> bool:
        return self.start is not None and self.end is not None

    @property
    def language_distribution(self) -> str:
        return ";".join(
            f"{language}:{count}" for language, count in sorted(self.language_counts.items())
        )


def _normalize_with_languages(
    text: str,
    languages: Sequence[str],
) -> Stage1TextProjection:
    """Apply Stage 2 MDF value normalization while carrying labels forward."""
    out_chars: list[str] = []
    out_langs: list[str] = []

    for char, language in zip(text, languages):
        char = char.lower().replace(",", ";")
        for normalized_char in char:
            out_chars.append(normalized_char)
            out_langs.append(language)

    joined = "".join(out_chars).strip()
    leading_trim = len("".join(out_chars)) - len("".join(out_chars).lstrip())
    if leading_trim:
        out_langs = out_langs[leading_trim:]

    compact_chars: list[str] = []
    compact_langs: list[str] = []
    last_was_space = False
    for char, language in zip(joined, out_langs):
        if char.isspace():
            if compact_chars and not last_was_space:
                compact_chars.append(" ")
                compact_langs.append(language)
            last_was_space = True
            continue
        compact_chars.append(char)
        compact_langs.append(language)
        last_was_space = False

    if compact_chars and compact_chars[-1] == " ":
        compact_chars.pop()
        compact_langs.pop()

    return Stage1TextProjection("".join(compact_chars), tuple(compact_langs))


def normalize_mdf_value_for_projection(value: str) -> str:
    """Normalize an MDF field value exactly for Stage1-to-MDF lookup."""
    text = unicodedata.normalize("NFC", value.strip())
    text = text.strip().lower().replace(",", ";")
    text = _TAG_RE.sub("", text)
    text = _WHITESPACE_RE.sub(" ", text)
    return text.strip()


def build_stage1_projection(
    stage1_gold_path: str | Path,
    lang_map_path: str | Path,
) -> Stage1TextProjection:
    """Build searchable Stage 1 text with one language label per character."""
    stage1_gold_path = Path(stage1_gold_path)
    raw_gold = stage1_gold_path.read_text(encoding="utf-8")
    lang_map = PageLanguageMap.load(lang_map_path)
    raw_char_lang = lang_map.language_char_map(raw_gold)
    clean_gold = collapsed_clean_text(stage1_gold_path)
    clean_lang = project_clean_languages(raw_gold, raw_char_lang, clean_gold)
    return _normalize_with_languages(clean_gold, clean_lang)


def _is_scoring_noise(char: str) -> bool:
    return char.isspace() or unicodedata.category(char).startswith("P")


def _compact_text_with_index(text: str) -> tuple[str, list[int]]:
    chars: list[str] = []
    indexes: list[int] = []
    for index, char in enumerate(text):
        if _is_scoring_noise(char):
            continue
        chars.append(char)
        indexes.append(index)
    return "".join(chars), indexes


def _language_counts(
    projection: Stage1TextProjection,
    start: int,
    end: int,
) -> dict[str, int]:
    return _language_counts_for_ranges(projection, ((start, end),))


def _language_counts_for_ranges(
    projection: Stage1TextProjection,
    ranges: Sequence[tuple[int, int]],
) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for start, end in ranges:
        for char, language in zip(projection.text[start:end], projection.languages[start:end]):
            if language in {SPACE, META} or _is_scoring_noise(char):
                continue
            counts[language] += 1
    return dict(counts)


def _primary_language(counts: dict[str, int]) -> str:
    if not counts:
        return META
    top = max(counts.values())
    return sorted(language for language, count in counts.items() if count == top)[0]


def _find_exact(text: str, needle: str, cursor: int) -> tuple[int, int] | None:
    start = text.find(needle, cursor)
    if start == -1:
        start = text.find(needle)
    if start == -1:
        return None
    return start, start + len(needle)


def _find_compact(text: str, needle: str, cursor: int) -> tuple[int, int] | None:
    compact_text, index_map = _compact_text_with_index(text)
    compact_needle, _ = _compact_text_with_index(needle)
    if not compact_needle:
        return None
    compact_cursor = 0
    while compact_cursor < len(index_map) and index_map[compact_cursor] < cursor:
        compact_cursor += 1
    start = compact_text.find(compact_needle, compact_cursor)
    if start == -1:
        start = compact_text.find(compact_needle)
    if start == -1:
        return None
    end = start + len(compact_needle) - 1
    return index_map[start], index_map[end] + 1


def _is_token_char(char: str) -> bool:
    return unicodedata.category(char)[0] in {"L", "N", "M"}


def _token_spans(text: str) -> list[tuple[str, int, int]]:
    spans: list[tuple[str, int, int]] = []
    index = 0
    while index < len(text):
        while index < len(text) and not _is_token_char(text[index]):
            index += 1
        start = index
        while index < len(text) and _is_token_char(text[index]):
            index += 1
        if start < index:
            spans.append((text[start:index], start, index))
    return spans


def _find_ordered_token_ranges(
    text: str,
    needle: str,
    cursor: int,
) -> tuple[tuple[tuple[int, int], ...], bool]:
    """Find needle tokens in order; returns ranges and whether all tokens matched."""
    tokens = [
        token
        for token in _token_spans(needle)
        if len(token[0]) > 1 or any(char.isalpha() for char in token[0])
    ]
    if not tokens:
        return (), False

    ranges: list[tuple[int, int]] = []
    search_from = cursor
    all_found = True
    for token, _token_start, _token_end in tokens:
        start = text.find(token, search_from)
        if start == -1:
            start = text.find(token)
        if start == -1:
            all_found = False
            continue
        end = start + len(token)
        ranges.append((start, end))
        search_from = end
    return tuple(ranges), all_found and len(ranges) == len(tokens)


def _is_structural_value(marker: str, normalized_value: str) -> bool:
    return marker in _STRUCTURAL_MARKERS and bool(
        _STRUCTURAL_VALUE_RE.fullmatch(normalized_value)
    )


def project_mdf_value(
    *,
    dictionary: str,
    page_id: str,
    record_index: int,
    line_index: int,
    marker: str,
    value: str,
    projection: Stage1TextProjection,
    cursor: int,
) -> tuple[MdfValueProjection, int]:
    """Project one MDF field value onto Stage 1 text.

    Returns the projection and the next monotonic cursor. The marker is retained
    only as metadata; matching uses ``value``.
    """
    normalized_value = normalize_mdf_value_for_projection(value)
    if not normalized_value:
        return (
            MdfValueProjection(
                dictionary=dictionary,
                page_id=page_id,
                record_index=record_index,
                line_index=line_index,
                marker=marker,
                value=value,
                normalized_value=normalized_value,
                status="empty",
            ),
            cursor,
        )
    if _is_structural_value(marker, normalized_value):
        return (
            MdfValueProjection(
                dictionary=dictionary,
                page_id=page_id,
                record_index=record_index,
                line_index=line_index,
                marker=marker,
                value=value,
                normalized_value=normalized_value,
                status="structural",
                primary_language=META,
            ),
            cursor,
        )

    match = _find_exact(projection.text, normalized_value, cursor)
    status = "exact"
    if match is None:
        match = _find_compact(projection.text, normalized_value, cursor)
        status = "compact"
    if match is None:
        ranges, all_tokens = _find_ordered_token_ranges(
            projection.text, normalized_value, cursor
        )
        if ranges:
            counts = _language_counts_for_ranges(projection, ranges)
            return (
                MdfValueProjection(
                    dictionary=dictionary,
                    page_id=page_id,
                    record_index=record_index,
                    line_index=line_index,
                    marker=marker,
                    value=value,
                    normalized_value=normalized_value,
                    status="token" if all_tokens else "partial",
                    start=min(start for start, _end in ranges),
                    end=max(end for _start, end in ranges),
                    primary_language=_primary_language(counts),
                    language_counts=counts,
                    source_ranges=ranges,
                ),
                max(cursor, max(end for _start, end in ranges)),
            )
        return (
            MdfValueProjection(
                dictionary=dictionary,
                page_id=page_id,
                record_index=record_index,
                line_index=line_index,
                marker=marker,
                value=value,
                normalized_value=normalized_value,
                status="unmapped",
            ),
            cursor,
        )

    start, end = match
    counts = _language_counts(projection, start, end)
    result = MdfValueProjection(
        dictionary=dictionary,
        page_id=page_id,
        record_index=record_index,
        line_index=line_index,
        marker=marker,
        value=value,
        normalized_value=normalized_value,
        status=status,
        start=start,
        end=end,
        primary_language=_primary_language(counts),
        language_counts=counts,
        source_ranges=((start, end),),
    )
    return result, max(cursor, end)


def project_mdf_records(
    *,
    dictionary: str,
    page_id: str,
    records: Sequence[MdfRecord],
    projection: Stage1TextProjection,
) -> list[MdfValueProjection]:
    """Project all gold MDF field values for one page in record/line order."""
    cursor = 0
    results: list[MdfValueProjection] = []
    for record in records:
        for line in record.lines:
            projected, cursor = project_mdf_value(
                dictionary=dictionary,
                page_id=page_id,
                record_index=record.index,
                line_index=line.line_index,
                marker=line.marker,
                value=line.value,
                projection=projection,
                cursor=cursor,
            )
            results.append(projected)
    return results


def project_mdf_file_to_stage1(
    *,
    dictionary: str,
    mdf_path: str | Path,
    stage1_gold_path: str | Path,
    lang_map_path: str | Path,
) -> list[MdfValueProjection]:
    """Project every gold MDF value in *mdf_path* to Stage 1 language spans."""
    mdf_path = Path(mdf_path)
    projection = build_stage1_projection(stage1_gold_path, lang_map_path)
    records = parse_mdf(mdf_path.read_text(encoding="utf-8"))
    return project_mdf_records(
        dictionary=dictionary,
        page_id=mdf_path.parent.name,
        records=records,
        projection=projection,
    )


def _stage1_paths_for_mdf(dataset_dir: Path, dictionary: str, page_id: str) -> tuple[Path, Path]:
    stage1_dir = dataset_dir / dictionary / "Stage 1 Gold OCR" / page_id
    return (
        stage1_dir / f"{page_id}_stage1_GOLD_flat.txt",
        stage1_dir / f"{page_id}_lang.json",
    )


def iter_dataset_gold_mdf(dataset_dir: str | Path) -> Iterable[tuple[str, Path]]:
    """Yield ``(dictionary, gold_mdf_path)`` for dataset Stage 2 gold files."""
    dataset_dir = Path(dataset_dir)
    for dictionary_dir in sorted(p for p in dataset_dir.iterdir() if p.is_dir()):
        stage2_root = dictionary_dir / "Stage 2 MDF file"
        if not stage2_root.is_dir():
            continue
        for mdf_path in sorted(stage2_root.glob("*/*.mdf.txt")):
            yield dictionary_dir.name, mdf_path


def audit_dataset(
    dataset_dir: str | Path,
    *,
    dictionaries: set[str] | None = None,
) -> list[MdfValueProjection]:
    """Project every available Stage 2 gold MDF line under a dataset root."""
    dataset_dir = Path(dataset_dir)
    all_results: list[MdfValueProjection] = []
    for dictionary, mdf_path in iter_dataset_gold_mdf(dataset_dir):
        if dictionaries is not None and dictionary not in dictionaries:
            continue
        stage1_gold_path, lang_map_path = _stage1_paths_for_mdf(
            dataset_dir, dictionary, mdf_path.parent.name
        )
        if not stage1_gold_path.is_file() or not lang_map_path.is_file():
            logger.warning(
                "Skipping %s %s: missing Stage 1 gold or lang map",
                dictionary,
                mdf_path.parent.name,
            )
            continue
        all_results.extend(
            project_mdf_file_to_stage1(
                dictionary=dictionary,
                mdf_path=mdf_path,
                stage1_gold_path=stage1_gold_path,
                lang_map_path=lang_map_path,
            )
        )
    return all_results


def summarize(results: Sequence[MdfValueProjection]) -> Counter[str]:
    """Count projection statuses."""
    return Counter(result.status for result in results)


def write_csv(results: Sequence[MdfValueProjection], path: str | Path) -> None:
    """Write detailed projection rows."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "dictionary",
        "page_id",
        "record_index",
        "line_index",
        "marker",
        "status",
        "start",
        "end",
        "primary_language",
        "language_distribution",
        "source_ranges",
        "normalized_value",
        "value",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for result in results:
            writer.writerow(
                {
                    "dictionary": result.dictionary,
                    "page_id": result.page_id,
                    "record_index": result.record_index,
                    "line_index": result.line_index,
                    "marker": result.marker,
                    "status": result.status,
                    "start": "" if result.start is None else result.start,
                    "end": "" if result.end is None else result.end,
                    "primary_language": result.primary_language,
                    "language_distribution": result.language_distribution,
                    "source_ranges": ";".join(
                        f"{start}:{end}" for start, end in result.source_ranges
                    ),
                    "normalized_value": result.normalized_value,
                    "value": strip_tags(result.value),
                }
            )


def _print_summary(results: Sequence[MdfValueProjection]) -> None:
    counts = summarize(results)
    total = sum(counts.values())
    print(f"Projected MDF field values: {total}")
    for status, count in sorted(counts.items()):
        print(f"  {status}: {count}")
    unmapped = [result for result in results if result.status == "unmapped"]
    if unmapped:
        print("\nUnmapped examples:")
        for result in unmapped[:20]:
            print(
                f"  {result.dictionary} {result.page_id} "
                f"line {result.line_index} \\{result.marker}: {result.value}"
            )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Project gold Stage 2 MDF field values onto Stage 1 lang-script spans."
        )
    )
    parser.add_argument(
        "--dataset-dir",
        type=Path,
        default=Path("dataset/MUDIDI/dictionaries"),
        help="MUDIDI dataset dictionaries root.",
    )
    parser.add_argument(
        "--dictionary",
        action="append",
        dest="dictionaries",
        default=None,
        help="Only audit this dictionary folder name (repeatable).",
    )
    parser.add_argument(
        "--output-csv",
        type=Path,
        default=None,
        help="Optional detailed CSV path.",
    )
    parser.add_argument(
        "--fail-on-unmapped",
        action="store_true",
        help="Exit non-zero if any MDF value cannot be projected.",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )
    results = audit_dataset(
        args.dataset_dir,
        dictionaries=set(args.dictionaries) if args.dictionaries else None,
    )
    _print_summary(results)
    if args.output_csv is not None:
        write_csv(results, args.output_csv)
        print(f"\nDetailed CSV: {args.output_csv}")
    if args.fail_on_unmapped and any(result.status == "unmapped" for result in results):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
