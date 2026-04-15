# Google Sheets

The Google Sheet is the primary human interface for the pipeline. SQLite is the source of truth — the sheet is a synced view.

---

## Tabs

### Sheet1 — Full Archive

All jobs that passed deduplication. Reference view only — not interactive (except the APPLY_FLAG checkbox, which is a legacy field). Use the Dashboard for workflow actions.

Columns A–N:
| Col | Field |
|---|---|
| A | fingerprint (hidden) |
| B | APPLY_FLAG (checkbox) |
| C | relevance_score |
| D | title |
| E | company |
| F | location |
| G | remote_status |
| H | stage |
| I | known_contacts |
| J | comp_estimate |
| K | ai_notes |
| L | date_found |
| M | source |
| N | url |

Rejected rows are greyed out (conditional formatting on `stage="rejected"`).

---

### Dashboard — Actionable Queue

The working view. Updated by `sync_sheet.py` (runs after triage and after every prep).
`poll_flags.py` reads this tab every 30 minutes and acts on STATUS and REJECT_REASON.

**Filter:** jobs with `relevance_score >= 7 AND stage IN (scored, manual_review, prep_in_progress)` OR `stage = materials_drafted`.

**Sort:** `materials_drafted` jobs first (most actionable), then by score descending.

Columns A–N:
| Col | Field | Who writes it |
|---|---|---|
| A | STATUS | You (via dropdown) |
| B | REJECT_REASON | You (via dropdown) |
| C | fingerprint (hidden) | System |
| D | fit_score | System |
| E | probability_score | System |
| F | relevance_score | System |
| G | title (hyperlink) | System |
| H | company | System (hyperlink to Drive folder when prepped) |
| I | location | System |
| J | remote_status | System |
| K | known_contacts | System |
| L | comp_estimate | System |
| M | ai_notes | System |
| N | date_found | System |

---

## STATUS Dropdown (col A)

The STATUS dropdown drives the entire application workflow.

| Value | Set by | What happens |
|---|---|---|
| *(empty)* | System (default) | No action |
| `Flag for Prep` | You | `poll_flags.py` triggers `prep_application.py` within 30 min |
| `Prep in Progress` | System | Set when prep is actively running (prevents duplicate triggers) |
| `Regenerate` | You | Deletes existing prep folder and re-runs prep from scratch |
| `Ready to Apply` | System | Set automatically when `stage=materials_drafted` (prep done) |
| `Waitlist` | You | Defers the job — folder moves to `_waitlisted/`, appears on Waitlist tab |
| `Applied` | You | `poll_flags.py` updates DB `stage=applied`, moves folder to `_applied/` |
| `Interviewing` | You | `poll_flags.py` updates DB `stage=interview` |
| `Offer` | You | `poll_flags.py` updates DB `stage=offer` |
| `Not Selected` | You | Company rejected — `stage=not_selected`, folder stays in `_applied/`, no feedback_log |
| `Withdrew` | You | `poll_flags.py` updates DB `stage=withdrawn` |

**Important:** `Ready to Apply` and `Prep in Progress` are system-set. Setting them manually has no effect on the DB — the poller ignores them.

---

## REJECT_REASON Dropdown (col B)

Behavior depends on the STATUS column:

**If STATUS = `Not Selected` (company rejection):**
1. `poll_flags.py` (within 30 min) detects the value
2. DB updated: `stage=not_selected`, `reject_reason=<value>`
3. No `feedback_log` write (company rejections don't contaminate the scorer)
4. Folder stays in `companies/_applied/` with a `NOT_SELECTED_{reason}_{date}.txt` marker file
5. Waitlisted jobs at the same company are surfaced via ntfy notification

**Otherwise (user rejection):**
1. `poll_flags.py` (within 30 min) detects the value
2. DB updated: `stage=rejected`, `reject_reason=<value>`
3. Row written to `feedback_log` table (for pattern analysis)
4. If a prep folder exists for this job: it is moved to `companies/_rejected/`
5. rclone sync fires immediately (non-blocking) to push the move to Google Drive
6. Job disappears from Dashboard on next sync

"Not Selected" is checked before generic rejection in the poll cycle to prevent routing errors.

**Tip:** You can reject and prep at the same time by setting both — rejection wins. If you change your mind after rejecting, you'd need to manually update the DB.

---

## Review Tab — Manual Review Triage

Jobs that the scorer flagged for human review (null scores, schema validation failures, edge cases).

**Filter:** `stage = manual_review`

Columns A–H:
| Col | Field | Who writes it |
|---|---|---|
| A | STATUS | You (dropdown: `Promote`) |
| B | REJECT_REASON | You (dropdown — same options as Dashboard) |
| C | fingerprint (hidden) | System |
| D | title (hyperlink) | System |
| E | company | System |
| F | score_flag_reason | System — why the scorer flagged this job |
| G | source | System |
| H | date_found | System |

**Promote:** `poll_flags.py` sets `score=7, stage=scored` → job appears on Dashboard.
**REJECT_REASON:** same rejection workflow as Dashboard.

---

## Waitlist Tab — Deferred Jobs

Jobs you want to keep but aren't ready to pursue yet. Not a rejection — does not write to `feedback_log` or contaminate the scorer feedback loop.

**Filter:** `stage = waitlisted`

Columns A–K:
| Col | Field | Who writes it |
|---|---|---|
| A | STATUS | You (dropdown: `Reactivate`) |
| B | REJECT_REASON | You (dropdown — same options as Dashboard) |
| C | fingerprint (hidden) | System |
| D | title (hyperlink) | System |
| E | company | System |
| F | relevance_score | System |
| G | location | System |
| H | remote_status | System |
| I | ai_notes | System |
| J | date_found | System |
| K | blocking_app | System — active application at same company (title + stage) |

**Reactivate:** restores to `scored` (no folder) or `materials_drafted` (has folder), moves folder back from `_waitlisted/`.
**REJECT_REASON:** rejects the job from the waitlist (same workflow as Dashboard).
**blocking_app:** computed at sync time. When an active application at the same company is rejected or withdrawn, `notify.py` sends a notification to surface the waitlisted job.

---

## Rejected Applications Tab

Read-only reference view of jobs that were rejected after reaching the `applied` stage. Useful for tracking company-side rejections.

Columns A–H:
| Col | Field |
|---|---|
| A | title (hyperlink) |
| B | company (hyperlink to Drive folder if available) |
| C | reject_reason |
| D | applied_date |
| E | rejected_date |
| F | fit_score |
| G | probability_score |
| H | ai_notes |

---

## Color Coding

| Column | Color trigger | Color |
|---|---|---|
| STATUS col A | `Flag for Prep` | Entire row turns light blue |
| STATUS col A | `Prep in Progress` | Entire row turns warm yellow |
| STATUS col A | `Regenerate` | Entire row turns warm orange |
| STATUS col A | `Ready to Apply` | Entire row turns teal |
| STATUS col A | `Waitlist` | Entire row turns warm amber |
| STATUS col A | `Applied` | Entire row turns green |
| STATUS col A | `Interviewing` | Entire row turns purple |
| STATUS col A | `Offer` | Entire row turns gold |
| STATUS col A | `Withdrew` | Entire row turns grey |
| REJECT_REASON col B | Any value | Cell gets a distinct color per reason |
| remote_status col J | `Remote` | Red background |
| remote_status col J | `Hybrid` | Yellow background |
| remote_status col J | `On-site`/`Onsite` | Green background |
| known_contacts col K | Non-empty | Amber background |
| Sheet1 stage col H | `rejected` | Entire row turns grey with grey text |

---

## Formatting Maintenance

If the sheet loses formatting (tabs reorganized, conditional formatting deleted, etc.):

```bash
python3 scripts/setup_sheets.py
```

This re-applies all formatting. It is idempotent — safe to run at any time. It will:
1. Delete existing row banding and re-add it
2. Replace all conditional formatting rules (not add duplicates)
3. Set all dropdown validations
4. Hide/unhide the correct columns
5. Set column widths

---

## Google Sheet Architecture Notes

**Why SQLite instead of Sheets as database?**
Google Sheets has race conditions when multiple concurrent writes happen. The API has rate limits that cause failures under load. SQLite is ACID, fast, and queryable with SQL. The sheet is purely for display and user input.

**Why read fingerprint (col C) instead of row index?**
The sheet is re-written from scratch on each sync. Row positions are unstable. The fingerprint identifies a job uniquely across both the sheet and the DB.

**Why does the poller run every 30 min instead of instantly?**
launchd/systemd granularity. 30 min is the practical minimum for a scheduled interval. If you need faster response, you can run `python3 scripts/poll_flags.py` manually immediately after flagging.
