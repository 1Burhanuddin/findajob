# Scorer rewire — abandoned 2026-04-27

**Issues:** #276 (original attempt), #285 (rewire). Both closed-not-fixed.
**Branch (deleted):** `feat/285-scorer-rewire` — recoverable from reflog if needed.

## What was tried

Replace `config/roles/job_scorer.md`'s **TIER 1 EXCEPTION** floor mechanic with two complementary signals:

1. **COMPETENCY-FIT AXIS** — instructs the LLM to evaluate JD content against the candidate profile's `## Core Competencies` directly, surfacing a `competency_fit: N/10` line in `ai_notes`.
2. **STRATEGIC-PREFERENCE SIGNAL** — reads both `## Target Companies` (from profile.md) and the discoverer's `discovered_companies.md` (from #284, shipped) as **inputs to scoring, not floors**.

Plus the supporting code changes: `_build_discovered_block()` helper in `findajob.scoring`, `discovered_block` parameter on `score_job()`, `_DISCOVERED_BLOCK` module constant in `scripts/triage.py`, field-agnostic smoke test, 30-day mtime staleness check on the discovered file.

Ran two operator-stack rescores (~$9 in API + ~9h elapsed):

| Iteration | Scope | Gate [a] (mismatch ↓) | Gate [b] (applied ≥7) | Result |
|---|---|---|---|---|
| 1 | Structural rewire + "Level fit / IC-vs-leadership shape" paragraph | 79% (≥60% target) ✅ | 33 of 55 applied <7 (tolerance ≤7) ❌ | FAIL |
| 2 | Structural rewire only — seniority paragraph dropped | 72% ✅ | 22 of 55 applied <7 ❌ | FAIL |

## Why it didn't ship

Removing TIER 1 EXCEPTION's score-6 floor caused 22 of 55 applied jobs to drop below 7. Of those 22, the mix was **partly correct downgrades** (Sr DC Operations Technician at xAI 8→1 — operator was over-applying) and **partly over-corrections** (operator-shape ops/program-management roles dropping inappropriately).

The over-correction component was anticipated by the design spec's §8 risk row: *"Operator-side `## Title Calibration Notes` content from the prior #276 attempt over-fires now that ROLE-SHAPE CALIBRATION is gone — out of scope for this issue. If detected post-merge, the operator can edit `## Title Calibration Notes` directly (gitignored, no PR needed)."*

In practice that risk turned out to be too costly to validate. Hand-grading the 22 violations to separate "correct downgrade" from "over-fire" requires the operator's full domain knowledge. The operator doesn't have time to do that, and shipping a known-regression with a "fix it post-merge in gitignored config" handoff was a worse trade than walking away.

## What we learned (worth not re-attempting blindly)

1. **TIER 1 EXCEPTION's floor was load-bearing on a real signal — strategic preference + foot-in-the-door at named companies.** Replacing the floor with "factor it in as input" guidance was not strong enough to retain operator-applied jobs at score 7+. Any future rewrite that drops the floor needs a stronger STRATEGIC-PREFERENCE mechanism (not just guidance, possibly a soft floor) — or has to accept that applied-job score retention isn't the right gate.

2. **The applied-job set is mixed signal for verification.** Some applies are foot-in-the-door at TIER 1 companies that the operator wouldn't apply to today. Using applied-jobs-stay-≥7 as a hard gate validates "the new prompt agrees with last quarter's apply decisions," not "the new prompt is better." A future scorer change should consider a different verification corpus shape.

3. **Operator-side `## Title Calibration Notes` from the #276 era is overfitted to TIER 1 EXCEPTION.** Any future scorer-prompt restructure that touches TIER 1 EXCEPTION's role needs to plan for parallel cleanup of the operator's `## Title Calibration Notes`, not relegate it to "out of scope, edit post-merge."

4. **Verification rescore corpus extraction needs proper CSV quoting.** First iteration burned ~$3 + 2h on garbage rows because the 819-row corpus was dumped via sqlite3 CLI's `-separator $'\t'` with no quoting; JD content has embedded tabs and newlines. Use Python `csv.writer` with `QUOTE_ALL`. Lesson captured at `~/.claude/projects/-home-brockamer-Code-findajob/memory/feedback_sqlite_cli_dump_unsafe.md`.

5. **Long-running batch jobs need built-in healthchecks.** A row-20 sanity check would have caught the corrupted-corpus failure in 3 minutes instead of 2 hours. Lesson captured at `~/.claude/projects/-home-brockamer-Code-findajob/memory/feedback_long_running_batch_healthchecks.md`.

## What still needs scorer attention (separate, smaller scope)

- **Score-5/6 false positives in the operator's queue.** The original problem #276 was filed against (132 score-6 jobs hand-graded as ~88% mismatches) is still real. Walking away from the structural rewire doesn't fix it. Future approaches:
  - Operator-side `## Title Calibration Notes` enrichment (gitignored, no PR needed) — narrow, safe, doesn't touch tracked code
  - `scorer_prefilter.py` deterministic title-pattern additions (the locus split from the original #276 spec is still valid: title-deterministic = prefilter, JD-content = profile)
  - More aggressive pre-filter Stage 1 patterns for clearly-wrong titles (DC technician, junior, associate)

- **Cost-log token-estimate drift** (#304) — pre-existing rescore_all.py drift, unrelated to #285's failure. Still worth fixing eventually.

## Cost summary

- **Time:** ~9 hours of session work
- **API spend:** ~$9 (iter 1 corrupted ~$3 + iter 1 clean ~$3 + iter 2 ~$3)
- **Code changes shipped:** none (all on the abandoned branch)
- **Code changes shipped *adjacent* to this work:** #302 board UX fix, README polish, CLAUDE.md scheduler-row drift fix — all useful, all independent of the abandoned rewrite

## Pointers

- Spec (deleted with branch): `docs/superpowers/specs/2026-04-27-scorer-rewire-design.md`
- Plan (deleted with branch): `docs/superpowers/plans/2026-04-27-scorer-rewire.md`
- Iteration 1 gate report (saved on dev VM): `tmp/role_shape_285_gate_report.md` (overwritten by iter 2)
- Iteration 2 rescore CSV (saved on dev VM): `tmp/role_shape_285_rescore.csv` (763 rows, gitignored)
- Iteration 1 rescore CSV (saved on dev VM): `tmp/role_shape_285_rescore_partial.csv` (856 rows, ~95% garbage from corpus corruption — keep as a "this is what corruption looks like" example)

If a future session wants to revisit this approach, start from the spec/plan in the reflog of the deleted branch — but only after addressing learning #1 above (replace the floor with a stronger mechanism, not just "factor it in" guidance).
