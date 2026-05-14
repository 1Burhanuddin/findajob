"""Tests for findajob.cost_rollups SQL helpers."""

from __future__ import annotations

import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.fixture
def db(tmp_path: Path) -> sqlite3.Connection:
    """Fresh init_db.py-bootstrapped connection."""
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


def _insert_job_with_costs(
    conn: sqlite3.Connection,
    job_id: str,
    rows: list[tuple[str, float | None]],
) -> None:
    """Seed jobs.id and one cost_log row per (operation, cost_usd) tuple."""
    conn.execute(
        """INSERT INTO jobs
           (id, fingerprint, title, company, location, source, url, stage)
           VALUES (?, ?, 'Title', 'Company', 'Loc', 'src', '', 'applied')""",
        (job_id, f"fp-{job_id}"),
    )
    for op, cost in rows:
        conn.execute(
            """INSERT INTO cost_log (job_id, operation, model, cost_usd, success)
               VALUES (?, ?, 'google/gemini-3-flash-preview', ?, 1)""",
            (job_id, op, cost),
        )
    conn.commit()


def test_per_job_cost_sums_non_null_rows(db: sqlite3.Connection) -> None:
    from findajob.cost_rollups import per_job_cost

    _insert_job_with_costs(
        db,
        "job-a",
        [("briefing", 0.10), ("resume_tailor", 0.50), ("cover_letter", None)],
    )

    cost = per_job_cost(db, "job-a")
    assert cost == pytest.approx(0.60, rel=1e-3)


def test_per_job_cost_returns_none_for_all_nulls(db: sqlite3.Connection) -> None:
    from findajob.cost_rollups import per_job_cost

    _insert_job_with_costs(db, "job-b", [("briefing", None), ("score", None)])

    assert per_job_cost(db, "job-b") is None


def test_per_job_breakdown_groups_by_operation(db: sqlite3.Connection) -> None:
    from findajob.cost_rollups import per_job_breakdown

    _insert_job_with_costs(
        db,
        "job-d",
        [
            ("briefing", 0.20),
            ("resume_tailor", 0.30),
            ("cover_letter", 0.25),
            ("briefing", 0.05),  # second briefing call, e.g. regenerate
        ],
    )

    rows = per_job_breakdown(db, "job-d")
    by_op = {r.operation: r.cost_usd for r in rows}
    assert by_op["briefing"] == pytest.approx(0.25, rel=1e-3)  # 0.20 + 0.05
    assert by_op["resume_tailor"] == pytest.approx(0.30, rel=1e-3)
    assert by_op["cover_letter"] == pytest.approx(0.25, rel=1e-3)


def _insert_cost_log(
    conn: sqlite3.Connection,
    *,
    weeks_ago: int,
    cost: float,
    operation: str = "briefing",
) -> None:
    """Insert one cost_log row at exactly N×7 days before 'now'.

    Shifting by exactly 7N days preserves weekday and time-of-day, so the
    row lands in the Nth-previous week of any tz: "now" is by definition
    in current week (UTC and PT both), "now − 7 days" is in last week,
    etc. Avoids the Sunday-anchored variant which becomes flaky when the
    test runs at UTC times where UTC Sunday and PT Sunday differ
    (roughly UTC 00:00–08:00 on Sundays).
    """
    conn.execute(
        """INSERT INTO cost_log
           (job_id, operation, model, cost_usd, success, logged_at)
           VALUES (NULL, ?, 'google/gemini-3-flash-preview', ?, 1,
                   datetime('now', ?))""",
        (operation, cost, f"-{weeks_ago * 7} days"),
    )
    conn.commit()


def test_weekly_spend_returns_n_weeks_oldest_first(db: sqlite3.Connection) -> None:
    from findajob.cost_rollups import weekly_spend

    _insert_cost_log(db, weeks_ago=0, cost=1.00)  # current week
    _insert_cost_log(db, weeks_ago=1, cost=2.00)  # 1 week ago
    _insert_cost_log(db, weeks_ago=2, cost=3.00)  # 2 weeks ago

    weeks = weekly_spend(db, weeks=4)
    assert len(weeks) == 4
    # Last entry = current week.
    assert weeks[-1].prep_usd == pytest.approx(1.00, rel=1e-3)
    # Second-to-last = 1 week ago.
    assert weeks[-2].prep_usd == pytest.approx(2.00, rel=1e-3)
    # Third-to-last = 2 weeks ago.
    assert weeks[-3].prep_usd == pytest.approx(3.00, rel=1e-3)
    # Fourth-to-last = 3 weeks ago, no inserts → zero.
    assert weeks[-4].prep_usd == pytest.approx(0.00, abs=1e-9)
    # Scoring side stays zero — _insert_cost_log defaults operation='briefing'.
    assert all(w.scoring_usd == pytest.approx(0.0, abs=1e-9) for w in weeks)


