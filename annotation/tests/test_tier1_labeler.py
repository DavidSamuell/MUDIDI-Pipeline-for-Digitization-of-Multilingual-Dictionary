"""Unit tests for the Tier-1 script-check labeler (annotation/labelers/tier1_labeler.py)."""

from __future__ import annotations

import pytest

from label_studio_ner import page_map_to_ls_task, ls_task_to_page_map  # noqa: E402
from tier1_labeler import (  # noqa: E402
    Tier1Error,
    label_page,
)

from mudidi.schemas.language_span import SPACE  # noqa: E402


def _lang_at(page_map, raw, needle):
    """Return the single language covering the first occurrence of *needle*."""
    start = raw.index(needle)
    char_map = page_map.language_char_map(raw)
    langs = {char_map[i] for i in range(start, start + len(needle))}
    assert len(langs) == 1, f"{needle!r} spans multiple languages: {langs}"
    return next(iter(langs))


def test_greek_english_partition():
    raw = "<b>᾿Αδράχνω</b>, v. a. to seize.\nergy, laxly.\n"
    page_map = label_page(
        raw,
        dictionary="Greek-English",
        page=38,
        source_language="Greek",
        target_languages=["English"],
    )
    page_map.validate_against(raw)  # full coverage + sha bind
    assert _lang_at(page_map, raw, "Αδράχνω") == "Greek"
    assert _lang_at(page_map, raw, "seize") == "English"
    assert _lang_at(page_map, raw, "ergy") == "English"


def test_markup_wrapped_source_word_is_source():
    raw = "<b>᾿Αδράχνω</b> rest\n"
    page_map = label_page(
        raw,
        dictionary="Greek-English",
        page=1,
        source_language="Greek",
        target_languages=["English"],
    )
    # The whole markup-wrapped token (incl. the incidental Latin ``b`` of the tag).
    assert _lang_at(page_map, raw, "<b>᾿Αδράχνω</b>") == "Greek"


def test_georgian_russian_partition():
    raw = "<b>ესენი</b> эти; см.\n"
    page_map = label_page(
        raw,
        dictionary="Georgian-Russian",
        page=116,
        source_language="Georgian",
        target_languages=["Russian"],
    )
    page_map.validate_against(raw)
    assert _lang_at(page_map, raw, "ესენი") == "Georgian"
    assert _lang_at(page_map, raw, "эти") == "Russian"
    assert _lang_at(page_map, raw, "см") == "Russian"


def test_punct_and_digits_carry_forward():
    # Header line: Greek source, "=" and "13" are punct/digit and inherit Greek.
    raw = "ΑΔΡΑ = 13 = ΑΕΡΟ\n"
    page_map = label_page(
        raw,
        dictionary="Greek-English",
        page=1,
        source_language="Greek",
        target_languages=["English"],
    )
    assert _lang_at(page_map, raw, "=") == "Greek"
    assert _lang_at(page_map, raw, "13") == "Greek"


def test_full_coverage_and_contiguity():
    raw = "<b>ესენი</b> эти\n"
    page_map = label_page(
        raw,
        dictionary="Georgian-Russian",
        page=1,
        source_language="Georgian",
        target_languages=["Russian"],
    )
    # Spans tile [0, len) with no gaps/overlaps and whitespace is SPACE.
    assert page_map.spans[0].start == 0
    assert page_map.spans[-1].end == len(raw)
    for prev, cur in zip(page_map.spans, page_map.spans[1:]):
        assert cur.start == prev.end
    char_map = page_map.language_char_map(raw)
    assert char_map[raw.index(" ")] == SPACE


def test_ner_round_trip_is_lossless():
    raw = "<b>᾿Αδράχνω</b>, to seize.\n"
    page_map = label_page(
        raw,
        dictionary="Greek-English",
        page=1,
        source_language="Greek",
        target_languages=["English"],
    )
    task = page_map_to_ls_task(page_map, raw)
    rebuilt = ls_task_to_page_map(
        task, raw, dictionary="Greek-English", page=1, labeled_via="heuristic"
    )
    assert rebuilt.canonical().spans == page_map.canonical().spans


def test_non_tier1_dictionary_raises():
    with pytest.raises(Tier1Error):
        label_page(
            "akɔɔtee small\n",
            dictionary="Canala-English",
            page=12,
            source_language="Canala",
            target_languages=["English"],
        )


def test_empty_page_has_no_spans():
    page_map = label_page(
        "",
        dictionary="Greek-English",
        page=1,
        source_language="Greek",
        target_languages=["English"],
    )
    assert page_map.spans == []
    page_map.validate_against("")
