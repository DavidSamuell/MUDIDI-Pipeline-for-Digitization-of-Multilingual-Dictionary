"""Unit tests for the Label Studio NER round-trip (annotation/label_studio_ner.py)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from label_studio_ner import (  # noqa: E402  (flat sibling import)
    build_labels_config,
    load_label_set,
    ls_task_to_page_map,
    page_map_to_ls_task,
)
from span_schema import (  # noqa: E402
    META,
    SPACE,
    LanguageSpan,
    PageLanguageMap,
    SpanMapError,
    sha256_of,
)

SNIPPET = "akɔɔtee small crab"


def _canala_map() -> PageLanguageMap:
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


def test_task_span_text_matches_gold_slice():
    task = page_map_to_ls_task(_canala_map(), SNIPPET)
    results = task["predictions"][0]["result"]
    # SPACE spans are dropped: 3 meaningful regions remain.
    assert len(results) == 3
    for result in results:
        value = result["value"]
        assert SNIPPET[value["start"] : value["end"]] == value["text"]
        assert len(value["labels"]) == 1
        assert value["labels"][0] != SPACE


def test_round_trip_is_identity_up_to_canonical():
    page_map = _canala_map()
    # Act
    task = page_map_to_ls_task(page_map, SNIPPET)
    rebuilt = ls_task_to_page_map(
        task, SNIPPET, dictionary="Canala-English", page=12
    )
    # Assert: the labelling (spans) survives; provenance metadata may differ.
    assert rebuilt.canonical().spans == page_map.canonical().spans


def test_annotation_overrides_prediction():
    page_map = _canala_map()
    task = page_map_to_ls_task(page_map, SNIPPET)
    # Human submits an annotation that relabels the first region as English.
    submitted = {
        "model_version": "label-studio",
        "result": [
            {
                "from_name": "label",
                "to_name": "text",
                "type": "labels",
                "value": {"start": 0, "end": 7, "text": "akɔɔtee", "labels": ["English"]},
            }
        ],
    }
    task["annotations"] = [submitted]
    rebuilt = ls_task_to_page_map(task, SNIPPET, dictionary="Canala-English", page=12)
    assert rebuilt.language_char_map(SNIPPET)[0] == "English"


def test_tampered_region_text_raises():
    task = page_map_to_ls_task(_canala_map(), SNIPPET)
    mutated = SNIPPET.replace("small", "smbll")  # same length, different slice
    with pytest.raises(SpanMapError):
        ls_task_to_page_map(task, mutated, dictionary="Canala-English", page=12)


def test_build_labels_config_lists_languages_and_meta():
    config = build_labels_config(["Canala", "English"])
    assert '<Label value="Canala"/>' in config
    assert '<Label value="English"/>' in config
    assert f'<Label value="{META}"/>' in config
    assert 'toName="text"' in config
    assert 'value="$text"' in config


def test_load_label_set_reads_dictionary_languages_yaml(tmp_path):
    (tmp_path / "dictionary_languages.yaml").write_text(
        "layout: bilingual\n"
        "source:\n  language: Canala\n  code: canala\n"
        "targets:\n- language: English\n  code: en\n",
        encoding="utf-8",
    )
    assert load_label_set(tmp_path) == ["Canala", "English"]


def test_load_label_set_missing_file_returns_empty(tmp_path):
    assert load_label_set(tmp_path) == []
