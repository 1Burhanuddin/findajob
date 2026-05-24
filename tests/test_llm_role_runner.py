"""Characterization tests for `findajob.llm.role_runner`.

This module is the canonical home for `run_role` after the M3 cleanup
PR consolidated the two byte-equivalent copies that lived in
`findajob.{prep,interview}.role_runner` after the import-only
extractions.

Behavior tests (HTTP-mocked cost-logging, OpenRouterError handling,
retry semantics) live in `tests/test_prep_application_cost_logging.py`
and `tests/test_interview_prep_cost_logging.py` — both already point at
this module after the patch-target update. This file covers the
public-API surface and the consolidation invariants.

**Note on what this file does NOT test.** The "module load is
side-effect-free" property (the `load_env()` spy pattern used in the
package import-safety tests) doesn't apply here: `findajob.llm.role_runner`
doesn't import `load_env` at all, and there's no module-load risk to
guard against. Adding a reimport-based spy here would be worse than
useless — it would invalidate the `run_role` references that other test
files (`test_prep_application_cost_logging.py`,
`test_interview_prep_cost_logging.py`) take at collection time, causing
their `patch("findajob.llm.role_runner.complete", ...)` to silently miss.
The test-ordering pitfall from PR #542 applies doubly here because
`run_role` is the canonical function being patched suite-wide.
"""

from __future__ import annotations

import importlib


def test_run_role_callable_with_correct_signature():
    """`findajob.llm.role_runner.run_role` is the canonical entrypoint."""
    import inspect

    from findajob.llm.role_runner import run_role

    assert callable(run_role)

    sig = inspect.signature(run_role)
    params = sig.parameters

    # Positional / required
    assert "role" in params and params["role"].kind == inspect.Parameter.POSITIONAL_OR_KEYWORD
    assert "prompt" in params and params["prompt"].kind == inspect.Parameter.POSITIONAL_OR_KEYWORD

    # Keyword-only optionals
    for keyword_param in ("cached_prefix", "pin_provider", "conn", "job_id", "timeout"):
        assert keyword_param in params, f"missing keyword arg: {keyword_param}"
        assert params[keyword_param].kind == inspect.Parameter.KEYWORD_ONLY


def test_orchestrators_import_run_role_from_canonical_location():
    """Both prep and interview orchestrators must use the consolidated module.

    After the cleanup PR, neither `findajob.prep.role_runner` nor
    `findajob.interview.role_runner` exists; both orchestrators import
    `run_role` from `findajob.llm.role_runner`. This test fails if a
    future refactor accidentally re-introduces a per-package copy.
    """
    import inspect

    from findajob.interview import orchestrator as interview_orchestrator
    from findajob.llm.role_runner import run_role as canonical_run_role
    from findajob.prep import orchestrator as prep_orchestrator

    # Both orchestrators should expose `run_role` as an imported name
    assert prep_orchestrator.run_role is canonical_run_role, (
        "findajob.prep.orchestrator.run_role is not the canonical findajob.llm.role_runner.run_role"
    )
    assert interview_orchestrator.run_role is canonical_run_role, (
        "findajob.interview.orchestrator.run_role is not the canonical findajob.llm.role_runner.run_role"
    )

    # The deleted modules should NOT exist
    for deleted in ("findajob.prep.role_runner", "findajob.interview.role_runner"):
        try:
            importlib.import_module(deleted)
        except ModuleNotFoundError:
            continue
        raise AssertionError(
            f"{deleted} still exists; the cleanup PR was supposed to delete it. "
            "Check that the file is gone and that no callers re-imported it."
        )

    # Sanity: the inspected signatures match
    assert (
        inspect.signature(prep_orchestrator.run_role)
        == inspect.signature(interview_orchestrator.run_role)
        == inspect.signature(canonical_run_role)
    )


def test_ntfy_send_imported_by_prep_and_interview_orchestrators():
    """Prep and interview orchestrators use `ntfy.send` for persistent notifications."""
    from findajob.interview import orchestrator as interview_orchestrator
    from findajob.prep import orchestrator as prep_orchestrator

    for module in (prep_orchestrator, interview_orchestrator):
        assert hasattr(module, "ntfy_send"), (
            f"{module.__name__} missing ntfy_send import"
        )
        assert callable(module.ntfy_send)
