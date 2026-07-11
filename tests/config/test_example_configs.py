from __future__ import annotations

from pathlib import Path

import pytest

from mudidi.config.yaml_config import load_yaml_config


ROOT = Path(__file__).resolve().parents[2]
EXAMPLE_CONFIGS = sorted((ROOT / "examples" / "configs").rglob("*.yaml"))


def test_canonical_example_configs_exist() -> None:
    names = {path.name for path in EXAMPLE_CONFIGS}
    assert names >= {
        "directory-inference.yaml",
        "pdf-inference.yaml",
        "stage1-benchmark.yaml",
        "stage2-e2e-benchmark.yaml",
        "stage1-evaluation.yaml",
        "stage2-evaluation.yaml",
    }


@pytest.mark.parametrize("path", EXAMPLE_CONFIGS, ids=lambda path: path.name)
def test_canonical_example_config_validates(path: Path) -> None:
    config = load_yaml_config(path)
    assert config.version == 1
