# Architecture

## Overview

Two distinct workflows, both scheduler-driven:

| Workflow | Trigger | Duration | Output |
|---|---|---|---|
| **Daily Triage** | 7:00 AM via scheduler | 30–60 min | 100–500 jobs scored and written to SQLite |
| **Prep** | User flags a job in the Dashboard | 5–10 min | Folder with resume, cover letter, briefing, outreach drafts |

Everything between them is mediated by SQLite. The Google Sheet is a synced view — not the source of truth.

---

## Daily Triage Pipeline

```
┌─────────────────────────────────────────────────────────┐
│                    triage.py (7:00 AM)                  │
└──────────────────────┬──────────────────────────────────┘
                       │
          ┌────────────┴────────────┐
          │                         │
  ┌───────▼──────────┐   ┌──────────▼──────────┐
  │  Gmail OAuth2    │   │  jobs-api14 RapidAPI │
  │  - LinkedIn jobs │   │  - LinkedIn search   │
  │  - Indeed digest │   │  - Indeed search     │
  │  - Recruiter msg │   │  - /v2/linkedin/get  │
  └───────┬──────────┘   └──────────┬──────────┘
          └────────────┬────────────┘
                       │
          ┌────────────▼────────────────┐
          │  Greenhouse JSON API        │
          │  (per slug in feed_urls.txt)│
          └────────────┬────────────────┘
                       │
          ┌────────────▼────────────────┐
          │  clean_title() + clean_company() │
          │  SHA-256 fingerprint dedup  │
          └────────────┬────────────────┘
                       │
          ┌────────────▼────────────────────────────┐
          │  scorer_prefilter.py                    │
          │  Stage 1: title regex → score 1, skip   │
          │  Stage 2: in-domain, no JD → score 5/6  │
          └────────────┬────────────────────────────┘
                       │  (jobs that pass both stages)
          ┌────────────▼────────────────┐
          │  aichat-ng job_scorer       │
          │  Model: DeepSeek v3.2       │
          │  Profile injected directly  │
          │  Output: JSON + validation  │
          └────────────┬────────────────┘
                       │
          ┌────────────▼────────────────┐
          │  SQLite write (pipeline.db) │
          │  Audit log per transition   │
          └────────────┬────────────────┘
                       │
          ┌────────────▼────────────────┐
          │  sync_sheet.py              │
          │  Sheet1 (archive)           │
          │  Dashboard (actionable)     │
          └─────────────────────────────┘
```

---

## Prep Workflow

```
User sets STATUS = "Flag for Prep" in Dashboard
          │
          ▼
poll_flags.py (runs every 30 min)
  reads Dashboard!A2:C10000
  matches fingerprint → DB job
  validates company (not an aggregator)
          │
          ▼
prep_application.py (runs in foreground)
  Loads JD from DB (never re-curls)
  Loads profile.md + master_resume.md (direct injection, no RAG)
          │
    ┌─────┴──────────────────────────────────────┐
    │  Sequential LLM calls (aichat-ng):          │
    │  1. resume_tailor → tailored_resume_DRAFT.md │
    │  2. resume_change_reviewer → CHANGES.md     │
    │  3. cover_letter_writer → cover_letter_DRAFT.md │
    │  4. company_researcher (Perplexity sonar-pro) │
    │  5. briefing_writer → company_briefing.md   │
    │  6. find_contacts.py → outreach_*.txt       │
    └─────┬──────────────────────────────────────┘
          │
    pandoc converts .md → .docx for each document
          │
    DB updated: stage = materials_drafted
    sync_sheet.py: Dashboard STATUS → "Ready to Apply"
    ntfy notification sent
    rclone bisync: companies/ → Google Drive
```

---

## Data Model

### SQLite Tables

