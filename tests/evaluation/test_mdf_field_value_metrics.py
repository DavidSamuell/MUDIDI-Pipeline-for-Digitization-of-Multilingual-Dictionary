"""Tests for Stage 2 MDF field-value metrics and marker role mapping."""

from __future__ import annotations

from pathlib import Path

import yaml

from mudidi.evaluation.stage2.mdf_evaluator import MdfEvaluator
from mudidi.evaluation.stage2.mdf_marker_roles import (
    build_marker_language_map,
    marker_role_bucket,
)
from mudidi.schemas.dictionary_languages import (
    DictionaryLanguagesConfig,
    SourceLanguageConfig,
    TargetLanguageConfig,
)


def _write_mdf(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_mdf_evaluator_field_value_and_headword_metrics(tmp_path: Path) -> None:
    gold = tmp_path / "gold.mdf.txt"
    pred = tmp_path / "pred.mdf.txt"
    _write_mdf(
        gold,
        "\\lx lemma\n\\gn gloss one\n\n\\lx other\n\\gn gloss two\n",
    )
    _write_mdf(
        pred,
        "\\lx lemna\n\\gn gloss one\n\n\\lx other\n\\gn gloss two\n",
    )

    metrics = MdfEvaluator().evaluate(pred, gold, page_id="test/page")
    assert metrics.field_value_quality.matched_spans == 4
    assert metrics.field_value_quality.gcer > 0.0
    assert metrics.headword_quality.matched_spans == 2
    assert metrics.headword_quality.gcer > 0.0
    assert metrics.gloss_quality.gcer == 0.0


def test_chukchi_marker_language_map() -> None:
    config = DictionaryLanguagesConfig(
        layout="bilingual",
        source=SourceLanguageConfig(language="Chukchi"),
        targets=[TargetLanguageConfig(language="Russian")],
    )
    mapping = build_marker_language_map(config)
    assert mapping["lx"] == "Chukchi"
    assert mapping["gn"] == "Russian"
    assert marker_role_bucket("lx", mapping) == "source:chukchi"
    assert marker_role_bucket("gn", mapping) == "target:ru"


def test_na_trilingual_marker_language_map() -> None:
    config = DictionaryLanguagesConfig(
        layout="inline_trilingual",
        source=SourceLanguageConfig(language="Na"),
        targets=[
            TargetLanguageConfig(language="English"),
            TargetLanguageConfig(language="Chinese"),
            TargetLanguageConfig(language="French"),
        ],
    )
    mapping = build_marker_language_map(config)
    assert mapping["ge"] == "English"
    assert mapping["gn"] == "Chinese"
    assert mapping["gr"] == "French"
    assert marker_role_bucket("ge", mapping) == "target:en"
    assert marker_role_bucket("gn", mapping) == "target:zh"
    assert marker_role_bucket("gr", mapping) == "target:fr"


def test_custom_source_marker_uses_source_bucket() -> None:
    mapping = {
        "lx": "Chukchi",
        "gn": "Russian",
        "xy": "Chukchi",
    }
    assert marker_role_bucket("xy", mapping) == "source:chukchi"


def test_custom_target_marker_uses_target_bucket() -> None:
    mapping = {
        "lx": "Chukchi",
        "gn": "Russian",
        "zz": "Russian",
    }
    assert marker_role_bucket("zz", mapping) == "target:ru"


def test_per_language_metrics_with_dictionary_yaml(tmp_path: Path) -> None:
    lang_dir = tmp_path / "Chukchi-Russian"
    lang_dir.mkdir(parents=True)
    yaml_path = lang_dir / "dictionary_languages.yaml"
    yaml_path.write_text(
        yaml.safe_dump(
            {
                "layout": "bilingual",
                "source": {"language": "Chukchi"},
                "targets": [{"language": "Russian"}],
            }
        ),
        encoding="utf-8",
    )
    pred_root = tmp_path / "Chukchi-Russian" / "stage-2" / "exp" / "page_3"
    gold = tmp_path / "gold.mdf.txt"
    pred = pred_root / "page_3.mdf.txt"
    _write_mdf(gold, "\\lx a\n\\gn b\n")
    _write_mdf(pred, "\\lx a\n\\gn b\n")

    metrics = MdfEvaluator(dictionary_languages_path=yaml_path).evaluate(
        pred, gold, page_id="Chukchi-Russian/page_3"
    )
    assert "source:chukchi" in metrics.language_quality
    assert "target:ru" in metrics.language_quality
    assert metrics.language_quality["source:chukchi"].gcer == 0.0
    assert metrics.language_quality["target:ru"].gcer == 0.0
