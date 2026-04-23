# Ingest Duplicate Smart Handling — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When `/ingest/manual` hits an existing row, branch on its stage — link post-application jobs to the right board tab, and automatically resurface pre-application jobs onto the Dashboard.

**Architecture:** Three new action helpers in `findajob.actions` handle the mutations (un-reject, reactivate, refresh). A new `_handle_duplicate()` private function in `findajob.ingest` fetches the full existing row, calls the right helper, and returns an enriched `IngestResult`. The route handler and template render stage-appropriate messages and deep links.

**Tech Stack:** Python / SQLite / FastAPI / HTMX / Jinja2 / pytest

---

## File Map

| File | Change |
|---|---|
| `src/findajob/ingest.py` | Extend `IngestResult`; add `_handle_duplicate()`; update `ingest_manual_job()` |
| `src/findajob/actions.py` | Add `un_reject_job()`, `reactivate_from_ingest()`, `refresh_active_job()` |
| `src/findajob/web/routes/ingest.py` | Map new `result.status` values to `_render_result()` calls |
| `src/findajob/web/templates/ingest/_result.html` | Render `already_applied`, `not_selected`, `resurfaced` outcomes |
| `tests/test_ingest.py` | Add audit_log/feedback_log to SCHEMA; add tests for each `_handle_duplicate` branch |
| `tests/test_actions_resurface.py` | New file — unit tests for the three new action helpers |
| `tests/test_web_ingest.py` | Add audit_log/feedback_log to SCHEMA; add integration tests for new outcomes |

---

## Task 1: Extend `IngestResult` and test schemas

**Files:**
- Modify: `src/findajob/ingest.py:48-63`
- Modify: `tests/test_ingest.py:19-42`
- Modify: `tests/test_web_ingest.py:20-43`

- [ ] **Step 1: Extend `IngestResult` in `src/findajob/ingest.py`**

Replace the existing `IngestResult` dataclass (lines 48–63) with:

```python
@dataclass(frozen=True)
class IngestResult:
    """Outcome of a single ``ingest_manual_job`` call.

    - ``status="ingested"``: new row inserted; ``job_id`` is the new id.
    - ``status="duplicate"``: existing row matched by an unhandled state
      (should not occur in practice after _handle_duplicate is wired up).
    - ``status="resurfaced"``: existing row was un-rejected / reactivated /
      refreshed; job is now on the Dashboard.
    - ``status="already_applied"``: existing row is post-application; no
      mutation. Link to /board/applied.
    - ``status="not_selected"``: company rejected the application; no
      mutation. Link to /board/rejected and materials folder.
    """

    status: Literal["ingested", "duplicate", "resurfaced", "already_applied", "not_selected"]
    job_id: str
    company: str
    title: str
    fingerprint: str | None = None
    existing_match: str | None = None   # "strict" / "url" / "loose"
    existing_stage: str | None = None   # stage of the row at submission time
    prep_folder_path: str | None = None # for not_selected materials link
    prep_launched: bool = False
```

- [ ] **Step 2: Add `audit_log` and `feedback_log` to SCHEMA in `tests/test_ingest.py`**

After the closing `);` of the `jobs` table in `SCHEMA`, append:

```python
SCHEMA = """
CREATE TABLE jobs (
    id TEXT PRIMARY KEY,
    fingerprint TEXT UNIQUE NOT NULL,
    loose_fingerprint TEXT,
    url TEXT NOT NULL,
    title TEXT NOT NULL,
    company TEXT NOT NULL,
    location TEXT DEFAULT '',
    source TEXT NOT NULL,
    raw_jd_text TEXT,
    remote_status TEXT DEFAULT 'Unknown',
    known_contacts TEXT DEFAULT '',
    ai_notes TEXT,
    relevance_score INTEGER,
    stage TEXT DEFAULT 'discovered',
    apply_flag INTEGER DEFAULT 0,
    reject_reason TEXT DEFAULT '',
    prep_folder_path TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    dupe_of TEXT DEFAULT ''
);
CREATE TABLE audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL,
    field_changed TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT,
    changed_at TEXT DEFAULT (datetime('now')),
    changed_by TEXT DEFAULT 'system'
);
CREATE TABLE feedback_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL,
    title TEXT NOT NULL,
    company TEXT NOT NULL,
    relevance_score INTEGER,
    reject_reason TEXT NOT NULL,
    jd_excerpt TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now'))
);
"""
```

- [ ] **Step 3: Apply the same SCHEMA addition to `tests/test_web_ingest.py`**

Same pattern as Step 2 — append `audit_log` and `feedback_log` CREATE statements to the `SCHEMA` string in that file.

- [ ] **Step 4: Run existing tests to confirm no regressions from the dataclass change**

```bash
uv run pytest tests/test_ingest.py tests/test_web_ingest.py -v
```

Expected: all existing tests pass (new fields are optional with defaults).

- [ ] **Step 5: Commit**

```bash
git add src/findajob/ingest.py tests/test_ingest.py tests/test_web_ingest.py
git commit -m "feat(ingest): extend IngestResult with resurface status fields"
```

---

## Task 2: Three action helpers in `actions.py` (TDD)

**Files:**
- Create: `tests/test_actions_resurface.py`
- Modify: `src/findajob/actions.py` (append after `reset_prep_to_scored`)

