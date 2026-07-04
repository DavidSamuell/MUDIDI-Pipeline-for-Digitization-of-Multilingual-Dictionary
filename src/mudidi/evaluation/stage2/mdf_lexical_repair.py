"""Conservative lexical repair for Stage 2 MDF values using Stage 1 OCR text.

Stage 2 is allowed to restructure Stage 1 OCR into MDF, but it should not silently
``correct`` lexical characters. This module repairs only Unicode lexical runs
(letters, numbers, combining marks) inside MDF field values, preserving the Stage 2
marker choice, line boundaries, whitespace, and punctuation.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import re
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from mudidi.evaluation.stage1.flatten import flatten_stage1_tsv
from mudidi.evaluation.stage1.per_language_quality import collapsed_clean_text
from mudidi.evaluation.stage1.tag_parser import strip_tags
from mudidi.evaluation.stage2.mdf_stage1_projection import (
    _find_compact,
    _find_exact,
    normalize_mdf_value_for_projection,
)

logger = logging.getLogger(__name__)

MDF_LINE_RE = re.compile(r"^(?P<prefix>\\(?P<marker>[a-zA-Z0-9_-]+)\s+)(?P<value>.*)$")
LEXICAL_CATEGORIES = {"L", "N", "M"}
REPAIR_VERSION = "stage2-lexical-repair-v1"


@dataclass(frozen=True)
class RepairConfig:
    """Thresholds for conservative Stage 2 lexical repair."""

    min_value_lexical_chars: int = 8
    min_anchor_coverage: float = 0.8
    max_span_to_value_ratio: float = 1.5
    allow_approximate: bool = True


@dataclass(frozen=True)
class LexicalRun:
    """One contiguous lexical run in a string."""

    text: str
    start: int
    end: int


@dataclass(frozen=True)
class RepairDecision:
    """Audit row for one MDF line considered by the repair pass."""

    line_number: int
    marker: str
    status: str
    match_status: str
    changed: bool
    original_value: str
    repaired_value: str
    source_value: str
    source_start: int | None = None
    source_end: int | None = None
    anchor_coverage: float = 0.0
    reason: str = ""


@dataclass(frozen=True)
class RepairResult:
    """Result of repairing one MDF page."""

    text: str
    decisions: list[RepairDecision]

    @property
    def changed_lines(self) -> int:
        return sum(1 for decision in self.decisions if decision.changed)


def is_lexical_char(char: str) -> bool:
    """Return true for letters, numbers, and combining marks."""
    return unicodedata.category(char)[0] in LEXICAL_CATEGORIES


def lexical_runs(text: str) -> list[LexicalRun]:
    """Return lexical runs in *text*."""
    runs: list[LexicalRun] = []
    index = 0
    while index < len(text):
        while index < len(text) and not is_lexical_char(text[index]):
            index += 1
        start = index
        while index < len(text) and is_lexical_char(text[index]):
            index += 1
        if start < index:
            runs.append(LexicalRun(text=text[start:index], start=start, end=index))
    return runs


def lexical_length(text: str) -> int:
    """Count lexical characters in *text*."""
    return sum(1 for char in text if is_lexical_char(char))


def normalize_stage1_text_for_repair(stage1_path: str | Path) -> str:
    """Return clean Stage 1 text suitable for matching MDF values."""
    stage1_path = Path(stage1_path)
    if stage1_path.name.endswith(".tsv"):
        text = flatten_stage1_tsv(stage1_path)
        return _normalize_source_text(text)
    return collapsed_clean_text(stage1_path)


def _normalize_source_text(text: str) -> str:
    normalized = unicodedata.normalize("NFC", strip_tags(text))
    normalized = normalized.strip().lower().replace(",", ";")
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def _normalize_source_display_text(text: str) -> str:
    normalized = unicodedata.normalize("NFC", strip_tags(text))
    normalized = re.sub(r"\s+", " ", normalized.strip())
    return normalized


def _token_ranges(text: str) -> list[tuple[str, int, int]]:
    return [(run.text, run.start, run.end) for run in lexical_runs(text)]


def _expand_to_lexical_boundaries(text: str, start: int, end: int) -> tuple[int, int]:
    while start > 0 and is_lexical_char(text[start - 1]):
        start -= 1
    while end < len(text) and is_lexical_char(text[end]):
        end += 1
    return start, end


def _find_approximate_token_span(
    source_text: str,
    normalized_value: str,
    cursor: int,
    config: RepairConfig,
) -> tuple[int, int, float] | None:
    value_tokens = [
        token
        for token in _token_ranges(normalized_value)
        if len(token[0]) > 1 or any(char.isalpha() for char in token[0])
    ]
    if not value_tokens:
        return None

    ranges: list[tuple[int, int, int, int]] = []
    covered = 0
    search_from = cursor
    for token, _value_start, _value_end in value_tokens:
        start = source_text.find(token, search_from)
        if start == -1:
            start = source_text.find(token)
        if start == -1:
            continue
        end = start + len(token)
        ranges.append((start, end, _value_start, _value_end))
        covered += lexical_length(token)
        search_from = end

    value_lexical = lexical_length(normalized_value)
    if not ranges or not value_lexical:
        return None
    coverage = covered / value_lexical
    if coverage < config.min_anchor_coverage:
        return None

    start = min(
        max(0, source_start - value_start)
        for source_start, _end, value_start, _value_end in ranges
    )
    end = max(
        min(len(source_text), source_end + len(normalized_value) - value_end)
        for _source_start, source_end, _value_start, value_end in ranges
    )
    if end <= start:
        return None
    if (end - start) / max(len(normalized_value), 1) > config.max_span_to_value_ratio:
        return None
    start, end = _expand_to_lexical_boundaries(source_text, start, end)
    return start, end, coverage


def _replace_lexical_runs(template: str, source_value: str) -> str | None:
    template_runs = lexical_runs(template)
    source_runs = lexical_runs(source_value)
    if not template_runs or len(template_runs) != len(source_runs):
        return None

    pieces: list[str] = []
    cursor = 0
    for template_run, source_run in zip(template_runs, source_runs):
        pieces.append(template[cursor : template_run.start])
        pieces.append(source_run.text)
        cursor = template_run.end
    pieces.append(template[cursor:])
    return "".join(pieces)


def _find_source_span(
    source_text: str,
    normalized_value: str,
    cursor: int,
    config: RepairConfig,
) -> tuple[int, int, str, float] | None:
    exact = _find_exact(source_text, normalized_value, cursor)
    if exact is not None:
        return exact[0], exact[1], "exact", 1.0

    compact = _find_compact(source_text, normalized_value, cursor)
    if compact is not None:
        return compact[0], compact[1], "compact", 1.0

    if not config.allow_approximate:
        return None

    approximate = _find_approximate_token_span(
        source_text,
        normalized_value,
        cursor,
        config,
    )
    if approximate is None:
        return None
    start, end, coverage = approximate
    return start, end, "approximate-token", coverage


def repair_mdf_text(
    mdf_text: str,
    stage1_text: str,
    *,
    config: RepairConfig | None = None,
) -> RepairResult:
    """Repair MDF lexical characters from Stage 1 OCR text."""
    config = config or RepairConfig()
    source_text = _normalize_source_text(stage1_text)
    source_display_text = _normalize_source_display_text(stage1_text)
    cursor = 0
    output_lines: list[str] = []
    decisions: list[RepairDecision] = []

    for line_number, line in enumerate(mdf_text.splitlines(), start=1):
        match = MDF_LINE_RE.match(line)
        if match is None:
            output_lines.append(line)
            continue

        marker = match.group("marker")
        prefix = match.group("prefix")
        value = match.group("value")
        normalized_value = normalize_mdf_value_for_projection(value)
        value_lexical = lexical_length(normalized_value)
        if value_lexical < config.min_value_lexical_chars:
            output_lines.append(line)
            decisions.append(
                RepairDecision(
                    line_number=line_number,
                    marker=marker,
                    status="skipped",
                    match_status="none",
                    changed=False,
                    original_value=value,
                    repaired_value=value,
                    source_value="",
                    reason="too_few_lexical_chars",
                )
            )
            continue

        span = _find_source_span(source_text, normalized_value, cursor, config)
        if span is None:
            output_lines.append(line)
            decisions.append(
                RepairDecision(
                    line_number=line_number,
                    marker=marker,
                    status="skipped",
                    match_status="none",
                    changed=False,
                    original_value=value,
                    repaired_value=value,
                    source_value="",
                    reason="no_safe_source_span",
                )
            )
            continue

        start, end, match_status, coverage = span
        source_value = source_display_text[start:end]
        if match_status in {"exact", "compact"}:
            output_lines.append(line)
            decisions.append(
                RepairDecision(
                    line_number=line_number,
                    marker=marker,
                    status="unchanged",
                    match_status=match_status,
                    changed=False,
                    original_value=value,
                    repaired_value=value,
                    source_value=source_value,
                    source_start=start,
                    source_end=end,
                    anchor_coverage=coverage,
                    reason="already_safely_anchored",
                )
            )
            cursor = max(cursor, end)
            continue

        repaired_value = _replace_lexical_runs(value, source_value)
        if repaired_value is None:
            output_lines.append(line)
            decisions.append(
                RepairDecision(
                    line_number=line_number,
                    marker=marker,
                    status="skipped",
                    match_status=match_status,
                    changed=False,
                    original_value=value,
                    repaired_value=value,
                    source_value=source_value,
                    source_start=start,
                    source_end=end,
                    anchor_coverage=coverage,
                    reason="lexical_run_count_mismatch",
                )
            )
            cursor = max(cursor, end)
            continue

        changed = repaired_value != value
        output_lines.append(f"{prefix}{repaired_value}")
        decisions.append(
            RepairDecision(
                line_number=line_number,
                marker=marker,
                status="repaired" if changed else "unchanged",
                match_status=match_status,
                changed=changed,
                original_value=value,
                repaired_value=repaired_value,
                source_value=source_value,
                source_start=start,
                source_end=end,
                anchor_coverage=coverage,
            )
        )
        cursor = max(cursor, end)

    repaired_text = "\n".join(output_lines) + ("\n" if mdf_text.endswith("\n") else "")
    return RepairResult(text=repaired_text, decisions=decisions)


def repair_mdf_file(
    *,
    mdf_path: str | Path,
    stage1_path: str | Path,
    output_path: str | Path,
    audit_path: str | Path | None = None,
    config: RepairConfig | None = None,
) -> RepairResult:
    """Repair one MDF file from one Stage 1 transcript and write outputs."""
    mdf_path = Path(mdf_path)
    stage1_path = Path(stage1_path)
    output_path = Path(output_path)
    mdf_text = mdf_path.read_text(encoding="utf-8")
    stage1_text = normalize_stage1_text_for_repair(stage1_path)
    result = repair_mdf_text(mdf_text, stage1_text, config=config)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(result.text, encoding="utf-8")
    if audit_path is not None:
        write_repair_audit(result, audit_path)
    return result


def write_repair_audit(result: RepairResult, audit_path: str | Path) -> None:
    """Write a JSON audit for one repaired MDF page."""
    audit_path = Path(audit_path)
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "repair_version": REPAIR_VERSION,
        "changed_lines": result.changed_lines,
        "line_decisions": [asdict(decision) for decision in result.decisions],
    }
    audit_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def iter_e2e_mdf_files(pred_root: Path) -> Iterable[tuple[str, str, str, Path]]:
    """Yield ``(language, experiment, page, mdf_path)`` under an E2E output root."""
    for language_dir in sorted(path for path in pred_root.iterdir() if path.is_dir()):
        stage2_root = language_dir / "stage-2"
        if not stage2_root.is_dir():
            continue
        for experiment_dir in sorted(path for path in stage2_root.iterdir() if path.is_dir()):
            for mdf_path in sorted(experiment_dir.glob("page_*/*.mdf.txt")):
                yield language_dir.name, experiment_dir.name, mdf_path.parent.name, mdf_path


def repair_e2e_tree(
    *,
    pred_root: str | Path,
    output_root: str | Path,
    stage1_experiment: str,
    audit_csv_path: str | Path,
    config: RepairConfig | None = None,
) -> list[dict[str, str | int]]:
    """Repair every MDF page in an E2E benchmark tree."""
    pred_root = Path(pred_root)
    output_root = Path(output_root)
    audit_csv_path = Path(audit_csv_path)
    rows: list[dict[str, str | int]] = []

    for language, experiment, page, mdf_path in iter_e2e_mdf_files(pred_root):
        stage1_path = (
            pred_root
            / language
            / "stage-1"
            / stage1_experiment
            / page
            / f"{page}_stage1_flat.txt"
        )
        rel_mdf = mdf_path.relative_to(pred_root)
        out_path = output_root / rel_mdf
        page_audit_path = out_path.with_name(f"{page}_lexical_repair.json")
        if not stage1_path.is_file():
            logger.warning("Skipping %s: missing Stage 1 transcript %s", mdf_path, stage1_path)
            continue

        result = repair_mdf_file(
            mdf_path=mdf_path,
            stage1_path=stage1_path,
            output_path=out_path,
            audit_path=page_audit_path,
            config=config,
        )
        rows.append(
            {
                "language": language,
                "experiment": experiment,
                "page": page,
                "changed_lines": result.changed_lines,
                "considered_lines": len(result.decisions),
                "input_mdf": str(mdf_path),
                "output_mdf": str(out_path),
                "audit_json": str(page_audit_path),
            }
        )

    audit_csv_path.parent.mkdir(parents=True, exist_ok=True)
    with audit_csv_path.open("w", newline="", encoding="utf-8") as handle:
        fieldnames = [
            "language",
            "experiment",
            "page",
            "changed_lines",
            "considered_lines",
            "input_mdf",
            "output_mdf",
            "audit_json",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return rows


def build_arg_parser() -> argparse.ArgumentParser:
    """Build CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="Repair Stage 2 MDF lexical drift from Stage 1 OCR transcripts."
    )
    parser.add_argument("--pred-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--stage1-experiment", required=True)
    parser.add_argument("--audit-csv", type=Path, required=True)
    parser.add_argument("--min-anchor-coverage", type=float, default=0.8)
    parser.add_argument("--min-value-lexical-chars", type=int, default=8)
    parser.add_argument("--max-span-to-value-ratio", type=float, default=1.5)
    parser.add_argument("--exact-only", action="store_true")
    return parser


def main() -> None:
    """CLI entry point."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    args = build_arg_parser().parse_args()
    config = RepairConfig(
        min_value_lexical_chars=args.min_value_lexical_chars,
        min_anchor_coverage=args.min_anchor_coverage,
        max_span_to_value_ratio=args.max_span_to_value_ratio,
        allow_approximate=not args.exact_only,
    )
    rows = repair_e2e_tree(
        pred_root=args.pred_root,
        output_root=args.output_root,
        stage1_experiment=args.stage1_experiment,
        audit_csv_path=args.audit_csv,
        config=config,
    )
    changed = sum(int(row["changed_lines"]) for row in rows)
    logger.info("Repaired %s MDF pages; changed %s field lines", len(rows), changed)


if __name__ == "__main__":
    main()
