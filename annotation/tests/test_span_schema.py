"""Unit tests for the span-label gold contract (annotation/label_studio/span_schema.py)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from span_schema import (  # noqa: E402  (flat import; see annotation/tests/conftest.py)
    SPACE,
    LanguageSpan,
    PageLanguageMap,
    SpanMapError,
    sha256_of,
)

# Real Canala gold snippet: IPA headword (multi-codepoint) + English definition.
SNIPPET = "akɔɔtee small crab"  # len == 18 codepoints


def _canala_map() -> PageLanguageMap:
    """A valid, contiguous, full-coverage map over SNIPPET (role-free)."""
    return PageLanguageMap(
        dictionary="Canala-English",
        page=12,
        source_text_sha=sha256_of(SNIPPET),
        labeled_via="heuristic",
        spans=[
            LanguageSpan(start=0, end=7, language="Canala"),
            LanguageSpan(start=7, end=8, language=SPACE),
            LanguageSpan(start=8, end=13, language="English"),
            LanguageSpan(start=13, end=14, language=SPACE),
            LanguageSpan(start=14, end=18, language="English"),
        ],
    )


def test_json_round_trip(tmp_path):
    # Arrange
    page_map = _canala_map()
    path = tmp_path / "page_12_lang.json"
    # Act
    page_map.save(path)
    loaded = PageLanguageMap.load(path)
    # Assert
    assert loaded == page_map


def test_contiguous_map_validates_against_text():
    _canala_map().validate_against(SNIPPET)  # does not raise


def test_gap_rejected_at_construction():
    with pytest.raises(ValidationError):
        PageLanguageMap(
            dictionary="X",
            page=1,
            source_text_sha="x",
            labeled_via="heuristic",
            spans=[
                LanguageSpan(start=0, end=5, language="English"),
                LanguageSpan(start=6, end=10, language="English"),
            ],
        )


def test_overlap_rejected_at_construction():
    with pytest.raises(ValidationError):
        PageLanguageMap(
            dictionary="X",
            page=1,
            source_text_sha="x",
            labeled_via="heuristic",
            spans=[
                LanguageSpan(start=0, end=6, language="English"),
                LanguageSpan(start=5, end=10, language="English"),
            ],
        )


def test_span_end_must_exceed_start():
    with pytest.raises(ValidationError):
        LanguageSpan(start=5, end=5, language="English")


def test_sha_guard_rejects_mutated_text():
    page_map = _canala_map()
    with pytest.raises(SpanMapError):
        page_map.validate_against(SNIPPET + " mutated")


def test_language_char_map():
    labels = _canala_map().language_char_map(SNIPPET)
    assert len(labels) == len(SNIPPET)
    assert labels[0] == "Canala"  # IPA headword
    assert labels[7] == SPACE
    assert labels[8] == "English"


def test_canonical_merges_adjacent_same_language():
    page_map = PageLanguageMap(
        dictionary="X",
        page=1,
        source_text_sha=sha256_of("abcd"),
        labeled_via="heuristic",
        spans=[
            LanguageSpan(start=0, end=2, language="English"),
            LanguageSpan(start=2, end=4, language="English"),
        ],
    )
    canon = page_map.canonical()
    assert len(canon.spans) == 1
    assert (canon.spans[0].start, canon.spans[0].end) == (0, 4)


def test_role_survives_json_round_trip(tmp_path):
    page_map = PageLanguageMap(
        dictionary="X",
        page=1,
        source_text_sha=sha256_of("ab"),
        labeled_via="heuristic",
        spans=[LanguageSpan(start=0, end=2, language="Canala", role="headword")],
    )
    path = tmp_path / "m.json"
    page_map.save(path)
    assert PageLanguageMap.load(path).spans[0].role == "headword"


def test_empty_text_requires_no_spans():
    empty = PageLanguageMap(
        dictionary="X",
        page=1,
        source_text_sha=sha256_of(""),
        labeled_via="heuristic",
    )
    empty.validate_against("")  # ok
    with pytest.raises(SpanMapError):
        _canala_map().validate_against("")  # sha mismatch
