# Metric Layer — Design Spec

## Issue(s)
- #229 — C.0: schema + cost instrumentation + config-drift detector (in-flight via plan `2026-04-24-metric-layer-c0.md`)
- #230 — C.1: view-layer dashboards (depends on #229)
- #231 — C.2: stratified analysis surfaces (depends on #230)

**Date:** 2026-04-24
**Parent epic:** #228 — Data-driven tuning loop (subsystem C of A–H decomposition)
**Subsystem:** C — Metric Layer (read-only measurement foundation)
**Status:** Design approved via brainstorming session; ready for implementation-plan pass

---

## 1. Context

The pipeline captures strong raw signal today — `jobs`, `audit_log`, `feedback_log`, `cost_log`, and the `/logs/pipeline.jsonl` event stream — but only one view surfaces it: `/stats/funnel`, which shows daily stage-transition counts. There is no way to answer any of the questions a tuner, or a disciplined operator, needs to answer before making changes:

- Is Dashboard→prep conversion trending up or down? Is it worse for LinkedIn than Greenhouse?
- Do jobs scored 9-10 actually convert to applications, or is the scorer overshooting?
- Which reject reasons are dominant for which sources?
- How do applied jobs actually perform (interview rate, silent-ghost rate)?
- Are we spending more per useful-result than we were a month ago?
- Did the last scorer-prompt edit hurt or help precision?

The Metric Layer (subsystem C of the parent epic) builds the measurement foundation that makes all downstream tuning possible. It is read-only, computes metrics with data-science rigor, and surfaces them through seven stratified web dashboards. It does **not** decide what to tune, when to tune, or write any tunes back — those are subsystems D (analyzer), E (recommendation surface), F (application layer), G (trigger engine), and H (evaluation).

The parent epic decomposes the tuning loop into 8 subsystems (A–H). This spec covers only C. A–H are designed independently in their own specs.

## 2. Objectives

| Role | Metric | Treatment |
|---|---|---|
| **Primary objective** | Precision — dashboard→prep conversion | Optimize (the tuner should move this up) |
| **Secondary validator** | Outcome — interview rate on applied | Protect (block any tune that degrades this once N is sufficient) |
| **Recall guardrail** | Weekly re-score audit upgrade rate | Alert when > 10% in a week |
| **Budget constraint — cost** | `$` per week, `$` per applied job | Hard cap; the tuner must respect |
| **Budget constraint — throughput** | Prepped jobs per week | Hard cap; the tuner must respect |

**Rationale for precision as primary:** dashboard→prep conversion is a per-job binary decision the operator makes dozens of times a week; a few hundred decisions produce statistically defensible precision estimates by stratum. Outcome metrics (interview rate) are the ultimate goal but produce usable signal only after ~6 weeks given 5–15% response rates and 14–21 day response latencies. The data-science-rigorous framing is "tune on the proxy, validate on the ultimate, block on budget, guardrail against recall collapse."

## 3. Scope

### 3.1 In scope

- SQL views and Python metric helpers that compute the dashboard figures
- Seven `/stats/*` pages rendering those figures with Wilson 95% CIs, min-N gates, and config-change markers
- A `config_changes` table + detector that logs every edit to a tunable lever
- A `recall_audit` table + weekly cron that re-scores a sample of hard-rejected and low-scored jobs
- Schema additions (`company_tier`, `scored_by` columns on `jobs`)
- Cost-tracking instrumentation for prep, outreach, briefing, and company-research LLM calls (today only scoring is tracked)

### 3.2 Out of scope (deferred to other subsystems)

- Analyzer logic — no "this is bad" labels, no thresholds, no recommendations (subsystem D)
- Recommendation surface — no "apply this tune" buttons (subsystem E)
- Write-back to tunable configs — the metric layer reads `config_changes`, never writes it except via the edit-detector (subsystem F)
- Trigger engine — no cron-based firing of analyzer/recommendation logic (subsystem G)
- Evaluation / A-B — no before/after comparison UI beyond eyeballing config-change markers (subsystem H)
- Per-beta-tester cost split — operator absorbs Alice Doe's cost until #225 (per-function API keys) lands
- New event captures (abandoned-prep, prep-ignored, materials-viewing) — subsystem A; C computes queue-depth directly from `audit_log` without them

