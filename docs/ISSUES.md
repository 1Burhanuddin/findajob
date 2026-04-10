# Open Issues / Parking Lot

Tracked items that need implementation, investigation, or a decision.
Format: `- [ ]` open, `- [x]` closed. Add date and brief context when closing.

---

## Pipeline Bugs (from 2026-04-10 triage run)

- [x] **Gmail digest emails ingested as jobs** *(closed 2026-04-10)*
  Added `startswith()` filter in `parse_jobs_from_email()` for "Jobs similar to/at/in"
  digest subject lines. Rejected 12 existing fake jobs in DB.

- [x] **Blank-company gmail_linkedin jobs keep entering DB** *(closed 2026-04-10)*
  `triage.py` now auto-rejects gmail_linkedin jobs with unresolvable company immediately
  after enrichment attempt. Row stays in DB with `reject_reason='Blank Company'`.

- [ ] **Duplicate jobs with and without company — fingerprint gap**
  "Critical Environment Operations Manager" exists twice: `company=Microsoft` (score 8)
  and `company=""` (score 5). Same for "Senior Manager, Data Center Operations, JoinOCI"
  (Oracle vs blank). Fingerprint includes company, so blank-company and resolved-company
  copies don't dedup. Fix: add a secondary dedup pass on `title + location` (ignoring
  company) for `gmail_linkedin` jobs, or dedup at scoring time by checking if a
  higher-scored version of the same title already exists.

- [x] **Feedback block over-correction — zero 9-10 scores** *(closed 2026-04-10)*
  Softened instruction: "score it LOW (1-4)" → "reduce by 2-3 points"; "weight heavily" →
  "consider"; added "Minimum score is always 1" guard. Monitor next 2-3 runs.

- [ ] **`sync_sheet.py` has no log confirmation**
  Called inline by `triage.py` with `subprocess.run(check=False)`. If it fails, there is
  no `pipeline.jsonl` event and no alert. Fix: add a `log_event('sync_complete', ...)` at
  the end of `sync_sheet.py` with row counts for each tab. Surface sync failures in
  `notify.py health-check`.

- [x] **LinkedIn JD missing for all gmail jobs** *(closed 2026-04-10)*
  Root cause: `extract_linkedin_job_id()` regex matched `linkedin.com/jobs/view/(\d+)`
  but gmail emails use `linkedin.com/comm/jobs/view/` URLs. The `/comm/` path segment
  was never matched → `api_id` always empty → every gmail_linkedin job scored without JD.
  Fix: regex now `linkedin\.com/(?:comm/)?jobs/view/(\d+)`. 353 existing jobs are
  backfillable. Next triage run will fetch JDs correctly for new gmail jobs.

---

## Pipeline Enhancements

- [ ] **`_applied` / `_rejected` archive folders need rclone target update** *(Low)*
  `poll_flags.py` now moves folders to `companies/_applied/` and `companies/_rejected/`
  instead of `_DONE`. The rclone bisync target (`gdrive:01 PROJECTS/Jobs To Apply For`)
  covers the whole `companies/` directory, so syncing works automatically. But the
  Google Drive folder names will show `_applied` and `_rejected` as top-level dirs.
  Confirm this is acceptable or update the Drive folder layout.

- [x] **3 jobs missing fit_score / probability_score** *(closed 2026-04-10)*
  Nscale Infrastructure Operations Manager (80.8/72.3) and Tenstorrent Field Application
  Engineer (77.2/77.7) confirmed populated. Issue resolved.

- [ ] **Populate `company_signal` column in Google Sheet**
  The column exists in the schema (`config/scoring_schema.json` and Sheet) but is never written.
  Candidate approach: extract signal from `company_researcher` (Perplexity) output during
  `prep_application.py` and back-fill via `sync_sheet.py`. Signals to surface: funding events,
  layoffs, headcount trajectory, product launches (last 6 months).

- [x] **`ingest_form.py` fingerprint diverges from `triage.py`** *(closed 2026-04-09)*
  Fixed: `ingest_form.py` now uses the same `normalize()`-based fingerprint as `triage.py`
  (title + company + location), replacing the old URL+company+title approach.

