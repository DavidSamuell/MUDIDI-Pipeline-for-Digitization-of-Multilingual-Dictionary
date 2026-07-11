from __future__ import annotations

import argparse
from pathlib import Path

from mudidi.cli.run import (
    execution_namespace_from_config,
    resolve_extraction_config,
    run_resolved_command,
)
from mudidi.config.yaml_config import InferenceConfig


def test_resolve_minimal_cli_inference_uses_defaults(tmp_path: Path) -> None:
    args = argparse.Namespace(
        pages=str(tmp_path / "pages"),
        output_dir=str(tmp_path / "output"),
        dry_run=True,
    )

    config = resolve_extraction_config(args, kind="inference")

    assert isinstance(config, InferenceConfig)
    assert config.pipeline.stage1_mode == "flat"
    assert config.input.pages == tmp_path / "pages"
    assert config.output.directory == tmp_path / "output"


def test_cli_values_override_yaml_without_overwriting_omitted_fields(
    tmp_path: Path,
) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(
        """
version: 1
kind: inference
input:
  pages: original-pages
output:
  directory: original-output
models:
  default: provider/yaml
runtime:
  batch_size: 4
""".strip(),
        encoding="utf-8",
    )
    args = argparse.Namespace(
        config=path,
        pages=str(tmp_path / "override-pages"),
        model="provider/cli",
        dry_run=True,
    )

    config = resolve_extraction_config(args, kind="inference")

    assert config.input.pages == tmp_path / "override-pages"
    assert config.models.default == "provider/cli"
    assert config.runtime.batch_size == 4
    assert config.output.directory == tmp_path / "original-output"


def test_execution_namespace_maps_advanced_yaml_settings(tmp_path: Path) -> None:
    config = InferenceConfig.model_validate(
        {
            "kind": "inference",
            "input": {"pages": tmp_path / "pages"},
            "output": {"directory": tmp_path / "output"},
            "pipeline": {"stage": "1", "stage1_typography": True},
            "models": {"default": "provider/default", "stage1": "provider/s1"},
            "agentic": {"stage1": True, "max_iterations": 3},
            "runtime": {"batch_size": 2, "overwrite": True},
        }
    )

    namespace = execution_namespace_from_config(config)

    assert namespace.input_image == str(tmp_path / "pages")
    assert namespace.output == str(tmp_path / "output")
    assert namespace.stage1_typography is True
    assert namespace.stage1_agentic is True
    assert namespace.agentic_max_iterations == 3
    assert namespace.batch_size == 2
    assert namespace.overwrite is True


def test_dry_run_does_not_invoke_extraction(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    args = argparse.Namespace(
        pages=str(tmp_path / "pages"),
        output_dir=str(tmp_path / "output"),
        dry_run=True,
    )
    monkeypatch.setattr(
        "mudidi.cli.extract.main",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("must not execute")),
    )

    assert run_resolved_command(args, parser=argparse.ArgumentParser(), kind="inference") == 0
    output = capsys.readouterr().out
    assert '"kind": "inference"' in output
    assert '"stage1_mode": "flat"' in output

