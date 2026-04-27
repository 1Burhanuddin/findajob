# Metric Layer C.0 — Implementation Plan

## Issue(s)
- #229 — Metric Layer C.0: schema + cost instrumentation + config-drift detector

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the schema, instrumentation, and config-change detection prerequisites that make the Metric Layer view layer (C.1) possible — no user-visible UI shipped in this phase.

**Architecture:** Three additive DB tables (`config_changes`, `recall_audit`) and two columns (`jobs.company_tier`, `jobs.scored_by`), a pure-function drift detector hooked into three write surfaces (triage pre-call, `/config/` POST, onboarding injector), and cost-tracking instrumentation on the four LLM operations not yet logged (prep materials, outreach, briefing, company research).

**Tech Stack:** Python 3.12, sqlite3, pytest, FastAPI (existing), aichat-ng via subprocess (existing). No new dependencies.

**Reference:** Design spec at `docs/superpowers/specs/2026-04-24-metric-layer-design.md` §6, §7.4, §8 (C.0 row). Issue #229.

---

## Pre-task: Branch + CHANGELOG entry

- [ ] **Step 1: Create feature branch off origin/main**

Local `main` drifts from origin via squash-merge; always branch off origin.

```bash
git fetch origin
git checkout -b feat/229-metric-layer-c0 origin/main
```

Expected: new branch, clean working tree.

- [ ] **Step 2: Seed `[Unreleased]` CHANGELOG entry with `### Migration required` marker**

Modify: `CHANGELOG.md` — add under `[Unreleased]` at the top:

```markdown
## [Unreleased]

### Added

- **Metric Layer C.0 schema** (#229): new `config_changes` and `recall_audit` tables; new `jobs.company_tier` and `jobs.scored_by` columns; cost-tracking instrumentation on prep materials, outreach, briefing, and company research LLM calls; config-drift detector runs at triage start, `/config/` POST, and onboarding injection.

### Migration required

- Schema: run `scripts/init_db.py` on upgrade. Backfill existing rows with `uv run python scripts/backfill_company_tier.py` and `uv run python scripts/backfill_scored_by.py`. Both scripts are idempotent.
```

- [ ] **Step 3: Commit CHANGELOG seed**

```bash
git add CHANGELOG.md
git commit -m "docs(changelog): seed C.0 Unreleased entry with migration marker

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 1: `config_changes` and `recall_audit` tables + schema migrations in init_db.py

**Files:**
- Modify: `scripts/init_db.py` (after the existing `loose_fingerprint` ALTER block, before the `executescript`)
- Test: `tests/test_init_db_schema.py` (new test functions added to existing file)

- [ ] **Step 1: Write the failing test**

Modify: `tests/test_init_db_schema.py` — append:

```python
def test_init_db_creates_config_changes_table(tmp_path, monkeypatch):
    monkeypatch.setenv("JSP_BASE", str(tmp_path))
    (tmp_path / "data").mkdir()
    import importlib
    import scripts.init_db
    importlib.reload(scripts.init_db)

    conn = sqlite3.connect(tmp_path / "data" / "pipeline.db")
    cols = {r[1] for r in conn.execute("PRAGMA table_info(config_changes)").fetchall()}
    assert cols >= {"id", "lever", "changed_at", "changed_by", "change_summary", "content_hash", "diff_summary"}
    conn.close()


def test_init_db_creates_recall_audit_table(tmp_path, monkeypatch):
    monkeypatch.setenv("JSP_BASE", str(tmp_path))
    (tmp_path / "data").mkdir()
    import importlib
    import scripts.init_db
    importlib.reload(scripts.init_db)

    conn = sqlite3.connect(tmp_path / "data" / "pipeline.db")
    cols = {r[1] for r in conn.execute("PRAGMA table_info(recall_audit)").fetchall()}
    assert cols >= {"id", "job_id", "audited_at", "original_score", "original_scored_by", "auditor_model", "audited_score", "upgraded", "audit_notes"}
    conn.close()


def test_init_db_adds_company_tier_and_scored_by_columns(tmp_path, monkeypatch):
    monkeypatch.setenv("JSP_BASE", str(tmp_path))
    (tmp_path / "data").mkdir()
    import importlib
    import scripts.init_db
    importlib.reload(scripts.init_db)

    conn = sqlite3.connect(tmp_path / "data" / "pipeline.db")
    cols = {r[1] for r in conn.execute("PRAGMA table_info(jobs)").fetchall()}
    assert "company_tier" in cols
    assert "scored_by" in cols
    conn.close()


def test_init_db_is_idempotent_on_rerun(tmp_path, monkeypatch):
    """Running init_db twice must not raise on duplicate columns/tables."""
    monkeypatch.setenv("JSP_BASE", str(tmp_path))
    (tmp_path / "data").mkdir()
    import importlib
    import scripts.init_db
    importlib.reload(scripts.init_db)  # first run
    importlib.reload(scripts.init_db)  # second run — must not crash
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_init_db_schema.py -v
```

Expected: the four new tests fail — tables/columns don't exist.

- [ ] **Step 3: Implement — extend the ALTER TABLE block and executescript in init_db.py**

Modify: `scripts/init_db.py` — replace the existing block starting at line 16 through the end of the `executescript` call with:

```python
_existing_tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
if "jobs" in _existing_tables:
    _jobs_cols = {row[1] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()}
    if "loose_fingerprint" not in _jobs_cols:
        conn.execute("ALTER TABLE jobs ADD COLUMN loose_fingerprint TEXT")
        conn.commit()
    if "company_tier" not in _jobs_cols:
        conn.execute("ALTER TABLE jobs ADD COLUMN company_tier TEXT DEFAULT 'unknown'")
        conn.commit()
    if "scored_by" not in _jobs_cols:
        conn.execute("ALTER TABLE jobs ADD COLUMN scored_by TEXT DEFAULT ''")
        conn.commit()
