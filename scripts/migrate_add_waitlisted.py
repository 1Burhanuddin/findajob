#!/usr/bin/env python3
"""One-time migration: add 'waitlisted' to the jobs.stage CHECK constraint.

SQLite cannot ALTER CHECK constraints in-place, so this script rebuilds the
jobs table with the new constraint.  Safe to run multiple times — exits early
if the constraint already allows 'waitlisted'.

Usage:  python3 scripts/migrate_add_waitlisted.py
"""

import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from findajob.paths import BASE

DB_PATH = Path(BASE) / "data" / "pipeline.db"

# ── The new CREATE TABLE DDL (identical to init_db.py after this migration) ──

CREATE_JOBS_NEW = """\
CREATE TABLE jobs_new (
    id TEXT PRIMARY KEY,
    fingerprint TEXT UNIQUE NOT NULL,
    url TEXT NOT NULL,
    title TEXT NOT NULL,
    company TEXT NOT NULL,
    location TEXT DEFAULT '',
    source TEXT NOT NULL,
    raw_jd_text TEXT,

    relevance_score INTEGER CHECK(relevance_score BETWEEN 1 AND 10),
    interview_likelihood INTEGER CHECK(interview_likelihood BETWEEN 1 AND 10),
    strengths_alignment TEXT,
    industry_sector TEXT,
    comp_estimate TEXT DEFAULT '',
    ai_notes TEXT,
    score_status TEXT CHECK(score_status IN ('scored', 'manual_review', 'needs_info')),
    score_flag_reason TEXT,
    remote_status TEXT DEFAULT 'Unknown',

    network_depth INTEGER DEFAULT 0,
    known_contacts TEXT DEFAULT '',
    stage TEXT DEFAULT 'discovered' CHECK(stage IN (
        'discovered', 'enriched', 'scored', 'manual_review',
        'prep_in_progress', 'materials_drafted', 'waitlisted', 'applied',
        'response_received', 'interview', 'offer', 'rejected', 'withdrawn'
    )),
    stage_updated TEXT,
    status TEXT DEFAULT 'active' CHECK(status IN (
        'active', 'manual_review', 'skipped', 'applied',
        'rejected', 'interviewing', 'offer'
    )),
    apply_flag INTEGER DEFAULT 0,
    reject_reason TEXT DEFAULT '',
    prep_folder_path TEXT,
    gdrive_folder_url TEXT,
    fit_score REAL,
    probability_score REAL,

    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    dupe_of TEXT DEFAULT ''
)"""

INDICES = [
    "CREATE INDEX idx_jobs_fingerprint ON jobs(fingerprint)",
    "CREATE INDEX idx_jobs_stage ON jobs(stage)",
    "CREATE INDEX idx_jobs_apply_flag ON jobs(apply_flag)",
    "CREATE INDEX idx_jobs_updated ON jobs(updated_at)",
]


def already_migrated(conn: sqlite3.Connection) -> bool:
    """Return True if the stage constraint already accepts 'waitlisted'."""
    try:
        conn.execute(
            "INSERT INTO jobs (id, fingerprint, url, title, company, source, stage) "
            "VALUES ('__migration_test__', '__mt__', '', '', '', '', 'waitlisted')"
        )
        conn.execute("DELETE FROM jobs WHERE id = '__migration_test__'")
        conn.rollback()
        return True
    except sqlite3.IntegrityError:
        conn.rollback()
        return False


def migrate() -> None:
    if not DB_PATH.exists():
        print(f"ERROR: DB not found at {DB_PATH}", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA foreign_keys = OFF")

    # ── Idempotency check ────────────────────────────────────────────────
    if already_migrated(conn):
        print("Migration already applied — 'waitlisted' is accepted. Nothing to do.")
        conn.close()
        return

    # ── Backup (only when migration is actually needed) ──────────────────
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = DB_PATH.with_suffix(f".db.bak.{ts}")
    shutil.copy2(DB_PATH, backup)
    print(f"Backup: {backup}")

    # ── Get column list from existing table ──────────────────────────────
    cols = [row[1] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()]
    col_list = ", ".join(cols)

    # ── Rebuild inside a transaction ─────────────────────────────────────
    row_count_before = conn.execute("SELECT count(*) FROM jobs").fetchone()[0]
    print(f"Rows before migration: {row_count_before}")

    conn.execute("BEGIN")
    try:
        conn.execute(CREATE_JOBS_NEW)
        conn.execute(f"INSERT INTO jobs_new ({col_list}) SELECT {col_list} FROM jobs")

        row_count_after = conn.execute("SELECT count(*) FROM jobs_new").fetchone()[0]
        if row_count_after != row_count_before:
            raise RuntimeError(
                f"Row count mismatch: jobs={row_count_before}, jobs_new={row_count_after}"
            )

        conn.execute("DROP TABLE jobs")
        conn.execute("ALTER TABLE jobs_new RENAME TO jobs")

        for idx_sql in INDICES:
            conn.execute(idx_sql)

        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()

    # ── Verify ───────────────────────────────────────────────────────────
    conn = sqlite3.connect(str(DB_PATH))
    integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
    if integrity != "ok":
        print(f"WARNING: integrity_check returned: {integrity}", file=sys.stderr)
        conn.close()
        sys.exit(1)

    final_count = conn.execute("SELECT count(*) FROM jobs").fetchone()[0]
    conn.close()
    print(f"Rows after migration: {final_count}")
    print(f"Integrity check: {integrity}")
    print("Migration complete — 'waitlisted' stage added.")


if __name__ == "__main__":
    migrate()
