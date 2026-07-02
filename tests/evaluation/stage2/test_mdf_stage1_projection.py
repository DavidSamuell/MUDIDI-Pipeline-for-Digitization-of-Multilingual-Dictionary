from pathlib import Path

from mudidi.evaluation.stage2.mdf_parser import parse_mdf
from mudidi.evaluation.stage2.mdf_stage1_projection import (
    build_stage1_projection,
    project_mdf_records,
)
from mudidi.schemas.language_span import LanguageSpan, PageLanguageMap, sha256_of


def _write_stage1_page(
    tmp_path: Path,
    raw_text: str,
    labeled_segments: list[tuple[str, str]],
) -> tuple[Path, Path]:
    page_dir = tmp_path / "page_1"
    page_dir.mkdir()
    gold_path = page_dir / "page_1_stage1_GOLD_flat.txt"
    map_path = page_dir / "page_1_lang.json"
    gold_path.write_text(raw_text, encoding="utf-8")

    spans: list[LanguageSpan] = []
    cursor = 0
    for text, language in labeled_segments:
        assert raw_text[cursor : cursor + len(text)] == text
        spans.append(
            LanguageSpan(start=cursor, end=cursor + len(text), language=language)
        )
        cursor += len(text)
    assert cursor == len(raw_text)

    PageLanguageMap(
        dictionary="Test-English",
        page=1,
        source_text_sha=sha256_of(raw_text),
        labeled_via="label-studio",
        spans=spans,
    ).save(map_path)
    return gold_path, map_path


def test_project_mdf_values_uses_field_value_not_marker(tmp_path: Path) -> None:
    raw = "<b>λόγος</b> word"
    gold_path, map_path = _write_stage1_page(
        tmp_path,
        raw,
        [
            ("<b>", "space"),
            ("λόγος", "Greek-Greek"),
            ("</b>", "space"),
            (" ", "space"),
            ("word", "English-Latin"),
        ],
    )
    projection = build_stage1_projection(gold_path, map_path)
    records = parse_mdf("\\lx λόγος\n\\ge word\n")

    results = project_mdf_records(
        dictionary="Test-English",
        page_id="page_1",
        records=records,
        projection=projection,
    )

    assert [r.marker for r in results] == ["lx", "ge"]
    assert [r.primary_language for r in results] == ["Greek-Greek", "English-Latin"]
    assert all("\\lx" not in r.normalized_value for r in results)


def test_project_mdf_values_can_use_ordered_token_provenance(tmp_path: Path) -> None:
    raw = "اکھیوُر / letter of an اچھُر alphabet"
    gold_path, map_path = _write_stage1_page(
        tmp_path,
        raw,
        [
            ("اکھیوُر", "Kashmiri-Arabic"),
            (" / ", "space"),
            ("letter of an", "English-Latin"),
            (" ", "space"),
            ("اچھُر", "Kashmiri-Arabic"),
            (" ", "space"),
            ("alphabet", "English-Latin"),
        ],
    )
    projection = build_stage1_projection(gold_path, map_path)
    records = parse_mdf("\\va اکھیوُر / اچھُر\n\\ge letter of an alphabet\n")

    results = project_mdf_records(
        dictionary="Kashmiri-English",
        page_id="page_1",
        records=records,
        projection=projection,
    )

    assert results[0].status == "token"
    assert results[0].primary_language == "Kashmiri-Arabic"
    assert results[1].status == "token"
    assert results[1].primary_language == "English-Latin"


def test_project_mdf_values_marks_sense_numbers_structural(tmp_path: Path) -> None:
    raw = "λόγος word"
    gold_path, map_path = _write_stage1_page(
        tmp_path,
        raw,
        [("λόγος", "Greek-Greek"), (" ", "space"), ("word", "English-Latin")],
    )
    projection = build_stage1_projection(gold_path, map_path)
    records = parse_mdf("\\sn 2\n")

    [result] = project_mdf_records(
        dictionary="Greek-English",
        page_id="page_1",
        records=records,
        projection=projection,
    )

    assert result.status == "structural"
    assert result.primary_language == "meta"
    assert not result.mapped
