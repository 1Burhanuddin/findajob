# Spec: Smart Duplicate Handling on `/ingest/manual`

**Date:** 2026-04-23
**Status:** Approved

## Problem

When the `/ingest/` form detects a loose fingerprint match it currently returns a flat
"Already in DB" amber box with no link and no path forward. The operator is stuck: they
can't find the existing row and can't force the job onto the Dashboard.

## Goal

One form submission should be enough. The response tells the operator exactly where
the existing job is, and automatically re-surfaces it to the Dashboard when that is
the right thing to do.

## Behavior by Stage

When `POST /ingest/manual` hits an existing row, branch on `jobs.stage`:

| Existing stage | Mutation | UI link(s) |
|---|---|---|
| `applied` / `interview` / `offer` / `withdrew` | None | `/board/applied` |
| `not_selected` | None | `/board/rejected` + materials folder (if `prep_folder_path` resolves) |
| `rejected` | Un-reject (see below) | `/board/dashboard` |
| `waitlisted` | Reactivate (see below) | `/board/dashboard` |
| `scored` / `manual_review` / `prep_in_progress` / `materials_drafted` | Refresh (see below) | `/board/dashboard` |

**"Overwrite submitted fields"** applies to all mutating branches: `url`, `location`,
`remote_status`, `raw_jd_text`, `notes`, `known_contacts`. A blank submitted value does
NOT clobber a non-blank existing value.

### Un-reject (stage = `rejected`)

1. Clear `reject_reason`.
2. Set `stage = 'scored'`, `relevance_score = 8`.
3. Overwrite submitted fields.
4. Move prep folder from `companies/_rejected/` back to `companies/` (update
   `prep_folder_path`).
5. Delete all `feedback_log` rows for this job (they reflect a now-superseded user
   rejection and must not contaminate the scorer's feedback loop).
6. Write an `audit_log` entry: `action='un_rejected'`.

### Reactivate (stage = `waitlisted`)

1. Set `stage = 'scored'`, `relevance_score = 8`.
2. Overwrite submitted fields.
3. Move prep folder from `companies/_waitlisted/` back to `companies/` (update
   `prep_folder_path`).
4. Write an `audit_log` entry: `action='reactivated_from_waitlist_via_ingest'`.

### Refresh (stage = `scored` / `manual_review` / `prep_in_progress` / `materials_drafted`)

1. Overwrite submitted fields.
2. If `relevance_score < 8`, set to 8.
3. If `stage = 'manual_review'`, set `stage = 'scored'`.
4. Write an `audit_log` entry: `action='refreshed_via_ingest'`.

## UI: Result Partial (`ingest/_result.html`)

New `outcome` values beyond the existing `success` / `duplicate` / `error`:

| outcome | Color | Message | Links |
|---|---|---|---|
| `already_applied` | blue | "Already applied — see Applied board." | `/board/applied` |
| `not_selected` | gray | "You were not selected for this role. Here's where you left it:" | `/board/rejected`, materials folder (if available) |
| `resurfaced` | emerald | "Re-surfaced to Dashboard. Fields updated." (stage-specific detail) | `/board/dashboard` |

The existing `duplicate` outcome (shown when something has gone wrong / unhandled
stage) stays as a fallback.

## Data Layer

### `IngestResult` dataclass extensions

```python
@dataclass(frozen=True)
class IngestResult:
    status: Literal["ingested", "duplicate", "resurfaced", "already_applied", "not_selected"]
    job_id: str
    company: str
    title: str
    existing_match: str | None = None   # "strict" / "url" / "loose"
    existing_stage: str | None = None   # stage of the row at time of submission
    prep_folder_path: str | None = None # for not_selected materials link
    prep_launched: bool = False
```

### New `findajob.actions` helpers

`un_reject_job(conn, job_id, overwrite_fields)` — implements the un-reject sequence
above. Distinct from the waitlist reactivation path.

`refresh_active_job(conn, job_id, overwrite_fields)` — implements the refresh sequence
for already-visible stages.

Reuse existing `handle_reactivate` logic from `board_actions.py` for the waitlisted
path, or inline an equivalent into a new `reactivate_from_ingest(conn, job_id,
overwrite_fields)` helper that also handles field overwrites (the board-action version
does not accept new field data).

### Routing changes

`ingest_manual_job()` in `findajob/ingest.py` grows a post-dedup branch that calls the
appropriate action and returns the new `IngestResult` status. The route handler in
`web/routes/ingest.py` maps each status to a `_render_result()` call with the right
outcome string.

## Out of Scope

- Surfacing this smart-resurface logic in `triage.py` or `ingest_form.py` — those paths
  can't know operator intent.
- Un-rejecting from anywhere other than `/ingest/` — an explicit board UI for that is a
  separate feature.
- Moving the folder back when `prep_folder_path` is NULL (nothing to move).

## Testing

New test cases needed (in `tests/`):

- Applied/interview/offer/withdrew stages → returns `already_applied`, no DB change.
- `not_selected` stage → returns `not_selected`, `prep_folder_path` surfaced if set.
- `rejected` stage → returns `resurfaced`, stage becomes `scored`, `feedback_log` rows
  deleted, folder path updated, `audit_log` entry written.
- `waitlisted` stage → returns `resurfaced`, stage becomes `scored`, folder path updated.
- `scored` stage with low score → returns `resurfaced`, score bumped to 8.
- `manual_review` stage → returns `resurfaced`, stage → `scored`.
- Blank submitted field does NOT overwrite non-blank existing value.

## Documentation Impact

- `CLAUDE.md` § Pipeline Context Table — no change (ingest behavior not enumerated there).
- `docs/setup/configure.md` — no change (no new config).
- No new env vars, schemas, or migration-required changes.
