"""Per-prep cost projection at ``_run_prep_phase_a`` start (#713).

At the start of a prep run the orchestrator emits a ``prep_cost_projection``
event with the expected per-prep cost computed from each role's configured
model (via role frontmatter) and trailing-30d ``cost_log`` medians for
that ``(role, model)`` pair. When the projection exceeds 1.5x the trailing
30d median full-prep cost, a higher-severity ``prep_cost_projection_high``
event fires too. Both events are non-blocking — the operator wanted to
know about creep, not be gated.

SQLite has no ``PERCENTILE_CONT``; medians are computed in Python from
the small row sets the queries return (<= ~30 rows per role, <= ~90 per-prep
totals).

Cold-start (no relevant ``cost_log`` history) is a normal state, not an
error: ``projected_usd`` / ``ceiling_usd`` come back as ``None`` and the
caller still emits the event with ``n_roles_with_history=0``.
"""

from __future__ import annotations

import sqlite3
import statistics
from collections.abc import Callable
from dataclasses import dataclass

from findajob.cost_tracking import role_model

# Roles invoked across a full prep run (Phase A: company_researcher,
# briefing_writer, fit_analyst; Phase B: resume_tailor,
# resume_change_reviewer, cover_letter_writer, recruiter_critic;
# outreach_drafter is called from scripts/find_contacts.py at Phase B tail).
PREP_ROLES: tuple[str, ...] = (
    "company_researcher",
    "briefing_writer",
    "fit_analyst",
    "resume_tailor",
    "resume_change_reviewer",
    "cover_letter_writer",
    "recruiter_critic",
    "outreach_drafter",
)


@dataclass(frozen=True)
class RoleMedian:
    role: str
    model: str
    median_usd: float | None
    n_samples: int


@dataclass(frozen=True)
class ProjectionResult:
    projected_usd: float | None
    n_roles: int
    n_roles_with_history: int
    expensive_role: str | None
    recent_median_usd: float | None
    n_history_preps: int
    ceiling_usd: float | None
    per_role: tuple[RoleMedian, ...]


def _median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def _role_median(
    conn: sqlite3.Connection,
    role: str,
    model: str,
) -> tuple[float | None, int]:
    rows = conn.execute(
        """SELECT cost_usd
           FROM cost_log
           WHERE operation = ?
             AND model = ?
             AND cost_usd IS NOT NULL
             AND logged_at IS NOT NULL
             AND logged_at >= datetime('now', '-30 days')""",
        (role, model),
    ).fetchall()
    values = [float(r[0]) for r in rows]
    return _median(values), len(values)


def _recent_per_prep_median(conn: sqlite3.Connection) -> tuple[float | None, int]:
    """Trailing-30d median per-prep cost. Excludes scoring.

    Regenerates that emit multiple calls per role collapse to one larger
    per-``job_id`` data point; acceptable v1 — the ceiling is an alert
    threshold, not an SLA.
    """
    rows = conn.execute(
        """SELECT job_id, SUM(cost_usd) AS total
           FROM cost_log
           WHERE cost_usd IS NOT NULL
             AND logged_at IS NOT NULL
             AND logged_at >= datetime('now', '-30 days')
             AND operation != 'score'
             AND job_id IS NOT NULL
           GROUP BY job_id
           HAVING total IS NOT NULL"""
    ).fetchall()
    values = [float(r[1]) for r in rows]
    return _median(values), len(values)


def compute_projection(
    conn: sqlite3.Connection,
    roles: tuple[str, ...] = PREP_ROLES,
    role_model_fn: Callable[[str], str] | None = None,
) -> ProjectionResult:
    """Project per-prep cost from configured models and recent ``cost_log`` medians.

    ``role_model_fn`` defaults to :func:`findajob.cost_tracking.role_model`;
    tests inject a stub to avoid depending on real role frontmatter files.
    """
    resolver = role_model_fn or role_model

    per_role: list[RoleMedian] = []
    projected = 0.0
    n_with_history = 0
    expensive_role: str | None = None
    expensive_median: float = -1.0

    for role in roles:
        model = resolver(role)
        median, n = _role_median(conn, role, model)
        per_role.append(RoleMedian(role=role, model=model, median_usd=median, n_samples=n))
        if median is not None:
            projected += median
            n_with_history += 1
            if median > expensive_median:
                expensive_median = median
                expensive_role = role

    projected_total: float | None = projected if n_with_history > 0 else None
    recent_median, n_history_preps = _recent_per_prep_median(conn)
    ceiling = recent_median * 1.5 if recent_median is not None else None

    return ProjectionResult(
        projected_usd=projected_total,
        n_roles=len(roles),
        n_roles_with_history=n_with_history,
        expensive_role=expensive_role,
        recent_median_usd=recent_median,
        n_history_preps=n_history_preps,
        ceiling_usd=ceiling,
        per_role=tuple(per_role),
    )