### Step 1: Write failing tests

- [ ] **Step 1: Create `tests/test_actions_resurface.py` with the full test suite**

```python
"""Tests for the three ingest-path action helpers:
un_reject_job, reactivate_from_ingest, refresh_active_job."""

from __future__ import annotations

import os
import sqlite3
import uuid

import pytest

from findajob import actions as actions_mod

SCHEMA = """
CREATE TABLE jobs (
    id TEXT PRIMARY KEY,
    fingerprint TEXT UNIQUE NOT NULL,
    url TEXT NOT NULL,
    title TEXT NOT NULL,
    company TEXT NOT NULL,
    location TEXT DEFAULT '',
    source TEXT NOT NULL DEFAULT 'test',
    raw_jd_text TEXT,
    remote_status TEXT DEFAULT 'Unknown',
    known_contacts TEXT DEFAULT '',
    ai_notes TEXT,
    relevance_score INTEGER DEFAULT 7,
    stage TEXT DEFAULT 'scored',
    apply_flag INTEGER DEFAULT 0,
    reject_reason TEXT DEFAULT '',
    prep_folder_path TEXT,
    updated_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL,
    field_changed TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT,
    changed_at TEXT DEFAULT (datetime('now')),
    changed_by TEXT DEFAULT 'system'
);
CREATE TABLE feedback_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL,
    title TEXT NOT NULL,
    company TEXT NOT NULL,
    relevance_score INTEGER,
    reject_reason TEXT NOT NULL,
    jd_excerpt TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now'))
);
"""


@pytest.fixture()
def db(tmp_path, monkeypatch):
    import findajob.utils as utils_mod
    monkeypatch.setattr(utils_mod, "LOG_PATH", str(tmp_path / "events.jsonl"))
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


@pytest.fixture()
def companies_dir(tmp_path, monkeypatch):
    base = tmp_path / "companies"
    base.mkdir()
    (base / "_rejected").mkdir()
    (base / "_waitlisted").mkdir()
    monkeypatch.setattr(actions_mod, "BASE", str(tmp_path))
    return base


def _insert_job(conn, *, stage="scored", score=5, folder=None, reject_reason=""):
    job_id = str(uuid.uuid4())[:8]
    fp = f"fp_{job_id}"
    conn.execute(
        """INSERT INTO jobs
           (id, fingerprint, url, title, company, relevance_score, stage,
            prep_folder_path, reject_reason)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (job_id, fp, f"https://example.com/{job_id}",
         "Data Center Manager", "Acme Corp", score, stage, folder, reject_reason),
    )
    conn.commit()
    return conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()


# ── un_reject_job ────────────────────────────────────────────────────────────

class TestUnRejectJob:
    def test_stage_set_to_scored(self, db, companies_dir):
        job = _insert_job(db, stage="rejected", score=5, reject_reason="Low Fit Score")
        actions_mod.un_reject_job(db, job, {})
        row = db.execute("SELECT stage, relevance_score, reject_reason FROM jobs WHERE id=?", (job["id"],)).fetchone()
        assert row["stage"] == "scored"
        assert row["relevance_score"] == 8
        assert row["reject_reason"] == ""

    def test_feedback_log_rows_deleted(self, db, companies_dir):
        job = _insert_job(db, stage="rejected", reject_reason="Low Fit Score")
        db.execute(
            "INSERT INTO feedback_log (job_id, title, company, relevance_score, reject_reason) VALUES (?,?,?,?,?)",
            (job["id"], "Data Center Manager", "Acme Corp", 5, "Low Fit Score"),
        )
        db.commit()
        assert db.execute("SELECT COUNT(*) FROM feedback_log WHERE job_id=?", (job["id"],)).fetchone()[0] == 1
        actions_mod.un_reject_job(db, job, {})
        assert db.execute("SELECT COUNT(*) FROM feedback_log WHERE job_id=?", (job["id"],)).fetchone()[0] == 0

    def test_audit_log_entry_written(self, db, companies_dir):
        job = _insert_job(db, stage="rejected", reject_reason="Bad Fit")
        actions_mod.un_reject_job(db, job, {})
        row = db.execute(
            "SELECT * FROM audit_log WHERE job_id=? AND field_changed='stage'", (job["id"],)
        ).fetchone()
        assert row is not None
        assert row["old_value"] == "rejected"
        assert row["new_value"] == "scored"

    def test_folder_moved_from_rejected(self, db, companies_dir):
        rejected_folder = companies_dir / "_rejected" / "Acme_Corp_Data_Center_Manager"
        rejected_folder.mkdir()
        job = _insert_job(db, stage="rejected", folder=str(rejected_folder))
        actions_mod.un_reject_job(db, job, {})
        assert not rejected_folder.exists()
        dest = companies_dir / "Acme_Corp_Data_Center_Manager"
        assert dest.is_dir()
        row = db.execute("SELECT prep_folder_path FROM jobs WHERE id=?", (job["id"],)).fetchone()
        assert row["prep_folder_path"] == str(dest)

    def test_non_blank_fields_overwritten(self, db, companies_dir):
        job = _insert_job(db, stage="rejected")
        actions_mod.un_reject_job(db, job, {
            "url": "https://new.example.com/job",
            "location": "Austin, TX",
            "remote_status": "Hybrid",
            "raw_jd_text": "New JD text",
            "notes": "New notes",
            "known_contacts": "Jane Doe",
        })
        row = db.execute(
            "SELECT url, location, remote_status, raw_jd_text, ai_notes, known_contacts FROM jobs WHERE id=?",
            (job["id"],),
        ).fetchone()
        assert row["url"] == "https://new.example.com/job"
        assert row["location"] == "Austin, TX"
        assert row["remote_status"] == "Hybrid"
        assert row["raw_jd_text"] == "New JD text"
        assert row["ai_notes"] == "New notes"
        assert row["known_contacts"] == "Jane Doe"

    def test_blank_submitted_field_does_not_clobber_existing(self, db, companies_dir):
        job = _insert_job(db, stage="rejected")
        db.execute("UPDATE jobs SET url='https://original.com/job', location='Menlo Park, CA' WHERE id=?", (job["id"],))
        db.commit()
        job = db.execute("SELECT * FROM jobs WHERE id=?", (job["id"],)).fetchone()
        actions_mod.un_reject_job(db, job, {"url": "", "location": ""})
        row = db.execute("SELECT url, location FROM jobs WHERE id=?", (job["id"],)).fetchone()
        assert row["url"] == "https://original.com/job"
        assert row["location"] == "Menlo Park, CA"


# ── reactivate_from_ingest ───────────────────────────────────────────────────

class TestReactivateFromIngest:
    def test_stage_set_to_scored(self, db, companies_dir):
        job = _insert_job(db, stage="waitlisted", score=7)
        actions_mod.reactivate_from_ingest(db, job, {})
        row = db.execute("SELECT stage, relevance_score FROM jobs WHERE id=?", (job["id"],)).fetchone()
        assert row["stage"] == "scored"
        assert row["relevance_score"] == 8

    def test_folder_moved_from_waitlisted(self, db, companies_dir):
        waitlisted_folder = companies_dir / "_waitlisted" / "Acme_Corp_Data_Center"
        waitlisted_folder.mkdir()
        job = _insert_job(db, stage="waitlisted", folder=str(waitlisted_folder))
        actions_mod.reactivate_from_ingest(db, job, {})
        assert not waitlisted_folder.exists()
        dest = companies_dir / "Acme_Corp_Data_Center"
        assert dest.is_dir()
        row = db.execute("SELECT prep_folder_path FROM jobs WHERE id=?", (job["id"],)).fetchone()
        assert row["prep_folder_path"] == str(dest)

    def test_audit_log_entry_written(self, db, companies_dir):
        job = _insert_job(db, stage="waitlisted")
        actions_mod.reactivate_from_ingest(db, job, {})
        row = db.execute(
            "SELECT * FROM audit_log WHERE job_id=? AND field_changed='stage'", (job["id"],)
        ).fetchone()
        assert row is not None
        assert row["old_value"] == "waitlisted"
        assert row["new_value"] == "scored"

    def test_non_blank_fields_overwritten(self, db, companies_dir):
        job = _insert_job(db, stage="waitlisted")
        actions_mod.reactivate_from_ingest(db, job, {"url": "https://new.example.com/", "location": "Denver, CO"})
        row = db.execute("SELECT url, location FROM jobs WHERE id=?", (job["id"],)).fetchone()
        assert row["url"] == "https://new.example.com/"
        assert row["location"] == "Denver, CO"

    def test_blank_submitted_field_does_not_clobber_existing(self, db, companies_dir):
        job = _insert_job(db, stage="waitlisted")
        db.execute("UPDATE jobs SET url='https://original.com/' WHERE id=?", (job["id"],))
        db.commit()
        job = db.execute("SELECT * FROM jobs WHERE id=?", (job["id"],)).fetchone()
        actions_mod.reactivate_from_ingest(db, job, {"url": ""})
        row = db.execute("SELECT url FROM jobs WHERE id=?", (job["id"],)).fetchone()
        assert row["url"] == "https://original.com/"


# ── refresh_active_job ───────────────────────────────────────────────────────

class TestRefreshActiveJob:
    def test_low_score_bumped_to_8(self, db, companies_dir):
        job = _insert_job(db, stage="scored", score=5)
        actions_mod.refresh_active_job(db, job, {})
        row = db.execute("SELECT relevance_score FROM jobs WHERE id=?", (job["id"],)).fetchone()
        assert row["relevance_score"] == 8

    def test_score_8_not_changed(self, db, companies_dir):
        job = _insert_job(db, stage="scored", score=8)
        actions_mod.refresh_active_job(db, job, {})
        row = db.execute("SELECT relevance_score FROM jobs WHERE id=?", (job["id"],)).fetchone()
        assert row["relevance_score"] == 8

    def test_manual_review_promoted_to_scored(self, db, companies_dir):
        job = _insert_job(db, stage="manual_review", score=6)
        actions_mod.refresh_active_job(db, job, {})
        row = db.execute("SELECT stage FROM jobs WHERE id=?", (job["id"],)).fetchone()
        assert row["stage"] == "scored"

    def test_already_scored_stage_unchanged(self, db, companies_dir):
        job = _insert_job(db, stage="scored", score=9)
        actions_mod.refresh_active_job(db, job, {})
        row = db.execute("SELECT stage FROM jobs WHERE id=?", (job["id"],)).fetchone()
        assert row["stage"] == "scored"

    def test_non_blank_fields_overwritten(self, db, companies_dir):
        job = _insert_job(db, stage="scored")
        actions_mod.refresh_active_job(db, job, {"raw_jd_text": "Updated JD"})
        row = db.execute("SELECT raw_jd_text FROM jobs WHERE id=?", (job["id"],)).fetchone()
        assert row["raw_jd_text"] == "Updated JD"
```

