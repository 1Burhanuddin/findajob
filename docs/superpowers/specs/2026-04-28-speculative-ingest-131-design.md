# Speculative Company Briefing + Candidate-Tailored Role Synth — Design

Issue: [#131](https://github.com/brockamer/findajob/issues/131)
Date: 2026-04-28
Status: Approved (pending operator review of this doc)

---

## Overview

Submit a company name through the web `/ingest/` form's new **Speculative** mode. The pipeline runs a candidate-led Perplexity Deep Research pass, then synthesizes 1–5 role profiles aligned to the candidate's strengths and the company's apparent hiring posture. After an operator review-and-approve gate, each kept role becomes a `[SPEC]`-prefixed `jobs` row in `stage='scored'` with `source='web_speculative'` and `synthetic=1`. The operator can then flag-for-prep through the existing dashboard, generating a cover letter and outreach draft framed for cold submission. Sending the outreach transitions the row to `applied` (gate-counting) with the button labeled "Sent Outreach" instead of "Applied." Synthetic rows are excluded from `feedback_log` writes and from the scorer's feedback loader on read.

This is the cold-outreach path for companies the operator wants to reach but that aren't currently posting a matching opening.

---

## Decisions Adopted

These are the brainstorming outcomes — settled, not open.

| # | Decision | Reasoning (short) |
|---|---|---|
| 1 | **Apply-gate counting via row attributes (Option D)**: speculative rows reuse the `applied` stage; distinction lives in `synthetic=1` + `source='web_speculative'`; button label flips per-row | Smallest schema/surface delta; gate query unchanged; reject machinery inherits correct behavior via the `synthetic` flag |
| 2 | **No dedup (Option D3)**: every submission re-researches | Operator preference; simplifies B2/B3; can revisit if cost becomes a concern |
| 3 | **Soft-warn rate limit (Option R2)**: form shows "you've already submitted N today" but does not block | Operator preference; trust over hard gates; cost-vs-clicks tradeoff stays visible |
| 4 | **Speculative requests live in their own table (Option P1)**: new `speculative_requests` table holds all pre-approval state; `jobs` rows only get written on Approve | Eliminates leak risk that a `pending_synthesis=1` flag forgotten in any query would cause; clean lifecycle separation |
| 5 | **`candidate_led_briefing` uses Perplexity Deep Research** (`openrouter:perplexity/sonar-deep-research`) | Best grounding for the no-JD speculative case; ~$0.25–$0.75 per submission acceptable cost for the quality gain |
| 6 | **Submission flow is async**: form POST writes a `speculative_requests` row, kicks a detached subprocess, returns a status page; status page polls until research completes; review page is reached from there | 1–5 min latency on Deep Research means synchronous request-response is unviable; mirrors the existing `prep_application.py` detached-subprocess + sentinel pattern |
| 7 | **Aging/decay for unused speculative rows: defer to follow-up** | Out of scope today; if it becomes a problem, a future ticket adds 30d-no-stage-change → `waitlisted` |
| 8 | **Self-evaluation / confidence flag in briefing: defer to follow-up** | Out of scope today; if hallucination rate is bad in the field, future role-prompt revision adds it |
| 9 | **CLI entry point: not built in this round** | Web form is the only entry; CLI is a later ergonomics improvement |
| 10 | **No new auth / perimeter unchanged** | Wireguard-only access pattern that the rest of the app already lives behind |

---

## Architecture

### Data Model

#### New table: `speculative_requests`

```sql
CREATE TABLE speculative_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company TEXT NOT NULL,
    hint TEXT,                                  -- optional operator hint, e.g. "data center team"
    personal_notes TEXT,                        -- optional connection / context notes
    status TEXT NOT NULL DEFAULT 'researching', -- researching | ready_for_review | approved | trashed | failed
    error_message TEXT,                         -- populated when status='failed'
    briefing_md TEXT,                           -- full markdown briefing from candidate_led_briefing
    role_cards_json TEXT,                       -- JSON array of role cards from speculative_roles_synth
    briefing_folder TEXT,                       -- companies/{Company}_SPECULATIVE_{date}_{HHMMSS}/ (set after research completes)
    submitted_at TEXT NOT NULL DEFAULT (datetime('now')),
    research_completed_at TEXT,
    approved_at TEXT,
    approved_role_count INTEGER,                -- count of role cards the operator kept on approve
    briefing_prompt_version TEXT,               -- e.g. "candidate_led_briefing@v1"
    synth_prompt_version TEXT                   -- e.g. "speculative_roles_synth@v1"
);

CREATE INDEX idx_speculative_status ON speculative_requests(status);
CREATE INDEX idx_speculative_company_submitted ON speculative_requests(company, submitted_at);
```

#### `jobs` table — additive migration

```sql
ALTER TABLE jobs ADD COLUMN synthetic INTEGER NOT NULL DEFAULT 0;
-- existing source column already covers source='web_speculative'
-- existing stage column reused (no new enum value)
```

The `synthetic=1` flag is the canonical row-level signal for "this is a speculative row." Used by:
- `findajob.actions.handle_rejection` and `handle_not_selected` — skip `feedback_log` write when `synthetic=1`
- `findajob.scoring` feedback loader — exclude `WHERE synthetic=1` from training feedback retrieval
- Dashboard render — `[SPEC]` badge styling and "Sent Outreach" button label flip
- Future stats — split metrics by `synthetic` cohort

### Pipeline Components

```
+----------------+      +--------------------+      +----------------------+
|  /ingest/      | POST | speculative_       | spawn| scripts/             |
|  Speculative   |----->| requests row       |----->| run_speculative_     |
|  form mode     |      | (status=researching)     | research.py          |
+----------------+      +--------------------+      | (detached)           |
        |                       |                   +----------------------+
        |                       |                              |
        |                       |                              | calls aichat-ng
        |                       |                              v
        |                       |                   +----------------------+
        |                       |                   | candidate_led_       |
        |                       |                   | briefing role        |
        |                       |                   | (sonar-deep-research)|
        |                       |                   +----------------------+
        |                       |                              |
        |                       |                              v
        |                       |                   +----------------------+
        |                       |                   | speculative_roles_   |
        |                       |                   | synth role           |
        |                       |                   | (claude sonnet)      |
        |                       |                   +----------------------+
        |                       |                              |
        |                       v                              v
        |              +--------------------+      +----------------------+
        |              | status_polling     |<-----| update row:          |
        |              | page (HTMX poll)   |      |   briefing_md,       |
        |              +--------------------+      |   role_cards_json,   |
        |                       |                  |   status='ready_for_ |
        |                       |                  |   review'            |
        |                       v                  +----------------------+
        |              +--------------------+
        |              | /speculative/      |
        |              | review/{id}        |
        |              | (briefing +        |
        |              |  role cards +      |
        |              |  keep/drop +       |
        |              |  regenerate +      |
        |              |  trash + approve)  |
        |              +--------------------+
        |                       |
        |                       v Approve
        |              +--------------------+
        |              | write 1 jobs row   |
        |              | per kept role with |
        |              | synthetic=1,       |
        |              | source='web_       |
        |              | speculative',      |
        |              | [SPEC] prefix,     |
        |              | stage='scored'     |
        |              +--------------------+
        |                       |
        |                       v
        |              +--------------------+
        |              | Dashboard /board/  |
        |              | renders [SPEC]     |
        |              | rows with badge    |
        |              | + speculative-     |
        |              | aware button       |
        |              | labels             |
        |              +--------------------+
```

### File Layout

New files:

```
src/findajob/speculative/
    __init__.py
    runner.py            # async runner: orchestrates briefing + roles_synth, updates speculative_requests row
    parser.py            # parses LLM output into validated role-card dicts
    approver.py          # given speculative_request_id + kept_role_indices, writes jobs rows + briefing folder
    storage.py           # creates {Company}_SPECULATIVE_{date}_{HHMMSS}/ folders + briefing.md write

src/findajob/web/routes/
    speculative.py       # GET/POST /ingest/speculative; GET /speculative/status/{id}; GET/POST /speculative/review/{id}; POST /speculative/approve/{id}; POST /speculative/trash/{id}; POST /speculative/regenerate/{id}

src/findajob/web/templates/speculative/
    status.html          # async status page with HTMX polling
    review.html          # review-and-approve page

scripts/
    run_speculative_research.py  # entry point — invoked as detached subprocess from POST /ingest/speculative

config/roles/
    candidate_led_briefing.md
    speculative_roles_synth.md

tests/
    test_speculative_runner.py
    test_speculative_parser.py
    test_speculative_approver.py
    test_speculative_routes.py
    test_synthetic_guards.py     # the correctness-critical feedback_log + scorer skip tests
```

Modified files:

```
src/findajob/web/routes/ingest.py        # add Speculative mode toggle to existing form
src/findajob/web/templates/ingest/
    form.html                             # add mode toggle + speculative fieldset
src/findajob/actions.py                   # handle_rejection, handle_not_selected: synthetic guard
src/findajob/scoring.py                   # feedback loader: WHERE synthetic=0
src/findajob/web/routes/board.py          # button-label flip on speculative applied-stage rows
src/findajob/web/templates/board/_job_row.html  # render [SPEC] badge + speculative-aware action button
src/findajob/web/routes/board_actions.py  # POST /board/jobs/{fp}/sent-outreach (alias to apply, but for synthetic rows; or reuse /apply with detection — see below)
config/roles/cover_letter_writer.md       # speculative-aware variant block; controlled via prompt-template branching at prep time
config/roles/outreach_drafter.md          # same — speculative-aware variant
scripts/prep_application.py               # detect synthetic=1 jobs and feed the speculative variant into cover-letter and outreach
src/findajob/utils.py                     # one-line helper: is_synthetic_job(job_dict) for clarity at call sites
docs/CLAUDE.md                            # Pipeline Context Table row; new section in "Web is the Write Surface"; synthetic-jobs convention
docs/CHANGELOG.md                         # [Unreleased] entry
docs/usage.md                             # speculative submission walkthrough
```

### "Sent Outreach" vs "Applied" — Concrete Mechanics

Per Decision 1, both buttons hit the same handler and both result in `stage='applied'`. The differentiation is purely in render:

- Real row (`synthetic=0`): button text "Applied", endpoint `POST /board/jobs/{fp}/apply`
- Speculative row (`synthetic=1`): button text "Sent Outreach", endpoint `POST /board/jobs/{fp}/sent-outreach` (thin alias that calls the same internal `findajob.actions.handle_apply` helper but writes a distinct `audit_log.changed_by='outreach_button'` for traceability)

Both endpoints emit identical `stage` audit_log entries (`old_value=materials_drafted, new_value=applied`), so the apply-gate query stays a single-predicate query against `field_changed='stage' AND new_value='applied'`. The `changed_by` column lets stats slice "applied via ATS" vs "applied via cold outreach" without changing the gate logic.

### Async Submission Pattern (Mirrors `prep_application.py`)

1. `POST /ingest/speculative` validates inputs, INSERTs a `speculative_requests` row with `status='researching'`, spawns `scripts/run_speculative_research.py {request_id}` as a detached subprocess (same pattern as `POST /board/jobs/{fp}/prep`), and returns `303 → /speculative/status/{request_id}`.
2. The runner script:
   - Reads the request row + `candidate_context/profile.md` + `candidate_context/master_resume.md`
   - Calls `aichat-ng -r candidate_led_briefing` with the company + hint + candidate context
   - Calls `aichat-ng -r speculative_roles_synth` with the briefing + candidate context
   - Writes the briefing folder + `briefing.md` to disk
   - Updates the request row: `briefing_md`, `role_cards_json`, `briefing_folder`, `status='ready_for_review'`, `research_completed_at`
   - On any failure: sets `status='failed'` + `error_message`, emits `speculative_research_failed` to `pipeline.jsonl`
3. `/speculative/status/{id}` polls every 5s via HTMX. When `status='ready_for_review'`, it auto-redirects to `/speculative/review/{id}`. When `status='failed'`, it shows the error inline with retry options.

### Review Page Behavior

- Renders the briefing markdown
- Renders each role card in `role_cards_json` as a self-contained block with a `[ Keep ]` / `[ Drop ]` toggle (default: Keep)
- Three actions at the bottom:
  - **Approve** → posts to `POST /speculative/approve/{id}` with the list of kept role indices; the approver module writes one `jobs` row per kept card, sets `status='approved'`, redirects to dashboard
  - **Regenerate** → posts to `POST /speculative/regenerate/{id}` with optional updated hint; resets status to `researching` and re-runs the runner; previous briefing/roles are overwritten in place (audit_log records the regeneration)
  - **Trash** → posts to `POST /speculative/trash/{id}`; sets `status='trashed'`; no `jobs` rows are ever written; redirects to `/ingest/`

### Speculative-Aware Cover Letter and Outreach

`scripts/prep_application.py` detects `synthetic=1` and routes to a variant of the prompt:

- **Cover letter (synthetic=1):** opens with the speculative framing — "I noticed Nebius is growing rapidly across four sites; I'm reaching out because here's why I'd be a fit even without an open role." Uses the `[role description]` from the synthesized card as the implicit JD.
- **Outreach (synthetic=1):** explicitly framed as cold outreach to a recruiter or target-team leader. The role card's `suggested_contact_type` (recruiter / hiring manager / senior IC) drives the salutation and length register.

Both variants share the role file but inject a `{{speculative_mode}}` boolean into the system prompt; the role file branches on it. This keeps prompt-version churn low.

### Guardrails (Correctness-Critical)

These are the tests that must exist before B1 can land:

1. `handle_rejection(job)` skips `feedback_log` write when `job.synthetic=1` — unit test asserts `feedback_log` row count unchanged after rejecting a synthetic job, while non-synthetic still writes.
2. `handle_not_selected(job)` skips `feedback_log` write when `job.synthetic=1` — same shape.
3. Scorer feedback loader (`findajob.scoring.load_feedback_log`) excludes `WHERE synthetic=1` rows. Test seeds 1 synthetic + 1 non-synthetic feedback row, asserts only non-synthetic is returned.
4. `synthetic` defaults to `0` on existing rows after migration — assert via fresh-DB migration test.

### Async Subprocess Failure Modes

| Mode | Detection | Recovery |
|---|---|---|
| `aichat-ng` returns non-zero exit | runner catches subprocess error | sets `status='failed'`, `error_message=<stderr tail>`, status page surfaces "Research failed: \<msg\>. [ Retry ] [ Trash ]" |
| `candidate_led_briefing` succeeds but `speculative_roles_synth` fails | runner partial — briefing already written to row | sets `status='failed'` with note that briefing is preserved; retry runs only the synth step (cheap) |
| Subprocess killed (oom, container restart) | row stays in `status='researching'` indefinitely | watchdog (`scripts/watchdog.py`) gets a new branch: `speculative_requests` with `status='researching'` for >10min → set `status='failed'`, `error_message='research timed out or was interrupted'` |
| User regenerates while research still in flight | route checks `status` before re-spawning | refuse with 409 + status-page redirect |

---

## Phasing & PR Breakdown

To stay shippable today and respect the project's plan-conventions, work splits into four mergeable PRs. Each PR is independently green-CI-able and behind no feature flags (the speculative form mode is the natural progressive disclosure — until B3 ships, the toggle isn't visible).

