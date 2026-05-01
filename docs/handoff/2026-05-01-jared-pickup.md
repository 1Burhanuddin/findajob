# Jared session-handoff — 2026-05-01

Pick up from the structural review. Use this doc + `docs/roadmap.md` Decision 19 + Epic #338 Session note as the cold-pickup briefing.

## Where the board is right now

- **Active milestone: General Availability.** Due 2026-05-12. Scope-tightened today from 10 → 5 issues.
- **Milestones renamed** (no more `v0.9 / v1.1 / v1.4 / v1.2 / v1.3` prefixes).
- **Status flow:** canonical jared 5-column model — `Backlog → Up Next → In Progress → Blocked → Done` — Priority + Milestone govern *what* to pull next; column position governs *flow*.
- **Apply gate today: 1/3 PT.** Every operating session checks `audit_log` for the day's `stage→applied` transitions before pulling new Medium/Low scope.

## What needs to ship to close GA

Five open issues in the milestone, ordered by what to pick up first:

### 1. #345 — Discoverer role-anchor regex doesn't match onboarding profile.md schema  ★ Real bug

**Why first:** the only true correctness defect in GA. Every onboarded user (including alice / papa / dave / judy / tango) gets a degraded Perplexity search query because `_FIRST_BULLET_RE` in `src/findajob/discoverer/prompt.py` expects bulleted `## Target Roles`, but the v2 onboarding interviewer emits a single-sentence `## Target Role`. Falls through to generic fallback ("people in the candidate's field"). Search query goes ungrounded.

**Shape of fix:** loosen the regex to match either schema, OR rev `onboarding_interviewer.md` to emit both forms. Pick the cheaper path. Add a regression test pinning both shapes.

**Done = ** new tester onboarding produces a Perplexity query with the role headline inlined; existing operator profile.md still parses cleanly.

### 2. #84 — `excluded_employers` config + prefilter enforcement

**Why next:** real generalization gap. Every onboarding interview captures employers the user won't work for; pipeline currently has nowhere to put them, so exclusion is non-deterministic (relies on LLM scorer reading "Not open to:" line in profile.md).

**Shape of fix:** ship `config/excluded_employers.yaml.example` (gitignored .yaml + tracked .example with generic placeholders). Wire into `src/findajob/scorer_prefilter.py` Stage 1 — match before LLM call, score 1, `rejection_reason = "excluded_employer"`. Self-contained, no deps.

**Done = ** acceptance criteria 1+2 in the issue body. Plus update onboarding injector to write the user's collected exclusions into `config/excluded_employers.yaml` automatically.

### 3. #373 — Tracking: dave/judy/tango onboarding  ★ External-paced

**Why this counts as GA:** acceptance criterion #1 of the milestone is "external tester is deriving daily utility — not merely testing." alice (deployed 2026-04-30) + papa (2026-04-29) prove the path; dave/judy/tango onboarding completes the cohort.

**Shape:** not engineering work — operator hands off URL + Basic Auth + onboarding prompt to each tester, waits for paste-back, observes first successful triage. Closes when all three have at least one `pipeline_complete` event in their stack's `audit_log`. Tester-paced, not blocked on code.

**Jared role:** check this every session. If a tester onboards, mark the checklist item closed. If 7+ days pass with no movement, surface as a re-engagement decision for the operator.

### 4. #275 — Expand `gmail_linkedin` saved-search docs

**Why:** highest-ROI doc work in GA. `gmail_linkedin` is the highest-hit-rate source (15.93% vs 1.95% for greenhouse_json). Multiplying it costs zero code — only setting up more LinkedIn saved searches. Doc gap is preventing testers from adopting the multiplier.

**Shape:** short section in `docs/usage.md` (or new `docs/usage/expanding-sources.md`) covering how to set up a LinkedIn saved-job alert, recommended tuning for breadth-without-spam, examples of 5–10 generic saved searches across keyword + geo dimensions.

**Done = ** a new tester reading the doc can stand up 3+ saved searches in 15 minutes. Pair with #76's docs sweep if they get bundled.

### 5. #76 — Refresh operations/architecture/scripts-reference for Docker deploy

**Why last:** longest-tail polish in GA. The native-install language scattered across these three docs is technically correct but stale (every active user is on Docker). Not blocking GA's operational acceptance — alice and papa are already deriving daily utility — but worth closing before declaring GA shipped.

**Shape:** rewrite `docs/operations.md`, `docs/architecture.md`, `docs/scripts-reference.md` into parallel Docker + Native Operations sections. Keep both — Docker primary, native as fallback reference. No new architecture claims (anti-drift rule 1 — reference canonical docs, don't restate).

**Risk:** scope creep into "rewrite everything." Cap at the 3 named docs. If you find yourself touching a 4th, stop and surface.

## What's NOT in GA anymore (post-2026-05-01 reshape)

These were moved out so GA could close inside the May 12 date. Don't pull them back in unless something material changes:

- **Multi-Tenancy Foundations** (next milestone): #283 (onboarding query derivation), #287 (discoverer cost guardrail), #336 (in-app onboarding chat UI), #339 (per-tester API key isolation), #338 ([Epic] anchor), #211/#212/#215 (paste-back polish), #344 (multi-tenant scheduler stagger), #330/#333 (already shipped under v0.8.3 / v0.9.0), #372 (per-tenant geography filter from nux-papa).
- **Funnel + Triage UX**: #85 (Style Rules into prep prompts), #358 (fallback queue), #362 (rejection auto-detect — has fresh design spec at `docs/superpowers/specs/2026-05-01-362-rejection-detection-design.md`).
- **Ops Hardening**: #181 (Playwright e2e), #126 (uv standardization), #301 (data audit + backup), #359 / #360 (admin error-paths follow-ups).

## Standing checks for every Jared session this week

1. **Apply gate.** Query `audit_log` on docker.lan for today's PT applies. If under 3, no Medium/Low scope-pulls.
2. **GA pulse.** Are all 5 GA issues still in motion? Anything aged > 7 days with no commits / comments → flag for the operator.
3. **Tester pulse (#373).** Any of dave/judy/tango onboarded since last check? Update checklist.
4. **Spec drift.** New untracked spec at `docs/superpowers/specs/2026-05-01-362-rejection-detection-design.md` (#362) — committed yet? If no, surface.

## After GA closes

Promote `Multi-Tenancy Foundations` to active milestone. Move the GA section in `docs/roadmap.md` to "Shipped and retired milestones" + add a new `## Active milestone: Multi-Tenancy Foundations` section with the same shape (goal, acceptance criteria, remaining scope, decisions, scope-out). Resume path for the milestone is captured in the Session note on Epic #338 — `#336` (in-app onboarding chat UI) is the largest remaining piece.

## Pointers

- `docs/roadmap.md` Decision 19 — full record of today's reshape.
- `docs/project-board.md` — current board conventions (canonical 5-column flow).
- Epic #338 Session note (2026-05-01) — Multi-Tenancy Foundations resume path.
- `docs/superpowers/specs/2026-05-01-362-rejection-detection-design.md` — fresh spec, untracked, awaiting commit decision.
