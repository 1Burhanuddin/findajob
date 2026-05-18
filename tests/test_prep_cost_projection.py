"""Tests for findajob.prep.cost_projection (#713)."""

from __future__ import annotations

import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.fixture
def db(tmp_path: Path) -> sqlite3.Connection:
    db_path = tmp_path / "pipeline.db"
    subprocess.run(
        [sys.executable, "scripts/init_db.py", str(db_path)],
        check=True,
        cwd=Path(__file__).resolve().parent.parent,
    )
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


def _seed_cost_row(
    conn: sqlite3.Connection,
    *,
    job_id: str,
    operation: str,
    model: str,
    cost_usd: float,
    days_ago: int = 1,
) -> None:
    conn.execute(
        """INSERT INTO cost_log (job_id, operation, model, cost_usd, success, logged_at)
           VALUES (?, ?, ?, ?, 1, datetime('now', ?))""",
        (job_id, operation, model, cost_usd, f"-{days_ago} days"),
    )


def _seed_job(conn: sqlite3.Connection, job_id: str) -> None:
    conn.execute(
        """INSERT INTO jobs
           (id, fingerprint, title, company, location, source, url, stage)
           VALUES (?, ?, 'T', 'C', 'L', 's', '', 'applied')""",
        (job_id, f"fp-{job_id}"),
    )


def _stub_resolver(mapping: dict[str, str]):
    return lambda role: mapping.get(role, "unknown")


def test_cold_start_emits_sentinels(db: sqlite3.Connection) -> None:
    from findajob.prep.cost_projection import compute_projection

    result = compute_projection(db, role_model_fn=_stub_resolver({}))

    assert result.projected_usd is None
    assert result.ceiling_usd is None
    assert result.recent_median_usd is None
    assert result.n_history_preps == 0
    assert result.n_roles_with_history == 0
    assert result.expensive_role is None
    assert result.n_roles == 8


def test_happy_path_sums_role_medians_and_picks_expensive(db: sqlite3.Connection) -> None:
    from findajob.prep.cost_projection import compute_projection

    resolver = _stub_resolver(
        {
            "briefing_writer": "opus",
            "resume_tailor": "opus",
            "cover_letter_writer": "opus",
            "recruiter_critic": "opus",
            "company_researcher": "perplexity",
            "fit_analyst": "perplexity",
            "resume_change_reviewer": "haiku",
            "outreach_drafter": "haiku",
        }
    )

    # Seed three rows per (role, model) to make the median deterministic.
    seeds = {
        "briefing_writer": ("opus", [0.20, 0.25, 0.30]),  # median 0.25
        "resume_tailor": ("opus", [0.25, 0.27, 0.29]),  # median 0.27
        "cover_letter_writer": ("opus", [0.28, 0.29, 0.30]),  # median 0.29
        "recruiter_critic": ("opus", [0.03, 0.04, 0.05]),  # median 0.04
        "company_researcher": ("perplexity", [0.01, 0.02, 0.03]),  # median 0.02
        "fit_analyst": ("perplexity", [0.06, 0.07, 0.08]),  # median 0.07
        "resume_change_reviewer": ("haiku", [0.001, 0.002, 0.003]),  # 0.002
        "outreach_drafter": ("haiku", [0.05, 0.06, 0.07]),  # 0.06
    }
    for i, (role, (model, costs)) in enumerate(seeds.items()):
        for j, c in enumerate(costs):
            jid = f"job-{role}-{j}"
            _seed_job(db, jid)
            _seed_cost_row(db, job_id=jid, operation=role, model=model, cost_usd=c, days_ago=1 + i)
    db.commit()

    result = compute_projection(db, role_model_fn=resolver)

    expected = 0.25 + 0.27 + 0.29 + 0.04 + 0.02 + 0.07 + 0.002 + 0.06
    assert result.projected_usd == pytest.approx(expected, rel=1e-3)
    assert result.n_roles == 8
    assert result.n_roles_with_history == 8
    assert result.expensive_role == "cover_letter_writer"  # 0.29 is the max median


def test_only_some_roles_have_history(db: sqlite3.Connection) -> None:
    from findajob.prep.cost_projection import compute_projection

    resolver = _stub_resolver({"briefing_writer": "opus", "resume_tailor": "opus"})
    _seed_job(db, "j1")
    _seed_cost_row(db, job_id="j1", operation="briefing_writer", model="opus", cost_usd=0.40, days_ago=2)
    db.commit()

    result = compute_projection(db, roles=("briefing_writer", "resume_tailor"), role_model_fn=resolver)

    assert result.projected_usd == pytest.approx(0.40, rel=1e-3)
    assert result.n_roles_with_history == 1
    assert result.expensive_role == "briefing_writer"


def test_excludes_rows_older_than_30_days(db: sqlite3.Connection) -> None:
    from findajob.prep.cost_projection import compute_projection

    resolver = _stub_resolver({"briefing_writer": "opus"})
    _seed_job(db, "old")
    _seed_job(db, "fresh")
    _seed_cost_row(db, job_id="old", operation="briefing_writer", model="opus", cost_usd=9.99, days_ago=45)
    _seed_cost_row(db, job_id="fresh", operation="briefing_writer", model="opus", cost_usd=0.10, days_ago=5)
    db.commit()

    result = compute_projection(db, roles=("briefing_writer",), role_model_fn=resolver)

    assert result.projected_usd == pytest.approx(0.10, rel=1e-3)


