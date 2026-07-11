from __future__ import annotations

import pytest

from mudidi.cli.main import build_parser


def test_public_command_tree_parses_production_run() -> None:
    parser = build_parser()
    args = parser.parse_args(
        [
            "run",
            "--pages",
            "dictionary.pdf",
            "--output-dir",
            "output",
            "--dry-run",
        ]
    )

    assert args.command == "run"
    assert args.pages == "dictionary.pdf"
    assert args.dry_run is True


def test_public_command_tree_parses_common_input_overrides() -> None:
    parser = build_parser()
    args = parser.parse_args(
        [
            "run",
            "--pages",
            "dictionary.pdf",
            "--output-dir",
            "output",
            "--intro",
            "introduction.pdf",
            "--intro-pages",
            "1-3",
            "--alphabet",
            "alphabet.txt",
            "--dictionary-languages",
            "languages.yaml",
        ]
    )

    assert args.intro == "introduction.pdf"
    assert args.intro_pages == "1-3"
    assert args.alphabet == "alphabet.txt"
    assert args.dictionary_languages == "languages.yaml"


def test_public_command_tree_parses_benchmark_samples_override() -> None:
    parser = build_parser()
    args = parser.parse_args(
        [
            "benchmark",
            "run",
            "--samples-dir",
            "samples",
            "--output-dir",
            "output",
        ]
    )

    assert args.samples_dir == "samples"


def test_public_command_tree_parses_benchmark_evaluation() -> None:
    parser = build_parser()
    args = parser.parse_args(
        [
            "benchmark",
            "evaluate",
            "stage1",
            "--config",
            "stage1-evaluation.yaml",
        ]
    )

    assert args.command == "benchmark"
    assert args.benchmark_command == "evaluate"
    assert args.evaluation_stage == "stage1"


def test_unknown_run_option_fails_immediately() -> None:
    parser = build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(["run", "--unknown-option"])
