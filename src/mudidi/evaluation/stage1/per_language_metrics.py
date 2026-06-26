"""Per-language Stage 1 metric containers.

Mirrors :class:`mudidi.evaluation.stage1.stage1_metrics.CharacterQualityMetrics`
but partitioned by language. Ratios are pooled from raw counts (micro-average),
exactly as the blended metric pools, so summing the per-language counts reproduces
the page-level blended numbers (the consistency oracle).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class PerLanguageMetrics:
    """Character + word quality for one language on a page (or aggregated)."""

    language: str
    gcer: float = 0.0
    wer: float = 0.0
    text_edit: float = 0.0
    total_graphemes_gold: int = 0
    total_graphemes_pred: int = 0
    total_grapheme_edits: int = 0
    total_words_gold: int = 0
    total_word_edits: int = 0
    # Language-attribution quality of the prediction's characters (secondary).
    attr_tp: int = 0
    attr_fp: int = 0
    attr_fn: int = 0

    @property
    def precision(self) -> float:
        denom = self.attr_tp + self.attr_fp
        return self.attr_tp / denom if denom else 0.0

    @property
    def recall(self) -> float:
        denom = self.attr_tp + self.attr_fn
        return self.attr_tp / denom if denom else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) else 0.0


@dataclass
class PageLanguageReport:
    """Per-language metrics for one page plus the blended totals (oracle target)."""

    page_id: str = ""
    per_language: Dict[str, PerLanguageMetrics] = field(default_factory=dict)
    blended_gcer: float = 0.0
    blended_grapheme_edits: int = 0
    blended_graphemes_gold: int = 0


def aggregate(reports: List[PageLanguageReport]) -> Dict[str, PerLanguageMetrics]:
    """Pool per-language counts across pages and recompute ratios (micro-average)."""
    acc: Dict[str, PerLanguageMetrics] = {}
    for report in reports:
        for language, metrics in report.per_language.items():
            running = acc.setdefault(language, PerLanguageMetrics(language=language))
            running.total_graphemes_gold += metrics.total_graphemes_gold
            running.total_graphemes_pred += metrics.total_graphemes_pred
            running.total_grapheme_edits += metrics.total_grapheme_edits
            running.total_words_gold += metrics.total_words_gold
            running.total_word_edits += metrics.total_word_edits
            running.attr_tp += metrics.attr_tp
            running.attr_fp += metrics.attr_fp
            running.attr_fn += metrics.attr_fn
    for running in acc.values():
        running.gcer = (
            running.total_grapheme_edits / running.total_graphemes_gold
            if running.total_graphemes_gold
            else 0.0
        )
        running.wer = (
            running.total_word_edits / running.total_words_gold
            if running.total_words_gold
            else 0.0
        )
        denom = max(running.total_graphemes_gold, running.total_graphemes_pred, 1)
        running.text_edit = running.total_grapheme_edits / denom
    return acc