```

Then append these two `CREATE TABLE` blocks to the `executescript` string (before the closing `""")`):

```sql
CREATE TABLE IF NOT EXISTS config_changes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lever TEXT NOT NULL,
    changed_at TEXT DEFAULT (datetime('now')),
    changed_by TEXT DEFAULT 'manual',
    change_summary TEXT,
    content_hash TEXT,
    diff_summary TEXT
);

CREATE INDEX IF NOT EXISTS idx_config_changes_lever_time ON config_changes(lever, changed_at);

CREATE TABLE IF NOT EXISTS recall_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL,
    audited_at TEXT DEFAULT (datetime('now')),
    original_score INTEGER,
    original_scored_by TEXT,
    auditor_model TEXT NOT NULL,
    audited_score INTEGER,
    upgraded INTEGER DEFAULT 0,
    audit_notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_recall_audit_time ON recall_audit(audited_at);
```

Also add a `jobs` column index that C.1 will want:

```sql
CREATE INDEX IF NOT EXISTS idx_jobs_company_tier ON jobs(company_tier);
CREATE INDEX IF NOT EXISTS idx_jobs_scored_by ON jobs(scored_by);
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/test_init_db_schema.py -v
```

Expected: all four tests pass.

- [ ] **Step 5: Run full test suite for regressions**

```bash
uv run pytest -q
```

Expected: no failures introduced.

- [ ] **Step 6: Commit**

```bash
git add scripts/init_db.py tests/test_init_db_schema.py
git commit -m "feat(#229): add config_changes, recall_audit tables + jobs columns

Idempotent ALTER TABLE pattern mirrors loose_fingerprint precedent.
Schema only — population and backfill in later tasks.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Prefilter returns `scored_by` alongside score result

**Files:**
- Modify: `src/findajob/scorer_prefilter.py:49-91` (extend return dict)
- Test: `tests/test_scorer_prefilter.py` (existing file, new assertions)

- [ ] **Step 1: Write the failing test**

Modify: `tests/test_scorer_prefilter.py` — append:

```python
def test_prefilter_stage1_returns_scored_by_prefilter_stage1():
    result, _ = prefilter_score("Software Engineer at Acme", "Acme", jd_usable=True)
    assert result is not None
    assert result["scored_by"] == "prefilter_stage1"


def test_prefilter_stage2_returns_scored_by_prefilter_stage2():
    result, _ = prefilter_score("Data Center Technician", "Acme", jd_usable=False)
    assert result is not None
    assert result["scored_by"] == "prefilter_stage2"


def test_prefilter_none_when_llm_needed_returns_no_scored_by():
    """When prefilter defers to LLM, there's no result dict — caller sets scored_by='llm'."""
    result, _ = prefilter_score("Operations Manager at Acme Corp", "Acme", jd_usable=True)
    assert result is None
```

Note: the first test relies on "Software Engineer" being in hard-reject rules. If your test fixtures use different terms, swap to a term known to hit hard reject. The second relies on "Data Center Technician" being in in-domain patterns.

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_scorer_prefilter.py -v -k scored_by
```

Expected: the two new tests fail — `KeyError: 'scored_by'`.

- [ ] **Step 3: Add `scored_by` to both prefilter return dicts**

Modify: `src/findajob/scorer_prefilter.py` — within `prefilter_score`:

Stage 1 return dict (line 64-74): add `"scored_by": "prefilter_stage1",` before the closing `}`.

Stage 2 return dict (line 79-89): add `"scored_by": "prefilter_stage2",` before the closing `}`.

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/test_scorer_prefilter.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/findajob/scorer_prefilter.py tests/test_scorer_prefilter.py
git commit -m "feat(#229): prefilter returns scored_by stage tag

Stage 1 hard rejects return scored_by='prefilter_stage1';
Stage 2 in-domain/no-JD defaults return 'prefilter_stage2'.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: LLM scoring path sets `scored_by='llm'`

**Files:**
- Modify: `src/findajob/scoring.py` — `score_job` return paths
- Test: `tests/test_scoring.py` (existing or new)

- [ ] **Step 1: Write the failing test**

Create or modify: `tests/test_scoring.py` — append (or write a new `test_scoring_scored_by.py` if no `test_scoring.py` exists):

```python
from unittest.mock import patch, MagicMock

from findajob.scoring import score_job


def test_score_job_sets_scored_by_llm_on_successful_scoring(monkeypatch):
    """When prefilter defers, the LLM path returns scored_by='llm'."""
    fake_result = MagicMock()
    fake_result.returncode = 0
    fake_result.stdout = (
        '{"score_status": "scored", "relevance_score": 7, "interview_likelihood": 6, '
        '"strengths_alignment": "x", "industry_sector": "tech", "comp_estimate": "", '
        '"ai_notes": "", "score_flag_reason": null, "remote_status": "Remote"}'
    )
    fake_result.stderr = ""
    monkeypatch.setattr("findajob.scoring.subprocess.run", lambda *a, **k: fake_result)

    # Use a title/company that will NOT hit prefilter (non-reject, ambiguous with JD)
    result, _ = score_job(
        title="Operations Program Manager",
        company="Some Company",
        jd_text="A long, usable JD about running operations programs " * 20,
        candidate_profile="CANDIDATE PROFILE: example",
    )
    assert result["scored_by"] == "llm"


def test_score_job_preserves_prefilter_scored_by(monkeypatch):
    """When prefilter returns, its scored_by tag is preserved downstream."""
    result, _ = score_job(
        title="Software Engineer",  # assumed in hard-reject list
        company="Acme",
        jd_text="",
        candidate_profile="CANDIDATE PROFILE: example",
    )
    assert result["scored_by"] == "prefilter_stage1"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_scoring.py -v -k scored_by
```

Expected: tests fail — `scored_by` key not in result dict from LLM path.

- [ ] **Step 3: Implement — add scored_by='llm' to every LLM-branch return**

Modify: `src/findajob/scoring.py` — for each LLM-branch return dict (the timeout branch ~L161, the rc-nonzero branch ~L183, the validation-failed-but-title-hard-reject branch ~L201, the validation-failed-pure branch ~L213, and the final success path at the end):

- Timeout: add `"scored_by": "llm"` to dict
- Nonzero rc: add `"scored_by": "llm"` to dict
- Validation+hard-reject fallback: add `"scored_by": "prefilter_stage1"` (this branch falls back to prefilter behavior)
- Validation failed: add `"scored_by": "llm"`
- Success path (final parsed return): add `"scored_by": "llm"` to the parsed dict before returning — i.e., at line ~224 insert `parsed["scored_by"] = "llm"` before the `return parsed, latency_ms`.

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/test_scoring.py -v
```

Expected: tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/findajob/scoring.py tests/test_scoring.py
git commit -m "feat(#229): LLM scoring path tags scored_by='llm'

Preserves prefilter's 'prefilter_stage1'/'prefilter_stage2' tags
when returned; adds 'llm' for all LLM-branch outcomes including
timeout, rc-nonzero, and validation failures.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Triage persists `scored_by` to DB

**Files:**
- Modify: `scripts/triage.py:514-538` (the UPDATE jobs block)
- Test: `tests/test_triage_score_persist.py` (new file)

- [ ] **Step 1: Write the failing test**

Create: `tests/test_triage_score_persist.py`:

```python
"""Verify triage writes scored_by into the jobs row after scoring."""
import sqlite3

import pytest


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    db = tmp_path / "pipeline.db"
    monkeypatch.setenv("JSP_BASE", str(tmp_path))
    (tmp_path / "data").mkdir()
    import importlib
    import scripts.init_db
    importlib.reload(scripts.init_db)
    return sqlite3.connect(tmp_path / "data" / "pipeline.db")


