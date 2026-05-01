# #336 In-app Onboarding Interview — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace (and supplement) the paste-back onboarding flow with an in-app multi-turn LLM chat. Non-technical testers complete onboarding without leaving findajob's UI: no tab-switching, no copy-paste discipline, no out-of-band prompt delivery from operator. Paste-back stays as the escape hatch.

**Architecture:**
- New `findajob.onboarding.interview_runner` orchestrates multi-turn OpenRouter chat-completions calls (extends the urllib pattern from `openrouter_smoke.py`).
- New `findajob.onboarding.session_store` wraps a new `onboarding_sessions` SQLite table (idempotent ALTER via `init_db.py`).
- New routes under `findajob.web.routes.onboarding_interview` — start / turn / resume / finalize.
- New templates: `onboarding/interview.html` (full-page chat UI) + `onboarding/_turn.html` (HTMX swap-in partial).
- Operator-funded inference via `OPENROUTER_OPERATOR_KEY` env var. Distinct from the per-tester key collected at finalize.
- Existing `parse_emission` + `inject` reused verbatim for finalize → write files + sentinel.
- Paste-back path preserved on `/onboarding/` index — both options rendered.

**Tech stack:** Python 3.13, FastAPI APIRouter, Jinja2, urllib (stdlib), sqlite3, pytest, HTMX 2, Tailwind utility classes.

**Spec:** Issue #336 body (acceptance criteria + decisions).

---

## Goal + scope

