"""Regression tests for the score-column ordering on board tabs (#302).

The fit_score / probability_score / interview_likelihood / relevance_score
columns must:
1. All be visible by default on tabs that declare them
2. Render in this left-to-right order: relevance_score, interview_likelihood,
   fit_score, probability_score

The ordering puts the two compositional/relative signals (Rel, Likelihood)
together on the left and the two derived briefing scores (Fit, Prob)
together on the right.

Regression for #302: probability_score was previously default_visible=False
and the registry ordering had likelihood after probability_score, so the
operator never saw the briefing-derived probability column on the daily
triage view.
"""

from __future__ import annotations

import pytest

from findajob.web.filters.registry import DASHBOARD_COLUMNS, WAITLIST_COLUMNS

SCORE_COLUMNS = ("relevance_score", "interview_likelihood", "fit_score", "probability_score")


@pytest.mark.parametrize("spec", [DASHBOARD_COLUMNS, WAITLIST_COLUMNS])
def test_all_four_score_columns_default_visible(spec):
    """Every score column declared on the tab must be visible by default."""
    by_name = {c.name: c for c in spec}
    for col in SCORE_COLUMNS:
        if col in by_name:
            assert by_name[col].default_visible is True, f"{col} must be default_visible=True (regression of #302)"


@pytest.mark.parametrize("spec", [DASHBOARD_COLUMNS, WAITLIST_COLUMNS])
def test_score_columns_render_in_canonical_order(spec):
    """When a tab declares all four score columns, they must appear in the
    order: relevance_score, interview_likelihood, fit_score, probability_score.

    Other (non-score) columns may appear between them on tabs that interleave
    them — what matters is that the relative ORDER of the four scores is
    preserved.
    """
    score_indices = {c.name: i for i, c in enumerate(spec) if c.name in SCORE_COLUMNS}
    if len(score_indices) < 4:
        # Tab doesn't declare all four; nothing to assert here.
        return
    expected_order = list(SCORE_COLUMNS)
    actual_order = sorted(expected_order, key=lambda n: score_indices[n])
    assert actual_order == expected_order, f"score columns out of canonical order: {actual_order}"