- [ ] **Step 2: Run tests to confirm they all fail with ImportError / AttributeError**

```bash
uv run pytest tests/test_actions_resurface.py -v 2>&1 | head -30
```

Expected: `AttributeError: module 'findajob.actions' has no attribute 'un_reject_job'`

- [ ] **Step 3: Implement the three action helpers in `src/findajob/actions.py`**

Append after the `reset_prep_to_scored` function:

```python
_OVERWRITE_FIELD_MAP: dict[str, str] = {
    "url": "url",
    "location": "location",
    "remote_status": "remote_status",
    "raw_jd_text": "raw_jd_text",
    "notes": "ai_notes",
    "known_contacts": "known_contacts",
}


def _apply_overwrite_fields(set_parts: list[str], params: list, overwrite_fields: dict[str, str]) -> None:
    """Append non-blank submitted fields to a SET clause builder."""
    for key, col in _OVERWRITE_FIELD_MAP.items():
        if overwrite_fields.get(key):
            set_parts.append(f"{col}=?")
            params.append(overwrite_fields[key])


def un_reject_job(conn: sqlite3.Connection, job: Any, overwrite_fields: dict[str, str]) -> None:
    """Reverse a user rejection: restore to scored, delete feedback_log rows.

    Clears reject_reason, sets relevance_score=8, overwrites non-blank
    submitted fields, moves prep folder from _rejected/ back to companies/.
    Deletes feedback_log rows so the scorer's feedback loop stays clean.
    """
    now = datetime.now(UTC).isoformat()

    set_parts = ["stage='scored'", "reject_reason=''", "relevance_score=8", "updated_at=?"]
    params: list = [now]
    _apply_overwrite_fields(set_parts, params, overwrite_fields)
    params.append(job["id"])

    conn.execute(f"UPDATE jobs SET {', '.join(set_parts)} WHERE id=?", params)
    conn.execute("DELETE FROM feedback_log WHERE job_id=?", (job["id"],))

    folder = job["prep_folder_path"] if job["prep_folder_path"] else None
    if folder and os.path.isdir(folder):
        dest = os.path.join(BASE, "companies", os.path.basename(folder))
        shutil.move(folder, dest)
        conn.execute("UPDATE jobs SET prep_folder_path=? WHERE id=?", (dest, job["id"]))
        log_event("folder_moved_from_rejected", job_id=job["id"], folder=os.path.basename(folder))

    conn.commit()
    write_audit(conn, job["id"], "stage", "rejected", "scored")
    write_audit(conn, job["id"], "reject_reason", job["reject_reason"] or "", "")
    log_event("job_un_rejected", job_id=job["id"], company=job["company"], title=job["title"])


def reactivate_from_ingest(conn: sqlite3.Connection, job: Any, overwrite_fields: dict[str, str]) -> None:
    """Reactivate a waitlisted job via manual ingest.

    Sets stage=scored, relevance_score=8, overwrites non-blank submitted
    fields, moves prep folder from _waitlisted/ back to companies/.
    """
    now = datetime.now(UTC).isoformat()

    set_parts = ["stage='scored'", "relevance_score=8", "updated_at=?"]
    params: list = [now]
    _apply_overwrite_fields(set_parts, params, overwrite_fields)
    params.append(job["id"])

    conn.execute(f"UPDATE jobs SET {', '.join(set_parts)} WHERE id=?", params)

    folder = job["prep_folder_path"] if job["prep_folder_path"] else None
    if folder and os.path.isdir(folder):
        dest = os.path.join(BASE, "companies", os.path.basename(folder))
        shutil.move(folder, dest)
        conn.execute("UPDATE jobs SET prep_folder_path=? WHERE id=?", (dest, job["id"]))
        log_event("folder_moved_from_waitlisted", job_id=job["id"], folder=os.path.basename(folder))

    conn.commit()
    write_audit(conn, job["id"], "stage", "waitlisted", "scored")
    log_event("job_reactivated_via_ingest", job_id=job["id"], company=job["company"], title=job["title"])


def refresh_active_job(conn: sqlite3.Connection, job: Any, overwrite_fields: dict[str, str]) -> None:
    """Refresh an already-visible job submitted again via ingest.

    Bumps relevance_score to 8 if below 8. Promotes manual_review → scored.
    Overwrites non-blank submitted fields. No folder moves.
    """
    now = datetime.now(UTC).isoformat()
    old_stage = job["stage"]
    new_stage = "scored" if old_stage == "manual_review" else old_stage

    set_parts = ["updated_at=?"]
    params: list = [now]

    if (job["relevance_score"] or 0) < 8:
        set_parts.append("relevance_score=8")
    if new_stage != old_stage:
        set_parts.append("stage=?")
        params.append(new_stage)

    _apply_overwrite_fields(set_parts, params, overwrite_fields)
    params.append(job["id"])

    conn.execute(f"UPDATE jobs SET {', '.join(set_parts)} WHERE id=?", params)
    conn.commit()

    if new_stage != old_stage:
        write_audit(conn, job["id"], "stage", old_stage, new_stage)
    log_event(
        "job_refreshed_via_ingest",
        job_id=job["id"],
        company=job["company"],
        title=job["title"],
        old_stage=old_stage,
    )
```

