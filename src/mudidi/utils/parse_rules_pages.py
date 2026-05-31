"""Resolve Stage 2 Pass 1 parse-rules sample page stems and image paths."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


@dataclass(frozen=True)
class ParseRulesSample:
    """One page used for Pass 1 parse-rules discovery."""

    stem: str
    image_path: Path
    transcription: str


def normalize_parse_rules_page_stems(
    values: str | list[str] | None,
) -> list[str]:
    """Expand CLI ``--parse-rules-page`` values into an ordered stem list.

    Supports repeated flags and comma-separated lists, e.g.
    ``--parse-rules-page page_1 --parse-rules-page page_50`` or
    ``--parse-rules-page page_1,page_50``.
    """
    if values is None:
        return []
    if isinstance(values, str):
        values = [values]

    stems: list[str] = []
    for raw in values:
        for part in raw.split(","):
            stem = part.strip()
            if stem:
                stems.append(stem)
    return stems


def select_parse_rules_sample_images(
    images: list[Path],
    stems: list[str],
) -> list[Path]:
    """Map parse-rules stems to snippet paths from the current run."""
    if not images:
        raise ValueError("No dictionary pages available for parse-rules discovery.")

    by_stem = {path.stem: path for path in images}
    if not stems:
        return [images[0]]

    missing = [stem for stem in stems if stem not in by_stem]
    if missing:
        available = sorted(by_stem)
        raise ValueError(
            f"--parse-rules-page stem(s) not found in --pages input: {missing}. "
            f"Available stems: {available}"
        )
    return [by_stem[stem] for stem in stems]


def format_sample_pages_block(samples: Sequence[tuple[str, str]]) -> str:
    """Build multi-sample transcription block for Pass 1 user prompt."""
    blocks: list[str] = []
    for stem, transcription in samples:
        blocks.append(
            f'<sample_transcription page="{stem}">\n{transcription.strip()}\n</sample_transcription>'
        )
    return "\n\n".join(blocks)
