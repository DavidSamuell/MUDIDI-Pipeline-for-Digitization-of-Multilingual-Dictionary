"""Shared text-quality metrics for aligned gold/pred string pairs."""

from __future__ import annotations

from collections.abc import Sequence

import grapheme
import jiwer
import Levenshtein

from mudidi.evaluation.stage1.stage1_metrics import CharacterQualityMetrics
from mudidi.evaluation.stage1.tag_parser import casefold_letters_for_eval

_JIWER_WORD_TRANSFORM = jiwer.Compose([jiwer.ReduceToListOfListOfWords()])


def aggregate_text_quality(pairs: Sequence[tuple[str, str]]) -> CharacterQualityMetrics:
    """Compute TextEdit, GCER, and WER over aligned (gold, pred) text pairs."""
    if not pairs:
        return CharacterQualityMetrics()

    total_grapheme_edits = 0
    total_graphemes_gold = 0
    total_graphemes_pred = 0
    total_words_gold = 0
    text_edit_sum = 0.0
    matched = len(pairs)

    gold_spans: list[str] = []
    pred_spans: list[str] = []

    for gold_raw, pred_raw in pairs:
        gold = casefold_letters_for_eval(gold_raw)
        pred = casefold_letters_for_eval(pred_raw)
        pg = list(grapheme.graphemes(pred))
        gg = list(grapheme.graphemes(gold))
        edits = Levenshtein.distance(pg, gg)
        total_grapheme_edits += edits
        total_graphemes_gold += len(gg)
        total_graphemes_pred += len(pg)
        total_words_gold += len(gold_raw.split())
        gold_spans.append(gold)
        pred_spans.append(pred)
        if gg or pg:
            text_edit_sum += edits / max(len(gg), len(pg), 1)

    wer = 0.0
    if gold_spans or pred_spans:
        word_output = jiwer.process_words(
            gold_spans,
            pred_spans,
            reference_transform=_JIWER_WORD_TRANSFORM,
            hypothesis_transform=_JIWER_WORD_TRANSFORM,
        )
        wer = float(word_output.wer)

    text_edit = text_edit_sum / len(pairs)
    gcer = (
        total_grapheme_edits / total_graphemes_gold if total_graphemes_gold else 0.0
    )
    total_word_edits = round(wer * total_words_gold)

    return CharacterQualityMetrics(
        text_edit=text_edit,
        gcer=gcer,
        wer=wer,
        total_graphemes_gold=total_graphemes_gold,
        total_graphemes_pred=total_graphemes_pred,
        total_grapheme_edits=total_grapheme_edits,
        total_words_gold=total_words_gold,
        total_word_edits=total_word_edits,
        matched_spans=matched,
        missing_spans=0,
        extra_spans=0,
    )


def merge_character_quality(metrics: Sequence[CharacterQualityMetrics]) -> CharacterQualityMetrics:
    """Micro-average character quality metrics across pages."""
    if not metrics:
        return CharacterQualityMetrics()
    total_grapheme_edits = sum(m.total_grapheme_edits for m in metrics)
    total_graphemes_gold = sum(m.total_graphemes_gold for m in metrics)
    total_words_gold = sum(m.total_words_gold for m in metrics)
    total_word_edits = sum(m.total_word_edits for m in metrics)
    matched = sum(m.matched_spans for m in metrics)
    text_edit = sum(m.text_edit * m.matched_spans for m in metrics) / matched if matched else 0.0
    gcer = total_grapheme_edits / total_graphemes_gold if total_graphemes_gold else 0.0
    wer = total_word_edits / total_words_gold if total_words_gold else 0.0
    return CharacterQualityMetrics(
        text_edit=text_edit,
        gcer=gcer,
        wer=wer,
        total_graphemes_gold=total_graphemes_gold,
        total_graphemes_pred=sum(m.total_graphemes_pred for m in metrics),
        total_grapheme_edits=total_grapheme_edits,
        total_words_gold=total_words_gold,
        total_word_edits=total_word_edits,
        matched_spans=matched,
        missing_spans=sum(m.missing_spans for m in metrics),
        extra_spans=sum(m.extra_spans for m in metrics),
    )
