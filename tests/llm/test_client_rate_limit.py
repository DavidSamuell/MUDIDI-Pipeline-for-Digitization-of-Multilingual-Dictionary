"""Tests for LLM rate-limit backoff and shared provider pause."""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock, patch

import pytest
from litellm.exceptions import RateLimitError

from mudidi.llm import client as llm_client


class _FakeHeaders(dict):
    pass


def test_retry_wait_seconds_uses_openrouter_retry_after() -> None:
    exc = Exception(
        '{"error":{"metadata":{"retry_after_seconds":12}}}'
    )
    wait = llm_client._retry_wait_seconds(exc, attempt=0)
    assert wait == pytest.approx(13.0)


def test_retry_wait_seconds_uses_retry_after_header() -> None:
    response = MagicMock()
    response.headers = _FakeHeaders({"Retry-After": "5"})
    exc = RateLimitError(
        message="rate limited",
        llm_provider="gemini",
        model="gemini/gemini-3.1-pro-preview",
        response=response,
    )
    wait = llm_client._retry_wait_seconds(exc, attempt=0)
    assert wait == pytest.approx(6.0)


def test_retry_wait_seconds_falls_back_to_exponential_backoff() -> None:
    wait = llm_client._retry_wait_seconds(Exception("503 service unavailable"), attempt=2)
    assert wait == pytest.approx(4.0)


def test_provider_backoff_blocks_other_threads() -> None:
    backoff = llm_client._ProviderBackoff()
    finished = threading.Event()

    backoff.pause(0.5)

    def worker() -> None:
        backoff.wait_if_paused()
        finished.set()

    thread = threading.Thread(target=worker)
    thread.start()
    time.sleep(0.05)
    assert not finished.is_set()

    thread.join(timeout=2.0)
    assert finished.is_set()


def test_completion_with_retries_pauses_and_retries_on_rate_limit() -> None:
    calls: list[int] = []

    def fake_completion(**kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise RateLimitError(
                message="429 rate limit",
                llm_provider="gemini",
                model="gemini/gemini-3.1-pro-preview",
            )
        return MagicMock(
            model=kwargs["model"],
            choices=[MagicMock(finish_reason="stop", message=MagicMock(content="ok"))],
            usage=MagicMock(
                prompt_tokens=1,
                completion_tokens=1,
                total_tokens=2,
                prompt_tokens_details=None,
            ),
        )

    with patch.object(llm_client.litellm, "completion", side_effect=fake_completion):
        with patch.object(llm_client._backoff, "pause") as pause_mock:
            with patch.object(llm_client._backoff, "wait_if_paused"):
                response = llm_client._completion_with_retries(
                    {"model": "gemini/gemini-3.1-pro-preview", "messages": []}
                )

    assert response.choices[0].message.content == "ok"
    assert len(calls) == 2
    pause_mock.assert_called_once()


def test_is_retryable_transient_error_public_wrapper() -> None:
    exc = RateLimitError(
        message="429 rate limit exceeded",
        llm_provider="gemini",
        model="x",
    )
    assert llm_client.is_retryable_transient_error(exc) is True
    assert llm_client.is_retryable_transient_error(ValueError("bad input")) is False