| Phase | Scope | Why this slice | PR |
|---|---|---|---|
| **B1 — Foundation + Guardrails** | `synthetic` column migration on `jobs`; `speculative_requests` table; `is_synthetic_job` helper; `handle_rejection` / `handle_not_selected` skip `feedback_log` when `synthetic=1`; scorer feedback loader excludes synthetic; unit tests for all four guards | Lands the correctness-critical guards first. After this PR merges, even if every other phase shipped half-broken, no synthetic row could ever pollute scorer feedback. Defense-in-depth at the foundation. | PR #1 |
| **B2 — Synthesis Pipeline** | `candidate_led_briefing` and `speculative_roles_synth` role .md files; `src/findajob/speculative/{runner,parser,approver,storage}.py`; `scripts/run_speculative_research.py` async entry; integration test that runner writes correct row state with mocked aichat-ng outputs | The pipeline that produces speculative content. Headless-runnable for testing. No web form yet — synthesis can be invoked manually via `python scripts/run_speculative_research.py <id>` against a hand-INSERTed `speculative_requests` row. | PR #2 |
| **B3 — Web Form + Status + Review + Approve** | `/ingest/` mode toggle; speculative form fields; status page with HTMX polling; review page with role-card keep/drop UI; Approve writes `jobs` rows; Regenerate re-spawns runner; Trash; soft-warn rate limit on submit | Operator UX. Delivers the intended user-facing workflow. After this merges, the operator can submit PSIquantum + ai& through the form. | PR #3 |
| **B4 — Speculative-Aware Prep + Sent-Outreach Button + Docs** | Cover-letter prompt variant for synthetic; outreach-drafter prompt variant for synthetic; `prep_application.py` routes synthetic rows to variants; "Sent Outreach" button label + `POST /board/jobs/{fp}/sent-outreach` alias handler; CLAUDE.md updates; CHANGELOG.md updates; `docs/usage.md` walkthrough; watchdog branch for stuck `researching` requests | Closing-the-loop work. After B4 merges, the synthesized rows can produce well-framed outreach material and the apply-gate counts the cold-email correctly. | PR #4 |

