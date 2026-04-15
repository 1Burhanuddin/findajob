# Feature Ideas / Improvement Backlog

Speculative improvements, new capabilities, and enhancements to consider.
Not bugs — nothing here is broken. Prioritize after open issues are resolved.
Format: `- [ ]` not started, `- [~]` in progress, `- [x]` shipped.

---

## Ingestion

- [x] **Google Form → manual job ingestion pipeline** *(shipped 2026-04-08)*
  Form: [see CLAUDE.local.md]
  Responses sheet ID stored in `config/form_responses_sheet_id.txt`.
  `scripts/ingest_form.py` polls every 30 min via `com.OWNER.jobpipeline.form-ingest` launchd agent.
  New jobs injected as `source=manual_form`, `stage=scored`, `relevance_score=8`.
  Optional "Generate company folder immediately" checkbox triggers `prep_application.py`.
  Fields: Job URL, Company, Title, Location, Remote Status, Notes, Known Contacts, Generate Folder.

---

## Scoring / Triage

- [x] **Scoring accuracy analysis — false negative audit** *(closed 2026-04-11)*
  Ran full false negative scan: no alarming buried gems. Score-6 target company jobs are
  correctly sitting at the Tier 1 floor (working as designed). 17 "data center" titled jobs at
  score 6 are visible in the Review tab for manual promotion. The real problem was false
  positives (80.6% FP rate on score 8+), not false negatives. Root cause: scorer rated IC
  hardware engineering roles (NPI validation, systems engineering, deployment engineering) too
  high. Fixed via scorer prompt ENGINEER TITLE CALIBRATION section — disambiguates IC hardware
  work (bench/design/validation) vs ops/program work (candidate's domain).
  Prefilter additions: quality engineer, process engineer, manufacturing test, systems
  development engineer. Removed "forward deployed engineer" from Stage 2 in-domain defaults.

- [x] **Feedback loop — systematic learning from rejections** *(shipped 2026-04-11)*
  `scripts/analyze_feedback.py` reads feedback_log + jobs to produce: rejection breakdown,
  false positive analysis (score 8+ rejected), title keyword signals (applied vs rejected),
  company repeat patterns, source FP rates, and actionable prefilter/search suggestions.
  `notify.py feedback-review` updated to surface key stats from the analysis.
  First run findings: 80.6% of rejections are score 8+ (false positives); Greenhouse has 73%
  FP rate on score-7+ jobs; "engineer" title without "operations/data center" context is the
  dominant FP signal. Prefilter updated with quality/process/systems-dev engineer patterns.
  Search queries updated: removed "forward deployed engineer", "data center engineer"; added
  "data center technician manager", "datacenter site manager", "AI infrastructure operations".

## Data Sources

- [ ] **Evaluate alternative job APIs**
  Currently using jobs-api14 (RapidAPI) for LinkedIn + Indeed. First API found, not necessarily
  best. Evaluate: coverage (are we missing jobs that appear on other boards?), JD completeness
  (do other APIs return full JDs without truncation?), cost, rate limits. Candidates: LinkedIn
  official API (requires partnership), Adzuna, The Muse, Remotive, company career pages direct.

---

## Prep / Output

- [x] **Waitlist — "yes but not right now" deferred jobs** *(shipped 2026-04-12)*
  New `waitlisted` stage and Waitlist sheet tab. Jobs at companies where user already
  applied can be moved off Dashboard without rejection. Folders move to `_waitlisted/`.
  "Reactivate" on Waitlist tab restores to scored or materials_drafted. ntfy notification
  fires when blocking application is rejected/withdrawn. 16 unit tests added.

---

## Observability

*(nothing yet)*

---

## Platform / Open Source (Long-term)

The dual goals of this project: (1) get Daniel a job, and (2) eventually make this pipeline
useful for any job seeker. These are aligned — every hardening improvement also makes it
more generalizable. The path from personal tool → general tool is roughly:

- [x] **PII audit + scrub** *(done 2026-04-11)*
  Full audit completed. All tracked files scrubbed. Pre-commit hook blocks future PII.
  See ISSUES.md "Quality & Security" section for details.

- [ ] **Comprehensive user-facing docs**
  Setup guide (prerequisites, Google Sheets setup, API keys, first run), usage guide (daily
  workflow, Dashboard actions, Review tab), tuning guide (search queries, prefilter, scorer
  prompt), troubleshooting. Currently docs/ is solid for the author but not for a stranger.

- [ ] **Containerize with Docker Compose** *(enables "clone and run")*
  Single docker-compose.yml that runs triage, poller, and sync on a schedule. Eliminates
  launchd/systemd setup friction. Makes the "install" story dramatically simpler for non-Linux
  users. Prerequisites: externalize all personal config to a single .env file.

- [ ] **Web dashboard (replace Google Sheets)**
  Local web UI that replaces Sheet1/Dashboard/Review tabs. The Google Sheets dependency is the
  biggest barrier to general adoption — requires GCP project, service account, sharing setup.
  A simple local Flask/FastAPI app with a React frontend could replace the entire Sheets layer.
  This is a major effort but transforms the product from "personal tool with cloud plumbing"
  to "self-hosted job search app."

- [ ] **Generalize personal config layer**
  Currently CLAUDE.local.md, profile.md, master_resume.md, jsearch_queries.txt, feed_urls.txt
  are all personal. Need a clean onboarding flow: `cp config/*.example config/` and guided
  setup. The pipeline logic is already generic — it's the config that's personal.

- [ ] **Guided onboarding interview — LLM-driven profile builder**
  The current pipeline is highly effective because of deep, manually curated candidate context
  (profile.md, master_resume.md, voice samples, scorer boost/reduce criteria, target company
  lists). A general user can't replicate this depth on their own. Solution: a structured
  LLM-conducted interview (~1-2 hours) that produces all candidate context files.

  **Phase 1 — Document upload + analysis:**
  User uploads everything they have: resume(s), LinkedIn export, cover letters, performance
  reviews, project descriptions, portfolio links. An LLM with a dedicated interviewer role
  analyzes the material, identifies strengths, gaps, career patterns, and industry vocabulary.
  Produces a draft profile.md and initial scorer criteria.

  **Phase 2 — Structured interview:**
  The LLM asks targeted questions to fill gaps the documents don't cover: what roles excite
  you and why, what's your actual day-to-day, what do peers say you're best at, what work do
  you never want to do again, what are your comp expectations, geographic constraints, etc.
  Questions adapt based on document analysis — skip what's already clear, dig into what's
  ambiguous. Output: finalized profile.md, master_resume.md, target company list, search
  queries, scorer boost/reduce criteria, voice/tone markers for cover letter generation.

  **Phase 3 — Continuous calibration (implicit + explicit feedback):**
  *Implicit:* Track rejection rate by reason, score band, source, and company. If user
  rejects 90% of "hardware engineer" titles, auto-suggest adding it to hard-reject patterns.
  Surface patterns weekly via the existing feedback-review notification. The analyzer already
  does this (`analyze_feedback.py`) — extend it to propose config changes, not just report.
  *Explicit — daily:* Single-question micro-survey via ntfy or dashboard prompt. "Was
  today's Dashboard useful? (yes/no/didn't look)" or "Any job you wish had appeared today?"
  Rotates through a question bank. Low friction, high signal over time.
  *Explicit — weekly:* 5-minute survey (ntfy link or in-dashboard). "Review these 5
  rejections — would you change any? Are the search categories still right? Anything
  missing?" Surfaces drift before it compounds.
  Both implicit and explicit signals feed back into profile.md and scorer criteria —
  either as auto-suggestions the user approves or as direct config updates.

---

## Engineering Quality

Most foundations shipped 2026-04-12 (pyproject.toml, ruff, 302 tests, CI, package layout,
type hints, mypy). Remaining items for full maturity:

- [ ] **Integration tests**
  302 tests cover pure functions only. No tests for the pipeline flow: inserting a job,
  running it through dedup/enrichment/scoring, verifying DB output. Requires test DB
  fixtures and mock API responses. Catches "pieces don't fit together" bugs that unit
  tests miss.

- [ ] **DB migration system (Alembic)**
  Schema changes are manual `ALTER TABLE` on the live DB with no versioning. Stable today,
  but blocks multi-machine deploys and safe schema evolution. Worth adding once schema
  changes become more than once-a-quarter.

- [ ] **Log rotation**
  `pipeline.jsonl` grows forever. No `logrotate` config. Add a weekly rotation rule or
  a size-based rotation in the bootstrap.sh systemd setup.

---

## Shipped

*(move items here with ship date)*
