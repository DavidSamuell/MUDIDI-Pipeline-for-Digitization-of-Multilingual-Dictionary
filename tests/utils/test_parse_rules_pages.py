"""Tests for parse-rules sample page resolution."""

from __future__ import annotations

from pathlib import Path

import pytest

from mudidi.utils.parse_rules_pages import (
    format_sample_pages_block,
    normalize_parse_rules_page_stems,
    select_parse_rules_sample_images,
)


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        (None, []),
        ("page_1", ["page_1"]),
        (["page_1", "page_2"], ["page_1", "page_2"]),
        (["page_1,page_2", "page_3"], ["page_1", "page_2", "page_3"]),
    ],
)
def test_normalize_parse_rules_page_stems(
    values: str | list[str] | None,
    expected: list[str],
) -> None:
    assert normalize_parse_rules_page_stems(values) == expected


def test_select_parse_rules_sample_images_defaults_to_first(tmp_path: Path) -> None:
    images = [tmp_path / "page_10.png", tmp_path / "page_2.png"]
    for path in images:
        path.write_bytes(b"x")
    selected = select_parse_rules_sample_images(images, [])
    assert selected == [images[0]]


def test_select_parse_rules_sample_images_missing_stem(tmp_path: Path) -> None:
    image = tmp_path / "page_1.png"
    image.write_bytes(b"x")
    with pytest.raises(ValueError, match="not found"):
        select_parse_rules_sample_images([image], ["page_99"])


def test_format_sample_pages_block() -> None:
    block = format_sample_pages_block(
        [
            ("page_1", "alpha line"),
            ("page_50", "beta line"),
        ]
    )
    assert '<sample_transcription page="page_1">' in block
    assert "alpha line" in block
    assert '<sample_transcription page="page_50">' in block
