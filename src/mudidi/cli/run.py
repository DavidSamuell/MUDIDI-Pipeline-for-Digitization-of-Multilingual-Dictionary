"""``mudidi run`` command — inference and benchmark extraction."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from mudidi.config.run_config import RUN_STAGE_CHOICES, stage_from_cli
from mudidi.llm.prompt_store import configure_prompts, default_prompts_path
from mudidi.cli.model_args import forward_model_argv, register_model_arguments
from mudidi.utils.pdf_split import parse_page_spec


def register_run_arguments(parser: argparse.ArgumentParser) -> None:
    """Register arguments for ``mudidi run``."""
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--benchmark",
        action="store_true",
        help="Benchmark mode: samples tree layout, gold defaults, no neighbor context.",
    )

    parser.add_argument(
        "--pages",
        dest="pages",
        help="Snippets directory or single source PDF (requires --dict-pages). "
        "Alias for --input-image.",
    )
    parser.add_argument(
        "--dict-pages",
        dest="dict_pages",
        help="When --pages is a PDF: 1-based dictionary pages to process "
        "(e.g. '1-10' or '1,3,5'). Required for PDF input; uses pdftk.",
    )
    parser.add_argument(
        "--input-image",
        dest="input_image",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--output-dir",
        dest="output_dir",
        help="Output directory. Inference: stage-1/ and stage-2/ subdirs. "
        "Alias for --output.",
    )
    parser.add_argument(
        "-o",
        "--output",
        dest="output",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--samples-dir",
        dest="samples_dir",
        help="Benchmark: parent directory of per-language sample folders.",
    )
    parser.add_argument(
        "--languages",
        nargs="+",
        default=None,
        help="Benchmark: subset of language folders under --samples-dir.",
    )
    parser.add_argument(
        "--intro",
        help="Introduction directory or text/image file. Not used when --pages is a PDF "
        "(use --intro-pages instead).",
    )
    parser.add_argument(
        "--intro-pages",
        dest="intro_pages",
        help="When --pages is a PDF: 1-based introduction pages from that same PDF "
        "(e.g. '1-5'). Optional; uses pdftk.",
    )
    parser.add_argument(
        "--alphabet",
        help="Path to alphabet list (.txt or markdown) or alphabet image.",
    )
    parser.add_argument(
        "--ocr-text",
        dest="ocr_text",
        help="Directory of OCR hint files keyed by page stem (off by default).",
    )
    parser.add_argument(
        "--stage",
        choices=list(RUN_STAGE_CHOICES),
        default="all",
        help="Run Stage 1 only, Stage 2 (Pass 1 + Pass 2), both stages (all), "
        "Stage 2 Pass 1 only (2-pass-1), or Stage 2 Pass 2 only "
        "(2-pass-2; requires existing parse-rules.json). Default: all.",
    )
    parser.add_argument(
        "--stage1-source",
        choices=["gold", "predictions"],
        default=None,
        dest="stage1_source",
        help="Stage 2 transcript source. Benchmark default: gold. Inference: predictions.",
    )
    parser.add_argument(
        "--parse-rules-page",
        action="append",
        dest="parse_rules_pages",
        help="1-based page number(s) for Stage 2 Pass 1 (same syntax as --dict-pages: "
        "e.g. '1', '1-4', '50,200'). Repeat the flag or comma-separate. "
        "Default: first page. Two+ pages use multi-sample Pass 1.",
    )
    parser.add_argument(
        "--parse-rules-file",
        type=str,
        dest="parse_rules_file",
        help="Load parse-rules.json from PATH; skip Pass 1 LLM discovery. "
        "Always reads PATH (overrides any cached parse-rules.json in --output-dir).",
    )
    parser.add_argument(
        "--dictionary-languages",
        type=str,
        dest="dictionary_languages",
        default=None,
        help="Optional path to dictionary_languages.yaml for Stage 2 Pass 1 "
        "(layout and source/target language hint). Inference: opt-in only. "
        "Benchmark: auto-loads per-entry YAML when omitted.",
    )
    parser.add_argument(
        "--prompt-cache",
        choices=["auto", "off"],
        default="auto",
        dest="prompt_cache",
        help="Prompt caching mode. auto uses litellm/provider prompt caching when "
        "supported; off sends uncached prompts (default: auto).",
    )
    parser.add_argument(
        "--media-reference",
        choices=["auto", "inline", "file-uri"],
        default="auto",
        dest="media_reference",
        help="How to attach reusable media such as toolbox PDFs. auto uses file "
        "parts/URIs when supported and falls back to inline data; inline always "
        "uses base64 data; file-uri prefers URI/file parts with inline fallback.",
    )
    parser.add_argument(
        "--prompt-cache-key",
        default=None,
        dest="prompt_cache_key",
        help="Optional stable cache key prefix for providers that accept cache "
        "routing hints (for example OpenAI prompt_cache_key).",
    )
    parser.add_argument(
        "--no-stage1-typography",
        action="store_true",
        dest="no_stage1_typography",
        help="Inference only: omit bold/italic <b>/<i> markup instructions from "
        "Stage 1 prompts and structured output schema (plain text transcripts).",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=1,
        dest="batch_size",
        help="Concurrent page workers for two_stage LLM steps (default: 1). "
        "Thread pool over litellm.completion calls (no litellm batch API flag).",
    )
    parser.add_argument(
        "--prompts-file",
        type=str,
        default=None,
        dest="prompts_file",
        help="Path to PROMPT.json (default: bundled assets).",
    )
    register_model_arguments(parser)


def _validate_pdf_page_args(run_args: argparse.Namespace) -> None:
    """Validate PDF page specs before delegating to the extract driver."""
    pages = run_args.pages or run_args.input_image
    pages_path = Path(pages) if pages else None
    is_source_pdf = bool(
        pages_path and pages_path.is_file() and pages_path.suffix.lower() == ".pdf"
    )

    if is_source_pdf:
        if not run_args.dict_pages:
            raise SystemExit(
                "--dict-pages is required when --pages is a PDF "
                "(e.g. '1-10' or '1,3,5')"
            )
        try:
            if not parse_page_spec(run_args.dict_pages):
                raise SystemExit("--dict-pages must list at least one page")
        except ValueError as exc:
            raise SystemExit(f"Invalid --dict-pages: {exc}") from exc
        if run_args.intro:
            raise SystemExit(
                "--intro cannot be used when --pages is a PDF; "
                "pass --intro-pages to select pages from the same PDF"
            )
        if run_args.intro_pages:
            try:
                if not parse_page_spec(run_args.intro_pages):
                    raise SystemExit("--intro-pages must list at least one page")
            except ValueError as exc:
                raise SystemExit(f"Invalid --intro-pages: {exc}") from exc
    else:
        if run_args.dict_pages:
            raise SystemExit(
                "--dict-pages is only valid when --pages is a single PDF file"
            )
        if run_args.intro_pages:
            raise SystemExit(
                "--intro-pages is only valid when --pages is a single PDF file"
            )


def _merge_extract_args(_run_args: argparse.Namespace, remaining: Sequence[str]) -> list[str]:
    """Forward unhandled flags to the legacy extract driver."""
    return list(remaining)


def run_from_args(run_args: argparse.Namespace, remaining: Sequence[str]) -> int:
    """Execute ``mudidi run`` by delegating to the extract driver."""
    pages = run_args.pages or run_args.input_image
    output = run_args.output_dir or run_args.output

    if run_args.benchmark:
        if not run_args.samples_dir and not pages:
            raise SystemExit("--benchmark requires --samples-dir or --pages with sample layout.")
    elif not pages or not output:
        raise SystemExit("Inference mode requires --pages and --output-dir.")

    _validate_pdf_page_args(run_args)

    if run_args.prompts_file:
        configure_prompts(run_args.prompts_file)
    else:
        configure_prompts(default_prompts_path())

    import sys

    from mudidi.cli import extract as extract_module

    argv = ["mudidi-run"]
    if run_args.benchmark:
        argv.append("--benchmark")
    if pages:
        argv.extend(["--pages", pages, "--input-image", pages])
    if output:
        argv.extend(["--output-dir", output, "--output", output])
    if run_args.samples_dir:
        argv.extend(["--samples-dir", run_args.samples_dir])
    if run_args.languages:
        argv.extend(["--languages", *run_args.languages])
    if run_args.intro:
        argv.extend(["--intro", run_args.intro])
    if run_args.intro_pages:
        argv.extend(["--intro-pages", run_args.intro_pages])
    if run_args.dict_pages:
        argv.extend(["--dict-pages", run_args.dict_pages])
    if run_args.alphabet:
        argv.extend(["--alphabet", run_args.alphabet])
    if run_args.ocr_text:
        argv.extend(["--ocr-text", run_args.ocr_text])
    stage = stage_from_cli(run_args.stage)
    argv.extend(["--stage", stage])
    if run_args.stage1_source:
        argv.extend(["--stage1-source", run_args.stage1_source])
    if run_args.parse_rules_pages:
        for stem in run_args.parse_rules_pages:
            argv.extend(["--parse-rules-page", stem])
    if run_args.parse_rules_file:
        argv.extend(["--parse-rules-file", run_args.parse_rules_file])
    if run_args.dictionary_languages:
        argv.extend(["--dictionary-languages", run_args.dictionary_languages])
    argv.extend(["--prompt-cache", run_args.prompt_cache])
    argv.extend(["--media-reference", run_args.media_reference])
    if run_args.prompt_cache_key:
        argv.extend(["--prompt-cache-key", run_args.prompt_cache_key])
    if run_args.no_stage1_typography:
        argv.append("--no-stage1-typography")
    if getattr(run_args, "batch_size", 1) != 1:
        argv.extend(["--batch-size", str(run_args.batch_size)])
    if run_args.prompts_file:
        argv.extend(["--prompts-file", run_args.prompts_file])
    forward_model_argv(argv, run_args)
    argv.extend(_merge_extract_args(run_args, remaining))

    old_argv = sys.argv
    try:
        sys.argv = argv
        return extract_module.main()
    finally:
        sys.argv = old_argv
