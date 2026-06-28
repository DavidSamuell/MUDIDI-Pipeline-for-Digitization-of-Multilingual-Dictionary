"""Pull submitted Label Studio NER annotations back into annotation/outputs *_lang.json.

For every "NER: <dict>" project, this exports the tasks, and for each task that has a
*submitted human annotation* it rebuilds the :class:`PageLanguageMap` from the
annotation and overwrites ``annotation/outputs/<dict>/page_<N>_lang.json``. Tasks with
no human annotation are left untouched — their existing LLM-drafted map stands.

Submitted annotations win over predictions (see ``label_studio_ner._latest_results``),
so this captures the reviewer's corrections. Writes are skipped when the rebuilt map is
identical to the file on disk, so re-running is a no-op until something actually changes.

Usage:
    uv run python annotation/label_studio/sync_from_label_studio.py \
        --ls-url http://localhost:8083 --ls-token "$LS_ACCESS_TOKEN"

Environment:
    LABEL_STUDIO_URL    — Label Studio base URL (default: http://localhost:8080)
    LABEL_STUDIO_TOKEN  — API token (legacy Token or PAT)
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

import requests
from pydantic import ValidationError

# Flat-sibling imports: add annotation/label_studio/ to path.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from label_studio_ner import ls_task_to_page_map  # noqa: E402
from setup_ner_projects import _PROJECT_PREFIX, LabelStudioClient  # noqa: E402
from span_schema import PageLanguageMap, SpanMapError, sha256_of  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pure conversion (no network, no disk) — testable in isolation
# ---------------------------------------------------------------------------

def page_map_from_task(task: dict) -> tuple[str, int, PageLanguageMap] | None:
    """Rebuild ``(dict_name, page, page_map)`` from a task's submitted annotation.

    Returns None when the task carries no human annotation, or its data is missing the
    fields the import needs (``text``, ``language``, ``page_name``). The task's own
    ``data.text`` is the raw gold the regions index into, so no gold re-read is needed.
    """
    if not task.get("annotations"):
        return None
    data = task.get("data") or {}
    raw_text = data.get("text")
    dict_name = data.get("language")
    page_name = data.get("page_name") or ""
    if raw_text is None or not dict_name or "_" not in page_name:
        return None
    page = int(page_name.rsplit("_", 1)[-1])
    page_map = ls_task_to_page_map(
        task,
        raw_text,
        dictionary=dict_name,
        page=page,
        labeled_via="label-studio",
        rule_set=str(data.get("rule_set", "")),
    )
    return dict_name, page, page_map


# ---------------------------------------------------------------------------
# Disk write (idempotent — only writes when the map actually changed)
# ---------------------------------------------------------------------------

def _output_path(outputs_root: Path, dict_name: str, page: int) -> Path:
    return outputs_root / dict_name / f"page_{page}_lang.json"


def _is_unchanged(out_path: Path, page_map: PageLanguageMap) -> bool:
    """True if ``out_path`` already holds an equivalent (canonical) map."""
    if not out_path.is_file():
        return False
    try:
        existing = PageLanguageMap.model_validate_json(out_path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return False
    return existing.canonical().spans == page_map.canonical().spans


def write_synced_map(
    outputs_root: Path, dict_name: str, page: int, page_map: PageLanguageMap, *, dry_run: bool
) -> str:
    """Write the synced map; return one of 'updated' | 'unchanged' | 'dry-run' | 'new'."""
    out_path = _output_path(outputs_root, dict_name, page)
    if _is_unchanged(out_path, page_map):
        return "unchanged"
    status = "new" if not out_path.is_file() else "updated"
    if dry_run:
        return "dry-run"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    page_map.save(out_path)
    return status


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sync submitted Label Studio NER annotations into annotation/outputs.",
    )
    parser.add_argument(
        "--outputs-root",
        type=Path,
        default=Path("annotation/outputs"),
        help="Root of per-dictionary *_lang.json folders (default: annotation/outputs).",
    )
    parser.add_argument(
        "--ls-url",
        default=os.getenv("LABEL_STUDIO_URL", "http://localhost:8080"),
        help="Label Studio base URL.",
    )
    parser.add_argument(
        "--ls-token",
        default=os.getenv("LABEL_STUDIO_TOKEN"),
        help="Label Studio API token (legacy Token or PAT).",
    )
    parser.add_argument(
        "--dictionaries",
        nargs="+",
        metavar="DICT",
        help="Only sync these dictionaries (default: all NER projects).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would change without writing any files.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if not args.ls_token:
        logger.error("No Label Studio token. Set LABEL_STUDIO_TOKEN or pass --ls-token.")
        return 1

    client = LabelStudioClient(args.ls_url, args.ls_token)
    try:
        projects = client.list_projects()
    except requests.HTTPError as exc:
        logger.error("Cannot connect to Label Studio at %s: %s", args.ls_url, exc)
        return 1

    # Map "NER: <dict>" projects -> dict name, honouring the --dictionaries filter.
    requested = set(args.dictionaries) if args.dictionaries else None
    ner_projects: list[tuple[str, int]] = []
    for project in projects:
        title = project.get("title", "")
        if not title.startswith(_PROJECT_PREFIX):
            continue
        dict_name = title[len(_PROJECT_PREFIX):]
        if requested is None or dict_name in requested:
            ner_projects.append((dict_name, project["id"]))

    if not ner_projects:
        logger.warning("No matching 'NER: …' projects found.")
        return 0

    logger.info(
        "Syncing %d project(s)%s", len(ner_projects), " (dry-run)" if args.dry_run else ""
    )

    totals = {"updated": 0, "new": 0, "unchanged": 0, "dry-run": 0, "error": 0}
    for dict_name, project_id in sorted(ner_projects):
        try:
            tasks = client.export_tasks(project_id)
        except requests.HTTPError as exc:
            logger.error("%s: export failed: %s", dict_name, exc)
            totals["error"] += 1
            continue

        annotated = 0
        for task in tasks:
            converted = _convert(task, dict_name)
            if converted is None:
                continue
            annotated += 1
            _, page, page_map = converted
            status = write_synced_map(
                args.outputs_root, dict_name, page, page_map, dry_run=args.dry_run
            )
            totals[status] = totals.get(status, 0) + 1
            if status in ("updated", "new", "dry-run"):
                logger.info("  %s page %d: %s", dict_name, page, status)
        logger.info("%s: %d task(s) with submitted annotations", dict_name, annotated)

    logger.info(
        "Done — %d updated, %d new, %d unchanged%s",
        totals["updated"], totals["new"], totals["unchanged"],
        f", {totals['dry-run']} would change (dry-run)" if args.dry_run else "",
    )
    if totals["error"]:
        logger.warning("%d project(s) failed to export", totals["error"])
    return 0


def _convert(task: dict, dict_name: str) -> tuple[str, int, PageLanguageMap] | None:
    """Wrap ``page_map_from_task`` with per-task error isolation + a sha sanity check."""
    try:
        result = page_map_from_task(task)
    except (SpanMapError, ValidationError) as exc:
        logger.error("  %s: skipping a task — invalid annotation: %s", dict_name, exc)
        return None
    if result is None:
        return None
    name, page, page_map = result
    # The map binds to the task's own gold text; guard against a dict/page mismatch.
    raw_text = (task.get("data") or {}).get("text", "")
    if page_map.source_text_sha != sha256_of(raw_text):
        logger.error("  %s page %d: sha mismatch — skipping", name, page)
        return None
    return name, page, page_map


if __name__ == "__main__":
    sys.exit(main())
