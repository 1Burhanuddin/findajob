# findajob — CLAUDE.md

Read by Claude Code at the start of every session. Authoritative context for this codebase.
Personal identifiers (name, targets, API topic, form URLs) live in `CLAUDE.local.md` (gitignored).

---

## Self-Governance — Check Before Every Command

Before writing any command, path, binary call, or file location:

- [ ] Python: use `sys.executable` in scripts; check `config/paths.env` for the platform path
- [ ] aichat-ng: get path from `AICHAT` in `scripts/paths.py` — never hardcode, never call bare `aichat`
- [ ] pandoc: get path from `PANDOC` in `scripts/paths.py`
- [ ] aichat-ng config dir: macOS = `~/Library/Application Support/aichat_ng/`; Linux = `~/.config/aichat_ng/`
- [ ] Roles dir: `<repo>/config/roles/` — `.md` files only, never `.yaml`
- [ ] Master resume: `rag_sources/master_resume.md` — never `config/master_resume.md`
- [ ] Anthropic client in aichat-ng config: `type: claude` — never `type: anthropic`; prefix `claude:` not `anthropic:`
- [ ] RAG never passed to scorer, cover letter writer, or outreach drafter
- [ ] macOS sed: `sed -i '' ...`; Linux sed: `sed -i ...` (no empty string)
- [ ] All binary paths come from `scripts/paths.py` — never hardcode platform paths in scripts

**If uncertain about any value: say so. Do not guess.**

---

## Pipeline Context Table

| Item | Value |
|------|-------|
| Default model | `gemini:gemini-3-flash-preview` |
| Embedding model | `gemini-embed:gemini-embedding-001` — dedicated named client, never touched by `--sync-models` |
| `job_scorer` | `openrouter:deepseek/deepseek-v3.2` — profile.md injected directly; `--rag` NEVER used |
| `resume_tailor` / `cover_letter_writer` | `claude:claude-opus-4-6:thinking`, `max_tokens: 4096` |
| `company_researcher` | `perplexity:sonar-reasoning-pro` |
| `briefing_writer` | `claude:claude-sonnet-4-6:thinking` |
| `outreach_drafter` | `claude:claude-sonnet-4-6` — profile injected directly |
| `fit_analyst` | `perplexity:sonar-reasoning-pro` — appended to company briefing |
| `resume_change_reviewer` / `network_analyst` | `gemini:gemini-3-flash-preview` |
| Job ingestion | jobs-api14 (RapidAPI) — LinkedIn (`datePosted: 'day'`) + Indeed; Gmail OAuth2 |
| pip | `pip3 install --break-system-packages` (no venv) |
| Path resolution | `scripts/paths.py` — reads `config/paths.env`; BASE derived from `__file__` |
| Roles dir | `config/roles/` |
| Master resume | `rag_sources/master_resume.md` |
| Profile | `config/profile.md` |
| DB | `data/pipeline.db` |
| Pre-filter | `scripts/scorer_prefilter.py` — Stage 1 regex hard reject, Stage 2 no-JD default |
| RAG index | `job_search_rag` — never passed to scorer/CL/outreach |
| Scheduler | macOS: launchd agents; Linux: systemd user services (see docs/setup/install-linux.md) |
| ntfy topic | in `data/.env` as `NTFY_TOPIC`; also in `CLAUDE.local.md` |
| Google Form | URL and response sheet ID in `CLAUDE.local.md` and `config/form_responses_sheet_id.txt` |

---

## Key File Locations

```
<repo>/scripts/paths.py                     # central path resolver — import BASE, AICHAT, PANDOC, RCLONE
<repo>/config/paths.env                     # binary path overrides (gitignored; see paths.env.example)
<repo>/config/roles/                        # role .md files (8 roles)
<repo>/data/pipeline.db                     # SQLite — source of truth
<repo>/data/.env                            # API keys (chmod 600; gitignored)
<repo>/config/profile.md                    # candidate profile (gitignored; see profile.md.example)
<repo>/rag_sources/master_resume.md         # master resume (gitignored; see master_resume.md.example)
<repo>/config/scoring_schema.json           # JSON schema for LLM scorer output validation
<repo>/config/jsearch_queries.txt           # LinkedIn/Indeed search queries (gitignored)
<repo>/config/feed_urls.txt                 # Greenhouse company slugs (gitignored)
<repo>/config/gmail_oauth_client.json       # Gmail OAuth2 credentials (gitignored)
<repo>/config/gmail_token.json              # Gmail token cache (gitignored)
<repo>/data/connections.csv                 # LinkedIn connections export (gitignored)
<repo>/scripts/scorer_prefilter.py          # deterministic pre-filter (Stage 1 + 2)
<repo>/scripts/triage.py                    # daily ingest → score → DB
<repo>/scripts/poll_flags.py                # reads Dashboard!A2:C10000 (STATUS, REJECT_REASON, fingerprint)
<repo>/scripts/sync_sheet.py                # SQLite → Sheet1 + Dashboard
<repo>/scripts/setup_sheets.py             # one-time sheet formatting (idempotent)
<repo>/scripts/prep_application.py          # on-demand LLM material generation
<repo>/scripts/find_contacts.py             # LinkedIn contact matching + outreach drafts
<repo>/scripts/ingest_form.py               # Google Form → DB ingestion
<repo>/scripts/notify.py                    # ntfy push notifications (5 subcommands)
<repo>/scripts/rename_folders.py            # rename company folders to new format (idempotent)
<repo>/companies/                           # prep output folders ({Company}_{AbbrevTitle}_{date}_{time})
<repo>/companies/_done/                     # applied/rejected/withdrawn folders
<repo>/logs/pipeline.jsonl                  # structured event log
<repo>/data/pipeline.db                     # feedback_log table: rejection history
```

