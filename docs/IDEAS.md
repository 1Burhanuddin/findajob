# Feature Ideas / Improvement Backlog

> **Kanban board:** https://github.com/users/brockamer/projects/1
> The GitHub Project board is the source of truth for active work. This file is a
> human-readable summary. Each open item below links to its GitHub Issue.

Speculative improvements, new capabilities, and enhancements to consider.
Not bugs — nothing here is broken. Prioritize after open issues are resolved.

**Priority:** `HIGH` = directly helps get a job faster. `MED` = quality/efficiency improvement.
`LOW` = nice-to-have or future-facing. `BLOCKED` = waiting on a dependency.

---

## Active — Job Search Impact

- [ ] **Search expansion Phase 3 — robotics/AV/adjacent ATS feeds** `HIGH` [#1](https://github.com/brockamer/findajob/issues/1)
  Probe Greenhouse/Ashby/Lever APIs for: Figure AI, Agility Robotics, Apptronik,
  Boston Dynamics, Waymo, Zoox, Aurora, Motional, Serve Robotics, ILM, DNEG,
  TAE Technologies, Commonwealth Fusion. Add verified feeds to feed_urls.txt,
  new jsearch queries, update TIER1.
  **Depends on:** Phase 1+2 (shipped). **Spec:** `specs/2026-04-15-search-expansion-design.md`

- [ ] **Search expansion Phase 4 — validate and tune** `HIGH` `BLOCKED` [#2](https://github.com/brockamer/findajob/issues/2)
  Review first week of Dashboard results from expanded feeds + updated scorer.
  Tune scorer, adjust jsearch queries, remove low-signal terms.
  **Depends on:** Phase 3.

- [ ] **Evaluate alternative job APIs** `MED` [#3](https://github.com/brockamer/findajob/issues/3)
  Currently using jobs-api14 (RapidAPI) for LinkedIn + Indeed. Evaluate: coverage,
  JD completeness, cost, rate limits. Candidates: Adzuna, The Muse, Remotive,
  company career pages direct.

- [ ] **21 enriched jobs need rescore** `MED` [#4](https://github.com/brockamer/findajob/issues/4)
  Leftover from interrupted rescore session (originally 33, triage processed some).
  Tomorrow's triage won't pick these up — they need manual rescore or a mechanism
  to process stuck enriched-stage jobs.

---

## Active — Pipeline Quality

- [ ] **`not_selected` stage — distinguish user vs. company rejections** `MED` [#5](https://github.com/brockamer/findajob/issues/5)
  Company rejections shouldn't feed the scorer tuning loop. Need: new STATUS
  dropdown "Not Selected", new stage `not_selected`, folder stays in `_applied/`,
  no `feedback_log` write. `analyze_feedback.py` excludes from false-positive analysis.
  **Details:** `docs/ISSUES.md` Pipeline Gaps section.

- [ ] **GDrive sync audit — remaining cleanup** `LOW` [#6](https://github.com/brockamer/findajob/issues/6)
  Tasks 3-4 from `plans/2026-04-15-gdrive-sync-audit.md`: purge stale Drive copies,
  resolve two AWS waitlisted jobs sharing one folder. Architectural fixes (Tasks 1-2,
  6-7) are shipped. These are data hygiene items, not blocking anything.

- [ ] **Integration tests** `MED` [#7](https://github.com/brockamer/findajob/issues/7)
  423 tests cover pure functions only. No tests for pipeline flow: insert job →
  dedup → enrich → score → verify DB output. Requires test DB fixtures and mock
  API responses. Catches "pieces don't fit together" bugs.

- [ ] **Log rotation** `LOW` [#8](https://github.com/brockamer/findajob/issues/8)
  `pipeline.jsonl` grows forever. Add `logrotate` config or size-based rotation.
  Not urgent at current scale (~50KB/day).

- [ ] **DB migration system (Alembic)** `LOW` [#9](https://github.com/brockamer/findajob/issues/9)
  Schema changes are manual ALTER TABLE. Stable today, but blocks safe schema
  evolution at scale. Worth adding once schema changes become frequent.

---

## Future — Open Source / Generalization

These make the pipeline useful for any job seeker, not just the current user.
All are deferred until the pipeline is actively getting the user hired.

- [ ] **Generalize personal config layer** `MED` [#10](https://github.com/brockamer/findajob/issues/10)
  Externalize TIER1, prefilter patterns, in-domain patterns from code to config.
  Pipeline logic is already generic — config is what's personal. Clean onboarding
  flow: `cp config/*.example config/` and guided setup.
  **Tracking:** `docs/GENERALIZATION.md` has the full inventory.

- [ ] **Guided onboarding interview — LLM-driven profile builder** `LOW` [#12](https://github.com/brockamer/findajob/issues/12)
  Structured LLM interview (~1-2 hours) that produces all candidate context files.
  Phase 1: document upload + analysis. Phase 2: targeted questions. Phase 3:
  continuous calibration from rejection patterns.
  **Depends on:** Generalize config layer.

- [ ] **Comprehensive user-facing docs** `MED` [#11](https://github.com/brockamer/findajob/issues/11)
  Setup guide, usage guide, tuning guide, troubleshooting. Currently docs/ is
  solid for the author but not for a stranger.
  **Depends on:** Generalize config layer (so docs describe the general flow).

- [ ] **Containerize with Docker Compose** `LOW` [#13](https://github.com/brockamer/findajob/issues/13)
  Single docker-compose.yml. Eliminates systemd/launchd setup friction. Requires
  rearchitecting scheduler (systemd → cron or external scheduler).
  **Depends on:** Generalize config layer.

- [ ] **Web dashboard (replace Google Sheets)** `LOW` [#14](https://github.com/brockamer/findajob/issues/14)
  Local Flask/FastAPI + React frontend replacing Sheet1/Dashboard/Review tabs.
  Biggest barrier to adoption is the Google Sheets dependency. Major effort.
  **Depends on:** Docker containerization (loosely).

---

## Low Priority / Monitoring

- [ ] **RAG source documents — manual editing pass** `LOW` [#15](https://github.com/brockamer/findajob/issues/15)
  Content quality of `candidate_context/` docs hasn't been reviewed since initial
  setup. RAG only used in REPL context. Low urgency.

- [ ] **`regen_resumes.py` title extraction is best-effort** `LOW` [#16](https://github.com/brockamer/findajob/issues/16)
  Parses role title from `REVIEW_CHECKLIST.md` header — may return empty.
  Only affects this diag script, not the main pipeline.

---

## Shipped

- [x] **Google Form → manual job ingestion pipeline** *(2026-04-08)*
- [x] **Scoring accuracy analysis — false negative audit** *(2026-04-11)*
- [x] **Feedback loop — systematic learning from rejections** *(2026-04-11)*
- [x] **Waitlist — "yes but not right now" deferred jobs** *(2026-04-12)*
- [x] **PII audit + scrub** *(2026-04-11)*
- [x] **Search expansion Phase 1 — 17 ATS feeds** *(2026-04-15)*
- [x] **Search expansion Phase 2 — cross-industry scorer prompt** *(2026-04-15)*
- [x] **LXC migration — laptop to Proxmox container** *(2026-04-14)*
- [x] **Dashboard status integration — Prep in Progress, Regenerate** *(2026-04-14)*
- [x] **GDrive sync — push-only architecture, Drive-side moves** *(2026-04-14)*
- [x] **Rejected Applications tab with Drive links** *(2026-04-14)*
- [x] **Drive consistency health checks** *(2026-04-14)*
- [x] **CI failure monitoring via ntfy** *(2026-04-15)*
- [x] **User-Agent headers + 429 backoff on fetchers** *(2026-04-15)*
- [x] **LLM output normalization (remote_status, score clamping)** *(2026-04-15)*
- [x] **SQLite busy_timeout across all scripts** *(2026-04-15)*
- [x] **Package restructure (src/findajob/) + CI** *(2026-04-12)*
