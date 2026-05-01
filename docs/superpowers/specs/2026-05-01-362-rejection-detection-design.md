# Auto-detect company rejection emails via Gmail and suggest status change — Design Spec

## Issue(s)
- #362 — Auto-detect company rejection emails via Gmail and suggest status change

**Date:** 2026-05-01
**Status:** Draft — grounded in 2026-05-01 corpus walk of operator's Gmail
**Related work:** #330 (Gmail IMAP transparency contract), #344 (multi-tenant scheduler), #371 (graceful no-op for unconfigured stacks)

---

## 1. Context

Today, when a company decides not to move a candidate forward, the operator finds out via email and manually flips the row on the Applied tab to `not_selected` with a `reject_reason`. This works but has two known drift modes:

1. **Missed rejections.** Empirical scan of operator's Gmail on 2026-05-01 against the 54 currently-applied jobs surfaced at least 3 rejection emails the DB had not yet caught up with — Zoox (Lever), CoreWeave (Greenhouse, twice), and Fluidstack (Ashby). The Applied tab still shows them as live applications. This understates the silence/ghosting picture and bloats `days_since_applied`.

2. **Unread inbox cost.** The operator already opens these emails by hand to mark the row. There is no value-add from human reading; the email is templated and the action is mechanical.

The DB stage `not_selected` already exists with a one-way transition (`applied → not_selected`) wired through `POST /board/jobs/{fp}/not-selected`, and the action correctly skips the scorer feedback loop (company rejections are not scoring signal — the operator's *own* rejections are). The piece missing is: detect a rejection email, identify the matching applied job, and surface a one-click confirmation to the operator.

The framing in #362's title is **suggest** — human-in-loop. This spec preserves that framing throughout. There is no pathway in this design that auto-flips a row without operator confirmation.

## 2. Objectives

| Role | Metric | Treatment |
|---|---|---|
| **Primary objective** | Inbox-detected rejections surface in findajob within ≤30 min, requiring one click to apply | Pipeline scheduled job (cron) + Dashboard widget |
| **Hard floor — no silent state changes** | The mechanism must never write `stage=not_selected` without operator click | Suggestions queue, never direct mutation |
| **Hard floor — IMAP transparency** | Continues to honor `docs/superpowers/specs/2026-04-30-330-design.md` IMAP contract | Read-only verbs only (no STORE / EXPUNGE / MOVE) |
| **Hard floor — no scorer contamination** | Detected rejections must take the `not_selected` path, not `rejected`, so feedback_log stays clean | Reuse existing `handle_not_selected` action |
| **Soft floor — high precision** | False positives are worse than false negatives — a wrong "suggest" trains the operator to ignore the widget | Layered detection (sender + body markers) before optional LLM tiebreaker |
| **Soft floor — multi-tenant** | Mechanism must work for any tester, not just operator's stack | Reuse per-stack `config/gmail.json` already in place; no new global state |
| **Generalization gate** | Diff of tracked files | No company names, candidate names, or domain-specific phrasing baked in — patterns live in a config file |

## 3. Empirical grounding (2026-05-01 corpus walk)

54 applied jobs in operator's DB; 47 distinct companies. Sampled the operator's Gmail inbox for application correspondence in the matching window.

### 3.1 ATS / sender taxonomy observed

| Platform | Sender pattern | Ack subject | Rejection subject | Rejection body marker |
|---|---|---|---|---|
| Greenhouse | `no-reply@us.greenhouse-mail.io`, `no-reply@eu.greenhouse-mail.io` | "Thank you for applying to {Company}" | "Important information about your application to {Company}" | "Unfortunately, we are not moving forward with" |
| Ashby | `no-reply@ashbyhq.com` | "{Company} \| Application Received" | "Thank you for your interest in {Company}" / "{Company} Application Update" | "decided to move forward with other candidates whose [...] more closely [aligns/match]" |
| Lever | `no-reply@hire.lever.co` | (none observed yet) | "Thanks for your interest in {Company}, {Name}" | "decided to pursue other candidates whose backgrounds and experience more closely align" |
| Workday-style | `no-reply@talent.{company}.com`, `{company}@myworkday.com` | "Thank you for your interest in {Company}" | "Update on your application for the position {Title}" | "After careful review of your application" |
| Smartrecruiters | `notification@smartrecruiters.com` | "Your Application for {Title} at {Company}" | (not yet observed in corpus) | n/a |
| Microsoft Careers | `donotreply@email.careers.microsoft.com` | "Thank you for your application!" | (not yet observed) | n/a |
| Oracle Talent | `noreply@oracle.com` | "We received your application" / "Thank you for your application to Oracle" | (not yet observed) | n/a |
| In-house bulk | `no-reply@{company}.com` (Atari, Lightmatter, Tenstorrent, Nscale, Waymo, xAI, Tesla, OpenAI, etc.) | varies — "Thank you for your application/interest" | varies — "Update about your application status", "Thank you for your interest in {Company}" | varies — "yours was not selected for further consideration", "the position has been filled", "we are no longer accepting applications" |
| LinkedIn relay | `jobs-noreply@linkedin.com`, `jobalerts-noreply@linkedin.com` | "Your application to {Title} at {Company}" | LinkedIn does not relay rejections — out of scope as a source | n/a |

### 3.2 High-precision rejection phrases

These phrases are present in confirmed rejection bodies and absent from confirmed acks. The detector treats any one of these as a strong rejection signal:

- "decided to move forward with other candidates"
- "decided to pursue other candidates"
- "Unfortunately, we are not moving forward"
- "will not be moving forward"
- "yours was not selected"
- "your application was not selected"
- "regret to inform"
- "the position has been filled"
- "no longer accepting applications"
- "we have decided not to proceed"

### 3.3 Acknowledgment phrases (must NOT trigger)

- "Thank you for applying to..."
- "Your application has been received"
- "We will review your application shortly"
- "Application Received"

Empirically, the same ATS sends both ack and rejection from the same sender address. Subject line alone is not a reliable separator — Ashby acks and rejections both lead with "Thank you for your interest". **Body content is what differentiates.**

### 3.4 Edge cases observed in the corpus

- **Soft pause** (Lambda — `elysse.curry@lambdal.com`): "We are pausing the recruitment process for this site until Fall 2026." This is a rejection-equivalent for purposes of `days_since_applied` accounting, but with a distinct reason ("Position paused, will reconsider later"). Worth surfacing as `not_selected` with a sub-reason.
- **Position filled** (Tenstorrent): "The position has been filled and we are no longer accepting applications." — rejection-equivalent.
- **Repeat applications to the same role** (CoreWeave applied 2026-04-10, rejected 2026-04-13, applied again 2026-04-23): the matching algorithm must scope to the most recent active `applied` audit_log entry, not just `jobs.id`.
- **Wrong-name salutations** (Zoox rejection addresses operator as "John", Tesla ack also "John", Oracle ack "Hello John"): the salutation is unreliable cross-correspondence; do not condition detection on candidate name. Sender + body markers + role/company match are sufficient.
- **LinkedIn-applied jobs (Ellaway Blues, Blue Signal)** receive only LinkedIn's "Your application was sent to {Company}" relay; the company itself does not email through Gmail. These rejections will continue to require manual marking.

## 4. Architecture

### 4.1 Pipeline placement

A new scheduled job `scripts/detect_rejections.py` runs every 30 minutes via supercronic (`ops/scheduled-jobs.yaml`). It reuses the existing per-stack `gmail_imap.py` connection — no new credentials, no new IMAP verbs.

```
+-----------------------+      +-----------------------+      +-----------------------------+
|  scripts/             |      |  findajob.            |      |  Dashboard widget           |
|  detect_rejections.py | ---> |  rejection_detector   | ---> |  /board?suggested_rej=N     |
|  (cron, 30 min)       |      |  (new module)         |      |  one-click confirm          |
+-----------------------+      +-----------------------+      +-----------------------------+
         |                            |
         v                            v
  +--------------+         +-------------------------+
  | gmail_imap   |         | rejection_suggestions   |
  | (existing)   |         | (new SQLite table)      |
  +--------------+         +-------------------------+
```

### 4.2 New module — `src/findajob/rejection_detector/`

Pure-data package, no FastAPI imports. Consumes `bytes` (raw RFC 822) and `dict` (jobs row), emits `RejectionSuggestion | None`. Easily unit-testable from fixtures.

- `patterns.py` — config-driven `SENDER_FINGERPRINTS`, `REJECTION_BODY_MARKERS`, `ACK_BODY_MARKERS`, `SOFT_PAUSE_MARKERS`. Single source of truth; not hardcoded in detector logic.
- `parser.py` — extract `(sender_domain, subject, plaintext_body, html_body, candidate_company, candidate_role)` from a raw email. Body extraction handles both `text/plain` and `text/html` (strip via `bs4` — already a transitive dep of httpx? if not, add).
- `classifier.py` — three-layer cascade:
  1. **Layer 1 (sender+body):** Match `sender_domain` against `SENDER_FINGERPRINTS`. If sender matches a known ATS, scan body for `REJECTION_BODY_MARKERS` + absence of `ACK_BODY_MARKERS`. Strong match → emit `confidence='high'`.
  2. **Layer 2 (body-only):** If sender unknown but body contains a rejection marker, emit `confidence='medium'` (still surface to operator, but flag as needs-review).
  3. **Layer 3 (LLM tiebreak):** Reserved for ambiguous cases — sender known but body markers conflict, or for `SOFT_PAUSE_MARKERS`. Use `openrouter:google/gemini-3-flash-preview` (cheapest deterministic-ish model already in the stack); cap at `max_tokens=128`, prompt asks for JSON `{is_rejection: bool, reason: str, role: str|null}`. Out of scope for v1 — add only if Layer 1+2 precision falls below 95% on the operator's corpus.
- `matcher.py` — given `(extracted_company, extracted_role, email_received_at)`, find the candidate `jobs.id`:
  - Filter `jobs` to `stage IN ('applied', 'materials_drafted')` AND `synthetic = 0`.
  - Tokenize+lowercase company; require token-set overlap ≥ 0.8 (use `rapidfuzz` — already a dep).
  - If multiple candidates by company, narrow by role title (token-set ≥ 0.6).
  - On exactly one match: emit suggestion. On ambiguity: emit suggestion with `match_status='ambiguous'`. On zero: emit suggestion with `match_status='unmatched'` (operator can manually attach).

### 4.3 New SQLite table — `rejection_suggestions`

```sql
CREATE TABLE rejection_suggestions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    gmail_message_id TEXT NOT NULL UNIQUE,    -- IMAP UID + folder, dedup key
    received_at TEXT NOT NULL,                -- email date header, ISO-T
    detected_at TEXT NOT NULL DEFAULT (datetime('now')),
    sender TEXT NOT NULL,
    subject TEXT NOT NULL,
    body_excerpt TEXT NOT NULL,               -- first 500 chars of plaintext, for UI preview
    extracted_company TEXT,
    extracted_role TEXT,
    matched_job_id TEXT,                      -- nullable; FK to jobs.id when single match
    match_status TEXT NOT NULL,               -- 'matched' | 'ambiguous' | 'unmatched'
    confidence TEXT NOT NULL,                 -- 'high' | 'medium'
    suggested_reason TEXT NOT NULL,           -- 'Company passed' | 'Position filled' | 'Position paused' | 'Other'
    user_action TEXT NOT NULL DEFAULT 'pending',  -- 'pending' | 'confirmed' | 'rejected' | 'reattributed'
    user_action_at TEXT,
    user_chose_job_id TEXT                    -- when match_status='ambiguous' or 'unmatched' and user picked
);
CREATE INDEX rejection_suggestions_user_action ON rejection_suggestions(user_action);
CREATE INDEX rejection_suggestions_matched_job ON rejection_suggestions(matched_job_id);
```

`gmail_message_id` is the dedup key — a row per inbound email, never re-processed. The state survives operator action (rows stay in the table; `user_action` is updated) so the audit trail is preserved.

### 4.4 IMAP changes to `gmail_imap.py`

Minimal additive changes to preserve the transparency contract (#330):

- Extend `sender_allowlist` semantics: today it gates *which senders are scanned for jobs*. The new use case is *which senders are scanned for rejections*. The cleanest path is a **second allowlist** in `config/gmail.json`: `rejection_sender_allowlist`. Defaults to the union of ATS platforms in §3.1. Per-tester overrides allowed; in particular, in-house company senders (`no-reply@{company}.com`) are added per-tester since those vary by who applied where.
- New helper `fetch_messages_for_rejection_scan(config, state)` — same `BODY.PEEK` semantics, separate UID checkpoint (`gmail_state.json` gets a sibling key `rejection_last_uid`).
- `pipeline.jsonl` events: `rejection_email_scanned`, `rejection_suggestion_created`, with redacted sender + matched_job_id.

The transparency-invariant tests in `tests/test_transparency_invariants.py` must be extended to cover the rejection scanner — same property: no STORE / COPY / EXPUNGE / APPEND / MOVE / CREATE / DELETE.

### 4.5 Web surface

#### 4.5.1 Dashboard widget

A new tile on `/board/dashboard/` (above the queue, below the score histogram):

> **3 rejection emails detected** — [Review] [Dismiss all]

Pending count = `SELECT COUNT(*) FROM rejection_suggestions WHERE user_action='pending'`. Tile only renders when count > 0.

#### 4.5.2 Review page — `/board/rejections-review/`

Card-per-suggestion layout. Each card:
- **Header:** sender, subject, received date.
- **Body excerpt:** first 500 chars of plaintext.
- **Match info:** `matched_job_id` rendered as job title + applied date if `match_status='matched'`. If ambiguous/unmatched, dropdown of recent applied jobs.
- **Suggested reason:** dropdown defaulting to `suggested_reason` from the row. Operator can change.
- **Actions:** `[Confirm — mark Not Selected]` | `[This isn't a rejection]` | `[Skip for now]`

`Confirm` posts to `POST /board/rejections-review/{id}/confirm`, which:
1. Looks up `matched_job_id` (or `user_chose_job_id`).
2. Calls `findajob.actions.handle_not_selected(job_id, reason)` — same code path as the existing manual flow. Writes audit_log, moves folder, leaves `feedback_log` untouched.
3. Updates `rejection_suggestions.user_action='confirmed'`.

`This isn't a rejection` sets `user_action='rejected'`. `Skip for now` is a no-op (row stays `pending`).

#### 4.5.3 No new write surfaces beyond `findajob.actions.handle_not_selected`

The existing `not-selected` action is the only writer to `stage`. The new endpoint orchestrates but does not re-implement. This preserves the "Web is the Write Surface" rule (CLAUDE.md §Critical Architecture Rules).

### 4.6 ntfy integration

When `detect_rejections.py` finds suggestions, it sends a single ntfy notification:

> **2 new rejection emails detected** — [Review on Dashboard]

Throttled to once per detection cycle even if multiple suggestions land. Reuses `scripts/notify.py` infrastructure.

## 5. Detection algorithm — formal pseudocode

```python
def classify_email(raw_email: bytes) -> RejectionSuggestion | None:
    parsed = parser.parse(raw_email)

    # Hard skips — no point spending compute
    if parsed.sender_domain in NON_RECRUITING_DOMAINS:        # linkedin.com job-alerts, indeed
        return None
    if parsed.subject_lower.startswith(("re:", "fwd:")):       # operator replied; not a fresh rejection
        return None

    # Layer 1 — sender fingerprint + body markers
    sender_fp = patterns.match_sender(parsed.sender_domain)
    has_rej_marker = patterns.has_rejection_marker(parsed.plaintext_body)
    has_ack_marker = patterns.has_ack_marker(parsed.plaintext_body)

    if sender_fp and has_rej_marker and not has_ack_marker:
        confidence = "high"
    elif has_rej_marker and not has_ack_marker:               # unknown sender, strong body
        confidence = "medium"
    else:
        return None                                            # acks and unknowns drop out

    # Soft-pause subtype
    suggested_reason = "Company passed"
    if patterns.has_soft_pause_marker(parsed.plaintext_body):
        suggested_reason = "Position paused"
    elif patterns.has_position_filled_marker(parsed.plaintext_body):
        suggested_reason = "Position filled"

    # Match to a job
    extracted = parser.extract_company_and_role(parsed)
    match = matcher.match_job(extracted.company, extracted.role, parsed.received_at)

    return RejectionSuggestion(
        gmail_message_id=parsed.message_id,
        received_at=parsed.received_at,
        sender=parsed.sender,
        subject=parsed.subject,
        body_excerpt=parsed.plaintext_body[:500],
        extracted_company=extracted.company,
        extracted_role=extracted.role,
        matched_job_id=match.job_id,
        match_status=match.status,                             # 'matched' | 'ambiguous' | 'unmatched'
        confidence=confidence,
        suggested_reason=suggested_reason,
    )
```

## 6. Migration

- New `rejection_suggestions` table: idempotent `CREATE TABLE IF NOT EXISTS` in `init_db.py`.
- New `rejection_sender_allowlist` key in `config/gmail.json`: defaults to the ATS list in §3.1 if absent. Per-tester additions made via `/config/gmail/` editor (existing UI).
- New cron entry in `ops/scheduled-jobs.yaml`: `detect-rejections` every 30 min, staggered per-stack via the existing `_offset_for_stack` mechanism (#344).
- Documentation: `docs/usage.md` adds a "Rejection detection" subsection. `CLAUDE.md` §Pipeline Context Table adds the new role/script.
- `### Migration required` bullet in `CHANGELOG.md` — none, all changes are additive (new table, new sender allowlist key with safe default, new cron job).

## 7. Open questions

1. **HTML-only emails.** Some senders ship HTML-only (no `text/plain` part). Confirm the corpus rate and decide whether `bs4` strip is sufficient or if more aggressive normalization is needed. Initial sample suggests ~80% have plaintext. Body extraction needs a fallback path; treat as a Task 1 implementation concern.
2. **Confidence threshold for unattended suggestions.** The widget currently surfaces both `high` and `medium`. If `medium` proves noisy (false positives from generic body matches on non-ATS senders), gate the widget to `high` only and bury `medium` behind a "Show low-confidence" toggle. Decide post-launch with first-week telemetry.
3. **Recruiter follow-ups misclassified.** A recruiter writing "We're not moving forward with the senior role but want to discuss the staff role" is *not* a rejection of the candidate, just of one role. Heuristic: if the matched job's title is in the body alongside a rejection phrase AND another role title also appears, mark `confidence='medium'` and let the operator review. Not v1; flag in code with a TODO.
4. **Multi-tenant pattern updates.** The pattern config (`patterns.py`) lives in tracked code; new ATS senders detected on tester stacks should propagate back to all stacks. Decide: is this `pip install -e .` updates only (operator pushes new version), or hot-reloadable via a config file? Default: tracked code, ship via release. Hot-reload deferred until pattern churn justifies it.
5. **Does the operator want bulk-confirm?** "Confirm all matched-high suggestions in one click" reduces friction but trades off oversight. Initial design: per-card confirm. Add bulk only if usage telemetry shows operator confirms ≥80% of high-confidence suggestions unchanged.

## 8. Dependencies and assumptions

- `gmail_imap.py` exists and works on operator + tester stacks (confirmed; v0.8 multi-tenant rollout).
- `findajob.actions.handle_not_selected` is the canonical writer for `stage=not_selected` (confirmed in `src/findajob/actions.py`).
- `rapidfuzz` is already a dep (confirmed in `pyproject.toml`).
- `bs4` (BeautifulSoup) is *not* yet a direct dep but is transitively available; treat as a Task 1 verification — add to `pyproject.toml` if not present.
- The existing `/board/dashboard/` template has a clear region for the new tile (confirmed by template inspection — there's a header section above the queue table).

## 9. Issue acceptance criteria — mapping

| #362 acceptance criterion | Spec section |
|---|---|
| Detect company rejection emails in Gmail | §4.1, §5 |
| Suggest (not auto-apply) status change | §4.5.2, §4.5.3 |
| Match to existing applied job | §4.2 (matcher.py), §5 |
| Don't contaminate scorer feedback loop | §2 hard floor + §4.5.3 (reuses `handle_not_selected`) |
| Multi-tenant — works for testers too | §2 generalization gate, §4.4, §6 |

---

## Implementation note (post-approval)

Once this spec is approved, an implementation plan will land at `docs/superpowers/plans/2026-MM-DD-362-rejection-detection-c0.md` enumerating:
1. Schema migration + `rejection_suggestions` table
2. `findajob.rejection_detector` package + tests against fixtures derived from the 2026-05-01 corpus
3. `gmail_imap.py` extension + extended transparency tests
4. `scripts/detect_rejections.py` entry point + cron registration
5. Web routes + templates + Dashboard widget integration
6. ntfy integration + throttling
7. Whole-feature verification gate on operator's stack first, then Phase 3 testers
8. Documentation
