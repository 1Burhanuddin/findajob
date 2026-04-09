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

**Filter:** jobs with `relevance_score >= 7 AND stage IN (scored, manual_review)` OR `stage = materials_drafted`.

**Sort:** `materials_drafted` jobs first (most actionable), then by score descending.

Columns A–L:
| Col | Field | Who writes it |
|---|---|---|
| A | STATUS | You (via dropdown) |
| B | REJECT_REASON | You (via dropdown) |
| C | fingerprint (hidden) | System |
| D | relevance_score | System |
| E | title (hyperlink) | System |
| F | company | System |
| G | location | System |
| H | remote_status | System |
| I | known_contacts | System |
| J | comp_estimate | System |
| K | ai_notes | System |
| L | date_found | System |

---

## STATUS Dropdown (col A)

The STATUS dropdown drives the entire application workflow.

| Value | Set by | What happens |
|---|---|---|
| *(empty)* | System (default) | No action |
| `Flag for Prep` | You | `poll_flags.py` triggers `prep_application.py` within 30 min |
| `Ready to Apply` | System | Set automatically when `stage=materials_drafted` (prep done) |
| `Applied` | You | `poll_flags.py` updates DB `stage=applied` |
| `Interviewing` | You | `poll_flags.py` updates DB `stage=interview` |
| `Offer` | You | `poll_flags.py` updates DB `stage=offer` |
| `Withdrew` | You | `poll_flags.py` updates DB `stage=withdrawn` |

**Important:** `Ready to Apply` is system-set. Setting it manually has no effect on the DB — the poller ignores it.

---

## REJECT_REASON Dropdown (col B)

Setting any value in REJECT_REASON triggers the rejection workflow.

**What happens when you set REJECT_REASON:**
1. `poll_flags.py` (within 30 min) detects the value
2. DB updated: `stage=rejected`, `reject_reason=<value>`
3. Row written to `feedback_log` table (for pattern analysis)
4. If a prep folder exists for this job: it is moved to `companies/_done/`
5. `rclone bisync` fires immediately (non-blocking) to sync the move to Google Drive
6. Job disappears from Dashboard on next sync (stage=rejected no longer matches the filter)

Rejection takes priority over `Flag for Prep` in the same poll cycle.

**Tip:** You can reject and prep at the same time by setting both — rejection wins. If you change your mind after rejecting, you'd need to manually update the DB.

---

## Color Coding

| Column | Color trigger | Color |
|---|---|---|
| STATUS col A | `Flag for Prep` | Entire row turns light blue |
| STATUS col A | `Ready to Apply` | Entire row turns teal |
| STATUS col A | `Applied` | Entire row turns green |
| STATUS col A | `Interviewing` | Entire row turns purple |
| STATUS col A | `Offer` | Entire row turns gold |
| STATUS col A | `Withdrew` | Entire row turns grey |
| REJECT_REASON col B | Any value | Cell gets a distinct color per reason |
| remote_status col H | `Remote` | Red background |
| remote_status col H | `Hybrid` | Yellow background |
| remote_status col H | `On-site`/`Onsite` | Green background |
| known_contacts col I | Non-empty | Amber background |
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
