# #301 — End-to-end data model audit

**Date:** 2026-05-03
**Scope:** Audit + triage only. Implementation of the backup mechanism, restore procedure, `docs/setup/` Backups section, and `CLAUDE.md` data-ownership table is split into follow-up issues filed against the findings here.

## Issues

- #301 — parent audit (closed when this spec lands and follow-ups are filed)
- #426 — backup mechanism implementation
- #427 — verified restore procedure (blocked by #426)
- #428 — `CLAUDE.md` data-ownership table
- #429 — reject-reason taxonomy extraction (vocab leak + drift fix)

This audit answers four questions for every persisted artifact in the pipeline:

1. **Where does it live** — container path, host bind-mount, or outside the container?
2. **Who owns it** — operator-authored, pipeline-generated, or mixed?
3. **What's its backup status today?**
4. **Is it rebuildable if lost** — yes / no / partially?

Plus a vocabulary leakage scan: every enum, dropdown option, and string constant in tracked code reviewed for operator-domain leakage.

---

## 1. Data inventory

All paths shown are container-internal (`/app/…`); the host bind-mount root is `/opt/stacks/findajob-{handle}/state/`. Sizes shown are from the operator's stack snapshot taken 2026-05-03 (oldest and densest of the 6 stacks on `docker.lan`).

### 1.1 SQLite — `data/pipeline.db` (~146 MB)

The single file that, if lost, takes the most operator history with it. Currently contains:

