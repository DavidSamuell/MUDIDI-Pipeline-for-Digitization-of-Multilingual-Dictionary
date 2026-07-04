from pathlib import Path

from mudidi.agentic.verifier_loop import (
    AgenticIssue,
    AgenticLoopConfig,
    AgenticPatchVerifierDecision,
    AgenticTextPatch,
    AgenticVerifierDecision,
    patch_decision_to_verifier_decision,
    run_bounded_verifier_loop,
)


def test_loop_accepts_initial_output_without_rewrite(tmp_path: Path) -> None:
    calls: list[str] = []

    def verify(output: str, attempt: int) -> AgenticVerifierDecision:
        calls.append(f"verify:{attempt}:{output}")
        return AgenticVerifierDecision(decision="accept", confidence=0.91)

    def rewrite(output: str, decision: AgenticVerifierDecision, attempt: int) -> str:
        raise AssertionError("rewrite should not run after accept")

    result = run_bounded_verifier_loop(
        stage="stage1",
        initial_output="initial transcript",
        artifact_dir=tmp_path,
        output_suffix=".txt",
        verify=verify,
        rewrite=rewrite,
        config=AgenticLoopConfig(max_iterations=2),
    )

    assert result.output == "initial transcript"
    assert result.stop_reason == "accepted"
    assert result.rewrite_count == 0
    assert calls == ["verify:0:initial transcript"]
    assert (tmp_path / "attempt_0_output.txt").read_text() == "initial transcript"
    assert (tmp_path / "attempt_0_verifier.json").is_file()
    assert (tmp_path / "final_decision.json").is_file()


def test_loop_records_verifier_usage_in_artifacts_and_final_decision(tmp_path: Path) -> None:
    def verify(output: str, attempt: int):
        return (
            AgenticVerifierDecision(decision="accept", confidence=0.91),
            {
                "model": "verifier",
                "prompt_tokens": 10,
                "completion_tokens": 3,
                "total_tokens": 13,
                "reasoning_tokens": 2,
                "response_text_tokens": 1,
                "cost_usd": 0.25,
            },
        )

    def rewrite(output: str, decision: AgenticVerifierDecision, attempt: int) -> str:
        raise AssertionError("rewrite should not run after accept")

    result = run_bounded_verifier_loop(
        stage="stage1",
        initial_output="initial transcript",
        artifact_dir=tmp_path,
        output_suffix=".txt",
        verify=verify,
        rewrite=rewrite,
        config=AgenticLoopConfig(max_iterations=2),
    )

    assert result.agentic_usage_summary["total_cost_usd"] == 0.25
    assert result.attempts[0].verifier_usage["reasoning_tokens"] == 2
    assert (tmp_path / "attempt_0_verifier_usage.json").is_file()
    final_decision = (tmp_path / "final_decision.json").read_text()
    assert '"agentic_usage_summary"' in final_decision


def test_patch_decision_converts_to_exact_verifier_issues() -> None:
    decision = patch_decision_to_verifier_decision(
        AgenticPatchVerifierDecision(
            decision="retry",
            confidence=0.88,
            patches=[
                AgenticTextPatch(
                    line_index=2,
                    old="<b>abc</b>",
                    new="<b>abd</b>",
                    confidence=0.91,
                    reason="visible final character is d",
                )
            ],
        )
    )

    assert decision.decision == "retry"
    assert decision.confidence == 0.88
    assert decision.issues[0].type == "exact_text_patch"
    assert decision.issues[0].line_index == 2
    assert decision.issues[0].current_text == "<b>abc</b>"
    assert decision.issues[0].expected_text == "<b>abd</b>"


def test_loop_rewrites_until_verifier_accepts(tmp_path: Path) -> None:
    verifier_outputs = [
        AgenticVerifierDecision(
            decision="retry",
            confidence=0.62,
            issues=[
                AgenticIssue(
                    type="reading_order_error",
                    severity="high",
                    evidence="columns were read independently",
                    suggested_fix="read aligned rows",
                )
            ],
            retry_instruction="Read rows left to right.",
        ),
        AgenticVerifierDecision(decision="accept", confidence=0.94),
    ]

    def verify(output: str, attempt: int) -> AgenticVerifierDecision:
        return verifier_outputs[attempt]

    def rewrite(output: str, decision: AgenticVerifierDecision, attempt: int) -> str:
        assert attempt == 1
        assert decision.retry_instruction == "Read rows left to right."
        return "corrected transcript"

    result = run_bounded_verifier_loop(
        stage="stage1",
        initial_output="bad transcript",
        artifact_dir=tmp_path,
        output_suffix=".txt",
        verify=verify,
        rewrite=rewrite,
        config=AgenticLoopConfig(max_iterations=2),
    )

    assert result.output == "corrected transcript"
    assert result.stop_reason == "accepted"
    assert result.rewrite_count == 1
    assert (tmp_path / "attempt_1_output.txt").read_text() == "corrected transcript"
    assert (tmp_path / "attempt_1_verifier.json").is_file()


