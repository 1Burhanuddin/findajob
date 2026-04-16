# Dashboard Status Integration Plan — COMPLETE (2026-04-14)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Dashboard STATUS column accurately reflect every stage of the job lifecycle — especially "Prep in Progress" while prep is running, and reliable "Regenerate" handling.

**Architecture:** Three scripts participate in the status lifecycle: `poll_flags.py` reads user actions from the sheet, `prep_application.py` runs LLM prep, and `sync_sheet.py` writes DB state back to the sheet. The fix tightens the contract between them so the sheet always reflects ground truth.

**Tech Stack:** Python 3.12, Google Sheets API, SQLite, pytest

**Spec:** This plan. No separate spec doc.

**Prerequisites:** The earlier session already applied these fixes (in working tree, uncommitted):
- `sync_sheet.py` line 257: "Flag for Prep" cleared when `stage in ("materials_drafted", "prep_in_progress")`
- `sync_sheet.py` line 136: `apply_flag` only generates "Flag for Prep" when `stage in ("scored", "manual_review", "enriched")`
- `poll_flags.py`: All `Popen` calls have `start_new_session=True`
- `findajob-poller.service`: `KillMode=process`
- `bootstrap.sh`: `KillMode=process` in service template

---

## Status Lifecycle — Complete Map

This is the intended behavior after all tasks are complete:

| # | Sheet STATUS | Trigger | DB stage | What happens |
|---|-------------|---------|----------|-------------|
| 1 | *(empty)* | System | `scored` | Job scored, waiting for user decision |
| 2 | `Flag for Prep` | User selects | `scored` → `prep_in_progress` | Poller picks up flag, sets stage, launches prep |
| 3 | `Prep in Progress` | System (sync) | `prep_in_progress` | Sync derives from DB stage — **NEW** |
| 4 | `Ready to Apply` | System (sync) | `materials_drafted` | Prep complete, materials in folder |
| 5 | `Regenerate` | User selects | `materials_drafted` → `prep_in_progress` | Poller deletes old folder, re-runs prep |
| 6 | `Prep in Progress` | System (sync) | `prep_in_progress` | Same as #3 — after Regenerate processed |
| 7 | `Waitlist` | User selects | `waitlisted` | Poller moves folder to `_waitlisted/` |
| 8 | `Applied` | User selects | `applied` | Poller moves folder to `_applied/` |
| 9 | `Interviewing` | User selects | `interview` | Poller updates stage |
| 10 | `Offer` | User selects | `offer` | Poller updates stage |
| 11 | `Withdrew` | User selects | `withdrawn` | Poller updates stage, surfaces waitlisted jobs |
| 12 | *(REJECT_REASON set)* | User selects | `rejected` | Poller rejects, moves folder to `_rejected/` |

**Key transitions to verify end-to-end:**
- `(empty)` → `Flag for Prep` → `Prep in Progress` → `Ready to Apply` (happy path)
- `Ready to Apply` → `Regenerate` → `Prep in Progress` → `Ready to Apply` (regen path)
- `Ready to Apply` → `Applied` (apply path)
- `Ready to Apply` → `Waitlist` (defer path)
- Any → REJECT_REASON set (reject path)

---

## Task 1: Add "Prep in Progress" status to sync_sheet.py

**Files:**
- Modify: `scripts/sync_sheet.py:134-139` (build_row status logic)
- Test: `tests/test_sync_sheet.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_sync_sheet.py` class `TestBuildRowDashboard`:

```python
def test_prep_in_progress_shows_prep_in_progress(self):
    row = _make_row(stage="prep_in_progress")
    result = build_row(row, DASH_HEADERS, DASH_LOOKUP, use_status=True)
    assert result[0] == "Prep in Progress"

def test_prep_in_progress_apply_flag_1_still_shows_prep_in_progress(self):
    """apply_flag=1 should NOT override stage-derived status."""
    row = _make_row(stage="prep_in_progress", apply_flag=1)
    result = build_row(row, DASH_HEADERS, DASH_LOOKUP, use_status=True)
    assert result[0] == "Prep in Progress"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_sync_sheet.py::TestBuildRowDashboard::test_prep_in_progress_shows_prep_in_progress tests/test_sync_sheet.py::TestBuildRowDashboard::test_prep_in_progress_apply_flag_1_still_shows_prep_in_progress -v`

