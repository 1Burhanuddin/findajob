# Speculative Ingest (#131) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship #131 in full — speculative company submission via the `/ingest/` form, Perplexity Deep Research briefing + Claude Sonnet role synthesis, review-and-approve gate, speculative-aware cover-letter and outreach prompts, "Sent Outreach" button that counts toward the apply-gate and stays out of the scorer feedback loop.

**Architecture:** Phased into four sequenced PRs. B1 lands the `synthetic` column + `speculative_requests` table + correctness-critical guards in `findajob.actions` and `findajob.scoring`. B2 lands the synthesis pipeline (two new role files, a runner module, a script entry point). B3 lands the web form + async status page + review/approve/regenerate/trash UX. B4 lands the speculative-aware prep variants + `/apply` handler synthetic branch + watchdog branch + docs.

**Tech Stack:** Python 3.12; FastAPI + Jinja2 + HTMX (no SPA); SQLite (additive migrations via existing `init_db.py` pattern); aichat-ng for LLM dispatch; Perplexity Sonar Deep Research (`openrouter:perplexity/sonar-deep-research`) for the briefing role; Claude Sonnet 4.6 (`openrouter:anthropic/claude-sonnet-4-6`) for the role-synthesizer; `uv run pytest / ruff / mypy` for local CI.

**Spec:** `docs/superpowers/specs/2026-04-28-speculative-ingest-131-design.md` — read first. Documentation Impact, self-review checklist (spec-section → task), and risks live there. This plan is the executable counterpart.

**Out of scope (per spec, deferred):** aging/decay of unused speculative rows; briefing self-evaluation/confidence flag; CLI submission entry point; dedup; hard rate limit.

---

## Phase B1 — Foundation + Guardrails

**Branch:** `feat/131-b1-foundation`
**PR title:** `feat(speculative): add synthetic-jobs schema + scorer/feedback_log guards (B1 of #131)`
**PR labels:** `migration-required`
**Migration required:** yes — adds `jobs.synthetic` column + creates `speculative_requests` table on every stack at deploy time.

### Task 1: Branch off origin/main

**Files:** none (git only)

- [ ] **Step 1: Fetch and create branch off origin/main**

```bash
git fetch origin
git checkout -b feat/131-b1-foundation origin/main
```

Expected: `Switched to a new branch 'feat/131-b1-foundation'`. Local main may have drifted from origin/main; branching off origin/main avoids the squash-merge drift trap.

---

### Task 2: Add `synthetic` column to `jobs` (idempotent migration in `init_db.py`)

**Files:**
- Modify: `scripts/init_db.py:14-22` — extend the existing additive-column block

- [ ] **Step 1: Read existing `init_db.py` migration block**

Read `scripts/init_db.py` lines 14-22 (the existing `loose_fingerprint` ALTER block). The new column slots into the same pattern.

- [ ] **Step 2: Add the synthetic-column ALTER**

Edit `scripts/init_db.py`. After the existing `if "loose_fingerprint" not in _jobs_cols:` block (around line 22), add:

```python
    if "synthetic" not in _jobs_cols:
        conn.execute("ALTER TABLE jobs ADD COLUMN synthetic INTEGER NOT NULL DEFAULT 0")
        conn.commit()
```

- [ ] **Step 3: Add `synthetic` to the canonical `CREATE TABLE jobs` block**

In the `conn.executescript("""...""")` block in `scripts/init_db.py`, locate the `jobs` CREATE TABLE (around line 25-58). Add the column declaration after `dupe_of TEXT DEFAULT ''`:

```sql
    synthetic INTEGER NOT NULL DEFAULT 0,
```

So the block ends:

```sql
    ...
    dupe_of TEXT DEFAULT '',
    synthetic INTEGER NOT NULL DEFAULT 0
);
```

(Note the comma placement — `dupe_of` line gets a trailing comma; `synthetic` does not.)

- [ ] **Step 4: Run init_db against an in-memory test DB and verify the column lands**

```bash
uv run python -c "
import sqlite3, sys
sys.path.insert(0, 'src')
conn = sqlite3.connect(':memory:')
# Simulate a legacy DB without the synthetic column
conn.executescript('CREATE TABLE jobs (id TEXT PRIMARY KEY, fingerprint TEXT UNIQUE);')
# Run the additive block
existing = {row[1] for row in conn.execute('PRAGMA table_info(jobs)').fetchall()}
if 'synthetic' not in existing:
    conn.execute('ALTER TABLE jobs ADD COLUMN synthetic INTEGER NOT NULL DEFAULT 0')
cols = [row[1] for row in conn.execute('PRAGMA table_info(jobs)').fetchall()]
assert 'synthetic' in cols, f'missing synthetic: {cols}'
print('OK: synthetic column added')
"
```

Expected: `OK: synthetic column added`

- [ ] **Step 5: Commit**

```bash
git add scripts/init_db.py
git commit -m "$(cat <<'EOF'
feat(schema): add jobs.synthetic column for speculative-row marking (B1.1 of #131)

Idempotent ALTER TABLE block in init_db.py mirrors the existing
loose_fingerprint pattern. Default 0 so all existing rows are non-synthetic
post-migration. Column is the canonical row-level signal for the
correctness-critical guards landing in subsequent tasks.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Add `speculative_requests` table to `init_db.py`

**Files:**
- Modify: `scripts/init_db.py` — extend the `executescript` SQL block

- [ ] **Step 1: Add the table definition**

In `scripts/init_db.py`, inside the `conn.executescript("""...""")` block, after the `duplicate_groups` block, add:

```sql
CREATE TABLE IF NOT EXISTS speculative_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company TEXT NOT NULL,
    hint TEXT,
    personal_notes TEXT,
    status TEXT NOT NULL DEFAULT 'researching',
    error_message TEXT,
    briefing_md TEXT,
    role_cards_json TEXT,
    briefing_folder TEXT,
    submitted_at TEXT NOT NULL DEFAULT (datetime('now')),
    research_completed_at TEXT,
    approved_at TEXT,
    approved_role_count INTEGER,
    briefing_prompt_version TEXT,
    synth_prompt_version TEXT
);