def test_loop_stops_when_rewrite_is_unchanged(tmp_path: Path) -> None:
    def verify(output: str, attempt: int) -> AgenticVerifierDecision:
        return AgenticVerifierDecision(
            decision="retry",
            confidence=0.8,
            issues=[
                AgenticIssue(
                    type="ungrounded_text",
                    severity="medium",
                    evidence="same issue",
                    suggested_fix="remove ungrounded text",
                )
            ],
        )

    def rewrite(output: str, decision: AgenticVerifierDecision, attempt: int) -> str:
        return "  same output\n"

    result = run_bounded_verifier_loop(
        stage="stage2",
        initial_output="same output",
        artifact_dir=tmp_path,
        output_suffix=".mdf.txt",
        verify=verify,
        rewrite=rewrite,
        config=AgenticLoopConfig(max_iterations=2),
    )

    assert result.output == "same output"
    assert result.stop_reason == "unchanged"
    assert result.rewrite_count == 0
    assert not (tmp_path / "attempt_1_output.mdf.txt").exists()


def test_loop_stops_when_retry_confidence_is_too_low(tmp_path: Path) -> None:
    def verify(output: str, attempt: int) -> AgenticVerifierDecision:
        return AgenticVerifierDecision(
            decision="retry",
            confidence=0.2,
            issues=[
                AgenticIssue(
                    type="possible_ocr_error",
                    severity="low",
                    evidence="maybe a bad character",
                    suggested_fix="check it",
                )
            ],
        )

    def rewrite(output: str, decision: AgenticVerifierDecision, attempt: int) -> str:
        raise AssertionError("rewrite should not run for low-confidence retry")

    result = run_bounded_verifier_loop(
        stage="stage1",
        initial_output="same output",
        artifact_dir=tmp_path,
        output_suffix=".txt",
        verify=verify,
        rewrite=rewrite,
        config=AgenticLoopConfig(max_iterations=2, min_retry_confidence=0.6),
    )

    assert result.output == "same output"
    assert result.stop_reason == "low_confidence_retry"
    assert result.rewrite_count == 0


def test_loop_stops_when_retry_has_no_concrete_issue(tmp_path: Path) -> None:
    def verify(output: str, attempt: int) -> AgenticVerifierDecision:
        return AgenticVerifierDecision(
            decision="retry",
            confidence=0.9,
            issues=[AgenticIssue(type="character_conflation", severity="medium")],
        )

    def rewrite(output: str, decision: AgenticVerifierDecision, attempt: int) -> str:
        raise AssertionError("rewrite should not run without concrete edit evidence")

    result = run_bounded_verifier_loop(
        stage="stage1",
        initial_output="same output",
        artifact_dir=tmp_path,
        output_suffix=".txt",
        verify=verify,
        rewrite=rewrite,
        config=AgenticLoopConfig(max_iterations=2, require_concrete_retry_issue=True),
    )

    assert result.output == "same output"
    assert result.stop_reason == "vague_retry"
    assert result.rewrite_count == 0


def test_loop_treats_retry_instruction_without_evidence_as_vague(tmp_path: Path) -> None:
    def verify(output: str, attempt: int) -> AgenticVerifierDecision:
        return AgenticVerifierDecision(
            decision="retry",
            confidence=0.9,
            issues=[
                AgenticIssue(
                    type="format",
                    severity="medium",
                    line_index=3,
                    suggested_fix="move this line",
                )
            ],
            retry_instruction="Please fix this.",
        )

    def rewrite(output: str, decision: AgenticVerifierDecision, attempt: int) -> str:
        raise AssertionError("rewrite should not run without evidence or exact span")

    result = run_bounded_verifier_loop(
        stage="stage1",
        initial_output="same output",
        artifact_dir=tmp_path,
        output_suffix=".txt",
        verify=verify,
        rewrite=rewrite,
        config=AgenticLoopConfig(max_iterations=2, require_concrete_retry_issue=True),
    )

    assert result.stop_reason == "vague_retry"
    assert result.rewrite_count == 0


