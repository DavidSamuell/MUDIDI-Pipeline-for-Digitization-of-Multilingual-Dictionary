"""Unit tests for the Label Studio -> annotation/outputs sync (no live LLM, no network)."""

from __future__ import annotations

from label_studio_ner import page_map_to_ls_task  # noqa: E402  (flat import; see conftest.py)
from span_schema import SPACE, LanguageSpan, PageLanguageMap, sha256_of  # noqa: E402
from sync_from_label_studio import page_map_from_task, write_synced_map  # noqa: E402

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
            LanguageSpan(start=8, end=18, language="English"),
        ],
    )


def _annotate(task: dict, start: int, end: int, label: str) -> dict:
    """Attach a single submitted human annotation region to a task."""
    task["annotations"] = [
        {
            "result": [
                {
                    "from_name": "label",
                    "to_name": "text",
                    "type": "labels",
                    "value": {
                        "start": start,
                        "end": end,
                        "text": SNIPPET[start:end],
                        "labels": [label],
                    },
                }
            ]
        }
    ]
    return task


def test_page_map_from_task_uses_submitted_annotation():
    task = page_map_to_ls_task(_canala_map(), SNIPPET)
    # Human relabels the first headword from Canala -> English.
    _annotate(task, 0, 7, "English")

    name, page, new_map = page_map_from_task(task)

    assert name == "Canala-English"
    assert page == 12
    assert new_map.language_char_map(SNIPPET)[0] == "English"  # correction applied
    assert new_map.labeled_via == "label-studio"  # provenance flips to human review


def test_page_map_from_task_none_without_annotation():
    # Predictions only (no human submission) -> nothing to sync.
    task = page_map_to_ls_task(_canala_map(), SNIPPET)
    assert page_map_from_task(task) is None


def test_page_map_from_task_none_when_annotations_are_id_stubs():
    # Label Studio export may list annotation IDs without embedding the objects.
    task = page_map_to_ls_task(_canala_map(), SNIPPET)
    task["annotations"] = [259]
    assert page_map_from_task(task) is None


def test_write_synced_map_new_then_unchanged(tmp_path):
    page_map = _canala_map()
    # First write creates the file.
    assert write_synced_map(tmp_path, "Canala-English", 12, page_map, dry_run=False) == "new"
    out = tmp_path / "Canala-English" / "page_12_lang.json"
    assert out.is_file()
    # Re-running with the same map is a no-op.
    assert (
        write_synced_map(tmp_path, "Canala-English", 12, page_map, dry_run=False)
        == "unchanged"
    )


def test_write_synced_map_dry_run_writes_nothing(tmp_path):
    page_map = _canala_map()
    assert write_synced_map(tmp_path, "Canala-English", 12, page_map, dry_run=True) == "dry-run"
    assert not (tmp_path / "Canala-English" / "page_12_lang.json").exists()
