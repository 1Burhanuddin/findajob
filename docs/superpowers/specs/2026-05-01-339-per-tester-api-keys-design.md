# Per-tester API key isolation at onboarding — Design Spec

## Issue(s)
- #339 — Per-tester API key isolation: each tester provides own OpenRouter / RapidAPI / Google keys at onboarding

**Date:** 2026-05-01
**Status:** Drafted; ready for operator review before plan authorship
**Related work:**
- #336 (in-app onboarding interview) — code-complete; tester rollout gated on this issue
- #390 (rewrite onboarding interview prompt for in-app context) — paired blocker; orthogonal to this issue (prompt content vs. route/UX wiring)
- #148 (paste-back onboarding) — original key-collection path; current behavior is the floor we generalize from
- #239 (credentials hygiene — plaintext-to-encrypted) — composes with this issue, not blocked by it
- #338 (parent epic — multi-tenancy + per-tester scaling)

---

## 1. Context

Today, every findajob tester stack on `docker.lan` (`findajob-alice`, `findajob-papa`, `findajob-dave`, `findajob-judy`, `findajob-tango`) runs with the **operator's** API keys baked into the per-stack `data/.env`:

- `OPENROUTER_API_KEY` — funds 10 of 11 pipeline LLM roles plus the in-app interview (#336)
- `RAPIDAPI_KEY` — funds jobs-api14 (LinkedIn + Indeed) ingestion
- `GOOGLE_API_KEY` — funds Gemini embeddings for the RAG index

This was the pragmatic choice for trial deployments: testers don't have to procure keys before they can see the pipeline run, and the operator is happy to fund Phase-3 NUX validation. It does not survive scaling beyond a handful of trusted testers:

- **Billing/security boundary leak** — every tester's container env carries the operator's keys. A subverted tester stack (lost laptop, shared credential, malicious extension) compromises the operator's wallet directly.
- **Rate-limit interference** — RapidAPI's free-tier monthly quota is shared across all stacks. One tester's aggressive triage cadence drains capacity for the operator and other testers without visibility.
- **Tester churn cost** — when a tester churns, the operator can't cleanly free that stack's allocation; everything is on the operator's bill until the operator manually rotates and redeploys.
- **Self-deploy NUX is structurally impossible.** A net-new tester who clones the image and stands up their own stack today gets an unstartable pipeline because there is no path for them to insert their own keys without operator hand-holding.

The deliverable is the wiring that lets a fresh stack accept its own credentials at onboarding and persist them only to that stack's `data/.env`. The operator's stack and the dogfood stack (`findajob-test`, #389) keep operator-funded behavior as a labeled, env-gated fallback.

This issue is the **second of two blockers** before #336 ships to testers. Its peer is #390 (rewrite the role prompt for in-app context). The two are orthogonal: this issue changes route handlers, templates, and persistence. #390 changes prompt content. They can land independently and in either order; the prompt's per-LLM key-collection language at L391–475 will be deleted by #390 regardless of how this issue resolves.

## 2. Objectives

| Role | Metric | Treatment |
|---|---|---|
| **Primary objective** | A net-new tester can onboard end-to-end with only their own API keys | Index page collects all three keys; injector merges into per-stack `data/.env` |
| **Hard floor — operator-funded path coexists** | `findajob-test` + operator-deployed-for-tester scenarios still work | `OPENROUTER_OPERATOR_KEY` env var stays as labeled fallback for the in-app interview chat |
| **Hard floor — no key leakage across stacks** | Per-stack `data/.env` carries only that tester's keys | Injector writes scoped to the tester's stack; operator's keys never appear in tester env unless operator-funded mode is explicitly enabled on that stack |
| **Hard floor — fail-closed on bad keys** | Pipeline cannot enter a "scheduled triage with broken keys" state | OpenRouter smoke-check at collection (already exists for paste-back); RapidAPI + Google validated for format-presence at collection, live-tested on first scheduled use with structured error logs |
| **Soft floor — backwards compat** | Existing tester stacks (alice/papa/dave/judy/tango) keep running unchanged | Sentinel `data/.onboarding-complete` already skips the onboarding guard; this issue's changes affect net-new onboardings only. Migration of existing stacks to per-tester keys is separately scoped |
| **Generalization gate** | Diff of tracked files | Zero hardcoded tester keys, no operator-specific defaults; `data/.env.example` remains the canonical seed |

The "operator-funded path coexists" floor matters because `findajob-test` (#389) is the operator's dogfood instance for #336 walkthroughs. It must be able to run the in-app interview without the operator manually procuring a tester key for every dogfood pass. The env-var fallback (`OPENROUTER_OPERATOR_KEY`) is the architectural seam that lets that scenario keep working.

## 3. Scope

### 3.1 In scope

- **Onboarding index page (`/onboarding/`)** gains a key-collection form. The form collects all three keys before either interview path becomes available.
- **In-app interview routes (`onboarding_interview.py`)** stop reading `OPENROUTER_OPERATOR_KEY` directly for chat. They read the tester's collected key from session storage; fall back to `OPENROUTER_OPERATOR_KEY` only when no tester key was supplied AND the env var is set.
- **Paste-back inject (`onboarding.py`)** continues collecting OpenRouter at finalize for paste-back's UX, but additionally accepts RapidAPI + Google keys (collected on the same form for both paths).
- **Injector (`findajob/onboarding/injector.py`)** extends `env_updates` to write `RAPIDAPI_KEY` and `GOOGLE_API_KEY` alongside the existing `OPENROUTER_API_KEY`.
- **Session store (`findajob/onboarding/session_store.py`)** gains optional credential fields so the in-app path can persist keys across tab-close-resume without re-prompting.
- **Smoke checks** — extend the existing `verify_openrouter_key()` pattern with `verify_rapidapi_key()` and `verify_google_api_key()`. Live calls deferred to first use; format-presence validation runs at collection.
- **Templates** — new partial `_keys_form.html` shared by the index page (in-app entry) and the paste-back form.
- **Tests** — unit coverage for injector env-merge with the two new keys, route handler coverage for the new collection POST, and an integration test extending `tests/test_onboarding_interview_integration.py` to confirm in-app start succeeds with tester-supplied OpenRouter and zero operator key.
- **Documentation** — `docs/setup/install-docker.md` first-time-onboarding section gains the "you'll need three keys" preamble; `CLAUDE.md` Pipeline Context Table notes per-stack key isolation; `CHANGELOG.md` entry under `[Unreleased]` → `Added` with a `### Migration required` bullet for net-new tester stack expectations.

### 3.2 Out of scope

- **Migration of existing tester stacks** (alice/papa/dave/judy/tango) from operator-funded to self-funded keys. Separate operational task; scoped only when at least one tester is ready to procure their own keys.
- **At-rest encryption of `data/.env`.** That's #239's territory. Plaintext-on-disk is the floor this issue ships against; the same plaintext model the pipeline already uses.
- **Key rotation UX** (let a tester replace their OpenRouter key without re-onboarding). Out of scope; rerun mode (`?mode=rerun`) is the existing escape hatch.
- **GUI for the operator to provision keys on a tester's behalf.** The CLI / `sed -i` workflow stays the operator's tool when wanted.
- **Per-key billing dashboards / usage views.** Operator dashboard (#333) is the home for that signal if it ever lands; #339 only closes the leak.
- **Splitting OpenRouter into separate keys per role** (e.g. dedicated key for embeddings). One key per provider; same model the pipeline uses today.
- **Smoke-checking RapidAPI / Google with real network calls at collection time.** Format-presence validation only — RapidAPI's free-tier rate-limits are tight enough that adding a smoke call to every onboarding would compete with the user's own quota. First scheduled-triage failure is the live-test moment; logged + ntfy'd, not silently swallowed.

## 4. Architecture

### 4.1 Collection point: the index page

`/onboarding/` index becomes the canonical collection point for all three keys. The page's flow becomes:

1. **Welcome banner** (existing) — backup warning when `?mode=rerun`, otherwise none.
2. **NEW: API keys form.** Three text inputs (`openrouter_api_key`, `rapidapi_key`, `google_api_key`) with help links to each provider's key page. Submit posts to `POST /onboarding/keys`.
3. **Resume affordance** (existing) — rendered when a session exists.
4. **In-app interview affordance** (existing button "Start the interview") — disabled until keys are collected (`/onboarding/keys` returns 200) AND either a tester OpenRouter key is on file OR `OPENROUTER_OPERATOR_KEY` is set.
5. **Paste-back affordance** (existing form) — pre-fills the OpenRouter field from collected state, no longer requires re-entry.

The new POST handler `/onboarding/keys`:
- Validates format-presence (non-empty after strip; OpenRouter must start with `sk-or-v1-`).
- Runs the existing `verify_openrouter_key()` smoke check on OpenRouter.
- On success, writes the three keys to a new "collected_credentials" row in the session_store (or, if no session exists yet, to a fresh credentials-only session).
- Returns the index page rendered with affordances enabled and keys masked (input value rendered as `***last4`).

This single collection point eliminates the asymmetry between paste-back (collects at finalize) and in-app (relies on env). Both paths now read collected keys from the same storage at inject time.

### 4.2 Operator-funded fallback semantics

`OPENROUTER_OPERATOR_KEY` env var keeps its existing role for the **chat-runner side** of the in-app interview but loses its gate-control role for **route registration**. Concretely:

| Scenario | `OPENROUTER_OPERATOR_KEY` set? | Tester collected own OR key? | In-app interview chat funded by |
|---|---|---|---|
| Net-new self-deploy (target audience for this issue) | unset | yes | tester's collected key |
| `findajob-test` dogfood / operator-deployed-for-tester | set | optional | tester's collected key if present, else operator's env key |
| Existing tester stacks (alice/papa/...) | unset | no (sentinel skips guard) | n/a — onboarding doesn't run |

`onboarding_interview.py` `_operator_key()` becomes a fallback resolver:

```python
def _resolved_chat_key(request: Request, session_id: str) -> str:
    """Return the OpenRouter key for chat-runner calls, in precedence order:
    1. The tester's own key collected at /onboarding/keys.
    2. The operator-funded env var (OPENROUTER_OPERATOR_KEY) when set.
    3. Empty — caller must surface a 503 / actionable error.
    """
    ...
```

Route registration loses its `OPENROUTER_OPERATOR_KEY`-only gate. The new gate is "either a collected-credentials row exists for some session OR `OPENROUTER_OPERATOR_KEY` is set" — checked at request time, not import time, so the in-app affordance enables as soon as the tester completes the keys form even on a stack with no operator env var.

### 4.3 Persistence: session_store extension

`onboarding_sessions` table gains three nullable columns:

```sql
ALTER TABLE onboarding_sessions ADD COLUMN tester_openrouter_key TEXT DEFAULT NULL;
ALTER TABLE onboarding_sessions ADD COLUMN tester_rapidapi_key TEXT DEFAULT NULL;
ALTER TABLE onboarding_sessions ADD COLUMN tester_google_key TEXT DEFAULT NULL;
```

Migration shipped via the existing `findajob.onboarding.session_store` schema-init (idempotent `CREATE TABLE IF NOT EXISTS` + `PRAGMA table_info` driven `ALTER TABLE`). No standalone migration script — the table is pure ephemeral session state, not pipeline source-of-truth.

Storage lifecycle:
- **Written** when `/onboarding/keys` POST succeeds.
- **Read** by `start_interview`, `post_turn`, `finalize_interview` (in-app) and `onboarding_inject` (paste-back) at execution time.
- **Cleared** when the session is `mark_complete`d (after successful inject) or 7 days after `last_turn_at` via session cleanup. Plaintext-on-disk model is unchanged from `data/.env`; no special handling.

A session that holds collected credentials but has no `history` rows yet is the "collected keys, hasn't started chat" state. The index page treats `find_active()` differently for these — it shows the keys-collected affordance, not a resume affordance.

### 4.4 Injector extension

`findajob/onboarding/injector.py` `inject()` signature:

```python
def inject(
    base_root: Path,
    captured: dict[str, str],
    *,
    openrouter_api_key: str = "",
    rapidapi_key: str = "",         # NEW
    google_api_key: str = "",       # NEW
    skip_smoke_check: bool = False,
) -> InjectResult:
```

`env_updates` populates analogously:

```python
if rapidapi_key.strip():
    env_updates["RAPIDAPI_KEY"] = rapidapi_key.strip()
if google_api_key.strip():
    env_updates["GOOGLE_API_KEY"] = google_api_key.strip()
```

`merge_env_content()` stays unchanged — it already handles arbitrary keys against the `.env.example` template. The two new keys are already in `data/.env.example` (line 10 + line 15), so the merge produces correct ordering.

### 4.5 Smoke checks

OpenRouter: existing `verify_openrouter_key()` continues to gate inject. Runs at `/onboarding/keys` POST and again at finalize/inject; second call is cheap (1-token completion is bounded) and catches the "key was rotated between collection and inject" edge case.

RapidAPI + Google: format-presence only at collection. First scheduled use surfaces failures. The `findajob.fetchers` paths already log `jobsapi_error` / equivalent on failed RapidAPI calls; we extend that path with one structured `pipeline.jsonl` event (`onboarding_rapidapi_smoke_failed` / `onboarding_google_smoke_failed`) emitted on the first scheduled triage that fails because of a key, so the operator dashboard (#333) and the existing notify-issues alert (Mon/Wed/Fri 08:00) surface the breakage.

Rationale for not live-testing at collection: jobs-api14's BASIC free tier is 150 requests/month (~5/day). A live test at every onboarding burns one. Multiplied across the projected NUX wave (5 testers + churn + rerun mode + dev iteration), that's a meaningful slice of a quota that should belong to the pipeline. Format-presence validation catches the dominant bug class (paste-typo, copied wrong key) without quota cost.

### 4.6 Cross-cutting: paste-back form

Paste-back's existing form at `templates/onboarding/_paste_form.html` retains its OpenRouter input but the input is now pre-filled from collected credentials when the index page renders post-keys-collection. RapidAPI and Google fields are added to paste-back's form too — symmetric with in-app, so a tester who picks paste-back doesn't have to backtrack to the keys form.

If the user collected keys via `/onboarding/keys` first, the paste-back form's OpenRouter input is read-only with a "Change keys" link to clear and re-enter.

## 5. Failure modes and recovery

| Failure | Surface | Recovery |
|---|---|---|
| Tester pastes invalid OpenRouter format | `/onboarding/keys` 400 with format hint | Re-paste; index page preserves other two key inputs |
| OpenRouter live verify fails at collection | `/onboarding/keys` 400 with `OnboardingSmokeCheckFailed.user_message` | Same as paste-back finalize today |
| RapidAPI / Google key wrong but format-valid | First scheduled triage fails; `pipeline.jsonl` event + ntfy | Tester reruns onboarding (`?mode=rerun`) and fixes the bad key |
| Tab-close after keys collected, before chat starts | Session in DB with credentials but no history | Index page shows "keys collected — start interview" affordance, not a resume affordance |
| `OPENROUTER_OPERATOR_KEY` set AND tester collects own key | Tester's key wins | No surface — both paths funded by tester key, env key inert for that session |
| Smoke check passes at collection, key rotated before finalize | `OnboardingSmokeCheckFailed` at inject time | Existing paste-back recovery: error rendered, paste content preserved, re-finalize after re-pasting key |

## 6. Migration story

This issue ships **for net-new onboardings only**. Existing tester stacks have `data/.onboarding-complete` and skip the onboarding guard entirely.

Operator-driven migration of an existing stack to per-tester keys, when wanted, is a documented operational sequence:

1. `ssh docker.lan && sudo docker compose -f /opt/stacks/findajob-{handle}/compose.yaml stop`
2. Operator coordinates with the tester to procure their own keys.
3. `sudo sed -i 's|^OPENROUTER_API_KEY=.*|OPENROUTER_API_KEY=...|' /opt/stacks/findajob-{handle}/state/data/.env` (and same for `RAPIDAPI_KEY` / `GOOGLE_API_KEY`).
4. `sudo docker compose -f .../compose.yaml up -d`.

Alternative: tester opens the stack URL with `?mode=rerun`, fills the new keys form, the injector backs up + overwrites `data/.env`. Less server-side fiddling, but a destructive UI path that re-fires the injector — operator should expect to verify nothing valuable was lost.

Documenting both is `docs/setup/install-docker.md` work in this issue's `Documentation Impact` section.

## 7. Generalization

No domain-locked content introduced. All three keys have generic provider names, validation logic is format-shape only (OpenRouter prefix), and `data/.env.example` already lists them. Fields render as plain text inputs; no field-specific copy.

`docs/GENERALIZATION.md` does not need a new entry — this is a multi-tenancy fix, not a domain-vocabulary fix.

## 8. Resolved decisions

The following were resolved in the design discussion before plan authorship:

1. **RapidAPI key is optional.** Field renders alongside OpenRouter and Google but accepts blank input. When blank, `RAPIDAPI_KEY` is omitted from `data/.env` (not set to empty string), so the existing `os.environ.get("RAPIDAPI_KEY", "")` paths in `findajob.fetchers` log their existing `RAPIDAPI_KEY not set in .env` skip-message and the pipeline runs with Greenhouse/Ashby/Lever + Gmail-imap as the active ingestion sources. UI surfaces a warning ("LinkedIn/Indeed search will be inactive until you add this key") and links to the new tester docs page (see resolution #2).
2. **Google API key is optional.** Same shape as RapidAPI: blank-tolerant, no env write when blank, warning + doc link in UI. Pipeline runs identically for the daily triage cycle; only the optional RAG rebuild (Sun 03:00 PT, REPL-only consumer) is inert without it. New tester-facing documentation page authored at `docs/setup/api-keys.md` walks through both providers' sign-up flows; the form's warning bubble links to that page.
3. **OpenRouter live smoke check stays at collection.** The existing `verify_openrouter_key()` 1-token completion (~$0.000003) is a strong fail-fast signal; collection-time re-use catches paste-typos before the user invests in the interview.
4. **Visual layout: stepwise panels.** Index page renders three panels in order: "Step 1: API keys" (the new keys form), "Step 2: Pick how you want to onboard" (in-app interview button + paste-back form, both disabled until Step 1 succeeds), and the existing rerun-mode banner above all of them when applicable.

The two RapidAPI-quota and Google-AI-Studio-procurement details validated against current April 2026 documentation: jobs-api14 BASIC tier provides 150 requests/month free with no credit card; Google AI Studio API keys are free to create with no Google Cloud or billing setup required. Both flows + cost expectations are documented in `docs/setup/api-keys.md`, which the in-app warning bubbles link to.

## 9. Acceptance criteria mapping

| #339 "Done when" | Spec section that covers it |
|---|---|
| 1. Onboarding flow (#336) collects each tester's own OpenRouter, RapidAPI, and Google API keys | §4.1 Collection point |
| 2. Per-stack `data/.env` carries only that tester's credentials; no shared/operator keys leak | §4.4 Injector extension; §6 Migration story |
| 3. Operator's stack remains the only one with operator's credentials | §4.2 Operator-funded fallback semantics; §3.2 Migration of existing stacks out of scope |
| 4. Documented in onboarding guide | §3.1 documentation work; §6 Migration story |
