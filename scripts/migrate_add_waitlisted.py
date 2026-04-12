#!/usr/bin/env python3
"""One-time migration: add 'waitlisted' to the jobs.stage CHECK constraint.

SQLite cannot ALTER CHECK constraints in-place, so this script rebuilds the
jobs table by reading the existing schema from sqlite_master and patching
the CHECK constraint.  Safe to run multiple times — exits early if the
constraint already allows 'waitlisted'.

Usage:  python3 scripts/migrate_add_waitlisted.py
"""

import re
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from findajob.paths import BASE

DB_PATH = Path(BASE) / "data" / "pipeline.db"

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

    # ── Read existing schema from sqlite_master ──────────────────────────
    original_ddl = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='jobs'").fetchone()[0]

    # Patch: insert 'waitlisted' after 'materials_drafted' in the stage CHECK
    old_fragment = "'materials_drafted', 'applied'"
    new_fragment = "'materials_drafted', 'waitlisted', 'applied'"
    if old_fragment not in original_ddl:
        print("ERROR: Could not find expected stage CHECK fragment in schema.", file=sys.stderr)
        print(f"  Looking for: {old_fragment}", file=sys.stderr)
        conn.close()
        sys.exit(1)

    patched_ddl = original_ddl.replace(old_fragment, new_fragment, 1)
    # Rename to jobs_new for the swap
    patched_ddl = re.sub(r"^CREATE TABLE jobs\b", "CREATE TABLE jobs_new", patched_ddl, count=1)

    # ── Get column list from existing table ──────────────────────────────
    cols = [row[1] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()]
    col_list = ", ".join(cols)

    # ── Rebuild inside a transaction ─────────────────────────────────────
    row_count_before = conn.execute("SELECT count(*) FROM jobs").fetchone()[0]
    print(f"Rows before migration: {row_count_before}")

    conn.execute("BEGIN")
    try:
        conn.execute(patched_ddl)
        conn.execute(f"INSERT INTO jobs_new ({col_list}) SELECT {col_list} FROM jobs")

        row_count_after = conn.execute("SELECT count(*) FROM jobs_new").fetchone()[0]
        if row_count_after != row_count_before:
            raise RuntimeError(f"Row count mismatch: jobs={row_count_before}, jobs_new={row_count_after}")

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