def test_loop_stops_when_rewrite_changes_too_much(tmp_path: Path) -> None:
    def verify(output: str, attempt: int) -> AgenticVerifierDecision:
        return AgenticVerifierDecision(
            decision="retry",
            confidence=0.9,
            issues=[
                AgenticIssue(
                    type="localized_character_error",
                    severity="medium",
                    evidence="line 1 has one wrong character",
                    suggested_fix="change abc to abd",
                )
            ],
        )

    def rewrite(output: str, decision: AgenticVerifierDecision, attempt: int) -> str:
        return "completely unrelated regenerated page"

    result = run_bounded_verifier_loop(
        stage="stage1",
        initial_output="abc\nsecond line\nthird line",
        artifact_dir=tmp_path,
        output_suffix=".txt",
        verify=verify,
        rewrite=rewrite,
        config=AgenticLoopConfig(max_iterations=2, max_rewrite_delta_ratio=0.4),
    )

    assert result.output == "abc\nsecond line\nthird line"
    assert result.stop_reason == "destructive_rewrite"
    assert result.rewrite_count == 0
    assert (tmp_path / "attempt_1_rejected_output.txt").is_file()


def test_loop_applies_safe_verifier_patch_before_calling_rewriter(tmp_path: Path) -> None:
    verifier_outputs = [
        AgenticVerifierDecision(
            decision="retry",
            confidence=0.9,
            issues=[
                AgenticIssue(
                    type="localized_character_error",
                    severity="medium",
                    line_index=0,
                    current_text="abc",
                    expected_text="abd",
                    evidence="line 1 has c where d is visible",
                    suggested_fix="replace abc with abd",
                )
            ],
        ),
        AgenticVerifierDecision(decision="accept", confidence=0.95),
    ]

    def verify(output: str, attempt: int) -> AgenticVerifierDecision:
        return verifier_outputs[attempt]

    def rewrite(output: str, decision: AgenticVerifierDecision, attempt: int) -> str:
        raise AssertionError("safe verifier patch should run before LLM rewrite")

    result = run_bounded_verifier_loop(
        stage="stage1",
        initial_output="abc\nsecond line",
        artifact_dir=tmp_path,
        output_suffix=".txt",
        verify=verify,
        rewrite=rewrite,
        config=AgenticLoopConfig(max_iterations=2, prefer_verifier_patches=True),
    )

    assert result.output == "abd\nsecond line"
    assert result.stop_reason == "accepted"
    assert result.rewrite_count == 1
    assert (tmp_path / "attempt_1_output.txt").read_text() == "abd\nsecond line"


def test_loop_records_rewriter_usage_when_rewriter_runs(tmp_path: Path) -> None:
    verifier_outputs = [
        AgenticVerifierDecision(
            decision="retry",
            confidence=0.9,
            issues=[
                AgenticIssue(
                    type="reading_order_error",
                    severity="medium",
                    evidence="line order is wrong",
                    suggested_fix="rewrite line order",
                )
            ],
        ),
        AgenticVerifierDecision(decision="accept", confidence=0.95),
    ]

    def verify(output: str, attempt: int) -> AgenticVerifierDecision:
        return verifier_outputs[attempt]

    def rewrite(output: str, decision: AgenticVerifierDecision, attempt: int):
        return (
            "corrected",
            {
                "model": "rewriter",
                "prompt_tokens": 20,
                "completion_tokens": 5,
                "total_tokens": 25,
                "cost_usd": 0.5,
            },
        )

    result = run_bounded_verifier_loop(
        stage="stage1",
        initial_output="bad",
        artifact_dir=tmp_path,
        output_suffix=".txt",
        verify=verify,
        rewrite=rewrite,
        config=AgenticLoopConfig(
            max_iterations=2,
            prefer_verifier_patches=False,
            max_rewrite_delta_ratio=None,
        ),
    )

    assert result.output == "corrected"
    assert result.agentic_usage_summary["total_cost_usd"] == 0.5
    assert result.attempts[0].rewrite_usage["total_tokens"] == 25
    assert (tmp_path / "attempt_1_rewrite_usage.json").is_file()


def test_loop_rejects_too_many_patch_issues(tmp_path: Path) -> None:
    issues = [
        AgenticIssue(
            type="exact_text_patch",
            line_index=i,
            current_text=f"old{i}",
            expected_text=f"new{i}",
        )
        for i in range(3)
    ]

    def verify(output: str, attempt: int) -> AgenticVerifierDecision:
        return AgenticVerifierDecision(
            decision="retry",
            confidence=0.9,
            issues=issues,
        )

    def rewrite(output: str, decision: AgenticVerifierDecision, attempt: int) -> str:
        raise AssertionError("rewrite should not run when patch count exceeds gate")

    result = run_bounded_verifier_loop(
        stage="stage1",
        initial_output="old0\nold1\nold2",
        artifact_dir=tmp_path,
        output_suffix=".txt",
        verify=verify,
        rewrite=rewrite,
        config=AgenticLoopConfig(max_iterations=2, max_patches_per_attempt=2),
    )

    assert result.stop_reason == "patch_quality_rejected"
    assert result.rewrite_count == 0