def test_triage_update_includes_scored_by_column(fresh_db):
    """The UPDATE statement written by triage must include scored_by."""
    # Read the source of triage.py and verify the UPDATE string contains scored_by
    from pathlib import Path
    src = Path(__file__).resolve().parents[1] / "scripts" / "triage.py"
    text = src.read_text()
    # Anchor on the scoring UPDATE (not the other UPDATEs)
    idx = text.find("UPDATE jobs SET\n                        relevance_score=")
    assert idx > 0, "could not find scoring UPDATE block"
    block = text[idx:idx + 1200]
    assert "scored_by=?" in block, "scored_by column not in scoring UPDATE"
    assert "company_tier=?" in block, "company_tier column not in scoring UPDATE"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_triage_score_persist.py -v
```

Expected: fail — `scored_by=?` not yet in the UPDATE.

- [ ] **Step 3: Implement — extend triage UPDATE to write scored_by + company_tier**

Modify: `scripts/triage.py` — replace the UPDATE block at lines 514-538 with:

```python
                conn.execute(
                    """
                    UPDATE jobs SET
                        relevance_score=?, interview_likelihood=?, strengths_alignment=?,
                        industry_sector=?, comp_estimate=?, ai_notes=?,
                        score_status=?, score_flag_reason=?, remote_status=?,
                        scored_by=?, company_tier=?,
                        stage=?, stage_updated=?, status=?, updated_at=?
                    WHERE id=?
                """,
                    (
                        scored.get("relevance_score"),
                        scored.get("interview_likelihood"),
                        scored.get("strengths_alignment"),
                        scored.get("industry_sector", ""),
                        scored.get("comp_estimate", ""),
                        scored.get("ai_notes", ""),
                        scored.get("score_status", "manual_review"),
                        scored.get("score_flag_reason", ""),
                        scored.get("remote_status", "Unknown"),
                        scored.get("scored_by", ""),
                        scored.get("company_tier", "unknown"),
                        stage,
                        now,
                        status,
                        now,
                        job_id,
                    ),
                )
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/test_triage_score_persist.py -v
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add scripts/triage.py tests/test_triage_score_persist.py
git commit -m "feat(#229): triage persists scored_by + company_tier to jobs

Populate both new columns at score-write time. company_tier is
set by the tier resolver (Task 5); scored_by comes from scoring.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Tier resolver + score-time company_tier population

**Files:**
- Create: `src/findajob/tiers.py`
- Modify: `src/findajob/scoring.py` — inject tier into scored dict
- Modify: `src/findajob/scorer_prefilter.py` — same
- Test: `tests/test_tiers.py` (new)

- [ ] **Step 1: Write the failing test**

Create: `tests/test_tiers.py`:

```python
"""Tests for tier resolution against companies_of_interest.txt."""
from pathlib import Path

import pytest

from findajob.tiers import resolve_tier, load_tier1_companies


def test_resolve_tier_returns_tier1_for_exact_match(tmp_path, monkeypatch):
    coi = tmp_path / "config" / "companies_of_interest.txt"
    coi.parent.mkdir()
    coi.write_text("Acme Corporation\nGlobex\n")
    monkeypatch.setattr("findajob.tiers._coi_path", lambda: coi)
    load_tier1_companies.cache_clear()
    assert resolve_tier("Acme Corporation") == "tier1"
    assert resolve_tier("Globex") == "tier1"


def test_resolve_tier_case_insensitive(tmp_path, monkeypatch):
    coi = tmp_path / "config" / "companies_of_interest.txt"
    coi.parent.mkdir()
    coi.write_text("Acme Corporation\n")
    monkeypatch.setattr("findajob.tiers._coi_path", lambda: coi)
    load_tier1_companies.cache_clear()
    assert resolve_tier("ACME CORPORATION") == "tier1"
    assert resolve_tier("acme corporation") == "tier1"


def test_resolve_tier_returns_other_for_no_match(tmp_path, monkeypatch):
    coi = tmp_path / "config" / "companies_of_interest.txt"
    coi.parent.mkdir()
    coi.write_text("Acme Corporation\n")
    monkeypatch.setattr("findajob.tiers._coi_path", lambda: coi)
    load_tier1_companies.cache_clear()
    assert resolve_tier("Globex") == "other"


def test_resolve_tier_returns_unknown_if_file_missing(tmp_path, monkeypatch):
    missing = tmp_path / "does" / "not" / "exist.txt"
    monkeypatch.setattr("findajob.tiers._coi_path", lambda: missing)
    load_tier1_companies.cache_clear()
    assert resolve_tier("Acme") == "unknown"


def test_resolve_tier_empty_company_returns_unknown():
    assert resolve_tier("") == "unknown"
    assert resolve_tier(None) == "unknown"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_tiers.py -v
```

Expected: ImportError — `findajob.tiers` does not exist.

- [ ] **Step 3: Create the tiers module**

Create: `src/findajob/tiers.py`:

```python
"""Tier resolver for company_tier column population.

Reads the per-instance ``config/companies_of_interest.txt`` (one company per
line, case-insensitive) and maps a company name to one of:

* ``'tier1'`` — name matches a line in the file
* ``'other'`` — file exists but no match
* ``'unknown'`` — file missing, empty company name, or read error

The file is cached at module load via ``functools.lru_cache``; call
``load_tier1_companies.cache_clear()`` from tests or after the file is
rewritten in the same process.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from findajob.paths import BASE


def _coi_path() -> Path:
    return Path(BASE) / "config" / "companies_of_interest.txt"


@lru_cache(maxsize=1)
def load_tier1_companies() -> frozenset[str]:
    """Return a frozenset of lowercased Tier 1 company names.

    Returns an empty frozenset if the file is missing (so ``resolve_tier``
    can distinguish "no match" from "file missing").
    """
    try:
        text = _coi_path().read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        return frozenset()
    names = {line.strip().lower() for line in text.splitlines() if line.strip()}
    return frozenset(names)


def resolve_tier(company: str | None) -> str:
    """Return 'tier1', 'other', or 'unknown' for a company name."""
    if not company:
        return "unknown"
    if not _coi_path().is_file():
        return "unknown"
    names = load_tier1_companies()
    return "tier1" if company.strip().lower() in names else "other"
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/test_tiers.py -v
```

Expected: all five tests pass.

- [ ] **Step 5: Inject tier into scored dict — prefilter paths**

Modify: `src/findajob/scorer_prefilter.py` — add `company` to both Stage 1 and Stage 2 return dicts' `company_tier` field:

At the top:

```python
from findajob.tiers import resolve_tier
```

In Stage 1 return dict, add:
```python
"company_tier": resolve_tier(company),
```

In Stage 2 return dict, add:
```python
"company_tier": resolve_tier(company),
```

- [ ] **Step 6: Inject tier into scored dict — LLM paths**

Modify: `src/findajob/scoring.py`:

At the top:

```python
from findajob.tiers import resolve_tier
```

In every LLM-branch return (timeout, rc-nonzero, validation failed, and the final success path before return), add:

```python
"company_tier": resolve_tier(company),
```

For the final success branch at line ~224, add before the return:

```python
parsed["company_tier"] = resolve_tier(company)
```

- [ ] **Step 7: Run the full relevant test suite**

