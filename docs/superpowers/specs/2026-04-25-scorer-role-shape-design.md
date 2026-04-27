# Scorer Role-Shape Mismatch Reduction — Design Spec

## Issue(s)
- #276 — Penalize role-shape mismatches (seniority, IC-vs-manager) against profile

**Date:** 2026-04-25
**Status:** Design approved via brainstorming session; ready for implementation-plan pass
**Related work:** #65 (prior scorer prompt neutralization), #84 (excluded_employers — same locus-split pattern), #150 (future guided tuning UI), #228 (data-driven tuning loop)

---

## 1. Context

The scorer over-weights domain keywords (DC, hardware, NPI, server, GPU) without distinguishing the **shape of the role** versus the operator's profile. This produces a high false-positive rate at scores 5–6 — the band that the just-shipped per-column filter framework (#273) now exposes to the operator.

A hand-graded sample of the operator's score-6 pool on 2026-04-25 (132 jobs in `stage='scored'`, post-dedup) found:

- ~12% (≈16 jobs) match the operator's actual role shape — Director-of-NPI, Production Manager, Product Development Manager, Infrastructure Lead, Ops/Program Manager.
- ~88% are domain matches but role-shape mismatches the operator will reject on sight: data-center technicians, IC hardware/EE/robotics engineers, TPMs lacking people-management depth, forward-deployed/customer-engineer roles.

The score-5 pool (64 jobs) shows the same pattern less acutely.

The scorer prompt was neutralized in #65 to derive rejects and in-domain signal from the candidate profile rather than enumerate categories. That move was correct but did not reach the **seniority axis** or the **IC-vs-manager axis**. The profile encodes leadership-shape signal (years of management, span of leadership, founded-orgs language); the scorer does not currently penalize roles whose JD content describes a contribution shape that conflicts with that profile.

The dashboard surface created by #273 turns this scorer issue from a hidden quality problem into a visible one: 200+ score-5/6 rows now reach the operator's queue, and the operator's hand-grade confirms most are unproductive. Tightening the scorer is the load-bearing follow-up before the new surface delivers value.

## 2. Objectives

| Role | Metric | Treatment |
|---|---|---|
| **Primary objective** | False-positive reduction in the 132+64 hand-grade pool | ≥60% of operator-confirmed mismatches drop to ≤4 after change |
| **Hard floor — false-negative protection** | Previously-applied jobs (every applied job in DB history) | Must re-score ≥7 |
| **Soft floor — false-negative protection** | The ~12% legit-shape matches in the hand-grade pool | Must stay ≥6 |
| **Drift guardrail** | Per (source × score-band) score deltas | No cell where >50% of jobs drop ≥3 points unless intentional |
| **Generalization gate** | Diff of tracked files | Zero enumerated titles, role-categories, companies, or industry vocabulary |

The first metric is the headline; the next three are non-negotiable safety gates. The fifth is the architectural constraint that keeps the change re-usable for operators in other fields (per `CLAUDE.md` §"PII and Domain-Neutrality").

## 3. Scope

### 3.1 In scope

- One tracked-code change to `config/roles/job_scorer.md`: a new abstract "Role-Shape Calibration" section that points the scorer at profile-derived role-shape signals without naming any titles or categories.
- New test file `tests/test_scorer_role_shape.py` covering any new prefilter regex patterns against a corpus of legitimate operator-target titles.
- A `CHANGELOG.md` entry under `[Unreleased]` → `Changed`.
- Operator-side edits to gitignored configuration on docker.lan: `candidate_context/profile.md` (enriched `## Title Calibration Notes` and/or new `## Role-Shape Calibration` section), `config/prefilter_rules.yaml` (narrow level-word patterns and unambiguous career-tier titles).
- Throwaway analysis artifacts in `tmp/`: extracted samples, observation notes, re-score CSV, delta computation. Gitignored.
- Operator-side migration documentation in the eventual PR description so the change can be applied to any future operator's stack.

### 3.2 Out of scope