def test_loop_infers_line_patch_from_simple_suggested_fix(tmp_path: Path) -> None:
    verifier_outputs = [
        AgenticVerifierDecision(
            decision="retry",
            confidence=0.9,
            issues=[
                AgenticIssue(
                    type="localized_character_error",
                    severity="medium",
                    line_index=0,
                    suggested_fix="abc -> abd",
                )
            ],
        ),
        AgenticVerifierDecision(decision="accept", confidence=0.95),
    ]

    def verify(output: str, attempt: int) -> AgenticVerifierDecision:
        return verifier_outputs[attempt]

    def rewrite(output: str, decision: AgenticVerifierDecision, attempt: int) -> str:
        raise AssertionError("safe inferred patch should run before LLM rewrite")

    result = run_bounded_verifier_loop(
        stage="stage1",
        initial_output="abc\nsecond line",
        artifact_dir=tmp_path,
        output_suffix=".txt",
        verify=verify,
        rewrite=rewrite,
        config=AgenticLoopConfig(max_iterations=2, prefer_verifier_patches=True),
    )

    assert result.output == "abd\nsecond line"
    assert result.stop_reason == "accepted"
    assert result.rewrite_count == 1


def test_loop_infers_line_patch_from_change_to_suggested_fix(tmp_path: Path) -> None:
    verifier_outputs = [
        AgenticVerifierDecision(
            decision="retry",
            confidence=0.9,
            issues=[
                AgenticIssue(
                    type="localized_character_error",
                    severity="medium",
                    line_index=0,
                    suggested_fix="Change 'abc' to 'abd' to correct the typo.",
                )
            ],
        ),
        AgenticVerifierDecision(decision="accept", confidence=0.95),
    ]

    def verify(output: str, attempt: int) -> AgenticVerifierDecision:
        return verifier_outputs[attempt]

    def rewrite(output: str, decision: AgenticVerifierDecision, attempt: int) -> str:
        raise AssertionError("safe inferred patch should run before LLM rewrite")

    result = run_bounded_verifier_loop(
        stage="stage1",
        initial_output="abc\nsecond line",
        artifact_dir=tmp_path,
        output_suffix=".txt",
        verify=verify,
        rewrite=rewrite,
        config=AgenticLoopConfig(max_iterations=2, prefer_verifier_patches=True),
    )

    assert result.output == "abd\nsecond line"
    assert result.stop_reason == "accepted"
    assert result.rewrite_count == 1


def test_loop_infers_header_deletion_from_suggested_fix(tmp_path: Path) -> None:
    verifier_outputs = [
        AgenticVerifierDecision(
            decision="retry",
            confidence=0.9,
            issues=[
                AgenticIssue(
                    type="tagging_error",
                    severity="medium",
                    line_index=0,
                    suggested_fix="Remove header '<b>Aa</b>' as it is not present.",
                )
            ],
        ),
        AgenticVerifierDecision(decision="accept", confidence=0.95),
    ]

    def verify(output: str, attempt: int) -> AgenticVerifierDecision:
        return verifier_outputs[attempt]

    def rewrite(output: str, decision: AgenticVerifierDecision, attempt: int) -> str:
        raise AssertionError("safe inferred deletion should run before LLM rewrite")

    result = run_bounded_verifier_loop(
        stage="stage1",
        initial_output="<b>Aa</b>\nfirst real line",
        artifact_dir=tmp_path,
        output_suffix=".txt",
        verify=verify,
        rewrite=rewrite,
        config=AgenticLoopConfig(max_iterations=2, prefer_verifier_patches=True),
    )

    assert result.output == "first real line"
    assert result.stop_reason == "accepted"
    assert result.rewrite_count == 1


def test_loop_keeps_last_rewrite_when_budget_is_exhausted(tmp_path: Path) -> None:
    def verify(output: str, attempt: int) -> AgenticVerifierDecision:
        return AgenticVerifierDecision(
            decision="retry",
            confidence=0.8,
            issues=[
                AgenticIssue(
                    type=f"issue_{attempt}",
                    severity="high",
                    evidence="still problematic",
                    suggested_fix=f"apply rewrite {attempt + 1}",
                )
            ],
        )

    def rewrite(output: str, decision: AgenticVerifierDecision, attempt: int) -> str:
        return f"rewrite {attempt}"

    result = run_bounded_verifier_loop(
        stage="stage2",
        initial_output="initial mdf",
        artifact_dir=tmp_path,
        output_suffix=".mdf.txt",
        verify=verify,
        rewrite=rewrite,
        config=AgenticLoopConfig(max_iterations=1),
    )

    assert result.output == "rewrite 1"
    assert result.stop_reason == "max_iterations"
    assert result.rewrite_count == 1
    assert (tmp_path / "attempt_1_output.mdf.txt").read_text() == "rewrite 1"
