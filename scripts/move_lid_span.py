#!/usr/bin/env python3
"""Move selected ``*_lang.json`` outputs into their Stage 1 Gold OCR page folders."""

from __future__ import annotations

import argparse
import logging
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_PAGE_RE = re.compile(r"page_(\d+)_lang\.json$")

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MovePlan:
    dictionary: str
    page: int
    source: Path
    destination: Path


def _page_number(path: Path) -> int | None:
    match = _PAGE_RE.fullmatch(path.name)
    if match is None:
        return None
    return int(match.group(1))


def _iter_output_files(
    outputs_root: Path,
    dictionaries_root: Path,
    selected: set[str] | None,
) -> list[MovePlan]:
    plans: list[MovePlan] = []
    for dict_dir in sorted(outputs_root.iterdir()):
        if not dict_dir.is_dir() or dict_dir.name.startswith("."):
            continue
        if selected is not None and dict_dir.name not in selected:
            continue
        for lang_json in sorted(dict_dir.glob("page_*_lang.json")):
            page = _page_number(lang_json)
            if page is None:
                continue
            destination = (
                dictionaries_root
                / dict_dir.name
                / "Stage 1 Gold OCR"
                / f"page_{page}"
                / lang_json.name
            )
            plans.append(
                MovePlan(
                    dictionary=dict_dir.name,
                    page=page,
                    source=lang_json,
                    destination=destination,
                )
            )
    return plans


def _filter_existing_pages(plans: list[MovePlan]) -> tuple[list[MovePlan], list[MovePlan]]:
    valid: list[MovePlan] = []
    skipped: list[MovePlan] = []
    for plan in plans:
        if plan.destination.parent.is_dir():
            valid.append(plan)
        else:
            skipped.append(plan)
    return valid, skipped


def run_move(
    *,
    outputs_root: Path,
    dictionaries_root: Path,
    dictionaries: list[str] | None,
    pages: set[int] | None,
    overwrite: bool,
    dry_run: bool,
) -> int:
    selected = set(dictionaries) if dictionaries else None
    plans = _iter_output_files(outputs_root, dictionaries_root, selected)
    if pages is not None:
        plans = [plan for plan in plans if plan.page in pages]
    if not plans:
        logger.warning("No matching page_<N>_lang.json files found to move.")
        return 0

    valid, missing_page_dirs = _filter_existing_pages(plans)
    moved = 0
    skipped_existing = 0

    for plan in missing_page_dirs:
        logger.warning(
            "skip %s page %d: destination page folder missing: %s",
            plan.dictionary,
            plan.page,
            plan.destination.parent,
        )

    for plan in valid:
        if not plan.source.is_file():
            logger.warning(
                "skip %s page %d: source missing: %s",
                plan.dictionary,
                plan.page,
                plan.source,
            )
            continue

        if plan.destination.exists() and not overwrite:
            logger.info(
                "skip %s page %d: destination exists (use --overwrite): %s",
                plan.dictionary,
                plan.page,
                plan.destination,
            )
            skipped_existing += 1
            continue

        logger.info(
            "%s %s -> %s",
            "plan" if dry_run else "move",
            plan.source,
            plan.destination,
        )
        if dry_run:
            moved += 1
            continue

        plan.destination.parent.mkdir(parents=True, exist_ok=True)
        if plan.destination.exists():
            plan.destination.unlink()
        shutil.move(str(plan.source), str(plan.destination))
        moved += 1

    logger.info(
        "Done: %d %s, %d skipped_existing, %d missing_page_dirs",
        moved,
        "planned" if dry_run else "moved",
        skipped_existing,
        len(missing_page_dirs),
    )

    if not dry_run:
        remaining = sum(1 for _ in outputs_root.rglob("page_*_lang.json"))
        logger.info("Remaining output files under %s: %d", outputs_root, remaining)

    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Move selected *_lang.json files from annotation/outputs into dataset page folders.",
    )
    parser.add_argument(
        "--outputs-root",
        type=Path,
        default=_REPO_ROOT / "annotation" / "outputs",
        help="Root containing per-dictionary page_<N>_lang.json files.",
    )
    parser.add_argument(
        "--dictionaries-root",
        type=Path,
        default=_REPO_ROOT / "dataset" / "MUDIDI" / "dictionaries",
        help="Dataset dictionaries root.",
    )
    parser.add_argument(
        "--dictionaries",
        "--languages",
        nargs="+",
        dest="dictionaries",
        default=None,
        metavar="DICT",
        help="Only move these dictionary/language folder names.",
    )
    parser.add_argument(
        "--pages",
        nargs="+",
        type=int,
        default=None,
        metavar="N",
        help="Only move these page numbers.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace an existing destination page_<N>_lang.json file.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview moves without changing files.",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    outputs_root = args.outputs_root.resolve()
    dictionaries_root = args.dictionaries_root.resolve()
    if not outputs_root.is_dir():
        raise SystemExit(f"outputs root not found: {outputs_root}")
    if not dictionaries_root.is_dir():
        raise SystemExit(f"dictionaries root not found: {dictionaries_root}")

    return run_move(
        outputs_root=outputs_root,
        dictionaries_root=dictionaries_root,
        dictionaries=args.dictionaries,
        pages=set(args.pages) if args.pages else None,
        overwrite=args.overwrite,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    raise SystemExit(main())
