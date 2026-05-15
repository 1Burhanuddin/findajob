"""Regression guard: `run_role` logs `openrouter_truncated` when
`CompletionResult.finish_reason == "length"`.

Without this, max_tokens-capped responses come back as non-empty strings
and the caller has no way to know the output was truncated. The
interview_prep flow (#666) and fit_analyst flow (#639) both hit this
silently — operators feel quality regressions instead of seeing a
diagnostic.

Patches `findajob.llm.role_runner.complete` directly (not via reimport)
so suite-wide `patch("findajob.llm.role_runner.complete", ...)` callers
aren't disturbed — see the warning in `test_llm_role_runner.py`.
"""

from __future__ import annotations

from unittest.mock import patch

from findajob.llm.openrouter import CompletionResult
from findajob.llm.role_runner import run_role


def _make_result(*, finish_reason: str | None, text: str = "partial output") -> CompletionResult:
    return CompletionResult(
        text=text,
        prompt_tokens=3000,
        completion_tokens=4096,
        cached_tokens=0,
        cost_usd=0.04,
        generation_id="g-test",
        finish_reason=finish_reason,
    )


def test_logs_openrouter_truncated_when_finish_reason_length():
    events: list[tuple[str, dict]] = []

    def _fake_log_event(event: str, **kw):
        events.append((event, kw))

    with (
        patch("findajob.llm.role_runner.complete", return_value=_make_result(finish_reason="length")),
        patch("findajob.llm.role_runner.log_event", side_effect=_fake_log_event),
    ):
        out = run_role("interview_prep", "prompt", job_id="job-iv-trunc")

    assert out == "partial output"
    truncated = [(e, kw) for e, kw in events if e == "openrouter_truncated"]
    assert len(truncated) == 1
    _, kw = truncated[0]
    assert kw["role"] == "interview_prep"
    assert kw["job_id"] == "job-iv-trunc"
    assert kw["completion_tokens"] == 4096
    assert kw["content_chars"] == len("partial output")


def test_does_not_log_truncated_when_finish_reason_stop():
    events: list[tuple[str, dict]] = []

    def _fake_log_event(event: str, **kw):
        events.append((event, kw))

    with (
        patch("findajob.llm.role_runner.complete", return_value=_make_result(finish_reason="stop")),
        patch("findajob.llm.role_runner.log_event", side_effect=_fake_log_event),
    ):
        run_role("interview_prep", "prompt", job_id="job-iv-ok")

    assert not [e for e, _ in events if e == "openrouter_truncated"]


def test_does_not_log_truncated_when_finish_reason_missing():
    """Backwards compat: older OpenRouter responses without finish_reason
    must not synthesize a truncation event."""
    events: list[tuple[str, dict]] = []

    def _fake_log_event(event: str, **kw):
        events.append((event, kw))

    with (
        patch("findajob.llm.role_runner.complete", return_value=_make_result(finish_reason=None)),
        patch("findajob.llm.role_runner.log_event", side_effect=_fake_log_event),
    ):
        run_role("interview_prep", "prompt", job_id="job-iv-none")

    assert not [e for e, _ in events if e == "openrouter_truncated"]