PRs B1→B4 are sequenced — each builds on the prior. B1 has no dependencies; B2 depends on B1's `synthetic` column; B3 depends on B2's runner; B4 depends on B3's row-creation path. **B1 carries the `migration-required` label** (it adds the `synthetic` column to `jobs` and creates the `speculative_requests` table — both deploy-time migrations on the bind-mounted DB). B2, B3, and B4 do not need the label — no schema, config, crontab, mount, or compose-down changes after B1.

---

## Documentation Impact

| Surface | Change | When (which phase) |
|---|---|---|
| `CLAUDE.md` Pipeline Context Table | Add `candidate_led_briefing` row (sonar-deep-research, async, 1–5 min latency) and `speculative_roles_synth` row (claude sonnet) | B2 |
| `CLAUDE.md` "Web is the Write Surface" section | Add the new endpoints (`POST /ingest/speculative`, `GET /speculative/status/{id}`, `GET /speculative/review/{id}`, `POST /speculative/{approve,regenerate,trash}/{id}`, `POST /board/jobs/{fp}/sent-outreach`); note the new detached-subprocess pattern (`run_speculative_research.py`) alongside `prep_application.py` and `interview_prep.py` | B3, B4 |
| `CLAUDE.md` "Hard Rejects are Code" / new "Synthetic Jobs Convention" section | Document: (1) `synthetic=1` invariants — never written to `feedback_log`, never read by scorer feedback loader, never sheet-synced; (2) `[SPEC]` title prefix is render-time decoration, not data; (3) `source='web_speculative'`; (4) `applied` stage is reused with row-attribute distinction | B1 (intro stub), B4 (full section) |
| `CLAUDE.md` "Output Folder Format" | Add the speculative variant: `{Company}_SPECULATIVE_{YYYY-MM-DD}_{HHMMSS}/briefing.md` | B2 |
| `CHANGELOG.md` `[Unreleased]` | One entry per PR with the conventional-commits prefix; B1 entry calls out `migration-required` | B1, B2, B3, B4 |
| `docs/usage.md` | New section: "Submitting a speculative company" — walkthrough of form → status → review → approve → flag-for-prep → send outreach | B4 |
| `docs/setup/` | No changes; no new env vars; no new bind mounts; no new secrets | n/a |
| Spec doc (this file) | Marked Status: Implemented at end of B4 with PR links | B4 |
| `config/paths.env.example` | No changes | n/a |
| Role file docstrings (`config/roles/candidate_led_briefing.md`, `config/roles/speculative_roles_synth.md`) | Each role file ships with its own front-matter / decision log per project convention | B2 |

