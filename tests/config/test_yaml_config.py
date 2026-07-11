from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from mudidi.config.yaml_config import (
    BenchmarkRunConfig,
    InferenceConfig,
    load_yaml_config,
    merge_explicit_overrides,
)


def test_load_inference_config_resolves_paths_from_config_file(tmp_path: Path) -> None:
    config_dir = tmp_path / "configs"
    config_dir.mkdir()
    path = config_dir / "inference.yaml"
    path.write_text(
        """
version: 1
kind: inference
input:
  pages: ../inputs/dictionary.pdf
output:
  directory: ../outputs/run
pipeline:
  stage: all
""".strip(),
        encoding="utf-8",
    )

    config = load_yaml_config(path, expected_kind="inference")

    assert isinstance(config, InferenceConfig)
    assert config.input.pages == (config_dir / "../inputs/dictionary.pdf").resolve()
    assert config.output.directory == (config_dir / "../outputs/run").resolve()
    assert config.pipeline.stage1_mode == "flat"


def test_yaml_config_rejects_unknown_fields(tmp_path: Path) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text(
        """
version: 1
kind: inference
input:
  pages: dictionary.pdf
output:
  directory: output
surprise: true
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ValidationError, match="surprise"):
        load_yaml_config(path)


def test_yaml_config_rejects_command_kind_mismatch(tmp_path: Path) -> None:
    path = tmp_path / "benchmark.yaml"
    path.write_text(
        """
version: 1
kind: benchmark_run
input:
  dataset_dir: dataset/MUDIDI/dictionaries
output:
  directory: outputs/benchmark
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="requires kind 'inference'"):
        load_yaml_config(path, expected_kind="inference")


def test_explicit_cli_overrides_replace_yaml_values() -> None:
    config = BenchmarkRunConfig.model_validate(
        {
            "version": 1,
            "kind": "benchmark_run",
            "input": {
                "dataset_dir": "/dataset",
                "languages": ["Evenki-Russian", "Chukchi-Russian"],
            },
            "output": {"directory": "/outputs"},
        }
    )

    merged = merge_explicit_overrides(
        config,
        {
            "input.languages": ["Yiddish-English"],
            "models.default": "provider/model",
        },
    )

    assert merged.input.languages == ["Yiddish-English"]
    assert merged.models.default == "provider/model"