```bash
uv run pytest tests/test_tiers.py tests/test_scorer_prefilter.py tests/test_scoring.py tests/test_triage_score_persist.py -v
```

Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add src/findajob/tiers.py src/findajob/scorer_prefilter.py src/findajob/scoring.py tests/test_tiers.py
git commit -m "feat(#229): resolve company_tier at score time

Reads config/companies_of_interest.txt (derived from
target_companies.md §Tier 1 by #148 onboarding injector).
Returns 'tier1'/'other'/'unknown'; injected into every scorer
output so the triage UPDATE can persist it.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Backfill scripts for existing rows

**Files:**
- Create: `scripts/backfill_company_tier.py`
- Create: `scripts/backfill_scored_by.py`
- Test: `tests/test_backfill_c0.py` (new)

- [ ] **Step 1: Write the failing test**

Create: `tests/test_backfill_c0.py`:

```python
"""Tests for the C.0 backfill scripts."""
import sqlite3
import subprocess
import sys

import pytest


@pytest.fixture
def seeded_db(tmp_path, monkeypatch):
    monkeypatch.setenv("JSP_BASE", str(tmp_path))
    (tmp_path / "data").mkdir()
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "companies_of_interest.txt").write_text("Acme Corp\nGlobex\n")

    import importlib
    import scripts.init_db
    importlib.reload(scripts.init_db)

    db_path = tmp_path / "data" / "pipeline.db"
    conn = sqlite3.connect(db_path)
    # Seed: three jobs with different (company, ai_notes) patterns
    conn.executemany(
        """
        INSERT INTO jobs (id, fingerprint, url, title, company, source, ai_notes, score_flag_reason, relevance_score)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            ("j1", "fp1", "u", "Engineer", "Acme Corp", "linkedin", "Normal LLM ai_notes", None, 7),
            ("j2", "fp2", "u", "SWE", "Globex", "linkedin", "Hard reject — title is outside candidate domain.", "Pre-filter hard reject: title matched \"SWE\"", 1),
            ("j3", "fp3", "u", "DC Technician", "Unknown Co", "indeed", "Title is directionally in-domain. JD unavailable — scored 5 per policy.", None, 5),
        ],
    )
    conn.commit()
    return tmp_path, conn


def test_backfill_company_tier_populates_tier1_and_other(seeded_db):
    tmp_path, conn = seeded_db
    subprocess.run([sys.executable, "scripts/backfill_company_tier.py"], check=True, env={"JSP_BASE": str(tmp_path), **__import__("os").environ})

    rows = {r[0]: r[1] for r in conn.execute("SELECT id, company_tier FROM jobs").fetchall()}
    assert rows["j1"] == "tier1"
    assert rows["j2"] == "tier1"
    assert rows["j3"] == "other"


def test_backfill_scored_by_heuristic_classification(seeded_db):
    tmp_path, conn = seeded_db
    subprocess.run([sys.executable, "scripts/backfill_scored_by.py"], check=True, env={"JSP_BASE": str(tmp_path), **__import__("os").environ})

    rows = {r[0]: r[1] for r in conn.execute("SELECT id, scored_by FROM jobs").fetchall()}
    assert rows["j1"] == "llm"
    assert rows["j2"] == "prefilter_stage1"
    assert rows["j3"] == "prefilter_stage2"


def test_backfill_idempotent(seeded_db):
    """Running twice produces the same result and does not raise."""
    tmp_path, conn = seeded_db
    env = {"JSP_BASE": str(tmp_path), **__import__("os").environ}
    subprocess.run([sys.executable, "scripts/backfill_company_tier.py"], check=True, env=env)
    subprocess.run([sys.executable, "scripts/backfill_company_tier.py"], check=True, env=env)
    count = conn.execute("SELECT COUNT(*) FROM jobs WHERE company_tier='tier1'").fetchone()[0]
    assert count == 2
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_backfill_c0.py -v
```

Expected: FileNotFoundError or non-zero exit — scripts don't exist.

- [ ] **Step 3: Implement `backfill_company_tier.py`**

Create: `scripts/backfill_company_tier.py`:

```python
#!/usr/bin/env python3
"""Backfill jobs.company_tier for existing rows.

Idempotent: safe to rerun. Reads companies_of_interest.txt via
findajob.tiers.resolve_tier so classification matches live scoring.
"""

from __future__ import annotations

import sqlite3

from findajob.paths import BASE
from findajob.tiers import load_tier1_companies, resolve_tier


def main() -> None:
    db_path = f"{BASE}/data/pipeline.db"
    conn = sqlite3.connect(db_path, timeout=30)
    load_tier1_companies.cache_clear()  # ensure fresh read

    rows = conn.execute("SELECT id, company FROM jobs").fetchall()
    updated = 0
    for job_id, company in rows:
        tier = resolve_tier(company)
        conn.execute("UPDATE jobs SET company_tier=? WHERE id=?", (tier, job_id))
        updated += 1
    conn.commit()
    conn.close()
    print(f"Backfilled company_tier on {updated} rows.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Implement `backfill_scored_by.py`**

Create: `scripts/backfill_scored_by.py`:

```python
#!/usr/bin/env python3
"""Backfill jobs.scored_by for existing rows.

Heuristic, not exact — uses score_flag_reason and ai_notes text to
classify pre-existing rows. Ambiguous rows default to 'llm' (the
safer over-count, since the scorer runs on every non-prefiltered job).

Idempotent: safe to rerun.
"""

from __future__ import annotations

import sqlite3

from findajob.paths import BASE


def classify(score_flag_reason: str | None, ai_notes: str | None) -> str:
    """Return one of 'prefilter_stage1' | 'prefilter_stage2' | 'llm'."""
    sfr = (score_flag_reason or "").lower()
    notes = (ai_notes or "").lower()
    if "pre-filter hard reject" in sfr or "pre-filter hard reject" in notes:
        return "prefilter_stage1"
    if "pre-filter in-domain/no-jd" in sfr or "pre-filter in-domain/no-jd" in notes:
        return "prefilter_stage2"
    return "llm"


def main() -> None:
    db_path = f"{BASE}/data/pipeline.db"
    conn = sqlite3.connect(db_path, timeout=30)

    rows = conn.execute("SELECT id, score_flag_reason, ai_notes FROM jobs").fetchall()
    updated = 0
    for job_id, sfr, notes in rows:
        scored_by = classify(sfr, notes)
        conn.execute("UPDATE jobs SET scored_by=? WHERE id=?", (scored_by, job_id))
        updated += 1
    conn.commit()
    conn.close()
    print(f"Backfilled scored_by on {updated} rows.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run the backfill tests**

```bash
uv run pytest tests/test_backfill_c0.py -v
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add scripts/backfill_company_tier.py scripts/backfill_scored_by.py tests/test_backfill_c0.py
git commit -m "feat(#229): backfill scripts for company_tier + scored_by

Idempotent one-shot scripts. company_tier uses live resolver;
scored_by uses heuristic on existing ai_notes / score_flag_reason.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: Config-drift detector core (hashing + write path)

**Files:**
- Create: `src/findajob/metrics/__init__.py` (empty)
- Create: `src/findajob/metrics/config_changes.py`
- Test: `tests/test_config_changes_detector.py` (new)

- [ ] **Step 1: Write the failing test**

Create: `tests/test_config_changes_detector.py`:

```python
"""Tests for the config-drift detector."""
import sqlite3

import pytest


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("JSP_BASE", str(tmp_path))
    (tmp_path / "data").mkdir()
    (tmp_path / "config").mkdir()
    (tmp_path / "candidate_context").mkdir()

    import importlib
    import scripts.init_db
    importlib.reload(scripts.init_db)
    return sqlite3.connect(tmp_path / "data" / "pipeline.db")


def test_first_call_records_every_existing_lever(fresh_db, tmp_path):
    from findajob.metrics.config_changes import detect_and_record

    (tmp_path / "candidate_context" / "profile.md").write_text("PROFILE V1")
    (tmp_path / "config" / "jsearch_queries.txt").write_text("query one\n")

    detect_and_record(fresh_db, changed_by="test")
    rows = fresh_db.execute("SELECT lever, changed_by FROM config_changes").fetchall()
    levers = {r[0] for r in rows}
    assert "profile" in levers
    assert "queries" in levers
    assert all(r[1] == "test" for r in rows)


def test_unchanged_content_does_not_insert_new_row(fresh_db, tmp_path):
    from findajob.metrics.config_changes import detect_and_record

    (tmp_path / "candidate_context" / "profile.md").write_text("PROFILE V1")

    detect_and_record(fresh_db, changed_by="test")
    detect_and_record(fresh_db, changed_by="test")

    n = fresh_db.execute("SELECT COUNT(*) FROM config_changes WHERE lever='profile'").fetchone()[0]
    assert n == 1


def test_changed_content_inserts_new_row(fresh_db, tmp_path):
    from findajob.metrics.config_changes import detect_and_record

    profile = tmp_path / "candidate_context" / "profile.md"
    profile.write_text("PROFILE V1")
    detect_and_record(fresh_db, changed_by="test")

    profile.write_text("PROFILE V2")
    detect_and_record(fresh_db, changed_by="test")

    rows = fresh_db.execute("SELECT content_hash FROM config_changes WHERE lever='profile' ORDER BY changed_at").fetchall()
    assert len(rows) == 2
    assert rows[0][0] != rows[1][0]


def test_missing_file_is_skipped_silently(fresh_db, tmp_path):
    from findajob.metrics.config_changes import detect_and_record

    (tmp_path / "candidate_context" / "profile.md").write_text("x")
    # no queries file

    detect_and_record(fresh_db, changed_by="test")
    levers = {r[0] for r in fresh_db.execute("SELECT lever FROM config_changes").fetchall()}
    assert "profile" in levers
    assert "queries" not in levers  # skipped, no error


def test_changed_by_propagates(fresh_db, tmp_path):
    from findajob.metrics.config_changes import detect_and_record

    (tmp_path / "candidate_context" / "profile.md").write_text("x")

    detect_and_record(fresh_db, changed_by="onboarding")
    row = fresh_db.execute("SELECT changed_by FROM config_changes WHERE lever='profile'").fetchone()
    assert row[0] == "onboarding"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_config_changes_detector.py -v
```

Expected: ImportError — module does not exist.

- [ ] **Step 3: Create the metrics package**

Create: `src/findajob/metrics/__init__.py` — empty file (marks package).

- [ ] **Step 4: Implement the detector**

Create: `src/findajob/metrics/config_changes.py`:

```python
"""Config-change detector for the tuning loop's hybrid windowing.

Hashes each tracked lever's content and writes a row to
``config_changes`` whenever the hash differs from the most recent
row for that lever (or no prior row exists).

Called from three surfaces (see spec §6.1):

* ``scripts/triage.py`` — pre-triage, ``changed_by='manual'`` by default
* ``src/findajob/web/routes/config.py`` — after a successful POST,
  ``changed_by='manual'``
* ``src/findajob/onboarding/injector.py`` — after paste-back,
  ``changed_by='onboarding'``
"""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

from findajob.paths import BASE

# Lever → relative path from BASE. A missing file means the lever is
# skipped silently (no error). Keep this list in sync with spec §6.1.
_LEVERS: dict[str, str] = {
    "profile": "candidate_context/profile.md",
    "master_resume": "candidate_context/master_resume.md",
    "scorer_prompt": "config/roles/job_scorer.md",
    "resume_tailor_prompt": "config/roles/resume_tailor.md",
    "cover_letter_prompt": "config/roles/cover_letter_writer.md",
    "briefing_writer_prompt": "config/roles/briefing_writer.md",
    "outreach_drafter_prompt": "config/roles/outreach_drafter.md",
    "company_researcher_prompt": "config/roles/company_researcher.md",
    "queries": "config/jsearch_queries.txt",
    "excluded_employers": "config/excluded_employers.yaml",
    "feed_urls": "config/feed_urls.txt",
    "prefilter_rules": "config/prefilter_rules.yaml",
    "in_domain_patterns": "config/in_domain_patterns.yaml",
    "target_companies": "config/target_companies.md",
}


def _hash_file(path: Path) -> str | None:
    """Return sha256 hex of file content, or None if unreadable."""
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except (FileNotFoundError, OSError):
        return None


def _latest_hash_for(conn: sqlite3.Connection, lever: str) -> str | None:
    row = conn.execute(
        "SELECT content_hash FROM config_changes WHERE lever=? ORDER BY id DESC LIMIT 1",
        (lever,),
    ).fetchone()
    return row[0] if row else None


def detect_and_record(
    conn: sqlite3.Connection,
    *,
    changed_by: str = "manual",
    change_summary: str | None = None,
) -> list[str]:
    """Scan every tracked lever and insert rows for any whose hash changed.

    Returns the list of lever names that were recorded (empty if nothing
    changed). Commits after each insert so partial failures don't lose
    state. Missing files are skipped silently.
    """
    recorded: list[str] = []
    base = Path(BASE)
    for lever, relpath in _LEVERS.items():
        full = base / relpath
        current = _hash_file(full)
        if current is None:
            continue  # file missing or unreadable; skip
        previous = _latest_hash_for(conn, lever)
        if current == previous:
            continue
        conn.execute(
            """
            INSERT INTO config_changes (lever, changed_by, change_summary, content_hash)
            VALUES (?, ?, ?, ?)
            """,
            (lever, changed_by, change_summary, current),
        )
        conn.commit()
        recorded.append(lever)
    return recorded
```

- [ ] **Step 5: Run the detector tests**

```bash
uv run pytest tests/test_config_changes_detector.py -v
```

Expected: all five pass.

- [ ] **Step 6: Commit**

```bash
git add src/findajob/metrics/__init__.py src/findajob/metrics/config_changes.py tests/test_config_changes_detector.py
git commit -m "feat(#229): config-drift detector for hybrid windowing

14 levers tracked; sha256-hash-based dedup against most recent
row per lever. Missing files skipped silently. Three integration
points wired in follow-up tasks.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: Wire detector into triage (pre-triage hook)

**Files:**
- Modify: `scripts/triage.py` — call `detect_and_record` before the scoring loop
- Test: `tests/test_triage_config_drift.py` (new)

- [ ] **Step 1: Write the failing test**

Create: `tests/test_triage_config_drift.py`:

```python
"""Verify triage calls the config-drift detector at pipeline start."""
from pathlib import Path


def test_triage_imports_detect_and_record():
    src = Path(__file__).resolve().parents[1] / "scripts" / "triage.py"
    text = src.read_text()
    assert "from findajob.metrics.config_changes import detect_and_record" in text, \
        "triage must import detect_and_record"


def test_triage_calls_detect_and_record_before_scoring():
    src = Path(__file__).resolve().parents[1] / "scripts" / "triage.py"
    text = src.read_text()
    call_idx = text.find("detect_and_record(")
    score_idx = text.find('log_event("scoring_complete"')
    assert call_idx > 0, "triage must call detect_and_record"
    assert call_idx < score_idx, "detect_and_record must be called before scoring"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_triage_config_drift.py -v
```

Expected: fail — import and call absent.

- [ ] **Step 3: Add the import and call in triage**

Modify: `scripts/triage.py`:

Near the top with other findajob imports, add:

```python
from findajob.metrics.config_changes import detect_and_record
```

Inside the main triage function, BEFORE the scoring block (i.e., before the `if to_score:` block around line 480, but after the DB connection is open and jobs have been ingested), add:

```python
        detect_and_record(conn, changed_by="manual", change_summary="pre-triage drift scan")
```

(Find a suitable spot after ingest and before scoring — the existing pattern suggests near the start of the main flow after DB open.)

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/test_triage_config_drift.py -v
```

Expected: both assertions pass.

- [ ] **Step 5: Commit**

```bash
git add scripts/triage.py tests/test_triage_config_drift.py
git commit -m "feat(#229): triage runs config-drift detector pre-scoring

Attributes every subsequent scoring cycle to the most recent
config state via config_changes rows.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 9: Wire detector into `/config/` POST handler

**Files:**
- Modify: `src/findajob/web/routes/config.py` — call detector after successful write
- Test: `tests/test_config_files_drift.py` (new)

- [ ] **Step 1: Write the failing test**

Create: `tests/test_config_files_drift.py`:

```python
"""Verify /config/files/ POST triggers config-drift detection."""
import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient


def test_config_post_inserts_config_changes_row(tmp_path, monkeypatch):
    monkeypatch.setenv("JSP_BASE", str(tmp_path))
    (tmp_path / "data").mkdir()
    (tmp_path / "candidate_context").mkdir()

    import importlib
    import scripts.init_db
    importlib.reload(scripts.init_db)

    from findajob.web.app import create_app
    app = create_app()
    client = TestClient(app)

    resp = client.post(
        "/config/files/candidate_context/profile.md",
        data={"content": "new profile content"},
    )
    assert resp.status_code == 200

    conn = sqlite3.connect(tmp_path / "data" / "pipeline.db")
    rows = conn.execute("SELECT lever, changed_by FROM config_changes WHERE lever='profile'").fetchall()
    assert len(rows) == 1
    assert rows[0][1] == "manual"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_config_files_drift.py -v
```

Expected: fail — no `config_changes` row inserted.

- [ ] **Step 3: Call the detector from the POST handler**

Modify: `src/findajob/web/routes/config.py`:

Add to imports:

```python
import sqlite3
from findajob.metrics.config_changes import detect_and_record
from findajob.paths import BASE
```

In `config_save` (the POST handler), after the successful `os.replace` but before the `return templates.TemplateResponse`, add:

```python
    try:
        conn = sqlite3.connect(f"{BASE}/data/pipeline.db", timeout=5)
        detect_and_record(conn, changed_by="manual", change_summary=f"edit via /config/ — {relpath}")
        conn.close()
    except Exception:
        pass  # drift detection is best-effort; never block a successful save
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/test_config_files_drift.py -v
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add src/findajob/web/routes/config.py tests/test_config_files_drift.py
git commit -m "feat(#229): /config/ POST triggers drift detection

Best-effort — a detection failure does not block a successful save.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 10: Wire detector into onboarding injector

**Files:**
- Modify: `src/findajob/onboarding/injector.py` — call detector after `mark_complete`
- Test: `tests/test_onboarding_injector.py` (extend existing)

- [ ] **Step 1: Write the failing test**

Modify: `tests/test_onboarding_injector.py` — append:

```python
def test_inject_records_config_changes_rows_for_written_levers(tmp_path, monkeypatch):
    """After inject(), config_changes should have rows for the levers whose files landed."""
    import sqlite3

    monkeypatch.setenv("JSP_BASE", str(tmp_path))
    (tmp_path / "data").mkdir()
    import importlib
    import scripts.init_db
    importlib.reload(scripts.init_db)

    from findajob.onboarding.injector import inject

    found = {
        "profile.md": "PROFILE",
        "master_resume.md": "RESUME",
        "prefilter_rules.yaml": "patterns: []",
        "target_companies.md": "## Tier 1\n- Acme Corp",
        "jsearch_queries.txt": "query one\n",
        "in_domain_patterns.yaml": "patterns: []",
        "business_sector_employers_reference.md": "# Employers",
    }
    inject(tmp_path, found)

    conn = sqlite3.connect(tmp_path / "data" / "pipeline.db")
    levers = {r[0] for r in conn.execute("SELECT DISTINCT lever FROM config_changes WHERE changed_by='onboarding'").fetchall()}
    assert {"profile", "master_resume", "target_companies", "queries", "prefilter_rules", "in_domain_patterns"} <= levers
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_onboarding_injector.py -v -k config_changes
```

Expected: fail — no rows.

- [ ] **Step 3: Call detector from injector**

Modify: `src/findajob/onboarding/injector.py`:

Add to imports:

```python
import sqlite3
from findajob.metrics.config_changes import detect_and_record
```

Inside `inject()`, after `mark_complete(base_root)` but still inside the `try:` block, add:

```python
        try:
            conn = sqlite3.connect(base_root / "data" / "pipeline.db", timeout=5)
            detect_and_record(conn, changed_by="onboarding", change_summary="onboarding paste-back")
            conn.close()
        except Exception:
            pass  # drift detection is best-effort
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/test_onboarding_injector.py -v
```

Expected: all tests pass (new one + existing ones).

- [ ] **Step 5: Commit**

```bash
git add src/findajob/onboarding/injector.py tests/test_onboarding_injector.py
git commit -m "feat(#229): onboarding injector triggers drift detection

changed_by='onboarding' tags bulk paste-back as a distinct source.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 11: Cost-tracking instrumentation in prep_application.py

**Files:**
- Modify: `scripts/prep_application.py` — wrap aichat() with `log_call`
- Test: `tests/test_prep_cost_tracking.py` (new)

- [ ] **Step 1: Write the failing test**

Create: `tests/test_prep_cost_tracking.py`:

```python
"""Verify prep_application.py logs every aichat-ng call to cost_log."""
from pathlib import Path


def test_prep_imports_log_call():
    src = Path(__file__).resolve().parents[1] / "scripts" / "prep_application.py"
    text = src.read_text()
    assert "from findajob.cost_tracking import log_call" in text, \
        "prep_application must import log_call"


def test_prep_aichat_helper_calls_log_call():
    """The aichat() helper should invoke log_call after every run."""
    src = Path(__file__).resolve().parents[1] / "scripts" / "prep_application.py"
    text = src.read_text()

    # Find the aichat function definition
    def_idx = text.find("def aichat(role")
    # Find its end — next top-level def
    next_def_idx = text.find("\ndef ", def_idx + 1)
    body = text[def_idx:next_def_idx]
    assert "log_call(" in body, "aichat() helper must call log_call"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_prep_cost_tracking.py -v
```

Expected: fail — no import or call.

- [ ] **Step 3: Instrument the `aichat()` helper**

Modify: `scripts/prep_application.py`:

Add to imports (top of file, near other `findajob` imports):

```python
import sqlite3
from findajob.cost_tracking import log_call
```

Replace the existing `aichat()` function (around line 39-51) with:

```python
def aichat(role, prompt, model_override=None, timeout=300, job_id=None):
    """Call aichat-ng and return stdout. No RAG — all context injected directly.

    When ``job_id`` is passed, the call is logged to ``cost_log`` so the
    metric layer can compute per-job-operation unit economics.
    """
    import time
    cmd = [AICHAT, "--role", role]
    if model_override:
        cmd += ["-m", model_override]
    cmd += ["-S", prompt]

    started = time.time()
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    latency_ms = int((time.time() - started) * 1000)

    output = result.stdout.strip()
    success = result.returncode == 0 and bool(output)

    if not success:
        log_event("aichat_failure", role=role, returncode=result.returncode, stderr=result.stderr.strip()[:500])

    # Strip <think>...</think> blocks that leak from :thinking models
    output = re.sub(r"<think>.*?</think>", "", output, flags=re.DOTALL).strip()

    if job_id is not None:
        try:
            conn = sqlite3.connect(f"{BASE}/data/pipeline.db", timeout=5)
            log_call(
                conn,
                job_id=job_id,
                operation=role,
                model=model_override or role,
                input_text=prompt,
                output_text=output,
                latency_ms=latency_ms,
                success=success,
            )
            conn.commit()
            conn.close()
        except Exception:
            pass  # cost tracking is best-effort

    return output
```

- [ ] **Step 4: Pass `job_id` to every aichat() call in prep_application.py**

Modify: `scripts/prep_application.py` — for every call to `aichat(...)` in the main flow (lines ~233, 244, 252, 263, 332, 382), pass `job_id=job_row["id"]` (or whatever the local variable holding the job id is called — check the surrounding context).

Example diff for one call:

```python
    # Before
    raw_briefing = aichat("company_researcher", brief_prompt, model_override="perplexity:sonar-reasoning-pro")
    # After
    raw_briefing = aichat("company_researcher", brief_prompt, model_override="perplexity:sonar-reasoning-pro", job_id=job_id)
```

Apply to all aichat calls where a job_id is in scope. Skip it if not — the helper handles None gracefully.

- [ ] **Step 5: Run the test**

```bash
uv run pytest tests/test_prep_cost_tracking.py -v
```

Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add scripts/prep_application.py tests/test_prep_cost_tracking.py
git commit -m "feat(#229): prep_application logs every aichat call to cost_log

aichat() helper accepts optional job_id; when passed, writes a
cost_log row with operation=role. Best-effort — never blocks prep.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 12: Cost-tracking instrumentation in find_contacts.py

**Files:**
- Modify: `scripts/find_contacts.py` — wrap aichat call with `log_call`
- Test: `tests/test_find_contacts_cost.py` (new)

- [ ] **Step 1: Write the failing test**

Create: `tests/test_find_contacts_cost.py`:

```python
"""Verify find_contacts.py logs outreach_drafter calls to cost_log."""
from pathlib import Path


def test_find_contacts_imports_log_call():
    src = Path(__file__).resolve().parents[1] / "scripts" / "find_contacts.py"
    text = src.read_text()
    assert "from findajob.cost_tracking import log_call" in text


def test_find_contacts_calls_log_call_after_subprocess_run():
    src = Path(__file__).resolve().parents[1] / "scripts" / "find_contacts.py"
    text = src.read_text()
    # outreach_drafter invocation — verify log_call is present in the module
    assert "log_call(" in text
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_find_contacts_cost.py -v
```

Expected: fail.

- [ ] **Step 3: Instrument the outreach call**

Modify: `scripts/find_contacts.py`:

Add to imports:

```python
import sqlite3
import time
from findajob.cost_tracking import log_call
```

Around line 97 (the outreach_drafter subprocess call), replace:

```python
    cmd = [AICHAT, "--role", "outreach_drafter", "-S", prompt]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
```

with:

```python
    cmd = [AICHAT, "--role", "outreach_drafter", "-S", prompt]
    started = time.time()
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    latency_ms = int((time.time() - started) * 1000)

    try:
        _conn = sqlite3.connect(f"{BASE}/data/pipeline.db", timeout=5)
        log_call(
            _conn,
            job_id=job_id,  # use the job_id local in the caller scope
            operation="outreach_drafter",
            model="claude:claude-sonnet-4-6",
            input_text=prompt,
            output_text=result.stdout.strip(),
            latency_ms=latency_ms,
            success=result.returncode == 0,
        )
        _conn.commit()
        _conn.close()
    except Exception:
        pass
```

Note: if `job_id` isn't in scope where the subprocess call is made, add a `job_id=None` argument to the enclosing function and thread it through from the caller — consult the surrounding function signature and propagate.

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/test_find_contacts_cost.py -v
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add scripts/find_contacts.py tests/test_find_contacts_cost.py
git commit -m "feat(#229): find_contacts logs outreach_drafter calls to cost_log

Best-effort cost tracking for the final LLM operation in the prep
flow. Completes cost coverage per /stats/cost requirements.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 13: Whole-feature verification gate

Run the end-to-end validation described in issue #229 acceptance criterion 6: run triage + prep once on a test job; confirm every LLM call lands in `cost_log` and every config edit lands in `config_changes`.

- [ ] **Step 1: Run the full test suite**

```bash
uv run pytest -q
```

Expected: zero failures.

- [ ] **Step 2: Run linters**

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy src/findajob
```

Expected: zero complaints across all three.

- [ ] **Step 3: Manual smoke — run `scripts/init_db.py` against a scratch DB**

```bash
JSP_BASE=/tmp/metric-c0-smoke bash -c 'mkdir -p $JSP_BASE/data && uv run python scripts/init_db.py && sqlite3 $JSP_BASE/data/pipeline.db ".schema config_changes"'
```

Expected: CREATE TABLE statement printed; no error.

- [ ] **Step 4: Manual smoke — verify backfill idempotency**

```bash
# Against the operator's real DB? NO — use a copy.
cp data/pipeline.db /tmp/pipeline-c0-smoke.db
JSP_BASE_OVERRIDE=/tmp sqlite3 /tmp/pipeline-c0-smoke.db "SELECT COUNT(*) FROM jobs WHERE company_tier='unknown'"
# Run backfill
# (Adapt env as needed — operator tests this against a real DB copy.)
```

Expected: after backfill, no rows have `company_tier='unknown'` unless the company field is truly empty.

- [ ] **Step 5: Push branch and open PR**

```bash
git push -u origin feat/229-metric-layer-c0
gh pr create \
    --title "feat(#229): Metric Layer C.0 — schema, drift detector, cost instrumentation" \
    --label migration-required \
    --body "$(cat <<'EOF'
## Summary

Phase C.0 of the Metric Layer (subsystem C of the data-driven tuning loop epic, #228). Schema + instrumentation prerequisites for C.1's view layer. No user-visible UI in this phase.

- New \`config_changes\` + \`recall_audit\` tables
- New \`jobs.company_tier\` + \`jobs.scored_by\` columns, populated at score time and backfilled for existing rows
- Config-drift detector hooked into three surfaces (triage pre-call, /config/ POST, onboarding injector)
- Cost-tracking instrumentation completed on prep, outreach, briefing, company research LLM calls (previously only scoring was tracked)

See spec: \`docs/superpowers/specs/2026-04-24-metric-layer-design.md\` §6, §7.4, §8.

Issue: #229 (parent epic: #228). Blocks: #230 (C.1 view layer).

## Migration required

- Run \`scripts/init_db.py\` on upgrade
- Run \`uv run python scripts/backfill_company_tier.py\`
- Run \`uv run python scripts/backfill_scored_by.py\`

All three are idempotent; safe to rerun.

## Test plan

- [x] All unit tests pass (\`uv run pytest -q\`)
- [x] Linters clean (ruff check, ruff format --check, mypy)
- [ ] Manual smoke: \`init_db.py\` against a scratch DB; schema verified
- [ ] Manual smoke: backfill scripts against a DB copy; \`company_tier\` and \`scored_by\` populated deterministically
- [ ] Manual smoke: edit one config file via \`/config/\`; confirm a row lands in \`config_changes\` with \`changed_by='manual'\`
- [ ] Manual smoke: run triage; confirm a pre-triage \`config_changes\` detection row lands with \`changed_by='manual'\` (or none if no edits)
- [ ] Manual smoke: run prep on one job; confirm \`cost_log\` has rows for every aichat operation (resume_tailor, cover_letter_writer, company_researcher, briefing_writer, fit_analyst, resume_change_reviewer)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Expected: PR opened with `migration-required` label. URL returned.

---

## Task 14: Close out

- [ ] **Step 1: Append a Session note to issue #229**

```bash
/home/brockamer/Code/jared//skills/jared/scripts/jared comment 229 "$(cat <<'EOF'
## Session 2026-04-24

### Progress
Implementation plan written (`docs/superpowers/plans/2026-04-24-metric-layer-c0.md`). 14 tasks covering schema, population, backfill, drift detector + 3 integration points, cost instrumentation on prep + find_contacts, and a validation gate. All tasks TDD.

### State
PR open: (URL filled in after Step 5 above). Awaiting review.

### Next action
After merge: run the three manual smoke items in the PR test plan on docker.lan; deploy image; run backfill scripts once per stack. Then pull #230 (C.1).
EOF
)"
```

- [ ] **Step 2: Done**

Once merged and smoke-tested on docker.lan, close #229 via `jared close 229`.

---

## Documentation Impact

Per `docs/plan-conventions.md`, enumerating every doc surface this plan touches:

- **CLAUDE.md** — no change needed in this phase; spec's §10 notes that a brief entry goes in when `src/findajob/metrics/` grows beyond `config_changes.py` (i.e., during C.1). C.0 adds one file to that package — too early to document.
- **CHANGELOG.md** — seeded in the pre-task. One `### Migration required` bullet enumerated.
- **docs/setup/install-docker.md** — no change; backfill commands are in the PR's test plan and in the CHANGELOG, sufficient for the upgrade path.
- **docs/superpowers/specs/2026-04-24-metric-layer-design.md** — this plan is an artifact of that spec; no spec changes needed.
- **docs/project-board.md** — no change; conventions unchanged.
- **Docstrings** — every new module (`src/findajob/tiers.py`, `src/findajob/metrics/__init__.py`, `src/findajob/metrics/config_changes.py`) and new script (`scripts/backfill_company_tier.py`, `scripts/backfill_scored_by.py`) has a module-level docstring per the codebase convention.
- **This plan** — committed to `docs/superpowers/plans/` so the PR description can reference it.

---

## Self-Review Checklist

Mapping every issue #229 acceptance criterion to a task:

| Issue #229 AC | Covered by |
|---|---|
| 1. `config_changes` table with required columns | Task 1 |
| 2. `recall_audit` table with required columns | Task 1 |
| 3. `jobs.company_tier` + `jobs.scored_by` columns, populated on new scores | Tasks 1, 2, 3, 4, 5 |
| 4. Backfill scripts for existing rows; `scored_by` ambiguous defaults to `'llm'` | Task 6 |
| 5. `scripts/detect_config_drift.py` (implemented as `findajob.metrics.config_changes.detect_and_record`) wired to triage, `/config/` POST, onboarding | Tasks 7, 8, 9, 10 |
| 6. `log_call` invoked for every aichat-ng call in prep, outreach, briefing/company-research paths; verified E2E | Tasks 11, 12, 13 |
| 7. `init_db.py` idempotent for fresh + upgrade | Task 1 (idempotency test) |
| 8. Unit tests for detector first-call / unchanged / changed; backfill determinism | Tasks 6, 7 |

Placeholder scan: none found (no TBD/TODO). Every code step includes the actual code.

Type-consistency scan: `scored_by` values `'prefilter_stage1' \| 'prefilter_stage2' \| 'llm'` consistent across prefilter, scoring, triage, backfill, and detector. `company_tier` values `'tier1' \| 'other' \| 'unknown'` consistent across tiers module, prefilter, scoring, triage, backfill. Function signature for `detect_and_record(conn, *, changed_by, change_summary)` consistent in every call site.

Scope check: this plan covers C.0 only. C.1 (view layer + `/stats/*` pages) and C.2 (recall-audit cron) are separate plans.
