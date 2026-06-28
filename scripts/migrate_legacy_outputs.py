#!/usr/bin/env python3
"""Copy legacy Stage 1 / stage-1-ocr / Stage 2 outputs into outputs/benchmark/."""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

_REPO_ROOT = Path(__file__).resolve().parents[1]

# Legacy subdir under dictionaries/{Lang}/outputs/ → (dest benchmark root, dest subdir name)
MIGRATION_MAP: tuple[tuple[str, str, str], ...] = (
    ("stage-1", "stage-1", "stage-1"),
    ("stage-1-ocr", "stage-1", "stage-1-ocr"),
    ("stage-2", "stage-2", "stage-2"),
)

logger = logging.getLogger(__name__)


@dataclass
class CopyRecord:
    language: str
    legacy_subdir: str
    source: str
    destination: str
    status: str
    file_count: int = 0
    reason: str = ""


@dataclass
class MigrationManifest:
    created_at: str
    legacy_root: str
    dataset_dir: str
    dest_root: str
    dry_run: bool
    overwrite: bool
    copied: list[CopyRecord] = field(default_factory=list)
    skipped: list[CopyRecord] = field(default_factory=list)
    migrated_languages: list[str] = field(default_factory=list)
    skipped_not_in_dataset: list[str] = field(default_factory=list)


def _count_files(root: Path) -> int:
    if not root.is_dir():
        return 0
    return sum(1 for p in root.rglob("*") if p.is_file())


def _iter_legacy_languages(legacy_root: Path) -> Iterator[str]:
    for child in sorted(legacy_root.iterdir()):
        if child.is_dir() and not child.name.startswith("."):
            yield child.name


def _dataset_allowlist(dataset_dir: Path) -> set[str]:
    return {
        p.name
        for p in dataset_dir.iterdir()
        if p.is_dir() and not p.name.startswith(".")
    }


def _dest_has_content(dest: Path) -> bool:
    if not dest.exists():
        return False
    if dest.is_file():
        return True
    return any(dest.iterdir())


def _copy_tree(
    source: Path,
    dest: Path,
    *,
    dry_run: bool,
    overwrite: bool,
) -> tuple[str, int]:
    """Copy source tree to dest. Returns (status, file_count)."""
    file_count = _count_files(source)
    if not source.is_dir():
        return "skipped", 0

    if _dest_has_content(dest) and not overwrite:
        return "skipped_conflict", file_count

    if dry_run:
        return "dry_run", file_count

    dest.parent.mkdir(parents=True, exist_ok=True)
    if shutil.which("rsync"):
        subprocess.run(
            ["rsync", "-a", f"{source}/", f"{dest}/"],
            check=True,
        )
    else:
        if dest.exists() and overwrite:
            shutil.rmtree(dest)
        shutil.copytree(source, dest, dirs_exist_ok=True)
    return "copied", file_count


def run_migration(
    *,
    legacy_root: Path,
    dataset_dir: Path,
    dest_root: Path,
    dry_run: bool = False,
    overwrite: bool = False,
    languages: list[str] | None = None,
) -> MigrationManifest:
    """Copy legacy prediction trees for dataset languages into dest_root."""
    allowlist = _dataset_allowlist(dataset_dir)
    selected = set(languages) if languages else allowlist

    manifest = MigrationManifest(
        created_at=datetime.now(timezone.utc).isoformat(),
        legacy_root=str(legacy_root.resolve()),
        dataset_dir=str(dataset_dir.resolve()),
        dest_root=str(dest_root.resolve()),
        dry_run=dry_run,
        overwrite=overwrite,
    )

    for lang_name in _iter_legacy_languages(legacy_root):
        if lang_name not in allowlist:
            manifest.skipped_not_in_dataset.append(lang_name)
            continue
        if lang_name not in selected:
            continue

        lang_legacy = legacy_root / lang_name / "outputs"
        if not lang_legacy.is_dir():
            continue

        lang_migrated = False
        for legacy_subdir, dest_benchmark_root, dest_subdir in MIGRATION_MAP:
            source = lang_legacy / legacy_subdir
            dest = dest_root / dest_benchmark_root / lang_name / dest_subdir
            status, file_count = _copy_tree(
                source,
                dest,
                dry_run=dry_run,
                overwrite=overwrite,
            )
            record = CopyRecord(
                language=lang_name,
                legacy_subdir=legacy_subdir,
                source=str(source.resolve()),
                destination=str(dest.resolve()),
                status=status,
                file_count=file_count,
            )
            if status in ("copied", "dry_run"):
                manifest.copied.append(record)
                lang_migrated = True
            elif status == "skipped":
                record.reason = "source missing"
                manifest.skipped.append(record)
            elif status == "skipped_conflict":
                record.reason = "destination exists (use --overwrite)"
                manifest.skipped.append(record)

        if lang_migrated and lang_name not in manifest.migrated_languages:
            manifest.migrated_languages.append(lang_name)

    manifest.skipped_not_in_dataset.sort()
    manifest.migrated_languages.sort()
    return manifest


def write_manifest(manifest: MigrationManifest, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(asdict(manifest), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Copy legacy dictionary outputs into outputs/benchmark/.",
    )
    parser.add_argument(
        "--legacy-root",
        type=Path,
        default=_REPO_ROOT / "dictionaries",
        help="Legacy dictionaries root (default: dictionaries/)",
    )
    parser.add_argument(
        "--dataset-dir",
        type=Path,
        default=_REPO_ROOT / "dataset" / "MUDIDI" / "dictionaries",
        help="Canonical dataset dictionary folders (name filter)",
    )
    parser.add_argument(
        "--dest-root",
        type=Path,
        default=_REPO_ROOT / "outputs" / "benchmark",
        help="Benchmark output root (default: outputs/benchmark/)",
    )
    parser.add_argument(
        "--languages",
        nargs="*",
        default=None,
        help="Optional subset of language folder names to migrate",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report planned copies without writing files",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace existing destination trees",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="Manifest JSON path (default: <dest-root>/migration_manifest.json)",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    legacy_root = args.legacy_root.resolve()
    dataset_dir = args.dataset_dir.resolve()
    dest_root = args.dest_root.resolve()

    if not legacy_root.is_dir():
        logger.error("Legacy root not found: %s", legacy_root)
        return 1
    if not dataset_dir.is_dir():
        logger.error("Dataset dir not found: %s", dataset_dir)
        return 1

    manifest = run_migration(
        legacy_root=legacy_root,
        dataset_dir=dataset_dir,
        dest_root=dest_root,
        dry_run=args.dry_run,
        overwrite=args.overwrite,
        languages=args.languages,
    )

    manifest_path = args.manifest or (dest_root / "migration_manifest.json")
    if not args.dry_run:
        write_manifest(manifest, manifest_path)

    logger.info(
        "Migrated %d language(s); %d copy operation(s); %d skipped; %d not in dataset",
        len(manifest.migrated_languages),
        len(manifest.copied),
        len(manifest.skipped),
        len(manifest.skipped_not_in_dataset),
    )
    if args.dry_run:
        logger.info("Dry run — no files written.")
    else:
        logger.info("Manifest: %s", manifest_path)

    for record in manifest.copied:
        logger.info(
            "  [%s] %s → %s (%d files)",
            record.status,
            record.source,
            record.destination,
            record.file_count,
        )
    for record in manifest.skipped:
        logger.warning(
            "  skipped %s (%s): %s",
            record.language,
            record.reason,
            record.source,
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
