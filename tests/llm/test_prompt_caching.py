"""Tests for prompt caching and media-reference message assembly."""

from __future__ import annotations

from pathlib import Path

from mudidi.extraction.llm_two_stage import _sanitize_messages
from mudidi.llm.client import _extract_usage, supports_prompt_cache_key
from mudidi.llm.pass_2 import build_direct_mdf_messages
from mudidi.schemas.field_cheatsheet import DictionaryMarkerCheatsheet, MarkerLine
from mudidi.utils.page_context import NeighborPage, PageContext
from mudidi.utils.image import file_content_part, is_remote_file_reference


def _field_map() -> DictionaryMarkerCheatsheet:
    return DictionaryMarkerCheatsheet(
        dictionary_name="Test Dictionary",
        markers=[
            MarkerLine(marker="lx", description="headword"),
            MarkerLine(marker="gn", description="gloss"),
        ],
        rules=["Use one \\lx per main entry."],
    )


def test_pass2_places_parse_rules_in_cacheable_static_message(tmp_path: Path) -> None:
    page = tmp_path / "page_1.png"
    page.write_bytes(b"fake-image")

    messages = build_direct_mdf_messages(
        transcription="this is page-specific OCR text",
        image_path=str(page),
        field_map=_field_map(),
        model="gemini/gemini-3.1-pro-preview",
        prompt_cache="auto",
        media_reference="inline",
        mode="benchmark",
    )

    assert len(messages) == 3
    assert messages[1]["role"] == "user"
    static_content = messages[1]["content"]
    assert static_content[-1]["cache_control"] == {"type": "ephemeral"}
    assert "MDF markers for Test Dictionary" in static_content[0]["text"]
    assert "\\lx   headword" in static_content[0]["text"]
    assert "this is page-specific OCR text" not in static_content[0]["text"]

    dynamic_content = messages[2]["content"]
    assert "this is page-specific OCR text" in dynamic_content[0]["text"]
    assert dynamic_content[1]["type"] == "image_url"


def test_pass2_prompt_cache_off_omits_cache_control(tmp_path: Path) -> None:
    page = tmp_path / "page_1.png"
    page.write_bytes(b"fake-image")

    messages = build_direct_mdf_messages(
        transcription="this is page-specific OCR text",
        image_path=str(page),
        field_map=_field_map(),
        model="gemini/gemini-3.1-pro-preview",
        prompt_cache="off",
        media_reference="inline",
        mode="benchmark",
    )

    assert "cache_control" not in messages[1]["content"][-1]


def test_pass2_inference_context_stays_dynamic(tmp_path: Path) -> None:
    page = tmp_path / "page_2.png"
    previous = tmp_path / "page_1.png"
    next_page = tmp_path / "page_3.png"
    for path in (page, previous, next_page):
        path.write_bytes(b"fake-image")
    page_context = PageContext(
        previous=NeighborPage("page_1", previous, "previous transcript"),
        next=NeighborPage("page_3", next_page, "next transcript"),
        current_stem="page_2",
    )

    messages = build_direct_mdf_messages(
        transcription="current transcript",
        image_path=str(page),
        field_map=_field_map(),
        model="gemini/gemini-3.1-pro-preview",
        prompt_cache="auto",
        media_reference="inline",
        mode="inference",
        page_context=page_context,
    )

    static_text = messages[1]["content"][0]["text"]
    dynamic_text = messages[2]["content"][0]["text"]
    assert "MDF markers for Test Dictionary" in static_text
    assert "current transcript" not in static_text
    assert "<current_page>" not in static_text
    assert "current transcript" in dynamic_text
    assert "<current_page>" in dynamic_text
    assert "previous transcript" in dynamic_text
    assert "next transcript" in dynamic_text


def test_file_content_part_uses_uri_for_remote_pdf() -> None:
    url = "https://example.com/toolbox.pdf"

    part = file_content_part(
        url,
        mime_type="application/pdf",
        media_reference="file-uri",
    )

    assert is_remote_file_reference(url)
    assert part == {
        "type": "file",
        "file": {"file_id": url, "format": "application/pdf"},
    }


def test_file_content_part_falls_back_to_file_data_for_local_pdf(tmp_path: Path) -> None:
    pdf = tmp_path / "toolbox.pdf"
    pdf.write_bytes(b"%PDF-1.7 fake")

    part = file_content_part(
        str(pdf),
        mime_type="application/pdf",
        media_reference="file-uri",
    )

    assert part["type"] == "file"
    assert part["file"]["format"] == "application/pdf"
    assert part["file"]["file_data"].startswith("data:application/pdf;base64,")


def test_extract_usage_includes_prompt_cache_metrics() -> None:
    class Usage:
        prompt_tokens = 100
        completion_tokens = 10
        total_tokens = 110
        prompt_tokens_details = {"cached_tokens": 80}
        cache_creation_input_tokens = 0
        cache_read_input_tokens = 80

    class Response:
        usage = Usage()

    usage = _extract_usage("openai/gpt-5.5", Response())

    assert usage["cached_tokens"] == 80
    assert usage["cache_creation_input_tokens"] == 0
    assert usage["cache_read_input_tokens"] == 80


def test_prompt_cache_key_support_is_direct_openai_only() -> None:
    assert supports_prompt_cache_key("openai/gpt-5.5")
    assert supports_prompt_cache_key("gpt-5.5")
    assert not supports_prompt_cache_key("gemini/gemini-3.1-pro-preview")
    assert not supports_prompt_cache_key("anthropic/claude-opus-4-5")


def test_sanitize_messages_redacts_file_data_payload() -> None:
    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "file",
                    "file": {
                        "file_data": "data:application/pdf;base64,abcdef",
                        "format": "application/pdf",
                    },
                }
            ],
        }
    ]

    sanitized = _sanitize_messages(messages)

    assert sanitized[0]["content"][0]["file"]["file_data"] == (
        "data:application/pdf;base64,<6 chars omitted>"
    )
    assert messages[0]["content"][0]["file"]["file_data"].endswith("abcdef")
