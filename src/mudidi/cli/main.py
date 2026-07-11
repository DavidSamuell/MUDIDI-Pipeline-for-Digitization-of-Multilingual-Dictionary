"""MUDIDI command-line entry point."""

from __future__ import annotations

import argparse
from pathlib import Path


def _add_sparse_run_arguments(parser: argparse.ArgumentParser) -> None:
    """Register common YAML overrides without implicit defaults."""
    parser.add_argument("--config", type=Path, default=argparse.SUPPRESS)
    parser.add_argument("--pages", default=argparse.SUPPRESS)
    parser.add_argument("--dict-pages", dest="dict_pages", default=argparse.SUPPRESS)
    parser.add_argument("--output-dir", dest="output_dir", default=argparse.SUPPRESS)
    parser.add_argument(
        "--stage",
        choices=["1", "2", "all", "2-pass-1", "2-pass-2"],
        default=argparse.SUPPRESS,
    )
    parser.add_argument("--model", default=argparse.SUPPRESS)
    parser.add_argument("--stage-1-model", dest="stage_1_model", default=argparse.SUPPRESS)
    parser.add_argument(
        "--stage-2-pass-1-model",
        dest="stage_2_pass_1_model",
        default=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--stage-2-pass-2-model",
        dest="stage_2_pass_2_model",
        default=argparse.SUPPRESS,
    )
    parser.add_argument("--overwrite", action="store_true", default=argparse.SUPPRESS)
    parser.add_argument("--dry-run", action="store_true", default=False)


def _add_sparse_evaluation_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", type=Path, default=argparse.SUPPRESS)
    parser.add_argument("--predicted", "-p", default=argparse.SUPPRESS)
    parser.add_argument("--gold", "-g", default=argparse.SUPPRESS)
    parser.add_argument("--dataset-dir", default=argparse.SUPPRESS)
    parser.add_argument("--pred-root", default=argparse.SUPPRESS)
    parser.add_argument("--output-dir", "-o", default=argparse.SUPPRESS)
    parser.add_argument("--languages", nargs="+", default=argparse.SUPPRESS)
    parser.add_argument("--experiment-name", action="append", default=argparse.SUPPRESS)


def build_parser() -> argparse.ArgumentParser:
    """Build the complete public MUDIDI command parser."""
    parser = argparse.ArgumentParser(
        prog="mudidi",
        description="Dictionary OCR and MDF extraction (inference and benchmark modes).",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run production inference.")
    _add_sparse_run_arguments(run_parser)
    run_parser.set_defaults(_handler=_run_inference)

    benchmark = subparsers.add_parser("benchmark", help="Benchmark workflows.")
    benchmark_sub = benchmark.add_subparsers(dest="benchmark_command", required=True)
    benchmark_run = benchmark_sub.add_parser("run", help="Run benchmark extraction.")
    _add_sparse_run_arguments(benchmark_run)
    benchmark_run.add_argument("--dataset-dir", default=argparse.SUPPRESS)
    benchmark_run.add_argument("--languages", nargs="+", default=argparse.SUPPRESS)
    benchmark_run.add_argument("--experiment-name", default=argparse.SUPPRESS)
    benchmark_run.set_defaults(_handler=_run_benchmark)

    evaluate = benchmark_sub.add_parser("evaluate", help="Evaluate predictions.")
    evaluate_sub = evaluate.add_subparsers(dest="evaluation_stage", required=True)
    for stage in ("stage1", "stage2"):
        stage_parser = evaluate_sub.add_parser(stage)
        _add_sparse_evaluation_arguments(stage_parser)
        stage_parser.set_defaults(_handler=_run_evaluation)

    config = subparsers.add_parser("config", help="Configuration utilities.")
    config_sub = config.add_subparsers(dest="config_command", required=True)
    validate = config_sub.add_parser("validate", help="Validate a YAML config.")
    validate.add_argument("config", type=Path)
    validate.set_defaults(_handler=_validate_config)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Dispatch one fully parsed MUDIDI command."""
    parser = build_parser()
    args = parser.parse_args(argv)
    return args._handler(args, parser)


def _run_inference(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    from mudidi.cli.run import run_resolved_command

    return run_resolved_command(args, parser=parser, kind="inference")


def _run_benchmark(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    from mudidi.cli.run import run_resolved_command

    return run_resolved_command(args, parser=parser, kind="benchmark_run")


def _run_evaluation(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    from mudidi.cli.run import run_evaluation_command

    kind = f"{args.evaluation_stage}_evaluation"
    return run_evaluation_command(args, parser=parser, kind=kind)


def _validate_config(args: argparse.Namespace, _parser: argparse.ArgumentParser) -> int:
    from mudidi.config.yaml_config import load_yaml_config

    config = load_yaml_config(args.config)
    print(f"Valid MUDIDI config: {config.kind} (version {config.version})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