Expected: FAIL — both return `""` instead of `"Prep in Progress"`

- [ ] **Step 3: Add prep_in_progress handling to build_row**

In `scripts/sync_sheet.py`, modify the build_row status logic. Insert between the `materials_drafted` check (line 134-135) and the `apply_flag` check (line 136-137):

```python
                elif row["stage"] == "materials_drafted":
                    sheet_row.append("Ready to Apply")
                elif row["stage"] == "prep_in_progress":
                    sheet_row.append("Prep in Progress")
                elif bool(val) and row["stage"] in ("scored", "manual_review", "enriched"):
                    sheet_row.append("Flag for Prep")
                else:
                    sheet_row.append("")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_sync_sheet.py -v`

Expected: all tests pass, including the two new ones.

- [ ] **Step 5: Commit**

```bash
git add scripts/sync_sheet.py tests/test_sync_sheet.py
git commit -m "Add 'Prep in Progress' status to Dashboard sync"
```

---

## Task 2: Preserve "Regenerate" in sync and clear stale action statuses

**Files:**
- Modify: `scripts/sync_sheet.py:221,257` (VALID_STATUSES and pending filter)
- Test: `tests/test_sync_sheet.py`

- [ ] **Step 1: Write the failing tests**

Update the `_resolve_pending` helper in `tests/test_sync_sheet.py` to match the current (and planned) logic, then add new test cases. Replace the existing `_resolve_pending` and `TestPendingStatusPreservation`:

```python
def _resolve_pending(pending_status, stage):
    """Replicate the sync_dashboard pending-status override logic.

    Returns the status_override to pass to build_row (None means let build_row derive).
    """
    if pending_status and not (
        pending_status in ("Flag for Prep", "Regenerate")
        and stage in ("materials_drafted", "prep_in_progress")
    ):
        return pending_status
    return None


class TestPendingStatusPreservation:
    def test_flag_for_prep_scored_preserved(self):
        assert _resolve_pending("Flag for Prep", "scored") == "Flag for Prep"

    def test_flag_for_prep_materials_drafted_not_preserved(self):
        assert _resolve_pending("Flag for Prep", "materials_drafted") is None

    def test_flag_for_prep_prep_in_progress_not_preserved(self):
        assert _resolve_pending("Flag for Prep", "prep_in_progress") is None

    def test_regenerate_scored_preserved(self):
        """Regenerate on a scored job (edge case) — preserve it for poller."""
        assert _resolve_pending("Regenerate", "scored") == "Regenerate"

    def test_regenerate_materials_drafted_preserved(self):
        """Regenerate on materials_drafted — preserve until poller processes it."""
        assert _resolve_pending("Regenerate", "materials_drafted") == "Regenerate"

    def test_regenerate_prep_in_progress_not_preserved(self):
        """After poller processes Regenerate → stage=prep_in_progress, clear it."""
        assert _resolve_pending("Regenerate", "prep_in_progress") is None

    def test_applied_preserved_regardless_of_stage(self):
        assert _resolve_pending("Applied", "scored") == "Applied"
        assert _resolve_pending("Applied", "materials_drafted") == "Applied"

    def test_empty_status_returns_none(self):
        assert _resolve_pending("", "scored") is None

    def test_waitlist_status_preserved(self):
        assert _resolve_pending("Waitlist", "scored") == "Waitlist"
```

- [ ] **Step 2: Run tests to verify new Regenerate tests fail**

Run: `pytest tests/test_sync_sheet.py::TestPendingStatusPreservation -v`