- [ ] **Resume exceeding 2 pages despite margin and bullet count rules** *(Low)*
  reference.docx margins set to 0.4" L/R, 0.5" T/B, and bullet count limits enforced in
  resume_tailor prompt, but some resumes still render at 3 pages in .docx output. May need
  pandoc geometry flags, font size adjustments in reference.docx, or tighter bullet count
  limits for roles with long bullets. Lower priority; user can trim manually.

- [x] **`cost_log` model name is hardcoded** *(closed 2026-04-10)*
  Added `_role_model('job_scorer')` helper in both `triage.py` and `rescore_all.py` that
  reads the `model:` field from the role's YAML frontmatter at startup. `SCORER_MODEL`
  constant replaces the hardcoded string in both cost_log inserts.

- [ ] **Shared utility functions are duplicated** *(Low — refactor when convenient)*
  `load_env()`, `validate_llm_json()`, and `jd_is_usable()` are copy-pasted across
  `triage.py`, `rescore_all.py`, `prep_application.py`, and `find_contacts.py`.
  Fix: consolidate into `scripts/utils.py` (or extend `paths.py`). Not urgent — all copies
  are in sync — but creates a maintenance hazard when any one of them needs a change.

- [ ] **`apply-reminder` notification should include daily checklist** *(Low)*
  The motivational nudge (`notify.py apply-reminder`) is just a quip. Add a brief
  daily task checklist after the quip to keep the workflow top-of-mind:
  1. Review high-scoring matches on the Dashboard — Flag for Prep or Reject each one
  2. Check "Ready to Apply" jobs — review generated materials, then Apply or Reject
  3. Triage the Review tab — Promote promising jobs to Dashboard or Reject
  4. Scan Sheet1 for any target-company jobs that may have been mis-scored
  5. Check ntfy health notification for pipeline errors or warnings
  Include real counts from the DB (e.g., "3 jobs awaiting review, 2 ready to apply,
  47 in manual review") so the checklist is actionable, not generic.

- [x] **Review tab flooded with obvious mismatches — prefilter expansion** *(closed 2026-04-10)*
  Expanded `_HARD_REJECT_PATTERNS` with ~40 new patterns across 12 categories (healthcare,
  construction, AV/events, food service, manufacturing, etc.). Added `_DC_CONTEXT_RE`
  override so titles containing "data center" aren't false-positive rejected. Added
  Stage 1.5 post-LLM-failure filter: if scorer JSON parse fails AND title matches
  hard-reject pattern, auto-score 1 instead of manual_review. 78 of 374 manual_review
  jobs would now be caught. Remaining ~296 are mostly legitimate DC jobs with missing JDs
  or genuinely ambiguous Tier 1 edge cases.

- [ ] **Drive folder state should stay consistent with DB stage at all times**
  `poll_flags.py` currently handles two transitions: rejected → `_rejected/` and
  applied → `_applied/`. But several gaps remain:
  **1. Missing folder moves for later stages:** Interviewing, Offer, and Withdrew update
  the DB stage but don't move the folder — it stays in `_applied/`. Should there be
  `_interviewing/` or similar? Or is `_applied/` the final active location and only the
  marker file changes? Needs a decision.
  **2. No reconciliation:** If rclone fails silently, or a folder is manually moved on disk
  or Drive, the DB `prep_folder_path` goes stale. Need a periodic reconciliation check
  (e.g., in `notify.py health-check`) that verifies `prep_folder_path` exists for all
  `materials_drafted`/`applied`/`interview` jobs and flags mismatches.
  **3. No rclone failure detection:** `poll_flags.py` and `prep_application.py` fire rclone
  with `check=False` / `Popen` (fire-and-forget). If the sync fails, no retry and no alert.
  Fix: capture rclone exit code, log failures, and surface in health check.
  **4. Reverse sync not supported:** Local is authoritative (`rclone sync` one-way push),
  so Drive-side moves are overwritten. This is by design, but if the user manually
  reorganizes folders on Drive, those changes are lost on next sync. Document this
  as expected behavior, or add a pre-sync check that warns before clobbering.
  Goal: any stage transition that has a folder should leave the filesystem, DB, and
  Drive in a consistent state, with health checks to detect and alert on drift.

---

## Infrastructure / Ops

- [ ] **RAG source documents — manual editing pass** *(Low)*
  Content quality of `rag_sources/` docs hasn't been reviewed since initial setup.
  Deferred until pipeline is stable. Low urgency — RAG only used in REPL context.

- [ ] **`regen_resumes.py` title extraction is best-effort** *(Low)*
  Parses role title from `REVIEW_CHECKLIST.md` header — may return empty for some folders.
  Only affects this diag script, not the main pipeline. Review v2 output for any folder
  where title hint shows `(none found)` in the run log.

- [x] **`resume_tailor` ignores bullet count and structure rules** *(closed 2026-04-09)*
  Fixed: restructured prompt with FORMAT LAW at top, explicit violation examples, SELF-CHECK
  checklist, and HARD LIMITS for bullet counts. Added `validate_resume.py` for mechanical
  verification. Post-fix: 0 HIGH violations across all 13 resumes. Added think-tag stripping
  for `:thinking` models.

- [x] **`score=None` on occasional jobs** *(closed 2026-04-10)*
  `score_job()` now catches `TimeoutExpired` (was uncaught — would crash the loop iteration),
  checks for non-zero exit / empty stdout, and logs distinct `score_error` events with
  `reason=timeout|subprocess_failed|null_score`. All failure paths return a structured
  `manual_review` dict instead of propagating exceptions.

---

## Side Projects

- [ ] **Build comprehensive master resume from historical documents**
  Use PDFs of performance reviews, project summaries, and other career materials to extract
  detailed accomplishments, metrics, and stories. Feed these into the master resume to give
  the resume_tailor and cover_letter_writer much richer source material to draw from.
  This is a separate project that would significantly improve output quality across all roles.

---

## Completed

- [x] **Poller systemd service failing — KillMode** *(closed 2026-04-10)*
  `findajob-poller.service` was `Type=oneshot` with default `KillMode=control-group`.
  Popen children (sync_sheet.py, prep_application.py) were killed when the main process
  exited, causing service timeout and failed state. "Flag for Prep" actions were silently
  ignored for 30+ min. Fix: added `KillMode=process` and `TimeoutStartSec=120` to poller
  service, same for triage service. Config-only fix (systemd unit files, not in repo).

- [x] **Sheet1 archival, Review tab, and health checks** *(closed 2026-04-10)*
  Sheet1 now filters: only syncs jobs with `score>=5`, lifecycle stages, `<14d old`, or target
  company. Low-score old jobs stay in DB only. New "Review" tab for `stage=manual_review` jobs
  (374 remaining after bulk-rejecting 153 blank-company entries). Review tab has STATUS=Promote
  (sets score=7, moves to Dashboard) and REJECT_REASON dropdowns. `poll_flags.py` reads both
  Dashboard and Review tabs. `notify.py health-check` now warns on: Sheet1 > 1000 rows,
  manual_review backlog > 100, target-company jobs scored ≤4 in last 7 days.
  `setup_sheets.py` creates and formats the Review tab (dropdowns, hidden fingerprint, banding).

- [x] **`_applied` / `_rejected` archive folder strategy** *(closed 2026-04-10)*
  Replaced single `_DONE` with `companies/_applied/` and `companies/_rejected/`.
  Rejections drop a `REJECTED_{reason}_{date}.txt` marker file for historical context.
  `poll_flags.py` updated; existing `_DONE` contents migrated; DB paths corrected.

- [x] **Dashboard flooded with 527 null-score `manual_review` jobs** *(closed 2026-04-10)*
  Prior fix added `OR (stage='manual_review' AND relevance_score IS NULL)` to catch scorer-timeout
  jobs. But 527 jobs (scorer failures + "missing JD" flags) matched, flooding the dashboard.
  Fix: removed that OR clause. High-scoring manual_review jobs (score>=7) still appear via the
  first condition. Null-score scorer-timeout jobs stay invisible — acceptable vs. flooding the queue.

- [x] **Dashboard sync to companies folder state** *(closed 2026-04-10)*
  `sync_sheet.py` now skips `materials_drafted` jobs whose `prep_folder_path` no longer exists
  on disk (e.g. moved to `_applied`/`_rejected` without a DB update). Prevents stale dashboard rows.

- [x] **`<think>` tag leakage from Claude `:thinking` models** *(closed 2026-04-10)*
  `aichat-ng` includes thinking tokens in stdout. Fixed: `aichat()` in `prep_application.py`
  strips all `<think>...</think>` blocks via regex after every call.

- [x] **Fit analysis added to company briefing** *(closed 2026-04-10)*
  New `fit_analyst` role (perplexity:sonar-reasoning-pro): 6-dim fit matrix + 3-dim
  probability assessment, 0-100% scale. Scores stored in DB and surfaced in Dashboard
  (cols D/E) with conditional formatting (red <40%, yellow 40-69%, green ≥70%).

- [x] **Pipeline reordered: briefing-first** *(closed 2026-04-10)*
  Company briefing now runs as Step 2 (before resume and cover letter). Resume and cover
  letter both receive `briefing[:3000]` as context. No extra LLM calls — same steps,
  better output quality for all downstream documents.

- [x] **Resume formatting and output rules overhaul** *(closed 2026-04-10)*
  resume_tailor role rewritten: name "Daniel Brock" enforced, em dash prohibition,
  middle-dot heading format, contract notation for TigerDC/Philly DA/Vytalize,
  LAVM cert "pending 2026", 2-page limit, Meta/Facebook restored, Forty Hertz italic note.
  cover_letter_writer: contact line from profile (no hardcoded PII), em dash prohibition.
  briefing_writer: emoji section headings, stories from master resume.
  validate_resume.py: em dash and name checks added.

- [x] **`prep_application.py` rclone used `--create-empty-src-dirs`** *(closed 2026-04-09)*
  Same flag that was broken in `poll_flags.py` — also existed in `prep_application.py:237`.
  The apt-installed rclone version doesn't support this flag for bisync.
  Removed. Every prep run would have triggered a rclone error silently (check=False).

- [x] **`triage.py` `find_contacts()` missing blank-company guard** *(closed 2026-04-09)*
  The inline `find_contacts()` in `triage.py` (used for triage-time contact lookup, not outreach)
  used `company.lower() in row['Company'].lower()` — which is True for blank company rows
  (`'' in 'anything'` is True). Added explicit guard for blank company and blank contact_co.
  The separate `find_contacts.py` already had the correct guard.

- [x] **`triage.py` double LinkedIn API call for gmail_linkedin company enrichment** *(closed 2026-04-09)*
  `fetch_jd()` called `fetch_linkedin_job_data(api_id)` for the JD, then main() called it
  again at line 740 to resolve the company — doubling RapidAPI quota consumption.
  Fixed by caching `result['company']` in `job['_linkedin_company']` during the first call,
  then reading the cache in main() instead of re-calling the API.

- [x] **`rescore_all.py` overwrote stage for post-scoring jobs** *(closed 2026-04-09)*
  Query included ALL jobs with JD text, including applied/interview/offer/rejected/withdrawn.
  Running rescore would reset their stage to 'scored' or 'manual_review', corrupting
  pipeline state. Added `AND stage IN ('scored', 'manual_review', 'enriched')` filter.

- [x] **Dashboard flooded with 527 null-score `manual_review` jobs** *(closed 2026-04-10)*
  Prior fix added `OR (stage='manual_review' AND relevance_score IS NULL)` to catch scorer-timeout
  jobs. But 527 jobs (scorer failures + "missing JD" flags) matched, flooding the dashboard.
  Fix: removed that OR clause. High-scoring manual_review jobs (score>=7) still appear via the
  first condition. Null-score scorer-timeout jobs stay invisible — acceptable vs. flooding the queue.

- [x] **`audit_log` missing index on `job_id`** *(closed 2026-04-09)*
  `init_db.py` had no index on `audit_log(job_id)`. Added `CREATE INDEX IF NOT EXISTS`.
  Applied to live DB immediately.

- [x] **`scorer_prefilter.py` TIER1 missing CoreWeave, Crusoe, Astera Labs** *(closed 2026-04-09)*
  These three are in the target company list (CLAUDE.local.md) but were absent from TIER1,
  so jobs at those companies with missing JD would score 5 instead of 6. Added to frozenset.

- [x] **`poll_flags.py` rclone used `--create-empty-src-dirs`** *(closed 2026-04-09)*
  Flag not supported by apt-installed rclone version for bisync. Removed.

- [x] **`config/ntfy_topic.txt` missing on Linux** *(closed 2026-04-09)*
  `triage.py` and `prep_application.py` inline `notify()` read from this file.
  File was not transferred during Mac → Linux migration and not created by bootstrap.
  Created the file. Updated both `notify()` functions to fall back to `data/.env NTFY_TOPIC`
  if file is missing, making fresh clones self-healing. Added to bootstrap --check.

- [x] **`scripts/setup_launchd.sh` tracked by git** *(closed 2026-04-09)*
  Mac-only launchd setup script with outdated labels (`com.OWNER.jobpipeline.*`) and only
  3 of the current 10 agents. Gitignored and removed from tracking.

- [x] **Prep triggered for blank-company and Dice-wrapper listings** *(closed 2026-04-08)*
  Fixed in `poll_flags.py`: `AGGREGATOR_PREFIXES` tuple + `is_valid_company()` guard skips blank or
  aggregator-wrapped companies before triggering `prep_application.py`.

- [x] **pandoc YAML parse error on cover letter files** *(closed 2026-04-09)*
  `cover_letter_DRAFT.md` files that began with `--- DRAFT ---` were misread by pandoc as
  YAML frontmatter. Fixed in `config/roles/cover_letter_writer.md`: rule 4 now explicitly
  states `# DRAFT — REQUIRES HUMAN EDITING` (plain Markdown heading, not YAML delimiters).
  Already in effect — any new cover letter should use the heading format.

- [x] **RSS/Greenhouse feeds returning 0 jobs** *(closed 2026-04-07)*
  Root cause: Greenhouse deprecated all RSS endpoints platform-wide (`/jobs.rss` returns 404 for all slugs, all companies).
  Fix: replaced `fetch_rss_jobs()` with `fetch_greenhouse_jobs()` using the public JSON API
  (`boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true`). Same `feed_urls.txt` slugs, no auth required.
  989 jobs now available across 10 Tier-1 targets (CoreWeave, xAI, Tenstorrent, Astera Labs, Cerebras,
  Lightmatter, MatX, SambaNova, Etched, Nscale). Shipped in `efcfc79`.

- [x] **All prior `companies/` resumes regenerated with master resume** *(closed 2026-04-07)*
  Original v1 resumes used a `[Master resume not found]` fallback due to a path issue.
  `regen_resumes.py` run on all pre-existing folders — every folder now has a `tailored_resume_DRAFT_v2`.
  Recent folders (Fluidstack, PlayStation) generated after fix; v1 is correct, no v2 needed.

- [x] **Gmail ingestion company enrichment validated** *(closed 2026-04-07)*
  295 `gmail_linkedin` + 22 `gmail_google` jobs confirmed in DB from production runs since 2026-04-01.
  Enrichment logic (LinkedIn API fallback for blank-company gmail_linkedin jobs) is deployed and running.

- [x] **21 blank-company contacts in connections.csv** *(closed 2026-04-07)*
  Blank-company guard confirmed in `find_contacts.py` lines 19-21:
  `if not s or not c: return False`. Permanent — CSV rows won't be cleaned.