### 3.3 Not in scope even as future work

- Historical re-scoring of already-scored jobs against new scorer prompts (this is subsystem H / backtest — different problem shape)
- Per-candidate tuning models trained from user behavior (far out of scope; this is a statistical dashboard, not ML)

## 4. Metric catalog

Seven pages under `/stats/`. Every metric is always stratified by `source × scorer-band × company-tier` where applicable. Every proportion is rendered with a Wilson 95% confidence interval. Every cell with N < 20 renders as "—" (min-N gate).

### `/stats/funnel` — retained, extended

Daily stage-transition counts over 30 days (currently exists). **Extension:** add per-source stratification.

### `/stats/precision` — primary objective view

- **Dashboard→prep conversion** — of jobs that actually reach the Dashboard UI (stage `scored` AND `relevance_score >= 7`, plus stage `manual_review`), the fraction flagged for prep. The ≥7 gate matches the filter in `CLAUDE.md` §"Google Sheet Architecture"; low-scored jobs never surface to the operator, so including them in the denominator would confuse "did the scorer filter well" with "did the operator triage well."
- **User-rejection rate by scorer-band** — of jobs scored ≥7, the fraction rejected by user. High values in the 9-10 band signal scorer overshoot.
- 7d and 28d columns side-by-side.
- Config-change markers overlaid on trend charts.

### `/stats/rejections` — reason attribution

Scope: **user rejections only** (from `feedback_log`). Company-side outcomes — `not_selected` — live on `/stats/outcomes`. The pipeline deliberately keeps these separate because company rejections must not feed the scorer's feedback loop (see `CLAUDE.md` §"Stage `not_selected`"); the analytics separation mirrors that architectural discipline.

- Reject-reason × source heatmap (rolling 28d).
- Reject-reason × company-tier heatmap.
- Reject-reason trend over time (weekly stacked area).
- Week-over-month delta table.

### `/stats/outcomes` — validation lens (D)

- Apply-to-response rate (interview | not_selected | silent-ghost after 21d), stratified by `source × company-tier × scorer-band-at-apply-time`.
- Response-latency distribution (median, p75, p95).
- Says "insufficient data" until each stratum reaches N ≥ 20. Expected to be largely empty for the first 4–6 weeks of tuner operation; that is correct behavior.

### `/stats/cost` — budget rail

- Weekly `$` total, trended.
- `$` per job-reaching-applied (unit economics), stratified by source.
- `$` by operation (score, prep-materials, outreach, briefing, company-research, recall-audit).
- Projection vs `weekly_cost_usd` cap (cap is a configured constant; tuner in subsystem F will read it).

### `/stats/signal` — operator diagnostic

- Ingest volume by source per day.
- Hard-reject rate by source (prefilter Stage 1 + prefilter Stage 2 + LLM, differentiated via `scored_by`).
- Queue depth — `materials_drafted` sitting > N days without apply (abandonment signal; rendered as a count, not an alert).
- `config_changes` timeline (read-only audit).

### `/stats/recall-audit` — recall guardrail

- Weekly random sample: 20 hard-rejects + 20 low-scored (relevance 3–6) jobs, re-scored by Sonnet 4.6.
- Metric: fraction of re-scores that upgrade to ≥6 (the "we-might-have-missed-this" rate).
- Alert when upgrade rate > 10% in a week.
- Cost budget: approximately `$0.50` / week.

## 5. Data-science treatment

### 5.1 Windowing — hybrid (rolling + config-version annotation)