def test_model_mismatch_excludes_history(db: sqlite3.Connection) -> None:
    """If a role was previously run on a different model, its old cost_log
    rows don't contribute. Switching models is a real event (#622-class) and
    the projection should reflect the *current* model's history only.
    """
    from findajob.prep.cost_projection import compute_projection

    resolver = _stub_resolver({"briefing_writer": "opus-4-7"})
    _seed_job(db, "j1")
    _seed_cost_row(db, job_id="j1", operation="briefing_writer", model="opus-4-6", cost_usd=0.20, days_ago=2)
    db.commit()

    result = compute_projection(db, roles=("briefing_writer",), role_model_fn=resolver)

    assert result.projected_usd is None
    assert result.n_roles_with_history == 0


def test_recent_median_excludes_scoring(db: sqlite3.Connection) -> None:
    from findajob.prep.cost_projection import compute_projection

    resolver = _stub_resolver({"briefing_writer": "opus"})
    # Two job_ids of prep activity, plus one fat scoring run that should be ignored.
    _seed_job(db, "prep-a")
    _seed_cost_row(db, job_id="prep-a", operation="briefing_writer", model="opus", cost_usd=1.00, days_ago=2)
    _seed_job(db, "prep-b")
    _seed_cost_row(db, job_id="prep-b", operation="briefing_writer", model="opus", cost_usd=2.00, days_ago=3)
    _seed_job(db, "score-only")
    _seed_cost_row(db, job_id="score-only", operation="score", model="haiku", cost_usd=50.00, days_ago=1)
    db.commit()

    result = compute_projection(db, roles=("briefing_writer",), role_model_fn=resolver)

    # Per-prep medians: prep-a=1.00, prep-b=2.00 → median 1.5; ceiling 2.25.
    assert result.recent_median_usd == pytest.approx(1.5, rel=1e-3)
    assert result.ceiling_usd == pytest.approx(2.25, rel=1e-3)
    assert result.n_history_preps == 2


def test_projection_at_or_below_ceiling_does_not_exceed(db: sqlite3.Connection) -> None:
    """Sanity: when role-median sum equals per-prep median, projection is at
    the median (well under 1.5x median ceiling). Caller must not fire
    ``prep_cost_projection_high`` in this case.
    """
    from findajob.prep.cost_projection import compute_projection

    resolver = _stub_resolver({"briefing_writer": "opus"})
    _seed_job(db, "hist")
    _seed_cost_row(db, job_id="hist", operation="briefing_writer", model="opus", cost_usd=0.50, days_ago=2)
    for i in range(3):
        jid = f"recent-{i}"
        _seed_job(db, jid)
        _seed_cost_row(db, job_id=jid, operation="briefing_writer", model="opus", cost_usd=1.00, days_ago=1)
    db.commit()

    result = compute_projection(db, roles=("briefing_writer",), role_model_fn=resolver)

    # role_median over 4 rows {0.50, 1.00, 1.00, 1.00} = 1.00.
    # per_prep totals: {0.50, 1.00, 1.00, 1.00} → median 1.00 → ceiling 1.50.
    assert result.projected_usd == pytest.approx(1.00, rel=1e-3)
    assert result.ceiling_usd == pytest.approx(1.50, rel=1e-3)
    assert result.projected_usd <= result.ceiling_usd


def test_projection_exceeds_ceiling_triggers_high(db: sqlite3.Connection) -> None:
    """AC5 trigger case: when a multi-role projection exceeds 1.5x recent
    per-prep median, the orchestrator should fire ``prep_cost_projection_high``.

    Setup decouples role-median sum from per-prep median: history is
    five preps of one cheap role at $0.10 each (per-prep median 0.10,
    ceiling 0.15), and the projection runs over three roles each at $0.10
    median → $0.30 projected. $0.30 > $0.15 ceiling fires HIGH.
    """
    from findajob.prep.cost_projection import compute_projection

    resolver = _stub_resolver(
        {"company_researcher": "perplexity", "briefing_writer": "opus", "fit_analyst": "perplexity"}
    )
    # Historical preps: 5 single-role preps, each $0.10. per-prep median = $0.10.
    for i in range(5):
        jid = f"hist-{i}"
        _seed_job(db, jid)
        _seed_cost_row(db, job_id=jid, operation="company_researcher", model="perplexity", cost_usd=0.10, days_ago=2)
    # Role-median fixtures: 3 separate roles each with $0.10 median, summed into the projection.
    for role, model in (
        ("briefing_writer", "opus"),
        ("fit_analyst", "perplexity"),
    ):
        for j in range(3):
            jid = f"role-{role}-{j}"
            _seed_job(db, jid)
            _seed_cost_row(db, job_id=jid, operation=role, model=model, cost_usd=0.10, days_ago=3 + j)
    db.commit()

    result = compute_projection(
        db,
        roles=("company_researcher", "briefing_writer", "fit_analyst"),
        role_model_fn=resolver,
    )

    # company_researcher contributes 0.10 (median of 5 hist rows), briefing_writer 0.10,
    # fit_analyst 0.10 → projection 0.30. per-prep median across hist-* = 0.10, ceiling 0.15.
    assert result.projected_usd == pytest.approx(0.30, rel=1e-3)
    assert result.ceiling_usd == pytest.approx(0.15, rel=1e-3)
    assert result.projected_usd > result.ceiling_usd
    assert result.n_roles_with_history == 3
