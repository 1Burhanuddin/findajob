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

---

## Infrastructure / Ops

- [ ] **RAG source documents — manual editing pass** *(Low)*
  Content quality of `rag_sources/` docs hasn't been reviewed since initial setup.
  Deferred until pipeline is stable. Low urgency — RAG only used in REPL context.

- [ ] **`regen_resumes.py` title extraction is best-effort** *(Low)*
  Parses role title from `REVIEW_CHECKLIST.md` header — may return empty for some folders.
  Only affects this diag script, not the main pipeline. Review v2 output for any folder
  where title hint shows `(none found)` in the run log.

- [ ] **`resume_tailor` ignores bullet count and structure rules** *(Medium)*
  Opus 4.6 consistently adds sub-headers within experience sections and exceeds per-role bullet limits
  despite explicit instructions in the role prompt. Workaround: manual cleanup pass after generation.
  Investigate: restructure prompt to use a worked example (few-shot) of the correct flat format; may
  need a post-processing script to strip bold sub-headers and enforce counts automatically.

- [ ] **`score=None` on occasional jobs** *(Low)*
  Some jobs log `score=None` in `pipeline.jsonl` (e.g. "AI Tutor - Telugu" 2026-04-07).
  Likely scorer timeout or malformed LLM response — not a crash. No fallback or retry exists.
  Investigate: add explicit `None` check in `triage.py` score extraction and log as `score_error` event.

- [x] **Prep triggered for blank-company and Dice-wrapper listings** *(closed 2026-04-08)*
  Fixed in `poll_flags.py`: `AGGREGATOR_PREFIXES` tuple + `is_valid_company()` guard skips blank or
  aggregator-wrapped companies before triggering `prep_application.py`.

- [ ] **pandoc YAML parse error on cover letter files** *(Low)*
  `cover_letter_DRAFT.md` files that begin with `--- DRAFT - REQUIRES HUMAN EDITING ---` are misread
  by pandoc as YAML frontmatter. Seen in `Amazon Web Services_2026-04-06_053449`. pandoc tries to
  parse the letter body as YAML and fails at the closing `---` on line 16.
  Fix: change the cover letter role header to a non-YAML-delimited format (e.g. plain `# DRAFT`) or
  add `---\n` as a proper empty frontmatter block before the marker.

---

## Completed

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