Every metric displays rolling 7d and 28d. The `config_changes` table records every edit to a tunable lever (profile, scorer prompt, queries, excluded_employers, feed URLs, master resume, role prompts, prefilter rules). Trend charts overlay a vertical marker at each change's timestamp, labeled with the lever. Operator can see by eye whether the metric moved after a change. The analyzer (subsystem D, future) will apply a stricter policy — "don't recommend a tune on a stratum where a related config change happened < 14 days ago" — but the dashboard itself does not hide data.

### 5.2 Stratification — always

Every metric is computed broken down by `source × scorer-band × company-tier` at minimum (where the stratification is meaningful — `cost` is not meaningfully stratified by scorer-band, etc.). Aggregates are available but always shown beside the drill-down. Rationale: Simpson's paradox. An overall improvement can hide a within-stratum regression.

### 5.3 Confidence intervals — Wilson 95%

Wilson's score interval for a binomial proportion. Cheap to compute, well-behaved at small N (unlike the normal approximation), standard in applied statistics. Rendered as `x% ± y` beside every proportion.

### 5.4 Minimum-N gate — N ≥ 20

Any stratum cell with N < 20 renders as "—". Prevents high-variance small-sample numbers from misleading the operator or the future analyzer. 20 is a pragmatic threshold (Wilson CI width at p=0.5, N=20 is ±21%; tighter than what the eye reliably separates from noise).

### 5.5 Multiple-testing correction — analyzer concern, not dashboard

The dashboard shows every stratum with a CI. The analyzer (subsystem D) will apply Benjamini-Hochberg correction when it fires, because it is simultaneously evaluating many strata against thresholds. The metric layer does not do this.

## 6. Schema additions

```sql
-- New: causal-attribution backbone for hybrid windowing
CREATE TABLE config_changes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lever TEXT NOT NULL,              -- profile | scorer_prompt | master_resume |
                                      -- resume_tailor_prompt | cover_letter_prompt |
                                      -- briefing_writer_prompt | outreach_drafter_prompt |
                                      -- company_researcher_prompt | queries |
                                      -- excluded_employers | feed_urls | prefilter_rules
    changed_at TEXT DEFAULT (datetime('now')),
    changed_by TEXT DEFAULT 'manual', -- manual | tuner | onboarding
    change_summary TEXT,              -- 1-line human description
    content_hash TEXT,                -- sha256 of current lever content, for dedup
    diff_summary TEXT                 -- optional structured diff payload
);
CREATE INDEX idx_config_changes_lever_time ON config_changes(lever, changed_at);

-- New: recall-guardrail storage
CREATE TABLE recall_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL,
    audited_at TEXT DEFAULT (datetime('now')),
    original_score INTEGER,
    original_scored_by TEXT,          -- prefilter_stage1 | prefilter_stage2 | llm
    auditor_model TEXT NOT NULL,      -- e.g., claude:claude-sonnet-4-6
    audited_score INTEGER,
    upgraded INTEGER DEFAULT 0,       -- 1 if audited_score >= 6 and original < 6
    audit_notes TEXT
);
CREATE INDEX idx_recall_audit_time ON recall_audit(audited_at);

-- Additive columns on jobs (ALTER TABLE pattern already used for loose_fingerprint)
ALTER TABLE jobs ADD COLUMN company_tier TEXT DEFAULT 'unknown';  -- tier1 | other | unknown
ALTER TABLE jobs ADD COLUMN scored_by TEXT DEFAULT '';            -- prefilter_stage1 | prefilter_stage2 | llm
```

### 6.1 Config-change detector

`scripts/detect_config_drift.py` hashes each tracked lever, compares against the most recent `config_changes.content_hash` for that lever, writes a row when the hash differs. Called from:

- `scripts/triage.py` — pre-triage, so every triage cycle attributes against the most recent config state
- `src/findajob/web/routes/config.py` — POST handler after any successful `/config/files/{path}` write
- `src/findajob/onboarding/injector.py` — after the paste-back injection completes (bulk change; emits one row per lever that moved)