Expected: `test_regenerate_materials_drafted_preserved` FAILS (Regenerate not in VALID_STATUSES so it's never captured).

Note: the `_resolve_pending` helper tests the logic in isolation. The actual code path also depends on VALID_STATUSES filtering, which we test by checking behavior, not the set directly.

- [ ] **Step 3: Add "Regenerate" to VALID_STATUSES and update filter**

In `scripts/sync_sheet.py`:

Line 221 — add `"Regenerate"` to the set:
```python
VALID_STATUSES = {"Flag for Prep", "Regenerate", "Applied", "Interviewing", "Offer", "Withdrew", "Waitlist"}
```

Line 257 — expand the filter to clear both action statuses:
```python
        if pending and not (pending in ("Flag for Prep", "Regenerate") and row["stage"] in ("materials_drafted", "prep_in_progress")):
            status_override = pending
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_sync_sheet.py -v`

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add scripts/sync_sheet.py tests/test_sync_sheet.py
git commit -m "Preserve Regenerate in sync, clear action statuses after processing"
```

---

## Task 3: Trigger sync after flag processing in poll_flags.py

**Files:**
- Modify: `scripts/poll_flags.py:452-474` (need_sync logic)
- Test: `tests/test_poll_flags.py` (optional — this is a one-line change to control flow)

Without this change, the Dashboard stays on "Flag for Prep" until an unrelated event (rejection, triage) triggers sync. With it, the poller triggers sync immediately after processing flags, so "Prep in Progress" appears within seconds.

- [ ] **Step 1: Add flagged_jobs to need_sync triggers**

In `scripts/poll_flags.py`, after the existing `need_sync` checks (around line 470), add:

```python
    if flagged_jobs:
        need_sync = True
```

Place it before the `if need_sync:` Popen call.

- [ ] **Step 2: Run existing tests**

Run: `pytest tests/test_poll_flags.py -v`

Expected: all pass (this is control flow, not logic).

- [ ] **Step 3: Commit**

```bash
git add scripts/poll_flags.py
git commit -m "Trigger sheet sync after flag processing for immediate status update"
```

---

## Task 4: Add "Prep in Progress" color to setup_sheets.py

**Files:**
- Modify: `scripts/setup_sheets.py:74-83,104-114` (STATUS_OPTIONS and STATUS_COLORS)

- [ ] **Step 1: Add "Prep in Progress" to STATUS_OPTIONS and STATUS_COLORS**

In `scripts/setup_sheets.py`:

Add to `STATUS_OPTIONS` (after "Flag for Prep", before "Regenerate"):
```python
STATUS_OPTIONS = [
    "Flag for Prep",
    "Prep in Progress",
    "Regenerate",
    "Ready to Apply",
    "Waitlist",
    "Applied",
    "Interviewing",
    "Offer",
    "Withdrew",
]
```

Add to `STATUS_COLORS` (after "Flag for Prep"):
```python
    "Prep in Progress": rgb(255, 235, 156),  # warm yellow — actively running
```

- [ ] **Step 2: Run setup_sheets.py to apply formatting**

```bash
cd ~/Code/findajob
python3 scripts/setup_sheets.py
```

Expected: completes without error. Check the Dashboard in the browser — "Prep in Progress" cells should now have warm yellow highlighting.

- [ ] **Step 3: Commit**

```bash
git add scripts/setup_sheets.py
git commit -m "Add Prep in Progress status color to Dashboard formatting"
```

---

## Task 5: End-to-end testing of every status transition

**No code changes.** This task validates the full lifecycle by exercising the pipeline with real data.

**Setup:** Pick a low-stakes test job currently on the Dashboard (score 7, stage=scored). If none are available, use one of the jobs that just had materials drafted. Record its fingerprint.

### Test A: Flag for Prep → Prep in Progress → Ready to Apply

- [ ] **Step 1: Set "Flag for Prep" on a scored job in the Dashboard**

Open the Google Sheet, go to Dashboard, pick a scored job with empty STATUS. Set STATUS to "Flag for Prep".

- [ ] **Step 2: Run the poller and verify DB transition**

```bash
cd ~/Code/findajob
python3 scripts/poll_flags.py
```

Check DB:
```bash
sqlite3 data/pipeline.db "SELECT stage, apply_flag FROM jobs WHERE fingerprint='<FP>';"
```
Expected: `prep_in_progress|1`

- [ ] **Step 3: Verify the sheet updated to "Prep in Progress"**

Wait a few seconds for the sync (triggered by poller). Reload the Dashboard in the browser.

Expected: STATUS cell shows "Prep in Progress" with warm yellow highlight.

If sync hasn't run yet:
```bash
python3 scripts/sync_sheet.py
```

- [ ] **Step 4: Wait for prep to complete and verify "Ready to Apply"**

Monitor prep completion:
```bash
tail -f logs/pipeline.jsonl | grep prep_complete
```

Once complete, run sync:
```bash
python3 scripts/sync_sheet.py
```

Expected: STATUS cell shows "Ready to Apply" with teal highlight. Company cell is a hyperlink to the Drive folder.

### Test B: Regenerate → Prep in Progress → Ready to Apply

- [ ] **Step 5: Set "Regenerate" on the job from Test A**

In the Dashboard, set STATUS to "Regenerate" on the job that now shows "Ready to Apply".

- [ ] **Step 6: Verify Regenerate survives a sync cycle**

Before running the poller, run sync to verify Regenerate is preserved:
```bash
python3 scripts/sync_sheet.py
```

Check the Dashboard — STATUS should still show "Regenerate" (not overwritten to "Ready to Apply").

- [ ] **Step 7: Run the poller and verify Regenerate → Prep in Progress**

```bash
python3 scripts/poll_flags.py
```

Check DB:
```bash
sqlite3 data/pipeline.db "SELECT stage, prep_folder_path FROM jobs WHERE fingerprint='<FP>';"
```
Expected: `prep_in_progress|` (empty folder path — old folder deleted).

Check sheet (after sync):
Expected: STATUS shows "Prep in Progress".

- [ ] **Step 8: Wait for regen prep to complete**

Same as Step 4. Verify "Ready to Apply" appears with new materials folder.

### Test C: Applied flow

- [ ] **Step 9: Set "Applied" on a "Ready to Apply" job**

Pick a job showing "Ready to Apply". Set STATUS to "Applied".

```bash
python3 scripts/poll_flags.py
```

Verify:
```bash
sqlite3 data/pipeline.db "SELECT stage FROM jobs WHERE fingerprint='<FP>';"
```
Expected: `applied`

Verify folder moved:
```bash
ls companies/_applied/ | grep <company>
```

### Test D: Waitlist flow

- [ ] **Step 10: Set "Waitlist" on a "Ready to Apply" job**

Pick a different job. Set STATUS to "Waitlist".

```bash
python3 scripts/poll_flags.py
python3 scripts/sync_sheet.py
```

Verify: job disappears from Dashboard, appears on Waitlist tab. Folder in `companies/_waitlisted/`.

### Test E: Rejection flow

- [ ] **Step 11: Set REJECT_REASON on any Dashboard job**

Pick a low-value job. Set REJECT_REASON to "Skills Mismatch" (col B).

```bash
python3 scripts/poll_flags.py
```

Verify: `stage=rejected` in DB. Folder in `companies/_rejected/` (if it had one). Job disappears from Dashboard.

### Test F: Systemd timer verification

- [ ] **Step 12: Verify timer-triggered poller works end-to-end**

Flag a job as "Flag for Prep" on the Dashboard. Do NOT run the poller manually. Wait for the next 30-min timer cycle.

After the timer fires:
```bash
journalctl --user -u findajob-poller.service --since "5 min ago"
```

Check that prep processes survive:
```bash
ps aux | grep prep_application | grep -v grep
```

Expected: prep processes running even though the poller service has exited.