---

## Critical Architecture Rules

### Path Resolution
All binary paths (AICHAT, PANDOC, RCLONE) come from `scripts/paths.py`, which reads `config/paths.env`.
Never hardcode platform paths in scripts. `BASE` is derived from `__file__` — the repo can live anywhere.
For subprocess calls to other pipeline scripts, always use `sys.executable`, not a hardcoded Python path.

### RAG Policy
RAG (`--rag job_search_rag`) is NEVER passed to `job_scorer`, `cover_letter_writer`,
`outreach_drafter`, or any role needing candidate-specific context. RAG chunking drops
contact info, employer names, and dates. All candidate context injected directly via
`profile.md` and `master_resume.md` string interpolation. RAG retained for REPL only.

### Hard Rejects are Code
`scorer_prefilter.py` handles hard rejects deterministically before any LLM call.
Stage 1: title regex → score 1, no LLM. Stage 2: in-domain + no JD → score 5/6, no LLM.
Never rely on LLM prompt instructions alone for boolean classification tasks.

### Abbreviation Clarifications
Any internally-branded teams, programs, or org names with ambiguous abbreviations must be
spelled out explicitly in role prompts and CLAUDE.local.md. LLMs will misinterpret
abbreviations if context is not given. See CLAUDE.local.md for this installation's specifics.

### Output Folder Format
`{Company}_{AbbrevTitle}_{YYYY-MM-DD}_{HHMMSS}` — title abbreviated to first 3 words, underscored.
The HHMMSS suffix is required to prevent same-day overwrites.
`abbrev_title()` is defined in `prep_application.py` and `rename_folders.py`.

### JD at Prep Time
`prep_application.py` reads JD from the database. Never re-curls the URL at prep time.

### company_match() Blank String Guard
`connections.csv` may have blank-company rows. `'' in 'anything'` is True in Python.
Every `company_match()` function must guard: `if not s or not c: return False`

### Title/Company Cleaning
API title and company fields contain appended metadata (location, salary, recency flags).
`clean_title()` and `clean_company()` must be applied at every ingest path before storing.

### LinkedIn JD Fetch
Direct curl to LinkedIn always returns auth wall. Always use RapidAPI `/v2/linkedin/get?id=`.
This applies to both `linkedin_jobsapi` and `gmail_linkedin` sources.

### LinkedIn Query Format
`jsearch_queries.txt`: 3-4 word natural phrases only. Keyword-heavy strings (5+ words)
return zero LinkedIn results. Validate each query manually before committing.

### Google Sheet Architecture

**Sheet1** — full archive (all non-dupe jobs, A–N):
`fingerprint(hidden) | APPLY_FLAG(checkbox) | score | title | company | location | remote | stage | contacts | comp | notes | date | source | url`

**Dashboard** — actionable queue (A–N), filter: `score>=7 AND stage IN (scored,manual_review)` OR `stage=materials_drafted`:
`STATUS(dropdown) | REJECT_REASON(dropdown) | fingerprint(hidden) | fit_score | probability_score | relevance_score | title(hyperlink) | company | location | remote | contacts | comp | notes | date`

**STATUS dropdown options** (col A): `Flag for Prep` → `Ready to Apply` → `Applied` → `Interviewing` → `Offer` → `Withdrew`
- `Flag for Prep` = user action → triggers `prep_application.py` via `poll_flags.py`
- `Ready to Apply` = system-set when `stage=materials_drafted` (prep done, folder exists)
- `Applied/Interviewing/Offer/Withdrew` = user action → `poll_flags.py` updates DB stage

**REJECT_REASON dropdown** (col B): 11 options (includes "Low Fit Score") → `poll_flags.py` sets `stage=rejected`, writes `feedback_log`, moves folder to `companies/_done/`, triggers rclone bisync immediately.

**poll_flags.py** reads `Dashboard!A2:C10000`. Rejection takes priority over prep trigger.

---

## Working Style

- Terse. User reports completion of each step before asking what's next.
- Read file contents before proposing changes. Never assume files match prior discussion.
- Diagnose root cause before fixing. No shotgun solutions.
- Copy-pasteable commands only. No placeholders. Use paths from `scripts/paths.py`. Platform-aware.
- Never confuse `aichat` with `aichat-ng`. Different binaries.
- Goal: working features first, polish later.
- Preserve the scheduler-driven daily run in all changes.

@CLAUDE.local.md
