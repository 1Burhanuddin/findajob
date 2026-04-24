# Retire Sheet1 Writes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop writing to the `Sheet1` tab everywhere (`sync_sheet.py`, `init_sheet.py`, `setup_sheets.py`), drop the related health-check alert, and update every doc surface that still describes Sheet1 as an active archival view. `/board/archive` has fully replaced Sheet1.

**Architecture:** Surgical removal. Sheet1 is a self-contained feature slice — one sync function, one init script, one formatting block in the setup script, one health-check block, one paragraph in CLAUDE.md, and a handful of doc references. No cross-cutting refactor needed. Existing Sheet1 tabs on user spreadsheets go stale but are not deleted by the pipeline (destructive ops stay in the user's hands via the Sheets UI).

**Tech Stack:** Python 3 (scripts), pytest (tests), Markdown (docs).

---

## Pre-scan findings (grep run 2026-04-23)

### Code
| File | Sheet1 references | Action |
|---|---|---|
| `scripts/sync_sheet.py:5, 67, 209, 221–275, 610, 673, 681` | `sync_sheet1()` function, call site, summary field, header comment | Delete function + call + field; update comment |
| `scripts/notify.py:198, 310–322` | `SHEET1_ROW_WARN`, Sheet1 row-count health check | Delete constant + block |
| `scripts/init_sheet.py` (37 lines whole file) | Writes headers to `Sheet1!A1` | Delete the file |
| `scripts/setup_sheets.py:4, 7, 434, 478, 600–~670` | Formats Sheet1 layout + grey-out on rejected | Delete Sheet1 formatting + grey-out-rejected-rows |

### Tests
| File | Context | Action |
|---|---|---|
| `tests/test_sync_sheet.py:229–~330, 367–369` | `TestBuildRowSheet1` class + `_assert_full_write` Sheet1 variant | Delete Sheet1 class; keep the shared helper test with a non-Sheet1 tab |
| `tests/test_notify_dejargon.py:30` | `"Sheet1"` in `USER_FACING_JARGON` list | **Keep unchanged** — it's asserting the word never appears in user-facing strings; still true and still useful |

### Docs
| File | Lines | Action |
|---|---|---|
| `CLAUDE.md:155` | script-description tab list | Drop "Sheet1" from the list |
| `CLAUDE.md:303` | "Sheet1 is already superseded by `/board/archive`" | Rewrite past-tense + drop the paragraph about filter rules |
| `CLAUDE.md:305–333` | Full Sheet1 paragraph (filter rules + column layout) | Delete |
| `CLAUDE.md:360` | Health-check warning list mentions "Sheet1 > 1000 rows" | Drop |
| `docs/architecture.md:71, 184` | ASCII diagram + "Sheet1 — Full Archive" section | Remove from diagram; delete section |
| `docs/google-sheets.md` (whole file, 304 lines) | Top section is Sheet1; cross-refs throughout | Remove Sheet1 section; add top-of-file note that archival is now `/board/archive` |
| `docs/usage.md:164, 216` | "Archive replaces the old Sheet1"; "Sheet1 is being retired (#136)" | Update to past tense: "`/board/archive` replaced Sheet1 in #136" |
| `docs/troubleshooting.md:111, 170` | Sheet1 retirement note in sync section; alert row in health-check table | Drop alert row; update sync section wording |
| `CHANGELOG.md` | `[Unreleased]` | New entry with `migration-required` surface called out (orphaned Sheet1 tab is cosmetic, delete via Sheets UI) |

---

## File structure

### Files deleted
- `scripts/init_sheet.py` — 37-line file exists solely to write Sheet1 headers

### Files modified
- `scripts/sync_sheet.py` — remove `sync_sheet1()` + call + field
- `scripts/notify.py` — remove `SHEET1_ROW_WARN` + health-check block
- `scripts/setup_sheets.py` — remove Sheet1 formatting section
- `tests/test_sync_sheet.py` — remove `TestBuildRowSheet1` class
- `CLAUDE.md`, `docs/architecture.md`, `docs/google-sheets.md`, `docs/usage.md`, `docs/troubleshooting.md`, `CHANGELOG.md` — see table above

---

## Task 1: Verify pre-scan and establish test baseline

**Files:** (no changes — verification only)

- [ ] **Step 1: Confirm tests pass on current main**

```bash
uv run pytest tests/test_sync_sheet.py tests/test_notify_dejargon.py -v
```

Expected: all pass. Record any failures — they're pre-existing and must not be blamed on this change.

- [ ] **Step 2: Baseline the file-size / LOC to delete**

```bash
wc -l scripts/init_sheet.py scripts/sync_sheet.py scripts/notify.py scripts/setup_sheets.py
```

Record baselines — this is the "before" for the CHANGELOG.

- [ ] **Step 3: Confirm existing Sheet1 tab behavior**

```bash
ssh docker.lan 'docker compose -f /opt/stacks/findajob-<operator-stack>/compose.yaml exec -T scheduler /app/scripts/sync_sheet.py 2>&1 | tail -5'
```

Expected: prints "Sheet1: N rows synced" line. Records that Sheet1 writes are currently happening — baseline for manual post-deploy verification.

- [ ] **Step 4: No commit**

---

## Task 2: Remove `sync_sheet1()` from `sync_sheet.py`

**Files:**
- Modify: `scripts/sync_sheet.py:5` (header comment), `scripts/sync_sheet.py:67` (section header), `scripts/sync_sheet.py:209–275` (Sheet1 branch + `sync_sheet1()`), `scripts/sync_sheet.py:610` (retirement comment), `scripts/sync_sheet.py:673, 681` (call + summary field)

- [ ] **Step 1: Open `sync_sheet.py` and read the header block**

```bash
sed -n '1,70p' scripts/sync_sheet.py
```

Identify:
- Line 5: top-of-file docstring line mentioning Sheet1 — rewrite or drop that sentence
- Line 67: `# ── Sheet1: full archive ─…` section header + whatever Sheet1-specific logic is in lines 67–220

- [ ] **Step 2: Delete the Sheet1 section (lines 67–~220)**

Read the actual file to find the exact boundary — the section ends where the next non-Sheet1 function/section begins. Remove the full block including the `build_row(…, use_status=False)` Sheet1 branch if it's defined purely for Sheet1 use.

If `build_row()` is shared between Sheet1 and another tab, keep the function but remove its `use_status=False` Sheet1 callers. **Double-check before deletion:** `grep -n "use_status=False" scripts/sync_sheet.py` — if there are non-Sheet1 callers, preserve them.

- [ ] **Step 3: Delete `sync_sheet1()` function body (lines 221–275)**

Remove the entire `def sync_sheet1(svc, conn): …` block.

- [ ] **Step 4: Remove call site and summary field**

```bash
grep -n "sync_sheet1\|n_sheet1\|sheet1=" scripts/sync_sheet.py
```

Expected after step 3: one call at ~line 673, one field at ~line 681. Delete both. Also remove `n_sheet1` variable binding.

- [ ] **Step 5: Update the retirement comment at line 610**

Original reads something like "…the Sheet1-write retirement tracked in #136." Rewrite to: "Sheet1 writes were retired in #136 — the archival view is now `/board/archive`."

- [ ] **Step 6: Sanity check — no remaining Sheet1 references**

```bash
grep -nE "Sheet1|sheet1|sync_sheet1|use_status=False" scripts/sync_sheet.py
```

Expected: empty output (zero matches). If any remain, read the context and decide whether to remove or keep (e.g., a docstring comment explaining history is fine to keep; an actual Sheets API call is not).

- [ ] **Step 7: Run sync_sheet tests**

```bash
uv run pytest tests/test_sync_sheet.py -v
```

Expected: **some failures** — `TestBuildRowSheet1` references the removed path. That's fine; Task 6 cleans those up. Other tests must still pass.

- [ ] **Step 8: No commit yet** — batch with Task 3 to avoid intermediate broken state.

---

## Task 3: Remove Sheet1 health check from `notify.py`

**Files:**
- Modify: `scripts/notify.py:198` (constant), `scripts/notify.py:310–322` (health-check block)

- [ ] **Step 1: Delete `SHEET1_ROW_WARN` constant**

```bash
grep -n "SHEET1_ROW_WARN" scripts/notify.py
```

Delete the constant definition at line 198 (it will be one line like `SHEET1_ROW_WARN = 5000  # warn if Sheet1 …`).

- [ ] **Step 2: Delete the Sheet1 row-count block**

Read `scripts/notify.py` around lines 308–325:

```python
# Sheet1 row count (approximate — same filter as sync_sheet.py)
sheet1_count = conn.execute("""…""").fetchone()[0]
if sheet1_count > SHEET1_ROW_WARN:
    issues.append(f"WARN: Sheet1 has ~{sheet1_count} rows (threshold: {SHEET1_ROW_WARN})")
```

Delete the entire block including the SQL query and the comment preceding it.

- [ ] **Step 3: Sanity check**

```bash
grep -nE "Sheet1|sheet1|SHEET1" scripts/notify.py
```

Expected: zero matches.

- [ ] **Step 4: Run notify tests**

```bash
uv run pytest tests/test_notify_dejargon.py -v
```

Expected: **all pass**. The test verifies "Sheet1" doesn't appear in user-facing notification strings; removing the word from `notify.py` source is compatible with that.

- [ ] **Step 5: Commit (Tasks 2 + 3 together)**

```bash
git add scripts/sync_sheet.py scripts/notify.py
git commit -m "$(cat <<'EOF'
feat(sync): retire Sheet1 writes and health-check alert (#136)

sync_sheet1() removed; sync_sheet.py now writes only to Dashboard,
Applied, Review, Waitlist, and Rejected Applications tabs. The
notify.py health-check drops the "Sheet1 > N rows" warning since
the tab is no longer maintained.

/board/archive replaced Sheet1 in #60. Existing Sheet1 tabs on
user spreadsheets will go stale; users can delete them manually
via the Sheets UI — no programmatic deletion.
EOF
)"
```

---

## Task 4: Delete `scripts/init_sheet.py`

**Files:**
- Delete: `scripts/init_sheet.py`

- [ ] **Step 1: Confirm no callers**

```bash
grep -rn "init_sheet" --include="*.py" --include="*.yaml" --include="*.yml" --include="*.toml" --include="Dockerfile*" . | grep -v __pycache__
```

Expected: matches only inside `scripts/init_sheet.py` itself (self-references in comments) and possibly doc files. If anything in `ops/`, `Dockerfile`, or supercronic crontab references it, stop and surface that — it's a live entry point that the plan didn't account for.

- [ ] **Step 2: Delete the file**

```bash
git rm scripts/init_sheet.py
```

- [ ] **Step 3: Sanity check**

```bash
test ! -f scripts/init_sheet.py && echo "OK deleted" || echo "STILL EXISTS"
```

- [ ] **Step 4: Commit**

```bash
git commit -m "$(cat <<'EOF'
refactor(sheets): delete init_sheet.py — Sheet1 retired (#136)

This script existed solely to write column headers to Sheet1 row 1
on initial setup. Sheet1 is no longer written; the script has no
remaining purpose.
EOF
)"
```

---

## Task 5: Remove Sheet1 formatting from `setup_sheets.py`

**Files:**
- Modify: `scripts/setup_sheets.py:4, 7, 434, 478, 600–~670` (Sheet1 formatting block + grey-out-rejected)

- [ ] **Step 1: Read and map the Sheet1 sections**

```bash
grep -nE "Sheet1|sheet1_id" scripts/setup_sheets.py
```

Expected matches (from pre-scan):
- Line 4, 7: docstring
- Line 434: `grey_out_rejected_rows()` docstring referencing Sheet1
- Line 478: `sheet1_id = sheets.get("Sheet1")`
- Lines 600–~670: `# ── Sheet1 formatting ─…` block + all column-width calls with `sheet1_id`

- [ ] **Step 2: Decide whether to delete grey-out-rejected-rows entirely**

`grey_out_rejected_rows()` only targeted Sheet1 (its docstring says "Grey out entire rows on Sheet1 where stage = 'rejected'."). If there are no other callers — and the function is Sheet1-specific — delete it.

```bash
grep -n "grey_out_rejected_rows\|grey_out" scripts/setup_sheets.py
```

If one definition + one call: delete both. Otherwise: inspect and decide.

- [ ] **Step 3: Rewrite the docstring**

Change the top-of-file docstring to drop Sheet1 from the list:
```python
"""
One-time setup: formats Dashboard, Review, Waitlist, Applied, and Rejected Applications tabs.

Layouts per tab are described inline at each tab's formatting block.
"""
```

- [ ] **Step 4: Delete the `sheet1_id = sheets.get("Sheet1")` line + the entire `# ── Sheet1 formatting ─…` block**

Everything from the section comment through the last `col_width(sheet1_id, …)` call.

- [ ] **Step 5: Sanity check**

```bash
grep -nE "Sheet1|sheet1" scripts/setup_sheets.py
```

Expected: zero matches.

- [ ] **Step 6: Try running the script in dry-run / import-only mode**

```bash
uv run python -c "import scripts.setup_sheets" 2>&1 | head
```

Expected: no import error. If the file was structured so that deletion broke indentation or left an orphaned `requests.append(...)` call, the import will fail — fix inline.

- [ ] **Step 7: Commit**

```bash
git add scripts/setup_sheets.py
git commit -m "$(cat <<'EOF'
refactor(sheets): drop Sheet1 formatting from setup_sheets.py (#136)

Removes the ~70-line Sheet1 layout block and the
grey_out_rejected_rows() helper (which only targeted Sheet1).
Script now formats Dashboard, Review, Waitlist, Applied, and
Rejected Applications only.
EOF
)"
```

---

## Task 6: Remove `TestBuildRowSheet1` from `tests/test_sync_sheet.py`

**Files:**
- Modify: `tests/test_sync_sheet.py:229–~330, 367–369`

- [ ] **Step 1: Read the affected test block**

```bash
sed -n '225,340p' tests/test_sync_sheet.py
```

Expected: a class `TestBuildRowSheet1` with several methods, all exercising `build_row(…, use_status=False)`.

- [ ] **Step 2: Delete the class**

Remove the entire `class TestBuildRowSheet1: …` block. Preserve the immediately-preceding `# build_row() — Sheet1 mode (use_status=False)` banner comment only if it makes semantic sense to keep in context of what's left; otherwise delete the banner too.

- [ ] **Step 3: Handle the `_assert_full_write` Sheet1 test (lines 367–369)**

```python
result = {"updatedRows": 56, "updatedRange": "Sheet1!A1:N56"}
_assert_full_write(result, 9919, "Sheet1")
```

If this is a test for `_assert_full_write()` that uses "Sheet1" as a string label: replace "Sheet1" with an equivalent non-retired tab name (`"Dashboard"` is fine — the helper is tab-agnostic, so the test keeps its coverage).

If the test is specifically asserting Sheet1 behavior: delete.

- [ ] **Step 4: Run the test file**

```bash
uv run pytest tests/test_sync_sheet.py -v
```

Expected: all pass.

- [ ] **Step 5: Run the whole suite**

```bash
uv run pytest -v 2>&1 | tail -20
```

Expected: same pass count as pre-change (minus the removed tests). No new failures.

- [ ] **Step 6: Run ruff and mypy**

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy scripts src 2>&1 | tail -5
```

Expected: clean (or same pre-existing issues as baseline, nothing new).

- [ ] **Step 7: Commit**

```bash
git add tests/test_sync_sheet.py
git commit -m "$(cat <<'EOF'
test(sync_sheet): remove TestBuildRowSheet1 after #136 retirement

The build_row() Sheet1 branch was removed; its tests are gone
with it. _assert_full_write() retains a shared test using
Dashboard as the tab-name fixture.
EOF
)"
```

---

## Task 7: Update `CLAUDE.md`

**Files:**
- Modify: `CLAUDE.md:155, 303–333, 360`

- [ ] **Step 1: Drop Sheet1 from the script-description line**

Line 155 currently reads approximately:
```
<repo>/scripts/sync_sheet.py                # SQLite → Sheet1 + Dashboard + Applied + Review + Waitlist + Rejected Applications tabs
```

Rewrite:
```
<repo>/scripts/sync_sheet.py                # SQLite → Dashboard + Applied + Review + Waitlist + Rejected Applications tabs (one-way, no Sheet reads)
```

- [ ] **Step 2: Rewrite the §"Google Sheet Architecture" intro**

Around line 303, there's a callout:
```
> ... Sheet1 is already superseded by `/board/archive` (#60).
```

Rewrite to remove the Sheet1 line entirely; if the callout loses its point, reshape the whole block to say "The Sheet is a read-only synced mirror of the DB for mobile/glance; active tabs are Dashboard, Applied, Review, Waitlist, and Rejected Applications until #14 ships."

- [ ] **Step 3: Delete the full `**Sheet1** — filtered archive (A–N) …` paragraph**

Lines ~305–~333: the paragraph describing the Sheet1 archival filter, the column layout (`fingerprint(hidden) | APPLY_FLAG(checkbox) | score | …`). Delete the entire block including the leading `**Sheet1**` header through the end of the column-layout line.

- [ ] **Step 4: Update the health-check warning list**

Line 360 currently:
```
**Health checks** (`notify.py health-check`): warns if Sheet1 > 1000 rows, manual_review backlog > 100, or any target-company job scored 3–6 in last 7 days (potential mis-scores).
```

Rewrite (drop the Sheet1 clause):
```
**Health checks** (`notify.py health-check`): warns if manual_review backlog > 100, a source silently stopped producing jobs, or any target-company job scored 3–6 in last 7 days (potential mis-scores).
```

- [ ] **Step 5: Sanity check**

```bash
grep -nE "Sheet1|sheet1" CLAUDE.md
```

Expected: zero matches.

- [ ] **Step 6: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(claude-md): drop Sheet1 architecture section (#136)"
```

---

## Task 8: Update `docs/architecture.md` and `docs/google-sheets.md`

**Files:**
- Modify: `docs/architecture.md:71, 184`
- Modify: `docs/google-sheets.md` (whole file)

- [ ] **Step 1: Update `architecture.md` diagram and section**

Line 71 has an ASCII diagram with `│  Sheet1 (archive)           │`. Replace that line with the `/board/archive` equivalent:
```
│  /board/archive (web)       │
```

Line 184 starts `### Sheet1 — Full Archive (A–N)`. Delete that entire section up to the next `###`.

- [ ] **Step 2: Sanity check architecture.md**

```bash
grep -nE "Sheet1|sheet1" docs/architecture.md
```

Expected: zero matches.

- [ ] **Step 3: Delete the Sheet1 section from `docs/google-sheets.md`**

Per the lean-docs principle: delete outright, not preserve in `<details>`. Two users exist (operator + Alice); no external audience for historical breadcrumbs.

Remove:
- The `### Sheet1 — Full Archive` section (line 16 onward until the next `###`)
- The `**Sheet1:**` block around line 268
- Line 63 column-mapping entry: simplify "plain text on Sheet1; hyperlinks on Dashboard/Applied/…" to just "hyperlinks into the materials viewer on Dashboard/Applied/Waitlist/Rejected Applications when `FINDAJOB_MATERIALS_BASE_URL` is set" (drop the Sheet1 clause)

Do **not** add a migration note at the top of the file — the CHANGELOG entry is the single migration surface.

- [ ] **Step 5: Sanity check**

```bash
grep -cE "Sheet1" docs/google-sheets.md
```

Expected: matches only inside the `<details>` block and the top-of-file migration note; all outside-details mentions removed.

- [ ] **Step 6: Commit**

```bash
git add docs/architecture.md docs/google-sheets.md
git commit -m "docs: move Sheet1 references to historical blocks (#136)"
```

---

## Task 9: Update the fresh user-facing docs

**Files:**
- Modify: `docs/usage.md:164, 216`
- Modify: `docs/troubleshooting.md:111, 170`

- [ ] **Step 1: Update `docs/usage.md` — delete Sheet1 mentions**

Line 164: `Archive replaces the old Sheet1 archive view.` → **delete this line entirely**. The Archive tab stands on its own; no need to name the thing it replaced.

Line 216 (inside `<details>` advanced block): the sentence "Sheet1 is being retired (#136); the web Archive tab replaces it." → **delete this sentence**. The remaining sentence about the other Sheet tabs continuing until #14 stays.

- [ ] **Step 2: Update `docs/troubleshooting.md` — delete Sheet1 mentions**

Line 111 (inside "Google Sheet isn't updating"): the "Note: Sheet1 (the full archive tab) is being retired..." paragraph → **delete the entire note paragraph**. The preceding sync_sheet troubleshooting content stays.

Line 170 — the Sheet1 alert row in the health-check table → **delete the entire row**.

- [ ] **Step 3: Verify no surviving Sheet1 references in user docs**

```bash
grep -nE "Sheet1|sheet1" docs/usage.md docs/troubleshooting.md docs/setup/README.md
```

Expected: zero matches.

- [ ] **Step 4: Commit**

```bash
git add docs/usage.md docs/troubleshooting.md
git commit -m "docs: update Sheet1 references in usage.md + troubleshooting.md to past tense (#136)"
```

---

## Task 10: Add CHANGELOG entry

**Files:**
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Read current `[Unreleased]` section**

```bash
grep -n "Unreleased\|## \[" CHANGELOG.md | head -10
```

- [ ] **Step 2: Add an entry under `[Unreleased]`**

```markdown
### Removed
- **Sheet1 writes (#136).** `sync_sheet.py` no longer writes to the `Sheet1` tab; the `notify.py` health-check drops the "Sheet1 > N rows" warning; `scripts/init_sheet.py` deleted; Sheet1 formatting removed from `setup_sheets.py`. `/board/archive` is the archival view going forward.

**Migration note:** Existing installs will have a stale `Sheet1` tab on their Google Sheet — no rows get written to it any more, but the tab itself is not programmatically deleted. Safe to delete manually via the Sheets UI: right-click the `Sheet1` tab → Delete. The pipeline does not read from it.
```

- [ ] **Step 3: Verify Markdown structure**

```bash
head -40 CHANGELOG.md
```

Expected: section renders cleanly under `## [Unreleased]`.

- [ ] **Step 4: Commit**

```bash
git add CHANGELOG.md
git commit -m "chore(changelog): note Sheet1 retirement (#136)"
```

---

## Task 11: Whole-feature verification gate

**Files:** (no changes — verification only)

- [ ] **Step 1: Repo-wide Sheet1 grep**

```bash
grep -rnE "Sheet1|sheet1|sync_sheet1|SHEET1_ROW_WARN" --include="*.py" --include="*.md" --include="*.yaml" --include="*.yml" --include="*.toml" . | grep -v __pycache__ | grep -v "docs/superpowers/plans/archived" | grep -v "docs/superpowers/specs/archived"
```

Expected survivors:
- `tests/test_notify_dejargon.py:30` — `"Sheet1"` in `USER_FACING_JARGON` (correct — still tests that this internal term stays out of user-facing strings)
- `docs/superpowers/plans/2026-04-23-retire-sheet1.md` — this file
- `CHANGELOG.md` — the entry just added

Any other survivor = a reference the plan missed. Stop and fix it before proceeding.

- [ ] **Step 2: Full test suite**

```bash
uv run pytest -v 2>&1 | tail -10
```

Expected: no new failures compared to Task 1 Step 1 baseline.

- [ ] **Step 3: ruff + mypy**

```bash
uv run ruff check . && uv run ruff format --check .
uv run mypy scripts src 2>&1 | tail -5
```

Expected: clean.

- [ ] **Step 4: Live sync_sheet.py dry run on docker.lan**

Before merging, run `sync_sheet.py` on the dogfood host and verify output no longer has a `Sheet1: N rows synced` line and no `Sheet1!A*` range calls.

```bash
ssh docker.lan 'docker compose -f /opt/stacks/findajob-<operator-stack>/compose.yaml exec -T scheduler /app/scripts/sync_sheet.py 2>&1'
```

Expected output lines name only: Dashboard, Applied, Review, Waitlist, Rejected Applications. No Sheet1.

- [ ] **Step 5: Live notify.py health-check dry run on docker.lan**

```bash
ssh docker.lan 'docker compose -f /opt/stacks/findajob-<operator-stack>/compose.yaml exec -T scheduler /app/scripts/notify.py health-check 2>&1'
```

Expected: no `Sheet1` mentions in output, regardless of current sheet1_count.

- [ ] **Step 6: Verify the Sheet1 tab on the live sheet is not being written**

Open the operator's Google Sheet, refresh, watch the "Last edit" timestamp on the Sheet1 tab. It should not update after the first sync cycle post-merge.

(This is a post-merge check — add a note to the PR description asking the operator to verify after deploy.)

---

## Task 12: PR + integration

**Files:** PR creation — no local files.

- [ ] **Step 1: Confirm branch state**

```bash
git log --oneline origin/main..HEAD
```

Expected: ~7 commits from Tasks 2–10.

Note: per project convention, this change goes via PR (pipeline code + `migration-required` triggers release notes). Branch name: `feat/136-retire-sheet1-writes`.

If work was done directly on `main` by habit: create a branch retroactively with `git checkout -b feat/136-retire-sheet1-writes` before pushing. Do NOT force-push to `main`.

- [ ] **Step 2: Push and open PR**

```bash
git push -u origin feat/136-retire-sheet1-writes
gh pr create \
  --title "feat(sync): retire Sheet1 writes (#136)" \
  --body "$(cat <<'EOF'
## Summary
- `sync_sheet.py` no longer writes to Sheet1
- `notify.py health-check` drops the "Sheet1 > N rows" alert
- `scripts/init_sheet.py` deleted (existed only to write Sheet1 headers)
- `scripts/setup_sheets.py` no longer formats Sheet1
- CLAUDE.md, docs/architecture.md, docs/google-sheets.md updated
- docs/usage.md + docs/troubleshooting.md updated to past tense

## Migration
Existing installs will have a stale `Sheet1` tab that no longer updates. Safe to delete manually via the Sheets UI. The pipeline does not read from it.

## Test plan
- [ ] `uv run pytest` passes
- [ ] `uv run ruff check . && uv run ruff format --check .` clean
- [ ] `uv run mypy scripts src` clean
- [ ] On docker.lan: run `sync_sheet.py` — output mentions no Sheet1
- [ ] On docker.lan: run `notify.py health-check` — output mentions no Sheet1
- [ ] On docker.lan: Google Sheet Sheet1 tab's "Last edit" timestamp does not advance after the next sync cycle

Closes #136.
EOF
)" \
  --label migration-required
```

- [ ] **Step 3: After CI green, merge**

```bash
gh pr merge --squash --delete-branch
```

- [ ] **Step 4: Post-merge**

Add a Session note + close #136 via jared:

```bash
gh issue comment 136 --body "<session note>"
jared close 136
```

---

## Documentation Impact

| Doc surface | Change |
|---|---|
| `CLAUDE.md` | §"Google Sheet Architecture" — drop Sheet1 paragraph; update health-check list; §"Key File Locations" — update sync_sheet.py description — Task 7 |
| `docs/architecture.md` | Diagram + "Sheet1 — Full Archive" section — Task 8 |
| `docs/google-sheets.md` | Move Sheet1 section into `<details>` historical block; update column-mapping table — Task 8 |
| `docs/usage.md` | Lines 164, 216 — past-tense wording — Task 9 |
| `docs/troubleshooting.md` | Line 111 wording + drop line 170 alert row — Task 9 |
| `CHANGELOG.md` | `[Unreleased]` — Task 10 |
| PR description | Migration note + test plan — Task 12 |
| GitHub issue #136 | Session note + close — post-merge |

---

## Self-Review Checklist

Map every AC from #136 to its implementing task:

| AC (from #136) | Implemented by |
|---|---|
| `sync_sheet.py` no longer writes to Sheet1 | Task 2 |
| `notify.py health-check` drops the Sheet1 > 1000 rows warning | Task 3 |
| CLAUDE.md §"Google Sheet Architecture" updates/removes Sheet1 | Task 7 |
| CHANGELOG `[Unreleased]` entry | Task 10 |

Plus adjacent work not called out in AC but required for consistency:
- Related scripts (`init_sheet.py`, `setup_sheets.py`) — Tasks 4, 5
- Tests (`test_sync_sheet.py`) — Task 6
- Other docs (architecture, google-sheets, usage, troubleshooting) — Tasks 8, 9

**Placeholder scan:** No "TBD", no "add appropriate X", no "similar to Task N". Every edit names line numbers or sections; every deletion has a grep-verifiable completion check.

**Type consistency:** No new types or signatures introduced. Existing `build_row()`, `sync_dashboard()`, etc. are preserved; only Sheet1-specific call sites are removed.

**Spec coverage:** #136 is a targeted retirement, not a spec-backed feature. All four AC items are covered. Adjacent cleanups (tests, related scripts, docs) are listed above.

**Destructive-op audit:** The only "delete" operations are `git rm scripts/init_sheet.py` and deletion of code blocks within other files. No destructive ops against the user's Google Sheet — the orphaned Sheet1 tab is left in place, and the migration note documents that the user can delete it manually.
