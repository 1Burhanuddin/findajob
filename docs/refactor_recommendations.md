# JobSearchPipeline — Refactor Recommendations
*Generated: 2026-04-08*

---

## What's Actually Working Well

The core architecture is sound. Three-stage scoring (deterministic prefilter → LLM → JSON validation) is the right pattern. Direct profile injection instead of RAG for candidate context was the right call. The launchd-driven daily run is solid. The role system in aichat-ng gives you per-model tuning without code changes. The fingerprint deduplication works. These are all good decisions — don't touch them.

---

## Critical Issues (Fix Now)

**1. API keys in aichat-ng's config.yaml are plaintext**
Every key you use (Anthropic, Gemini, OpenAI, xAI, Groq, Perplexity, OpenRouter) is in a single unencrypted file. If you ever sync that Mac, back it up to a new machine, or run anything that reads `~/Library/Application Support/`, those keys are exposed. The fix is to move them to `~/.zshenv` as environment variables and reference them via `env:VARIABLE_NAME` in the aichat-ng config, which it supports natively.

**2. No retry logic anywhere**
LinkedIn JD fetches, Greenhouse API calls, RapidAPI searches — all fire once and silently fail if the network hiccups. Given that triage runs once a day and you can't easily re-run just the failed jobs, a single API timeout means those jobs get scored with no JD and land in `manual_review` indefinitely. Exponential backoff with 2-3 attempts would fix this.

**3. `prep_application.py` subprocess failures are silent**
`check=False` on the pandoc calls and the find_contacts subprocess means you can get a partial prep folder with no error surfaced. One aichat-ng timeout mid-run and you get a folder with a resume but no cover letter, with `materials_drafted` in the DB as if everything succeeded.

---

## High-Impact Refactors (Worth Doing)

**4. `prep_application.py` runs everything serially — it's very slow**
Six sequential LLM calls, each blocking on the previous. Resume tailor → change reviewer → cover letter → researcher → briefing writer → outreach — all in one long chain. The resume tailor, cover letter writer, company researcher, and find_contacts are fully independent. They could all run in parallel threads, cutting wall time roughly 4x. This is the single biggest quality-of-life improvement.

**5. `triage.py` has no transaction safety**
Jobs are committed one-by-one as they're processed. If triage crashes at job 400 out of 800, you have 400 partial records in inconsistent states. The fix is to wrap each job's ingest-enrich-score cycle in an explicit transaction and only commit on success.

**6. ~~`sync_sheet.py` has an O(n²) bug in COL_MAP lookup~~** *(fixed 2026-04-08)*
`S1_LOOKUP` and `DASH_LOOKUP` are now built once as reverse dicts. `build_row()` does a single dict lookup per cell.

**7. `rclone bisync` path is fragile and inconsistently referenced**
The launchd plist and `prep_application.py` use `gdrive:01 PROJECTS/Jobs To Apply For` (spaces, no underscores). The bisync cache files use underscores. This mismatch caused a sync failure on 2026-04-07. The path should be defined once — in `.env` or a config file — and referenced everywhere.

---

## Medium-Impact Issues (Fix When You Have Time)

**8. `company_match()` in `find_contacts.py` has false-positive risk**
Uses substring containment after stripping suffixes. "Apple" matches "GreenApple Inc." If `company` is a short or common string (like "AI"), it will match everything. Should use word-boundary regex instead of `in`.

**9. ~~The `company_signal` column exists everywhere but is never written~~ (resolved — deprecated)**
Column removed from init_db.py schema. Company intel surfaced via company_briefing.docx at prep time instead. Live DB column left in place (harmless, always empty).

**10. `needs_info` is a valid stage in the DB schema but not in `scoring_schema.json` and never used in code**
Dead code that adds confusion. Either implement it or remove it from the DB constraint.

**11. `clean_company.py` is a now-obsolete patch script**
The function it patched is already live in `triage.py`. Delete it.

**12. Log files grow forever**
`pipeline.jsonl` is already 1.6 MB after a few weeks. No rotation. `launchd_poller_stderr.log` had 25 KB of the same error repeated. Add `newsyslog` entries or a weekly rotation cron.

---

## Lower Priority (Leave Alone or Defer)

- **No unit tests** — adding tests for a single-user automation pipeline isn't high ROI. The LLM calls aren't testable in any meaningful way.
- **Hardcoded tool paths** — the CLAUDE.md governance prevents misuse; the paths are stable on this machine. Not worth abstracting.
- **RAG corpus quality** — acknowledged low priority in ISSUES.md; RAG is only used in REPL mode.
- **No pagination on Greenhouse API** — Greenhouse returns full job lists by default; pagination isn't needed unless a single company has >250 openings.

---

## Recommended Refactor Order

| Priority | Work | Impact |
|---|---|---|
| 1 | Move API keys out of aichat-ng config.yaml to `~/.zshenv` | Security |
| 2 | Retry logic in triage.py (3 attempts, exponential backoff) | Fewer manual_review orphans |
| 3 | Parallelize prep_application.py LLM calls with threads | ~4x faster prep |
| 4 | Fix prep subprocess error handling (`check=True`, log failures) | No more silent failures |
| 5 | DB transaction safety in triage.py (wrap per-job cycle) | No partial state on crash |
| ~~6~~ | ~~Fix O(n²) COL_MAP lookup in sync_sheet.py~~ | **Done 2026-04-08** |
| ~~7~~ | ~~Wire up `company_signal` column from Perplexity output~~ | **Deprecated 2026-04-10** |
| 8 | Log rotation via newsyslog | Housekeeping |
| 9 | Delete `scripts/clean_company.py` | Cleanup |