CREATE INDEX IF NOT EXISTS idx_speculative_status ON speculative_requests(status);
CREATE INDEX IF NOT EXISTS idx_speculative_company_submitted ON speculative_requests(company, submitted_at);
```

- [ ] **Step 2: Verify the table is created on a fresh DB**

```bash
uv run python -c "
import sqlite3, subprocess
db = '/tmp/_specreq_smoke.db'
import os; os.path.exists(db) and os.remove(db)
import findajob.paths as p
# Run init_db with BASE pointed at a tmp dir
import sys; sys.argv = ['init_db.py']
# Instead: run init_db's executescript against an in-memory DB by reading the file
src = open('scripts/init_db.py').read()
conn = sqlite3.connect(':memory:')
# Find the executescript call and run its body
import re
m = re.search(r'executescript\(\"\"\"(.+?)\"\"\"\)', src, re.S)
assert m, 'could not find executescript'
conn.executescript(m.group(1))
tables = [r[0] for r in conn.execute(\"SELECT name FROM sqlite_master WHERE type='table'\").fetchall()]
assert 'speculative_requests' in tables, f'missing: {tables}'
print('OK: speculative_requests table created')
"
```

Expected: `OK: speculative_requests table created`

- [ ] **Step 3: Commit**

```bash
git add scripts/init_db.py
git commit -m "$(cat <<'EOF'
feat(schema): add speculative_requests table (B1.2 of #131)

Holds all pre-approval state for a speculative submission: company, hint,
research artifacts (briefing_md + role_cards_json), status lifecycle
(researching | ready_for_review | approved | trashed | failed),
prompt-version tags for quality-over-time analysis. Two indices: status
(for runner / watchdog lookups) and (company, submitted_at) (for ad-hoc
forensics).

jobs rows are only written on Approve; trash/failed paths leave jobs
untouched.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Add `is_synthetic_job` helper to `findajob.utils`

**Files:**
- Modify: `src/findajob/utils.py` — add helper
- Test: `tests/test_utils.py` — add test

- [ ] **Step 1: Write the failing test**

Append to `tests/test_utils.py`:

```python
def test_is_synthetic_job_true_for_flag_one():
    from findajob.utils import is_synthetic_job
    assert is_synthetic_job({"synthetic": 1}) is True


def test_is_synthetic_job_false_for_flag_zero():
    from findajob.utils import is_synthetic_job
    assert is_synthetic_job({"synthetic": 0}) is False


def test_is_synthetic_job_false_when_key_missing():
    from findajob.utils import is_synthetic_job
    # Legacy / partial dicts default to non-synthetic.
    assert is_synthetic_job({}) is False


def test_is_synthetic_job_truthy_string_treated_as_true():
    from findajob.utils import is_synthetic_job
    # SQLite returns 1/0 as int but be defensive against driver quirks.
    assert is_synthetic_job({"synthetic": "1"}) is True
```

- [ ] **Step 2: Run test to verify failure**

```bash
uv run pytest tests/test_utils.py::test_is_synthetic_job_true_for_flag_one -v
```

Expected: `ImportError` or `AttributeError: module 'findajob.utils' has no attribute 'is_synthetic_job'`.

- [ ] **Step 3: Implement the helper**

Append to `src/findajob/utils.py`:

```python
def is_synthetic_job(job: Any) -> bool:
    """Return True when this row represents a speculative (cold-outreach) job.

    Driven by the ``jobs.synthetic`` column, which is set to 1 by the speculative
    approver and 0 (default) for all real postings. Treat any truthy value
    (1, "1") as synthetic; absence or 0 means real.
    """
    if not job:
        return False
    val = job.get("synthetic") if hasattr(job, "get") else None
    if val is None:
        # sqlite3.Row supports __getitem__ but not .get(); fall back.
        try:
            val = job["synthetic"]
        except (KeyError, IndexError, TypeError):
            return False
    return bool(int(val)) if val is not None else False
```

If `Any` isn't already imported in `src/findajob/utils.py`, add `from typing import Any` near the top.

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_utils.py -v -k "synthetic"
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/findajob/utils.py tests/test_utils.py
git commit -m "$(cat <<'EOF'
feat(utils): is_synthetic_job() helper (B1.3 of #131)

Single read site for the synthetic flag. Defensive against missing keys,
sqlite3.Row vs dict, and string-typed values. Used by handle_rejection,
handle_not_selected, the scorer feedback loader, and (in B4) the
/apply handler's changed_by branch.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: `handle_rejection` skips `feedback_log` write when synthetic

**Files:**
- Modify: `src/findajob/actions.py:26-64` — `handle_rejection`
- Test: `tests/test_actions.py` — add test

- [ ] **Step 1: Write the failing test**

Append to `tests/test_actions.py`:

```python
def test_handle_rejection_skips_feedback_log_for_synthetic(tmp_path, monkeypatch):
    """A synthetic job rejected by the user must NOT write to feedback_log —
    contaminating the scorer's feedback loop with synthetic signal would be a
    permanent data-quality hit. Real-job rejection still writes."""
    monkeypatch.setattr(actions, "BASE", str(tmp_path))
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA + """
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
        CREATE TABLE audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT NOT NULL,
            field_changed TEXT NOT NULL,
            old_value TEXT,
            new_value TEXT,
            changed_at TEXT DEFAULT (datetime('now')),
            changed_by TEXT DEFAULT 'system'
        );
        ALTER TABLE jobs ADD COLUMN synthetic INTEGER NOT NULL DEFAULT 0;
    """)
    syn_id = str(uuid.uuid4())
    real_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO jobs (id, fingerprint, url, title, company, source, stage, relevance_score, synthetic) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (syn_id, "syn-fp", "http://x", "[SPEC] PSI Eng", "PSIQuantum", "web_speculative", "applied", 7, 1),
    )
    conn.execute(
        "INSERT INTO jobs (id, fingerprint, url, title, company, source, stage, relevance_score, synthetic) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (real_id, "real-fp", "http://y", "Real Eng", "RealCo", "greenhouse", "applied", 7, 0),
    )

    syn_job = conn.execute("SELECT * FROM jobs WHERE id=?", (syn_id,)).fetchone()
    real_job = conn.execute("SELECT * FROM jobs WHERE id=?", (real_id,)).fetchone()

    actions.handle_rejection(conn, syn_job, "Fit Mismatch")
    actions.handle_rejection(conn, real_job, "Fit Mismatch")

    syn_count = conn.execute("SELECT COUNT(*) FROM feedback_log WHERE job_id=?", (syn_id,)).fetchone()[0]
    real_count = conn.execute("SELECT COUNT(*) FROM feedback_log WHERE job_id=?", (real_id,)).fetchone()[0]
    assert syn_count == 0, "synthetic rejection must not write feedback_log"
    assert real_count == 1, "real rejection must still write feedback_log"

    # Stage transition still happens for both — synthetic guard only affects feedback_log
    syn_after = conn.execute("SELECT stage FROM jobs WHERE id=?", (syn_id,)).fetchone()
    real_after = conn.execute("SELECT stage FROM jobs WHERE id=?", (real_id,)).fetchone()
    assert syn_after["stage"] == "rejected"
    assert real_after["stage"] == "rejected"
```

- [ ] **Step 2: Run test to verify failure**

```bash
uv run pytest tests/test_actions.py::test_handle_rejection_skips_feedback_log_for_synthetic -v
```

Expected: FAIL with `assert 0 == 0` succeeding for `syn_count` BUT `real_count` actually being `1` succeeds — wait, this test will actually fail because synthetic rejection DOES currently write to feedback_log (so syn_count will be 1, not 0). The first assert fails.

- [ ] **Step 3: Add the synthetic guard in `handle_rejection`**

Edit `src/findajob/actions.py`. The function starts at line 26. The feedback_log INSERT is at line 38-42. Wrap the INSERT in a synthetic guard.

Replace lines 38-42:

```python
    conn.execute(
        """INSERT INTO feedback_log (job_id, title, company, relevance_score, reject_reason, jd_excerpt)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (job["id"], job["title"], job["company"], job["relevance_score"], reason, jd_excerpt),
    )
```

with:

```python
    from findajob.utils import is_synthetic_job  # local import to avoid circular at module load

    if not is_synthetic_job(job):
        conn.execute(
            """INSERT INTO feedback_log (job_id, title, company, relevance_score, reject_reason, jd_excerpt)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (job["id"], job["title"], job["company"], job["relevance_score"], reason, jd_excerpt),
        )
```

(Local import is intentional: `findajob.actions` is imported by code that also imports `findajob.utils`; keeping the import inside the function avoids any ordering surprise during module init. The cost is one dict lookup per call — negligible.)

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_actions.py::test_handle_rejection_skips_feedback_log_for_synthetic -v
```

Expected: 1 passed.

Also run the existing actions tests to confirm no regression:

```bash
uv run pytest tests/test_actions.py -v
```

Expected: all passed.

- [ ] **Step 5: Commit**

```bash
git add src/findajob/actions.py tests/test_actions.py
git commit -m "$(cat <<'EOF'
feat(actions): handle_rejection skips feedback_log for synthetic jobs (B1.4 of #131)

Synthetic (cold-outreach) jobs must not contribute to the scorer's
feedback loop on rejection — synthesizer hallucinations would otherwise
become permanent training-data contamination.

Stage transition + audit_log entry + folder move are unchanged. Only the
feedback_log INSERT is gated on is_synthetic_job(job).

Test asserts both halves: synthetic skipped, real still writes.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: Scorer feedback loader excludes synthetic rows

**Files:**
- Modify: `src/findajob/scoring.py:63-78` — `_build_feedback_block`
- Test: `tests/test_scoring.py` — add test

The scorer's feedback loader queries `feedback_log` directly. After Task 5 lands, no new synthetic-job rejections will write to `feedback_log` — but historical rows could exist (and defense-in-depth dictates filtering at read time too). The filter is via JOIN on `jobs.synthetic`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_scoring.py` (create the file if it doesn't have these helpers — check existing test_scoring.py for patterns):

```python
def test_build_feedback_block_excludes_synthetic(tmp_path, monkeypatch):
    """The scorer's feedback block must not include rejection history from
    synthetic jobs. Even if a synthetic-job rejection bypassed the write-time
    guard (data already in feedback_log from before the guard landed), the
    read-time filter excludes it."""
    import sqlite3
    from findajob import scoring

    db_path = tmp_path / "test_pipeline.db"
    monkeypatch.setattr(scoring, "DB_PATH", str(db_path))

    conn = sqlite3.connect(str(db_path))
    conn.executescript("""
        CREATE TABLE jobs (
            id TEXT PRIMARY KEY,
            fingerprint TEXT UNIQUE,
            title TEXT,
            company TEXT,
            synthetic INTEGER NOT NULL DEFAULT 0
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
    """)
    # Two rejected jobs: one synthetic, one real, same reason.
    conn.execute("INSERT INTO jobs (id, fingerprint, title, company, synthetic) VALUES (?, ?, ?, ?, ?)",
                 ("syn1", "fp-syn", "[SPEC] X Eng", "PSI", 1))
    conn.execute("INSERT INTO jobs (id, fingerprint, title, company, synthetic) VALUES (?, ?, ?, ?, ?)",
                 ("real1", "fp-real", "Real X Eng", "RealCo", 0))
    conn.execute("INSERT INTO feedback_log (job_id, title, company, relevance_score, reject_reason) VALUES (?, ?, ?, ?, ?)",
                 ("syn1", "[SPEC] X Eng", "PSI", 7, "Fit Mismatch"))
    conn.execute("INSERT INTO feedback_log (job_id, title, company, relevance_score, reject_reason) VALUES (?, ?, ?, ?, ?)",
                 ("real1", "Real X Eng", "RealCo", 7, "Fit Mismatch"))
    conn.commit()
    conn.close()

    block = scoring._build_feedback_block()
    assert "Real X Eng" in block
    assert "[SPEC]" not in block, "synthetic rejection title leaked into feedback block"
    # Should report "1x" (the real one), not "2x"
    assert '1x "Fit Mismatch"' in block
```

- [ ] **Step 2: Run test to verify failure**

```bash
uv run pytest tests/test_scoring.py::test_build_feedback_block_excludes_synthetic -v
```

Expected: FAIL — `[SPEC]` is in the block, count is 2x not 1x.

- [ ] **Step 3: Add the JOIN-based synthetic exclusion in `_build_feedback_block`**

Edit `src/findajob/scoring.py`. Replace the SELECT in `_build_feedback_block` (around lines 69-74):

```python
        rows = conn.execute("""
            SELECT reject_reason, title, relevance_score
            FROM feedback_log
            WHERE reject_reason NOT IN ('Stale/Closed', 'Already Applied', 'Other')
            ORDER BY reject_reason, title
        """).fetchall()
```

with:

```python
        rows = conn.execute("""
            SELECT f.reject_reason, f.title, f.relevance_score
            FROM feedback_log f
            LEFT JOIN jobs j ON j.id = f.job_id
            WHERE f.reject_reason NOT IN ('Stale/Closed', 'Already Applied', 'Other')
              AND COALESCE(j.synthetic, 0) = 0
            ORDER BY f.reject_reason, f.title
        """).fetchall()
```

(`LEFT JOIN` so that orphaned `feedback_log` rows whose `jobs` row has been deleted still get included in scoring history. `COALESCE(..., 0)` treats missing as non-synthetic.)

- [ ] **Step 4: Run tests to verify**

```bash
uv run pytest tests/test_scoring.py -v
```

Expected: all passed (new test + any existing scoring tests). If the existing tests don't seed `synthetic` column on `jobs`, they may need an `ALTER TABLE jobs ADD COLUMN synthetic INTEGER NOT NULL DEFAULT 0` in their schema fixture — patch as needed.

- [ ] **Step 5: Commit**

```bash
git add src/findajob/scoring.py tests/test_scoring.py
git commit -m "$(cat <<'EOF'
feat(scoring): feedback block excludes synthetic rows (B1.5 of #131)

Defense-in-depth complement to the write-time guard in handle_rejection.
LEFT JOIN against jobs.synthetic and exclude. Even if a synthetic
rejection slipped past the write-time check (e.g. historical rows from
before the guard, or a future code path that bypasses handle_rejection),
the scorer prompt never sees synthetic-rejection signal.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: Update existing test fixtures for `synthetic` column

**Files:**
- Modify: `tests/test_actions.py` — `SCHEMA` constant
- Modify: `tests/test_actions_resurface.py`, `tests/test_waitlist.py`, etc. — any test that builds a `jobs` table without `synthetic`

- [ ] **Step 1: Update the SCHEMA constant in `tests/test_actions.py`**

Edit `tests/test_actions.py`. The `SCHEMA` constant defines an inline `CREATE TABLE jobs`. Add `synthetic INTEGER NOT NULL DEFAULT 0,` near the end of the column list, between `dupe_of TEXT DEFAULT ''` and the closing `);`.

- [ ] **Step 2: Search for and patch any other `CREATE TABLE jobs` test fixtures**

```bash
grep -lE "CREATE TABLE jobs|CREATE TABLE IF NOT EXISTS jobs" tests/ -r | sort -u
```

For each file returned, open it and add the `synthetic INTEGER NOT NULL DEFAULT 0,` column to the `CREATE TABLE jobs` block in its schema fixture. The placement is just before the final closing `);`.

- [ ] **Step 3: Run the full test suite**

```bash
uv run pytest -x
```

Expected: all passed. If any test fails because its fixture mismatches the canonical schema, patch its SCHEMA constant.

- [ ] **Step 4: Commit**

```bash
git add tests/
git commit -m "$(cat <<'EOF'
test(fixtures): add synthetic column to jobs schema fixtures (B1.6 of #131)

Mechanical update to align inline CREATE TABLE jobs definitions in tests
with the new canonical schema. No behavior change in any existing test;
the column defaults to 0 so existing assertions are unaffected.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 8: Add CLAUDE.md stub for synthetic-jobs convention

**Files:**
- Modify: `CLAUDE.md` — add new section after "Hard Rejects are Code"

- [ ] **Step 1: Add the section**

In `CLAUDE.md`, after the `### Hard Rejects are Code` section, insert:

```markdown
### Synthetic Jobs Convention (Speculative Cold-Outreach)

Some `jobs` rows are *synthetic* — generated by the speculative ingest path
(`/ingest/?mode=speculative`, see #131) for cold-outreach to companies that
aren't currently posting a matching opening. These rows are marked with
`jobs.synthetic=1` and `source='web_speculative'`, and their titles are
prefixed with `[SPEC] `.

Invariants enforced in code:
- `findajob.actions.handle_rejection` and `handle_not_selected` SKIP
  `feedback_log` writes when `jobs.synthetic=1`. Synthetic rejections
  must never feed the scorer.
- `findajob.scoring._build_feedback_block` LEFT JOINs to `jobs` and
  excludes `synthetic=1` rows from the scorer prompt's rejection history.
- Speculative rows reuse the `applied` stage (no new enum value); the
  distinction lives in `synthetic=1` + `source='web_speculative'`.

The `[SPEC] ` title prefix is decoration — defense-in-depth — not data.
The `synthetic` flag is the canonical signal.
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "$(cat <<'EOF'
docs(claude-md): synthetic jobs convention (B1.7 of #131)

Documents the contract that handle_rejection / handle_not_selected /
scorer feedback loader all enforce: synthetic=1 rows never enter
feedback_log on write or scorer history on read.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 9: Add CHANGELOG entry for B1

**Files:**
- Modify: `docs/CHANGELOG.md` (or `CHANGELOG.md` — check repo for existing path)

- [ ] **Step 1: Add entry**

Locate the `[Unreleased]` block in `CHANGELOG.md`. Add under `### Added`:

```markdown
- (#131) Schema foundation for speculative ingest: new `jobs.synthetic` column and `speculative_requests` table. Synthetic rows are excluded from `feedback_log` writes (`handle_rejection`, `handle_not_selected`) and from scorer feedback reads (`_build_feedback_block`). Migration required: `synthetic` column adds via idempotent ALTER on existing stacks; `speculative_requests` is a fresh CREATE.
```

Add a `### Migration required` block (or extend the existing one):

```markdown
### Migration required

- (#131) `jobs.synthetic` column + `speculative_requests` table land via `init_db.py`. On deploy: container restart runs `init_db.py` automatically; no operator action needed beyond `docker compose pull && docker compose up -d`.
```

- [ ] **Step 2: Commit**

```bash
git add CHANGELOG.md
git commit -m "$(cat <<'EOF'
docs(changelog): B1 of #131 — synthetic schema foundation

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 10: Run full CI locally + push + open PR

- [ ] **Step 1: Run linters and full test suite**

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy src/findajob
uv run pytest -x
```

Expected: all green.

- [ ] **Step 2: Push and open the PR**

```bash
git push -u origin feat/131-b1-foundation
gh pr create --title "feat(speculative): schema + scorer/feedback_log guards (B1 of #131)" --body "$(cat <<'EOF'
## Summary

- Adds `jobs.synthetic` column (idempotent ALTER) and creates `speculative_requests` table — schema foundation for #131.
- `handle_rejection` and `handle_not_selected` skip `feedback_log` writes when `synthetic=1`.
- `_build_feedback_block` LEFT JOINs and excludes synthetic rows.
- Adds `is_synthetic_job` helper in `findajob.utils`.
- Documents the synthetic-jobs convention in `CLAUDE.md`.

This is **B1 of 4** for #131. B2 will land the synthesis pipeline; B3 the web form/UX; B4 the speculative-aware prep + sent-outreach button.

## Migration required

`jobs.synthetic` adds via idempotent ALTER; `speculative_requests` is a fresh CREATE. Container restart on deploy runs `init_db.py` automatically.

## Test plan

- [ ] `uv run pytest tests/test_actions.py tests/test_scoring.py tests/test_utils.py` green
- [ ] On the dev box, run `uv run python scripts/init_db.py` against a copy of the prod DB; confirm `synthetic` column added and `speculative_requests` table created
- [ ] Sanity: `sqlite3 data/pipeline.db "SELECT COUNT(*) FROM jobs WHERE synthetic=1"` returns 0 (no false positives)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)" --label migration-required
```

- [ ] **Step 3: Wait for CI; merge when green**

```bash
gh pr checks --watch
```

When green, merge:

```bash
gh pr merge --squash --delete-branch
git fetch origin && git checkout main && git pull
```

---

## Phase B2 — Synthesis Pipeline

**Branch:** `feat/131-b2-synthesis`
**Branch base:** `origin/main` (post-B1 merge)
**PR title:** `feat(speculative): briefing + role-synth pipeline runner (B2 of #131)`
**PR labels:** none (no migrations, no compose/crontab/mounts)

### Task 11: Branch + scaffold `src/findajob/speculative/` package

**Files:**
- Create: `src/findajob/speculative/__init__.py`

- [ ] **Step 1: Branch off origin/main (post-B1 merge)**

```bash
git fetch origin
git checkout -b feat/131-b2-synthesis origin/main
```

- [ ] **Step 2: Scaffold the package**

Create `src/findajob/speculative/__init__.py`:

```python
"""Speculative ingest pipeline — see docs/superpowers/specs/2026-04-28-speculative-ingest-131-design.md.

Modules:
- runner.py    : orchestrates the briefing + role-synth call sequence
- parser.py    : validates LLM output into role-card dicts
- approver.py  : on operator approve, writes jobs rows from kept role cards
- storage.py   : creates speculative briefing folder + writes briefing.md
"""
```

- [ ] **Step 3: Commit**

```bash
git add src/findajob/speculative/__init__.py
git commit -m "$(cat <<'EOF'
feat(speculative): scaffold src/findajob/speculative/ package (B2.1 of #131)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 12: Author `candidate_led_briefing` role file

**Files:**
- Create: `config/roles/candidate_led_briefing.md`

- [ ] **Step 1: Read existing perplexity-based role files for the convention**

```bash
cat config/roles/company_researcher.md | head -40
cat config/roles/fit_analyst.md | head -40
```

These are the existing perplexity sonar-reasoning-pro roles. The new role mirrors the front-matter pattern (model, max_tokens, system prompt) but uses `sonar-deep-research`.

- [ ] **Step 2: Write the role file**

Create `config/roles/candidate_led_briefing.md`:

````markdown
---
model: openrouter:perplexity/sonar-deep-research
temperature: 0.3
---

You are a research analyst producing a hiring-posture briefing on a target company for a candidate considering speculative cold outreach. The candidate's profile and master resume are provided below as context. There is no job description — you are inferring likely role surfaces from the company's apparent hiring direction, recent announcements, leadership communications, and operational footprint.

# Output

Return well-formed Markdown with these sections, in this order:

## 🏢 Company Snapshot
2–4 sentences. What they do, scale (employees, revenue, recent funding), industry position.

## 📈 Hiring Signals
Bullet list. Specific signals you found: open recs by category, recent leadership hires, public statements about expansion, geographic moves, organizational changes. Cite sources inline.

## 🎯 Likely Role Surfaces for This Candidate
Bullet list of 3–6 plausible role types this company would hire that align with the candidate's background. Each bullet: role title or function + 1-sentence why-this-fits drawing on candidate's specific experience. Be concrete; do not list every role they hire.

## 🤝 Suggested Angle of Approach
2–3 sentences. Recommended framing for cold outreach: which team or function to target, what posture (recruiter, hiring manager, senior IC), what to lead with from the candidate's background.

## 👥 Known Contacts (if any)
If the candidate's profile or visible LinkedIn graph reveals any direct or 2nd-degree contacts at the target, list them. If none, write "None identified — outreach should be cold."

## ❓ Likely Interview Questions
List 5–8 questions the candidate should expect, drawn from the role surfaces you identified.

## 💡 Stories from Your Background
For each likely interview question, point to a specific story from the candidate's master resume that maps best.

# Constraints

- Ground every claim in a citation. Do not infer hiring signals from generic web copy.
- Do not invent roles the company isn't plausibly hiring for.
- Do not recommend an angle the candidate's resume doesn't actually support.
- The briefing is consumed by a downstream synthesizer; structure matters.

# Candidate context

{{candidate_profile}}

---

{{master_resume}}

---

# Target

Company: {{company}}

Optional operator hint: {{hint}}

Optional connection notes: {{personal_notes}}
````

- [ ] **Step 3: Commit**

```bash
git add config/roles/candidate_led_briefing.md
git commit -m "$(cat <<'EOF'
feat(speculative): candidate_led_briefing role on sonar-deep-research (B2.2 of #131)

Drives the briefing pass: structured markdown with company snapshot,
hiring signals, likely role surfaces tailored to candidate background,
suggested cold-outreach angle, known contacts, and a Q + Stories pair
that the role-synthesizer and downstream interview_prep both consume.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 13: Author `speculative_roles_synth` role file

**Files:**
- Create: `config/roles/speculative_roles_synth.md`

- [ ] **Step 1: Write the role file**

Create `config/roles/speculative_roles_synth.md`:

````markdown
---
model: openrouter:anthropic/claude-sonnet-4-6
max_tokens: 4096
temperature: 0.4
---

You synthesize 1–5 plausible job roles a target company might hire that align with this candidate's background, given a researcher's hiring-posture briefing. Output is consumed by an approver that writes one `jobs` row per role you return.

# Output

Return ONLY a JSON array. No prose, no markdown fences. Schema for each element:

```json
{
  "title": "string — concrete job title; will be prefixed with [SPEC] downstream",
  "description": "string — 4-8 sentence synthesized job description, framed as if posted; pulls from the briefing's hiring signals and likely role surfaces",
  "why_this_fits_candidate": "string — 2-4 sentence specific match between candidate's resume and this role; cite specific resume bullets",
  "likely_team_or_org": "string — best guess at internal team / function / org",
  "suggested_contact_type": "recruiter | hiring_manager | senior_ic"
}
```

# Constraints

- Return between 1 and 5 cards. Quality over quantity. If the briefing only supports 1 strong match, return 1; do not pad.
- Do NOT return cards for roles the briefing's "Likely Role Surfaces" section does not list.
- Each card's `description` must read like a real posting — responsibilities, qualifications, scope. Anchor in the briefing.
- Each card's `why_this_fits_candidate` must reference specific entries from the candidate's master resume below.
- Do not fabricate technical details, internal program names, or seniority levels not supported by the briefing.

# Candidate context

{{candidate_profile}}

---

{{master_resume}}

---

# Briefing (from candidate_led_briefing role)

{{briefing}}
````

- [ ] **Step 2: Commit**

```bash
git add config/roles/speculative_roles_synth.md
git commit -m "$(cat <<'EOF'
feat(speculative): speculative_roles_synth role on Claude Sonnet 4.6 (B2.3 of #131)

JSON-array output schema (title, description, why_this_fits_candidate,
likely_team_or_org, suggested_contact_type). Hard cap 5 cards; quality
over quantity. Constrains synthesis to roles the briefing's "Likely Role
Surfaces" section actually supports.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 14: Implement `speculative.parser` — JSON validation

**Files:**
- Create: `src/findajob/speculative/parser.py`
- Create: `tests/test_speculative_parser.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_speculative_parser.py`:

```python
"""Tests for findajob.speculative.parser — validates LLM-output role cards."""

from __future__ import annotations

import json

import pytest

from findajob.speculative.parser import RoleCard, parse_role_cards


def test_parses_valid_array():
    raw = json.dumps([
        {
            "title": "Critical Infrastructure Engineer",
            "description": "Own deployment of GPU clusters at new sites.",
            "why_this_fits_candidate": "Candidate landed FTW Lab in a single half.",
            "likely_team_or_org": "Site Operations",
            "suggested_contact_type": "hiring_manager",
        }
    ])
    cards = parse_role_cards(raw)
    assert len(cards) == 1
    assert cards[0].title == "Critical Infrastructure Engineer"
    assert cards[0].suggested_contact_type == "hiring_manager"


def test_strips_leading_markdown_fence():
    """LLMs sometimes wrap JSON in ```json fences despite instructions."""
    raw = "```json\n" + json.dumps([{
        "title": "X",
        "description": "Y",
        "why_this_fits_candidate": "Z",
        "likely_team_or_org": "T",
        "suggested_contact_type": "recruiter",
    }]) + "\n```"
    cards = parse_role_cards(raw)
    assert len(cards) == 1


def test_caps_at_five_cards():
    raw = json.dumps([
        {"title": f"Role {i}", "description": "D", "why_this_fits_candidate": "W",
         "likely_team_or_org": "T", "suggested_contact_type": "recruiter"}
        for i in range(8)
    ])
    cards = parse_role_cards(raw)
    assert len(cards) == 5  # surplus dropped


def test_rejects_invalid_contact_type():
    raw = json.dumps([{
        "title": "X", "description": "Y", "why_this_fits_candidate": "Z",
        "likely_team_or_org": "T", "suggested_contact_type": "ceo",  # invalid
    }])
    with pytest.raises(ValueError, match="suggested_contact_type"):
        parse_role_cards(raw)


def test_rejects_missing_required_field():
    raw = json.dumps([{"title": "X"}])
    with pytest.raises(ValueError, match="missing"):
        parse_role_cards(raw)


def test_rejects_non_array():
    raw = json.dumps({"title": "X"})  # object, not array
    with pytest.raises(ValueError, match="array"):
        parse_role_cards(raw)


def test_rejects_empty_array():
    """Spec requires 1-5 cards — empty is a synthesis failure, not silent success."""
    raw = json.dumps([])
    with pytest.raises(ValueError, match="empty|at least one"):
        parse_role_cards(raw)
```

- [ ] **Step 2: Run test to verify failure**

```bash
uv run pytest tests/test_speculative_parser.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement parser**

Create `src/findajob/speculative/parser.py`:

```python
"""Validates LLM output from speculative_roles_synth into RoleCard objects.

Defensive against LLMs that wrap JSON in markdown fences despite instructions,
return more than 5 cards, omit required fields, or use invalid enums.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Literal

ContactType = Literal["recruiter", "hiring_manager", "senior_ic"]
_VALID_CONTACT_TYPES: set[str] = {"recruiter", "hiring_manager", "senior_ic"}
_MAX_CARDS = 5


@dataclass(frozen=True)
class RoleCard:
    title: str
    description: str
    why_this_fits_candidate: str
    likely_team_or_org: str
    suggested_contact_type: ContactType


def parse_role_cards(raw: str) -> list[RoleCard]:
    """Parse a speculative_roles_synth output into validated RoleCard objects.

    Raises ValueError on any structural problem. Caps at 5 cards.
    """
    cleaned = _strip_markdown_fence(raw).strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise ValueError(f"role-cards output is not valid JSON: {e}") from e

    if not isinstance(data, list):
        raise ValueError("role-cards output must be a JSON array, got: " + type(data).__name__)
    if not data:
        raise ValueError("role-cards output is empty — synthesis must produce at least one card")

    cards: list[RoleCard] = []
    for i, item in enumerate(data[:_MAX_CARDS]):
        if not isinstance(item, dict):
            raise ValueError(f"role card {i} is not a JSON object")
        for required in ("title", "description", "why_this_fits_candidate",
                         "likely_team_or_org", "suggested_contact_type"):
            if required not in item or not item[required]:
                raise ValueError(f"role card {i} missing required field: {required}")
        contact_type = item["suggested_contact_type"]
        if contact_type not in _VALID_CONTACT_TYPES:
            raise ValueError(
                f"role card {i} has invalid suggested_contact_type "
                f"{contact_type!r}; expected one of {sorted(_VALID_CONTACT_TYPES)}"
            )
        cards.append(RoleCard(
            title=str(item["title"]).strip(),
            description=str(item["description"]).strip(),
            why_this_fits_candidate=str(item["why_this_fits_candidate"]).strip(),
            likely_team_or_org=str(item["likely_team_or_org"]).strip(),
            suggested_contact_type=contact_type,
        ))
    return cards


def _strip_markdown_fence(s: str) -> str:
    """Remove ```json ... ``` or ``` ... ``` fence wrapping if present."""
    fence_match = re.match(r"^```(?:json)?\s*\n(.+?)\n```\s*$", s.strip(), re.S)
    if fence_match:
        return fence_match.group(1)
    return s
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_speculative_parser.py -v
```

Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add src/findajob/speculative/parser.py tests/test_speculative_parser.py
git commit -m "$(cat <<'EOF'
feat(speculative): role-cards parser with defensive validation (B2.4 of #131)

Strips markdown fences, validates required fields and contact-type enum,
caps at 5 cards, rejects empty arrays. 7 unit tests cover the LLM
edge-cases (fence wrapping, surplus cards, invalid enums, missing fields,
non-array root).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 15: Implement `speculative.storage` — briefing folder + briefing.md

**Files:**
- Create: `src/findajob/speculative/storage.py`
- Create: `tests/test_speculative_storage.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_speculative_storage.py`:

```python
"""Tests for findajob.speculative.storage."""

from __future__ import annotations

from pathlib import Path

import pytest

from findajob.speculative.storage import speculative_folder_name, write_briefing


def test_folder_name_includes_company_date_time():
    name = speculative_folder_name("PSIQuantum", when_iso="2026-04-28T14:30:00")
    assert name == "PSIQuantum_SPECULATIVE_2026-04-28_143000"


def test_folder_name_strips_company_unsafe_chars():
    # Slashes, colons, etc. must not appear in folder names.
    name = speculative_folder_name("ai/&:Co", when_iso="2026-04-28T09:00:00")
    assert "/" not in name
    assert ":" not in name
    assert name.startswith("ai_Co_SPECULATIVE_") or name.startswith("ai__Co_SPECULATIVE_")


def test_write_briefing_creates_folder_and_md(tmp_path):
    folder = write_briefing(
        base_dir=tmp_path,
        company="PSIQuantum",
        briefing_md="# briefing\n\nbody\n",
        when_iso="2026-04-28T14:30:00",
    )
    assert folder.exists()
    assert folder.is_dir()
    md = folder / "briefing.md"
    assert md.read_text() == "# briefing\n\nbody\n"
    assert folder.name == "PSIQuantum_SPECULATIVE_2026-04-28_143000"
```

- [ ] **Step 2: Run test to verify failure**

```bash
uv run pytest tests/test_speculative_storage.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement storage**

Create `src/findajob/speculative/storage.py`:

```python
"""Filesystem layout for speculative submissions:

    {BASE}/companies/{Company}_SPECULATIVE_{YYYY-MM-DD}_{HHMMSS}/briefing.md

The folder name is referenced by `speculative_requests.briefing_folder` so
the approver and prep paths can locate the briefing on read.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path


def speculative_folder_name(company: str, when_iso: str | None = None) -> str:
    """Return the canonical folder name (no parent path) for a speculative briefing."""
    safe_company = re.sub(r"[^A-Za-z0-9_]+", "_", company).strip("_") or "Unknown"
    when = datetime.fromisoformat(when_iso) if when_iso else datetime.now()
    stamp = when.strftime("%Y-%m-%d_%H%M%S")
    return f"{safe_company}_SPECULATIVE_{stamp}"


def write_briefing(
    base_dir: Path,
    company: str,
    briefing_md: str,
    when_iso: str | None = None,
) -> Path:
    """Create the speculative folder under base_dir and write briefing.md."""
    folder = Path(base_dir) / speculative_folder_name(company, when_iso=when_iso)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "briefing.md").write_text(briefing_md)
    return folder
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_speculative_storage.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/findajob/speculative/storage.py tests/test_speculative_storage.py
git commit -m "$(cat <<'EOF'
feat(speculative): briefing folder layout + write_briefing helper (B2.5 of #131)

Folder convention: {Company}_SPECULATIVE_{YYYY-MM-DD}_{HHMMSS}.
Mirrors the existing applied-folder convention but with SPECULATIVE
in place of the abbreviated title.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 16: Implement `speculative.runner` — orchestrates briefing + role-synth

**Files:**
- Create: `src/findajob/speculative/runner.py`
- Create: `tests/test_speculative_runner.py`

- [ ] **Step 1: Write the failing test (with mocked aichat-ng)**

Create `tests/test_speculative_runner.py`:

```python
"""Tests for findajob.speculative.runner — orchestrates briefing + role-synth.

aichat-ng subprocess is mocked. We assert the runner:
1. Reads the speculative_requests row and candidate context files
2. Calls the briefing role, then the synth role with the briefing as input
3. Writes briefing.md to a freshly-created folder
4. Updates the request row to status='ready_for_review' with briefing_md +
   role_cards_json + briefing_folder + research_completed_at populated
5. On any failure, sets status='failed' + error_message
"""

from __future__ import annotations

import json
import sqlite3
from unittest.mock import patch

import pytest

from findajob.speculative.runner import run_research

SCHEMA = """
CREATE TABLE speculative_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company TEXT NOT NULL,
    hint TEXT,
    personal_notes TEXT,
    status TEXT NOT NULL DEFAULT 'researching',
    error_message TEXT,
    briefing_md TEXT,
    role_cards_json TEXT,
    briefing_folder TEXT,
    submitted_at TEXT NOT NULL DEFAULT (datetime('now')),
    research_completed_at TEXT,
    approved_at TEXT,
    approved_role_count INTEGER,
    briefing_prompt_version TEXT,
    synth_prompt_version TEXT
);
"""


def _seed(conn: sqlite3.Connection) -> int:
    cur = conn.execute(
        "INSERT INTO speculative_requests (company, hint, personal_notes, status) VALUES (?, ?, ?, 'researching')",
        ("PSIQuantum", "advanced computing infrastructure", None),
    )
    conn.commit()
    return cur.lastrowid


def _ok_briefing() -> str:
    return "# briefing\n\n## 🏢 Company Snapshot\nbody\n"


def _ok_role_cards() -> str:
    return json.dumps([
        {
            "title": "Critical Infrastructure Engineer",
            "description": "Own GPU cluster bring-up.",
            "why_this_fits_candidate": "FTW Lab analog.",
            "likely_team_or_org": "Site Operations",
            "suggested_contact_type": "hiring_manager",
        }
    ])


def test_run_research_happy_path(tmp_path):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    req_id = _seed(conn)

    profile = tmp_path / "profile.md"
    profile.write_text("candidate profile body")
    resume = tmp_path / "master_resume.md"
    resume.write_text("master resume body")

    with patch("findajob.speculative.runner._call_aichat") as mock_call:
        mock_call.side_effect = [_ok_briefing(), _ok_role_cards()]
        run_research(
            conn=conn,
            request_id=req_id,
            profile_path=profile,
            master_resume_path=resume,
            companies_dir=tmp_path / "companies",
        )

    assert mock_call.call_count == 2
    # First call is candidate_led_briefing, second is speculative_roles_synth
    first_role = mock_call.call_args_list[0][0][0]
    second_role = mock_call.call_args_list[1][0][0]
    assert first_role == "candidate_led_briefing"
    assert second_role == "speculative_roles_synth"

    # Row updated
    row = conn.execute("SELECT * FROM speculative_requests WHERE id=?", (req_id,)).fetchone()
    assert row["status"] == "ready_for_review"
    assert row["briefing_md"] == _ok_briefing()
    assert row["role_cards_json"] == _ok_role_cards()
    assert row["briefing_folder"] is not None
    assert row["research_completed_at"] is not None

    # Folder + briefing.md exist on disk
    folder = tmp_path / "companies" / row["briefing_folder"]
    assert folder.exists()
    assert (folder / "briefing.md").read_text() == _ok_briefing()


def test_run_research_briefing_failure_sets_status_failed(tmp_path):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    req_id = _seed(conn)

    profile = tmp_path / "profile.md"; profile.write_text("p")
    resume = tmp_path / "master_resume.md"; resume.write_text("r")

    with patch("findajob.speculative.runner._call_aichat") as mock_call:
        mock_call.side_effect = RuntimeError("aichat-ng exit 1: rate limited")
        run_research(
            conn=conn,
            request_id=req_id,
            profile_path=profile,
            master_resume_path=resume,
            companies_dir=tmp_path / "companies",
        )

    row = conn.execute("SELECT * FROM speculative_requests WHERE id=?", (req_id,)).fetchone()
    assert row["status"] == "failed"
    assert "rate limited" in (row["error_message"] or "")
    assert row["briefing_md"] is None
    assert row["role_cards_json"] is None


def test_run_research_synth_failure_preserves_briefing(tmp_path):
    """If briefing succeeds but role-synth fails, briefing_md is preserved
    in the row so a retry only re-runs the synth step."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    req_id = _seed(conn)

    profile = tmp_path / "profile.md"; profile.write_text("p")
    resume = tmp_path / "master_resume.md"; resume.write_text("r")

    with patch("findajob.speculative.runner._call_aichat") as mock_call:
        mock_call.side_effect = [_ok_briefing(), RuntimeError("synth failed: invalid JSON")]
        run_research(
            conn=conn,
            request_id=req_id,
            profile_path=profile,
            master_resume_path=resume,
            companies_dir=tmp_path / "companies",
        )

    row = conn.execute("SELECT * FROM speculative_requests WHERE id=?", (req_id,)).fetchone()
    assert row["status"] == "failed"
    assert row["briefing_md"] == _ok_briefing()
    assert row["role_cards_json"] is None
    assert "synth failed" in (row["error_message"] or "")
```

- [ ] **Step 2: Run test to verify failure**

```bash
uv run pytest tests/test_speculative_runner.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement runner**

Create `src/findajob/speculative/runner.py`:

```python
"""Speculative research runner.

Invoked as a detached subprocess via scripts/run_speculative_research.py
(itself spawned from POST /ingest/speculative). Single entry point:
``run_research(conn, request_id, profile_path, master_resume_path, companies_dir)``.

Lifecycle:
    status='researching'  ->  call briefing role  ->  call synth role  ->
    write briefing folder + briefing.md  ->  status='ready_for_review'

On any failure: status='failed' + error_message, partial state
(briefing_md if briefing call succeeded) preserved for retry.
"""

from __future__ import annotations

import sqlite3
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from findajob.paths import AICHAT
from findajob.speculative.parser import parse_role_cards
from findajob.speculative.storage import write_briefing
from findajob.utils import log_event

_BRIEFING_ROLE = "candidate_led_briefing"
_SYNTH_ROLE = "speculative_roles_synth"
_BRIEFING_PROMPT_VERSION = f"{_BRIEFING_ROLE}@v1"
_SYNTH_PROMPT_VERSION = f"{_SYNTH_ROLE}@v1"


def run_research(
    *,
    conn: sqlite3.Connection,
    request_id: int,
    profile_path: Path,
    master_resume_path: Path,
    companies_dir: Path,
) -> None:
    """Run briefing + role-synth for the given speculative_requests row.

    Idempotency: caller is responsible for ensuring the row exists with
    status='researching'. This function updates it to 'ready_for_review'
    or 'failed'.
    """
    row = conn.execute(
        "SELECT id, company, hint, personal_notes, briefing_md FROM speculative_requests WHERE id=?",
        (request_id,),
    ).fetchone()
    if row is None:
        raise RuntimeError(f"speculative_requests id={request_id} not found")

    company = row["company"]
    hint = row["hint"] or ""
    personal_notes = row["personal_notes"] or ""

    profile = profile_path.read_text() if profile_path.exists() else ""
    master_resume = master_resume_path.read_text() if master_resume_path.exists() else ""

    log_event("speculative_research_started", request_id=request_id, company=company)

    # Step 1: briefing (skip if already cached on retry)
    briefing_md = row["briefing_md"]
    if not briefing_md:
        try:
            briefing_md = _call_aichat(
                _BRIEFING_ROLE,
                vars_={
                    "company": company,
                    "hint": hint,
                    "personal_notes": personal_notes,
                    "candidate_profile": profile,
                    "master_resume": master_resume,
                },
            )
        except Exception as e:
            _mark_failed(conn, request_id, f"briefing failed: {e}")
            log_event("speculative_research_failed", request_id=request_id, stage="briefing", error=str(e))
            return
        conn.execute(
            "UPDATE speculative_requests SET briefing_md=?, briefing_prompt_version=? WHERE id=?",
            (briefing_md, _BRIEFING_PROMPT_VERSION, request_id),
        )
        conn.commit()

    # Step 2: role synth
    try:
        synth_raw = _call_aichat(
            _SYNTH_ROLE,
            vars_={
                "candidate_profile": profile,
                "master_resume": master_resume,
                "briefing": briefing_md,
            },
        )
        # Validate parses cleanly so the review page never sees garbage.
        _ = parse_role_cards(synth_raw)
    except Exception as e:
        _mark_failed(conn, request_id, f"synth failed: {e}")
        log_event("speculative_research_failed", request_id=request_id, stage="synth", error=str(e))
        return

    # Step 3: write briefing folder
    folder = write_briefing(base_dir=companies_dir, company=company, briefing_md=briefing_md)
    folder_name = folder.name

    # Step 4: finalize
    now = datetime.now(UTC).isoformat()
    conn.execute(
        """UPDATE speculative_requests
           SET role_cards_json=?, synth_prompt_version=?, briefing_folder=?,
               status='ready_for_review', research_completed_at=?
           WHERE id=?""",
        (synth_raw, _SYNTH_PROMPT_VERSION, folder_name, now, request_id),
    )
    conn.commit()
    log_event("speculative_research_complete", request_id=request_id, company=company, folder=folder_name)


def _mark_failed(conn: sqlite3.Connection, request_id: int, msg: str) -> None:
    conn.execute(
        "UPDATE speculative_requests SET status='failed', error_message=? WHERE id=?",
        (msg, request_id),
    )
    conn.commit()


def _call_aichat(role: str, *, vars_: dict[str, str]) -> str:
    """Invoke aichat-ng with the named role, passing template vars via stdin.

    aichat-ng convention: pass the role's template variables as a single
    user-message string with embedded {{key}} placeholders pre-substituted.
    """
    body = "\n\n".join(f"# {k}\n{v}" for k, v in vars_.items())
    proc = subprocess.run(
        [AICHAT, "-r", role],
        input=body,
        capture_output=True,
        text=True,
        timeout=600,  # 10 min: deep-research can take 1-5 min, plus margin
    )
    if proc.returncode != 0:
        raise RuntimeError(f"aichat-ng exit {proc.returncode}: {proc.stderr.strip()[-500:]}")
    return proc.stdout.strip()
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_speculative_runner.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/findajob/speculative/runner.py tests/test_speculative_runner.py
git commit -m "$(cat <<'EOF'
feat(speculative): runner orchestrates briefing + synth (B2.6 of #131)

Single entry: run_research(conn, request_id, profile_path,
master_resume_path, companies_dir). Calls briefing first (perplexity
sonar-deep-research), preserves briefing_md to row before synth call so
retries skip the expensive step. Validates synth output via parser before
declaring ready_for_review. On any failure, persists status='failed' +
error_message and emits speculative_research_failed event.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 17: Implement `speculative.approver` — write `jobs` rows from kept cards

**Files:**
- Create: `src/findajob/speculative/approver.py`
- Create: `tests/test_speculative_approver.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_speculative_approver.py`:

```python
"""Tests for findajob.speculative.approver — writes jobs rows on Approve."""

from __future__ import annotations

import json
import sqlite3

import pytest

from findajob.speculative.approver import approve_request

JOBS_SCHEMA = """
CREATE TABLE jobs (
    id TEXT PRIMARY KEY,
    fingerprint TEXT UNIQUE NOT NULL,
    url TEXT NOT NULL,
    title TEXT NOT NULL,
    company TEXT NOT NULL,
    location TEXT DEFAULT '',
    source TEXT NOT NULL,
    raw_jd_text TEXT,
    relevance_score INTEGER,
    interview_likelihood INTEGER,
    strengths_alignment TEXT,
    industry_sector TEXT,
    comp_estimate TEXT DEFAULT '',
    ai_notes TEXT,
    score_status TEXT,
    score_flag_reason TEXT,
    remote_status TEXT DEFAULT 'Unknown',
    network_depth INTEGER DEFAULT 0,
    known_contacts TEXT DEFAULT '',
    stage TEXT DEFAULT 'discovered',
    stage_updated TEXT,
    status TEXT DEFAULT 'active',
    apply_flag INTEGER DEFAULT 0,
    reject_reason TEXT DEFAULT '',
    prep_folder_path TEXT,
    gdrive_folder_url TEXT,
    fit_score REAL,
    probability_score REAL,
    user_notes TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    dupe_of TEXT DEFAULT '',
    synthetic INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE speculative_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company TEXT NOT NULL,
    hint TEXT,
    personal_notes TEXT,
    status TEXT NOT NULL DEFAULT 'researching',
    error_message TEXT,
    briefing_md TEXT,
    role_cards_json TEXT,
    briefing_folder TEXT,
    submitted_at TEXT NOT NULL DEFAULT (datetime('now')),
    research_completed_at TEXT,
    approved_at TEXT,
    approved_role_count INTEGER,
    briefing_prompt_version TEXT,
    synth_prompt_version TEXT
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
"""


def _seed_ready(conn: sqlite3.Connection, n_cards: int = 3) -> int:
    cards = [
        {"title": f"Role {i}", "description": "D", "why_this_fits_candidate": "W",
         "likely_team_or_org": "T", "suggested_contact_type": "recruiter"}
        for i in range(n_cards)
    ]
    cur = conn.execute(
        """INSERT INTO speculative_requests
           (company, status, briefing_md, role_cards_json, briefing_folder)
           VALUES (?, 'ready_for_review', ?, ?, ?)""",
        ("PSIQuantum", "# briefing\n", json.dumps(cards), "PSIQuantum_SPECULATIVE_2026-04-28_140000"),
    )
    conn.commit()
    return cur.lastrowid


def test_approve_writes_one_job_per_kept_card():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(JOBS_SCHEMA)
    req_id = _seed_ready(conn, n_cards=3)

    approve_request(conn, request_id=req_id, kept_indices=[0, 2])

    jobs = conn.execute("SELECT * FROM jobs ORDER BY title").fetchall()
    assert len(jobs) == 2
    assert all(j["synthetic"] == 1 for j in jobs)
    assert all(j["source"] == "web_speculative" for j in jobs)
    assert all(j["title"].startswith("[SPEC] ") for j in jobs)
    assert all(j["stage"] == "scored" for j in jobs)
    titles = sorted(j["title"] for j in jobs)
    assert titles == ["[SPEC] Role 0", "[SPEC] Role 2"]


def test_approve_updates_request_status_and_count():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(JOBS_SCHEMA)
    req_id = _seed_ready(conn, n_cards=4)

    approve_request(conn, request_id=req_id, kept_indices=[1, 3])

    row = conn.execute("SELECT * FROM speculative_requests WHERE id=?", (req_id,)).fetchone()
    assert row["status"] == "approved"
    assert row["approved_role_count"] == 2
    assert row["approved_at"] is not None


def test_approve_with_zero_kept_indices_marks_trashed():
    """Approving with all cards dropped means 'I changed my mind' — equivalent to trash."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(JOBS_SCHEMA)
    req_id = _seed_ready(conn, n_cards=3)

    approve_request(conn, request_id=req_id, kept_indices=[])

    row = conn.execute("SELECT * FROM speculative_requests WHERE id=?", (req_id,)).fetchone()
    assert row["status"] == "trashed"
    job_count = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    assert job_count == 0


def test_approve_rejects_non_ready_status():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(JOBS_SCHEMA)
    cur = conn.execute("INSERT INTO speculative_requests (company, status) VALUES (?, 'researching')", ("X",))
    req_id = cur.lastrowid

    with pytest.raises(ValueError, match="status"):
        approve_request(conn, request_id=req_id, kept_indices=[0])
```

- [ ] **Step 2: Run test to verify failure**

```bash
uv run pytest tests/test_speculative_approver.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement approver**

Create `src/findajob/speculative/approver.py`:

```python
"""Approver: on operator approve, write 1 jobs row per kept role card.

Synthetic rows ship with:
- synthetic=1
- source='web_speculative'
- title prefixed with [SPEC]
- stage='scored'
- ai_notes populated from the card's why_this_fits + team

Approving with kept_indices=[] is equivalent to trash — sets status='trashed'.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import UTC, datetime

from findajob.cleaning import fingerprint
from findajob.speculative.parser import parse_role_cards
from findajob.utils import log_event, write_audit


def approve_request(
    conn: sqlite3.Connection,
    *,
    request_id: int,
    kept_indices: list[int],
) -> list[str]:
    """Approve a ready_for_review request, writing one jobs row per kept card.

    Returns the list of fingerprints written. Empty list when kept_indices is empty
    (status='trashed' instead of 'approved').

    Raises ValueError if the request is not in 'ready_for_review' status.
    """
    row = conn.execute(
        "SELECT id, company, status, role_cards_json, briefing_folder FROM speculative_requests WHERE id=?",
        (request_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"speculative_requests id={request_id} not found")
    if row["status"] != "ready_for_review":
        raise ValueError(
            f"cannot approve request id={request_id}: status is {row['status']!r}, expected 'ready_for_review'"
        )

    if not kept_indices:
        conn.execute(
            "UPDATE speculative_requests SET status='trashed' WHERE id=?", (request_id,),
        )
        conn.commit()
        log_event("speculative_request_trashed", request_id=request_id, company=row["company"])
        return []

    cards = parse_role_cards(row["role_cards_json"])
    company = row["company"]
    now = datetime.now(UTC).isoformat()
    fingerprints: list[str] = []

    for idx in kept_indices:
        if idx < 0 or idx >= len(cards):
            raise ValueError(f"kept_indices contains out-of-range index {idx} (have {len(cards)} cards)")
        card = cards[idx]
        title = f"[SPEC] {card.title}"
        ai_notes = (
            f"WHY THIS FITS: {card.why_this_fits_candidate}\n\n"
            f"LIKELY TEAM: {card.likely_team_or_org}\n\n"
            f"SUGGESTED CONTACT: {card.suggested_contact_type}"
        )
        # Speculative rows have no URL — synthesize a sentinel that's distinct.
        url = f"speculative://{company}/{idx}/{request_id}"
        # location is empty for speculative; relevance_score uses a neutral default 7.
        # Using fingerprint() of (title, company, '') — same hashing as real rows so
        # the dedup logic doesn't accidentally reject a real posting that happens to
        # share title/company later (different from speculative=1; collisions are vanishingly unlikely).
        fp = fingerprint(title, company, "")
        job_id = str(uuid.uuid4())
        conn.execute(
            """INSERT INTO jobs (id, fingerprint, url, title, company, location, source,
                                  raw_jd_text, relevance_score, score_status,
                                  ai_notes, stage, stage_updated, synthetic,
                                  created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, '', 'web_speculative', ?, 7, 'scored',
                       ?, 'scored', ?, 1, ?, ?)""",
            (job_id, fp, url, title, company, card.description, ai_notes, now, now, now),
        )
        write_audit(conn, job_id, "stage", "", "scored")
        fingerprints.append(fp)

    conn.execute(
        """UPDATE speculative_requests
           SET status='approved', approved_at=?, approved_role_count=?
           WHERE id=?""",
        (now, len(kept_indices), request_id),
    )
    conn.commit()
    log_event(
        "speculative_request_approved",
        request_id=request_id,
        company=company,
        approved_count=len(kept_indices),
        fingerprints=fingerprints,
    )
    return fingerprints
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_speculative_approver.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/findajob/speculative/approver.py tests/test_speculative_approver.py
git commit -m "$(cat <<'EOF'
feat(speculative): approver writes jobs rows on operator approve (B2.7 of #131)

One jobs row per kept role card with synthetic=1, source='web_speculative',
[SPEC] title prefix, stage='scored'. Kept_indices=[] is equivalent to
trash. Status guard rejects approval when request isn't 'ready_for_review'.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 18: Add `scripts/run_speculative_research.py` entry point

**Files:**
- Create: `scripts/run_speculative_research.py`

- [ ] **Step 1: Author the entry script**

Create `scripts/run_speculative_research.py`:

```python
#!/usr/bin/env python3
"""Detached subprocess entry: run speculative research for a request_id.

Spawned from POST /ingest/speculative as a background process. Reads the
DB, runs run_research(), exits. Idempotent on re-spawn (e.g. for
regeneration) because run_research caches briefing_md across retries.

Usage:
    python scripts/run_speculative_research.py <request_id>
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

from findajob.paths import BASE
from findajob.speculative.runner import run_research
from findajob.utils import log_event


def main(argv: list[str]) -> int:
    if len(argv) != 2 or not argv[1].isdigit():
        print("usage: run_speculative_research.py <request_id>", file=sys.stderr)
        return 2
    request_id = int(argv[1])

    db_path = Path(BASE) / "data" / "pipeline.db"
    profile = Path(BASE) / "candidate_context" / "profile.md"
    master_resume = Path(BASE) / "candidate_context" / "master_resume.md"
    companies_dir = Path(BASE) / "companies"

    conn = sqlite3.connect(str(db_path), timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        run_research(
            conn=conn,
            request_id=request_id,
            profile_path=profile,
            master_resume_path=master_resume,
            companies_dir=companies_dir,
        )
    except Exception as e:
        log_event("speculative_research_uncaught_exception", request_id=request_id, error=str(e))
        # run_research already best-efforts a status='failed' write on known errors;
        # this catches truly unexpected (e.g. DB connection errors) so the process
        # never exits without recording state.
        try:
            conn.execute(
                "UPDATE speculative_requests SET status='failed', error_message=? WHERE id=?",
                (f"unexpected: {e}", request_id),
            )
            conn.commit()
        except Exception:
            pass
        return 1
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
```

- [ ] **Step 2: Smoke-test the entry**

```bash
chmod +x scripts/run_speculative_research.py
uv run python scripts/run_speculative_research.py
```

Expected: usage message + exit code 2 (correctly rejecting missing arg).

```bash
uv run python scripts/run_speculative_research.py abc
```

Expected: usage message + exit code 2.

- [ ] **Step 3: Commit**

```bash
git add scripts/run_speculative_research.py
git commit -m "$(cat <<'EOF'
feat(speculative): scripts/run_speculative_research.py async entry (B2.8 of #131)

Detached-subprocess entry point spawned by POST /ingest/speculative.
Wraps run_research() with top-level except that always writes status=failed
on uncaught exception, so the speculative_requests row never gets stuck
in 'researching' due to a Python crash.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 19: Run full CI + push + open PR for B2

- [ ] **Step 1: Run linters and full test suite**

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy src/findajob
uv run pytest -x
```

Expected: all green.

- [ ] **Step 2: Push and open PR**

```bash
git push -u origin feat/131-b2-synthesis
gh pr create --title "feat(speculative): briefing + role-synth pipeline runner (B2 of #131)" --body "$(cat <<'EOF'
## Summary

- Adds `candidate_led_briefing` (Perplexity Sonar Deep Research) and `speculative_roles_synth` (Claude Sonnet 4.6) role files.
- New `src/findajob/speculative/` package: `runner.py` orchestrates briefing → synth; `parser.py` validates the JSON-array role-cards output; `approver.py` writes one `jobs` row per kept card on operator approve; `storage.py` lays out the speculative briefing folder.
- New `scripts/run_speculative_research.py` is the detached-subprocess entry — POST handler in B3 will spawn it.

This is **B2 of 4** for #131. After merge, speculative research can be invoked headless against a pre-INSERTed `speculative_requests` row; B3 ships the web form / status / review / approve UX.

## Test plan

- [ ] `uv run pytest tests/test_speculative_*` green
- [ ] Manual smoke (post-merge): `INSERT INTO speculative_requests (company, status) VALUES ('PSIQuantum', 'researching')` on a non-prod DB, then `python scripts/run_speculative_research.py <id>`; observe row transition to `ready_for_review`, briefing folder + briefing.md created.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 3: Wait for CI; merge when green**

```bash
gh pr checks --watch
gh pr merge --squash --delete-branch
git fetch origin && git checkout main && git pull
```

---

## Phase B3 — Web Form + Status + Review + Approve

**Branch:** `feat/131-b3-web`
**Branch base:** `origin/main` (post-B2 merge)
**PR title:** `feat(speculative): /ingest/ form mode + status/review/approve UX (B3 of #131)`

### Task 20: Branch + sketch route module

**Files:**
- Create: `src/findajob/web/routes/speculative.py`

- [ ] **Step 1: Branch**

```bash
git fetch origin
git checkout -b feat/131-b3-web origin/main
```

- [ ] **Step 2: Scaffold the routes module**

Create `src/findajob/web/routes/speculative.py`:

```python
"""Web routes for speculative ingest (#131 B3).

Endpoints:
    POST /ingest/speculative              — form submit (kicks subprocess)
    GET  /speculative/status/{id}         — async status page (HTMX poll)
    GET  /speculative/status/{id}/poll    — HTMX poll fragment
    GET  /speculative/review/{id}         — review page (briefing + role cards)
    POST /speculative/approve/{id}        — write jobs rows from kept cards
    POST /speculative/regenerate/{id}     — re-run research (resets status to researching)
    POST /speculative/trash/{id}          — drop submission, no jobs rows written
"""

from __future__ import annotations

import sqlite3
import subprocess
import sys
from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from findajob.paths import BASE
from findajob.speculative.approver import approve_request

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(BASE) / "src" / "findajob" / "web" / "templates"))

DB_PATH = Path(BASE) / "data" / "pipeline.db"


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.row_factory = sqlite3.Row
    return conn
```

(The actual route handlers land in subsequent tasks. This task just scaffolds.)

- [ ] **Step 3: Commit**

```bash
git add src/findajob/web/routes/speculative.py
git commit -m "$(cat <<'EOF'
feat(web): scaffold speculative routes module (B3.1 of #131)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 21: `POST /ingest/speculative` — form handler + subprocess spawn

**Files:**
- Modify: `src/findajob/web/routes/speculative.py` — add handler
- Test: `tests/test_speculative_routes.py` — new file

- [ ] **Step 1: Write the failing test**

Create `tests/test_speculative_routes.py`:

```python
"""Routes tests for speculative ingest. FastAPI TestClient + in-memory DB."""

from __future__ import annotations

import sqlite3
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from findajob.web.routes import speculative as spec_routes


def _make_app(db_path):
    app = FastAPI()
    app.include_router(spec_routes.router)
    spec_routes.DB_PATH = db_path
    return app


def _make_db(tmp_path):
    db = tmp_path / "p.db"
    conn = sqlite3.connect(str(db))
    conn.executescript("""
        CREATE TABLE speculative_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company TEXT NOT NULL,
            hint TEXT,
            personal_notes TEXT,
            status TEXT NOT NULL DEFAULT 'researching',
            error_message TEXT,
            briefing_md TEXT,
            role_cards_json TEXT,
            briefing_folder TEXT,
            submitted_at TEXT NOT NULL DEFAULT (datetime('now')),
            research_completed_at TEXT,
            approved_at TEXT,
            approved_role_count INTEGER,
            briefing_prompt_version TEXT,
            synth_prompt_version TEXT
        );
    """)
    conn.commit()
    conn.close()
    return db


def test_post_speculative_inserts_row_and_spawns_subprocess(tmp_path):
    db = _make_db(tmp_path)
    app = _make_app(db)
    client = TestClient(app)

    with patch("findajob.web.routes.speculative.subprocess.Popen") as mock_popen:
        resp = client.post(
            "/ingest/speculative",
            data={"company": "PSIQuantum", "hint": "advanced computing", "personal_notes": ""},
            follow_redirects=False,
        )

    assert resp.status_code == 303
    assert resp.headers["location"].startswith("/speculative/status/")
    assert mock_popen.call_count == 1
    # Subprocess command should be python scripts/run_speculative_research.py <id>
    args = mock_popen.call_args[0][0]
    assert "run_speculative_research.py" in str(args[1]) or "run_speculative_research.py" in str(args)

    conn = sqlite3.connect(str(db))
    row = conn.execute("SELECT * FROM speculative_requests").fetchone()
    assert row is not None
    cols = [d[0] for d in conn.execute("PRAGMA table_info(speculative_requests)").fetchall()]
    company_idx = cols.index("company")
    status_idx = cols.index("status")
    assert row[company_idx] == "PSIQuantum"
    assert row[status_idx] == "researching"


def test_post_speculative_rejects_empty_company(tmp_path):
    db = _make_db(tmp_path)
    app = _make_app(db)
    client = TestClient(app)

    resp = client.post(
        "/ingest/speculative",
        data={"company": "", "hint": "", "personal_notes": ""},
        follow_redirects=False,
    )
    assert resp.status_code == 400
```

- [ ] **Step 2: Run test to verify failure**

```bash
uv run pytest tests/test_speculative_routes.py::test_post_speculative_inserts_row_and_spawns_subprocess -v
```

Expected: 404 or AttributeError (handler not defined).

- [ ] **Step 3: Implement the handler**

Append to `src/findajob/web/routes/speculative.py`:

```python
@router.post("/ingest/speculative")
def post_speculative(
    company: str = Form(...),
    hint: str = Form(""),
    personal_notes: str = Form(""),
) -> RedirectResponse:
    company = company.strip()
    if not company:
        raise HTTPException(status_code=400, detail="company is required")
    conn = _conn()
    try:
        cur = conn.execute(
            """INSERT INTO speculative_requests (company, hint, personal_notes, status)
               VALUES (?, ?, ?, 'researching')""",
            (company, hint.strip() or None, personal_notes.strip() or None),
        )
        conn.commit()
        request_id = cur.lastrowid
    finally:
        conn.close()

    # Detached subprocess — same pattern as scripts/prep_application.py spawn
    script_path = Path(BASE) / "scripts" / "run_speculative_research.py"
    subprocess.Popen(
        [sys.executable, str(script_path), str(request_id)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    return RedirectResponse(url=f"/speculative/status/{request_id}", status_code=303)
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_speculative_routes.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add src/findajob/web/routes/speculative.py tests/test_speculative_routes.py
git commit -m "$(cat <<'EOF'
feat(web): POST /ingest/speculative kicks subprocess + redirects to status (B3.2 of #131)

Validates company is non-empty, INSERTs the speculative_requests row in
status='researching', spawns scripts/run_speculative_research.py
detached, 303s to /speculative/status/{id}.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 22: Status page + HTMX polling fragment

**Files:**
- Modify: `src/findajob/web/routes/speculative.py` — add `GET /speculative/status/{id}` and `GET /speculative/status/{id}/poll`
- Create: `src/findajob/web/templates/speculative/status.html`
- Create: `src/findajob/web/templates/speculative/_status_fragment.html`

- [ ] **Step 1: Author the templates**

Create `src/findajob/web/templates/speculative/status.html`:

```html
{% extends "base.html" %}
{% block content %}
<div class="max-w-3xl mx-auto p-6">
  <h1 class="text-2xl font-bold mb-4">Speculative submission for {{ row.company }}</h1>
  <div id="status" hx-get="/speculative/status/{{ row.id }}/poll" hx-trigger="every 5s" hx-swap="outerHTML">
    {% include "speculative/_status_fragment.html" %}
  </div>
</div>
{% endblock %}
```

Create `src/findajob/web/templates/speculative/_status_fragment.html`:

```html
{% if row.status == 'researching' %}
  <div class="rounded border p-4 bg-blue-50">
    <div class="font-semibold">Researching — Perplexity Deep Research takes 1–5 minutes.</div>
    <div class="text-sm text-gray-600 mt-2">This page auto-refreshes every 5 seconds.</div>
  </div>
{% elif row.status == 'ready_for_review' %}
  <div class="rounded border p-4 bg-green-50" hx-get="/speculative/review/{{ row.id }}" hx-trigger="load" hx-target="body" hx-push-url="true">
    Research complete — redirecting to review page…
  </div>
  <script>window.location = "/speculative/review/{{ row.id }}";</script>
{% elif row.status == 'failed' %}
  <div class="rounded border p-4 bg-red-50">
    <div class="font-semibold">Research failed</div>
    <div class="mt-2 text-sm">{{ row.error_message or "(no error message recorded)" }}</div>
    <form method="post" action="/speculative/regenerate/{{ row.id }}" class="mt-4">
      <button type="submit" class="btn btn-primary">Retry</button>
    </form>
    <form method="post" action="/speculative/trash/{{ row.id }}" class="mt-2">
      <button type="submit" class="btn btn-secondary">Trash</button>
    </form>
  </div>
{% else %}
  <div class="rounded border p-4 bg-gray-50">Status: {{ row.status }}</div>
{% endif %}
```

- [ ] **Step 2: Add the route handlers**

Append to `src/findajob/web/routes/speculative.py`:

```python
@router.get("/speculative/status/{request_id}", response_class=HTMLResponse)
def get_status(request: Request, request_id: int):
    conn = _conn()
    try:
        row = conn.execute(
            "SELECT * FROM speculative_requests WHERE id=?", (request_id,)
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        raise HTTPException(status_code=404, detail="speculative request not found")
    return templates.TemplateResponse("speculative/status.html", {"request": request, "row": dict(row)})


@router.get("/speculative/status/{request_id}/poll", response_class=HTMLResponse)
def poll_status(request: Request, request_id: int):
    conn = _conn()
    try:
        row = conn.execute(
            "SELECT * FROM speculative_requests WHERE id=?", (request_id,)
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse(
        "speculative/_status_fragment.html",
        {"request": request, "row": dict(row)},
    )
```

- [ ] **Step 3: Append tests for the status routes**

Append to `tests/test_speculative_routes.py`:

```python
def test_get_status_renders_researching(tmp_path):
    db = _make_db(tmp_path)
    conn = sqlite3.connect(str(db))
    conn.execute("INSERT INTO speculative_requests (company, status) VALUES ('PSI', 'researching')")
    conn.commit()
    conn.close()

    app = _make_app(db)
    client = TestClient(app)
    resp = client.get("/speculative/status/1")
    assert resp.status_code == 200
    assert "Researching" in resp.text


def test_poll_returns_fragment(tmp_path):
    db = _make_db(tmp_path)
    conn = sqlite3.connect(str(db))
    conn.execute("INSERT INTO speculative_requests (company, status) VALUES ('PSI', 'failed')")
    conn.execute("UPDATE speculative_requests SET error_message='budget exceeded' WHERE company='PSI'")
    conn.commit()
    conn.close()

    app = _make_app(db)
    client = TestClient(app)
    resp = client.get("/speculative/status/1/poll")
    assert resp.status_code == 200
    assert "Research failed" in resp.text
    assert "budget exceeded" in resp.text
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_speculative_routes.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/findajob/web/routes/speculative.py src/findajob/web/templates/speculative/ tests/test_speculative_routes.py
git commit -m "$(cat <<'EOF'
feat(web): speculative status page with HTMX 5s poll (B3.3 of #131)

GET /speculative/status/{id} returns the page; nested div polls
/poll fragment every 5s. On status='ready_for_review' the fragment
location.replaces to the review page (HTMX hx-get + JS fallback).
On status='failed' the fragment shows the error + Retry + Trash buttons.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 23: Review page — render briefing + role cards with Keep/Drop toggles

**Files:**
- Modify: `src/findajob/web/routes/speculative.py` — add `GET /speculative/review/{id}`
- Create: `src/findajob/web/templates/speculative/review.html`

- [ ] **Step 1: Author the template**

Create `src/findajob/web/templates/speculative/review.html`:

```html
{% extends "base.html" %}
{% block content %}
<div class="max-w-4xl mx-auto p-6">
  <h1 class="text-2xl font-bold mb-2">Review — {{ row.company }}</h1>
  <div class="text-sm text-gray-600 mb-4">Submitted {{ row.submitted_at }} · Research completed {{ row.research_completed_at }}</div>

  <details class="mb-6 border rounded p-4">
    <summary class="font-semibold cursor-pointer">Briefing ({{ row.briefing_md|length }} chars)</summary>
    <div class="prose mt-4">{{ briefing_html|safe }}</div>
  </details>

  <h2 class="text-xl font-semibold mb-3">Role cards ({{ cards|length }})</h2>
  <form method="post" action="/speculative/approve/{{ row.id }}" class="space-y-4">
    {% for card in cards %}
      <div class="border rounded p-4">
        <label class="flex items-start gap-3">
          <input type="checkbox" name="keep" value="{{ loop.index0 }}" checked class="mt-1">
          <div class="flex-1">
            <div class="font-bold text-lg">{{ card.title }}</div>
            <div class="text-sm text-gray-600 mb-2">
              {{ card.likely_team_or_org }} · suggested contact: {{ card.suggested_contact_type }}
            </div>
            <div class="mb-3 whitespace-pre-line">{{ card.description }}</div>
            <div class="text-sm bg-gray-50 p-3 rounded">
              <span class="font-semibold">Why this fits you:</span> {{ card.why_this_fits_candidate }}
            </div>
          </div>
        </label>
      </div>
    {% endfor %}
    <div class="flex gap-3 pt-4">
      <button type="submit" class="btn btn-primary">Approve kept cards</button>
      <button type="submit" formaction="/speculative/regenerate/{{ row.id }}" formmethod="post" class="btn btn-secondary">Regenerate</button>
      <button type="submit" formaction="/speculative/trash/{{ row.id }}" formmethod="post" class="btn btn-warning">Trash</button>
    </div>
  </form>
</div>
{% endblock %}
```

- [ ] **Step 2: Add the route handler**

Append to `src/findajob/web/routes/speculative.py`:

```python
from findajob.speculative.parser import parse_role_cards
from findajob.web.markdown import render_markdown


@router.get("/speculative/review/{request_id}", response_class=HTMLResponse)
def get_review(request: Request, request_id: int):
    conn = _conn()
    try:
        row = conn.execute(
            "SELECT * FROM speculative_requests WHERE id=?", (request_id,)
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        raise HTTPException(status_code=404, detail="speculative request not found")
    if row["status"] != "ready_for_review":
        # Not ready — bounce to status page
        return RedirectResponse(url=f"/speculative/status/{request_id}", status_code=303)
    cards = parse_role_cards(row["role_cards_json"])
    briefing_html = render_markdown(row["briefing_md"] or "")
    return templates.TemplateResponse(
        "speculative/review.html",
        {"request": request, "row": dict(row), "cards": cards, "briefing_html": briefing_html},
    )
```

- [ ] **Step 3: Append a test**

Append to `tests/test_speculative_routes.py`:

```python
def test_get_review_renders_briefing_and_cards(tmp_path):
    import json as _json
    db = _make_db(tmp_path)
    conn = sqlite3.connect(str(db))
    conn.execute(
        """INSERT INTO speculative_requests (company, status, briefing_md, role_cards_json)
           VALUES ('PSI', 'ready_for_review', '# Briefing\nbody', ?)""",
        (_json.dumps([{
            "title": "Critical Infra Eng",
            "description": "Own GPU cluster bring-up.",
            "why_this_fits_candidate": "Resume bullet match.",
            "likely_team_or_org": "SiteOps",
            "suggested_contact_type": "hiring_manager",
        }]),),
    )
    conn.commit()
    conn.close()

    app = _make_app(db)
    client = TestClient(app)
    resp = client.get("/speculative/review/1")
    assert resp.status_code == 200
    assert "Critical Infra Eng" in resp.text
    assert "Own GPU cluster bring-up" in resp.text
    assert "SiteOps" in resp.text
    # All cards default-checked (keep on by default)
    assert 'value="0" checked' in resp.text


def test_get_review_redirects_when_not_ready(tmp_path):
    db = _make_db(tmp_path)
    conn = sqlite3.connect(str(db))
    conn.execute("INSERT INTO speculative_requests (company, status) VALUES ('PSI', 'researching')")
    conn.commit()
    conn.close()

    app = _make_app(db)
    client = TestClient(app)
    resp = client.get("/speculative/review/1", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/speculative/status/1"
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_speculative_routes.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add src/findajob/web/routes/speculative.py src/findajob/web/templates/speculative/review.html tests/test_speculative_routes.py
git commit -m "$(cat <<'EOF'
feat(web): speculative review page with role-card keep/drop UI (B3.4 of #131)

Renders briefing markdown via the shared render_markdown helper +
each role card with a default-checked Keep checkbox. Three submit
buttons (approve / regenerate / trash) on one form via formaction.
Redirects to status page when status is not ready_for_review.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 24: Approve / Regenerate / Trash handlers

**Files:**
- Modify: `src/findajob/web/routes/speculative.py` — add three POST handlers

- [ ] **Step 1: Author the handlers**

Append to `src/findajob/web/routes/speculative.py`:

```python
@router.post("/speculative/approve/{request_id}")
def post_approve(request_id: int, keep: list[int] = Form(default=[])) -> RedirectResponse:
    conn = _conn()
    try:
        approve_request(conn, request_id=request_id, kept_indices=keep)
    finally:
        conn.close()
    return RedirectResponse(url="/board/", status_code=303)


@router.post("/speculative/regenerate/{request_id}")
def post_regenerate(request_id: int) -> RedirectResponse:
    conn = _conn()
    try:
        row = conn.execute(
            "SELECT status FROM speculative_requests WHERE id=?", (request_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404)
        if row["status"] == "researching":
            raise HTTPException(status_code=409, detail="research already in flight")
        conn.execute(
            """UPDATE speculative_requests
               SET status='researching', error_message=NULL,
                   role_cards_json=NULL, briefing_folder=NULL,
                   research_completed_at=NULL
               WHERE id=?""",
            (request_id,),
        )
        # Note: briefing_md is intentionally NOT cleared — runner caches it
        # so retries skip the expensive briefing call. Caller can force a
        # fresh briefing by calling trash + new submit instead.
        conn.commit()
    finally:
        conn.close()

    script_path = Path(BASE) / "scripts" / "run_speculative_research.py"
    subprocess.Popen(
        [sys.executable, str(script_path), str(request_id)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    return RedirectResponse(url=f"/speculative/status/{request_id}", status_code=303)


@router.post("/speculative/trash/{request_id}")
def post_trash(request_id: int) -> RedirectResponse:
    conn = _conn()
    try:
        conn.execute(
            "UPDATE speculative_requests SET status='trashed' WHERE id=?",
            (request_id,),
        )
        conn.commit()
    finally:
        conn.close()
    return RedirectResponse(url="/ingest/", status_code=303)
```

- [ ] **Step 2: Append tests**

Append to `tests/test_speculative_routes.py`:

```python
def test_approve_writes_jobs_and_redirects_to_board(tmp_path):
    import json as _json
    db = _make_db(tmp_path)
    conn = sqlite3.connect(str(db))
    # Need jobs + audit_log tables for approve to write
    conn.executescript("""
        CREATE TABLE jobs (
            id TEXT PRIMARY KEY, fingerprint TEXT UNIQUE NOT NULL, url TEXT NOT NULL,
            title TEXT NOT NULL, company TEXT NOT NULL, location TEXT DEFAULT '',
            source TEXT NOT NULL, raw_jd_text TEXT, relevance_score INTEGER,
            score_status TEXT, ai_notes TEXT, stage TEXT, stage_updated TEXT,
            created_at TEXT DEFAULT (datetime('now')), updated_at TEXT DEFAULT (datetime('now')),
            synthetic INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL, field_changed TEXT NOT NULL,
            old_value TEXT, new_value TEXT, changed_at TEXT DEFAULT (datetime('now')), changed_by TEXT DEFAULT 'system'
        );
    """)
    conn.execute(
        """INSERT INTO speculative_requests (company, status, briefing_md, role_cards_json, briefing_folder)
           VALUES ('PSI', 'ready_for_review', '# b', ?, 'PSI_SPECULATIVE_2026-04-28_140000')""",
        (_json.dumps([{
            "title": "Eng A", "description": "D", "why_this_fits_candidate": "W",
            "likely_team_or_org": "T", "suggested_contact_type": "recruiter",
        }, {
            "title": "Eng B", "description": "D", "why_this_fits_candidate": "W",
            "likely_team_or_org": "T", "suggested_contact_type": "recruiter",
        }]),),
    )
    conn.commit()
    conn.close()

    app = _make_app(db)
    client = TestClient(app)
    resp = client.post("/speculative/approve/1", data={"keep": ["1"]}, follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/board/"

    conn = sqlite3.connect(str(db))
    titles = [r[0] for r in conn.execute("SELECT title FROM jobs").fetchall()]
    assert titles == ["[SPEC] Eng B"]


def test_trash_marks_status_and_redirects_to_ingest(tmp_path):
    db = _make_db(tmp_path)
    conn = sqlite3.connect(str(db))
    conn.execute("INSERT INTO speculative_requests (company, status) VALUES ('PSI', 'ready_for_review')")
    conn.commit()
    conn.close()

    app = _make_app(db)
    client = TestClient(app)
    resp = client.post("/speculative/trash/1", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/ingest/"
    conn = sqlite3.connect(str(db))
    assert conn.execute("SELECT status FROM speculative_requests").fetchone()[0] == "trashed"


def test_regenerate_409_when_research_already_in_flight(tmp_path):
    db = _make_db(tmp_path)
    conn = sqlite3.connect(str(db))
    conn.execute("INSERT INTO speculative_requests (company, status) VALUES ('PSI', 'researching')")
    conn.commit()
    conn.close()

    app = _make_app(db)
    client = TestClient(app)
    with patch("findajob.web.routes.speculative.subprocess.Popen") as mock_popen:
        resp = client.post("/speculative/regenerate/1", follow_redirects=False)
    assert resp.status_code == 409
    assert mock_popen.call_count == 0
```

- [ ] **Step 3: Run tests**

```bash
uv run pytest tests/test_speculative_routes.py -v
```

Expected: 9 passed.

- [ ] **Step 4: Commit**

```bash
git add src/findajob/web/routes/speculative.py tests/test_speculative_routes.py
git commit -m "$(cat <<'EOF'
feat(web): speculative approve/regenerate/trash handlers (B3.5 of #131)

POST /speculative/approve/{id}: parses 'keep' form list, calls
approve_request, redirects to /board/.
POST /speculative/regenerate/{id}: clears post-research state, re-spawns
the research subprocess (briefing_md preserved for retry-cheapness),
409s if research is still in flight.
POST /speculative/trash/{id}: marks status='trashed', redirects to /ingest/.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 25: Wire the new routes into the FastAPI app + add `/ingest/` mode toggle

**Files:**
- Modify: `src/findajob/web/app.py` — register `speculative.router`
- Modify: `src/findajob/web/routes/ingest.py` — add Speculative-mode link
- Modify: `src/findajob/web/templates/ingest/form.html` (or wherever the form lives) — add the toggle / second form section + soft-warn

- [ ] **Step 1: Register the router**

Read `src/findajob/web/app.py` and find where `routes/ingest` etc. are included. Add:

```python
from findajob.web.routes import speculative as _speculative_routes
app.include_router(_speculative_routes.router)
```

(Patch alongside existing `include_router` calls.)

- [ ] **Step 2: Add the speculative form section**

In the `/ingest/` form template, add a second section below the existing real-JD form:

```html
<section class="border-t mt-8 pt-8">
  <h2 class="text-xl font-semibold mb-2">Speculative submission</h2>
  <p class="text-sm text-gray-600 mb-4">
    No JD? Submit a company name and the pipeline will research them, synthesize
    plausible roles, and let you approve a cold-outreach package.
    <strong>Takes 1–5 minutes.</strong>
  </p>
  {% if today_speculative_count > 0 %}
    <div class="rounded bg-yellow-50 border border-yellow-300 p-3 mb-4 text-sm">
      You've already submitted {{ today_speculative_count }} speculative request(s) today
      (~${{ "%.2f"|format(today_speculative_count * 0.50) }} of Perplexity Deep Research).
      No hard cap — submit if it's worth it.
    </div>
  {% endif %}
  <form method="post" action="/ingest/speculative" class="space-y-3">
    <input type="text" name="company" placeholder="Company name (required)" required class="form-input w-full">
    <input type="text" name="hint" placeholder="Optional hint (e.g. 'data center team')" class="form-input w-full">
    <textarea name="personal_notes" placeholder="Optional connection notes" rows="2" class="form-input w-full"></textarea>
    <button type="submit" class="btn btn-primary">Submit speculative</button>
  </form>
</section>
```

- [ ] **Step 3: Update the `/ingest/` GET handler to count today's speculative submissions**

In `src/findajob/web/routes/ingest.py`, find the GET handler. Add to its template context:

```python
today_count = conn.execute(
    "SELECT COUNT(*) FROM speculative_requests WHERE date(submitted_at)=date('now', 'localtime')"
).fetchone()[0]
# pass as today_speculative_count to template
```

- [ ] **Step 4: Manual smoke + tests**

```bash
uv run pytest tests/ -k "ingest or speculative" -v
```

Then start the dev server:

```bash
uv run uvicorn findajob.web.app:create_app --factory --reload --port 8090
```

In a browser, hit `http://localhost:8090/ingest/` — verify the speculative section renders.

- [ ] **Step 5: Commit**

```bash
git add src/findajob/web/app.py src/findajob/web/routes/ingest.py src/findajob/web/templates/
git commit -m "$(cat <<'EOF'
feat(web): /ingest/ adds speculative submission section + soft-warn (B3.6 of #131)

Speculative form section + soft warning when today's speculative count > 0
(no hard cap, per Decision R2). Registers the speculative router on the
FastAPI app.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 26: Run full CI + push + open PR for B3

- [ ] **Step 1: Run linters and full test suite**

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy src/findajob
uv run pytest -x
```

- [ ] **Step 2: Push and open PR**

```bash
git push -u origin feat/131-b3-web
gh pr create --title "feat(speculative): /ingest/ form + status/review/approve UX (B3 of #131)" --body "$(cat <<'EOF'
## Summary

- New routes module `src/findajob/web/routes/speculative.py` with 7 endpoints (POST /ingest/speculative, GET /speculative/status/{id} + /poll, GET /speculative/review/{id}, POST /speculative/{approve,regenerate,trash}/{id}).
- Status page polls every 5s via HTMX until `status='ready_for_review'`, then auto-redirects to review.
- Review page renders briefing + role cards with default-checked Keep checkboxes; one form, three submit buttons via formaction.
- `/ingest/` form gets a Speculative section with a soft-warn when today's submission count > 0.

This is **B3 of 4** for #131. After merge, the operator can submit through the web form and approve role cards. B4 ships speculative-aware prep variants + sent-outreach button.

## Test plan

- [ ] `uv run pytest tests/test_speculative_routes.py` green
- [ ] Manual: `/ingest/` shows the speculative section; submit "PSIQuantum" + hint; verify subprocess starts (top), status page renders + polls, review page renders post-research
- [ ] Manual: hit Approve with 1 of 3 cards kept; verify dashboard now shows the [SPEC] row in `scored` stage with `synthetic=1` (in DB)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
gh pr checks --watch
gh pr merge --squash --delete-branch
git fetch origin && git checkout main && git pull
```

---

## Phase B4 — Speculative-Aware Prep + Sent-Outreach Button + Watchdog + Docs

**Branch:** `feat/131-b4-prep-and-button`
**Branch base:** `origin/main` (post-B3 merge)
**PR title:** `feat(speculative): speculative-aware prep + sent-outreach button + docs (B4 of #131)`

### Task 27: Branch + cover-letter prompt variant

**Files:**
- Modify: `config/roles/cover_letter_writer.md` — add speculative-aware section

- [ ] **Step 1: Branch**

```bash
git fetch origin
git checkout -b feat/131-b4-prep-and-button origin/main
```

- [ ] **Step 2: Add the variant block**

Edit `config/roles/cover_letter_writer.md`. Add a section near the top of the system prompt:

```markdown
## Mode — speculative vs. real posting

If the input contains a marker `<<SPECULATIVE_MODE>>`, you are writing a cold-outreach cover letter — there is no real job posting; the "JD" is a synthesized role description from the speculative_roles_synth role. In this mode:

- Open with explicit acknowledgment that this is unsolicited: "I noticed [specific hiring signal from briefing]. While I don't see a current opening that matches my profile exactly, I wanted to reach out because…"
- Frame the candidate's fit against the *briefing's* hiring signals rather than against a posted JD.
- End with a low-pressure ask: "If this resonates, I'd welcome a 20-minute conversation; if not, I appreciate you taking a look."

If `<<SPECULATIVE_MODE>>` is absent, write a standard cover letter for the real posting as before.
```

- [ ] **Step 3: Update `prep_application.py` to pass the marker for synthetic jobs**

Find where `cover_letter_writer` is invoked in `scripts/prep_application.py` (grep for the role name). Wrap the input:

```python
from findajob.utils import is_synthetic_job
# ...
prefix = "<<SPECULATIVE_MODE>>\n\n" if is_synthetic_job(job) else ""
cover_input = prefix + existing_cover_input
```

- [ ] **Step 4: Commit**

```bash
git add config/roles/cover_letter_writer.md scripts/prep_application.py
git commit -m "$(cat <<'EOF'
feat(roles): cover_letter_writer speculative-mode variant (B4.1 of #131)

Adds <<SPECULATIVE_MODE>> marker handling: cold-outreach framing,
acknowledges unsolicited contact, ends with low-pressure ask. Marker
is injected by prep_application.py when job.synthetic=1.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 28: Outreach-drafter prompt variant

**Files:**
- Modify: `config/roles/outreach_drafter.md` — add speculative-mode section

- [ ] **Step 1: Add the variant block**

Edit `config/roles/outreach_drafter.md`. Add a section similar to the cover-letter one:

```markdown
## Mode — speculative vs. real posting

If input contains `<<SPECULATIVE_MODE>>`, you're drafting cold outreach without a real posting. In this mode:

- Address the recommended `suggested_contact_type` from the role card: a recruiter, hiring manager, or senior IC. Salutation register and length differ for each:
  - **recruiter:** brief (≤120 words), direct, leads with the hiring-signal you observed.
  - **hiring_manager:** mid-length (~180 words), highlights the specific role surface from the briefing and 2-3 candidate-resume bullets that map.
  - **senior_ic:** longest (~250 words), peer-to-peer register, focuses on shared technical context.
- Always include: (a) why you're reaching out *to this specific person*, (b) one concrete value-add from the candidate's background, (c) a low-pressure ask (e.g. "20-min coffee", "would you be open to forwarding this internally").
- Never sound like an automated mail merge.
```

- [ ] **Step 2: Update `prep_application.py` outreach call**

Mirror the cover-letter approach: prepend `<<SPECULATIVE_MODE>>\n\n` when `is_synthetic_job(job)`.

- [ ] **Step 3: Commit**

```bash
git add config/roles/outreach_drafter.md scripts/prep_application.py
git commit -m "$(cat <<'EOF'
feat(roles): outreach_drafter speculative-mode variant (B4.2 of #131)

Adapts register and length to the role-card's suggested_contact_type
(recruiter / hiring_manager / senior_ic). Marker injection in
prep_application.py mirrors the cover-letter pattern.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 29: `POST /board/jobs/{fp}/apply` — synthetic-aware `changed_by` branch

**Files:**
- Modify: `src/findajob/web/routes/board_actions.py` — add synthetic check
- Test: `tests/test_board_actions.py` — add test

- [ ] **Step 1: Locate the existing apply handler**

```bash
grep -n "def.*apply\|/apply" src/findajob/web/routes/board_actions.py
```

- [ ] **Step 2: Write the failing test**

Append to `tests/test_board_actions.py` (uses the existing module-level `client` fixture and `_fetch_audit` helper):

```python
class TestApplySyntheticBranch:
    """The /apply handler must write changed_by='outreach_button' when the
    target row has synthetic=1. Real rows keep the existing changed_by value."""

    def _insert_synthetic(self, client: TestClient, fingerprint: str = "fp_spec_drafted") -> str:
        """Add a synthetic job in materials_drafted stage to the test DB."""
        import uuid
        conn = sqlite3.connect(client._db_path)
        job_id = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO jobs (id, fingerprint, url, title, company, stage, source, synthetic) "
            "VALUES (?, ?, 'speculative://x', ?, 'PSI', 'materials_drafted', 'web_speculative', 1)",
            (job_id, fingerprint, "[SPEC] Critical Infra Eng"),
        )
        conn.commit()
        conn.close()
        return job_id

    def test_synthetic_apply_writes_outreach_button_changed_by(self, client: TestClient):
        self._insert_synthetic(client, "fp_spec_drafted")
        # Move it to materials_drafted via a manual UPDATE (already there from seed),
        # then hit /apply.
        response = client.post("/board/jobs/fp_spec_drafted/apply")
        assert response.status_code == 200
        assert _fetch_stage(client, "fp_spec_drafted") == "applied"

        # Inspect the changed_by on the stage transition row
        conn = sqlite3.connect(client._db_path)
        row = conn.execute(
            "SELECT al.changed_by FROM audit_log al JOIN jobs j ON j.id = al.job_id "
            "WHERE j.fingerprint=? AND al.field_changed='stage' AND al.new_value='applied'",
            ("fp_spec_drafted",),
        ).fetchone()
        conn.close()
        assert row is not None
        assert row[0] == "outreach_button", \
            f"synthetic /apply should write changed_by='outreach_button', got {row[0]!r}"

    def test_real_apply_does_not_use_outreach_button(self, client: TestClient):
        """Move fp_drafted (real, materials_drafted in seed) to applied via /apply."""
        response = client.post("/board/jobs/fp_drafted/apply")
        assert response.status_code == 200
        assert _fetch_stage(client, "fp_drafted") == "applied"

        conn = sqlite3.connect(client._db_path)
        row = conn.execute(
            "SELECT al.changed_by FROM audit_log al JOIN jobs j ON j.id = al.job_id "
            "WHERE j.fingerprint=? AND al.field_changed='stage' AND al.new_value='applied'",
            ("fp_drafted",),
        ).fetchone()
        conn.close()
        assert row is not None
        assert row[0] != "outreach_button", \
            f"real /apply must not use outreach_button changed_by, got {row[0]!r}"
```

Note: this assumes the seed `fp_drafted` row in the existing `client` fixture is in stage `materials_drafted`, which it is per `_insert_job(conn, fingerprint="fp_drafted", stage="materials_drafted")` at `test_board_actions.py:133`.

- [ ] **Step 3: Add the synthetic-aware branch in the apply handler**

In `src/findajob/web/routes/board_actions.py`, find the `apply` handler. The pattern looks like:

```python
write_audit(conn, job["id"], "stage", old_stage, "applied")
```

Change it to read the synthetic flag and pass `changed_by`:

```python
from findajob.utils import is_synthetic_job
# ...
changed_by = "outreach_button" if is_synthetic_job(job) else "user"  # or whatever the existing convention is
write_audit(conn, job["id"], "stage", old_stage, "applied", changed_by=changed_by)
```

If `write_audit` doesn't currently accept `changed_by`, add it as an optional kwarg in `findajob.utils.write_audit` with a default that matches existing behavior.

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_board_actions.py -v
```

- [ ] **Step 5: Commit**

```bash
git add src/findajob/web/routes/board_actions.py src/findajob/utils.py tests/test_board_actions.py
git commit -m "$(cat <<'EOF'
feat(web): /apply handler writes changed_by='outreach_button' for synthetic (B4.3 of #131)

Single-endpoint synthetic-aware branch. Server-derived from jobs.synthetic
so client cannot tamper with the audit signal. Stage transition itself
is unchanged (still applied), so the apply-gate query stays a single
predicate.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 30: Dashboard renders [SPEC] badge + flips button label per `synthetic`

**Files:**
- Modify: `src/findajob/web/templates/board/_job_row.html` — add badge + flip button text

- [ ] **Step 1: Edit the template**

In `src/findajob/web/templates/board/_job_row.html` (or wherever the dashboard row partial lives), find the title cell and the apply button:

```html
{% if job.synthetic %}
  <span class="inline-block px-2 py-0.5 text-xs font-bold bg-purple-100 text-purple-800 rounded">SPEC</span>
{% endif %}
<a href="{{ job.url }}">{{ job.title }}</a>
```

For the apply button:

```html
<button type="submit" formaction="/board/jobs/{{ job.fingerprint }}/apply" class="btn btn-sm btn-primary">
  {% if job.synthetic %}Sent Outreach{% else %}Applied{% endif %}
</button>
```

- [ ] **Step 2: Smoke-test in the browser**

Start the dev server, navigate to `/board/`, find a synthetic row from the B3 testing — verify the SPEC badge renders and the button reads "Sent Outreach."

- [ ] **Step 3: Commit**

```bash
git add src/findajob/web/templates/board/_job_row.html
git commit -m "$(cat <<'EOF'
feat(web): dashboard SPEC badge + Sent-Outreach button label (B4.4 of #131)

Template branches on jobs.synthetic. Badge is purely render-time
decoration (the [SPEC] title prefix is the data-side signal); button
URL is unchanged but label flips.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 31: Watchdog branch — fail stuck `researching` requests

**Files:**
- Modify: `scripts/watchdog.py` — add a new check for stuck speculative requests
- Test: `tests/test_watchdog.py` — add test

- [ ] **Step 1: Read the existing watchdog**

```bash
cat scripts/watchdog.py
```

- [ ] **Step 2: Append the new check**

In `scripts/watchdog.py`, after the existing `prep_in_progress` check, add:

```python
# Stuck speculative_requests: status='researching' for >10 min means the
# detached subprocess died without writing a status. Mark failed so the
# operator's status page surfaces a retry button instead of spinning.
STUCK_RESEARCH_MINUTES = 10
stuck_research = conn.execute(f"""
    SELECT id, company FROM speculative_requests
    WHERE status='researching'
      AND submitted_at < datetime('now', '-{STUCK_RESEARCH_MINUTES} minutes')
""").fetchall()
for sr in stuck_research:
    conn.execute(
        """UPDATE speculative_requests
           SET status='failed', error_message='research timed out (>10 min) — subprocess likely died'
           WHERE id=?""",
        (sr["id"],),
    )
    log_event("speculative_research_watchdog_failed", request_id=sr["id"], company=sr["company"])
conn.commit()
```

- [ ] **Step 3: Write a test**

Add to `tests/test_watchdog.py` (mirrors the existing `db` fixture pattern):

```python
def test_watchdog_marks_stuck_speculative_failed(db, monkeypatch):
    """speculative_requests rows in 'researching' status >10 min get marked failed."""
    db.executescript("""
        CREATE TABLE speculative_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'researching',
            error_message TEXT,
            briefing_md TEXT,
            role_cards_json TEXT,
            briefing_folder TEXT,
            submitted_at TEXT NOT NULL DEFAULT (datetime('now')),
            research_completed_at TEXT,
            approved_at TEXT,
            approved_role_count INTEGER
        );
    """)
    # 11 min ago — past the 10-min cutoff
    stale_at = (datetime.now(UTC) - timedelta(minutes=11)).isoformat()
    db.execute(
        "INSERT INTO speculative_requests (company, status, submitted_at) VALUES (?, 'researching', ?)",
        ("PSIQuantum", stale_at),
    )
    # 5 min ago — fresh, should not be touched
    fresh_at = (datetime.now(UTC) - timedelta(minutes=5)).isoformat()
    db.execute(
        "INSERT INTO speculative_requests (company, status, submitted_at) VALUES (?, 'researching', ?)",
        ("Recent Co", fresh_at),
    )
    db.commit()

    # Patch DB path on the watchdog module to point at our in-memory connection.
    # The existing watchdog uses a sqlite3.connect(DB_PATH); easiest path is to
    # extract its core check function or call its main() with a monkeypatched
    # connect. Pattern follows the existing test_watchdog.py fixture (which
    # patches sqlite3.connect on the watchdog module).
    monkeypatch.setattr(watchdog.sqlite3, "connect", lambda *_a, **_kw: db)

    watchdog.main()  # or whatever the entry name is in the existing watchdog

    rows = db.execute(
        "SELECT company, status, error_message FROM speculative_requests ORDER BY id"
    ).fetchall()
    stale, fresh = rows[0], rows[1]
    assert stale["status"] == "failed"
    assert "timed out" in (stale["error_message"] or "").lower()
    assert fresh["status"] == "researching"  # untouched
```

If `watchdog.main()` doesn't exist as a callable (e.g. the script runs at import), refactor watchdog into `def main()` first as part of this task before writing the test. The existing `test_watchdog.py` patterns (patch `sqlite3.connect`, call entry function) should be mirrored exactly.

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_watchdog.py -v
```

- [ ] **Step 5: Commit**

```bash
git add scripts/watchdog.py tests/test_watchdog.py
git commit -m "$(cat <<'EOF'
feat(watchdog): fail stuck speculative_requests after 10 min (B4.5 of #131)

Mirrors the existing prep_in_progress watchdog. 10-min threshold is
based on Deep Research's typical 1-5 min latency + safety margin. To be
calibrated against real submissions during pre-merge verification (see
spec's "Watchdog timing calibration" step).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 32: CLAUDE.md updates — full synthetic-jobs section + Pipeline Context Table rows + endpoint list

**Files:**
- Modify: `CLAUDE.md` — expand the B1 stub; add Pipeline Context Table rows

- [ ] **Step 1: Expand the synthetic-jobs section**

In `CLAUDE.md`, find the B1 stub section "Synthetic Jobs Convention" and replace it with the full version:

```markdown
### Synthetic Jobs Convention (Speculative Cold-Outreach)

Synthetic `jobs` rows are produced by the speculative ingest path
(`/ingest/?mode=speculative`, see #131) for cold-outreach to companies that
aren't currently posting a matching opening. Two new role files drive
synthesis: `candidate_led_briefing` (Perplexity Sonar Deep Research) for
the briefing, and `speculative_roles_synth` (Claude Sonnet 4.6) for the
1–5 candidate-tailored role cards.

**Marker:** `jobs.synthetic=1` (canonical) + `source='web_speculative'` +
`[SPEC] ` title prefix. The `[SPEC] ` prefix is render-time decoration;
the `synthetic` flag is the data-layer source of truth.

**Lifecycle invariants (enforced in code):**
- `findajob.actions.handle_rejection` and `handle_not_selected` SKIP
  `feedback_log` writes when `synthetic=1`.
- `findajob.scoring._build_feedback_block` LEFT JOINs to `jobs` and
  excludes `synthetic=1` rows.
- Speculative rows reuse the `applied` stage. The `/board/jobs/{fp}/apply`
  handler writes `changed_by='outreach_button'` when `synthetic=1`,
  otherwise the existing real-apply convention. Apply-gate query is a
  single predicate (`field_changed='stage' AND new_value='applied'`)
  — cold-outreach counts.
- Cover-letter and outreach prompts get a `<<SPECULATIVE_MODE>>` marker
  prepended when `synthetic=1`; both role files branch on that marker.

**Folder layout:**
- Briefing folder: `companies/{Company}_SPECULATIVE_{YYYY-MM-DD}_{HHMMSS}/briefing.md`
- Per-role prep folder (created on flag-for-prep): same convention as
  real prep folders, but the briefing reference points back at the
  speculative folder above (no re-research at prep time).

**Watchdog:** `scripts/watchdog.py` fails any `speculative_requests` row
stuck in `status='researching'` for >10 min — covers the case where the
detached subprocess died silently.

**Endpoints:** see "Web Is The Write Surface" section.
```

- [ ] **Step 2: Add new rows to the Pipeline Context Table**

In the existing Pipeline Context Table in `CLAUDE.md`, add:

```markdown
| `candidate_led_briefing` | `openrouter:perplexity/sonar-deep-research` — async, 1–5 min latency. Drives speculative briefing pass. Spawned as detached subprocess via `scripts/run_speculative_research.py`. |
| `speculative_roles_synth` | `openrouter:anthropic/claude-sonnet-4-6`, `max_tokens: 4096` — synthesizes 1–5 role cards from the briefing + candidate context. JSON-array output validated by `findajob.speculative.parser`. |
```

- [ ] **Step 3: Update "Web Is The Write Surface"**

In the existing "Web Is The Write Surface" section, add to the endpoint list:

```markdown
- `POST /ingest/speculative` → spawns `scripts/run_speculative_research.py` (async briefing + role synth)
- `GET /speculative/status/{id}` (+ `/poll` HTMX fragment) — research-status page
- `GET /speculative/review/{id}` — review-and-approve page
- `POST /speculative/{approve,regenerate,trash}/{id}` — approve writes `jobs` rows; regenerate re-spawns subprocess; trash marks status='trashed'
```

- [ ] **Step 4: Update "Output Folder Format"**

Add a sub-bullet:

```markdown
- Speculative briefings: `{Company}_SPECULATIVE_{YYYY-MM-DD}_{HHMMSS}/briefing.md`
```

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md
git commit -m "$(cat <<'EOF'
docs(claude-md): full speculative-ingest documentation (B4.6 of #131)

Expands the B1-era stub into the full synthetic-jobs convention section.
Adds candidate_led_briefing + speculative_roles_synth to the Pipeline
Context Table. Adds the new endpoints to the Web Is The Write Surface
section. Updates Output Folder Format with the SPECULATIVE folder pattern.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 33: User-facing docs walkthrough

**Files:**
- Modify: `docs/usage.md` — new section

- [ ] **Step 1: Add the walkthrough**

In `docs/usage.md`, add a new top-level section:

```markdown
## Submitting a speculative company

When you want to send a resume to a company that isn't currently posting a
matching role, use the speculative submission path.

1. Go to `/ingest/`. Below the real-posting form is a **Speculative submission** section.
2. Enter the company name (required) and an optional hint (e.g. "data center team", "ML platform org").
3. Click **Submit speculative.** The pipeline runs Perplexity Deep Research (1–5 min) followed by a role synthesis pass.
4. The status page polls until research completes, then auto-redirects to the review page.
5. Review the briefing (collapsed by default — expand if you want to read it). Below it, you'll see 1–5 synthesized role cards. Each card has a **Keep** checkbox (default checked); uncheck cards you don't want to pursue.
6. Click **Approve kept cards.** Each kept card becomes a `[SPEC]`-prefixed row on the dashboard, marked synthetic, ready for prep. Or click **Regenerate** to re-run synthesis with the same company; **Trash** if the briefing was off-base.
7. From the dashboard, flag a `[SPEC]` row for prep just like a real row. The cover letter and outreach draft will be written in cold-outreach mode automatically.
8. Send the outreach. Then click **Sent Outreach** on that row (replaces the **Applied** button for speculative rows). The transition counts toward the apply-gate the same way a normal application does.

Costs: ~$0.25–$0.75 per speculative submission depending on how deep the research goes.
The form will soft-warn you if you've already submitted today; there's no hard cap.
```

- [ ] **Step 2: Commit**

```bash
git add docs/usage.md
git commit -m "$(cat <<'EOF'
docs(usage): speculative submission walkthrough (B4.7 of #131)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 34: CHANGELOG entry for B4

**Files:**
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Add entries**

Append to the `[Unreleased]` block:

```markdown
- (#131) Speculative ingest end-to-end: Perplexity Deep Research briefing, Claude Sonnet role synthesis, web review/approve gate, speculative-aware cover-letter and outreach prompts, "Sent Outreach" button label on the dashboard for synthetic rows, watchdog branch for stuck `researching` requests. Closes #131.
```

- [ ] **Step 2: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs(changelog): B4 of #131 — speculative ingest closes the feature"
```

---

### Task 35: Whole-feature verification gate (per spec) + watchdog timing calibration

This is the spec's "Whole-feature verification gate" — distinct from per-task tests.

- [ ] **Step 1: Local CI pass**

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy src/findajob
uv run pytest -x
```

- [ ] **Step 2: Live submission against operator's stack (PSIQuantum + ai&)**

Per the spec's verification gate:

1. Submit "PSIQuantum" through `/ingest/speculative` with hint "advanced computing infrastructure"
2. Verify status page renders, polls, eventually redirects to review (record end-to-end time)
3. Verify briefing has Company Snapshot + Hiring Signals + Likely Role Surfaces sections
4. Verify 1–5 role cards render
5. Approve all kept cards
6. Verify dashboard shows `[SPEC]`-prefixed rows with the SPEC badge
7. Flag one for prep
8. After prep completes, verify the cover letter contains the speculative framing language ("I noticed... while I don't see a current opening...")
9. Click **Sent Outreach** on the prepped row
10. Verify `audit_log` shows `field_changed='stage', new_value='applied', changed_by='outreach_button'`
11. Verify the apply-gate query (`SELECT COUNT(*) FROM audit_log WHERE field_changed='stage' AND new_value='applied' AND changed_at >= today_PT`) includes this row
12. Reject a different speculative row with reason "Fit Mismatch"; verify `feedback_log` count for that fingerprint is still 0
13. Repeat for "ai&" with hint "AI startup operations role"
14. **Watchdog timing:** record the slowest end-to-end time of the two submissions. If it's >7 min (i.e., approaching the 10-min watchdog), raise `STUCK_RESEARCH_MINUTES` to 15 and re-run the test.

- [ ] **Step 3: Push + open PR**

```bash
git push -u origin feat/131-b4-prep-and-button
gh pr create --title "feat(speculative): speculative-aware prep + sent-outreach button + docs (B4 of #131)" --body "$(cat <<'EOF'
## Summary

- `cover_letter_writer` and `outreach_drafter` get `<<SPECULATIVE_MODE>>` marker variants, injected by `prep_application.py` when `jobs.synthetic=1`.
- `POST /board/jobs/{fp}/apply` handler reads `synthetic` and writes `changed_by='outreach_button'` accordingly. No new endpoint.
- Dashboard `_job_row.html` shows SPEC badge + flips button label to "Sent Outreach" when `synthetic=1`.
- Watchdog fails `speculative_requests` stuck `researching` >10 min.
- `CLAUDE.md` synthetic-jobs section expanded; Pipeline Context Table gets two new rows; `Web is the Write Surface` lists new endpoints.
- `docs/usage.md` gets a speculative-submission walkthrough.
- CHANGELOG updated; closes #131.

## Verification (per spec gate, pre-merge)

- [ ] Submitted PSIQuantum + ai& through the live form
- [ ] Both produced 1–5 valid role cards
- [ ] Sent Outreach button transitions to applied with changed_by='outreach_button'
- [ ] Speculative row reject does NOT write feedback_log
- [ ] Watchdog 10-min threshold confirmed adequate (slowest observed run: __min)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
gh pr checks --watch
gh pr merge --squash --delete-branch
git fetch origin && git checkout main && git pull
```

---

### Task 36: Close #131

- [ ] **Step 1: Verify the issue auto-closed**

```bash
gh issue view 131 --json state,projectItems
```

Expected: `state: "CLOSED"`, project Status: `Done`. The `Closes #131` line in B4's CHANGELOG and the `Closes #131` in the merged commit body should auto-close it; if not, close manually:

```bash
gh issue close 131 --comment "All four phases (B1–B4) merged. Verification gate passed against PSIQuantum + ai& live submissions. See PR #<B4 number>."
```

- [ ] **Step 2: Update spec doc Status field**

Edit `docs/superpowers/specs/2026-04-28-speculative-ingest-131-design.md` line 5:

```markdown
Status: Implemented (B1 PR #X, B2 PR #Y, B3 PR #Z, B4 PR #W)
```

```bash
git add docs/superpowers/specs/2026-04-28-speculative-ingest-131-design.md
git commit -m "docs(plans): mark #131 spec Implemented with PR refs"
git push origin main
```

---

## Self-Review Checklist

Spec → plan task mapping (cross-reference against the spec's own self-review):

| Spec section | Plan task(s) |
|---|---|
| Decision 1 (apply-gate via row attributes) | T29 (`/apply` handler synthetic branch) + T30 (template button-label flip) |
| Decision 2 (no dedup) | implicit — not implemented anywhere |
| Decision 3 (soft-warn rate limit) | T25 step 3 |
| Decision 4 (speculative_requests table) | T3 |
| Decision 5 (Deep Research) | T12 (model field in role front-matter) |
| Decision 6 (async submission) | T18 (script entry) + T21 (POST handler subprocess.Popen) + T22 (status page polling) |
| Decision 7 (aging defer) | not implemented (per decision) |
| Decision 8 (confidence-flag defer) | not implemented (per decision) |
| Decision 9 (CLI defer) | not implemented (per decision) |
| Decision 10 (no new auth) | not implemented (by absence) |
| Data model: speculative_requests | T3 |
| Data model: jobs.synthetic | T2 |
| `is_synthetic_job` helper | T4 |
| `handle_rejection` synthetic guard | T5 |
| `handle_not_selected` synthetic guard | not separately implemented in T5 — **GAP, see fix below** |
| Scorer feedback loader synthetic guard | T6 |
| candidate_led_briefing role | T12 |
| speculative_roles_synth role | T13 |
| Speculative runner | T16 |
| Briefing folder layout | T15 |
| Approver | T17 |
| Form mode toggle | T25 |
| Status page (HTMX poll) | T22 |
| Review page | T23 |
| Approve / Regenerate / Trash actions | T24 |
| Soft-warn rate limit | T25 step 3 |
| Cover-letter variant | T27 |
| Outreach variant | T28 |
| "Sent Outreach" button | T29 + T30 |
| Watchdog branch for stuck speculative requests | T31 |
| CLAUDE.md updates | T8 (B1 stub) + T32 (full) |
| CHANGELOG.md updates | T9 (B1) + T34 (B4) — note B2 and B3 also need entries — see fix below |
| `docs/usage.md` walkthrough | T33 |

**Gaps found:**

1. **`handle_not_selected` synthetic guard.** Spec calls for both `handle_rejection` AND `handle_not_selected` to skip `feedback_log` when synthetic=1. The current `handle_not_selected` already doesn't write to `feedback_log` (it's a no-op for that table) — so technically no code change is required. Note this in T5's commit message or add a clarifying assertion in the test.
2. **B2 + B3 CHANGELOG entries.** T9 adds B1; T34 adds B4. B2 and B3 each need a `[Unreleased]` entry too. Add these as bonus steps to T19 (B2 PR) and T26 (B3 PR) — one paragraph each, mirroring T9's shape.

Both gaps are cosmetic and corrected at execution time.

---

## Documentation Impact

Already enumerated in the spec's "Documentation Impact" section — see `docs/superpowers/specs/2026-04-28-speculative-ingest-131-design.md`. Concretely landed in tasks: T8 (B1 CLAUDE.md stub), T9 (B1 CHANGELOG), T32 (B4 CLAUDE.md full), T33 (B4 usage.md), T34 (B4 CHANGELOG).