def test_weekly_spend_splits_prep_and_scoring(db: sqlite3.Connection) -> None:
    """A score row goes to scoring_usd, non-score to prep_usd, same week."""
    from findajob.cost_rollups import weekly_spend

    _insert_cost_log(db, weeks_ago=0, cost=1.50, operation="briefing")
    _insert_cost_log(db, weeks_ago=0, cost=0.20, operation="score")
    _insert_cost_log(db, weeks_ago=0, cost=0.30, operation="score")

    weeks = weekly_spend(db, weeks=4)
    assert weeks[-1].prep_usd == pytest.approx(1.50, rel=1e-3)
    assert weeks[-1].scoring_usd == pytest.approx(0.50, rel=1e-3)


def test_weekly_spend_tz_shifts_week_boundary(db: sqlite3.Connection) -> None:
    """A row logged 'now' counts toward this week's prep total for any tz.

    Verifies the tz= param wires through to the SQL boundary filter — both
    UTC and America/Los_Angeles should bucket a fresh insert as "current
    week," and the local week_start label differs between the two when the
    operator's PT-anchored week boundary lands on a different calendar
    date than the UTC-anchored one (e.g., late Saturday PT = Sunday UTC).
    """
    from findajob.cost_rollups import weekly_spend

    _insert_cost_log(db, weeks_ago=0, cost=1.00)

    weeks_utc = weekly_spend(db, weeks=2, tz="UTC")
    weeks_pt = weekly_spend(db, weeks=2, tz="America/Los_Angeles")

    # The 'now' insert lands in this-week's bucket regardless of tz.
    assert weeks_utc[-1].prep_usd == pytest.approx(1.00, rel=1e-3)
    assert weeks_pt[-1].prep_usd == pytest.approx(1.00, rel=1e-3)
    # week_start label is a local-tz Sunday date, may differ between tzs.
    assert len(weeks_utc[-1].week_start) == 10  # YYYY-MM-DD
    assert len(weeks_pt[-1].week_start) == 10


def test_projected_monthly_scales_7d(db: sqlite3.Connection) -> None:
    from findajob.cost_rollups import projected_monthly

    # 3 prep inserts summing to $7.00 → projection = 7.0 × 30/7 = 30.0
    _insert_cost_log(db, weeks_ago=0, cost=2.10)
    _insert_cost_log(db, weeks_ago=0, cost=3.50)
    _insert_cost_log(db, weeks_ago=0, cost=1.40)
    result = projected_monthly(db)
    assert result.prep_usd == pytest.approx(30.0, rel=1e-3)
    assert result.scoring_usd is None


def test_projected_monthly_splits_prep_and_scoring(db: sqlite3.Connection) -> None:
    from findajob.cost_rollups import projected_monthly

    _insert_cost_log(db, weeks_ago=0, cost=0.70, operation="briefing")
    _insert_cost_log(db, weeks_ago=0, cost=1.40, operation="score")
    result = projected_monthly(db)
    assert result.prep_usd == pytest.approx(0.70 * 30.0 / 7.0, rel=1e-3)
    assert result.scoring_usd == pytest.approx(1.40 * 30.0 / 7.0, rel=1e-3)


def test_projected_monthly_none_when_no_recent_spend(db: sqlite3.Connection) -> None:
    from findajob.cost_rollups import projected_monthly

    result = projected_monthly(db)
    assert result.prep_usd is None
    assert result.scoring_usd is None


def test_spend_this_month_sums_current_month_rows(db: sqlite3.Connection) -> None:
    from findajob.cost_rollups import spend_this_month

    # Three rows in the current calendar month (datetime('now') default) summing to $4.20.
    _insert_job_with_costs(
        db,
        "job-spend",
        [("briefing", 1.50), ("resume_tailor", 2.00), ("cover_letter", 0.70)],
    )
    assert spend_this_month(db) == pytest.approx(4.20, rel=1e-3)


def test_spend_this_month_zero_when_empty(db: sqlite3.Connection) -> None:
    from findajob.cost_rollups import spend_this_month

    assert spend_this_month(db) == 0.0