**`jobs`** — one row per unique job posting
```
id TEXT PRIMARY KEY          -- generated UUID or "manual-{hex}"
fingerprint TEXT UNIQUE      -- SHA-256[:16] of normalized title+company+url
source TEXT                  -- linkedin_jobsapi | indeed | greenhouse | gmail_linkedin | gmail_google | manual | manual_form
title TEXT
company TEXT
location TEXT
remote_status TEXT           -- Remote | Hybrid | On-site | Unknown
url TEXT
raw_jd_text TEXT             -- full JD text fetched at ingest time
relevance_score INTEGER      -- 1–10 from LLM scorer
interview_likelihood INTEGER -- 1–10 from LLM scorer
ai_notes TEXT                -- LLM rationale
score_status TEXT            -- scored | manual_review | prefiltered
stage TEXT                   -- discovered | enriched | scored | manual_review |
                             --   materials_drafted | applied | interview | offer | withdrawn | rejected
apply_flag INTEGER           -- 0/1, mirrors Dashboard STATUS
reject_reason TEXT
comp_estimate TEXT
known_contacts TEXT
stage_updated TEXT           -- ISO timestamp of last stage change
prep_folder_path TEXT        -- absolute path to companies/ subfolder
created_at TEXT
updated_at TEXT
```

**`audit_log`** — immutable record of every field change
```
id INTEGER PRIMARY KEY AUTOINCREMENT
job_id TEXT
field_changed TEXT
old_value TEXT
new_value TEXT
changed_at TEXT DEFAULT (datetime('now'))
```

**`feedback_log`** — rejection history for pattern analysis
```
id INTEGER PRIMARY KEY AUTOINCREMENT
job_id TEXT
title TEXT
company TEXT
relevance_score INTEGER
reject_reason TEXT
jd_excerpt TEXT              -- first 500 chars of JD
logged_at TEXT DEFAULT (datetime('now'))
```

---

## Google Sheet Layout

### Sheet1 — Full Archive (A–N)
All jobs that passed dedup. Read-only reference view.

| Col | Field | Notes |
|---|---|---|
| A | fingerprint | Hidden — used by poll_flags.py |
| B | APPLY_FLAG | Checkbox (TRUE/FALSE) |
| C | relevance_score | |
| D | title | |
| E | company | |
| F | location | |
| G | remote_status | |
| H | stage | |
| I | known_contacts | |
| J | comp_estimate | |
| K | ai_notes | |
| L | date_found | |
| M | source | |
| N | url | |

### Dashboard — Actionable Queue (A–L)
Filter: `score >= 7 AND stage IN (scored, manual_review)` OR `stage = materials_drafted`.
poll_flags.py reads this tab every 30 min.

| Col | Field | Notes |
|---|---|---|
| A | STATUS | Dropdown — user sets this |
| B | REJECT_REASON | Dropdown — triggers rejection workflow |
| C | fingerprint | Hidden |
| D | relevance_score | |
| E | title | Hyperlink to job URL |
| F | company | |
| G | location | |
| H | remote_status | Color-coded |
| I | known_contacts | Amber when non-empty |
| J | comp_estimate | |
| K | ai_notes | |
| L | date_found | |

**STATUS lifecycle:**
`(empty)` → `Flag for Prep` *(user)* → prep runs → `Ready to Apply` *(system)* → `Applied` *(user)* → `Interviewing` → `Offer` / `Withdrew`

**REJECT_REASON:** setting any value triggers: stage=rejected, feedback_log entry, folder move to `_done/`, immediate rclone bisync.

---

## Key Design Decisions

| Decision | Why |
|---|---|
| SQLite as canonical store | Sheets-as-database creates race conditions and blocks programmatic queries. SQLite is ACID, queryable, and zero-config. |
| Direct profile injection (not RAG) | RAG chunking drops contact info, employer names, and dates. Profile is short enough to inject raw. |
| Two-stage prefilter before LLM | Hard rejects (wrong domain, title-deterministic) don't need LLM calls. Saves ~$0.10/day and speeds triage. |
| JSON output validation | `jsonschema` validates every LLM scoring response. Malformed output → manual_review, not a crash. |
| rclone bisync (not unidirectional) | Prep folders may be edited on other machines (phone via Google Drive). Bisync preserves both directions. |
| Rejection before prep in poll_flags | Prevents a race condition where a job gets prepped and then rejected in the same poll cycle. |
| `abbrev_title()` in folder names | Same-day preps for the same company would overwrite each other without title disambiguation. HHMMSS suffix prevents same-title same-day overwrites. |