---

## Testing Strategy

### Whole-feature verification gate

Distinct from per-task tests. After B4 merges, this is the green-light check:

1. Submit "PSIquantum" through `/ingest/speculative` with hint "advanced computing infrastructure"
2. Verify status page renders, polls, eventually redirects to review
3. Verify briefing has at least 3 distinct sections including a "likely role surfaces" section
4. Verify 1–5 role cards render
5. Approve all kept cards
6. Verify `jobs` rows appear on dashboard with `[SPEC]` prefix and distinct row styling
7. Flag one for prep; wait for completion; verify cover letter has the speculative framing language ("I noticed... I'd be a fit even without an open role")
8. Click "Sent Outreach" on the prepared row
9. Verify `audit_log` shows `field_changed='stage', new_value='applied', changed_by='outreach_button'`
10. Verify apply-gate query (`SELECT COUNT(*) FROM audit_log WHERE field_changed='stage' AND new_value='applied' AND changed_at >= today_PT`) includes this row
11. Reject a different speculative row with reason "Fit Mismatch"
12. Verify `feedback_log` has zero new rows for that fingerprint (synthetic=1 guard fired)
13. Run scorer in REPL; verify the rejected speculative row is not in the feedback context

### Per-PR tests

- **B1 (4 unit tests):** synthetic guard on `handle_rejection`; on `handle_not_selected`; scorer feedback loader exclusion; migration default.
- **B2 (3 tests):** runner integration with mocked aichat-ng (asserts row state transitions); parser handles edge-case role counts (0, 1, 5, 6 → cap at 5); approver writes correct number of `jobs` rows.
- **B3 (4 tests):** form POST creates request row + spawns subprocess (mocked); status page renders status correctly; review page renders briefing + role cards; approve writes jobs rows + redirects; trash sets status without writing rows.
- **B4 (3 tests):** cover-letter variant injection (prompt template renders the speculative block when `synthetic=1`); outreach-drafter variant; `POST /board/jobs/{fp}/sent-outreach` writes the correct audit_log row with `changed_by='outreach_button'` and the expected stage transition.

