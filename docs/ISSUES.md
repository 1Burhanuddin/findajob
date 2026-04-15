# Open Issues

> **Kanban board:** https://github.com/users/brockamer/projects/1
> The GitHub Project board is the source of truth for active work. This file is a
> human-readable summary. Each open item below links to its GitHub Issue.

Tracked items that need investigation, a fix, or a decision.
Closed items are collapsed at the bottom for historical reference.

---

## Pipeline Gaps

- [ ] **No distinction between user-rejection and company-rejection** `MED` [#5](https://github.com/brockamer/findajob/issues/5)
  When a company passes on an application, the same REJECT_REASON dropdown is used
  as "I decided this isn't a fit." Both set `stage=rejected`, write to `feedback_log`,
  and move the folder to `_rejected/`. This loses signal:
  1. Applied folders should stay in `_applied/` as application history.
  2. Company rejections contaminate the scorer feedback loop — a company passing
     doesn't mean the job was a bad match.

  **Proposed fix:**
  - New STATUS dropdown: `"Not Selected"`
  - New stage: `not_selected` — folder stays in `_applied/`, no `feedback_log` write
  - `poll_flags.py` handles like Applied/Interviewing (stage update, no folder move)
  - `analyze_feedback.py` excludes `not_selected` from false-positive analysis
  - Optionally track company rejection metadata (response time, rejection rate by tier)

---

## Resume / Materials

- [ ] **Resume generator not hyperlinking email and LinkedIn** `MED` [#24](https://github.com/brockamer/findajob/issues/24)
  Tailored resumes output the email address and LinkedIn profile URL as plain text
  instead of clickable hyperlinks. Pandoc + reference.docx should render `mailto:`
  and `https://` links — need to verify the Markdown source includes link syntax
  and that the docx template preserves hyperlink styling.

---

## Data Hygiene

- [ ] **GDrive: stale copies may remain from bisync era** `LOW` [#6](https://github.com/brockamer/findajob/issues/6)
  The architectural fix (push-only + Drive-side moves) is shipped. But 4 stale
  top-level Drive copies and 1 duplicate (_applied + _rejected for Tenstorrent)
  may still exist on Drive. Also: two AWS waitlisted jobs share one prep folder
  (identical abbrev_title + same batch timestamp). Verify and clean up manually.
  **Ref:** `plans/2026-04-15-gdrive-sync-audit.md` Tasks 3-5.

---

## Closed

<details>
<summary>Pipeline Bugs — all fixed 2026-04-10 through 2026-04-15</summary>

- [x] Gmail digest emails ingested as jobs *(2026-04-10)*
- [x] Blank-company gmail_linkedin jobs keep entering DB *(2026-04-10)*
- [x] Duplicate jobs — fingerprint gap after company resolution *(2026-04-10)*
- [x] Feedback block over-correction — zero 9-10 scores *(2026-04-10)*
- [x] `sync_sheet.py` has no log confirmation *(2026-04-10)*
- [x] LinkedIn JD missing for all gmail jobs (`/comm/` path) *(2026-04-10)*
- [x] LLM output validation failures (Remote-Friendly, score clamping) *(2026-04-15)*
- [x] SQLite `database is locked` crash during concurrent access *(2026-04-15)*

</details>

<details>
<summary>Pipeline Enhancements — all shipped 2026-04-08 through 2026-04-15</summary>

- [x] `_applied`/`_rejected` archive folder strategy *(2026-04-10)*
- [x] 3 jobs missing fit_score/probability_score *(2026-04-10)*
- [x] `company_signal` column deprecated *(2026-04-10 — won't fix)*
- [x] `ingest_form.py` fingerprint aligned with `triage.py` *(2026-04-09)*
- [x] Resume 2-page limit via reference.docx formatting *(2026-04-10)*
- [x] `cost_log` model name from role YAML, not hardcoded *(2026-04-10)*
- [x] Shared utilities consolidated to `scripts/utils.py` *(2026-04-10)*
- [x] Apply-reminder includes daily checklist with DB counts *(2026-04-10)*
- [x] Prefilter expansion — 40 new hard-reject patterns *(2026-04-10)*
- [x] Drive folder state consistent with DB stage *(2026-04-10)*
- [x] Dashboard status lifecycle (Prep in Progress, Regenerate) *(2026-04-14)*
- [x] Drive sync: push-only + server-side moves *(2026-04-14)*
- [x] Rejected Applications tab with Drive links *(2026-04-14)*
- [x] Drive consistency health checks *(2026-04-14)*
- [x] CI failure monitoring *(2026-04-15)*
- [x] User-Agent headers + 429 backoff on fetchers *(2026-04-15)*

</details>

<details>
<summary>Quality & Security — closed 2026-04-11</summary>

- [x] PII / proprietary info audit of all tracked files *(2026-04-11)*
  Full audit. Pre-commit hook blocks future PII. See `docs/GENERALIZATION.md`.

</details>

<details>
<summary>Resilience — all fixed 2026-04-12</summary>

- [x] Recurring systemd timers stop firing after boot *(2026-04-12)*
- [x] Triage silently completes with 0 jobs during DNS outage *(2026-04-12)*

</details>

<details>
<summary>Infrastructure / Ops — closed</summary>

- [x] `resume_tailor` ignores bullet count and structure rules *(2026-04-09)*
- [x] `score=None` on occasional jobs *(2026-04-10)*
- [x] JD text truncated at 8,000 chars — 16.6% of jobs affected *(2026-04-10)*
- [x] Duplicate company folders on Flag for Prep *(2026-04-10)*
- [x] Poller systemd service failing — KillMode *(2026-04-10)*
- [x] Sheet1 archival, Review tab, health checks *(2026-04-10)*
- [x] Dashboard flooded with 527 null-score jobs *(2026-04-10)*
- [x] Dashboard sync to companies folder state *(2026-04-10)*
- [x] `<think>` tag leakage from Claude `:thinking` models *(2026-04-10)*
- [x] Fit analysis added to company briefing *(2026-04-10)*
- [x] Pipeline reordered: briefing-first *(2026-04-10)*
- [x] Resume formatting and output rules overhaul *(2026-04-10)*
- [x] Various minor fixes: rclone flags, blank-company guards, double API calls,
  rescore_all stage filter, audit_log index, TIER1 gaps, ntfy_topic fallback,
  launchd script cleanup, aggregator/Dice guard, pandoc YAML error,
  Greenhouse API migration, resume regeneration, Gmail enrichment,
  blank-company contacts *(2026-04-07 through 2026-04-09)*

</details>