- [ ] **Step 4: Run tests — all must pass**

```bash
uv run pytest tests/test_actions_resurface.py -v
```

Expected: all 16 tests pass.

- [ ] **Step 5: Confirm existing action tests still pass**

```bash
uv run pytest tests/test_waitlist.py -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/findajob/actions.py tests/test_actions_resurface.py
git commit -m "feat(actions): un_reject_job, reactivate_from_ingest, refresh_active_job"
```

---

## Task 3: `_handle_duplicate()` in `ingest.py` + unit tests

**Files:**
- Modify: `src/findajob/ingest.py`
- Modify: `tests/test_ingest.py`

- [ ] **Step 1: Write failing tests in `tests/test_ingest.py`**

Add a `_insert_existing` helper and the duplicate-branch tests after `test_source_label_threaded_through`:

```python
def _insert_existing(conn: sqlite3.Connection, *, stage: str, score: int = 5,
                     company: str = "Acme Data Centers",
                     title: str = "Senior Operations Engineer",
                     location: str = "United States",
                     reject_reason: str = "", folder: str | None = None) -> sqlite3.Row:
    """Insert a pre-existing job at a given stage (imitates a row that triage or
    a prior ingest created)."""
    from findajob.cleaning import fingerprint, loose_fingerprint, clean_company, clean_title
    co = clean_company(company)
    ti = clean_title(title)
    fp = fingerprint(ti, co, location)
    lfp = loose_fingerprint(ti, co)
    job_id = f"triage-{fp}"
    conn.execute(
        """INSERT INTO jobs
           (id, fingerprint, loose_fingerprint, url, title, company, location, source,
            relevance_score, stage, apply_flag, reject_reason, prep_folder_path)
           VALUES (?, ?, ?, ?, ?, ?, ?, 'triage', ?, ?, 0, ?, ?)""",
        (job_id, fp, lfp, f"https://example.com/{fp}", ti, co, location, score, stage,
         reject_reason, folder),
    )
    conn.commit()
    return conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()


class TestHandleDuplicate:
    """_handle_duplicate branch tests — each exercises one stage category."""

    def test_applied_stage_returns_already_applied(self, conn, popen_calls):
        _insert_existing(conn, stage="applied", score=8)
        result = _submit(conn, location="United States")
        assert result.status == "already_applied"
        assert result.existing_stage == "applied"
        # No new row
        assert conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 1

    def test_interview_stage_returns_already_applied(self, conn, popen_calls):
        _insert_existing(conn, stage="interview", score=8)
        result = _submit(conn, location="United States")
        assert result.status == "already_applied"

    def test_offer_stage_returns_already_applied(self, conn, popen_calls):
        _insert_existing(conn, stage="offer", score=8)
        result = _submit(conn, location="United States")
        assert result.status == "already_applied"

    def test_withdrew_stage_returns_already_applied(self, conn, popen_calls):
        _insert_existing(conn, stage="withdrew", score=8)
        result = _submit(conn, location="United States")
        assert result.status == "already_applied"

    def test_not_selected_returns_not_selected_with_folder(self, conn, popen_calls, tmp_path):
        folder = str(tmp_path / "companies" / "_applied" / "Acme_Senior_2026-01-01_120000")
        _insert_existing(conn, stage="not_selected", score=8, folder=folder)
        result = _submit(conn, location="United States")
        assert result.status == "not_selected"
        assert result.existing_stage == "not_selected"
        assert result.prep_folder_path == folder
        assert conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 1

    def test_rejected_returns_resurfaced_and_updates_stage(self, conn, popen_calls):
        _insert_existing(conn, stage="rejected", score=4, reject_reason="Low Fit Score")
        # Seed a feedback_log row that should be deleted
        conn.execute(
            "INSERT INTO feedback_log (job_id, title, company, relevance_score, reject_reason)"
            " VALUES ('triage-' || ?, 'Senior Operations Engineer', 'Acme Data Centers', 4, 'Low Fit Score')",
            (conn.execute("SELECT fingerprint FROM jobs").fetchone()[0],),
        )
        conn.commit()
        result = _submit(conn, location="United States")
        assert result.status == "resurfaced"
        assert result.existing_stage == "rejected"
        row = conn.execute("SELECT stage, relevance_score, reject_reason FROM jobs").fetchone()
        assert row["stage"] == "scored"
        assert row["relevance_score"] == 8
        assert row["reject_reason"] == ""
        assert conn.execute("SELECT COUNT(*) FROM feedback_log").fetchone()[0] == 0

    def test_waitlisted_returns_resurfaced_and_updates_stage(self, conn, popen_calls):
        _insert_existing(conn, stage="waitlisted", score=7)
        result = _submit(conn, location="United States")
        assert result.status == "resurfaced"
        assert result.existing_stage == "waitlisted"
        row = conn.execute("SELECT stage, relevance_score FROM jobs").fetchone()
        assert row["stage"] == "scored"
        assert row["relevance_score"] == 8

    def test_scored_low_returns_resurfaced_and_bumps_score(self, conn, popen_calls):
        _insert_existing(conn, stage="scored", score=4)
        result = _submit(conn, location="United States")
        assert result.status == "resurfaced"
        row = conn.execute("SELECT relevance_score FROM jobs").fetchone()
        assert row["relevance_score"] == 8

    def test_manual_review_returns_resurfaced_and_promotes_stage(self, conn, popen_calls):
        _insert_existing(conn, stage="manual_review", score=6)
        result = _submit(conn, location="United States")
        assert result.status == "resurfaced"
        row = conn.execute("SELECT stage FROM jobs").fetchone()
        assert row["stage"] == "scored"

    def test_field_overwrite_on_resurface(self, conn, popen_calls):
        _insert_existing(conn, stage="rejected", score=4)
        result = _submit(conn, location="United States", raw_jd_text="Brand new JD content")
        assert result.status == "resurfaced"
        row = conn.execute("SELECT raw_jd_text FROM jobs").fetchone()
        assert row["raw_jd_text"] == "Brand new JD content"

    def test_fingerprint_populated_on_result(self, conn, popen_calls):
        _insert_existing(conn, stage="applied", score=8)
        result = _submit(conn, location="United States")
        assert result.fingerprint is not None

    def test_fingerprint_populated_on_fresh_insert(self, conn, popen_calls):
        result = _submit(conn)
        assert result.fingerprint is not None
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
uv run pytest tests/test_ingest.py::TestHandleDuplicate -v 2>&1 | head -30
```

