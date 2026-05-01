# Project Board — How It Works

<!-- Machine-readable metadata — jared scripts parse this. Do not reorder or
     rename the fields below. Narrative prose after the end marker is for
     humans. Re-run `scripts/bootstrap-project.py` (from the jared plugin)
     after any schema change to keep this block in sync with the board. -->

- Project URL: https://github.com/users/brockamer/projects/1
- Project number: 1
- Project ID: PVT_kwHOAgGulc4BUtxZ
- Owner: brockamer
- Repo: brockamer/findajob

### Status
- Field ID: PVTSSF_lAHOAgGulc4BUtxZzhCOoMM
- Backlog: 59bd4809
- Up Next: f94b6c8d
- In Progress: 87411b49
- Blocked: e0fccf99
- Done: 1b523c26

### Priority
- Field ID: PVTSSF_lAHOAgGulc4BUtxZzhCWZ08
- High: f0a4404c
- Medium: 4e8ef0ac
- Low: 79925e2f

<!-- End machine-readable block — narrative docs follow. -->

The GitHub Projects v2 board at [findajob Pipeline](https://github.com/users/brockamer/projects/1) is the **single source of truth for execution state** — what is being worked on, by whom, what state. Phase-level narrative and cross-issue decisions live in [`roadmap.md`](roadmap.md). If it isn't on the board or in the roadmap, it isn't on the plan.

This document describes the conventions so anyone (human or Claude session) can triage, prioritize, and move work consistently.

## Division of labor — board vs. roadmap vs. canonical docs

Drift is the main failure mode. Every fact has exactly one home. On conflict, the canonical home wins.

| Fact type | Lives in | Wins on conflict |
|---|---|---|
| Phase arc + phase ordering rationale | [`roadmap.md`](roadmap.md) | roadmap |
| Cross-issue decisions (numbered, append-only) | [`roadmap.md`](roadmap.md) | roadmap |
| Milestone-level acceptance criteria | [`roadmap.md`](roadmap.md) | roadmap |
| Issue Status, Priority, Milestone, labels | board | board |
| Issue body (summary, per-issue acceptance, prose depends-on) | issue | issue |
| Issue dependencies (`blockedBy` edges) | native GitHub dependency API | native edges |
| Deployment / architecture facts | [`deployment-model.md`](deployment-model.md) | canonical doc |
| Release process | [`release-process.md`](release-process.md) | canonical doc |

Issue bodies may *reference* the roadmap ("see Phase 4 in roadmap.md") but should not restate phase ordering or decisions. That's how drift starts. The jared sweep includes a drift-scan check for this (see `jared/references/board-sweep.md`).

## Columns (Status field)

Three columns in active use, left to right. An issue moves rightward as it progresses.

| Column | Meaning | Expected count |
|---|---|---|
| **Backlog** | All open work. Triaged (has Priority + usually Milestone) and prioritized via the Priority field, not by column position. | Unbounded |
| **Blocked** | Pulled out of Backlog only when an issue hits an unanticipated stoppage. Has a `## Blocked by` body section naming the unblock owner and the specific event being waited on. Returns to Backlog when unblocked. | 0–2 items |
| **Done** | Closed issues. Auto-populated when an issue closes. | Growing |

The `Up Next` and `In Progress` columns are retired (2026-05-01 structural review). They existed to model WIP-limited kanban for a multi-person team; in a solo-operator + AI-loop context shipping at a 5-patches-per-day cadence, the queue lived in conversation, not on the board, and the columns stayed empty. The board's job here is **prioritization** (Priority field) and **release grouping** (Milestone), not **flow control**. Issues now go straight from Backlog to Done.

**Rules:**
- Every open issue must have a Priority — Priority drives ordering, not column position.
- When an issue closes, it moves to Done automatically.
- An issue with unmet `blockedBy` dependencies is **not** "Blocked" — it's just queued. Items move to Blocked only after work has actively started and hit a stoppage.
- A `Backlog` item that's actively being worked on right now is still in `Backlog` — the conversation/PR is the source of truth for "what's in flight," not the column.

## Body sections — three independent dimensions

A given issue answers three independent questions, each with its own home:

| Question | Where it lives |
|---|---|
| Where is this work in the flow? | **Status column** (Backlog / Blocked / Done) |
| What does this issue depend on? | **Native `blockedBy`** — set via the GitHub dependencies API, visible in the "Linked issues" panel and Projects v2 dependency views |
| Who owns getting an actively-stuck item moving? | **`## Blocked by` body section** — present **only** on items currently in the Blocked Status column. Names the person, the specific event, and the expected-by date. |

The `## Depends on` body section, if present, is **prose context only**. The relationship data lives in native `blockedBy`. Don't parse `- #N` bullets out of body text — query `Issue.blockedBy` instead.

The `## Blocks` body section is retired. Express the inverse direction by adding a `blockedBy` edge on the dependent.

## Priority field

Three values. This is the canonical priority signal — **not** the legacy `priority: high / med / low` labels.

| Value | Meaning |
|---|---|
| **High** | Directly advances the current strategic goal (getting a job). Should be addressed before Medium work. Stakes are high, timeline is now. |
| **Medium** | Quality, efficiency, or reliability improvement. Important but not blocking the strategic goal. |
| **Low** | Nice-to-have, future-facing, or optional. Safe to defer indefinitely. |

**Rules:**
- Every open issue on the board must have a Priority set.
- High priority is scarce by design — if everything is High, nothing is.
- Two simultaneous High items in flight should be rare and deliberate (e.g., one blocking work and one small bug fix alongside it).
- If the user says "prioritize X," the intent is *X is the top of the queue*, not *X is another High item among many*.

## Labels

Labels describe **what kind of issue it is**, not where it lives on the board. Status and priority come from board fields, not labels.

Active labels:

| Label | Meaning |
|---|---|
| `bug` | Something isn't working |
| `enhancement` | New capability |
| `job-search` | Directly impacts job search results |
| `pipeline-quality` | Reliability, testing, ops |
| `data-hygiene` | Cleanup of stale or inconsistent data |
| `open-source` | Generalization and adoption |
| `documentation` | Docs-only change |
| `big-idea` | Speculative far-horizon concept; not on the active roadmap. Always pair with Priority: Low. |
| `personal` | User-specific content — not generalizable pipeline work (e.g. personal resume edits). Not part of the shared roadmap; tracked here for convenience only. |

Legacy labels (being phased out — Priority field is canonical):
- `priority: high`, `priority: med`, `priority: low`

If you see an issue with a `priority:` label but no Priority field value, reconcile by setting the field to match the label and either removing the label or leaving it for later cleanup.

## Dependency relationships

Native GitHub `blockedBy` is the canonical store for "issue X depends on issue Y."

**Add an edge:**
```bash
ID_DEPENDENT=$(gh issue view <X> --repo brockamer/findajob --json id --jq '.id')
ID_BLOCKER=$(gh issue view <Y> --repo brockamer/findajob --json id --jq '.id')
gh api graphql -f query='
  mutation($i: ID!, $b: ID!) {
    addBlockedBy(input: {issueId: $i, blockingIssueId: $b}) {
      issue { number }
    }
  }' -F i="$ID_DEPENDENT" -F b="$ID_BLOCKER"
```

**Read edges:**
```bash
gh api graphql -f query='
  query($o: String!, $r: String!, $n: Int!) {
    repository(owner: $o, name: $r) {
      issue(number: $n) { blockedBy(first: 20) { nodes { number title state } } }
    }
  }' -F o=brockamer -F r=findajob -F n=<X>
```

A `## Depends on` body section, when present, is **human prose** explaining *why* the dependency matters. It does not need to be parseable. The authoritative edge is `blockedBy`.

A `blockedBy` edge does **not** automatically move an issue to the Blocked column. Items move to Blocked only when actively-worked work has hit a stoppage.

## Epics (umbrella issues)

For thematic groupings spanning multiple issues, use **native GitHub sub-issue relationships**, not labels or milestones. The `Parent issue` / `Sub-issues progress` fields on the Projects board surface the hierarchy automatically.

Convention:

- Epic title prefix: `[Epic] <short theme>` — e.g. `[Epic] Cost observability: per-job tracking, dashboards, operator alerts`.
- Epic body has a **one-sentence deliverable** — the same discipline as a milestone. If you can't write it, the epic doesn't exist yet.
- Epic is `enhancement`-labeled, Medium priority by default. Children carry their own priorities.
- Wire parent-child via `addSubIssue` mutation:
  ```bash
  PARENT=$(gh issue view <parent#> --repo brockamer/findajob --json id --jq '.id')
  CHILD=$(gh issue view <child#> --repo brockamer/findajob --json id --jq '.id')
  gh api graphql -f query='mutation($p: ID!, $c: ID!) { addSubIssue(input:{issueId:$p, subIssueId:$c}) { issue { number } } }' -F p="$PARENT" -F c="$CHILD"
  ```
- An epic may span milestones. A child may be in a different milestone than its epic parent (not recommended, but allowed — the epic is thematic, the milestone is temporal).
- Epics can themselves close. Close when every child is closed and the deliverable sentence is true.

Epics are *not* a replacement for milestones. Milestones are release boundaries ("what ships together by date X"); epics are thematic ("all the work related to Y, whenever it ships").

## Triage checklist — new issue

When a new issue is filed (by the user, by Claude, or by auto-add):

1. **Auto-add to board.** `gh issue create` does not auto-add; use `gh project item-add 1 --owner brockamer --url <issue_url>`. Verify after — occasional race conditions require a retry.
2. **Set Priority** — High / Medium / Low per the definitions above.
3. **Leave Status as Backlog** unless explicitly scheduling.
4. **Apply labels** for issue type (`bug`, `enhancement`, etc.), scope (`job-search`, `pipeline-quality`, etc.), and `big-idea` if it's a speculative parking-lot item.

An issue without Priority will sort into the "no-field" bucket at the bottom of the board — effectively invisible.

## Moving work — status transitions

- **Backlog → Done** — happens automatically when the issue closes (via `gh issue close` or PR merge referencing the issue).
- **Backlog → Blocked** — only when an actively-worked item hits a stoppage. Add the `## Blocked by` body section naming the unblock owner and event.
- **Blocked → Backlog** — when the stoppage clears. Drop the `## Blocked by` section.
- **Any column → Done without closing** — avoid. If the work is done, close the issue; if it's obsolete, close with a comment explaining why.

## Apply gate

**No new features or elective improvements until the user applies to at least three jobs on the current calendar day (Pacific time).** Bug fixes are exempt. Threshold raised from 1 → 3 on 2026-04-23. This means:

- Before starting any new Medium/Low work, check the gate. If it hasn't cleared, clear the gate first.
- High-priority bug fixes and blockers to applying (e.g., damaged prep materials) are always fair game.
- Claude checks the gate by querying `audit_log` on docker.lan for today's `stage→applied` transitions; do not ask the user whether they've applied.

## Common inconsistencies to watch for

1. **Label says `priority: high` but Priority field is empty** — reconcile by setting the field.
2. **Open issue with no Priority** — every open issue must be triaged.
3. **Issue on board but closed** — should auto-move to Done; if not, set status manually.
4. **High-priority backlog items older than two weeks with no movement** — either downgrade to Medium, or close if no longer relevant.
5. **Open issue with no Milestone (and not labeled `big-idea` / `personal`)** — every working issue should be tied to a release-grouping milestone.

## Fields quick reference (for gh project CLI)

```
Project ID:          PVT_kwHOAgGulc4BUtxZ
Status field ID:     PVTSSF_lAHOAgGulc4BUtxZzhCOoMM
  Backlog:           59bd4809
  Up Next:           f94b6c8d
  In Progress:       87411b49
  Blocked:           e0fccf99
  Done:              1b523c26
Priority field ID:   PVTSSF_lAHOAgGulc4BUtxZzhCWZ08
  High:              f0a4404c
  Medium:            4e8ef0ac
  Low:               79925e2f
```

Example: move an item to Blocked (the only manual Status transition under current conventions):
```bash
gh project item-edit \
  --project-id PVT_kwHOAgGulc4BUtxZ \
  --id <ITEM_ID> \
  --field-id PVTSSF_lAHOAgGulc4BUtxZzhCOoMM \
  --single-select-option-id e0fccf99
```

The `Up Next` (`f94b6c8d`) and `In Progress` (`87411b49`) option IDs are retained in the GitHub Projects schema for historical items but are no longer used by convention — see "Columns" above.