`changed_by` column distinguishes the three surfaces. Future subsystem F will also write rows with `changed_by='tuner'`.

### 6.2 Column population

- `company_tier` is populated at score time in `src/findajob/scoring.py` before the `UPDATE jobs SET ...` — resolved from the current target-companies file. Existing rows are backfilled via a one-shot `scripts/backfill_company_tier.py` at migration.
- `scored_by` is populated at score time in `src/findajob/scorer_prefilter.py` (`'prefilter_stage1'` or `'prefilter_stage2'`) or in `src/findajob/scoring.py` (`'llm'` on the non-prefilter branch). Existing rows are backfilled via heuristic on `ai_notes` text and left `'llm'` when ambiguous.

## 7. Architecture

### 7.1 Module layout

```
src/findajob/metrics/
    __init__.py
    views.py              # Typed wrappers around each SQL view; accepts stratum dims + window days
    stats.py              # Wilson CI, min-N gate, stratum aggregation helpers
    config_changes.py     # Detector + write path; called from triage, /config/ POST, onboarding injector
    recall_audit.py       # Weekly sample-and-rescore; called from supercronic

sql/metrics/
    precision.sql         # Dashboard→prep conversion, stratified
    rejections.sql        # Reject-reason distributions
    outcomes.sql          # Apply-to-response with at-apply-time scorer band
    cost.sql              # $/week, $/applied-job, by operation
    signal.sql            # Ingest volume, hard-reject breakdown, queue depths
    funnel.sql            # (extracted from existing stats.py for consistency)
    recall_audit.sql      # (trivial — just pulls the table)

src/findajob/web/routes/stats.py
    # Extended with six new endpoints (one per new page)
    # funnel endpoint unchanged, just consuming the moved SQL
```

### 7.2 Rendering

Every new `/stats/*` page follows the pattern already established in `templates/stats/funnel.html`:

- Server computes metrics + CIs + min-N masking, pre-serializes a Chart.js payload, renders HTML with the chart div
- No fetch-on-load — page renders with data in-place
- Tailwind + `static/app.css` design tokens for consistency
- HTMX not required at this layer — pages are static views; filtering via URL query params (existing pattern)

### 7.3 Computation

No materialization for v1. Low hundreds of jobs today; each view query completes well under 100ms. Reassess if any view exceeds 200ms at 10× current data volume.

### 7.4 Instrumentation additions

`log_call` (existing in `src/findajob/cost_tracking.py`) is added to:

- `scripts/prep_application.py` — for every aichat-ng invocation (resume_tailor, cover_letter_writer, job analysis, resume_change_reviewer)
- `scripts/find_contacts.py` — for outreach drafting
- Any script that calls `briefing_writer` or `company_researcher` via aichat-ng

Total: ~4 instrumentation points. Pattern is identical to `scripts/triage.py:548`.

## 8. Staging plan

**C.0 — schema + instrumentation prereqs (week 1, ~3–4 days)**
- `init_db.py` additions (ALTER TABLE for columns, CREATE TABLE for new tables)
- Backfill scripts for `company_tier` and `scored_by`
- `config_drift` detector + three integration points
- Cost-tracking instrumentation on 4 additional operations
- Validation gate: triage + prep on one test job; confirm every LLM call lands in `cost_log` and every config edit lands in `config_changes`

**C.1 — view layer + dashboards (week 2, ~3–4 days)**
- `src/findajob/metrics/` module with Wilson CI + min-N gate helpers
- `sql/metrics/` view definitions
- Six new `/stats/*` pages + one extension to `/stats/funnel`
- Chart.js payloads following `funnel.html` pattern
- Unit tests for Wilson CI, min-N gate, and one end-to-end metric (precision) against a synthetic SQLite DB
- Validation gate: every `/stats/*` page renders against real data with plausible eyeball-checkable numbers

