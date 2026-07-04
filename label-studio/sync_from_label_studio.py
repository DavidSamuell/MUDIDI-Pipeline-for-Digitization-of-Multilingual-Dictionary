"""Sync submitted Label Studio OCR post-edits into the MUDIDI dataset gold tree.

Matches ``Post-Edit: {Dict}`` projects from ``label-studio/setup.py``.

Gold format is chosen explicitly (not inferred from Label Studio UI layout):

``--gold-format tsv`` (default)
    Legacy column projects: export header/left/middle/right/footer text areas to
    ``*_stage1_GOLD.tsv``, then always regenerate ``*_stage1_GOLD_flat.txt`` from
    that TSV via the stage-1 flatten spec.

``--gold-format flat``
    Recent single-body projects (flat transcript pushed as one ``body_text`` box):
    write ``*_stage1_GOLD_flat.txt`` only.

Usage:
    uv run python label-studio/sync_from_label_studio.py \\
        --ls-url http://216.158.235.114:8080 --ls-token "$VM_LS_TOKEN" --dry-run

    uv run python label-studio/sync_from_label_studio.py \\
        --gold-format flat --languages Hindi-Russian Coptic-English-Greek --dry-run
"""

from __future__ import annotations

import argparse
import csv
import io
import logging
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import requests
from pydantic import ValidationError

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "scripts"))
if str(_REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src"))

from export_label_studio_gold import (  # noqa: E402
    EXCLUDED_LANGUAGES,
    LabelStudioClient,
    LabelStudioExportError,
    LabelStudioProject,
    LabelStudioTask,
    build_tsv_rows,
    export_columns_for_task,
)
from mudidi.evaluation.stage1.flatten import flatten_stage1_rows  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

PROJECT_PREFIX = "Post-Edit: "
STAGE1_GOLD_OCR = "Stage 1 Gold OCR"
GoldFormat = Literal["tsv", "flat"]
WriteStatus = Literal["unchanged", "changed", "new", "skip", "dry-run"]


@dataclass(frozen=True)
class GoldPaths:
    """On-disk gold locations for one dictionary page."""

    page_dir: Path
    flat_path: Path
    tsv_path: Path


@dataclass
class PageSyncPlan:
    """Planned write for one Label Studio task."""

    page_name: str
    source: str
    gold_format: GoldFormat
    flat_path: Path
    tsv_path: Path
    flat_content: str | None = None
    tsv_content: str | None = None
    status: WriteStatus = "skip"


@dataclass
class DictionarySyncSummary:
    """Aggregate sync result for one dictionary."""

    dictionary: str
    project_id: int
    gold_format: GoldFormat
    pages: list[PageSyncPlan] = field(default_factory=list)

    @property
    def changed_pages(self) -> list[PageSyncPlan]:
        return [page for page in self.pages if page.status in ("changed", "new", "dry-run")]

    @property
    def has_changes(self) -> bool:
        return bool(self.changed_pages)


def gold_paths(dataset_dir: Path, dictionary: str, page_name: str) -> GoldPaths:
    """Return dataset gold paths for one page."""
    page_dir = dataset_dir / dictionary / STAGE1_GOLD_OCR / page_name
    return GoldPaths(
        page_dir=page_dir,
        flat_path=page_dir / f"{page_name}_stage1_GOLD_flat.txt",
        tsv_path=page_dir / f"{page_name}_stage1_GOLD.tsv",
    )


def tsv_content_from_columns(columns: dict[str, str]) -> str:
    """Serialize column text to stage-1 TSV file content."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter="\t")
    writer.writerow(["column_id", "line_number", "text"])
    writer.writerows(build_tsv_rows(columns))
    return buffer.getvalue()


def flat_content_from_tsv_columns(columns: dict[str, str], *, dictionary: str) -> str:
    """Derive flat eval gold from column buckets using the stage-1 flatten spec."""
    rows = build_tsv_rows(columns)
    dict_rows = [
        {"column_id": column_id, "line_number": line_number, "text": text}
        for column_id, line_number, text in rows
    ]
    lines = flatten_stage1_rows(dict_rows, language=dictionary)
    return "\n".join(lines)


def flat_content_from_body(columns: dict[str, str]) -> str:
    """Return flat gold from the single ``body_text`` / ``single`` bucket."""
    return columns.get("single", "").strip()


def _normalize_text(text: str) -> str:
    """Normalize trailing whitespace for stable on-disk comparisons."""
    if not text:
        return ""
    return text.rstrip("\n") + ("\n" if text.strip() else "")


def compare_text(path: Path, content: str) -> WriteStatus:
    """Compare proposed content with an on-disk file."""
    normalized = _normalize_text(content)
    if not path.is_file():
        return "new" if normalized.strip() else "skip"
    existing = _normalize_text(path.read_text(encoding="utf-8"))
    if existing == normalized:
        return "unchanged"
    return "changed"


def _page_status(
    paths: GoldPaths,
    *,
    gold_format: GoldFormat,
    tsv_content: str | None,
    flat_content: str | None,
) -> WriteStatus:
    """Return whether this page would change on disk for the chosen gold format."""
    if gold_format == "flat":
        if flat_content is None:
            return "skip"
        return compare_text(paths.flat_path, flat_content)

    if tsv_content is None or flat_content is None:
        return "skip"
    tsv_status = compare_text(paths.tsv_path, tsv_content)
    flat_status = compare_text(paths.flat_path, flat_content)
    if tsv_status in ("changed", "new") or flat_status in ("changed", "new"):
        return "changed" if paths.tsv_path.is_file() or paths.flat_path.is_file() else "new"
    return "unchanged"


def plan_page_sync(
    task: LabelStudioTask,
    dataset_dir: Path,
    *,
    gold_format: GoldFormat,
    include_prefill: bool,
) -> PageSyncPlan:
    """Build a sync plan for one Label Studio task without writing files."""
    paths = gold_paths(dataset_dir, task.data.language, task.data.page_name)
    columns, source = export_columns_for_task(task, include_prefill=include_prefill)
    plan = PageSyncPlan(
        page_name=task.data.page_name,
        source=source,
        gold_format=gold_format,
        flat_path=paths.flat_path,
        tsv_path=paths.tsv_path,
    )
    if source == "skip":
        return plan

    if gold_format == "flat":
        plan.flat_content = flat_content_from_body(columns)
        plan.status = _page_status(
            paths,
            gold_format=gold_format,
            tsv_content=None,
            flat_content=plan.flat_content,
        )
    else:
        plan.tsv_content = tsv_content_from_columns(columns)
        plan.flat_content = flat_content_from_tsv_columns(
            columns,
            dictionary=task.data.language,
        )
        plan.status = _page_status(
            paths,
            gold_format=gold_format,
            tsv_content=plan.tsv_content,
            flat_content=plan.flat_content,
        )
    return plan


def apply_page_sync(plan: PageSyncPlan, *, dry_run: bool) -> None:
    """Write one page plan to disk, honouring dry-run."""
    if plan.source == "skip" or plan.status == "unchanged":
        return

    if dry_run:
        plan.status = "dry-run"
        return

    plan.flat_path.parent.mkdir(parents=True, exist_ok=True)
    if plan.gold_format == "flat":
        if plan.flat_content is not None:
            plan.flat_path.write_text(_normalize_text(plan.flat_content), encoding="utf-8")
        plan.status = "updated"  # type: ignore[assignment]
        return

    if plan.tsv_content is not None:
        plan.tsv_path.write_text(plan.tsv_content, encoding="utf-8")
    if plan.flat_content is not None:
        plan.flat_path.write_text(_normalize_text(plan.flat_content), encoding="utf-8")
    plan.status = "updated"  # type: ignore[assignment]


def dictionary_name_from_title(title: str) -> str | None:
    """Extract dictionary folder name from a Label Studio project title."""
    if not title.startswith(PROJECT_PREFIX):
        return None
    return title[len(PROJECT_PREFIX) :]


def plan_dictionary_sync(
    client: LabelStudioClient,
    project: LabelStudioProject,
    dictionary: str,
    dataset_dir: Path,
    *,
    gold_format: GoldFormat,
    include_prefill: bool,
) -> DictionarySyncSummary:
    """Build sync plans for every task in one Label Studio project."""
    tasks = client.list_project_tasks(project.id)
    summary = DictionarySyncSummary(
        dictionary=dictionary,
        project_id=project.id,
        gold_format=gold_format,
    )
    for task in tasks:
        if task.data.language != dictionary:
            logger.warning(
                "  %s task %d language mismatch (%s)",
                dictionary,
                task.id,
                task.data.language,
            )
        summary.pages.append(
            plan_page_sync(
                task,
                dataset_dir,
                gold_format=gold_format,
                include_prefill=include_prefill,
            )
        )
    return summary


def _status_label(plan: PageSyncPlan) -> str:
    if plan.gold_format == "flat":
        return "flat"
    return "tsv+flat"


def log_dictionary_summary(summary: DictionarySyncSummary, *, dry_run: bool) -> None:
    """Log per-page sync results for one dictionary."""
    changed = summary.changed_pages
    if not changed:
        logger.info("%s: no changes", summary.dictionary)
        return

    logger.info(
        "%s: %d page(s) would change%s (project id=%d, gold-format=%s)",
        summary.dictionary,
        len(changed),
        " (dry-run)" if dry_run else "",
        summary.project_id,
        summary.gold_format,
    )
    for page in changed:
        logger.info(
            "  %s (%s) [%s]",
            page.page_name,
            page.source,
            _status_label(page),
        )


def run_sync(
    dataset_dir: Path,
    ls_url: str,
    ls_token: str,
    ls_auth_scheme: str,
    ls_access_token: str | None,
    languages: list[str] | None,
    *,
    gold_format: GoldFormat,
    include_prefill: bool,
    dry_run: bool,
) -> int:
    """Sync selected Label Studio projects into the dataset gold tree."""
    client = LabelStudioClient(ls_url, ls_token, ls_auth_scheme, access_token=ls_access_token)
    projects = client.list_projects()
    requested = set(languages) if languages else None

    candidates: list[tuple[str, LabelStudioProject]] = []
    for project in projects:
        dictionary = dictionary_name_from_title(project.title)
        if dictionary is None:
            continue
        if dictionary in EXCLUDED_LANGUAGES:
            logger.info("Skipping excluded dictionary: %s", dictionary)
            continue
        if requested is not None and dictionary not in requested:
            continue
        candidates.append((dictionary, project))

    if not candidates:
        logger.warning("No matching '%s…' projects found.", PROJECT_PREFIX)
        return 0

    logger.info(
        "Connected to Label Studio — checking %d dictionary project(s), gold-format=%s%s",
        len(candidates),
        gold_format,
        " (dry-run)" if dry_run else "",
    )

    summaries: list[DictionarySyncSummary] = []
    for dictionary, project in sorted(candidates, key=lambda item: item[0].lower()):
        summary = plan_dictionary_sync(
            client,
            project,
            dictionary,
            dataset_dir,
            gold_format=gold_format,
            include_prefill=include_prefill,
        )
        for page in summary.pages:
            apply_page_sync(page, dry_run=dry_run)
        log_dictionary_summary(summary, dry_run=dry_run)
        summaries.append(summary)

    changed_dicts = [summary for summary in summaries if summary.has_changes]
    unchanged_dicts = [summary.dictionary for summary in summaries if not summary.has_changes]

    logger.info(
        "Done — %d dictionary(ies) with changes, %d unchanged",
        len(changed_dicts),
        len(unchanged_dicts),
    )
    if unchanged_dicts:
        logger.info("Unchanged: %s", ", ".join(sorted(unchanged_dicts)))
    if dry_run and changed_dicts:
        logger.info("Re-run without --dry-run to write these changes.")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset-dir",
        type=Path,
        default=Path("dataset/MUDIDI/dictionaries"),
        help="Root of per-dictionary dataset folders (default: dataset/MUDIDI/dictionaries).",
    )
    parser.add_argument(
        "--languages",
        nargs="+",
        metavar="DICT",
        help="Only sync these dictionaries (default: all Post-Edit projects).",
    )
    parser.add_argument(
        "--gold-format",
        choices=("tsv", "flat"),
        default="tsv",
        help=(
            "tsv (default): write column *_stage1_GOLD.tsv and regenerate *_stage1_GOLD_flat.txt. "
            "flat: write *_stage1_GOLD_flat.txt only (single-body Label Studio projects)."
        ),
    )
    parser.add_argument(
        "--include-prefill",
        action="store_true",
        help="Export import-time OCR prefill when a task has no submitted annotation.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report dictionaries/pages that would change without writing files.",
    )
    parser.add_argument(
        "--ls-url",
        default=os.getenv("LABEL_STUDIO_URL", "http://localhost:8080"),
        help="Label Studio base URL.",
    )
    parser.add_argument(
        "--ls-token",
        default=os.getenv("LABEL_STUDIO_TOKEN"),
        help="Label Studio API token. Can also be set via LABEL_STUDIO_TOKEN.",
    )
    parser.add_argument(
        "--ls-access-token",
        default=os.getenv("LABEL_STUDIO_ACCESS_TOKEN"),
        help="Optional short-lived Label Studio access token for Bearer auth.",
    )
    parser.add_argument(
        "--ls-auth-scheme",
        default=os.getenv("LABEL_STUDIO_AUTH_SCHEME", "auto"),
        help="Authorization scheme: auto, Token, Bearer, or PAT.",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable DEBUG logging.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    if not args.ls_token:
        logger.error("No Label Studio token provided. Use --ls-token or LABEL_STUDIO_TOKEN.")
        return 1
    if not args.dataset_dir.is_dir():
        logger.error("Dataset directory not found: %s", args.dataset_dir)
        return 1

    try:
        return run_sync(
            args.dataset_dir.resolve(),
            args.ls_url,
            args.ls_token,
            args.ls_auth_scheme,
            args.ls_access_token,
            args.languages,
            gold_format=args.gold_format,
            include_prefill=args.include_prefill,
            dry_run=args.dry_run,
        )
    except (requests.HTTPError, ValidationError, LabelStudioExportError, ValueError) as error:
        logger.error("Sync failed: %s", error)
        return 1


if __name__ == "__main__":
    sys.exit(main())
