# Web Frontend Phase 14c — STATUS + REJECT_REASON Write Workflows

> **ARCHIVED** — Issue #61 shipped 2026-04-22 via PRs #178 (PR-A), #179 (PR-B), #180 (PR-C). See the closed issue and merged PRs for the canonical record. Follow-ups tracked in #181 (Playwright E2E), #182 (dedup cluster), #183 (.docx download).

**Issue:** [#61](https://github.com/brockamer/findajob/issues/61)
**Parent:** #14 (web frontend arc)
**Spec date:** 2026-04-22
**Status:** SHIPPED 2026-04-22.

Depends on #60 (shipped 2026-04-21) — the `/board/*` read-only scaffolding, `_job_row.html` partial, and shared `web/constants.py::FOLDER_STAGES` are preconditions for every action in this spec.

---

## Overview

14c turns the read-only board pages from #60 into the operator's primary write surface for every pipeline transition that currently lives on the Google Sheet. `poll_flags.py` — the ten-minute cron that translates Sheet edits to DB state — stops reading Sheets entirely and shrinks to a small watchdog. `sync_sheet.py` keeps writing to Sheets in parallel (one-way: DB → Sheet) until 14d (#14) retires the Sheet entirely.

The Sheet workspace remains viewable; the operator simply stops editing it.

### Acceptance criteria (from the issue)

1. All STATUS + REJECT_REASON workflows documented in `docs/architecture.md` work in the web UI: **Flag for Prep, Applied, Interviewing, Offer, Ghosted, Not Selected, Withdrew, Regenerate, Waitlist, Reactivate, Promote**.
2. `poll_flags.py` no longer calls `sheets_service.spreadsheets().values().get()` on any tab.
3. Sheet edits by the user are ignored by the pipeline (one-way sync: DB → Sheet).
4. No regressions in prep → applied → not_selected → rejected transitions.

Each criterion maps to a task in the companion plan.

---

## Foundational decisions (commit explicitly; do not leave open)

These are the decisions called out as load-bearing during design review. Every later section in this spec follows from them.

### D1 — Prep dispatch model: web handler launches subprocess directly

The `POST /board/jobs/{fp}/prep` handler launches `prep_application.py` via `subprocess.Popen(..., start_new_session=True)` and returns immediately. The subprocess lives past the HTTP response; it writes results to the DB and runs its own `sync_sheet.py` on completion.

**Rejected:** a persisted action queue table + worker. Adds a schema and a process for a single async action (prep dispatch). The DB `stage` column is already the queue: `stage='prep_in_progress'` with no running child means stale; the watchdog catches it.

**Consequence:** `scripts/prep_application.py --no-sync` is orphaned (its only caller was `poll_flags.py`). Flip the default: prep always runs `sync_sheet.py` on success. Drop the flag.

### D2 — `poll_flags.py` shrinks to a watchdog, renamed `scripts/watchdog.py`

After the pivot the script does one thing: reset jobs stuck in `prep_in_progress` for >60min to `scored` (current behavior, lines 191–214). Every Sheets read path is deleted. Every POST-handled transition is deleted. No consolidated sync (each web handler and each prep subprocess runs `sync_sheet.py` themselves when needed).

Rename is part of the refactor to prevent confusion: "polling flags" no longer describes the script. The supercronic entry in `ops/crontab` updates in the same PR.

### D3 — `Ghosted` is dropped as a distinct status

On the Sheet today `Ghosted` is a user-set string preserved across syncs; it's visual-only (stage stays `applied`). Without `sync_sheet.py` reading the Sheet back, there is no carrier for the flag.

The pre-existing age-based row coloring on `/board/applied` already turns a row gray at 21 days (`helpers.py::applied_age_bucket` → `row-applied-cold`). That covers the "quiet for weeks" visual intent. Operators who want to act on a ghosted application flip it to **Not Selected** — already a valid action.

**Rejected:** adding `jobs.ghosted INTEGER` and a UI toggle. Two states now do the work one state did before; the explicit flag adds a schema migration and a fourth row color rule with no observable benefit.

The `Ghosted` option disappears from the Applied tab's status options in the UI. `sync_sheet.py` stops emitting it. `poll_flags.py`'s existing behavior (which already treats `Ghosted` as a no-op for DB) is removed along with the whole poller.

### D4 — Endpoints: one POST per concrete action

`POST /board/jobs/{fingerprint}/{action}`, HTMX-submitted forms, return the re-rendered `<tr>` for the current tab. Matches 14b's HTMX idiom (§Data flow, 14b spec).

| Action | Endpoint | Tabs that surface it |
|---|---|---|
| Flag for Prep | `POST /board/jobs/{fp}/prep` | Dashboard |
| Regenerate | `POST /board/jobs/{fp}/regenerate` | Dashboard |
| Waitlist | `POST /board/jobs/{fp}/waitlist` | Dashboard |
| Applied | `POST /board/jobs/{fp}/apply` | Dashboard |
| Interviewing | `POST /board/jobs/{fp}/interview` | Applied |
| Offer | `POST /board/jobs/{fp}/offer` | Applied |
| Withdrew | `POST /board/jobs/{fp}/withdraw` | Applied |
| Not Selected | `POST /board/jobs/{fp}/not-selected` (form field: `reason`) | Applied |
| Reject | `POST /board/jobs/{fp}/reject` (form field: `reason`) | Dashboard, Applied, Review, Waitlist |
| Reactivate | `POST /board/jobs/{fp}/reactivate` | Waitlist |
| Promote | `POST /board/jobs/{fp}/promote` | Review |

**Rejected alternatives:**
- One catch-all `POST /board/jobs/{fp}/stage` taking a `new_stage` form field. Harder to log, harder to test, easier to mis-route (e.g., emitting `stage=rejected` via this endpoint bypasses `feedback_log`).
- REST-style verbs (`PATCH /jobs/{fp}`). FastAPI is GET/POST-only in 14b; no reason to add verb variety now.

### D5 — Concurrency cap preserved in the Prep handler

`poll_flags.py` today caps concurrent preps at 3 (`MAX_CONCURRENT_PREPS`). The web handler replicates this inline:

```python
in_flight = db.execute(
    "SELECT COUNT(*) FROM jobs WHERE stage='prep_in_progress'"
).fetchone()[0]
if in_flight >= 3:
    return HTMLResponse(..., status_code=429)  # HTMX shows a toast; DB unchanged
```

**Rejected:** silently dropping the cap. Prep hits Perplexity + Anthropic + pandoc sequentially — three jobs in parallel is already tight on memory inside the container; five is risky.

### D6 — Idempotency via DB-read-before-write

Every handler re-reads `jobs.stage` inside the request and returns early if the transition is already reflected. Matches `poll_flags.py`'s existing `if job["stage"] != new_stage` guard. Double-submit is a no-op, never a double-transition.

### D7 — Auth deferred; single-operator assumption restated

14b deferred auth explicitly (14b spec §Deferred). Adding POST endpoints does not change the threat model: the materials viewer already serves `/materials/{fp}/*.docx` over the same surface, and the stack runs on the operator's WireGuard mesh (CLAUDE.local.md §Platform). The spec restates the "don't expose to public internet" assumption and defers CSRF to the auth work item.

**Rejected:** a same-origin CSRF token. Adds setup overhead for zero threat reduction in the current deployment posture. Revisit when auth lands.

---

## The four Sheets-read paths that disappear

`poll_flags.py` has three `values().get()` calls today (`Dashboard!A2:C`, `Applied!A2:C`, `Review!A2:C`, `Waitlist!A2:C`). `sync_sheet.py` has three more read-back calls (`Dashboard!A2:C`, `Applied!A2:I`, and `Sheet1!A2:C` for preserved `pending_statuses` / `pending_rejects` / `pending_notes`).

After 14c:

| Read path | Consumer today | 14c disposition |
|---|---|---|
| `Dashboard!A2:C` | `poll_flags.py` (STATUS + REJECT + fp) | Deleted |
| `Applied!A2:C` | `poll_flags.py` (STATUS + REJECT + fp) | Deleted |
| `Review!A2:C` | `poll_flags.py` (STATUS + REJECT + fp) | Deleted |
| `Waitlist!A2:C` | `poll_flags.py` (STATUS + REJECT + fp) | Deleted |
| `Dashboard!A2:C` | `sync_sheet.py` (`pending_statuses`, `pending_rejects`) | Deleted — DB is now authoritative, nothing pending |
| `Applied!A2:I` | `sync_sheet.py` (`pending_statuses`, `pending_rejects`, `pending_notes`) | Deleted — same rationale; `user_notes` comes from DB |
| `Sheet1!A2:C` | `sync_sheet.py` (`pending_statuses` in Sheet1 sync — legacy) | Deleted |

Acceptance criterion 2 is "`poll_flags.py` no longer calls `values().get()`". Criterion 3 is "Sheet edits are ignored by the pipeline" — broader; covers the `sync_sheet.py` read paths as well. Both criteria must be verified in the plan, not just criterion 2.

---

## Handler matrix — invariants per action

Every handler performs, in order: **(1)** authz-guard (future no-op), **(2)** fp→job lookup, **(3)** stage precondition check (idempotency guard per D6), **(4)** the transition itself, **(5)** `sync_sheet.py` invocation if the row's visible tab changed, **(6)** render the new `<tr>` and return it to HTMX.

The transition logic in `(4)` must preserve exactly what `poll_flags.py` does today. The handlers reuse the existing pure functions in `poll_flags.py` (`handle_rejection`, `handle_not_selected`, `handle_waitlist`, `handle_reactivate`, `notify_waitlist_resurface`) — these get **extracted** to `src/findajob/actions.py` in PR-A so both the web layer and the old poller can call them. Once `poll_flags.py` is deleted in PR-B, only the web layer calls them.

Critical invariants that must survive the extraction (stated verbatim so the plan can verify):

- **Rejection writes `feedback_log`.** `handle_rejection` inserts a `feedback_log` row. All other actions — Not Selected, Withdrew, Waitlist — do NOT.
- **Not Selected drops a marker file in `_applied/`**. Folder does NOT move. Marker name: `NOT_SELECTED_{safe_reason}_{YYYY-MM-DD}.txt`.
- **Rejection moves folder to `_rejected/`** with marker `REJECTED_{safe_reason}_{YYYY-MM-DD}.txt`. `jobs.prep_folder_path` is updated to the new path.
- **Applied moves folder to `_applied/`** and sets `stage=applied`. The `applied_date` is sourced from `audit_log` (first transition into applied/interview/offer).
- **Waitlist moves folder to `_waitlisted/`** and sets `stage=waitlisted`. No `feedback_log` write.
- **Reactivate moves folder back from `_waitlisted/`** to `companies/`. Sets `stage=materials_drafted` if folder exists, else `stage=scored`.
- **`notify_waitlist_resurface` fires on rejection, not-selected, and withdraw.** Not on waitlist, not on apply, not on reject-from-waitlist (since it's the same company's other jobs we're surfacing).
- **Every transition writes `audit_log`** via `write_audit()`.
- **Regenerate** deletes the existing prep folder, sets stage back to `prep_in_progress`, and dispatches a fresh prep subprocess. `stage='prep_in_progress'` cannot self-Regenerate (the handler no-ops).
- **Promote** (from Review) sets `relevance_score=7`, `stage='scored'`, `score_status='scored'`, `score_flag_reason='Promoted from web UI'`.
- **Reject-from-Review, Reject-from-Waitlist, Reject-from-Dashboard, Reject-from-Applied** all use the same `handle_rejection` path — only the originating tab differs, the DB writes are identical.

---

## `poll_flags.py` → `watchdog.py`

### What it does after 14c

```python
# scripts/watchdog.py — runs every 10 min via supercronic.
# Single responsibility: reset jobs stuck in prep_in_progress > 60min.

STALE_PREP_MINUTES = 60

def main():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    stale = conn.execute(
        """SELECT id, title, company FROM jobs
           WHERE stage = 'prep_in_progress'
             AND stage_updated < datetime('now', ?)""",
        (f"-{STALE_PREP_MINUTES} minutes",),
    ).fetchall()
    for job in stale:
        reset_prep_to_scored(conn, job["id"], reason="watchdog_stale_reset")
    conn.close()
```

### What it stops doing

Every other block in today's `poll_flags.py` goes away: the Dashboard/Applied loop, the Review loop, the Waitlist loop, the child-prep-subprocess launching, the child-wait + consolidated sync, the `dashboard_db_rows` telemetry. All of it.

### ops/crontab change

Replace the `poll_flags.py` line with a `watchdog.py` line on the same schedule (every 10 min).

---

## `sync_sheet.py` changes

Scope for 14c (retirement of the script itself is 14d):

1. Delete the three `values().get()` calls (`Dashboard!A2:C`, `Applied!A2:I`, `Sheet1!A2:C`).
2. Delete the `pending_statuses`, `pending_rejects`, `pending_notes` preservation logic.
3. Delete the `user_notes` readback loop in `sync_applied`. `user_notes` is now written via the web UI (see D8 below — new Applied notes endpoint) and read from DB as before.
4. STATUS column is now always derived from DB stage. Remove the `Ghosted` branch from the derivation.
5. `APPLIED_VALID_STATUSES` / `VALID_STATUSES` constants go away.

### D8 — `user_notes` becomes a web POST

Today `user_notes` is a Sheet-side free-text column that `sync_sheet.py` reads back on each run. With reads deleted, notes edits need a home.

`POST /board/jobs/{fp}/notes` with form field `notes` updates `jobs.user_notes`. The Applied tab's notes cell becomes an `hx-post` input (HTMX `hx-trigger="blur, keyup changed delay:800ms"`). Rendered `<td>` returned on success.

---

## File structure after 14c

```
src/findajob/
  actions.py               — NEW. Extracted from poll_flags.py:
                                handle_rejection, handle_not_selected,
                                handle_waitlist, handle_reactivate,
                                notify_waitlist_resurface,
                                reset_prep_to_scored (moved from utils.py),
                                promote_to_scored (new — was inline in poll_flags).
                              All functions take (conn, job, ...) and commit.
                              Pure in the sense that they don't touch Sheets or
                              HTTP — the web handler and tests drive them directly.
  web/
    routes/
      board_actions.py      — NEW. POST handlers per D4 matrix. Calls into
                              findajob.actions. Returns re-rendered <tr>.
      board.py              — Extended. _DASHBOARD_COLS / _APPLIED_COLS /
                              _REVIEW_COLS / _WAITLIST_COLS gain the STATUS
                              and REJECT_REASON interactive cells. _job_row
                              rendering picks up the new controls.
    templates/
      board/
        _status_cell.html   — NEW. Per-tab STATUS dropdown (HTMX forms).
        _reject_cell.html   — NEW. REJECT_REASON dropdown (HTMX form).
        _notes_cell.html    — NEW. user_notes input (Applied tab only).
scripts/
  watchdog.py               — NEW. Stale-prep cleanup only (D2).
  poll_flags.py             — DELETED in PR-B.
  prep_application.py       — `--no-sync` flag removed; sync always runs (D1).
  sync_sheet.py             — Read paths deleted (§sync_sheet.py changes).
ops/
  crontab                   — poll_flags line → watchdog line.
tests/
  test_actions.py           — NEW. Unit tests for every function in findajob.actions.
  test_board_actions.py     — NEW. FastAPI TestClient tests per endpoint.
  test_watchdog.py          — NEW (or fold into test_poll_flags.py rename).
  test_poll_flags.py        — DELETED in PR-B, replaced by test_watchdog.py.
  e2e/                      — NEW. Playwright tests (D9 below).
```

---

## PR boundary — split into two

14c is the phase's highest-complexity piece. Ship it in two PRs under issue #61:

### PR-A — Web writes; `poll_flags.py` keeps reading as safety net

- Extract `findajob/actions.py` from `poll_flags.py`. `poll_flags.py` imports from the new module; behavior unchanged.
- Add `routes/board_actions.py` with all 11 POST handlers from D4.
- Add the STATUS / REJECT_REASON / notes HTMX cells to `_job_row.html` templates.
- Add the rate-limit / in-flight-count check for prep (D5).
- Tests: unit tests for every `actions.py` function; TestClient tests for every endpoint.
- **`poll_flags.py` keeps reading Sheets.** The Sheet remains a valid write surface during PR-A — safety net in case the web UI has a bug. Both paths call into `findajob.actions`, so behavior is identical.
- **`sync_sheet.py` unchanged in PR-A.** Still reads the Sheet for pending statuses.
- Documentation: new endpoints noted in `CHANGELOG.md` under [Unreleased].

PR-A is deployable on its own: operators get the full web-write experience, with Sheets still working as a fallback.

### PR-B — Pivot to one-way; retire `poll_flags.py`

- Delete `poll_flags.py`; add `watchdog.py`; update `ops/crontab`.
- Delete the three `values().get()` calls in `sync_sheet.py` and the pending-status preservation logic (§sync_sheet.py changes).
- Flip `prep_application.py`'s `--no-sync` default: drop the flag.
- `Ghosted` cleanup (D3).
- Playwright E2E suite (§Testing strategy).
- Documentation: `docs/architecture.md` Sheet-architecture section rewritten; `CLAUDE.md` board sections updated; `CHANGELOG.md` flagged `migration-required` (crontab changes per CLAUDE.md's release-management criteria).

PR-B is the step that closes acceptance criteria 2 and 3.

---

## Testing strategy

### Unit (both PRs)

- `tests/test_actions.py` — one test per `actions.py` function. Exercise:
  - `handle_rejection` writes `feedback_log`, moves folder, writes two `audit_log` rows (stage + reject_reason).
  - `handle_not_selected` does NOT write `feedback_log`, does NOT move folder, writes marker file with safe-reason slug.
  - `handle_waitlist` / `handle_reactivate` folder-move semantics.
  - `notify_waitlist_resurface` fires only when company has waitlisted rows.
- `tests/test_board_actions.py` — FastAPI TestClient per endpoint:
  - Happy path: POST → DB state reflects transition → response is the re-rendered `<tr>`.
  - Idempotency: double-POST is a no-op on the second call (status 200, DB unchanged).
  - Fingerprint not found → 404.
  - Prep dispatch cap: 3rd in-flight job returns 429, DB unchanged.
  - Regenerate when `stage='prep_in_progress'` is a no-op (guard from poll_flags line 268).
  - `notify_waitlist_resurface` Popen call is mocked; assert called on reject/not-selected/withdraw, not on apply/waitlist.

### D9 — E2E (PR-B only)

14b deferred Playwright to 14c explicitly. PR-B adds:

- `pyproject.toml`: `[project.optional-dependencies] dev` gains `playwright` and `pytest-playwright`.
- `tests/e2e/conftest.py`: fixture that spins up the FastAPI app on a random port against a `:memory:` DB or a temp copy of `pipeline.db` fixtures.
- `tests/e2e/test_dashboard_write.py`: click Flag for Prep, assert stage → `prep_in_progress` in DB; click Regenerate, assert folder deleted; click Waitlist, assert folder moved.
- `tests/e2e/test_applied_write.py`: set STATUS=Applied on Dashboard → row appears on Applied tab after sync; set Interviewing → stage=interview; edit notes → DB updated; set Not Selected → marker file exists in `_applied/`.
- `tests/e2e/test_review_write.py`: Promote → row moves to Dashboard. Reject → row moves to Rejected view.
- `tests/e2e/test_waitlist_write.py`: Reactivate → row returns to Dashboard with correct stage.

CI: add a separate job `pytest-e2e` that installs Chromium via `playwright install chromium` and runs the `tests/e2e/` directory. Keep it out of the default `pytest` invocation so developer feedback stays fast.

### End-to-end verification before PR-B merges

1. `docker compose up -d` on `docker.lan` against a copy of real `pipeline.db`.
2. On the operator's workstation, open `http://docker.lan:<port>/board/dashboard`.
3. Walk every action in the D4 matrix against at least one job: Flag for Prep, Regenerate, Waitlist, Reactivate, Apply, Interview, Offer, Withdraw, Not Selected, Reject, Promote. Verify DB state after each.
4. Confirm `sync_sheet.py` still writes the Sheet correctly — Sheet row transitions happen next sync, not instantly.
5. Confirm Sheet writes do NOT affect DB — make a Sheet edit, wait one watchdog cycle, confirm DB unchanged. (Acceptance criterion 3.)
6. Confirm the operator's actual application workflow (Flag for Prep → prep completes → Applied → Interviewing) works end-to-end in the UI for a real job posting.
7. Verify `apply_gate.md` — prep and apply paths still credit the apply-gate in DB (audit_log entries unchanged in shape).

---

## Data flow

```
┌────────────────────────────────────────────────────────────────┐
│  Operator clicks STATUS dropdown on /board/applied              │
└────────────────────────────────┬───────────────────────────────┘
                                 │ HTMX POST
                                 ▼
┌────────────────────────────────────────────────────────────────┐
│  routes/board_actions.py                                        │
│    1. fp → job lookup                                          │
│    2. idempotency guard (job.stage != target)                  │
│    3. call findajob.actions.<fn>(conn, job, ...)               │
│    4. spawn sync_sheet.py (Popen, detached)                    │
│    5. render _job_row for current tab, return <tr>             │
└────────────────────────────────┬───────────────────────────────┘
                                 │ <tr> via HTMX swap
                                 ▼
┌────────────────────────────────────────────────────────────────┐
│  Browser replaces row in-place                                  │
└────────────────────────────────────────────────────────────────┘
```

Prep dispatch adds one layer (`subprocess.Popen(prep_application.py, start_new_session=True)`). The handler returns before prep finishes; prep writes DB and calls `sync_sheet.py` itself on completion.

---

## Error handling

Matches `poll_flags.py` semantics, adapted to HTTP:

- **Fingerprint not found** → 404. HTMX `hx-target` unchanged — no swap.
- **Stage precondition not met** (e.g., Promote on a job whose `stage != 'manual_review'`) → 409, HTMX toast via `HX-Trigger: showToast` header. DB unchanged.
- **Prep cap reached** → 429, toast "3 jobs in prep — try again after one completes." DB unchanged.
- **Subprocess launch failure** (`Popen` raises `OSError`) → 500 with logged error. DB stage rolled back to `scored` in the handler's `except`.
- **DB locked** (SQLite concurrent write) → 503 with retry-after header. Rare but possible if watchdog runs during a web request.
- **`sync_sheet.py` failure** → logged, not fatal. The DB is authoritative; Sheet catches up on the next run (existing `triage_sync_failed` audit pattern — #170).

---

## Documentation Impact

Per CLAUDE.md plan conventions, every doc surface that needs to change is enumerated here. Per-task doc work lives in the companion plan.

- **`CHANGELOG.md`** — [Unreleased] entries:
  - PR-A: "Web UI gains interactive STATUS and REJECT_REASON controls on every board tab. Google Sheet edits still work in parallel."
  - PR-B: "`poll_flags.py` is removed; the web UI is the sole write surface. `sync_sheet.py` no longer reads user edits back from Sheets (one-way DB → Sheet). `migration-required`: crontab updated from `poll_flags.py` to `watchdog.py`."
- **`docs/architecture.md`** — the "Google Sheet Architecture" section needs rewriting after PR-B to drop the STATUS/REJECT_REASON-are-Sheet-write-surface language. The Prep Workflow diagram loses the `reads Dashboard!A2:C10000` step; prep is triggered by `POST /board/jobs/{fp}/prep` instead.
- **`CLAUDE.md`** — "Google Sheet Architecture" subsection: rewrite to describe Sheets as a one-way synced view (not a write surface). Drop STATUS/REJECT_REASON dropdown behaviors for poll_flags. Add a pointer to `/board/*` as the primary UI.
- **`CLAUDE.md`** — "Pipeline Context Table": add `watchdog.py` row; remove `poll_flags.py`.
- **`CLAUDE.md`** — "Critical Architecture Rules": add "Web handlers are the write surface" rule. Drop "Google Sheet Architecture" subrules that reference `poll_flags` reading Sheets.
- **`docs/setup/install-docker.md`** — board pages now have interactive controls. The smoke-test paragraph gets expanded: "click Flag for Prep on a row; confirm the row's STATUS cell updates and stage becomes `prep_in_progress` in the DB."
- **`docs/roadmap.md`** — check off 14c.
- **Docstrings** — `prep_application.py` docstring: remove `--no-sync` reference. `sync_sheet.py` module docstring: rewrite the "reads user edits back" sentence.
- **`scripts/watchdog.py`** — new module docstring.
- **Spec/plan cross-links** — after ship, add `> ARCHIVED` banner to this spec pointing at the merged PRs (matches 14b pattern).

---

## Open questions / risks

- **Watchdog under docker compose restarts.** Today if the container restarts mid-prep, `poll_flags.py`'s 60-min stale-reset catches it on the next scheduled run. `watchdog.py` preserves this. But the watchdog window means 60 min of UI lag between restart and the stale-reset. Not a regression — just worth knowing.
- **Sheet drift during PR-A.** PR-A has two write surfaces (web UI + Sheet). If an operator edits both for the same row in the same 10-min window, poll_flags processes the Sheet edit AFTER the web edit applied. Outcome is deterministic (whatever Sheet says wins) but surprising. Mitigation: ship PR-A and PR-B within a week; operator is advised to stop editing the Sheet once PR-A lands.
- **Concurrency cap accounting.** The cap counts `stage='prep_in_progress'` rows, not running subprocesses. If a subprocess crashes without resetting stage, the cap stays tripped until the 60-min watchdog kicks in. Accept this — it's how `poll_flags.py` behaves today.
- **CSRF later.** When auth lands, POST endpoints need CSRF tokens. Adding them retrofit is mechanical (one Jinja template include + one FastAPI middleware) — not a reason to block 14c.
- **Playwright flakiness.** Playwright E2E in CI can be flaky. Acceptable for a solo project; if it becomes a merge blocker, gate it behind `--e2e` and run manually before release tags.

---

## Related

- Parent arc: #14 — Web frontend phase.
- Dependency: #60 — 14b scaffolding (closed 2026-04-21).
- Follow-up: 14d (#14) — Sheet retirement.
- Load-bearing conventions: `docs/plan-conventions.md`, `docs/project-board.md`, `CLAUDE.md` commit-flow table.
