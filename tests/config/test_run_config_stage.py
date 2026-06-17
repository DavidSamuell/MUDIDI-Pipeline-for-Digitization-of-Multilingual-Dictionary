"""Tests for --stage CLI mapping and stage helper predicates."""

from __future__ import annotations

import pytest

from mudidi.config.run_config import (
    runs_stage1,
    runs_stage2_any,
    runs_stage2_pass1,
    runs_stage2_pass2,
    stage_from_cli,
)


@pytest.mark.parametrize(
    ("cli_value", "internal"),
    [
        ("1", "1"),
        ("2", "2"),
        ("all", "both"),
        ("both", "both"),
        ("2-pass-1", "2-pass-1"),
        ("2-pass-2", "2-pass-2"),
    ],
)
def test_stage_from_cli(cli_value: str, internal: str) -> None:
    assert stage_from_cli(cli_value) == internal


def test_stage_from_cli_rejects_unknown() -> None:
    with pytest.raises(ValueError, match="Invalid stage"):
        stage_from_cli("stage-3")


@pytest.mark.parametrize(
    ("stage", "expected"),
    [
        ("1", True),
        ("both", True),
        ("2", False),
        ("2-pass-1", False),
        ("2-pass-2", False),
    ],
)
def test_runs_stage1(stage: str, expected: bool) -> None:
    assert runs_stage1(stage) is expected


@pytest.mark.parametrize(
    ("stage", "pass1", "pass2"),
    [
        ("1", False, False),
        ("both", True, True),
        ("2", True, True),
        ("2-pass-1", True, False),
        ("2-pass-2", False, True),
    ],
)
def test_runs_stage2_helpers(stage: str, pass1: bool, pass2: bool) -> None:
    assert runs_stage2_any(stage) is (pass1 or pass2)
    assert runs_stage2_pass1(stage) is pass1
    assert runs_stage2_pass2(stage) is pass2
