"""Disk cache for Stage 1 evaluation metrics (incremental batch runs)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from collections import OrderedDict
from typing import Dict, List, Optional, Tuple

from mudidi.evaluation.stage1.per_language_metrics import (
    PageLanguageReport,
    PerLanguageMetrics,
)
from mudidi.evaluation.stage1.stage1_metrics import (
    CharacterQualityMetrics,
    MarkupQualityMetrics,
    ReadOrderMetrics,
    Stage1Metrics,
    TagMetrics,
)

CACHE_FILE_NAME = "stage1_eval_cache.json"
CACHE_FORMAT_VERSION = 13  # v13: adds per-language-script (per_language) metrics


def _per_language_report_to_cache_dict(report: Optional[PageLanguageReport]) -> Optional[dict]:
    """Serialize a ``PageLanguageReport`` (raw values, not display-rounded)."""
    if report is None:
        return None
    return {
        "page_id": report.page_id,
        "blended_gcer": report.blended_gcer,
        "blended_grapheme_edits": report.blended_grapheme_edits,
        "blended_graphemes_gold": report.blended_graphemes_gold,
        "per_language": {
            language: {
                "language": metrics.language,
                "gcer": metrics.gcer,
                "wer": metrics.wer,
                "text_edit": metrics.text_edit,
                "total_graphemes_gold": metrics.total_graphemes_gold,
                "total_graphemes_pred": metrics.total_graphemes_pred,
                "total_grapheme_edits": metrics.total_grapheme_edits,
                "total_words_gold": metrics.total_words_gold,
                "total_word_edits": metrics.total_word_edits,
                "attr_tp": metrics.attr_tp,
                "attr_fp": metrics.attr_fp,
                "attr_fn": metrics.attr_fn,
            }
            for language, metrics in report.per_language.items()
        },
    }


def _per_language_report_from_cache_dict(
    d: Optional[dict],
) -> Optional[PageLanguageReport]:
    if d is None:
        return None
    return PageLanguageReport(
        page_id=d.get("page_id", ""),
        per_language={
            language: PerLanguageMetrics(**metrics)
            for language, metrics in d.get("per_language", {}).items()
        },
        blended_gcer=float(d.get("blended_gcer", 0.0)),
        blended_grapheme_edits=int(d.get("blended_grapheme_edits", 0)),
        blended_graphemes_gold=int(d.get("blended_graphemes_gold", 0)),
    )


def _file_fingerprint(path: Path) -> Tuple[int, int]:
    st = path.stat()
    return (int(st.st_mtime_ns), int(st.st_size))


def stage1_metrics_to_cache_dict(m: Stage1Metrics) -> dict:
    """Serialize Stage1Metrics for JSON storage."""
    return {
        "page_id": m.page_id,
        "character_quality": {
            "text_edit": m.character_quality.text_edit,
            "gcer": m.character_quality.gcer,
            "wer": m.character_quality.wer,
            "total_graphemes_gold": m.character_quality.total_graphemes_gold,
            "total_graphemes_pred": m.character_quality.total_graphemes_pred,
            "total_grapheme_edits": m.character_quality.total_grapheme_edits,
            "total_words_gold": m.character_quality.total_words_gold,
            "total_word_edits": m.character_quality.total_word_edits,
            "matched_spans": m.character_quality.matched_spans,
            "missing_spans": m.character_quality.missing_spans,
            "extra_spans": m.character_quality.extra_spans,
        },
        "markup_quality": {
            "bold": {
                "true_positives": m.markup_quality.bold.true_positives,
                "false_positives": m.markup_quality.bold.false_positives,
                "false_negatives": m.markup_quality.bold.false_negatives,
            },
            "italic": {
                "true_positives": m.markup_quality.italic.true_positives,
                "false_positives": m.markup_quality.italic.false_positives,
                "false_negatives": m.markup_quality.italic.false_negatives,
            },
        },
        "read_order": {
            "read_order_edit": m.read_order.read_order_edit,
            "edit_distance": m.read_order.edit_distance,
            "max_length": m.read_order.max_length,
        },
        "per_language": _per_language_report_to_cache_dict(m.per_language),
    }


def stage1_metrics_from_cache_dict(d: dict) -> Stage1Metrics:
    """Restore Stage1Metrics from ``stage1_metrics_to_cache_dict`` output."""
    cq = d["character_quality"]
    mq = d["markup_quality"]
    ro = d.get("read_order", {})
    return Stage1Metrics(
        page_id=d["page_id"],
        character_quality=CharacterQualityMetrics(**cq),
        markup_quality=MarkupQualityMetrics(
            bold=TagMetrics(**mq["bold"]),
            italic=TagMetrics(**mq["italic"]),
        ),
        read_order=ReadOrderMetrics(
            read_order_edit=float(ro.get("read_order_edit", 0.0)),
            edit_distance=int(ro.get("edit_distance", 0)),
            max_length=int(ro.get("max_length", 0)),
        ),
        per_language=_per_language_report_from_cache_dict(d.get("per_language")),
    )


@dataclass
class CachedEntry:
    pred_fp: Tuple[int, int]
    gold_fp: Tuple[int, int]
    alignment_threshold: float
    character_alignment: str
    format_version: int
    metrics: Stage1Metrics
    per_language_script: bool = False


class Stage1EvalCache:
    """JSON-backed cache keyed by experiment + page_id."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._data: Dict[str, Dict[str, dict]] = {}

    def load(self) -> None:
        if not self.path.is_file():
            self._data = {}
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            self._data = {}
            return
        if raw.get("format_version") != CACHE_FORMAT_VERSION:
            self._data = {}
            return
        exps = raw.get("experiments")
        if isinstance(exps, dict):
            self._data = exps
        else:
            self._data = {}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "format_version": CACHE_FORMAT_VERSION,
            "experiments": self._data,
        }
        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def get_entry(self, experiment: str, page_id: str) -> Optional[CachedEntry]:
        blob = self._data.get(experiment, {}).get(page_id)
        if not blob:
            return None
        try:
            m = stage1_metrics_from_cache_dict(blob["metrics"])
            pf = blob["pred_fp"]
            gf = blob["gold_fp"]
            pred_fp = (int(pf[0]), int(pf[1]))
            gold_fp = (int(gf[0]), int(gf[1]))
            return CachedEntry(
                pred_fp=pred_fp,
                gold_fp=gold_fp,
                alignment_threshold=float(blob["alignment_threshold"]),
                character_alignment=str(blob.get("character_alignment", "quick_match")),
                format_version=int(blob.get("format_version", 0)),
                metrics=m,
                per_language_script=bool(blob.get("per_language_script", False)),
            )
        except (KeyError, TypeError, ValueError):
            return None

    def entry_valid(
        self,
        experiment: str,
        page_id: str,
        pred_path: Path,
        gold_path: Path,
        alignment_threshold: float,
        character_alignment: str,
        per_language_script: bool = False,
    ) -> bool:
        e = self.get_entry(experiment, page_id)
        if e is None:
            return False
        if e.format_version != CACHE_FORMAT_VERSION:
            return False
        if e.alignment_threshold != alignment_threshold:
            return False
        if e.character_alignment != character_alignment:
            return False
        # A page cached without --per-language-script has ``per_language=None``;
        # re-evaluate rather than silently reuse that stale (unpopulated) entry.
        if per_language_script and not e.per_language_script:
            return False
        try:
            if e.pred_fp != _file_fingerprint(pred_path):
                return False
            if e.gold_fp != _file_fingerprint(gold_path):
                return False
        except OSError:
            return False
        return True

    def put(
        self,
        experiment: str,
        page_id: str,
        pred_path: Path,
        gold_path: Path,
        alignment_threshold: float,
        character_alignment: str,
        metrics: Stage1Metrics,
        per_language_script: bool = False,
    ) -> None:
        self._data.setdefault(experiment, {})
        self._data[experiment][page_id] = {
            "pred_fp": list(_file_fingerprint(pred_path)),
            "gold_fp": list(_file_fingerprint(gold_path)),
            "alignment_threshold": alignment_threshold,
            "character_alignment": character_alignment,
            "format_version": CACHE_FORMAT_VERSION,
            "per_language_script": per_language_script,
            "metrics": stage1_metrics_to_cache_dict(metrics),
        }

    def prune_stale_paths(
        self, samples_dir: Path, *, stage1_output_subdir: str = "stage-1"
    ) -> None:
        """Remove entries whose prediction or gold files no longer exist on disk."""
        for exp in list(self._data.keys()):
            pages = self._data[exp]
            for page_id in list(pages.keys()):
                lang, sep, stem = page_id.partition("/")
                if not sep or not stem:
                    del pages[page_id]
                    continue
                page_dir = (
                    samples_dir / lang / "outputs" / stage1_output_subdir / exp / stem
                )
                gold_dir = samples_dir / lang / "outputs" / "stage-1-gold" / stem
                pred_flat = page_dir / f"{stem}_stage1_flat.txt"
                pred_tsv = page_dir / f"{stem}_stage1.tsv"
                gold_flat = gold_dir / f"{stem}_stage1_GOLD_flat.txt"
                gold_tsv = gold_dir / f"{stem}_stage1_GOLD.tsv"
                has_pred = pred_flat.is_file() or pred_tsv.is_file()
                has_gold = gold_flat.is_file() or gold_tsv.is_file()
                if not has_pred or not has_gold:
                    del pages[page_id]
            if not pages:
                del self._data[exp]

    def collect_valid_metrics(
        self,
        tasks: List[object],
        *,
        alignment_threshold: float,
        character_alignment: str,
        per_language_script: bool = False,
    ) -> OrderedDict[str, List[Stage1Metrics]]:
        """Group cached metrics by experiment for tasks with valid cache entries."""
        by_exp: OrderedDict[str, List[Stage1Metrics]] = OrderedDict()
        for task in tasks:
            if not self.entry_valid(
                task.experiment,
                task.page_id,
                task.pred_path,
                task.gold_path,
                alignment_threshold,
                character_alignment,
                per_language_script,
            ):
                continue
            entry = self.get_entry(task.experiment, task.page_id)
            if entry is None:
                continue
            by_exp.setdefault(task.experiment, []).append(entry.metrics)
        return by_exp
