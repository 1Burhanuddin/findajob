---
**Shipped in #339 on 2026-05-01. Final decisions captured in issue body.**
---

# Plan — #339 Per-tester API key isolation at onboarding

**Spec:** `docs/superpowers/specs/2026-05-01-339-per-tester-api-keys-design.md`
**Issue:** #339 [High] — Per-tester API key isolation: each tester provides own OpenRouter/RapidAPI/Google keys at onboarding
**Branched off:** `origin/main` (per `feedback_git_branch_off_origin`)
**Branch name:** `feat/339-per-tester-api-keys`

---

## Summary

Wire `/onboarding/` into a single collection point for OpenRouter, RapidAPI, and Google API keys. Persist OpenRouter to a per-session credential row so the in-app interview chat (#336) is funded by the tester's own key. Extend the injector to merge RapidAPI and Google into the per-stack `data/.env`. `OPENROUTER_OPERATOR_KEY` keeps its role as a labeled fallback for `findajob-test` and operator-deployed-for-tester scenarios.

---

## Documentation Impact

Documented in the same PRs as the code that creates the need for them. Items:

- **`docs/setup/api-keys.md`** — authored mid-plan against April 2026 provider docs (validated via web search; sources cited at the bottom of the file); referenced from the index page warning bubbles. Final review pass at PR-open time to confirm links remain current.
- **`docs/setup/install-docker.md`** — first-time onboarding section gets a "you'll need three keys before you start" preamble pointing at `api-keys.md`. New "Operating an existing stack" subsection covers operator-side rotation via `sed -i`.
- **`CLAUDE.md`** — Pipeline Context Table notes per-stack key isolation; "Onboarding" section under Web Frontend Architecture mentions the two-step `/onboarding/` flow (keys → interview).
- **`CHANGELOG.md`** — entry under `[Unreleased]` → `Added`. Includes a `### Migration required` bullet that **explicitly notes operator's stack and `findajob-test` need no change** (their `OPENROUTER_OPERATOR_KEY` env-funded path keeps working unmodified; existing tester stacks with the sentinel `data/.onboarding-complete` skip the new collection flow entirely). Migration applies only to net-new tester onboardings.
- **Spec doc** — already exists; will be referenced from each commit message via `docs/superpowers/specs/2026-05-01-339-per-tester-api-keys-design.md`.
- **Issue body** — final session note appended at wrap.

---

## Tasks

### Task 1 — Database schema: extend `onboarding_sessions` with credential columns

**Files:**
- `src/findajob/onboarding/session_store.py` — add three nullable TEXT columns to `_init_schema()`; add `set_credentials()` and `get_credentials()` helpers.
- `tests/test_onboarding_session_store.py` — schema migration test (idempotent) + credential round-trip test.

**Steps:**
1. In `_init_schema()`, after the existing `CREATE TABLE IF NOT EXISTS onboarding_sessions ...`, run a `PRAGMA table_info(onboarding_sessions)` check and `ALTER TABLE ADD COLUMN` for each of `tester_openrouter_key`, `tester_rapidapi_key`, `tester_google_key` (all `TEXT DEFAULT NULL`). Skip when column already exists. This pattern matches the existing schema-init style in the file.
2. Add `set_credentials(conn, session_id, *, openrouter_api_key, rapidapi_key, google_api_key)` — single UPDATE with the three values; blank strings stored as NULL (use `or None` coercion).
3. Add `get_credentials(conn, session_id) -> Credentials | None` returning a small dataclass with the three fields. Returns `None` when the row exists but all three are NULL — caller treats that as "not collected yet."
4. Add `find_credentials_only(conn) -> Session | None` — returns the most recent session that has at least one credential set but no `history` entries. Used by the index page to surface "keys collected, ready to start interview" state.

**Verification:**
- `uv run pytest tests/test_onboarding_session_store.py -v` — new tests pass; existing tests pass unchanged.
- `uv run pytest tests/ -q --no-header --tb=no | tail -5` — full suite still green.

**Commit:** `feat(onboarding): #339 — schema for per-tester credentials in onboarding_sessions`

---

### Task 2 — Smoke check + format validation helpers

**Files:**
- `src/findajob/onboarding/key_validation.py` — new module: `validate_openrouter_format()`, `validate_rapidapi_format()`, `validate_google_format()`. Pure-data functions returning `(bool, error_message)` tuples. No network.
- `src/findajob/onboarding/openrouter_smoke.py` — already exists with `verify_openrouter_key()`; no change.
- `tests/test_onboarding_key_validation.py` — coverage for the three format checks.

**Steps:**
1. `validate_openrouter_format(key)` — non-empty after strip; must start with `sk-or-v1-`. Return `(True, "")` on pass, `(False, message)` with a paste-typo-style hint on fail.
2. `validate_rapidapi_format(key)` — RapidAPI key format has shifted across the platform's history; there is no reliable length range or prefix. Validate only: non-empty after strip + printable ASCII + no whitespace anywhere in the value. This catches the dominant typo class (accidentally pasted a whole `curl -H "X-RapidAPI-Key: ..."` line, embedded newlines from copy/paste) without false-negativing valid enterprise/team keys. Allow blank → `(True, "")` (optional field).
3. `validate_google_format(key)` — non-empty after strip; Google API keys start with `AIza`. Allow blank → `(True, "")` (optional field).
4. All three keep error messages explicit about what was wrong (length, prefix, blank with required) so the index page can render them inline.

**Verification:**
- `uv run pytest tests/test_onboarding_key_validation.py -v`.
- `uv run ruff check src/findajob/onboarding/key_validation.py tests/test_onboarding_key_validation.py`.
- `uv run ruff format --check src/findajob/onboarding/key_validation.py tests/test_onboarding_key_validation.py`.

**Commit:** `feat(onboarding): #339 — format validators for OpenRouter / RapidAPI / Google keys`

---

### Task 3 — Injector extension: merge RapidAPI + Google into `data/.env`

**Files:**
- `src/findajob/onboarding/injector.py` — extend `inject()` signature; extend `env_updates`.
- `tests/test_onboarding_inject.py` — new cases covering optional-blank handling and merge ordering.

**Steps:**
1. Add `rapidapi_key: str = ""` and `google_api_key: str = ""` kwargs to `inject()` after the existing `openrouter_api_key`.
2. In the `env_updates` block (around line 278–280), add the symmetric `if rapidapi_key.strip(): env_updates["RAPIDAPI_KEY"] = rapidapi_key.strip()` and same for Google. **Blank values are not written** — the injector must NOT introduce empty `RAPIDAPI_KEY=` lines, because the `os.environ.get("RAPIDAPI_KEY", "")` paths in `findajob.fetchers` use empty-string truthiness for skip-vs-call routing.
3. Smoke-check call site (`verify_openrouter_key`) is unchanged — only OpenRouter gets a live verify per spec §4.5.
4. Update the docstring on `inject()` to document the two new kwargs and the optional-blank semantics.
5. Test cases:
   - All three keys provided → all three lines in merged env, in `.env.example` order.
   - OpenRouter only (RapidAPI + Google blank) → only `OPENROUTER_API_KEY=...` line; `RAPIDAPI_KEY` and `GOOGLE_API_KEY` stay at their `.env.example` placeholder values.
   - OpenRouter + RapidAPI, no Google → two lines updated, `GOOGLE_API_KEY` stays as placeholder.
   - All blank → no env_updates; merged env equals `.env.example`.

**Verification:**
- `uv run pytest tests/test_onboarding_inject.py -v`.
- Both ruff invocations.

**Commit:** `feat(onboarding): #339 — injector accepts RapidAPI and Google keys`

---

### Task 4 — `POST /onboarding/keys` route + index page form

**Files:**
- `src/findajob/web/routes/onboarding.py` — new POST handler `/onboarding/keys`; index handler reads `find_credentials_only()` to drive affordance state.
- `src/findajob/web/templates/onboarding/_keys_form.html` — new partial: three text inputs + a single submit button + warning bubbles for the optional fields linking to `/docs/setup/api-keys`.
- `src/findajob/web/templates/onboarding/index.html` — restructure into three stacked panels per spec §4.1; `_keys_form.html` is Step 1; existing in-app and paste-back affordances become Step 2 and are disabled (rendered with `disabled`/`aria-disabled` and a "Complete Step 1 first" overlay) until credentials exist.
- `tests/test_onboarding_routes.py` (existing) and `tests/test_onboarding_keys_route.py` (new) — coverage.

**Steps:**
1. New handler `POST /onboarding/keys`:
   - Form fields: `openrouter_api_key` (required), `rapidapi_key` (optional), `google_api_key` (optional).
   - Run all three format validators. **On any failure, re-render the index page with errors inline + preserved typed values, and DO NOT WRITE TO THE DB.** Format/smoke failure must not leave a session row behind.
   - Run `verify_openrouter_key()` on the OpenRouter value. On `OnboardingSmokeCheckFailed`, same: render with error, no DB write.
   - **On success** (all validations passed): call `find_credentials_only(conn)` first. If a credentials-only session already exists, **UPDATE it via `set_credentials()`**; if not, `create_session()` then `set_credentials()`. This prevents orphan-row accumulation when a user paste-typos several times before getting it right and prevents stale earlier-attempt rows from shadowing the corrected credentials in `find_credentials_only()`.
   - Return a 303 redirect to `/onboarding/` (which will now render Step 2 enabled).
2. Index handler updates:
   - In addition to existing `_active_session_for_index` lookup (which finds in-progress chat sessions), call `find_credentials_only()` to detect credentials-collected-but-no-chat-yet state.
   - Pass three booleans into the template: `keys_collected`, `has_in_progress_session`, `operator_funded_available` (`OPENROUTER_OPERATOR_KEY` set).
   - Step 2 is enabled when `keys_collected OR operator_funded_available` is true.
3. Template wiring:
   - `_keys_form.html` renders OpenRouter as required (red asterisk) and the other two with explicit "Optional" labels + warning bubbles linking to `/docs/setup/api-keys`. Form `action="/onboarding/keys"`, `method="post"`.
   - When `keys_collected=True`, render the form in a "keys collected" state: the three values masked as `***last4` with a "Change keys" button that resets the panel.
4. Test coverage:
   - POST with all three valid keys → 303 to `/onboarding/`, exactly one session row exists with credentials.
   - POST with only OpenRouter (blank optionals) → 303 with credentials persisted, blank fields stored as NULL.
   - POST with malformed OpenRouter → 400 with format error rendered, paste preserved, **zero session rows written**.
   - POST with bad OpenRouter that fails live verify → 400 with smoke-check error, **zero session rows written**.
   - **POST twice in a row, both successful with different keys → exactly one session row, with the second submission's values (UPDATE-not-INSERT semantic).**
   - **POST fail → POST fail → POST success → exactly one session row, with the successful submission's values (no orphans from failed attempts).**
   - GET `/onboarding/` after credentials collected → Step 2 affordances enabled in HTML.

**Verification:**
- `uv run pytest tests/test_onboarding_keys_route.py tests/test_onboarding_routes.py -v`.
- Manual smoke: start app locally, GET `/onboarding/`, verify the three-panel layout renders, Step 2 is disabled until Step 1 submits.

**Commit:** `feat(onboarding): #339 — /onboarding/keys collects three keys upfront`

---

### Task 5 — In-app interview reads tester key with operator fallback

**Files:**
- `src/findajob/web/routes/onboarding_interview.py` — replace `_operator_key()` with `_resolved_chat_key(request)`; remove import-time `OPENROUTER_OPERATOR_KEY` registration gate.
- `src/findajob/web/app.py` — registration condition becomes "always register the router; the runtime gate is per-request."
- `tests/test_onboarding_interview_routes.py` — extend existing tests; add new cases.

**Steps:**
1. New helper `_resolved_chat_key(request, session_id) -> str` per spec §4.2 — checks tester's collected key first via `get_credentials()`, falls back to `OPENROUTER_OPERATOR_KEY` env, returns empty string when neither is available.
2. `start_interview` rewires:
   - At the top, call `find_credentials_only()` to find the credentials-only session created by Task 4.
   - If found: call `_resolved_chat_key()` against THAT session's id; on success run the kickoff turn and migrate the session into "active interview" (history attached).
   - If not found AND `OPENROUTER_OPERATOR_KEY` is set: keep existing operator-funded path with a fresh session.
   - If not found AND env var also unset: 503 with actionable error pointing the user to Step 1.
3. `post_turn` and `finalize_interview`: replace `_operator_key()` reads with `_resolved_chat_key(request, session_id)`. Same 503 surface when neither source is available (defensive — should not be reachable if Step 1 succeeded).
4. `finalize_interview` form: when credentials are present, **hide the OpenRouter input entirely** (not just `readonly`) and render a `***last4` masked display + "Change keys" link pointing back to Step 1. Rationale: a `readonly` field still looks editable to many users — they paste a fresh key, click Finalize, and get confused when nothing changed. Hiding the field forces the explicit "Change keys" action. Keep the form-field POST contract (hidden input populated from credentials) so the existing handler code path is untouched. The visible input only renders when no credentials session exists at all (legacy direct-POST safety net).
5. Remove the `app.py` import-time gate at L46–50 and L89–92 — module is always imported.
6. **Update `_active_session_for_index` in `onboarding.py` (currently L42–68).** Today it short-circuits to `None` when `OPENROUTER_OPERATOR_KEY` is unset (L54). After Task 5 lands, that gate is wrong: a self-deploy stack with tester credentials should also surface the resume affordance for in-progress in-app sessions. Replace the env-only gate with the same precedence as `_resolved_chat_key()`: surface the resume affordance when EITHER tester credentials exist (via `find_credentials_only` or `find_active`) OR `OPENROUTER_OPERATOR_KEY` is set. Without this fix, a tester closes the tab mid-interview, comes back, and sees no resume button — has to start the interview over.
7. Test coverage:
   - In-app start with tester credentials, no `OPENROUTER_OPERATOR_KEY` env → succeeds.
   - In-app start with `OPENROUTER_OPERATOR_KEY` env, no tester credentials → succeeds (operator-funded path).
   - In-app start with neither → 503 with link back to `/onboarding/`.
   - Both available → tester key wins (verifies precedence).

**Verification:**
- `uv run pytest tests/test_onboarding_interview_routes.py -v`.
- Both ruff invocations.

**Commit:** `feat(onboarding): #339 — in-app interview funded by tester's own OpenRouter key`

---

### Task 6 — Paste-back form pre-fills from collected credentials

**Files:**
- `src/findajob/web/routes/onboarding.py` — `onboarding_inject` reads credentials from session if no form-supplied value present.
- `src/findajob/web/templates/onboarding/_paste_form.html` — render the OpenRouter input as read-only and pre-filled when credentials exist; render new RapidAPI + Google fields as optional pass-through (typically blank because Step 1 already collected them).

**Steps:**
1. In `onboarding_inject`, before reading form fields directly, look up `find_credentials_only()`. When a credentials session exists, prefer its values over form fields; form fields remain a fallback for the legacy "no Step 1" path (e.g. an external integration test that POSTs to inject directly).
2. Pass collected credentials to `inject()`'s three kwargs.
3. Template change: when credentials present, hide the OpenRouter input entirely and render a `***last4` masked display + "Change keys" link pointing back to Step 1.
4. **"Change keys" semantics:** clicking the link returns the user to Step 1 (form re-rendered editable, pre-filled with the current `***last4` masked values cleared to blank). The user re-submits Step 1 with new values; UPDATE-not-INSERT semantic from Task 4 means the credentials row is mutated in place. **Any in-progress chat session is preserved** — its `history` rows are untouched, and on the next turn `_resolved_chat_key()` reads the new credential value. No chat-history invalidation, no automatic finalization. This is the cleanest seam: credentials and chat are independently mutable.
5. Test:
   - Inject with credentials session present → all three keys flow into env merge.
   - Inject without credentials session, OpenRouter on form → existing behavior preserved.

**Verification:** `uv run pytest tests/test_onboarding_routes.py -v`; both ruff invocations.

**Commit:** `feat(onboarding): #339 — paste-back inject reads credentials from Step 1 session`

---

### Task 7 — Documentation

**Files:**
- `docs/setup/api-keys.md` — already authored in the spec phase. Final pass for tone/links.
- `docs/setup/install-docker.md` — add "you'll need three keys" preamble to first-time-onboarding section; new "Operating an existing stack" subsection for operator-side key rotation.
- `CLAUDE.md` — Pipeline Context Table footnote about per-stack key isolation; `/onboarding/` description updated to mention the two-step flow.
- `CHANGELOG.md` — `[Unreleased] → Added` entry; `### Migration required` subsection listing the net-new tester stack expectations and the in-app affordance now enabling without `OPENROUTER_OPERATOR_KEY`.

**Verification:**
- Read all four files end-to-end after edits.
- `git diff docs/ CLAUDE.md CHANGELOG.md` and verify no PII / hardcoded operator handles.
- `uv run pytest tests/test_transparency_invariants.py` (defensive — confirms onboarding-related disclosure assertions still pass).

**Commit:** `docs(onboarding): #339 — document per-tester key collection and rotation`

---

### Task 8 — Whole-feature verification

This is the gate that confirms #339 actually delivers acceptance criteria 1–4, distinct from the per-task green-tests check.

**Steps:**

1. **Unit + integration suite green:** `uv run pytest tests/ -q --no-header --tb=line | tail -10` — full suite passes including the new tests added across Tasks 1–6. Number of tests should be ≥ baseline of 1444 by an amount equal to the new tests added (target: +20 give or take).
2. **Static checks:** `uv run ruff check && uv run ruff format --check && uv run mypy src/findajob/onboarding/ src/findajob/web/routes/onboarding.py src/findajob/web/routes/onboarding_interview.py`.
3. **Local manual run — fresh-install simulation:**
   - Make a scratch dir, copy `data/.env.example` → `data/.env`, ensure `OPENROUTER_OPERATOR_KEY` is unset in the shell.
   - `uv run uvicorn findajob.web.app:create_app --factory --port 9001` against the scratch instance.
   - GET `/onboarding/` — verify three-panel layout, Step 2 disabled.
   - POST `/onboarding/keys` with a real OpenRouter key + blank RapidAPI + blank Google → verify 303 + Step 2 enables, "LinkedIn/Indeed search inactive" warning bubble visible.
   - Click "Start the interview" → verify the chat opens (kickoff turn returns) and the OpenRouter call was funded by the tester's collected key (check `pipeline.jsonl` event for the model+key path).
   - Cancel out, kill the server.
4. **Local manual run — operator-funded fallback:**
   - Same scratch dir, set `OPENROUTER_OPERATOR_KEY=sk-or-v1-...` in the shell.
   - Run uvicorn the same way.
   - GET `/onboarding/` — Step 2 should be ENABLED even before Step 1 because operator key is present (`operator_funded_available=True`).
   - Submit Step 1 to verify keys still get collected (so RapidAPI/Google land in env).
5. **Inject end-to-end against scratch instance:**
   - Use the existing minimal valid emission fixture from `tests/test_onboarding_interview_integration.py` (or, if that test inlines its emission, extract once into `tests/fixtures/onboarding/minimal_valid_emission.txt` as a Task 8 sub-step and load it both from the integration test and from this verification). Hand-typing 10 `<<<FILE: name>>>` blocks at verification time is exactly the kind of step that gets skipped under time pressure.
   - POST `/onboarding/inject` with the loaded emission and a real OpenRouter key.
   - Verify `data/.env` contains all three keys merged in correct positions; `data/.onboarding-complete` sentinel exists; `.backups/{stamp}/data/.env` exists with the pre-merge content.
6. **No-leak verification (acceptance criterion #2):** grep the resulting `data/.env` for the operator's known key signatures (any `sk-or-v1-...` value other than the test-session value, the operator's `RAPIDAPI_KEY` value if known, etc.) — must return zero matches. Confirm: tester's three values present at the expected positions, no operator key signature anywhere, `your_key_here` placeholders only on lines that this issue does not write to (NTFY_TOPIC, GROQ, XAI, etc.). This is the explicit "no shared/operator keys leak" check; merge ordering alone (step 5) does not prove absence.
7. **Acceptance criteria check:** map each "Done when" criterion in #339 to the verification evidence above; cross off as confirmed.
8. **Operator review** — bring evidence to operator before opening PR.

**Commit:** No new commit — this gate produces a Session note on #339 with the verification log.

---

### Task 9 — First-run NUX redirect from `/`

The `/board/`, `/materials/`, `/stats/` routes are guarded by `require_onboarding_complete` — a request lands on `/onboarding/` when the sentinel is missing. The bare landing route `/` is **not** guarded. A first-time user who points their browser at `https://findajob-{handle}.<operator-domain>/` lands on the marketing-style landing page with no signal that onboarding is the next step. The handoff requirement: a fresh container should dump the user into the (exitable) onboarding flow on first load without them having to know to navigate via `Tools → Onboarding`.

**Files:**
- `src/findajob/web/routes/__init__.py` — extend `_guard` dependency attachment to the landing router include.
- `tests/test_landing_route.py` (existing if present, else new) — coverage.

**Steps:**
1. In `routes/__init__.py`, the existing `_guard = [Depends(require_onboarding_complete)]` is attached to board/materials/stats includes (memory: `findajob.web.app.create_app`). Attach it to the landing include too. The result: GET `/` on a stack with no sentinel → 307 → `/onboarding/`. With sentinel present → landing renders normally.
2. **Exitable property is already preserved** by the existing onboarding page design — once on `/onboarding/`, the user can click any nav link to leave without completing. No changes to the onboarding template needed; this is a one-line guard attachment.
3. The cached `app.state.onboarding_complete` flag (set by `require_onboarding_complete` and the inject handlers) means the redirect fires at most once per process per fresh stack — performance cost is zero after first load.
4. Test coverage:
   - GET `/` with no sentinel → 307 with `Location: /onboarding/`.
   - GET `/` with sentinel present → 200 landing page.
   - After completing onboarding (cached state set), GET `/` → 200 landing page (no redirect loop).

**Verification:**
- `uv run pytest tests/test_landing_route.py -v` (or wherever the landing route is currently tested — find with `grep -rn "/landing\|def test_landing\|landing.html" tests/`).
- Local manual: with no sentinel in scratch stack, browse to `http://localhost:9001/` → expect to land on `/onboarding/` with the three-panel layout; click "Tools" in the nav → leaves onboarding without trapping.

**Commit:** `feat(onboarding): #339 — redirect / to /onboarding/ on first run when sentinel missing`

---

### Task 10 — README once-over

After Tasks 1–9 land and #339 is closed, the project's top-level `README.md` is overdue for a refresh that reflects the new self-deploy story. The two onboarding modalities (in-app interview from #336 + paste-back from #148) and the per-tester API key collection from this issue are the dominant change to a new reader's first impression.

**Files:**
- `README.md` (root of repo).

**Steps:**
1. Read the current README end-to-end. Identify sections that pre-date #336 and #339 and now read as stale (e.g. anything implying the operator hands keys to testers, anything that documents only the paste-back flow, any "what you need to start" list that omits the three-key collection).
2. Rewrite the introduction / "Getting started" section so the first thing a reader sees is:
   - **What findajob is** (one paragraph, unchanged unless stale).
   - **The two onboarding paths.** Lead with the in-app interview (now the primary path on stacks where the tester provides their own keys); paste-back is the secondary path for outbound-blocked deployments or testers who prefer an external LLM. One short paragraph each, with a link to `docs/setup/api-keys.md` for the keys story.
   - **What you'll need.** A short bulleted list naming the three providers + which are required vs. optional, with links to `docs/setup/api-keys.md`.
3. Audit the rest of the README for references to:
   - `OPENROUTER_OPERATOR_KEY` — should be described as the operator-funded fallback, not the only path.
   - "operator pre-seeds keys" / "operator hands keys to testers" framing — replace with self-deploy framing.
   - Any pre-`/onboarding/` setup instructions that ask the user to hand-edit `data/.env` — point at the in-app onboarding instead, with `.env` editing as the rerun-mode escape hatch.
4. Cross-check the README against `docs/setup/install-docker.md` (which Task 7 updated) so the two are coherent — README is the high-altitude pitch; `install-docker.md` is the concrete walk-through.
5. Hold the line on PII / domain-neutrality per `CLAUDE.md` — README is tracked and public.

**Verification:**
- Read the README aloud (or near-aloud) end-to-end as a fresh reader would. Note anything that requires already knowing the project to make sense; rewrite those.
- `git diff README.md` final review for PII slips.
- `uv run pytest tests/test_transparency_invariants.py` (defensive — README is sometimes referenced from disclosure surfaces).

**Commit:** `docs(readme): #339 — refresh getting-started for in-app interview + per-tester keys`

This task is a **separate small PR after #339's main PR merges**, not part of #339's PR. Rationale: keeping #339's PR focused on the wiring/UX/docs that directly satisfy its acceptance criteria, with the README polish as a clean follow-up. File a small follow-up issue at #339 close-time so this doesn't get forgotten.

---

### Task 11 — Documentation comb-through

A wider sweep of the project's documentation surface to deprecate references to the pre-#336 / pre-#339 world and to ensure the new onboarding flow is described accurately. Distinct from Task 10 (which is focused on the README) and from Task 7 (which patches specific files inside #339's PR scope) — this task is the systematic audit pass.

**Scope (files to review):**
- All of `docs/` — `setup/`, `superpowers/` indexes (not the historical specs/plans themselves), any standalone guides like `usage.md`, `troubleshooting.md`, `release-process.md`, `project-board.md`, `plan-conventions.md`, `GENERALIZATION.md`.
- `CLAUDE.md` (project) and any tracked `CLAUDE.md` references — confirm onboarding sections describe both modalities accurately and that the Pipeline Context Table footnotes are current.
- `CHANGELOG.md` — historical entries can stay as they are (history is history); only the `[Unreleased]` section gets touched.
- `docs/personal/dev-playbook.md` is gitignored (per CLAUDE.local) — out of scope.
- Any docstrings on the onboarding modules (`findajob/onboarding/*.py`, `findajob/web/routes/onboarding*.py`) that mention paste-back as the only path.

**Anti-targets (what NOT to touch):**
- Historical spec files in `docs/superpowers/specs/` — those are dated design records. Don't rewrite history.
- Historical plan files in `docs/superpowers/plans/archived/` — same.
- The `[Unreleased]` migration notes added by Task 7 — already current.

**Steps:**
1. Run a search pass for stale terminology:
   - `grep -rn "paste-back" docs/ src/findajob/ CLAUDE.md` — for each hit, confirm the surrounding language describes paste-back as one of two paths, not the only path.
   - `grep -rn "OPENROUTER_OPERATOR_KEY" docs/ src/findajob/` — for each hit, confirm framing as "operator-funded fallback" rather than the gate for the in-app interview.
   - `grep -rni "operator pre-seed\|operator hand\|operator seed" docs/ CLAUDE.md` — for each hit, decide whether the language still applies (operator-deployed-for-tester scenario) or should switch to self-deploy framing.
   - `grep -rn "Tools.*[Oo]nboarding\|/tools/.*onboarding" docs/ src/findajob/` — Tools page no longer has an onboarding link as primary entry (the Task 9 first-run redirect handles that); confirm any references make sense after that change.
2. For each affected file, decide: rewrite (if framing is structurally wrong), augment (if it's accurate but incomplete), or leave (if it's a historical reference). Apply changes.
3. Run a coherence pass — read the result of `docs/setup/install-docker.md` + `docs/setup/api-keys.md` + the updated README (Task 10) end-to-end as one continuous narrative. Note any contradictions or gaps and fix them.
4. Add a line to `docs/GENERALIZATION.md` if any newly-discovered domain-locked content surfaces during the comb-through; otherwise no change.
5. Cross-check no PII slips in any updated tracked file (per `feedback_third_party_pii` and the project's PII rules).

**Verification:**
- `git diff docs/ CLAUDE.md` final read-through for accuracy + PII.
- `uv run pytest tests/test_transparency_invariants.py` (defensive — disclosure surfaces sometimes pull from docs).
- One link-check pass: every internal markdown link resolves to a file that exists; every external URL is reachable (`xargs -n1 curl -ILs --max-time 5 -o /dev/null -w '%{http_code} %{url_effective}\n' < <(grep -rEho "https?://[^)\" ]+" docs/ | sort -u)` or similar).

**Commit:** `docs: #339 — comb-through to align project docs with new onboarding flow`

This is also a **separate small PR after #339's main PR merges**, sequenced after Task 10 (README first, then the wider docs audit). File the same follow-up issue as Task 10 or a sibling at #339 close-time.

---

## Advisor review gate

**Before deciding execution mode (subagent-driven vs. inline), invoke the advisor on this plan.**

Surface the plan to the advisor with explicit framing:

- The spec resolved four open questions; the plan reflects all four.
- `docs/setup/api-keys.md` was authored against April 2026 provider docs (validated via web search; sources cited).
- The injector's "blank-not-written" semantic in Task 3 is load-bearing for backwards compat with `findajob.fetchers`'s skip-vs-call routing.
- Task 5 deliberately keeps the operator-funded path alive for `findajob-test`; this is the architectural seam that lets the operator dogfood without a personal RapidAPI/Google key.
- Tasks 4 and 5 have the largest blast radius (route restructure + import-time gate removal); ask the advisor to confirm the runtime-gate-vs-import-time-gate change in Task 5 is the right shape.

Take the advisor's feedback seriously. If a structural concern surfaces, revise the plan before execution mode is chosen. Reconcile-call the advisor if their feedback contradicts spec evidence.

---

## Execution mode (decided AFTER advisor review)

After advisor sign-off, decide between:

- **Inline (single session, sequential tasks):** preferred when the plan is tight, tasks share strong context, and the operator wants to babysit. Reasonable here given the eight tasks, but the operator may prefer to parallelize.
- **Subagent-driven (per-task subagents):** preferred when tasks are independent and parallelizable. Tasks 1, 2, 3 are independent and could fan out; Tasks 4, 5, 6 have file-level overlap and serialize cleanly behind 1–3.

If subagent-driven: dispatch Tasks 1, 2, 3 in parallel (sonnet for impl per global memory `Subagent model defaults`); review each before serializing 4 → 5 → 6; final 7 + 8 inline.

---

## Self-review checklist

- [ ] Task 1: schema migration is idempotent; existing rows unaffected.
- [ ] Task 2: format validators cover OpenRouter prefix, RapidAPI length range, Google `AIza` prefix; blank tolerated for the two optional fields.
- [ ] Task 3: blank-not-written semantic preserved; merge ordering matches `.env.example`.
- [ ] Task 4: index page Step 2 disabled until credentials OR operator env; `_keys_form.html` partial reusable; warning bubbles link to `/docs/setup/api-keys`.
- [ ] Task 5: `_resolved_chat_key()` precedence is tester > operator > 503; route registration is no longer import-time gated.
- [ ] Task 6: paste-back pre-fills from credentials session; legacy direct-POST path still works.
- [ ] Task 7: `docs/setup/api-keys.md` (already authored) reviewed; `CHANGELOG.md` has `### Migration required` bullet; `CLAUDE.md` table updated.
- [ ] Task 8: full suite green; manual fresh-install simulation passes both with and without `OPENROUTER_OPERATOR_KEY`.
- [ ] Task 9: first-run redirect from `/` to `/onboarding/` lands inside #339's main PR; confirm exitable property in manual smoke.
- [ ] Task 10: follow-up issue filed for the README refresh after #339's main PR merges.
- [ ] Task 11: follow-up issue filed for the documentation comb-through after #339's main PR merges.
- [ ] Acceptance criteria 1–4 from #339 each map to a concrete task or verification step.
- [ ] No PII or hardcoded operator handles in any tracked diff.
- [ ] Branch was cut from `origin/main`, not local `main`.
- [ ] Apply gate observed (or "TPS Report" used) before substantive code work began.
- [ ] Advisor reviewed plan before execution mode chosen.
