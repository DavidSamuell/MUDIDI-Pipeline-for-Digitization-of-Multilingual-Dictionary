"""Tests for per-page usage timing helpers."""

from __future__ import annotations

import time

from mudidi.extraction.llm_two_stage import _sum_elapsed, _with_elapsed


def test_sum_elapsed_ignores_missing_values() -> None:
    assert _sum_elapsed(None, None) is None
    assert _sum_elapsed(1.2, None) == 1.2
    assert _sum_elapsed(1.2, 3.456) == 4.656


def test_with_elapsed_records_wall_clock() -> None:
    started = time.perf_counter()
    time.sleep(0.01)
    usage = _with_elapsed({"cost_usd": 0.01}, started)
    assert usage["cost_usd"] == 0.01
    assert usage["elapsed_seconds"] >= 0.01
