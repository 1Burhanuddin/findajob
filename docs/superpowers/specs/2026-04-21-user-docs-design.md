# User-Facing Documentation — Design Spec

**Issue:** #11 — Write user-facing documentation (setup, usage, tuning, troubleshooting)
**Date:** 2026-04-21
**Status:** Deferred — blocked on #61, #65, #84, #136, #148, #149. Spec is ready to execute once those ship.

---

## Problem

No user-facing docs exist beyond `CLAUDE.md` (Claude Code context, not human-readable). External testers (e.g., Alice Doe, #81) are onboarding now. The four missing guides block independent use of the pipeline.

---

## Decisions

1. **Four files, flat structure.** New files at `docs/setup/README.md`, `docs/usage.md`, `docs/tuning.md`, `docs/troubleshooting.md`. No new subdirectories.
2. **Audience: layered.** Non-technical first (plain language, "what you'll see", don't assume tech knowledge beyond basic PC/Macbook use), technical detail in `<details>` blocks or bottom "Reference" sections.
3. **Web UI primary.** Usage guide treats `/board/` tabs as the primary UX. Google Sheet equivalents noted but not primary. Sheet1 not documented (being retired).
4. **Setup guide is a cross-link index only.** `docs/setup/README.md` sequences the three existing setup files. No content duplication.
5. **No legacy infra.** Do not document: native systemd install, rclone/Drive sync, `install-linux.md` flows, Sheet1 as active surface.
6. **Verify before documenting.** Implementation must grep for every script and feature referenced before writing about it. If a script is gone, don't mention it.
7. **Enable user self-education.** In sections written for non technical users, to avoid deep dives into things like how to get an API key and how it works, how to set up Docker for this use case, etc, place toggle-collapsed callouts with suggested well crafted prompts for the LLM of their choice to explain something beyond what is in scope for this documentation.

---

## File Plan

### Files created (new)

| File | Purpose | ~Length |
|---|---|---|
| `docs/setup/README.md` | Start-here index: sequence the three existing setup files | ~1 page |
| `docs/usage.md` | Web UI daily workflow, tab-by-tab | ~4 pages |
| `docs/tuning.md` | Calibrate profile.md, prefilter, scorer, voice | ~3 pages |
| `docs/troubleshooting.md` | Symptom → diagnosis → fix; log reading; health alerts | ~3 pages |

### Files modified (existing)

| File | Change |
|---|---|
| `docs/setup/install-docker.md` | Add one line at top: "← New here? Start at `docs/setup/README.md`." |
| `docs/operations.md` | Add one line at top pointing to `docs/usage.md`; remove the native-install disclaimer |

---

## Content Outlines

### `docs/setup/README.md`

```
# Setup

Numbered reading order:
1. Prerequisites (→ prerequisites.md): API keys, ntfy
2. Install and deploy (→ install-docker.md): Docker stack setup
3. Configure (→ configure.md): run through the onboarding LLM prompt
4. Verify: health-check one-liner (inline)
5. What's next: links to usage.md and tuning.md
```

### `docs/usage.md`

```
# Daily Usage

## The daily loop
5-step morning routine (plain language)

## The Dashboard (/board/Dashboard)
- Columns: relevance_score / fit_score / probability_score explained in plain English
- STATUS dropdown: each option and what it triggers
- REJECT_REASON: when to use, what happens
- contacts column: what it means when populated

## What happens when you Flag for Prep
- Stage progression: Prep in Progress → Ready to Apply
- Materials folder creation; company column link

## The Review tab (/board/Review)
- What lands here (manual_review stage, uncertain scorer output)
- Promote vs. Reject workflow

## The Applied tab (/board/Applied)
- STATUS options post-application
- Ghosted: visual-only, no DB change
- Row color coding by recency/stage

## The Waitlist tab (/board/Waitlist)
- Deferred jobs: Reactivate vs. Reject
- Waitlist resurface ntfy notification

## The Archive tab (/board/Archive)
- All jobs ever ingested; filter/sort; replaces Sheet1

## Materials viewer (/materials/)
- What files are generated and what to do with each

## <details> For advanced users
Stage lifecycle, DB stage names, poll_flags.py timing, web UI vs. Sheet equivalences
```

### `docs/tuning.md`

```
# Tuning

## Where to start
Decision tree: symptom → which section to read

## Writing an effective profile.md (highest-leverage)
- Sections that matter most for scoring
- Tier 1 company list: format the scorer reads correctly
- "What to avoid": plain language, not regex
- Spelling out internally-branded programs
- Common mistakes and their scoring symptoms

## Prefilter: blocking jobs before the scorer (Stage 1)
- What config/prefilter_rules.yaml controls
- How to add a hard-reject title pattern
- How to test a pattern before committing
- What NOT to put in prefilter (field-specific terms)

## Score calibration: when good jobs score too low
- How to read feedback_log
- When to add a target company vs. adjust the profile
- Running rescore_all.py after a profile change

## Resume tailor / cover letter voice
- What candidate_context/voice_samples/ does
- How to add a writing sample
- Signs the CL voice is off; how to fix

## <details> For advanced users
Switching scorer models, prefilter Stage 2 behavior, rescore_all.py usage
```

### `docs/troubleshooting.md`

```
# Troubleshooting

## Reading the logs first
- docker compose logs scheduler
- pipeline.jsonl: event types, how to filter
- Health check: what notify.py health-check checks; alert meanings

## Symptom index

"No new jobs appearing"
→ Check pipeline_complete in logs; RapidAPI key; jsearch_queries.txt

"Jobs scoring 0 or not scoring"
→ aichat-ng smoke test; OpenRouter key/balance; Stage 2 prefilter (expected for no-JD jobs)

"Prep not completing / stuck in Prep in Progress"
→ Health check warns >1h; check prep subprocess error in logs; Anthropic key/rate limit

"Sheet not updating"
→ sync_sheet.py; service account credentials; sheet_id.txt

"Gmail not ingesting"
→ Token expired: re-run gmail-auth; OAuth client type (Desktop, not TV/limited input)

"Container won't start"
→ docker compose logs; mount path mismatch; missing state/ subdirectory

## Health check alert reference
One paragraph per alert that notify.py health-check can fire

## <details> For advanced users
Reading audit_log in pipeline.db; manually triggering resync or re-triage
```

---

## Audience Layering Pattern

Applied consistently across all four files:

- **Non-technical reader:** lead paragraph in plain language; "what you'll see on screen"; actions described as UI clicks not CLI commands
- **Developer-operator:** technical detail (env vars, SQL, log format, Python paths, script names) in `<details>` blocks labeled "For advanced users" or in a bottom "Reference" section
- One layered doc per topic — not two separate tracks

---

## Out of Scope

- `docs/setup/install-linux.md` — native install path is not the active deployment model; leave file in place but do not cross-link or update it
- Sheet1 — being retired; web Archive tab is the replacement; do not document Sheet1 as an active surface
- rclone/Drive sync — superseded by materials viewer; `state-migration.md` covers the historical transition
- `docs/operations.md` rewrite — `#76` tracks a full Docker rewrite; this spec only adds a link and removes the outdated native-install disclaimer

---

## Documentation Impact

| Doc surface | Change |
|---|---|
| `docs/setup/README.md` | Created (new) |
| `docs/usage.md` | Created (new) |
| `docs/tuning.md` | Created (new) |
| `docs/troubleshooting.md` | Created (new) |
| `docs/setup/install-docker.md` | Add "start here" back-link at top |
| `docs/operations.md` | Add usage.md forward-link; remove native-install disclaimer |
| `docs/superpowers/specs/` | This file |
| GitHub issue #11 | Add Session note after implementation; close when all 4 AC items verified |

---

## Verification Gate

After implementation, all four AC items from #11 must be satisfied:
1. Setup guide: a new user can follow docs/setup/README.md → prerequisites.md → install-docker.md → configure.md and have a running stack
2. Usage guide: a non-technical user can identify what to do in each `/board/` tab without reading code
3. Tuning guide: a user can locate and change the right file when scoring output is wrong
4. Troubleshooting guide: a user can diagnose every symptom listed in the index without reading source code

---

## Self-Review

- No TBDs or placeholders — all sections have explicit content outlines
- No contradictions: web UI is primary throughout; Sheet1 not mentioned as active
- Scope: four focused files, each under ~4 pages; fits one autonomous session
- Ambiguity resolved: "layered audience" defined as `<details>` blocks, not separate files
