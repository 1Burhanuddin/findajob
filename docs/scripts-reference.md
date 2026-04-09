# Scripts Reference

All scripts live in `scripts/`. Diag scripts live in `scripts/diag/` and are run manually only.

All scripts import `BASE`, `AICHAT`, `PANDOC`, and/or `RCLONE` from `scripts/paths.py`.
Never hardcode binary paths in scripts — add overrides to `config/paths.env` instead.

---

## Core Pipeline Scripts

### `triage.py`
**Run by:** scheduler (daily 7:00 AM)
**No arguments.**

Fetches jobs from all sources, deduplicates, enriches with JD text, scores with LLM, writes to SQLite. Calls `sync_sheet.py` at the end.

**Sources:**
- LinkedIn and Indeed via RapidAPI jobs-api14
- Gmail OAuth2 (LinkedIn job emails, Indeed digests, recruiter messages)
- Greenhouse JSON API (slugs from `config/feed_urls.txt`)

**Key events logged:** `triage_started`, `job_ingested`, `job_deduplicated`, `job_scored`, `pipeline_complete`

---

### `prep_application.py`
**Run by:** `poll_flags.py` (when user flags a job); also callable manually
**Args:** `company title url job_id`

Generates a full application package for one job. LLM calls run sequentially.

**Outputs (in `companies/{Company}_{AbbrevTitle}_{date}_{time}/`):**
- `tailored_resume_DRAFT.md` + `.docx`
- `tailored_resume_CHANGES.md`
- `cover_letter_DRAFT.md` + `.docx`
- `company_briefing.md` + `.docx`
- `outreach_*.txt` (one per matching contact, if any)
- `job_description.txt`
- `REVIEW_CHECKLIST.md`

**After completion:** updates DB to `stage=materials_drafted`, calls `sync_sheet.py`, sends ntfy notification, triggers rclone bisync.

---

### `poll_flags.py`
**Run by:** scheduler (every 30 min)
**No arguments.**

Reads `Dashboard!A2:C10000` from Google Sheets. Columns: STATUS, REJECT_REASON, fingerprint.

**Logic (in priority order):**
1. If `REJECT_REASON` is set and job not already rejected → calls `handle_rejection()`: updates DB, writes `feedback_log`, moves prep folder to `_done/`, fires rclone bisync (non-blocking)
2. If `STATUS` is `Applied/Interviewing/Offer/Withdrew` → updates DB stage
3. If `STATUS` is `Flag for Prep` and job is in `scored/manual_review/enriched` stage → validates company (not an aggregator) → calls `prep_application.py`

---

### `sync_sheet.py`
**Run by:** end of triage, end of prep; also callable manually
**No arguments.**

Reads SQLite, writes to Sheet1 (full archive) and Dashboard (actionable queue).

**Dashboard filter:** `relevance_score >= 7 AND stage IN ('scored', 'manual_review')` OR `stage = 'materials_drafted'`. Materials_drafted jobs float to the top (sorted first).

**STATUS value in Dashboard:** derived from DB — `Ready to Apply` if `stage=materials_drafted`, `Flag for Prep` if `apply_flag=1 AND stage≠materials_drafted`, else empty.

---

### `setup_sheets.py`
**Run by:** manually (once on new sheet; safe to re-run)
**No arguments.**

Creates and formats the Dashboard tab. Sets up:
- STATUS dropdown (col A) with conditional row highlighting
- REJECT_REASON dropdown (col B) with per-option colors
- Remote status color coding (col H): Remote=red, Hybrid=yellow, On-site=green
- Contacts amber highlight (col I)
- Row banding
- Column widths and hidden columns
- Rejected row formatting on Sheet1 (grey)

---

### `notify.py`
**Run by:** scheduler (5 subcommands on different schedules); also callable manually
**Args:** one subcommand

| Subcommand | What it sends |
|---|---|
| `daily-stats` | Queue depth, today's new jobs, last triage timestamp |
| `health-check` | Errors from last 25h of logs, last `pipeline_complete` event |
| `issues-ping` | Open items from `docs/ISSUES.md` |
| `apply-reminder` | Rotating motivational nudge to submit an application |
| `feedback-review` | Alert when `feedback_log` has ≥ 10 entries to analyze |

ntfy topic is read from `NTFY_TOPIC` in `data/.env`.

---

### `find_contacts.py`
**Run by:** `prep_application.py` (step 5)
**Args:** `company jd_text_excerpt outdir`

Reads `data/connections.csv`, finds LinkedIn connections at the target company, generates personalized outreach drafts for each match via aichat-ng.

**Output:** `{outdir}/outreach_{FirstName}_{LastName}.txt` for each match.

**Key guard:** `company_match()` always checks `if not s or not c: return False` — blank company strings would otherwise match everything.

---

### `ingest_form.py`
**Run by:** scheduler (every 30 min)
**No arguments.**

Polls the Google Form responses sheet for new rows. For each unprocessed row:
1. Creates a fingerprint from `url|company|title`
2. Deduplicates against existing DB jobs
3. Inserts as `source='manual_form'`, `stage='scored'`, `relevance_score=8`
4. Writes 'Processed: {timestamp}' to col J in the responses sheet
5. If "Generate folder" column = yes/y/true → calls `prep_application.py`
6. Calls `sync_sheet.py` after all ingestions

---

### `manual_prep.py`
**Run by:** manually (when you have a job outside the pipeline)
**Args:** optional path to job file (default: `manual_job.txt`)

File format:
```
company: CompanyName
title: Job Title
url: https://...
---
Full JD text below this line
```

Inserts job into DB and calls `prep_application.py` immediately.

---

### `scorer_prefilter.py`
**Run by:** imported by `triage.py` and `rescore_all.py` — not called directly
**Function:** `prefilter_score(title, jd_text, company) → (score, reason) or None`

Two-stage deterministic filter:
- Stage 1: title regex → score 1 (hard reject domains: healthcare, pure SWE, sales, security, etc.)
- Stage 2: in-domain title + no JD → score 5 or 6 (reasonable guess without content)

Returns `None` if the job should proceed to LLM scoring.

---

### `rescore_all.py`
**Run by:** manually (after model or prompt changes)
**No arguments.**

Re-runs the scorer on all jobs that have JD text. Use after changing `job_scorer` role or switching scorer model.

---

### `rename_folders.py`
**Run by:** manually (idempotent)
**No arguments.**

Renames `companies/` folders from old format (`{Company}_{date}_{time}`) to new format (`{Company}_{AbbrevTitle}_{date}_{time}`). Looks up DB for title. Updates `prep_folder_path` in DB. Safe to re-run — skips already-renamed folders.

---

### `init_db.py`
**Run by:** once on new install
**No arguments.**

Creates `data/pipeline.db` with all tables: `jobs`, `audit_log`, `feedback_log`. Safe to re-run — uses `CREATE TABLE IF NOT EXISTS`.

---

### `init_sheet.py`
**Run by:** once on new install, or after sheet restructure
**No arguments.**

Writes column headers to Sheet1 row 1.

---

## Diag Scripts (`scripts/diag/`)

Run manually for debugging. Not part of normal pipeline operation.

### `probe_scorer.py`
Shows raw aichat-ng scorer output for `manual_review` rows. Prints title, company, raw stdout, parsed score.

### `regen_resumes.py`
Re-runs `resume_tailor` for every folder in `companies/`. Outputs `tailored_resume_DRAFT_v2.md` and `.docx` alongside existing files. Does not overwrite originals.

### `debug_contacts.py`
Shows contact matching diagnostics for a batch of jobs. Useful for debugging false positive/negative company name matches.