Expected: `AssertionError` — `result.status == "duplicate"` but tests expect `"already_applied"`, `"resurfaced"`, etc.

- [ ] **Step 3: Implement `_handle_duplicate()` and wire it into `ingest_manual_job()` in `src/findajob/ingest.py`**

At the top of `ingest.py`, add the import:

```python
from findajob.actions import refresh_active_job, reactivate_from_ingest, un_reject_job
```

Then add the constant and function before `ingest_manual_job`:

```python
_APPLIED_STAGES = frozenset({"applied", "interview", "offer", "withdrew"})


def _handle_duplicate(
    conn: sqlite3.Connection,
    existing_id: str,
    overwrite_fields: dict[str, str],
) -> IngestResult:
    """Fetch the existing row and route to the right resurface path."""
    row = conn.execute(
        """SELECT id, fingerprint, title, company, stage, relevance_score,
                  reject_reason, prep_folder_path
           FROM jobs WHERE id=?""",
        (existing_id,),
    ).fetchone()

    stage = row["stage"]
    common = {
        "job_id": existing_id,
        "fingerprint": row["fingerprint"],
        "company": row["company"],
        "title": row["title"],
        "existing_stage": stage,
    }

    if stage in _APPLIED_STAGES:
        return IngestResult(status="already_applied", **common)

    if stage == "not_selected":
        return IngestResult(
            status="not_selected",
            prep_folder_path=row["prep_folder_path"],
            **common,
        )

    if stage == "rejected":
        un_reject_job(conn, row, overwrite_fields)
        return IngestResult(status="resurfaced", **common)

    if stage == "waitlisted":
        reactivate_from_ingest(conn, row, overwrite_fields)
        return IngestResult(status="resurfaced", **common)

    # scored / manual_review / prep_in_progress / materials_drafted
    refresh_active_job(conn, row, overwrite_fields)
    return IngestResult(status="resurfaced", **common)
```