The current onboarding flow (#148 + #328) requires the user to:
1. Open another tab to claude.ai / ChatGPT / their preferred LLM
2. Paste a long prompt
3. Run a 20–40 minute back-and-forth interview
4. Copy the LLM's emission
5. Come back to findajob and paste

This produced two real frictions during the alice + papa NUX walkthroughs (operator's observation): out-of-band prompt delivery from operator → tester is messy and error-prone, and copy-paste discipline + LLM-quality self-supervision are real cliffs for non-technical testers.

This plan ships an embedded chat UI that runs the full interview in-app, captures the same `<<<FILE: name>>>` blocks the existing parser already understands, and hands off to the existing injector for the actual file writes. **No protocol change to the emission format.**

**In scope:**
- `findajob.onboarding.interview_runner` — multi-turn LLM call with full-history submission per turn.
- `findajob.onboarding.session_store` — server-side persistence of conversation history + captured emission blocks.
- `onboarding_sessions` SQLite table — schema migration in `init_db.py`.
- Four new routes: `POST /onboarding/interview/start`, `POST /onboarding/interview/turn`, `GET /onboarding/interview/{session_id}`, `POST /onboarding/interview/{session_id}/finalize`.
- Two new templates: `onboarding/interview.html` + `onboarding/_turn.html`.
- `OPENROUTER_OPERATOR_KEY` env var — operator-funded inference. Absent → in-app fallback to paste-back only.
- Per-turn emission detection: scan assistant turn for `<<<FILE: name>>>...<<<END FILE: name>>>` blocks, accumulate on session row.
- Finalize affordance: surfaces only when all `ALLOWED_FILENAMES` captured. Triggers existing inject path with the user's own OpenRouter key (collected at finalize, same form as today).
- Error UX: 401 / 402 / 429 / 5xx mid-interview render appropriate messages in chat UI, log to `pipeline.jsonl`.
- Paste-back path preserved — `/onboarding/` index renders both "Run interview here" (in-app, when operator key set) AND "I already ran it elsewhere" (existing paste form, always).
- Tests: unit tests with mocked OpenRouter, multi-turn happy path, tab-close-resume, emission accumulation across turns, four error paths, integration test (start → turn → finalize → inject → sentinel).
- Documentation: `docs/setup/configure.md` (`OPENROUTER_OPERATOR_KEY` env var + cost), `CLAUDE.md` onboarding section, `docs/usage.md` (tester-facing description).

**Out of scope** (file as follow-ups if needed):
- SSE / token streaming. v1 is HTMX swap-on-response.
- Multiple model choices. Pin Sonnet 4.6.
- Voice input / TTS.
- Editing prior turns mid-interview. User can revise via a normal turn ("let me revise that"); no UI for retroactive edits.
- Per-tester operator-key budgets / spend caps. Belongs to a separate cost-hardening ticket.
- Changing the emission protocol. The 826-line `config/roles/onboarding_interviewer.md` is the same system prompt; the LLM emits the same `<<<FILE: name>>>` blocks; the parser is unchanged.

---

## Task 1: Schema migration — `onboarding_sessions` table

**Files:**
- Modify: `scripts/init_db.py` (idempotent ALTER pattern)
- Create: `tests/test_onboarding_sessions_schema.py`

**Steps:**
- [ ] Add `CREATE TABLE IF NOT EXISTS onboarding_sessions (...)` to `init_db.py` with columns:
  - `id` TEXT PRIMARY KEY (UUID4)
  - `history_json` TEXT NOT NULL — serialized list of `{"role":"user|assistant", "content":"..."}` turns
  - `captured_blocks_json` TEXT NOT NULL DEFAULT '{}' — `{filename: body}` map of emission blocks parsed so far
  - `started_at` TEXT NOT NULL — ISO UTC
  - `last_turn_at` TEXT NOT NULL — ISO UTC, updated on every turn
  - `completed_at` TEXT — ISO UTC, set on finalize success
  - `error_state` TEXT — last error message if any (rendered to user on resume)
- [ ] Test: schema is created idempotently; running init_db twice doesn't error.
- [ ] **Verification:** `uv run pytest tests/test_onboarding_sessions_schema.py -v`
- [ ] **Commit:** `feat(onboarding): #336 add onboarding_sessions table for in-app interview persistence`

## Task 2: `findajob.onboarding.session_store` — CRUD wrapper

**Files:**
- Create: `src/findajob/onboarding/session_store.py`
- Create: `tests/test_onboarding_session_store.py`

**Steps:**
- [ ] Functions: `create_session(db) -> str` (returns session_id), `get_session(db, session_id) -> Session | None`, `append_turn(db, session_id, role, content)`, `update_captured_blocks(db, session_id, blocks)`, `mark_complete(db, session_id)`, `set_error(db, session_id, message)`.
- [ ] `Session` dataclass: id, history (list[dict]), captured_blocks (dict[str,str]), started_at, last_turn_at, completed_at, error_state.
- [ ] All writes commit; reads return frozen dataclasses.
- [ ] **Verification:** `uv run pytest tests/test_onboarding_session_store.py -v`
- [ ] **Commit:** `feat(onboarding): #336 session_store CRUD for onboarding_sessions`

## Task 3: `findajob.onboarding.interview_runner` — multi-turn LLM client

**Files:**
- Create: `src/findajob/onboarding/interview_runner.py`
- Create: `tests/test_onboarding_interview_runner.py`

**Steps:**
- [ ] Module-level constants: `INTERVIEW_MODEL = "anthropic/claude-sonnet-4-6"`, `INTERVIEW_TIMEOUT_S = 120`, `INTERVIEW_MAX_TOKENS = 4096`.
- [ ] Function `run_turn(operator_key, system_prompt, history, user_message) -> tuple[str, dict]`: appends user turn to history, posts to OpenRouter chat-completions with full history + system prompt, returns `(assistant_text, usage_dict)`.
- [ ] Reuses the urllib + error-handling pattern from `openrouter_smoke.py`. Each error mode (401, 402, 429, 5xx, network) returns a friendly message via a dedicated `InterviewRunnerError` exception, never raises generic.
- [ ] Tests: mock `urllib.request.urlopen`. Assert the request payload includes the full message history. Assert each error path raises with the expected user-message.
- [ ] **Verification:** `uv run pytest tests/test_onboarding_interview_runner.py -v`
- [ ] **Commit:** `feat(onboarding): #336 interview_runner — multi-turn OpenRouter chat-completions client`

## Task 4: Routes — `findajob.web.routes.onboarding_interview`

**Files:**
- Create: `src/findajob/web/routes/onboarding_interview.py`
- Create: `tests/test_web_onboarding_interview_routes.py`
- Modify: `src/findajob/web/app.py` (register router conditionally on `OPENROUTER_OPERATOR_KEY` presence)

**Steps:**
- [ ] `POST /onboarding/interview/start` — creates a session, calls `run_turn` with the system prompt + an empty history + a synthetic "begin the interview" user kickoff (mirrors the existing role's expected first turn). Returns the assistant's first turn rendered via `_turn.html`.
- [ ] `POST /onboarding/interview/turn` — accepts `{session_id, message}`, calls `run_turn`, persists the new turn pair, scans the assistant message for emission blocks via `parse_emission`, accumulates onto the session, returns the assistant turn partial.
- [ ] `GET /onboarding/interview/{session_id}` — resume: render the full chat UI seeded with the persisted history.
- [ ] `POST /onboarding/interview/{session_id}/finalize` — accepts `{openrouter_api_key}`, validates all `ALLOWED_FILENAMES` are in `captured_blocks`, calls `inject(...)` (existing) with the user's key + the captured blocks, marks session complete, redirects to `/onboarding/complete.html`.
- [ ] If `OPENROUTER_OPERATOR_KEY` is unset → router not registered (issue acceptance #6).
- [ ] **Verification:** `uv run pytest tests/test_web_onboarding_interview_routes.py -v`
- [ ] **Commit:** `feat(onboarding): #336 in-app interview routes (start/turn/resume/finalize)`

## Task 5: Templates — `onboarding/interview.html` + `onboarding/_turn.html`

**Files:**
- Create: `src/findajob/web/templates/onboarding/interview.html`
- Create: `src/findajob/web/templates/onboarding/_turn.html`
- Modify: `src/findajob/web/templates/onboarding/index.html` (add "Run interview here" affordance when operator-key flag set)
- Create: `tests/test_web_onboarding_interview_render.py`

**Steps:**
- [ ] `interview.html`: full-page layout with message-list `<div id="messages">`, user-input form, HTMX-posts to `/onboarding/interview/turn` with `hx-target="#messages" hx-swap="beforeend"`. Finalize block (hidden until `captured_count == required_count`) — single-input OpenRouter API key + Finalize button.
- [ ] `_turn.html`: single message bubble, role-styled (user vs assistant). Uses Tailwind utility classes consistent with `index.html`'s palette.
- [ ] `index.html` update: when `operator_mode_interview_enabled` Jinja global is True, render two affordances side-by-side — "Run interview here" (link to start) and "I already ran the interview elsewhere" (existing paste form). When False, only paste form (current behavior).
- [ ] **Verification:** `uv run pytest tests/test_web_onboarding_interview_render.py -v`
- [ ] **Commit:** `feat(onboarding): #336 chat UI templates + interview entry point on /onboarding/`

## Task 6: Emission detection state machine

**Files:**
- Modify: `src/findajob/onboarding/interview_runner.py` (or new `findajob.onboarding.emission_tracker`)
- Modify: `src/findajob/web/routes/onboarding_interview.py`
- Create/extend: `tests/test_onboarding_interview_runner.py`

**Steps:**
- [ ] After every assistant turn, run `parse_emission(turn_text)` over the cumulative assistant transcript (concatenated assistant turns, not just last one — LLMs sometimes split blocks across turns).
- [ ] Update `captured_blocks` on the session row with whatever was parsed.
- [ ] Surface `captured_count / total_required` in the rendered `_turn.html` (small badge / progress hint).
- [ ] Finalize affordance unhides only when `len(captured_blocks) == len(ALLOWED_FILENAMES)`.
- [ ] Test: multi-turn emission where blocks arrive across two assistant turns; tracker captures both correctly.
- [ ] **Verification:** `uv run pytest tests/test_onboarding_interview_runner.py -v`
- [ ] **Commit:** `feat(onboarding): #336 emission detection across multi-turn assistant transcript`

## Task 7: Error UX — 401 / 402 / 429 / 5xx / network

**Files:**
- Modify: `src/findajob/web/routes/onboarding_interview.py`
- Create: `src/findajob/web/templates/onboarding/_turn_error.html`
- Modify: `tests/test_web_onboarding_interview_routes.py`

**Steps:**
- [ ] On `InterviewRunnerError`, render `_turn_error.html` partial with the runner's user-message + "Try Again" button (HTMX-posts the same turn).
- [ ] 429: include automatic-retry hint with countdown (10s).
- [ ] 401 / 402: surface OpenRouter dashboard link (operator's responsibility, not tester's — different message vs the per-tester smoke check at finalize).
- [ ] All errors logged via `log_event("onboarding_interview_error", session_id=..., error_class=..., status=...)`.
- [ ] Tests cover all four shapes.
- [ ] **Verification:** `uv run pytest tests/test_web_onboarding_interview_routes.py::TestErrorHandling -v`
- [ ] **Commit:** `feat(onboarding): #336 actionable error UI for OpenRouter failures mid-interview`

## Task 8: Tab-close-resume

**Files:**
- Modify: `src/findajob/web/templates/onboarding/index.html` (resume affordance)
- Create/extend: `tests/test_web_onboarding_interview_routes.py`

**Steps:**
- [ ] Index page detects an in-progress session for this stack via `session_store.find_active(db) -> Session | None` (returns most recent un-completed session, < 24h old).
- [ ] When found, render a "Resume your interview (last activity X minutes ago)" affordance linking to `/onboarding/interview/{session_id}`.
- [ ] Test: start session → close client → re-load index → see resume affordance → follow link → see full history.
- [ ] **Verification:** `uv run pytest tests/test_web_onboarding_interview_routes.py::TestResume -v`
- [ ] **Commit:** `feat(onboarding): #336 tab-close-resume — surface in-progress session on index`

## Task 9: Integration test — full interview → finalize → inject → sentinel

**Files:**
- Create: `tests/test_onboarding_interview_integration.py`

**Steps:**
- [ ] End-to-end test using `TestClient` + a mocked `urllib.request.urlopen` that scripts a canned multi-turn response sequence (LLM emits each required block across several turns).
- [ ] Assert: finalize call writes all 10 required files via `inject`, sentinel is created, `captured_blocks` matches `ALLOWED_FILENAMES`.
- [ ] **Verification:** `uv run pytest tests/test_onboarding_interview_integration.py -v`
- [ ] **Commit:** `test(onboarding): #336 integration test — start → turn × N → finalize → inject`

## Task 10: Documentation

**Files:**
- Modify: `docs/setup/configure.md` (add `OPENROUTER_OPERATOR_KEY` section: how to set, what it costs, what happens if unset)
- Modify: `CLAUDE.md` (Onboarding section: describe both paths, when each is used)
- Modify: `docs/usage.md` (if present — tester-facing description of in-app interview)
- Modify: `CHANGELOG.md` (Unreleased section, including a `### Migration required` bullet for operators wanting to opt their stacks in)

**Steps:**
- [ ] `configure.md`: env-var spec + cost ballpark (~$1 per onboarding for Sonnet 4.6 × ~30k tokens out) + opt-in instructions per stack.
- [ ] `CLAUDE.md`: brief two-line description of the new path; reference to plan + spec for deeper context.
- [ ] `CHANGELOG.md` Unreleased: feature description + migration note ("set `OPENROUTER_OPERATOR_KEY` in stack `.env` to enable the in-app path; absent leaves the existing paste-back path untouched").
- [ ] **Commit:** `docs(onboarding): #336 document in-app interview opt-in + cost`

## Task 11: Whole-feature verification gate

**Steps (run before merging the final task's PR):**
- [ ] `uv run pytest -x` — full suite green
- [ ] `uv run ruff check . && uv run ruff format --check .` — clean
- [ ] `uv run mypy src/` — clean
- [ ] On a fresh tmp BASE: complete a full in-app interview against a real OpenRouter key (operator's), verify the resulting files match what paste-back would have produced
- [ ] On the same tmp BASE: complete the paste-back path, verify the existing flow is unchanged
- [ ] On a fresh tmp BASE: start interview, close tab, re-open `/onboarding/`, confirm resume affordance appears and history loads
- [ ] On a fresh tmp BASE with `OPENROUTER_OPERATOR_KEY` unset: confirm `/onboarding/interview/start` returns 404 and `/onboarding/` shows only the paste form
- [ ] Confirm cost: a single test interview burns ~$1 of operator credit per a real OpenRouter dashboard read

---

## Documentation Impact

| Surface | Change |
|---|---|
| `docs/setup/configure.md` | Add `OPENROUTER_OPERATOR_KEY` env var section (Task 10) |
| `CLAUDE.md` | Onboarding architecture: both in-app and paste-back paths exist (Task 10) |
| `CLAUDE.md` "Pipeline Context Table" | Add row for in-app interview model (anthropic/claude-sonnet-4-6) |
| `docs/usage.md` | Tester-facing description of the new path (Task 10) |
| `CHANGELOG.md` | Unreleased section + `### Migration required` bullet — `OPENROUTER_OPERATOR_KEY` opt-in for operators (Task 10) |
| `docs/superpowers/specs/` | None — issue body is the spec; this plan is the implementation plan |
| Docstrings | New module docstrings on `interview_runner`, `session_store`, `onboarding_interview` route module |

---

## Self-review checklist — every issue acceptance criterion mapped to a task

| # | Criterion | Implementing task |
|---|---|---|
| 1 | `interview_runner.run_turn(...)` exists | Task 3 |
| 2 | Routes start/turn/resume/finalize | Task 4 |
| 3 | `onboarding_sessions` SQLite table | Task 1 |
| 4 | `interview.html` + per-turn partial | Task 5 |
| 5 | Emission-detection state machine | Task 6 |
| 6 | OpenRouter calls via `OPENROUTER_OPERATOR_KEY` | Task 3 + Task 4 |
| 7 | Unset operator key → in-app unavailable, paste-back still works | Task 4 (conditional router registration) |
| 8 | Error handling: network / 429 / 401 / 5xx | Task 7 |
| 9 | Paste-back path stays functional | Task 5 (index.html update preserves it) |
| 10 | Tests: multi-turn, resume, emission detection, errors, integration | Tasks 3, 4, 6, 7, 8, 9 |
| 11 | Docs: configure.md, CLAUDE.md, usage.md | Task 10 |

---

## Risks + open questions

- **Cost runaway:** a tester goes off-script, asks the LLM to write them a novel, burns $5 of operator credit. Mitigation: per-stack budget caps are out of scope (separate ticket). Operator can monitor via OpenRouter dashboard. If observed in practice, file a follow-up.
- **Conversation length:** an interview is ~30k tokens of context. Sonnet 4.6's 200k context handles this comfortably. If we ever hit a ceiling, we'd need history compression — out of scope for v1.
- **Concurrent sessions per tester:** acceptance criteria don't specify. Default behavior: each `start` creates a fresh session_id; resume affordance picks "most recent active." If tester opens two tabs, they'll see two separate interviews — unusual case, won't break, just inefficient. Don't engineer for it in v1.
- **Open question:** does the existing onboarding interview prompt (`config/roles/onboarding_interviewer.md`, 826 lines) need any edits for multi-turn use? The prompt is already designed for back-and-forth. Read carefully during Task 3 — if it has any single-shot assumptions, file them as scope amendments.
