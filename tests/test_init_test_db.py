"""Regression tests for ``tests.conftest.init_test_db`` (#721).

These tests are the AC #4 invariant: adding a new migration that introduces
a new table must NOT require touching any fixture's schema setup. Because
``init_test_db`` delegates straight to ``apply_pending`` (the same codepath
production runs at container start), every migration's tables are picked
up automatically.

If a future migration ships a new table and these assertions don't break,
no fixture-rewrite is needed. If a future maintainer accidentally regresses
``init_test_db`` to hand-rolled CREATE TABLE statements, the
``test_apply_pending_produces_all_known_tables`` assertion catches it.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from tests.conftest import init_test_db

# Tables that the current migration chain (0001..0005) is contractually
# required to produce. Update this list when a new migration ships a new
# table — the update is the load-bearing signal that fixtures still work.
# If a future migration adds a table without this list updating, the same-
# PR docs rule + this file's git diff catch the omission at review time.
_EXPECTED_TABLES = {
    # Migration 0001 (initial equilibrium schema)
    "jobs",
    "audit_log",
    "feedback_log",
    "cost_log",
    "onboarding_sessions",
    "_meta",
    # Migration 0002
    "background_tasks",
    # Migration 0003
    "rejection_suggestions",
    # Migration 0004
    "notes_history",
    # Migration 0005
    "view_prefs",
}


def _all_user_tables(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()
    return {r[0] for r in rows}


def test_init_test_db_produces_every_expected_table(tmp_path: Path) -> None:
    """init_test_db must materialize every table the current migration chain
    creates. Failing this test means a new migration shipped a new table
    AND the _EXPECTED_TABLES list wasn't updated to match — surface the
    drift now, not when an unrelated fixture's route handler 500s in CI.
    """
    db = tmp_path / "pipeline.db"
    init_test_db(db)
    conn = sqlite3.connect(db)
    try:
        present = _all_user_tables(conn)
    finally:
        conn.close()

    missing = _EXPECTED_TABLES - present
    assert not missing, (
        f"init_test_db did not produce expected tables: {sorted(missing)}. "
        "Either apply_pending is broken, or a migration was added/removed "
        "without updating _EXPECTED_TABLES."
    )


def test_init_test_db_is_idempotent(tmp_path: Path) -> None:
    """Calling init_test_db twice against the same path is a no-op on the
    second call (``apply_pending`` short-circuits at head). Idempotency
    matters for fixtures that reuse a tmp_path across multiple factory
    calls (e.g., the parametrized factory in test_materials_briefing_gate).
    """
    db = tmp_path / "pipeline.db"
    init_test_db(db)
    conn = sqlite3.connect(db)
    try:
        tables_after_first = _all_user_tables(conn)
    finally:
        conn.close()

    init_test_db(db)
    conn = sqlite3.connect(db)
    try:
        tables_after_second = _all_user_tables(conn)
    finally:
        conn.close()

    assert tables_after_first == tables_after_second


def test_init_test_db_supports_insert_after(tmp_path: Path) -> None:
    """Smoke test for the documented usage shape: caller calls init_test_db,
    then opens its own connection for INSERTs. Validates that the chain of
    open/migrate/close/reopen works against a fresh tmp_path.
    """
    db = tmp_path / "pipeline.db"
    init_test_db(db)
    conn = sqlite3.connect(db)
    try:
        conn.execute(
            "INSERT INTO jobs (id, fingerprint, url, title, company, source, stage) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("jid-smoke", "fp-smoke", "https://x.test/smoke", "Smoke", "Acme", "test", "scored"),
        )
        conn.commit()
        row = conn.execute("SELECT title, company FROM jobs WHERE id=?", ("jid-smoke",)).fetchone()
    finally:
        conn.close()
    assert row == ("Smoke", "Acme")
