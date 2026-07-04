import json
from pathlib import Path

from mudidi.cli.extract import _write_run_usage


def test_write_run_usage_counts_only_page_usage_files(tmp_path: Path) -> None:
    output_dir = tmp_path / "language"
    experiment_dir = output_dir / "stage-1" / "experiment"
    page_dir = experiment_dir / "page_1"
    agentic_dir = page_dir / "agentic" / "stage1"
    page_dir.mkdir(parents=True)
    agentic_dir.mkdir(parents=True)

    (page_dir / "page_1_usage.json").write_text(
        json.dumps(
            {
                "stage1": {"cost_usd": 0.1},
                "stage1_agentic": {"total_cost_usd": 0.2},
                "total_cost_usd": 0.3,
                "total_elapsed_seconds": 4.0,
            }
        ),
        encoding="utf-8",
    )
    (agentic_dir / "attempt_0_verifier_usage.json").write_text(
        json.dumps(
            {
                "cost_usd": 0.2,
                "elapsed_seconds": 10.0,
            }
        ),
        encoding="utf-8",
    )

    _write_run_usage(output_dir, usage_roots=[experiment_dir], parse_rules_roots=[])

    summary = json.loads((output_dir / "run_usage.json").read_text(encoding="utf-8"))
    assert summary["run_total_cost_usd"] == 0.3
    assert summary["run_total_elapsed_seconds"] == 4.0
    assert len(summary["pages"]) == 1
    assert summary["pages"][0]["page"] == "page_1"
