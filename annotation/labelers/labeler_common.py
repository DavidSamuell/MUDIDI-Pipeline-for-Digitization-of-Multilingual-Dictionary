"""Shared helpers for gold span-map labelers (discovery, paths, span grouping)."""

from __future__ import annotations

from pathlib import Path
from typing import List, Tuple

import yaml

from mudidi.schemas.language_span import LanguageSpan

OUTPUT_ROOT = Path("annotation/outputs")

_GOLD_GLOB = "Stage 1 Gold OCR/*/*_stage1_GOLD_flat.txt"


def _page_number(gold_path: Path) -> int:
    """Extract the integer page number from ``page_<N>_stage1_GOLD_flat.txt``."""
    name = gold_path.name
    stem = name.split("_stage1_GOLD_flat.txt")[0]
    digits = "".join(ch for ch in stem if ch.isdigit())
    return int(digits) if digits else 0


def discover_gold_pages(dictionary_dir: str | Path) -> List[Path]:
    """Return sorted gold flat-text page files for a dictionary."""
    return sorted(Path(dictionary_dir).glob(_GOLD_GLOB), key=_page_number)


def list_dictionaries(dictionaries_root: str | Path) -> List[str]:
    """Return dictionary folder names that have at least one gold page."""
    root = Path(dictionaries_root)
    names: List[str] = []
    for child in sorted(root.iterdir()):
        if child.is_dir() and discover_gold_pages(child):
            names.append(child.name)
    return names


def _dictionary_name(gold_path: Path) -> str:
    """Derive the dictionary folder name from a gold page path."""
    for parent in gold_path.parents:
        if parent.parent is not None and parent.name == "Stage 1 Gold OCR":
            return parent.parent.name
    return gold_path.parent.name


def _lang_map_path(gold_path: Path, output_root: str | Path = OUTPUT_ROOT) -> Path:
    """Output ``*_lang.json`` path under ``<output_root>/<dictionary>/``."""
    stem = gold_path.name.split("_stage1_GOLD_flat.txt")[0]
    return Path(output_root) / _dictionary_name(gold_path) / f"{stem}_lang.json"


def spans_from_labels(labels: List[str]) -> List[LanguageSpan]:
    """Group consecutive equal labels into contiguous spans."""
    spans: List[LanguageSpan] = []
    start = 0
    for index in range(1, len(labels) + 1):
        if index == len(labels) or labels[index] != labels[start]:
            spans.append(LanguageSpan(start=start, end=index, language=labels[start]))
            start = index
    return spans


def read_languages(dictionary_dir: str | Path) -> Tuple[str, List[str]]:
    """Return ``(source_language, target_languages)`` from ``dictionary_languages.yaml``."""
    path = Path(dictionary_dir) / "dictionary_languages.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"missing dictionary_languages.yaml under {dictionary_dir}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    source = data.get("source") or {}
    source_language = str(source.get("language") or "").strip()
    targets = [
        str(t["language"]).strip()
        for t in (data.get("targets") or [])
        if isinstance(t, dict) and t.get("language")
    ]
    if not source_language or not targets:
        raise ValueError(f"incomplete language metadata in {path}")
    return source_language, targets
