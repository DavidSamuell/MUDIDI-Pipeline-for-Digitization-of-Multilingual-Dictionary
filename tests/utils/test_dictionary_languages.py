"""Tests for dictionary_languages loading and Pass 1 resolution."""

from __future__ import annotations

from pathlib import Path

import pytest

from mudidi.schemas.dictionary_languages import (
    DictionaryLanguagesConfig,
    SourceLanguageConfig,
    TargetLanguageConfig,
)
from mudidi.utils.dictionary_languages import (
    load_dictionary_languages_file,
    load_pass1_dictionary_languages,
)

_MINIMAL_YAML = """\
layout: inline_bilingual
source:
  language: Evenki
targets:
  - language: Russian
"""


def test_load_dictionary_languages_file_accepts_new_layout_names(tmp_path: Path) -> None:
    path = tmp_path / "dictionary_languages.yaml"
    path.write_text(
        """\
layout: column_bilingual
source:
  language: Evenki
  column_id: left
targets:
  - language: Russian
    column_id: right
""",
        encoding="utf-8",
    )
    config = load_dictionary_languages_file(path)
    assert config.layout == "column_bilingual"
    assert config.source.column_id == "left"


def test_load_dictionary_languages_file_accepts_custom_layout_string(tmp_path: Path) -> None:
    path = tmp_path / "dictionary_languages.yaml"
    path.write_text(_MINIMAL_YAML.replace("inline_bilingual", "bilingual"), encoding="utf-8")
    config = load_dictionary_languages_file(path)
    assert config.layout == "bilingual"


def test_load_pass1_inference_without_flag_returns_none(tmp_path: Path) -> None:
    entry_dir = tmp_path / "my-dictionary"
    entry_dir.mkdir()
    (entry_dir / "dictionary_languages.yaml").write_text(_MINIMAL_YAML, encoding="utf-8")

    config = load_pass1_dictionary_languages(
        dictionary_languages_path=None,
        entry_dir=entry_dir,
        metadata_csv_path=None,
        benchmark=False,
    )
    assert config is None


def test_load_pass1_inference_with_explicit_path(tmp_path: Path) -> None:
    yaml_path = tmp_path / "inputs" / "dictionary_languages.yaml"
    yaml_path.parent.mkdir(parents=True)
    yaml_path.write_text(_MINIMAL_YAML, encoding="utf-8")

    config = load_pass1_dictionary_languages(
        dictionary_languages_path=yaml_path,
        entry_dir=None,
        metadata_csv_path=None,
        benchmark=False,
    )
    assert isinstance(config, DictionaryLanguagesConfig)
    assert config.layout == "inline_bilingual"
    assert config.source.language == "Evenki"


def test_load_pass1_benchmark_auto_loads_entry_yaml(tmp_path: Path) -> None:
    entry_dir = tmp_path / "Evenki-Russian"
    entry_dir.mkdir()
    (entry_dir / "dictionary_languages.yaml").write_text(_MINIMAL_YAML, encoding="utf-8")

    config = load_pass1_dictionary_languages(
        dictionary_languages_path=None,
        entry_dir=entry_dir,
        metadata_csv_path=None,
        benchmark=True,
    )
    assert config is not None
    assert config.source.language == "Evenki"


def test_pass1_config_hint_empty_when_no_config() -> None:
    """When dictionary_languages is not loaded, Pass 1 should omit the hint."""
    config: DictionaryLanguagesConfig | None = None
    hint = "" if config is None else config.pass1_config_hint()
    assert hint == ""


def test_pass1_config_hint_includes_layout_and_languages() -> None:
    config = DictionaryLanguagesConfig(
        layout="inline_bilingual",
        source=SourceLanguageConfig(language="Evenki"),
        targets=[TargetLanguageConfig(language="Russian")],
    )
    hint = config.pass1_config_hint()
    assert "layout=inline_bilingual" in hint
    assert "source=Evenki" in hint
    assert "Russian" in hint


def test_pass1_config_hint_includes_layout_description() -> None:
    config = DictionaryLanguagesConfig(
        layout="column_bilingual",
        layout_description="Headwords center; glosses in the right column.",
        source=SourceLanguageConfig(language="Evenki"),
        targets=[TargetLanguageConfig(language="Russian")],
    )
    hint = config.pass1_config_hint()
    assert "Layout note:" in hint
    assert "right column" in hint


def test_load_custom_layout_and_layout_description(tmp_path: Path) -> None:
    path = tmp_path / "dictionary_languages.yaml"
    path.write_text(
        """\
layout: my_custom_layout
layout-description: Appendix uses a different grid than the main body.
source:
  language: Evenki
targets:
  - language: Russian
""",
        encoding="utf-8",
    )
    config = load_dictionary_languages_file(path)
    assert config.layout == "my_custom_layout"
    assert config.layout_description is not None
    assert "Appendix" in config.layout_description


def test_load_dictionary_languages_file_missing_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_dictionary_languages_file(tmp_path / "missing.yaml")