---

## Self-Review Checklist (Maps Spec Sections → Implementing Tasks)

| Spec section | Implementing PR | Implementing task(s) within PR |
|---|---|---|
| Decision 1 (apply-gate via row attributes) | B4 | "Sent Outreach" button + alias endpoint |
| Decision 2 (no dedup) | (no implementation needed — absence) | n/a |
| Decision 3 (soft-warn rate limit) | B3 | Form pre-render queries today's submission count, renders inline warning |
| Decision 4 (speculative_requests table) | B1 | Schema migration |
| Decision 5 (Deep Research) | B2 | Role file `candidate_led_briefing.md` model field |
| Decision 6 (async submission) | B3 (form), B2 (runner) | Detached subprocess pattern from `prep_application.py` |
| Decision 7 (aging defer) | (no implementation) | future ticket |
| Decision 8 (confidence-flag defer) | (no implementation) | future ticket |
| Decision 9 (CLI defer) | (no implementation) | future ticket |
| Decision 10 (no new auth) | (no implementation — by absence) | n/a |
| Data model: speculative_requests | B1 | Schema migration |
| Data model: jobs.synthetic | B1 | Schema migration |
| `handle_rejection` synthetic guard | B1 | Code change + unit test |
| `handle_not_selected` synthetic guard | B1 | Code change + unit test |
| Scorer feedback loader synthetic guard | B1 | Code change + unit test |
| candidate_led_briefing role | B2 | Role file |
| speculative_roles_synth role | B2 | Role file |
| Speculative runner | B2 | `src/findajob/speculative/runner.py` + script entry |
| Briefing folder layout | B2 | `src/findajob/speculative/storage.py` |
| Approver | B2 | `src/findajob/speculative/approver.py` |
| Form mode toggle | B3 | `routes/ingest.py` + `templates/ingest/form.html` |
| Status page (HTMX poll) | B3 | `routes/speculative.py` + `templates/speculative/status.html` |
| Review page | B3 | `routes/speculative.py` + `templates/speculative/review.html` |
| Approve / Regenerate / Trash actions | B3 | `routes/speculative.py` |
| Soft-warn rate limit | B3 | Form pre-render query |
| Cover-letter variant | B4 | `config/roles/cover_letter_writer.md` template branch + `prep_application.py` invocation |
| Outreach variant | B4 | Same shape as cover letter |
| "Sent Outreach" button | B4 | `templates/board/_job_row.html` + `routes/board_actions.py` alias endpoint |
| Watchdog branch for stuck speculative requests | B4 | `scripts/watchdog.py` extension |
| CLAUDE.md updates | B1 (stub) + B4 (full) | Inline in same commits as the code |
| CHANGELOG.md updates | Each PR | Conventional-commits entry |
| `docs/usage.md` walkthrough | B4 | New section |

