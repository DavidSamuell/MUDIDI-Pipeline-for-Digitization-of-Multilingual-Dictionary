"""eval-flat: per-page flat text vs gold flat (spec v2)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Literal, Optional

from mudidi.evaluation.stage1.stage1_task_discovery import (
    FlatEvalTask,
    discover_dataset_tasks as _discover_dataset_tasks,
    discover_legacy_tasks as _discover_legacy_tasks,
)

from mudidi.evaluation.stage1.alignment import (
    align_lines_quick_match,
    align_page_collapsed,
)
from mudidi.evaluation.stage1.character_quality import compute_character_quality
from mudidi.evaluation.stage1.flatten import (
    flatten_stage1_tsv,
    load_flat_lines,
)
from mudidi.evaluation.stage1.markup_quality import compute_markup_quality
from mudidi.evaluation.stage1 import per_language_quality
from mudidi.evaluation.stage1.per_language_metrics import PageLanguageReport
from mudidi.evaluation.stage1.read_order import (
    compute_read_order,
    compute_read_order_collapsed,
)
from mudidi.evaluation.stage1.stage1_reports import Stage1ReportWriter
from mudidi.evaluation.stage1.stage1_metrics import Stage1Metrics
from mudidi.schemas.language_span import SpanMapError

logger = logging.getLogger(__name__)

Row = Dict[str, str]
MetricsProfile = Literal["full", "minimal"]
CharacterAlignmentMode = Literal["collapsed", "quick_match"]


def _lines_to_rows(lines: List[str]) -> List[Row]:
    return [
        {"column_id": "single", "line_number": str(i), "text": line}
        for i, line in enumerate(lines, start=1)
    ]


def _load_pred_lines(pred_path: Path) -> List[str]:
    if pred_path.suffix == ".tsv" or pred_path.name.endswith("_stage1.tsv"):
        text = flatten_stage1_tsv(pred_path)
        return text.splitlines() if text else []
    return load_flat_lines(pred_path)


class FlatStage1Evaluator:
    """Evaluate flat stage-1 predictions against flat gold.

    Character and typography default to OmniDocBench quick_match (line-level
    Adjacency Search Match). ReadOrderEdit uses the same matched pairs (quick_match)
    or anchor search in the collapsed pred string (collapsed mode).
    """

    def __init__(
        self,
        metrics_profile: MetricsProfile = "full",
        *,
        character_alignment: CharacterAlignmentMode = "quick_match",
        alignment_threshold: float = 0.6,
        per_language_script: bool = False,
    ) -> None:
        self.metrics_profile = metrics_profile
        self.character_alignment = character_alignment
        self.alignment_threshold = alignment_threshold
        self.per_language_script = per_language_script
        self._report_helper = Stage1ReportWriter(
            metrics_profile=metrics_profile,
            include_read_order=True,
            include_per_language_script=per_language_script,
        )

    def _metric_csv_cols(self) -> List[str]:
        return self._report_helper._metric_csv_cols()

    def evaluate(
        self,
        pred_path: str | Path,
        gold_path: str | Path,
        page_id: str = "",
    ) -> Stage1Metrics:
        pred_path = Path(pred_path)
        gold_path = Path(gold_path)
        pred_lines = _load_pred_lines(pred_path)
        gold_lines = load_flat_lines(gold_path)
        pred_rows = _lines_to_rows(pred_lines)
        gold_rows = _lines_to_rows(gold_lines)
        if self.character_alignment == "collapsed":
            content_alignment = align_page_collapsed(pred_rows, gold_rows)
            read_order = compute_read_order_collapsed(gold_lines, pred_lines)
        else:
            content_alignment = align_lines_quick_match(pred_rows, gold_rows)
            read_order = compute_read_order(content_alignment)
        char_q = compute_character_quality(content_alignment)
        markup_q = compute_markup_quality(content_alignment)

        per_language = None
        if self.per_language_script:
            per_language = self._evaluate_per_language_script(
                pred_path, gold_path, page_id
            )

        return Stage1Metrics(
            page_id=page_id,
            character_quality=char_q,
            markup_quality=markup_q,
            read_order=read_order,
            per_language=per_language,
        )

    @staticmethod
    def _evaluate_per_language_script(
        pred_path: Path, gold_path: Path, page_id: str
    ) -> Optional[PageLanguageReport]:
        """Evaluate per-language-script quality when a co-located ``*_lang.json``
        gold span map exists; ``None`` otherwise (silently skipped -- most
        dictionaries don't have one yet) or if the span map fails validation
        (logged and skipped rather than failing the whole run).
        """
        lang_map_path = per_language_quality.lang_map_path_for_gold(gold_path)
        if not lang_map_path.exists():
            return None
        try:
            return per_language_quality.evaluate_per_language(
                pred_path, gold_path, lang_map_path, page_id=page_id
            )
        except SpanMapError:
            logger.warning(
                "Skipping per-language-script eval for %s: invalid span map at %s",
                page_id,
                lang_map_path,
                exc_info=True,
            )
            return None

    @staticmethod
    def discover_tasks(
        samples_dir: str | Path,
        experiments: Optional[List[str]] = None,
        languages: Optional[List[str]] = None,
        stage1_output_subdir: str = "stage-1",
    ) -> List[FlatEvalTask]:
        """Discover flat gold/pred pairs under the legacy samples layout."""
        return _discover_legacy_tasks(
            samples_dir,
            experiments=experiments,
            languages=languages,
            stage1_output_subdir=stage1_output_subdir,
        )

    @staticmethod
    def discover_dataset_tasks(
        dataset_dir: str | Path,
        pred_root: str | Path,
        experiments: Optional[List[str]] = None,
        languages: Optional[List[str]] = None,
        stage1_output_subdir: str = "stage-1",
    ) -> List[FlatEvalTask]:
        """Discover flat gold/pred pairs under the MUDIDI dataset + benchmark layout."""
        return _discover_dataset_tasks(
            dataset_dir,
            pred_root,
            experiments=experiments,
            languages=languages,
            stage1_output_subdir=stage1_output_subdir,
        )

    def generate_text_report(
        self, results: List[Stage1Metrics], output_path: Path
    ) -> str:
        return self._report_helper.generate_text_report(results, output_path)

    def generate_json_report(
        self, results: List[Stage1Metrics], output_path: Path
    ) -> None:
        return self._report_helper.generate_json_report(results, output_path)

    def generate_csv_reports(
        self, results: List[Stage1Metrics], output_dir: Path
    ) -> None:
        return self._report_helper.generate_csv_reports(results, output_dir)

    def generate_per_language_script_csv(
        self, results: List[Stage1Metrics], output_path: Path
    ) -> None:
        return self._report_helper.generate_per_language_script_csv(
            results, output_path
        )

    def generate_per_language_script_detailed_csv(
        self, results_by_exp: dict, output_path: Path
    ) -> None:
        return self._report_helper.generate_per_language_script_detailed_csv(
            results_by_exp, output_path
        )

    def generate_per_language_script_summary_csv(
        self, results_by_exp: dict, output_path: Path
    ) -> None:
        return self._report_helper.generate_per_language_script_summary_csv(
            results_by_exp, output_path
        )

    def generate_detailed_csv(
        self,
        results_by_exp: dict,
        samples_dir: Path,
        output_path: Path,
        *,
        stage1_output_subdir: str = "stage-1",
        pred_root: Path | None = None,
    ) -> None:
        return self._report_helper.generate_detailed_csv(
            results_by_exp,
            samples_dir,
            output_path,
            stage1_output_subdir=stage1_output_subdir,
            pred_root=pred_root,
        )

    def generate_summary_csv(
        self,
        results_by_exp: dict,
        samples_dir: Path,
        output_path: Path,
        *,
        stage1_output_subdir: str = "stage-1",
        pred_root: Path | None = None,
    ) -> None:
        return self._report_helper.generate_summary_csv(
            results_by_exp,
            samples_dir,
            output_path,
            stage1_output_subdir=stage1_output_subdir,
            pred_root=pred_root,
        )
