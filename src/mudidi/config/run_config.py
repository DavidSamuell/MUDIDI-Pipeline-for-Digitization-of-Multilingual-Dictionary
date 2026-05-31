"""Pydantic run configuration for benchmark vs inference modes."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator

PromptMode = Literal["benchmark", "inference"]
RunStage = Literal["1", "2", "all"]
Stage1Source = Literal["gold", "predictions"]


def stage_from_cli(value: str) -> Literal["1", "2", "both"]:
    """Map CLI ``--stage`` value to internal run stage."""
    normalized = value.strip().lower()
    if normalized == "all":
        return "both"
    if normalized in ("1", "2", "both"):
        return normalized  # type: ignore[return-value]
    raise ValueError(f"Invalid stage: {value!r}. Use 1, 2, or all.")


class RunConfig(BaseModel):
    """Normalized configuration for a ``mudidi run`` invocation."""

    benchmark: bool = False
    pages_dir: Path
    output_dir: Path
    stage: RunStage = "all"
    prompt_mode: PromptMode = "inference"
    stage1_source: Stage1Source = "predictions"
    experiment_name: str = "default"
    stage2_experiment_name: str | None = None
    stage1_output_subdir: str = "stage-1"
    samples_dir: Path | None = None
    languages: list[str] | None = None
    intro_dir: Path | None = None
    alphabet_path: Path | None = None
    ocr_text_dir: Path | None = None
    parse_rules_page_stem: str | None = None

    model_config = {"arbitrary_types_allowed": True}

    @model_validator(mode="after")
    def _apply_mode_defaults(self) -> RunConfig:
        if self.benchmark:
            object.__setattr__(self, "prompt_mode", "benchmark")
        else:
            object.__setattr__(self, "prompt_mode", "inference")
            if self.stage in ("2", "all") and self.stage1_source == "gold":
                object.__setattr__(self, "stage1_source", "predictions")
        if self.stage2_experiment_name is None:
            object.__setattr__(self, "stage2_experiment_name", self.experiment_name)
        return self

    @property
    def internal_stage(self) -> Literal["1", "2", "both"]:
        return stage_from_cli(self.stage)

    @classmethod
    def from_namespace(cls, args: object) -> RunConfig:
        """Build from an argparse namespace produced by ``mudidi.cli.run``."""
        benchmark = bool(getattr(args, "benchmark", False))
        pages = getattr(args, "pages", None) or getattr(args, "input_image", None)
        output = getattr(args, "output_dir", None) or getattr(args, "output", None)
        if not pages or not output:
            raise ValueError("--pages and --output-dir are required.")
        stage_raw = getattr(args, "stage", "all")
        stage: RunStage = stage_raw if stage_raw in ("1", "2", "all") else "all"
        stage1_source = getattr(args, "stage1_source", None)
        if stage1_source is None:
            stage1_source = "gold" if benchmark else "predictions"
        intro = getattr(args, "intro", None)
        alphabet = getattr(args, "alphabet", None)
        ocr = getattr(args, "ocr_text", None)
        return cls(
            benchmark=benchmark,
            pages_dir=Path(pages),
            output_dir=Path(output),
            stage=stage,
            stage1_source=stage1_source,  # type: ignore[arg-type]
            experiment_name=getattr(args, "experiment_name", "default"),
            stage2_experiment_name=getattr(args, "stage2_experiment_name", None),
            stage1_output_subdir=getattr(args, "stage1_output_subdir", "stage-1"),
            samples_dir=Path(args.samples_dir) if getattr(args, "samples_dir", None) else None,
            languages=getattr(args, "languages", None),
            intro_dir=Path(intro) if intro else None,
            alphabet_path=Path(alphabet) if alphabet else None,
            ocr_text_dir=Path(ocr) if ocr else None,
            parse_rules_page_stem=getattr(
                args, "parse_rules_page", getattr(args, "cheatsheet_page", None)
            ),
        )

    def apply_to_namespace(self, args: object) -> None:
        """Copy normalized fields onto an argparse namespace for legacy extract code."""
        setattr(args, "benchmark", self.benchmark)
        setattr(args, "input_image", str(self.pages_dir))
        setattr(args, "output", str(self.output_dir))
        setattr(args, "stage", self.internal_stage)
        setattr(args, "stage1_source", self.stage1_source)
        setattr(args, "prompt_mode", self.prompt_mode)
        setattr(args, "experiment_name", self.experiment_name)
        setattr(args, "stage2_experiment_name", self.stage2_experiment_name)
        setattr(args, "stage1_output_subdir", self.stage1_output_subdir)
        if self.intro_dir:
            setattr(args, "intro", str(self.intro_dir))
        if self.alphabet_path:
            setattr(args, "alphabet", str(self.alphabet_path))
        if self.ocr_text_dir:
            setattr(args, "ocr_text", str(self.ocr_text_dir))
        if self.samples_dir:
            setattr(args, "samples_dir", str(self.samples_dir))
        if self.languages:
            setattr(args, "languages", self.languages)
