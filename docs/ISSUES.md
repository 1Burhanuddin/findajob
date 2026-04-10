# Open Issues / Parking Lot

Tracked items that need implementation, investigation, or a decision.
Format: `- [ ]` open, `- [x]` closed. Add date and brief context when closing.

---

## Pipeline Enhancements

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

- [ ] **`cost_log` model name is hardcoded** *(Low)*
  `triage.py:789` and `rescore_all.py:200` hardcode `'openrouter:deepseek/deepseek-v3.2'`
  in the cost_log insert. If the scorer model is changed in `config/roles/job_scorer.md`,
  the cost_log will silently report the wrong model. Fix: read the model from the role file
  frontmatter or pass it through from the scorer.

- [ ] **Shared utility functions are duplicated** *(Low — refactor when convenient)*
  `load_env()`, `validate_llm_json()`, and `jd_is_usable()` are copy-pasted across
  `triage.py`, `rescore_all.py`, `prep_application.py`, and `find_contacts.py`.
  Fix: consolidate into `scripts/utils.py` (or extend `paths.py`). Not urgent — all copies
  are in sync — but creates a maintenance hazard when any one of them needs a change.

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

- [ ] **`score=None` on occasional jobs** *(Low)*
  Some jobs log `score=None` in `pipeline.jsonl` (e.g. "AI Tutor - Telugu" 2026-04-07).
  Likely scorer timeout or malformed LLM response — not a crash. No fallback or retry exists.
  Investigate: add explicit `None` check in `triage.py` score extraction and log as `score_error` event.
  A retry with backoff on timeout would be the full fix.

---

## Side Projects

- [ ] **Build comprehensive master resume from historical documents**
  Use PDFs of performance reviews, project summaries, and other career materials to extract
  detailed accomplishments, metrics, and stories. Feed these into the master resume to give
  the resume_tailor and cover_letter_writer much richer source material to draw from.
  This is a separate project that would significantly improve output quality across all roles.

---

## Completed

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

- [x] **Dashboard invisible to `manual_review` jobs with NULL relevance_score** *(closed 2026-04-09)*
  Dashboard query: `relevance_score >= 7 AND stage IN ('scored', 'manual_review')`.
  SQLite NULL comparison returns NULL (falsy), so jobs where the scorer timed out or
  returned invalid JSON (stage='manual_review', relevance_score=NULL) never appeared
  on Dashboard and couldn't be actioned by a human. Added OR clause for NULL-score manual_review.

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