**C.2 — recall-audit cron (1–2 days)**
- Weekly supercronic entry: `recall_audit.py` samples 20 hard-rejects + 20 low-scored + re-scores with Sonnet 4.6 + writes to `recall_audit`
- `/stats/recall-audit` renders; emits ntfy alert if upgrade rate > 10%
- Validation gate: one manual invocation, eyeball the sample and scores

Total C: ~2 weeks sequential; C.0 and early C.1 groundwork can parallelize once schema is in.

## 9. Testing strategy

- Unit tests for statistical helpers (`wilson_ci`, `min_n_mask`, stratum aggregation) against known-answer fixtures
- Unit tests for each SQL view against a fixture SQLite DB with a small seeded dataset (jobs across sources, stages, scorer bands; audit_log with known transition patterns; feedback_log with known rejections; cost_log with known costs)
- Integration test: a `/stats/*` route returns 200 and contains the expected Chart.js payload keys
- No test attempts to assert "the number is right" beyond round-trip correctness — domain correctness is eyeball-validated at the staging gates

## 10. Documentation impact

Per CLAUDE.md plan conventions, enumerating every doc surface that changes.

- **CLAUDE.md** — add a brief entry to the "Key File Locations" block listing `src/findajob/metrics/` and `sql/metrics/`. Add one paragraph to the "Critical Architecture Rules" section: "Metric layer is read-only; never writes to tunable configs; `config_changes` is its own write surface via three specific entry points."
- **docs/setup/install-docker.md** — no change in C.0; a one-line mention of the recall-audit weekly cron in C.2.
- **docs/project-board.md** — no change.
- **CHANGELOG.md** — one `[Unreleased]` entry per phase (C.0, C.1, C.2) at merge time.
- **docs/superpowers/specs/2026-04-21-user-docs-design.md** — unchanged; tuning.md (issue #219) gets a new "Monitoring" section referencing the `/stats/*` pages, but that's #219's concern, not C's.
- **Docstrings** — new modules fully docstringed; SQL view files carry a header comment describing the metric.
- **This spec** — committed to the repo; becomes the authoritative design reference.

## 11. Success criteria

For C itself (not the parent epic):

1. All seven `/stats/*` pages render against real operator data with plausible numbers, eyeball-verified.
2. Every tunable lever's edit produces a `config_changes` row regardless of entry surface (manual, `/config/` editor, onboarding injector).
3. Every LLM call across the pipeline produces a `cost_log` row.
4. Weekly recall-audit runs autonomously via supercronic on the operator's stack for two consecutive weeks without intervention.
5. `/stats/precision` shows at least three distinct source strata with N ≥ 20 and non-overlapping CIs for at least one pair (i.e., the stratification is surfacing real structure, not just ratios on N=5 cells).
6. No performance regression on any view beyond 200ms under the operator's current data volume.

## 12. Open questions / deferred decisions

- **Whether `/stats/recall-audit` needs its own config file.** The sample size (20 + 20) and auditor model (Sonnet 4.6) are reasonable constants for v1 — will promote to config if a user wants to tune them.
- **Where to surface `$/prep-job` vs `$/applied-job`.** Both on `/stats/cost` is right; open question is whether to show them as separate charts or one chart with two series. Decide during C.1 implementation.
- **Company-tier values.** `company_tier` as `tier1 | other | unknown`. Multi-tier support (tier1/tier2/tier3 per profile.md example) is deferred — operator and first beta tester both use binary tier today. When a future user populates a multi-tier target list, this column becomes a wider enum; no structural change needed.

## 13. Related work

- #65 — neutralize `job_scorer.md` prompt — precursor to subsystem F (write-back); not a blocker for C but on the same epic.
- #85 — wire `profile.md` style-rules and framing into prep prompts — same pattern as #65.
- #219 — write `docs/tuning.md` — becomes materially better once C exists; `docs/tuning.md` should reference `/stats/*` pages as the monitoring surface.
- #225 — per-function API keys — unblocks per-tester cost split if/when that becomes a goal.
- #32 — the "Option D" cost-tracking work that seeded `cost_log`; this spec completes its coverage.
