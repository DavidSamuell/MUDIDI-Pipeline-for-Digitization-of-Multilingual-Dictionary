"""Resolve Stage-1 transcript files for Stage-2 consumption."""

from __future__ import annotations

from pathlib import Path
from typing import Literal, Optional

Stage1InputPreference = Literal["auto", "column", "flat"]
Stage1Source = Literal["gold", "predictions"]


def stage1_tsv_path(page_dir: Path, stem: str) -> Path:
    """Column transcription TSV for a page."""
    return page_dir / f"{stem}_stage1.tsv"


def stage1_flat_path(page_dir: Path, stem: str) -> Path:
    """Flat transcription text for a page."""
    return page_dir / f"{stem}_stage1_flat.txt"


def stage1_gold_tsv_path(page_dir: Path, stem: str) -> Path:
    """Human gold column TSV for a page."""
    return page_dir / f"{stem}_stage1_GOLD.tsv"


def stage1_gold_flat_path(page_dir: Path, stem: str) -> Path:
    """Derived flat gold transcription for a page."""
    return page_dir / f"{stem}_stage1_GOLD_flat.txt"


def stage1_gold_dir(output_dir: Path) -> Path:
    """Root directory for experiment-agnostic stage-1 gold."""
    return output_dir / "stage-1-gold"


def stage1_experiment_dir(
    output_dir: Path,
    experiment_name: str,
    *,
    subdir: str = "stage-1",
) -> Path:
    """Root directory for one Stage-1 experiment slot under ``outputs/``."""
    return output_dir / subdir / experiment_name


def stage1_transcript_kind(path: Path) -> Stage1InputPreference:
    """Return ``column`` or ``flat`` from the transcript file name."""
    name = path.name
    if name.endswith("_stage1_flat.txt") or name.endswith("_stage1_GOLD_flat.txt"):
        return "flat"
    return "column"


def _transcript_path_in_dir(
    page_dir: Path,
    stem: str,
    preference: Stage1InputPreference,
    *,
    tsv_path: Path,
    flat_path: Path,
) -> Optional[Path]:
    if preference == "column":
        return tsv_path if tsv_path.is_file() else None
    if preference == "flat":
        return flat_path if flat_path.is_file() else None
    if tsv_path.is_file():
        return tsv_path
    if flat_path.is_file():
        return flat_path
    return None


def stage1_transcript_path(
    page_dir: Path,
    stem: str,
    preference: Stage1InputPreference = "auto",
) -> Optional[Path]:
    """
    Pick a Stage-1 transcript from an experiment slot (predictions).

    Args:
        page_dir: ``outputs/stage-1/<experiment>/<stem>/``
        stem: Page stem (e.g. ``page_1``).
        preference: ``auto`` prefers column TSV, then flat; ``column`` / ``flat``
            require that artifact only.

    Returns:
        Resolved path, or ``None`` if nothing matches the preference.
    """
    return _transcript_path_in_dir(
        page_dir,
        stem,
        preference,
        tsv_path=stage1_tsv_path(page_dir, stem),
        flat_path=stage1_flat_path(page_dir, stem),
    )


def stage1_gold_transcript_path(
    gold_page_dir: Path,
    stem: str,
    preference: Stage1InputPreference = "auto",
) -> Optional[Path]:
    """
    Pick the stage-1 gold transcript Stage 2 should read.

    Args:
        gold_page_dir: ``outputs/stage-1-gold/<stem>/``
        stem: Page stem (e.g. ``page_3``).
        preference: ``auto`` prefers column TSV, then flat gold.
    """
    return _transcript_path_in_dir(
        gold_page_dir,
        stem,
        preference,
        tsv_path=stage1_gold_tsv_path(gold_page_dir, stem),
        flat_path=stage1_gold_flat_path(gold_page_dir, stem),
    )


def stage1_transcript_for_stage2(
    output_dir: Path,
    stem: str,
    preference: Stage1InputPreference = "auto",
    *,
    source: Stage1Source = "gold",
    experiment_name: str = "default",
    stage1_output_subdir: str = "stage-1",
    inference_layout: bool = False,
) -> Optional[Path]:
    """Resolve the Stage-1 transcript Stage 2 should consume.

    Args:
        output_dir: Entry ``outputs/`` directory (benchmark) or ``--output-dir`` (inference).
        stem: Page stem (e.g. ``page_14``).
        preference: Column vs flat transcript preference.
        source: ``gold`` reads ``stage-1-gold/``; ``predictions`` reads experiment slot
            or ``stage-1/<stem>/`` when ``inference_layout`` is True.
        experiment_name: Stage-1 experiment slot when ``source=predictions`` (benchmark).
        stage1_output_subdir: Parent folder under ``outputs/`` for Stage-1 predictions.
        inference_layout: When True, predictions live at ``{output_dir}/stage-1/{stem}/``.
    """
    if source == "gold":
        return stage1_gold_transcript_path(
            stage1_gold_dir(output_dir) / stem,
            stem,
            preference,
        )
    if inference_layout:
        return stage1_transcript_path(
            output_dir / "stage-1" / stem,
            stem,
            preference,
        )
    return stage1_transcript_path(
        stage1_experiment_dir(
            output_dir, experiment_name, subdir=stage1_output_subdir
        )
        / stem,
        stem,
        preference,
    )


def read_stage1_transcript_text(path: Path) -> str:
    """Load Stage-1 transcript file contents for Stage-2 prompts."""
    return path.read_text(encoding="utf-8")