In `ingest_manual_job`, replace the current duplicate early-return block:

```python
    if existing:
        return IngestResult(
            status="duplicate",
            job_id=existing["id"],
            company=company,
            title=title,
            existing_match=matched_tier,
        )
```

with:

```python
    if existing:
        overwrite_fields = {
            "url": url,
            "location": location,
            "remote_status": remote_status,
            "raw_jd_text": raw_jd_text,
            "notes": notes,
            "known_contacts": known_contacts,
        }
        return _handle_duplicate(conn, existing["id"], overwrite_fields)
```

Also add `fingerprint=fp` to the final `IngestResult` in `ingest_manual_job` (the `status="ingested"` return):

```python
    return IngestResult(
        status="ingested",
        job_id=job_id,
        fingerprint=fp,
        company=company,
        title=title,
        prep_launched=prep_launched,
    )
```

- [ ] **Step 4: Run all ingest unit tests**

```bash
uv run pytest tests/test_ingest.py -v
```

Expected: all tests pass including the new `TestHandleDuplicate` class.

- [ ] **Step 5: Commit**

```bash
git add src/findajob/ingest.py tests/test_ingest.py
git commit -m "feat(ingest): _handle_duplicate routes dups by stage; resurface pre-application jobs"
```

---

## Task 4: Update route handler and template

**Files:**
- Modify: `src/findajob/web/routes/ingest.py:98-107`
- Modify: `src/findajob/web/templates/ingest/_result.html`

- [ ] **Step 1: Update the route handler in `src/findajob/web/routes/ingest.py`**

Replace the current duplicate block:

```python
    if result.status == "duplicate":
        return _render_result(
            request,
            outcome="duplicate",
            message=(
                f"Already in DB: {result.company} / {result.title} "
                f"(matched by {result.existing_match}). No new row created."
            ),
            result=result,
        )
```

with:

```python
    if result.status == "already_applied":
        return _render_result(
            request,
            outcome="already_applied",
            message=f"Already applied — {result.company} / {result.title}.",
            result=result,
        )

    if result.status == "not_selected":
        return _render_result(
            request,
            outcome="not_selected",
            message=(
                f"You were not selected for {result.company} / {result.title}. "
                "Here's where you left it:"
            ),
            result=result,
        )

    if result.status == "resurfaced":
        stage_label = result.existing_stage or "unknown"
        return _render_result(
            request,
            outcome="resurfaced",
            message=(
                f"Re-surfaced to Dashboard — {result.company} / {result.title} "
                f"(was {stage_label})."
            ),
            result=result,
        )

    if result.status == "duplicate":
        return _render_result(
            request,
            outcome="duplicate",
            message=(
                f"Already in DB: {result.company} / {result.title} "
                f"(matched by {result.existing_match}). No new row created."
            ),
            result=result,
        )
```

- [ ] **Step 2: Update `src/findajob/web/templates/ingest/_result.html`**

Replace the entire file:

```html
{# Ingest submit result partial — swapped into #ingest-result by HTMX. #}
{% set styles = {
  "success":        "border-emerald-300 bg-emerald-50 text-emerald-900",
  "resurfaced":     "border-emerald-300 bg-emerald-50 text-emerald-900",
  "duplicate":      "border-amber-300 bg-amber-50 text-amber-900",
  "already_applied":"border-blue-300 bg-blue-50 text-blue-900",
  "not_selected":   "border-slate-300 bg-slate-50 text-slate-700",
  "error":          "border-red-300 bg-red-50 text-red-900",
} %}
<div data-outcome="{{ outcome }}"
     class="border rounded p-3 text-sm {{ styles.get(outcome, 'border-slate-300 bg-slate-50 text-slate-900') }}">
  <p>{{ message }}</p>
  {% if outcome == "success" %}
    <p class="mt-2">
      <a href="/board/dashboard" class="underline font-medium">View on Dashboard →</a>
    </p>
  {% elif outcome == "resurfaced" %}
    <p class="mt-2">
      <a href="/board/dashboard" class="underline font-medium">View on Dashboard →</a>
    </p>
  {% elif outcome == "already_applied" %}
    <p class="mt-2">
      <a href="/board/applied" class="underline font-medium">View on Applied board →</a>
    </p>
  {% elif outcome == "not_selected" %}
    <p class="mt-2 flex gap-4 flex-wrap">
      <a href="/board/rejected" class="underline font-medium">Rejected Applications →</a>
      {% if result and result.fingerprint %}
      <a href="/materials/{{ result.fingerprint }}" class="underline font-medium">Materials folder →</a>
      {% endif %}
    </p>
  {% endif %}
</div>
```

- [ ] **Step 3: Run the full test suite to check for regressions**

```bash
uv run pytest tests/test_ingest.py tests/test_actions_resurface.py -v
```

Expected: all tests pass.

- [ ] **Step 4: Commit**

```bash
git add src/findajob/web/routes/ingest.py src/findajob/web/templates/ingest/_result.html
git commit -m "feat(web): ingest result partial renders resurface/applied/not-selected outcomes"
```

---

## Task 5: Integration tests for new outcomes

**Files:**
- Modify: `tests/test_web_ingest.py`

- [ ] **Step 1: Write integration tests for each new outcome**

Add after `test_generate_folder_deferred_when_prep_queue_full` in `tests/test_web_ingest.py`:

