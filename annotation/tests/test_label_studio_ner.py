"""Unit tests for the Label Studio NER round-trip (annotation/label_studio/label_studio_ner.py)."""

from __future__ import annotations

import pytest

from label_studio_ner import (  # noqa: E402  (flat import; see annotation/tests/conftest.py)
    build_labels_config,
    load_label_set,
    ls_task_to_page_map,
    normalize_ls_task_dict,
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


def test_ls_task_to_page_map_tolerates_prediction_ids_from_export():
    """Label Studio export may return predictions as bare integer IDs."""
    page_map = _canala_map()
    task = page_map_to_ls_task(page_map, SNIPPET)
    task["predictions"] = [259]  # PrimaryKeyRelatedField stub from export API
    task["annotations"] = [
        {
            "result": [
                {
                    "from_name": "label",
                    "to_name": "text",
                    "type": "labels",
                    "value": {"start": 0, "end": 7, "text": "akɔɔtee", "labels": ["English"]},
                }
            ]
        }
    ]
    rebuilt = ls_task_to_page_map(task, SNIPPET, dictionary="Canala-English", page=12)
    assert rebuilt.language_char_map(SNIPPET)[0] == "English"


def test_normalize_ls_task_dict_filters_non_dict_entries():
    raw = {"predictions": [259, {"result": []}], "annotations": [42]}
    normalized = normalize_ls_task_dict(raw)
    assert normalized["predictions"] == [{"result": []}]
    assert normalized["annotations"] == []


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


def test_region_with_escaped_boundary_newline_reconciles():
    # Label Studio export can prepend the boundary newline to value.text and serialize
    # it as the literal escape '\\n' while keeping start/end pointing at the content.
    raw = "headword\nsmall crab"  # newline at index 8; "small crab" at [9:19]
    task = {
        "annotations": [
            {
                "result": [
                    {
                        "from_name": "label",
                        "to_name": "text",
                        "type": "labels",
                        "value": {
                            "start": 9,
                            "end": 19,
                            "text": "\\nsmall crab",  # literal backslash-n + content
                            "labels": ["English"],
                        },
                    }
                ]
            }
        ]
    }
    page_map = ls_task_to_page_map(task, raw, dictionary="Canala-English", page=1)
    # The offsets are honoured: [9:19] is English, the newline at 8 stays SPACE.
    cm = page_map.language_char_map(raw)
    assert cm[9] == "English"
    assert cm[8] == SPACE


def test_region_with_genuinely_different_text_still_raises():
    raw = "headword small crab"
    task = {
        "annotations": [
            {
                "result": [
                    {
                        "from_name": "label",
                        "to_name": "text",
                        "type": "labels",
                        "value": {
                            "start": 9,
                            "end": 14,
                            "text": "totally different",
                            "labels": ["English"],
                        },
                    }
                ]
            }
        ]
    }
    with pytest.raises(SpanMapError):
        ls_task_to_page_map(task, raw, dictionary="Canala-English", page=1)


def test_build_labels_config_lists_languages_and_meta():
    config = build_labels_config(["Canala", "English"])
    assert '<Label value="Canala"' in config
    assert '<Label value="English"' in config
    assert f'<Label value="{META}"' in config
    assert 'toName="text"' in config
    assert 'value="$text"' in config
    # Default config has no image panel.
    assert "<Image" not in config


def test_build_labels_config_assigns_distinct_colors():
    import re

    config = build_labels_config(["Canala", "English"])
    colors = re.findall(r'<Label value="[^"]+" background="([^"]+)"', config)
    # Every label (Canala, English, META) gets a colour, and none collide.
    assert len(colors) == 3
    assert len(set(colors)) == 3


def test_build_labels_config_image_adds_reference_panel():
    config = build_labels_config(["Canala", "English"], image=True)
    # The NER labelling controls survive…
    assert '<Label value="Canala"' in config
    assert 'value="$text"' in config
    # …and the original page render is bound side-by-side via $image_url.
    assert "<Image" in config
    assert 'value="$image_url"' in config


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


def test_resolve_page_image_copies_png_into_render_dir(tmp_path):
    from setup_ner_projects import resolve_page_image

    dict_dir = tmp_path / "Some-Dict"
    pages = dict_dir / "Dictionary pages"
    pages.mkdir(parents=True)
    (pages / "page_7.png").write_bytes(b"\x89PNG\r\n")  # content is irrelevant here

    render_dir = tmp_path / "renders" / "Some-Dict"
    url = resolve_page_image(dict_dir, 7, render_dir, document_root=tmp_path)

    # The PNG is materialized into the single per-dict render dir (one storage covers
    # the whole project) and served relative to the document root.
    assert (render_dir / "page_7.png").is_file()
    assert url == "/data/local-files/?d=renders/Some-Dict/page_7.png"


def test_resolve_page_image_missing_returns_none(tmp_path):
    from setup_ner_projects import resolve_page_image

    dict_dir = tmp_path / "Some-Dict"
    (dict_dir / "Dictionary pages").mkdir(parents=True)
    assert (
        resolve_page_image(
            dict_dir, 7, tmp_path / "renders" / "Some-Dict", document_root=tmp_path
        )
        is None
    )
