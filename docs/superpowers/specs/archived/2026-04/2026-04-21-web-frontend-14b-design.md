> **ARCHIVED** — Issue #60 shipped 2026-04-21. See the [closed issue](https://github.com/brockamer/findajob/issues/60) and its merged PRs (#134, #135) for the canonical record.

# Web Frontend Phase 14b — Read-Only Pipeline UI

**Issue:** [#60](https://github.com/brockamer/findajob/issues/60)
**Parent:** #14 (web frontend arc)
**Spec date:** 2026-04-21
**Status:** ARCHIVED — shipped.

---

## Overview

Ship a read-only web surface that lets the operator (and external testers) view all pipeline state in the browser without opening the Google Sheet. Foundation layer (shell, nav, styling, URL structure) lands first; five board pages (Dashboard, Applied, Review, Waitlist, Archive) wire in next.

The goal is a "credible Sheet replacement" for all read workflows. Write actions (STATUS dropdowns, Flag-for-Prep buttons, reject reasons) stay on the Sheet in 14b and migrate to the web UI in 14c (#61).

Every design decision here is made with the broader front-end roadmap in mind: manual job ingest (#79), synthetic JD submission (#131), config surfaces, feedback tuning, onboarding interview UI, doctor, stats/scoreboard, notifications, docs. The foundation this spec ships is the foundation every later feature builds on.

---

## Scope decisions (foundational — apply to all current and future front-end features)

These five decisions are hard to reverse once the foundation lands. Approved by the operator.

1. **Server-rendered HTML with HTMX. Not a SPA.** FastAPI + Jinja templates + HTMX for interactivity. Zero build step, every route testable with `TestClient`, consistent with the rest of the stack (Python, containerized). Alpine.js is added only when we need ephemeral client-side state (dropdowns, modals). Revisit only if a feature genuinely requires SPA-style state management (unlikely for internal tools).

2. **Grouped URL information architecture.** Top-level nav items map to feature groups, not individual pages.
   ```
   /              — landing / pipeline-at-a-glance
   /board/*       — 4 Sheet tabs + archive (this spec)
   /materials/*   — prep folder viewer (already shipped in #59)
   /ingest/*      — manual job form (#79), synthetic JD (#131)
   /tools/*       — doctor, stats, scoreboard (future)
   /config/*      — roles, prefilter, feedback tuning (future)
   /docs/*        — user-facing documentation (future)
   ```
   Top-nav stays at 7 links as we grow.

3. **Tailwind CSS via CDN.** One `<link>` tag, zero build. A small custom `app.css` file holds design tokens (CSS variables for brand colors matching Sheet conditional formatting). Migrate to a build step only if the CDN proves painful.

4. **Interactivity: HTMX for server-driven, Alpine.js when needed.** HTMX handles partial swaps (filter, sort, pagination, form POST) over plain HTTP. Alpine.js gets pulled in the first time we need client-only state and not before. Vanilla JS is not a default — it doesn't compose.

5. **UI state lives in URL query parameters.** `?sort=score&filter=meta` is shareable, bookmarkable, and matches server-rendered semantics. Cookies and localStorage are out of scope for 14b; adopt them only when auth or per-user preferences arrive.

---

## Deferred (out of scope for 14b)

- **Authentication / multi-user.** Single-operator-per-stack today. Document "don't expose to public internet" assumption. Bolt on FastAPI middleware if multi-user need ever materializes.
- **Mobile-first responsive design.** Tailwind gives us responsive for free; we don't design mobile-first.
- **Theming / branding polish.** Ship minimal; iterate when a tester says something concrete.
- **Playwright / browser E2E tests.** FastAPI `TestClient` is sufficient for read-only routes. Adopt Playwright in 14c when write workflows need click-through testing.
- **Component library.** Build up Jinja macros (`_job_row.html`, `_nav.html`) organically. Don't adopt a framework component system.
- **Write workflows.** No POST handlers, no buttons, no dropdowns that mutate state. Those are 14c / #61.

---

## PR boundary

Two PRs under #60.

### PR 1 — Foundation

Ship the shell and URL-IA restructure. Zero user-visible features beyond the new nav. Existing `/materials` functionality preserved at its new path.

### PR 2 — Board pages

Five pages under `/board/` (Dashboard, Applied, Review, Waitlist, Archive) with column sets matching the Sheet, sort via URL params, filter via HTMX, row-age + status coloring matching Sheet conditional formatting, and company-cell hyperlinks into the materials viewer.

Both PRs carry the `enhancement` label. Neither is `migration-required` — operators pull `:latest` and the new UI appears with no manual steps.

---

## File structure (after both PRs)

```
src/findajob/web/
  __init__.py
  app.py                   — create_app(); mounts routers + static
  folder_resolver.py       — unchanged from #59
  static/
    app.css                — design tokens (CSS variables), custom components
  templates/
    base.html              — shell: head, top-nav, main content block
    _nav.html              — top-nav macro (included in base)
    _job_row.html          — shared row partial for board tables
    landing.html           — new /
    materials/
      index.html           — moved from templates/index.html
      folder.html          — unchanged from #59
    board/
      dashboard.html
      applied.html
      review.html
      waitlist.html
      archive.html
      _filters.html        — filter form partial (HTMX target)
    placeholders/
      coming_soon.html     — shared stub for /ingest, /tools, /config, /docs
  routes/
    __init__.py            — aggregates routers
    landing.py             — / + placeholder groups
    materials.py           — /materials/* (extracted from current routes.py)
    board.py               — /board/*
    healthz.py             — /healthz (extracted)
```

The current monolithic `src/findajob/web/routes.py` (153 lines) is split into a `routes/` package. Each file owns one URL group. Future features (manual ingest, doctor, etc.) add new files without touching existing ones.

---

## PR 1 — Foundation

### Components

1. **`base.html` shell.** All pages extend it. Blocks: `title`, `nav` (defaults to `_nav.html` include), `content`. Head loads Tailwind CDN (`https://cdn.tailwindcss.com`), HTMX CDN (`https://unpkg.com/htmx.org@2`), and `/static/app.css`. Body = top-nav + main container.

2. **`_nav.html`.** Horizontal nav with seven links: Home (`/`), Board (`/board/dashboard`), Materials (`/materials/`), Ingest (`/ingest/`), Tools (`/tools/`), Config (`/config/`), Docs (`/docs/`). The link for the current page gets `aria-current="page"` and a Tailwind active style (bottom border or background).

3. **Landing page (`/`).** Queries `jobs` with `GROUP BY stage` once, renders a card grid showing row counts per stage. Card for each of: scored, materials_drafted, applied, waitlisted, rejected, not_selected. Over time this grows into a real dashboard; for PR 1 it's just row counts.

4. **URL IA migration.**
   - Existing `routes.py::index` handler → renamed `materials_index`, moved to `/materials/` in `routes/materials.py`.
   - New `landing` handler at `/` in `routes/landing.py`.
   - Deep link `/materials/{fingerprint}` and `/materials/{fingerprint}/{filename}` unchanged. sync_sheet.py hyperlinks from #130 keep working.
   - No redirect from old `/` to new `/`: the only consumer of the old `/` is the browser bar and the nav in docs; no Sheet/email links to preserve.

5. **Placeholder pages.** `/board/`, `/ingest/`, `/tools/`, `/config/`, `/docs/` each render `placeholders/coming_soon.html` with the group name and a one-liner describing what's planned + the tracking issue.

6. **Static assets.** New `src/findajob/web/static/app.css`. Initially holds CSS variables for the Sheet color palette:
   ```css
   :root {
     --color-applied-fresh: #c6e6b9;     /* 0–6 days, green */
     --color-applied-week:  #fff3b0;     /* 7–13 days, yellow */
     --color-applied-stale: #f4b7b0;     /* 14–20 days, red */
     --color-applied-cold:  #d6d6d6;     /* 21+ days, gray */
     --color-offer:         #ffd700;     /* gold */
     --color-interviewing:  #c8a2d8;     /* purple */
     --color-ghosted:       #d6d6d6;     /* gray */
     --color-contact-amber: #ffbf00;
   }
   ```
   Mounted via `app.mount("/static", StaticFiles(directory=...))` in `app.py`.

7. **HTMX bootstrapping.** CDN load in `base.html` head. Nav links get `hx-boost="true"` for smooth swaps; plain links still work if JS is off. No custom HTMX endpoints in PR 1.

8. **Route-module split.** Convert `src/findajob/web/routes.py` (153-line monolith) into a `routes/` package:
   - `routes/__init__.py` — aggregates all sub-routers into one `router` the app includes.
   - `routes/landing.py` — new `/` handler + placeholder-group handlers (`/board/`, `/ingest/`, `/tools/`, `/config/`, `/docs/`).
   - `routes/materials.py` — extracts the existing `index`, `folder_view`, and `file_serve` handlers from the current `routes.py`. The `index` handler is renamed to `materials_index` and moved to `/materials/`.
   - `routes/healthz.py` — extracts the existing `/healthz` handler.
   - `routes/board.py` — stub in PR 1 (placeholder handlers live in `landing.py`); filled with real tab routes in PR 2.

   `app.py::create_app` imports from `findajob.web.routes` and includes the aggregated router unchanged from the app's perspective.

### Tests (PR 1)

- Route handler tests via FastAPI `TestClient` for every URL: `/`, `/materials/`, `/materials/{fp}`, `/materials/{fp}/{file}`, `/healthz`, each `/board/`, `/ingest/`, `/tools/`, `/config/`, `/docs/` placeholder. Assert status 200 + nav is present in response body.
- `base.html` renders without error against an empty context.
- `_nav.html` highlights the current page (assert `aria-current="page"` on the expected link for each route).

### Documentation Impact (PR 1)

- `CHANGELOG.md` — [Unreleased] entry: "Web viewer adds a landing page and top nav. Materials folder index moves from `/` to `/materials/`; deep links `/materials/{fingerprint}` unchanged. Placeholder pages for board, ingest, tools, config, docs will fill in as features land."
- `docs/setup/install-docker.md` — update "Materials viewer port" section noting the UI now has a top nav; the smoke test URL is still `http://docker.lan:<port>/`.
- `CLAUDE.md` — add a "Web Frontend Architecture" subsection under "Key File Locations" pointing at `src/findajob/web/` with the route-group convention (one file per URL group, macros for shared partials) and the 5 foundational scope decisions above.
- `docs/roadmap.md` — if the 14 arc is tracked there, add a note that 14b foundation landed.

---

## PR 2 — Board pages

### Components

1. **Five routes under `/board/`.** Each reads `jobs` directly with the filter from CLAUDE.md's Sheet Architecture section. Columns below are the read-only subset — the Sheet's `STATUS` and `REJECT_REASON` columns are **omitted** in 14b because they are write-only signal cells (user sets them, `poll_flags.py` consumes and clears them) with no meaningful DB-persisted value to render. They reappear as interactive controls in 14c (#61).

   | Route | Filter | Column set (read-only columns only) |
   |---|---|---|
   | `/board/dashboard` | `(fit_score>=7 AND stage IN ('scored','manual_review')) OR stage IN ('prep_in_progress','materials_drafted')` | fit_score, probability_score, relevance_score, title, company, location, remote, contacts, comp, notes, date |
   | `/board/applied` | `stage IN ('applied','interview','offer')` | title, company, applied_date, days_since_applied (computed), stage, user_notes, known_contacts, location, remote, comp, ai_notes |
   | `/board/review` | `stage = 'manual_review'` | title, company, score_flag_reason, source, date |
   | `/board/waitlist` | `stage = 'waitlisted'` | title, company, relevance_score, location, remote, ai_notes, date, blocking_app (computed) |
   | `/board/archive` | `1=1` (no filter) | fit_score, title, company, stage, location, remote, date, source, url |

   `fingerprint` is carried as a `data-fingerprint` attribute on each row for the materials-link lookup, not rendered as a visible column.
   `applied_date` is not a column on `jobs`; it is looked up from `audit_log` (first row where `field_changed='stage'` and `new_value='applied'`). `days_since_applied` is computed in SQL from that.
   `blocking_app` is computed per-row at query time: the most recent active application at the same company that isn't this job.
   Column-name mapping — the table above uses the Sheet's display names (from CLAUDE.md's Sheet Architecture section). The DB-to-display mapping (e.g., `remote_status` → "remote", `comp_estimate` → "comp", `known_contacts` → "contacts") is an implementation detail for the plan.

2. **Shared `_job_row.html` partial.** Single template renders a `<tr>` for any tab. Takes the row plus a `columns` list (what to show) and a `tab` name (for conditional formatting context, e.g., Applied row-age coloring only applies on `/board/applied`). Write the coloring logic once.

3. **Sort via URL params.** Clicking a column header sets `?sort=<col>&desc=0|1`. Server passes through to `ORDER BY`. Default sort per tab lives in `routes/board.py`. Unknown columns silently fall back to default.

4. **Filter via HTMX.**
   - Single text input above each table with `hx-get="/board/<tab>/rows"`, `hx-trigger="keyup changed delay:200ms"`, `hx-target="#rows"`.
   - Server endpoint returns only the `<tbody>` inner HTML (filtered rows), HTMX swaps the content.
   - Filter matches against `title` + `company` with `LIKE ?` (case-insensitive via `COLLATE NOCASE`).
   - Empty filter shows all rows.

5. **Archive pagination.** Archive alone needs pagination (~10k rows today, growing). HTMX infinite scroll:
   - First request returns 100 rows plus a sentinel `<tr hx-get="/board/archive/rows?offset=100" hx-trigger="revealed" hx-swap="outerHTML">`.
   - Each response extends the sentinel's offset; final response omits the sentinel.
   - Sort and filter work the same as other tabs; pagination state resets when either changes.

6. **Conditional formatting.** Match Sheet color rules via Tailwind utility classes, driven off CSS variables from the foundation PR:
   - Applied row-age: `applied_date` → Tailwind class via template filter (`0–6d`: green, `7–13d`: yellow, `14–20d`: red, `21+d`: gray).
   - Stage-based: Offer → gold row, Interviewing → purple row, Ghosted (user-set flag, separate column) → gray row regardless of age.
   - Known contacts: if `known_contacts` non-empty, apply amber background to that cell only (not the whole row).
   - Remote column: color-coded based on value (Remote → green text, Hybrid → amber, On-site → gray).
   - Classes applied in `_job_row.html` via Jinja conditionals. No inline styles.

7. **Materials link on Applied.** Company cell renders as a link to `/materials/{fingerprint}` when the job has a prep folder (stage in `materials_drafted/prep_in_progress/applied/interview/offer/waitlisted/rejected/not_selected`). Falls back to plain text otherwise. Same logic as `sync_sheet.py::_materials_company_cell` from #130.

### Tests (PR 2)

- For each tab: test the filter `WHERE` clause against fixture rows, confirm the returned set matches the Sheet's filter formula's semantics.
- Sort: `?sort=fit_score&desc=1` returns rows descending by score.
- HTMX filter endpoint: POST "meta" returns only rows where `title` or `company` matches "meta" (case-insensitive).
- Conditional formatting: fabricate rows aged 0d, 7d, 14d, 21d; assert `_job_row.html` output contains the correct Tailwind class for each.
- Materials link: assert the Applied tab's company cell is a `<a href="/materials/{fp}">` when the job has a folder, plain text otherwise.
- Archive pagination: first request returns 100 rows + sentinel; second request at `offset=100` returns next 100; final request (no more rows) returns sentinel-less response.

### Documentation Impact (PR 2)

- `CHANGELOG.md` — [Unreleased] entry: "Web viewer now renders the Dashboard, Applied, Review, Waitlist, and Archive board pages directly from the database. `sync_sheet.py` keeps updating Sheets in parallel during the 14b → 14c → 14d migration."
- `docs/setup/install-docker.md` — add a paragraph describing the board pages and the parallel-operation story.
- `CLAUDE.md` — in the "Google Sheet Architecture" section, note that the web UI at `/board/*` renders the same column sets. Add a TODO pointing at 14d (retiring `sync_sheet.py`).
- `docs/roadmap.md` — check off 14b.

---

## Sheet1 and the archive page

Sheet1's archival filter (`score>=5 OR stage in lifecycle OR age<14d OR target company`) exists to keep the Google Sheet under its 1000-row performance cliff. The database has no such cliff.

The `/board/archive` page in PR 2 shows **every** job — 10,881 rows today, growing — with pagination, filter, and sort. This is strictly more useful than Sheet1:

- All jobs are browsable, not just the archival-filter subset.
- Text search ("meta", "operations", "nvidia") works across the full history.
- Stage/score/date filters compose. Sheet1 has no in-sheet filter UI.

**Follow-up (after PR 2 ships, tracked in a new issue):**
- Stop writing Sheet1 from `sync_sheet.py`. The other five tabs (Dashboard, Applied, Review, Waitlist, Rejected Applications) stay in place until 14c/14d.
- Retire the `notify.py health-check` "Sheet1 > 1000 rows" warning. It no longer matters.
- Update CLAUDE.md's "Google Sheet Architecture" section to drop the Sheet1 paragraph.

---

## Data flow

- Every route reads `state/data/pipeline.db` through a SQLite connection (same file `sync_sheet.py` reads). Read-only — no writes in 14b.
- Each tab runs one `SELECT` with a `WHERE` clause matching the Sheet's filter formula. Results render straight into the template.
- Filter endpoint: keystroke in the filter box → HTMX request → server runs the same `SELECT` with an added `WHERE title LIKE ? OR company LIKE ?` → returns `<tbody>` inner HTML → HTMX swaps it. ~200ms debounce.
- Sort: URL param → `ORDER BY`. Whitelist of sortable columns per tab; unknown columns fall back to default.
- Pagination (archive only): `LIMIT 100 OFFSET ?` driven by HTMX `revealed` trigger.
- Materials link on Applied: template-level check (`row.stage IN (<folder stages>) AND base_url set`), same logic as `sync_sheet.py` hyperlink code.
- `sync_sheet.py` continues its 10-min cron schedule unchanged. Web UI and Sheet stay in lockstep because both read the same DB.

---

## Error handling

- **Database file missing** → 503 with "pipeline database not found" message. Matches existing `/healthz` pattern.
- **Bad URL params** (e.g., `?sort=not_a_column`) → silently fall back to default sort.
- **Stale fingerprint in materials link** (folder deleted from disk) → `/materials/{fp}` 404s with the existing handler from #59.
- **Template render failure** → FastAPI's default 500 page. Don't hide bugs.
- **Empty tab** (Review has 0 rows today) → renders table header + a "No jobs in this stage right now" body message.
- **Filter endpoint receives empty string** → returns full (unfiltered) row set. Matches user expectation.
- **Archive pagination past end** → returns an empty response with no sentinel, HTMX stops requesting.

---

## Testing strategy

### PR 1 — Foundation

- **Unit tests only.** Each route verified with FastAPI `TestClient`: asserts status 200 + nav present.
- `base.html` and `_nav.html` render without error against minimal contexts.
- **No browser tests.** Foundation has no interactivity beyond nav-link clicks; not worth Playwright setup.

### PR 2 — Board pages

- **Unit tests per tab:** filter SQL returns the right fixture rows, sort orders correctly, filter endpoint narrows correctly, materials link appears when expected.
- **Template tests:** conditional-formatting classes apply to the right rows given fabricated ages / stages.
- **Pagination test:** archive serves 100-row chunks; sentinel behaviour correct.
- **No Playwright** — added when write workflows (14c/#61) introduce click-through flows worth testing in a real browser.

### End-to-end verification (runs before each PR merges)

1. `docker compose up -d` on a stack with a copy of the real `pipeline.db`.
2. Open the UI in a browser; click every nav link; confirm each renders.
3. **PR 1:** confirm landing page shows correct stage counts against DB query. Confirm materials index at `/materials/` shows the same folders the old `/` did.
4. **PR 2:** for each board tab, compare row count against the Google Sheet's corresponding tab. They should match (modulo anything in-flight in `sync_sheet.py`'s 10-min window).
5. **PR 2:** click a company cell on Applied, confirm the materials folder opens.
6. **PR 2:** test the filter box by typing a known company name; confirm narrowing happens live.
7. **PR 2:** scroll the archive page; confirm infinite scroll loads additional rows.

---

## Out of scope / follow-ups

Each of these gets its own issue at or before the time it's needed:

| Follow-up | When | Issue |
|---|---|---|
| Write workflows (STATUS, REJECT_REASON, Flag for Prep buttons) | 14c | #61 |
| Retire Sheet1 in `sync_sheet.py`; drop its health check | After PR 2 ships | new issue |
| Retire the Sheet entirely | 14d | part of #14 |
| Manual job ingest form | later | #79 |
| Synthetic JD submission | later | #131 |
| Doctor / health dashboard | later | new issue |
| Stats / scoreboard | later | new issue |
| Config surfaces (roles, prefilter) | later | new issue |
| User documentation site | later | new issue |
| Onboarding interview UI | later | new issue |
| Notifications viewer | later | new issue |
| Auth / multi-user | when multi-user need arrives | new issue |
| Playwright E2E tests | when 14c writes land | part of 14c |

---

## Open questions / risks

- **Route-module split migration.** The foundation PR splits `routes.py` into a `routes/` package. This is a structural change touching the test suite. Plan task must explicitly run existing tests to confirm no regressions in materials routes from #59.
- **CDN availability.** Tailwind and HTMX load from `cdn.tailwindcss.com` and `unpkg.com`. If either is unreachable (corporate proxy, offline dev), pages render unstyled but still work. Document this in `install-docker.md`; revisit with a self-hosted bundle if testers complain.
- **Materials link parity with sync_sheet.py.** The "which stages get a hyperlink" list must stay in sync between `sync_sheet.py::_materials_company_cell` and `_job_row.html`. Extract the stage list into a shared constant in `findajob.web.constants` (or similar) so the two call sites can't drift.

---

## Related

- Parent arc: #14 — Web frontend phase.
- Dependency satisfied: #59 — Web materials viewer (closed 2026-04-21).
- Next in arc: #61 — 14c write workflows.
- Upstream motivation: the broader front-end roadmap (#79, #131, doctor, stats, config, notifications, docs, onboarding) — all build on this foundation.