```python
def _insert_existing_job(db_path: str, *, stage: str, score: int = 8,
                          folder: str | None = None) -> None:
    """Seed a pre-existing job in the given stage directly into the DB."""
    from findajob.cleaning import fingerprint, loose_fingerprint, clean_company, clean_title
    co = clean_company("Acme Data Centers")
    ti = clean_title("Senior Operations Engineer")
    # location must be coarse so the loose-dedup tier fires
    loc = "United States"
    fp = fingerprint(ti, co, loc)
    lfp = loose_fingerprint(ti, co)
    job_id = f"triage-{fp}"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """INSERT INTO jobs
           (id, fingerprint, loose_fingerprint, url, title, company, location,
            source, relevance_score, stage, apply_flag, prep_folder_path)
           VALUES (?, ?, ?, ?, ?, ?, ?, 'triage', ?, ?, 0, ?)""",
        (job_id, fp, lfp, "https://example.com/original", ti, co, loc,
         score, stage, folder),
    )
    conn.commit()
    conn.close()


def test_duplicate_applied_returns_already_applied_partial(client: TestClient) -> None:
    # The existing row has a coarse location so the loose dedup tier fires.
    _insert_existing_job(client._db_path, stage="applied")  # type: ignore[attr-defined]
    # Submit with a specific city — will match via loose tier.
    data = dict(_VALID_FORM)
    data["location"] = "San Francisco, CA"
    resp = client.post("/ingest/manual", data=data)
    assert resp.status_code == 200
    assert 'data-outcome="already_applied"' in resp.text
    assert "Already applied" in resp.text
    assert "/board/applied" in resp.text
    # DB row count unchanged (1 pre-existing row, no new insert)
    assert _job_count(client) == 1


def test_duplicate_not_selected_returns_not_selected_partial(client: TestClient) -> None:
    _insert_existing_job(client._db_path, stage="not_selected", folder="/tmp/fake_folder")  # type: ignore[attr-defined]
    data = dict(_VALID_FORM)
    data["location"] = "San Francisco, CA"
    resp = client.post("/ingest/manual", data=data)
    assert resp.status_code == 200
    assert 'data-outcome="not_selected"' in resp.text
    assert "not selected" in resp.text.lower()
    assert "/board/rejected" in resp.text
    assert _job_count(client) == 1


def test_duplicate_rejected_returns_resurfaced_and_updates_db(client: TestClient) -> None:
    _insert_existing_job(client._db_path, stage="rejected", score=4)  # type: ignore[attr-defined]
    data = dict(_VALID_FORM)
    data["location"] = "San Francisco, CA"
    resp = client.post("/ingest/manual", data=data)
    assert resp.status_code == 200
    assert 'data-outcome="resurfaced"' in resp.text
    assert "/board/dashboard" in resp.text
    # Stage must be updated in DB
    conn = sqlite3.connect(client._db_path)  # type: ignore[attr-defined]
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT stage, relevance_score FROM jobs").fetchone()
    conn.close()
    assert row["stage"] == "scored"
    assert row["relevance_score"] == 8


def test_duplicate_waitlisted_returns_resurfaced(client: TestClient) -> None:
    _insert_existing_job(client._db_path, stage="waitlisted", score=7)  # type: ignore[attr-defined]
    data = dict(_VALID_FORM)
    data["location"] = "San Francisco, CA"
    resp = client.post("/ingest/manual", data=data)
    assert resp.status_code == 200
    assert 'data-outcome="resurfaced"' in resp.text
    conn = sqlite3.connect(client._db_path)  # type: ignore[attr-defined]
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT stage FROM jobs").fetchone()
    conn.close()
    assert row["stage"] == "scored"


def test_duplicate_low_scored_returns_resurfaced_and_bumps_score(client: TestClient) -> None:
    _insert_existing_job(client._db_path, stage="scored", score=3)  # type: ignore[attr-defined]
    data = dict(_VALID_FORM)
    data["location"] = "San Francisco, CA"
    resp = client.post("/ingest/manual", data=data)
    assert resp.status_code == 200
    assert 'data-outcome="resurfaced"' in resp.text
    conn = sqlite3.connect(client._db_path)  # type: ignore[attr-defined]
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT relevance_score FROM jobs").fetchone()
    conn.close()
    assert row["relevance_score"] == 8
```

- [ ] **Step 2: Run integration tests**

```bash
uv run pytest tests/test_web_ingest.py -v
```

Expected: all tests pass, including the 5 new ones.

- [ ] **Step 3: Run full test suite**

```bash
uv run pytest tests/ -v --tb=short 2>&1 | tail -20
```

Expected: all tests pass. Note the total count — it should be higher than before this feature.

- [ ] **Step 4: Run ruff and mypy**

```bash
uv run ruff check src/findajob/ingest.py src/findajob/actions.py src/findajob/web/routes/ingest.py && uv run ruff format --check src/findajob/ingest.py src/findajob/actions.py src/findajob/web/routes/ingest.py
```

```bash
uv run mypy src/findajob/ingest.py src/findajob/actions.py src/findajob/web/routes/ingest.py
```

Expected: no errors.

- [ ] **Step 5: Final commit**

```bash
git add tests/test_web_ingest.py
git commit -m "test(web): integration tests for resurface/applied/not-selected ingest outcomes"
```

---

## Whole-Feature Verification

After all tasks are committed:

```bash
uv run pytest tests/test_ingest.py tests/test_web_ingest.py tests/test_actions_resurface.py tests/test_waitlist.py -v
```

Expected: all pass with no skips.

Manual smoke test on docker.lan:
1. Find a job in `stage=rejected` in the DB (`sqlite3 /app/data/pipeline.db "SELECT fingerprint, company, title, stage FROM jobs WHERE stage='rejected' LIMIT 1"`).
2. Submit it via `/ingest/` with a different location (to trigger loose dedup).
3. Verify the result partial says "Re-surfaced to Dashboard" and links to `/board/dashboard`.
4. Verify the DB row now has `stage='scored'`, `relevance_score=8`, `reject_reason=''`, and no `feedback_log` rows.

---

## Self-Review Checklist (Spec → Tasks)

| Spec requirement | Task |
|---|---|
| applied/interview/offer/withdrew → link to /board/applied, no mutation | Task 3 `_handle_duplicate`, Task 4 route+template, Task 5 integration test |
| not_selected → link to /board/rejected + materials folder | Task 3, Task 4, Task 5 |
| rejected → un-reject: stage=scored, score=8, delete feedback_log, move folder | Task 2 `un_reject_job`, Task 3, Task 5 |
| waitlisted → reactivate: stage=scored, score=8, move folder | Task 2 `reactivate_from_ingest`, Task 3, Task 5 |
| scored/manual_review/prep_in_progress/materials_drafted → refresh: bump score/stage | Task 2 `refresh_active_job`, Task 3, Task 5 |
| Overwrite submitted fields (non-blank only) | Task 2 (all three helpers), Task 3 test |
| `fingerprint` on IngestResult for materials link | Task 1, Task 3 |
| `existing_stage` on IngestResult for route message | Task 1, Task 4 |
| audit_log entry on every mutation | Task 2 (all three helpers) |
| No mutations for post-application stages | Task 3 tests |