- Building the guided tuning UI (#150) — the principles surfaced in this work inform that design but do not implement it.
- Updating Alice's stack — Alice is a social-work candidate with a different profile; this work is operator-specific to the primary operator's stack. The tracked code change is generalization-safe and applies to both stacks at the next image rebuild.
- Backfilling historical scores — only newly-ingested jobs benefit from the change going forward. A one-off re-score script for the verification phase is in scope; a production backfill is not.
- Touching `scorer_prefilter.py` Python code — the existing two-stage mechanics already accommodate the new patterns. This work adds rules, not architecture.
- Building a metric-layer foundation for future tunes (subsystem C, #229–#231) — referenced for context, not delivered here.

### 3.3 Not in scope even as future work

- Per-pattern A/B testing infrastructure — premature given a single operator and single prompt.
- LLM-driven prefilter rule generation — speculative; the data-first methodology in this work is hand-driven by Claude with operator review.

## 4. Architecture — locus split (load-bearing)

The decision rule for where each kind of signal lives is the architectural foundation of this work:

> **The prefilter is title-deterministic only. If a JD is needed to make the call, the signal belongs in the LLM prompt + profile (`## Title Calibration Notes`), never in `prefilter_rules.yaml`.**

| Signal type | Locus | Examples |
|---|---|---|
| Title-deterministic and unambiguous | `config/prefilter_rules.yaml` (gitignored) | "Junior", "Associate", "Intern", "Data Center Technician", "Server Technician" with `context_suppressors` for legitimate edge cases |
| Title-token requiring disambiguation | Profile `## Title Calibration Notes` (gitignored) | "Senior TPM" — fits or does not depending on JD's content depth |
| JD-content shape (IC vs management, content depth) | Profile (new section) + scorer prompt pointer | "JD describes hands-on firmware bring-up vs. leading the team that ships firmware" |
| Generic seniority floor | Scorer prompt — abstract reference to candidate profile | "If profile shows N years of management trajectory, score IC roles below that line conservatively" |

**Rationale.** The prefilter is binary, has no LLM safety net, and runs against the title only. Putting JD-content signal there is the silent-failure mode: a wrong-locus rule loses good jobs invisibly. `context_suppressors` is the right escape hatch for *title-shape* edge cases ("Data Center Security Engineer" overrides `\bsecurity\b`); it is not a substitute for content-depth disambiguation. The asymmetric blast radius — silent uncorrectable false negatives in the prefilter, visible recoverable ones in the LLM prompt — argues for keeping the prefilter narrow and pushing nuance into the profile and the prompt that already reads it.

The profile is the locus, not the tracked prompt file. The scorer prompt at `config/roles/job_scorer.md` lines 84–87 already reads `## Title Calibration Notes` from the profile. This is an existing wired-up hook. The work is to push richer disambiguation content through it, not to invent new mechanisms.

## 5. Components and change surfaces

### 5.1 Tracked changes (committed via PR)

#### `config/roles/job_scorer.md` — new "Role-Shape Calibration" section

Inserted between the existing "CANDIDATE-TOKEN CALIBRATION" and "CROSS-INDUSTRY RECOGNITION" sections. Approximately 10–15 lines. Strictly abstract — references profile sections, names no titles, categories, companies, or industries. Tells the scorer to:

1. Read the profile's `## Title Calibration Notes` and any `## Role-Shape Calibration` section.
2. When a JD describes a contribution shape (IC technical work, management of engineers, customer-facing technical advocacy, etc.) that conflicts with the shape the profile is looking for, score conservatively even when the title token matches the candidate's vocabulary.
3. When the profile names a seniority floor (years of management, span of leadership), penalize JDs that describe pure-IC contribution work below that floor.

The section must pass the generalization gate by inspection — a reviewer should be able to read it without inferring the candidate's specific field.

#### `tests/test_scorer_role_shape.py` — new test file

Validates the *shape* of the new patterns we expect operators to add, against an inline fixture YAML (no dependency on the operator's gitignored `prefilter_rules.yaml`). Two test classes:

- `TestLevelWordPatternsRejectJuniorTitles` — generic level-word patterns (`\bjunior\b`, `\bintern\b`, `\bassociate\s+(engineer|analyst|developer)\b`) reject titles like "Junior Backend Engineer", "Software Engineering Intern", "Associate Data Analyst".
- `TestLevelWordPatternsPreserveSeniorTitles` — same patterns must NOT reject titles using the words in non-junior senses: "Senior Director" (contains "senior"), "Director, Junior Achievement Partnerships" (contains "junior" but is a director role — covered by `context_suppressors`), "Associate Vice President" (contains "associate" but is a senior role).

Tests are field-agnostic — no operator-specific titles in the corpus. They guard the prefilter mechanism, not the operator's content.

#### `CHANGELOG.md` — `[Unreleased]` entry

```
### Changed
- Scorer prompt: added "Role-Shape Calibration" section that directs the scorer to penalize JD-described contribution shapes that conflict with the candidate's profile-stated leadership shape, when the title token alone is ambiguous (#276)
```

### 5.2 Operator-side edits (gitignored, applied on docker.lan)

These edits are applied via the `/config/` web UI or by direct file edit on the docker.lan bind mount. They are **not** part of the PR; they are part of the operator-side migration the PR description documents.

#### `candidate_context/profile.md`

- Enrich `## Title Calibration Notes` with role-shape disambiguators sourced from Phase 1 data analysis (see §6).
- Optionally add a `## Role-Shape Calibration` section if Title Calibration becomes too long. The scorer prompt's new section reads both.

#### `config/prefilter_rules.yaml`

- Add a new `seniority_below_floor` category with narrow level-word patterns: `\bjunior\b`, `\bassociate\s+(engineer|analyst|developer)\b`, `\bintern\b`, etc. Patterns are derived from data observation, not from this spec doc — the spec defines the *shape* of the change, not its content.
- Add a `clear_career_mismatch` category with unambiguous title patterns: `\bdata\s+center\s+technician\b`, `\bserver\s+technician\b`, etc.
- Add `context_suppressors` for any legitimate edge case the data analysis surfaces (e.g., `\boperations\s+technician\s+(manager|lead)\b` to protect a managerial role that contains the word "technician").

### 5.3 Throwaway analysis artifacts (`tmp/`, gitignored)

- `tmp/role_shape_baseline.csv` — extracted samples from docker.lan
- `tmp/role_shape_observations.md` — Phase 1 analysis notes
- `tmp/role_shape_rescore.csv` — post-change scores plus deltas
- `tmp/role-shape-tuning-notes.md` — already exists; append throughout the work

## 6. Data flow and methodology

Five phases. Phase 0 → 1 is data-first analysis. Phase 2 → 4 is design-then-verify.

### Phase 0 — Data extraction

Pull from docker.lan:

- Operator's `profile.md`, `prefilter_rules.yaml`, `in_domain_patterns.yaml` — read into Claude's context, not committed.
- Two CSV exports into local `tmp/`:
  - `tmp/role_shape_hand_grade_pool.csv`: all 132 score-6 + 64 score-5 jobs currently in `stage='scored'`. Columns: `job_id, source, fingerprint, title, company, location, relevance_score, jd_text_first_2000_chars, score_status, ai_notes`.
  - `tmp/role_shape_baseline.csv`: stratified random sample across (source × score-band) cells from the last 90 days, plus forced inclusion of every job with an `audit_log` transition to `applied`. Same column shape plus `gold_set` flag and `applied_date` where applicable.

Total sample size estimate: ~700–900 jobs.

### Phase 1 — Data-first analysis

- Cluster titles in the 196-job hand-grade pool. Look for token co-occurrence patterns.
- Read 20–30 JDs from the 88% mismatch set; 5–10 from the 12% legit-shape set. Surface empirical phrase-pairs that distinguish them — e.g., "you'll write firmware" vs. "you'll lead the team that ships firmware", IC contribution language vs. management language, content-depth markers (silicon validation, schematic review, GPU memory subsystem expertise) vs. infrastructure-program markers (cross-functional rollout, capacity planning, vendor management).
- Write findings to `tmp/role_shape_observations.md`. This document is the bridge between the data and the prompt/profile content. Not committed.

### Phase 2 — Design changes informed by Phase 1

- Edit operator's `profile.md` (gitignored, applied on docker.lan or via `/config/`) with role-shape disambiguators sourced from Phase 1 observations. Specific phrases from the JD analysis go here.
- Edit operator's `prefilter_rules.yaml` (gitignored) with narrow level-word and clear-career-mismatch patterns plus any required `context_suppressors`.
- Edit tracked `config/roles/job_scorer.md` with the abstract "Role-Shape Calibration" pointer section.

### Phase 3 — Re-score and measure

- Run the full scoring pipeline (prefilter + LLM) against the ~700–900-job sample on docker.lan. The new operator-side configs are in place; the new scorer prompt is in place via image rebuild or volume override during the test run.
- Output `tmp/role_shape_rescore.csv` with columns: `job_id, source, current_score, new_score, delta, gold_set, in_hand_grade_pool, applied_flag`.

### Phase 4 — Verify against acceptance gates

- Compute the five gates from §2.
- For the 132+64 hand-grade pool: hand-spot-check the post-change scores against the operator's prior hand-grade categories (mismatch vs. legit-shape). The check is "of the score-6 jobs that dropped to ≤4, were they actually mismatches?" and "of the score-6 jobs that stayed ≥6, are they actually legit-shape matches?"
- For previously-applied jobs: automated check — every row's `new_score` must be ≥7. If any drop below, the change is rejected and Phase 2 is iterated.
- For the per (source × score-band) drift check: report the delta distribution per cell. Investigate any cell where >50% of jobs drop ≥3 points.
- For the generalization gate: inspect the diff of `config/roles/job_scorer.md` and any other tracked file for enumerated titles, role-categories, companies, or industry vocabulary.

### Phase 5 — Iterate or ship

- If all gates pass: open PR with the tracked changes; document operator-side migration in the PR description; close #276 on merge.
- If gates fail: iterate Phase 2 with the new observations from the failure. Hard ceiling of 3 prompt+profile iterations before re-scoping (e.g., considering a second-pass scorer or rethinking whether the issue is upstream of the scorer entirely).

## 7. Verification and acceptance gates

| Gate | Mechanism | Pass criterion |
|---|---|---|
| New prefilter regexes do not over-match | Unit tests in `tests/test_scorer_role_shape.py` against a corpus of operator-target titles | All target titles pass through |
| New prefilter regexes match intended targets | Same test file, separate test class | All intended-target titles match |
| Existing prefilter regression | Existing `tests/test_scorer_prefilter.py` tests | Green, no changes |
| Primary objective — false-positive reduction | Phase 4 manual + automated diff against hand-grade categories | ≥60% of mismatch jobs drop to ≤4 |
| Hard floor — applied-job protection | Phase 4 automated check | Every previously-applied job re-scores ≥7 |
| Soft floor — legit-shape protection | Phase 4 manual spot-check | All hand-graded legit-shape jobs re-score ≥6 |
| Source/score drift | Phase 4 per-cell delta report | No cell where >50% of jobs drop ≥3 points without intent |
| Generalization | Phase 4 inspection of tracked-file diff | Zero enumerated titles/categories/companies/industries |

The hard floor and the generalization gate are non-negotiable. The other gates may be revisited if Phase 4 surfaces a reason to recalibrate (e.g., the 60% target turns out to be too aggressive given the data; the soft floor needs to drop to ≥5 because the legit-shape set was misclassified during the original hand-grade).

## 8. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Profile edits drift over time and the prompt loses signal | The change is reversible — edit profile content out. Future tuning UI (#150) will surface profile sections as first-class affordances. |
| Re-score on docker.lan affects production DB | Re-score writes to `tmp/role_shape_rescore.csv` only; production DB is untouched until image rebuild + deploy. |
| Phase 4 acceptance fails after 3 iterations | Hard ceiling triggers re-scoping. Likely escalation: consider second-pass scorer or a separate "shape-fit" LLM pass distinct from the primary score. |
| Operator-side migration is missed when applying to a fresh stack | PR description includes the operator-side migration steps verbatim. Future onboarding interview (`config/roles/onboarding_interviewer.md`) is the natural place to fold this in for new operators. |
| Tracked code accidentally enumerates operator-specific titles | Pre-commit PII hook does not catch role-category names; reviewer must apply the generalization gate manually. The spec adds this gate to the §7 checklist. |
| Generalization regression on Alice's stack | Tracked changes are profile-driven and field-agnostic; Alice's `## Title Calibration Notes` will encode social-work-specific disambiguation when she adds it. The image rebuild deploys the new prompt to both stacks; only operator-side configs are stack-specific. |

## 9. Documentation Impact

| Surface | Change |
|---|---|
| `config/roles/job_scorer.md` | The change itself — new "Role-Shape Calibration" section |
| `CHANGELOG.md` | `[Unreleased]` → `Changed` entry citing #276 |
| `docs/superpowers/specs/2026-04-25-scorer-role-shape-design.md` | This file |
| Eventual implementation plan in `docs/superpowers/plans/` | Created during the writing-plans phase |
| PR description | Documents the operator-side migration steps for `profile.md` and `prefilter_rules.yaml` so that a future operator can apply them when pulling the new image |
| `CLAUDE.md` | None — the locus-split rule is captured in the spec and in `tmp/role-shape-tuning-notes.md`; if it proves load-bearing across multiple tuning changes, promote to `CLAUDE.md` then |
| `docs/usage.md`, `docs/setup/*` | None — this is a scorer behavior change with no operator-action change beyond the one-time profile/prefilter edit, which the PR description covers |
| `tmp/role-shape-tuning-notes.md` | Append session notes through Phase 5 |
| GitHub comments on #228, #150 | Already posted — generalizable principles for the eventual data-driven tuning loop and guided tuning UI |

## 10. Self-review checklist (spec-to-implementation map)

| Spec section | Implementing task |
|---|---|
| §4 locus split rule | Phase 2 — locus determines which file each change lands in |
| §5.1 `config/roles/job_scorer.md` change | Phase 2 — tracked code edit |
| §5.1 test file | Phase 2 — new test creation |
| §5.1 CHANGELOG | Phase 2 — entry under `[Unreleased]` |
| §5.2 profile edits | Phase 2 — operator-side, applied on docker.lan |
| §5.2 prefilter rules | Phase 2 — operator-side, applied on docker.lan |
| §5.3 throwaway artifacts | Phases 0, 1, 3 — created in `tmp/` |
| §6 Phase 0 (data extraction) | First implementation task |
| §6 Phase 1 (data-first analysis) | Second implementation task |
| §6 Phase 2 (design changes) | Third implementation task |
| §6 Phase 3 (re-score) | Fourth implementation task |
| §6 Phase 4 (verify) | Fifth implementation task |
| §6 Phase 5 (iterate or ship) | Sixth implementation task |
| §7 verification gates | Built into Phase 4 + dedicated PR-time check |
| §9 Documentation Impact | Each row maps to a Phase 2 or PR-time deliverable |
