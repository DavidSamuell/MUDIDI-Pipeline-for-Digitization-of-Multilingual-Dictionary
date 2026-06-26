"""Unit tests for per-language Stage 1 evaluation (per_language_quality)."""

from __future__ import annotations

from pathlib import Path

import pytest

from mudidi.evaluation.stage1.per_language_metrics import (
    PageLanguageReport,
    PerLanguageMetrics,
    aggregate,
)
from mudidi.evaluation.stage1.per_language_quality import (
    collapsed_clean_text,
    compute_per_language_quality,
    evaluate_per_language,
)
from mudidi.schemas.language_span import (
    SPACE,
    LanguageSpan,
    PageLanguageMap,
    SpanMapError,
    sha256_of,
)

GOLD = "akɔɔtee small crab in wait\namãrɛ the remains of\n"


def _build_map(raw: str) -> PageLanguageMap:
    """Label the first word of each line as the source (Canala), the rest English."""
    spans = []
    index = 0
    length = len(raw)
    line_start = True
    while index < length:
        if raw[index].isspace():
            stop = index
            while stop < length and raw[stop].isspace():
                stop += 1
            spans.append(LanguageSpan(start=index, end=stop, language=SPACE))
            if "\n" in raw[index:stop]:
                line_start = True
            index = stop
        else:
            stop = index
            while stop < length and not raw[stop].isspace():
                stop += 1
            spans.append(
                LanguageSpan(
                    start=index,
                    end=stop,
                    language="Canala" if line_start else "English",
                )
            )
            line_start = False
            index = stop
    return PageLanguageMap(
        dictionary="Canala-English",
        page=12,
        source_text_sha=sha256_of(raw),
        labeled_via="heuristic",
        spans=spans,
    )


def _write_case(tmp_path: Path, gold: str, pred: str):
    gold_path = tmp_path / "page_12_stage1_GOLD_flat.txt"
    pred_path = tmp_path / "page_12_stage1.txt"
    map_path = tmp_path / "page_12_lang.json"
    gold_path.write_text(gold, encoding="utf-8")
    pred_path.write_text(pred, encoding="utf-8")
    raw = gold_path.read_text(encoding="utf-8")  # sha must match what eval reads
    _build_map(raw).save(map_path)
    return pred_path, gold_path, map_path


def test_consistency_oracle(tmp_path):
    # Arrange: pred corrupts one English word ("small" -> "smxll").
    pred = GOLD.replace("small", "smxll")
    pred_path, gold_path, map_path = _write_case(tmp_path, GOLD, pred)
    # Act
    report = evaluate_per_language(pred_path, gold_path, map_path, page_id="page_12")
    # Assert: per-language grapheme counts pool to the blended totals.
    total_edits = sum(m.total_grapheme_edits for m in report.per_language.values())
    total_gold = sum(m.total_graphemes_gold for m in report.per_language.values())
    assert total_edits == report.blended_grapheme_edits
    assert total_gold == report.blended_graphemes_gold
    assert report.blended_grapheme_edits > 0  # the corruption registered


def test_english_only_corruption_isolated(tmp_path):
    pred = GOLD.replace("small", "smxll")
    pred_path, gold_path, map_path = _write_case(tmp_path, GOLD, pred)
    report = evaluate_per_language(pred_path, gold_path, map_path)
    assert report.per_language["English"].total_grapheme_edits > 0
    assert report.per_language["English"].gcer > 0
    assert report.per_language["Canala"].total_grapheme_edits == 0
    assert report.per_language["Canala"].gcer == 0.0


def test_source_only_corruption_isolated(tmp_path):
    pred = GOLD.replace("akɔɔtee", "akxxtee")
    pred_path, gold_path, map_path = _write_case(tmp_path, GOLD, pred)
    report = evaluate_per_language(pred_path, gold_path, map_path)
    assert report.per_language["Canala"].total_grapheme_edits > 0
    assert report.per_language["English"].total_grapheme_edits == 0


def test_word_error_partition(tmp_path):
    pred = GOLD.replace("small", "smxll")  # one English word substitution
    pred_path, gold_path, map_path = _write_case(tmp_path, GOLD, pred)
    report = evaluate_per_language(pred_path, gold_path, map_path)
    assert report.per_language["English"].total_word_edits == 1
    assert report.per_language["Canala"].total_word_edits == 0
    total_word_edits = sum(m.total_word_edits for m in report.per_language.values())
    assert total_word_edits == 1


def test_clean_prediction_is_zero(tmp_path):
    pred_path, gold_path, map_path = _write_case(tmp_path, GOLD, GOLD)
    report = evaluate_per_language(pred_path, gold_path, map_path)
    assert report.blended_grapheme_edits == 0
    for metrics in report.per_language.values():
        assert metrics.gcer == 0.0
        assert metrics.wer == 0.0


def test_empty_prediction_oracle_holds(tmp_path):
    pred_path, gold_path, map_path = _write_case(tmp_path, GOLD, "")
    report = evaluate_per_language(pred_path, gold_path, map_path)
    total_edits = sum(m.total_grapheme_edits for m in report.per_language.values())
    assert total_edits == report.blended_grapheme_edits
    assert report.blended_grapheme_edits > 0  # everything deleted


def test_sha_mismatch_refuses(tmp_path):
    pred_path, gold_path, map_path = _write_case(tmp_path, GOLD, GOLD)
    gold_path.write_text(GOLD + "tampered\n", encoding="utf-8")  # gold changed after labelling
    with pytest.raises(SpanMapError):
        evaluate_per_language(pred_path, gold_path, map_path)


def test_compute_core_matches_file_wrapper(tmp_path):
    # The strings-core entry should match the file wrapper (the path the flat
    # evaluator uses when feeding pair.gold.text / pair.pred.text).
    pred = GOLD.replace("small", "smxll")
    pred_path, gold_path, map_path = _write_case(tmp_path, GOLD, pred)
    raw_gold = gold_path.read_text(encoding="utf-8")
    lang_map = PageLanguageMap.load(map_path)
    core = compute_per_language_quality(
        collapsed_clean_text(gold_path),
        collapsed_clean_text(pred_path),
        raw_gold,
        lang_map,
        page_id="page_12",
    )
    wrapper = evaluate_per_language(pred_path, gold_path, map_path, page_id="page_12")
    assert core.blended_grapheme_edits == wrapper.blended_grapheme_edits
    assert (
        core.per_language["English"].total_grapheme_edits
        == wrapper.per_language["English"].total_grapheme_edits
    )


def test_aggregate_pools_counts():
    def _report(edits, gold):
        return PageLanguageReport(
            per_language={
                "English": PerLanguageMetrics(
                    language="English",
                    total_grapheme_edits=edits,
                    total_graphemes_gold=gold,
                )
            }
        )

    pooled = aggregate([_report(2, 10), _report(3, 30)])
    assert pooled["English"].total_grapheme_edits == 5
    assert pooled["English"].total_graphemes_gold == 40
    assert pooled["English"].gcer == 5 / 40
