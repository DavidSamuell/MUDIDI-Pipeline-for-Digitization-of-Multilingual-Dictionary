from __future__ import annotations

import argparse
import sys
from pathlib import Path

from mudidi.cli import run as run_cli


def test_run_forwards_agentic_flags(monkeypatch, tmp_path: Path) -> None:
    parser = argparse.ArgumentParser()
    run_cli.register_run_arguments(parser)
    args = parser.parse_args(
        [
            "--pages",
            str(tmp_path / "pages"),
            "--output-dir",
            str(tmp_path / "out"),
            "--stage1-agentic",
            "--stage1-typography",
            "--stage2-agentic",
            "--stage1-agentic-patch-verifier",
            "--agentic-max-iterations",
            "3",
            "--agentic-evaluator-model",
            "provider/eval",
            "--agentic-rewriter-model",
            "provider/rewrite",
            "--agentic-reasoning",
            "medium",
            "--agentic-evaluator-reasoning",
            "high",
            "--agentic-rewriter-reasoning",
            "low",
            "--agentic-min-retry-confidence",
            "0.7",
            "--agentic-max-rewrite-delta-ratio",
            "0.5",
            "--agentic-max-patches-per-attempt",
            "7",
            "--no-agentic-max-rewrite-delta-gate",
            "--no-agentic-verifier-patches",
            "--no-agentic-concrete-retry-gate",
            "--agentic-catastrophic-recovery",
        ]
    )

    captured: dict[str, list[str]] = {}

    def fake_extract_main() -> int:
        captured["argv"] = list(sys.argv)
        return 0

    monkeypatch.setattr(run_cli, "configure_prompts", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("mudidi.cli.extract.main", fake_extract_main)

    assert run_cli.run_from_args(args, []) == 0

    forwarded = captured["argv"]
    assert "--stage1-typography" in forwarded
    assert "--stage1-agentic" in forwarded
    assert "--stage2-agentic" in forwarded
    assert "--stage1-agentic-patch-verifier" in forwarded
    assert forwarded[forwarded.index("--agentic-max-iterations") + 1] == "3"
    assert forwarded[forwarded.index("--agentic-evaluator-model") + 1] == "provider/eval"
    assert forwarded[forwarded.index("--agentic-rewriter-model") + 1] == "provider/rewrite"
    assert forwarded[forwarded.index("--agentic-reasoning") + 1] == "medium"
    assert forwarded[forwarded.index("--agentic-evaluator-reasoning") + 1] == "high"
    assert forwarded[forwarded.index("--agentic-rewriter-reasoning") + 1] == "low"
    assert forwarded[forwarded.index("--agentic-min-retry-confidence") + 1] == "0.7"
    assert "--agentic-max-rewrite-delta-ratio" not in forwarded
    assert forwarded[forwarded.index("--agentic-max-patches-per-attempt") + 1] == "7"
    assert "--no-agentic-max-rewrite-delta-gate" in forwarded
    assert "--no-agentic-verifier-patches" in forwarded
    assert "--no-agentic-concrete-retry-gate" in forwarded
    assert "--agentic-catastrophic-recovery" in forwarded