---

## Open Items (from ticket — explicitly resolved or deferred)

| Ticket open question | Resolution |
|---|---|
| Apply-gate counting mechanism | Decision 1 — Option D — row-attribute distinction, alias endpoint with `changed_by='outreach_button'` |
| Aging / decay | Decision 7 — defer; if becomes a problem, future ticket auto-expires `synthetic=1` rows to `waitlisted` after 30d no stage change |
| De-dup window | Decision 2 — defer; no dedup in this implementation |
| Self-evaluation confidence flag | Decision 8 — defer |
| CLI entry point | Decision 9 — defer |

All five ticket open questions are now closed for this implementation.

---

## Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Deep Research costs spiral if operator power-uses the form | Medium | Medium | Soft-warn at submit-time (Decision 3); cost dashboard #87 will surface aggregate spend |
| Subprocess hangs without sentinel cleanup | Low | Medium | Watchdog branch (B4) auto-fails `researching` rows older than 10 min |
| Speculative row leaks into scorer training | Critical if it happens | High | Two independent guards (B1): write-time skip in `handle_rejection`, read-time exclusion in feedback loader. Both unit-tested |
| LLM hallucinates a fake role and operator approves it without noticing | Medium | Medium (a single bad outreach email) | Review-and-approve gate is mandatory (B3); operator literally clicks Keep on each card |
| `[SPEC]` prefix gets stripped in some downstream rendering and operator confuses speculative with real | Low | Medium | Two-layer defense: (a) approver writes `[SPEC] ` literally into `jobs.title` so the prefix flows through every existing render path that reads `title` (sheet sync, ntfy, dashboard, materials viewer titles); (b) dashboard render *additionally* shows a synthetic-keyed badge / row-color rule, so even if the prefix were stripped the visual differentiation persists. Both layers, not either-or. |
| Async subprocess fails silently (no row update, no log) | Low | High | Runner has top-level try/except that always writes `status='failed'` + `error_message` + emits `speculative_research_failed` to pipeline.jsonl; watchdog catches the silent-hang case |