| Table | Rows (operator) | Source | Rebuildable? |
|---|---|---|---|
| `jobs` | 13,416 | Pipeline-generated, but operator-curated via stage transitions, notes, `excluded_employers`, score corrections | **No.** Fetcher results from past dates aren't retrievable; rejection/applied transitions are operator decisions |
| `audit_log` | 43,338 | Pipeline-generated (every stage / reject_reason transition logged) | **No.** Audit-trail value derives from being the only record |
| `feedback_log` | 338 | Operator-generated (every user rejection writes here; feeds the scorer's feedback loop) | **No.** Each entry is an operator's stated rationale at the time |
| `cost_log` | 16,587 | Pipeline-generated (every LLM call) | **No** — but its value is observability, not state. Loss is recoverable. |
| `duplicate_groups` | 12,616 | Pipeline-generated (Tier 1 / loose-fingerprint dedup) | **Yes**, by re-running ingestion against the same source corpus |
| `onboarding_sessions` | 0 (operator) / variable (testers) | Tester credentials + interview transcript | **Partially** — re-onboarding loses the original transcript and any per-session credit |
| `speculative_requests` | 2 | Operator-generated (cold-outreach briefings pre-approval) | **Partially** — hint + personal_notes lost; briefing artifact survives in `companies/` if approved |

Schema is checked-in (`scripts/init_db.py`); migrations live under `scripts/migrations/` and run idempotently at app startup.

**Backup status today:** none scheduled. The operator has manual `.bak` snapshots in the same directory (`pipeline.db.bak`, `pipeline.db.bak.20260416_184455`, `pipeline.db.bak.20260416_184503`) — ad-hoc, same-host, no rotation, no off-host copy.

### 1.2 `candidate_context/` (~132 KB; hours of operator effort)

| Path | Size | Source | Rebuildable? |
|---|---|---|---|
| `profile.md` | 29 KB | Operator-authored (interview output + hand-curation: Title Calibration Notes, exclusions, accumulated edits) | **No** without re-doing the interview AND losing weeks of hand-tuning |
| `master_resume.md` | 38 KB | Operator-authored | **No** |
| `voice_samples/voice-samples.md` | 30 KB | Operator-authored | **No** without re-collecting writing samples |
| `discovered_companies.{md,json}` | 8 KB | Pipeline-generated (weekly cron) | **Yes**, next Sunday discoverer run reproduces |
| `voice_samples/README.md` | 725 B | Repo-baked template | **Yes** |

`profile.md.example` is a template, lives in the repo.

### 1.3 `config/` (~292 KB; mixed)

Operator-authored (interview-emitted or hand-curated):

| Path | Source | Rebuildable? |
|---|---|---|
| `target_companies.md` | Operator-curated (interview-emitted seed; hand-edited over time) | **No** without re-interview + drift since |
| `companies_of_interest.txt` | Operator-curated | **No** |
| `feed_urls.txt` | Operator-curated (Greenhouse/Lever/Ashby career-page URLs) | **No** |
| `prefilter_rules.yaml` | Operator-curated (interview-emitted, accumulates corrections) | **No** |
| `excluded_employers.yaml` (#84) | Operator-curated | **No** |
| `in_domain_patterns.yaml` | Operator-curated | **No** |
| `jsearch_queries.txt` | Operator-curated | **No** |
| `feedback_weights.yaml` | Operator-tuned | **No** |
| `companies_of_interest.txt` | Operator-curated | **No** |
| `active_sources.txt` | Per-stack adapter selection | **No** |
| `ntfy_topic.txt` | Operator-allocated | **No** (but trivial to re-allocate) |
| `sheet_id.txt`, `form_responses_sheet_id.txt` | Operator-allocated | **No** (but trivial to re-allocate) |
| `gmail.json` (chmod 600) | Operator-curated (IMAP creds + state) | **No** |
| `gsheets_creds.json` | Operator-curated (service-account JSON) | **No** |
| `gmail_state.json` | Pipeline-generated (IMAP UID checkpoint) | **Yes**, re-syncs on next poll |

Repo-baked (NOT in bind mount; `config/roles/` is symlinked to `/app/config/roles`):

| Path | Source |
|---|---|
| `config/roles/*.md` | Repo (8 role prompts) |
| `config/scoring_schema.json` | Repo |
| `config/model_pricing.yaml` | Repo |
| `config/reference.docx` | Repo (pandoc resume template) |
| `config/strip-bookmarks.lua` | Repo |
| `config/paths.env.example`, `config/*.example` | Repo (templates) |

### 1.4 `data/` — secrets + sentinel + LinkedIn graph

| Path | Source | Rebuildable? |
|---|---|---|
| `data/.env` (chmod 0640) | Operator-curated (OpenRouter / RapidAPI / Google keys, NTFY_TOPIC, etc.) | **No** without re-collecting all credentials |
| `data/.onboarding-complete` | Sentinel (NUX gate) | **Yes**, re-emit on next interview |
| `data/connections.csv` | Operator-uploaded (LinkedIn export) | **Yes**, by re-exporting from LinkedIn |

Stragglers seen in operator's stack (cleanup candidates, not state):
- `data/rescore_backfill.py` — script that wandered into `data/` from a one-off backfill run; doesn't belong here
- `data/.env.bak`, `data/.env.bak.1777125648` — manual env backups (same-host)
- `data/pipeline.db.bak*` — manual DB backups (same-host)

### 1.5 `companies/` (~22 MB)

| Path | Source | Rebuildable? |
|---|---|---|
| `companies/{Co}_{AbbrevTitle}_{date}_{HHMMSS}/` (active) | Pipeline-generated (briefing, tailored resume, cover letter, outreach, recruiter critique) | **Partial** — re-runnable per-job, but JD is no longer reachable for stale postings |
| `companies/_applied/`, `_waitlisted/`, `_rejected/`, `.stale/` | Same artifacts after stage transitions | **Same as above** |

Operator's stack has 169 total folders: 69 applied, 75 rejected, 14 waitlisted, 10 stale, 1 active.

### 1.6 `logs/` (~5.4 MB)

| Path | Source | Rebuildable? |
|---|---|---|
| `logs/pipeline.jsonl` | Pipeline-generated (structured event log) | **No** — historical observability lost if dropped |
| `logs/{form-ingest,jobsync,poller,triage,notify,ci-check,rescore_backfill}.log` | Legacy / pipeline-generated | Mostly stale; safe to drop |

### 1.7 `aichat_ng/`

| Path | Source | Rebuildable? |
|---|---|---|
| `aichat_ng/config.yaml` | Operator-curated (API keys mirror — duplicates `data/.env`) | **No**, but `data/.env` is the source of truth |
| `aichat_ng/models-override.yaml` | Repo-shipped + operator overrides | **Yes**, repo-shipped baseline |
| `aichat_ng/rags/` | Pipeline-generated (REPL RAG index over `candidate_context/`) | **Yes**, rebuilt weekly Sun 03:00 cron |

### 1.8 What's NOT in the bind mount

Worth saying explicitly: the `ghcr.io/brockamer/findajob:*` image carries the package, role prompts, schema migrations, supercronic schedules, and `aichat-ng` binary. Pulling a fresh tag re-hydrates all of that. The bind mount holds **only** the operator-curated and pipeline-history layer.

### 1.9 Loss-impact summary

| Lost | Recoverable from | Time cost |
|---|---|---|
| `pipeline.db` | Nothing (no off-host backup) | Total — start over from scratch |
| `candidate_context/` | Re-interview + LinkedIn | ~3–6 hours of operator time + lost hand-tuning |
| `config/` (operator-curated parts) | Re-interview emits ~half; hand-curation gone | Days of accumulated drift |
| `data/.env` | Re-collect every credential | Hours; rotation-grade pain |
| `companies/` | Re-run prep on each row in `pipeline.db` (if DB survived) | Cheap if DB intact |
| `data/connections.csv` | Re-export from LinkedIn | Minutes |
| `logs/pipeline.jsonl` | Nothing | Observability gap, not work loss |
| Image (`ghcr.io/brockamer/findajob:tag`) | `docker compose pull` | Minutes |

The data layer is the only thing that can't be regenerated by `docker compose pull` + a fresh interview. **Treating the bind mount as if it were reproducible has worked so far because nothing has gone wrong; it stops working the first time something does.**

---

## 2. Vocabulary leakage scan

### 2.1 Critical finding — reject-reason vocabulary leak + drift bug

The reject-reason taxonomy is duplicated across **four** sites with **two divergent lists**:

| Site | List | Notes |
|---|---|---|
| `src/findajob/web/templates/board/_reject_cell.html:34-44` | `Too Senior, Too Junior, Skills Mismatch, Too TPM-Heavy, Geography/Onsite, Company Not a Fit, Comp Too Low, Low Fit Score, Stale/Closed, Already Applied, Other` | **Operator-flavored.** This is the dropdown the operator actually uses. |
| `scripts/setup_sheets.py:87` (`REJECT_OPTIONS`) + `:121` (`REJECT_COLORS`) | Same as above | **Operator-flavored.** Drives Google Sheet validation + colors. |
| `src/findajob/web/routes/stats.py:51` (`REJECT_REASONS`) | Same as above | **Operator-flavored.** Comment claims "mirrors `REJECT_OPTIONS` in setup_sheets.py and the dropdown" — does. |
| `scripts/analyze_feedback.py:242-243` | Same set, also references `Too Software/Systems` | **Operator-flavored.** |
| `src/findajob/web/filters/registry.py:41` (`_REJECT_REASON_VALUES`) | `Low Fit Score, Not Interested, Compensation, Location, Company Culture, Role Mismatch, Already Applied, Stage Too Early, Stage Too Late, Recruiter Outreach, Other` | **Generic — diverged.** This is the per-column filter chip vocabulary. |

**Two problems:**

1. **Vocabulary leak (the audit's primary concern).** "Too TPM-Heavy" is operator-domain; Alice in social work has no use for it. The dropdown a tester sees today still carries operator-flavored options. This is the same shape of leak that motivates the issue body's example.
2. **Drift bug (incidental discovery).** `_REJECT_REASON_VALUES` (filter chips) doesn't match the dropdown vocabulary — so filtering the Dashboard by `reject_reason` matches values that don't exist in the data, and filter chips for actual rejections (Too Senior, Skills Mismatch) are missing. This is silently broken filtering.

**Triage:** file as a follow-up issue. Moving the reject-reason vocabulary out of tracked code into a single source of truth (`config/reject_reasons.yaml` or similar, interview-emitted) fixes both the leak and the drift in the same change.

### 2.2 Secondary findings (cosmetic / comment-only)

| Site | Finding | Severity |
|---|---|---|
| `src/findajob/web/company_history.py:9, 33` | Comments cite "Meta" / "Google" / "Google Cloud" as examples of company-name normalization | Cosmetic — comments only, behavior is generic. Consider rewriting as "{CompanyA}" / "{CompanyA Subsidiary}". |
| `src/findajob/web/templates/ingest/form.html:61` | Placeholder text: `"Remote / Menlo Park, CA / Los Angeles, CA"` | Operator-flavored geography in a placeholder. Trivial to genericize: `"Remote / City, State"`. |
| `scripts/diag/validate_resume.py:303` | Comment: "long Meta tenure" as an example | Cosmetic — comment only. |
| `config/roles/resume_tailor.md:127` | Example: "hardware skills near other hardware skills" | Acceptable — illustrative example, prompt itself is profile-driven. |

### 2.3 What was checked and is NOT a leak

- **Stage / status enums** (`discovered`, `applied`, `interview`, `rejected`, `waitlisted`, etc.) — domain-neutral universal job-search states. Fine.
- **Score flag reasons** (`excluded_employer`, `Scorer timeout`, `Validation: <error>`) — framework-level, not operator-domain. Fine.
- **"Tier 1"** terminology — used as a candidate-defined tier framework; the onboarding interviewer prompt explicitly teaches users to define their own Tier 1 with social-work / healthcare / education examples. Generic framework, not a leak.
- **Title vocabulary in `job_scorer.md`** ("engineer", "manager", "director") — used as examples to teach the scorer that titles alone aren't disqualifying. Generic, not a leak.
- **`interview_prep.md:76`** — explicitly enumerates per-field examples ("for an infrastructure/ops candidate ... for a clinical candidate ... for a sales candidate"). This is *good* generalization documentation, not a leak.
- **Notification subject lines in `notify.py`** — templated, no operator-specific tokens.

---

## 3. Recommendations & follow-ups

The implementation pieces of the original #301 acceptance criteria are filed as follow-up issues against this audit. Each links back here for the inventory + rationale; this audit's parent issue (#301) closes once the follow-ups are filed, and this spec stays current until all four follow-ups (#426, #427, #428, #429) ship.

### 3.1 Backup mechanism — #426 (criterion 2 — split out)

**Recommended shape:**
- Per-stack nightly tarball of `/opt/stacks/findajob-{handle}/state/` written to a sibling host on the same Proxmox cluster
- Excludes `companies/.stale/`, `aichat_ng/rags/`, transient `.bak` files
- 14-day rotation
- SQLite dumped via `.backup` rather than file-copy (handles WAL safely)
- Restore procedure exercised on a fresh stack annually + on every onboarding/schema-touching release

Cloud / off-host destinations are explicitly out of scope for v1 — same-Proxmox sibling host is the appetite-fit choice given the user count.

### 3.2 `docs/setup/` Backups section — #427 (criterion 4 — split out)

Documents:
- What the backup script captures and excludes
- Where backups land
- Step-by-step restore on a fresh `docker.lan` stack (and verification: re-run triage against the restored DB and confirm board state matches)

### 3.3 `CLAUDE.md` data-ownership table — #428 (criterion 5 — split out)

A new table mirroring the Container Context table but classifying state by ownership (operator-authored / pipeline-generated / mixed) and backup status. Becomes the canonical answer to "what gets backed up and what's reproducible?" so future work doesn't re-derive it.

### 3.4 Reject-reason vocabulary leak + drift fix — #429

Single follow-up issue covering both the leak (move taxonomy out of tracked code into operator-curated config; emit from interview) and the drift (single source of truth for all four sites). Minor placeholder/comment cleanups (§2.2) folded into the same issue if cheap.

### 3.5 Stale stragglers in `data/` (cleanup)

Operator-stack-only chore — out of scope for #301 but worth surfacing:
- `data/rescore_backfill.py` belongs in `scripts/`, not `data/`
- Manual `.bak` files in `data/` predate any backup scheme; keep until backup mechanism lands, then prune

---

## 4. Closing #301

This audit is the deliverable. Once the four follow-up issues (#426 backup mechanism, #427 restore docs, #428 ownership table, #429 reject-reason fix) are filed and linked, #301 closes. This spec doc stays in `docs/superpowers/specs/` (not archived) until all four follow-ups ship.
