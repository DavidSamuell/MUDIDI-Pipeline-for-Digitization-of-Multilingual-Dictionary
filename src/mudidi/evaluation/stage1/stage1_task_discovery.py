"""Discover Stage 1 flat eval tasks without evaluation dependencies."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional


@dataclass(frozen=True)
class FlatEvalTask:
    """One flat predicted vs flat gold evaluation unit."""

    experiment: str
    pred_path: Path
    gold_path: Path
    page_id: str


def discover_legacy_tasks(
    samples_dir: str | Path,
    experiments: Optional[List[str]] = None,
    languages: Optional[List[str]] = None,
    stage1_output_subdir: str = "stage-1",
) -> List[FlatEvalTask]:
    """
    Discover (experiment, page) pairs with flat gold and a flat or column pred.

    Gold: ``*/outputs/stage-1-gold/*/*_stage1_GOLD_flat.txt``
    Pred: ``*/outputs/<subdir>/<exp>/*/*_stage1_flat.txt`` or ``*_stage1.tsv``
    """
    samples_dir = Path(samples_dir)
    tasks: List[FlatEvalTask] = []
    selected_languages = set(languages) if languages else None

    golds_by_lang: Dict[Path, List[Path]] = {}
    for gold_path in sorted(
        samples_dir.glob("*/outputs/stage-1-gold/*/*_stage1_GOLD_flat.txt")
    ):
        lang = gold_path.parts[-5]
        if selected_languages and lang not in selected_languages:
            continue
        golds_by_lang.setdefault(gold_path.parents[3], []).append(gold_path)

    for lang_dir, gold_paths in sorted(golds_by_lang.items()):
        stage1_root = lang_dir / "outputs" / stage1_output_subdir
        if not stage1_root.is_dir():
            continue
        available = sorted(
            p.name
            for p in stage1_root.iterdir()
            if p.is_dir() and not p.name.startswith(".")
        )
        exp_names = (
            available if experiments is None else [e for e in experiments if e in available]
        )
        for exp in exp_names:
            for gold_path in gold_paths:
                stem = gold_path.parent.name
                page_dir = stage1_root / exp / stem
                pred_flat = page_dir / f"{stem}_stage1_flat.txt"
                pred_tsv = page_dir / f"{stem}_stage1.tsv"
                if pred_flat.is_file():
                    pred_path = pred_flat
                elif pred_tsv.is_file():
                    pred_path = pred_tsv
                else:
                    continue
                page_id = f"{lang_dir.name}/{stem}"
                tasks.append(
                    FlatEvalTask(
                        experiment=exp,
                        pred_path=pred_path,
                        gold_path=gold_path,
                        page_id=page_id,
                    )
                )
    return tasks


def discover_dataset_tasks(
    dataset_dir: str | Path,
    pred_root: str | Path,
    experiments: Optional[List[str]] = None,
    languages: Optional[List[str]] = None,
    stage1_output_subdir: str = "stage-1",
) -> List[FlatEvalTask]:
    """Discover gold/pred flat pairs under the MUDIDI dataset + benchmark layout.

    Gold:
        dataset_dir/{Lang}/Stage 1 Gold OCR/{page}/{page}_stage1_GOLD_flat.txt
        (fallback: ``*_stage1_GOLD.tsv`` flattened at eval time)

    Predictions:
        pred_root/{Lang}/{stage1_output_subdir}/{exp}/{page}/{page}_stage1_flat.txt
        (or ``*_stage1.tsv``)
    """
    dataset_dir = Path(dataset_dir)
    pred_root = Path(pred_root)
    tasks: List[FlatEvalTask] = []
    selected_languages = set(languages) if languages else None

    for lang_dir in sorted(p for p in dataset_dir.iterdir() if p.is_dir()):
        if selected_languages and lang_dir.name not in selected_languages:
            continue

        gold_root = lang_dir / "Stage 1 Gold OCR"
        stage1_root = pred_root / lang_dir.name / stage1_output_subdir
        if not gold_root.is_dir() or not stage1_root.is_dir():
            continue

        available = sorted(
            p.name
            for p in stage1_root.iterdir()
            if p.is_dir() and not p.name.startswith(".")
        )
        exp_names = (
            available
            if experiments is None
            else [e for e in experiments if e in available]
        )
        for exp in exp_names:
            for gold_flat in sorted(gold_root.glob("*/*_stage1_GOLD_flat.txt")):
                stem = gold_flat.parent.name
                page_dir = stage1_root / exp / stem
                pred_flat = page_dir / f"{stem}_stage1_flat.txt"
                pred_tsv = page_dir / f"{stem}_stage1.tsv"
                if pred_flat.is_file():
                    pred_path = pred_flat
                elif pred_tsv.is_file():
                    pred_path = pred_tsv
                else:
                    continue
                tasks.append(
                    FlatEvalTask(
                        experiment=exp,
                        pred_path=pred_path,
                        gold_path=gold_flat,
                        page_id=f"{lang_dir.name}/{stem}",
                    )
                )
            for gold_tsv in sorted(gold_root.glob("*/*_stage1_GOLD.tsv")):
                stem = gold_tsv.parent.name
                gold_flat = gold_tsv.parent / f"{stem}_stage1_GOLD_flat.txt"
                if gold_flat.is_file():
                    continue
                page_dir = stage1_root / exp / stem
                pred_flat = page_dir / f"{stem}_stage1_flat.txt"
                pred_tsv = page_dir / f"{stem}_stage1.tsv"
                if pred_flat.is_file():
                    pred_path = pred_flat
                elif pred_tsv.is_file():
                    pred_path = pred_tsv
                else:
                    continue
                tasks.append(
                    FlatEvalTask(
                        experiment=exp,
                        pred_path=pred_path,
                        gold_path=gold_tsv,
                        page_id=f"{lang_dir.name}/{stem}",
                    )
                )
    return tasks
