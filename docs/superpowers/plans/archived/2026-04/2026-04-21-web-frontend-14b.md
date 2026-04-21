# Web Frontend 14b Implementation Plan (#60)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a read-only pipeline front-end (#60) as two PRs — a foundation PR (shell, nav, Tailwind + HTMX wiring, URL-IA restructure, routes/ package split) followed by a board PR (five pages — Dashboard, Applied, Review, Waitlist, Archive — with sort, filter, conditional formatting, and materials link).

**Architecture:** Server-rendered HTML via FastAPI + Jinja; Tailwind via CDN; HTMX for partial swaps; URL-param UI state; one file per URL group. No SPA, no build step, no auth. See `docs/superpowers/specs/2026-04-21-web-frontend-14b-design.md` for design rationale.

**Tech Stack:** Python 3.12, FastAPI, Jinja2, Python-Markdown (all already installed from #59), SQLite (stdlib), Tailwind (CDN), HTMX (CDN). Tests: pytest + FastAPI `TestClient`.

---

## Spec reference

This plan implements `docs/superpowers/specs/2026-04-21-web-frontend-14b-design.md` (commit `d08cb4b` on `main`). Read the spec first if anything below is ambiguous. All five foundational scope decisions (Jinja+HTMX, grouped URL IA, Tailwind via CDN, HTMX+Alpine-when-needed, URL-param UI state) are resolved in the spec and not revisited here.

## Issues

- #60 — Web frontend 14b: read-only dashboard/applied/review/waitlist views. In Progress.

## Branch discipline

Per memory `feedback_git_branch_off_origin`, every branch is created from `origin/main`, never from local `main`. PR 1 branches off `origin/main` at Task 1; PR 2 branches off `origin/main` AFTER PR 1 merges (Task 12 / 13 transition).

## Goal + scope

**In scope:**
- PR 1: layout shell, top-nav (7 links), Tailwind + HTMX CDN wiring, URL restructure (move `/` materials index to `/materials/`, new `/` landing), split monolithic `routes.py` into a `routes/` package, placeholder pages for unshipped groups.
- PR 2: five board pages under `/board/` matching Sheet column sets; sort via URL params; HTMX filter per tab; HTMX infinite-scroll pagination on `/board/archive`; conditional formatting matching Sheet color rules; Applied tab's company cell hyperlinks into the materials viewer.

**Explicitly out of scope (spec §Deferred):**
- Write workflows (STATUS dropdowns, Flag-for-Prep, REJECT_REASON pickers) — 14c / #61.
- Auth — never mentioned by user; document "don't expose to public internet" only.
- Mobile-first design — Tailwind handles responsive for free.
- Playwright — added in 14c.
- Component framework — Jinja macros only.
- Retiring Sheet1 from `sync_sheet.py` — separate follow-up issue.

## File structure

**Created in PR 1:**
```
src/findajob/web/
  static/
    app.css                                         (CSS variables for Sheet color palette)
  templates/
    base.html                                       (shell: head + top-nav + content block)
    _nav.html                                       (top-nav macro)
    landing.html                                    (new /)
    materials/
      index.html                                    (moved from templates/index.html)
      folder.html                                   (moved from templates/folder.html)
    placeholders/
      coming_soon.html                              (shared stub)
  routes/
    __init__.py                                     (router aggregator)
    landing.py                                      (/ + placeholder groups)
    materials.py                                    (/materials/* extracted)
    healthz.py                                      (/healthz extracted)
    board.py                                        (stub in PR 1; filled in PR 2)

tests/test_web_landing.py                           (landing + placeholder routes)
tests/test_web_nav.py                               (active-link highlighting)
tests/test_web_routes_package.py                    (router aggregation smoke)
```

**Modified in PR 1:**
```
src/findajob/web/app.py                             (mount StaticFiles; import from routes package)
src/findajob/web/templates/base.html                (new — replaces anonymous inline base)
tests/test_web_routes.py                            (update imports for new path; keep existing assertions)
docs/setup/install-docker.md                        (+ top-nav mention)
CHANGELOG.md                                        ([Unreleased] entry)
CLAUDE.md                                           (+ "Web Frontend Architecture" subsection)
```

**Deleted in PR 1:**
```
src/findajob/web/routes.py                          (replaced by routes/ package)
src/findajob/web/templates/base.html                (if pre-existing inline version exists; overwritten)
src/findajob/web/templates/index.html               (moved to materials/index.html)
src/findajob/web/templates/folder.html              (moved to materials/folder.html)
```

**Created in PR 2:**
```
src/findajob/web/constants.py                       (FOLDER_STAGES — shared with sync_sheet.py)
src/findajob/web/templates/_job_row.html            (shared row partial)
src/findajob/web/templates/_filters.html            (HTMX filter form)
src/findajob/web/templates/board/
  dashboard.html
  applied.html
  review.html
  waitlist.html
  archive.html

tests/test_web_board_dashboard.py
tests/test_web_board_applied.py
tests/test_web_board_review.py
tests/test_web_board_waitlist.py
tests/test_web_board_archive.py
tests/test_web_board_filter.py                      (HTMX filter endpoint, shared)
tests/test_web_board_sort.py                        (URL-param sort, shared)
tests/test_web_board_formatting.py                  (conditional-formatting classes)
```

**Modified in PR 2:**
```
src/findajob/web/routes/board.py                    (fill in real handlers)
src/findajob/web/routes/landing.py                  (drop /board/ placeholder; board takes over)
scripts/sync_sheet.py                               (import FOLDER_STAGES from findajob.web.constants)
tests/test_sync_sheet.py                            (no behavioral change; import may update)
docs/setup/install-docker.md                        (+ board pages section)
CHANGELOG.md                                        ([Unreleased] entry)
CLAUDE.md                                           (§"Google Sheet Architecture" note about /board/*)
docs/roadmap.md                                     (check off 14b — if the arc is tracked here)
```

---

# PR 1 — Foundation

## Task 1: Create PR 1 feature branch and baseline

**Files:**
- Modify: working-tree branch state only

- [ ] **Step 1:** Fetch latest from origin.
  ```
  git fetch origin
  ```

- [ ] **Step 2:** Create feature branch off `origin/main`.
  ```
  git checkout -b feat/60-web-foundation origin/main
  ```

- [ ] **Step 3:** Confirm clean worktree; run existing web tests as baseline.
  ```
  python3 -m pytest tests/test_web_app.py tests/test_web_routes.py tests/test_web_folder_resolver.py -v
  ```
  Expected: all existing web tests pass (from #59).

- [ ] **Step 4:** No commit — this is branch setup only.

**Commit message:** (none — no files changed yet)

---

## Task 2: Split routes.py into routes/ package (structure only; no URL changes)

**Files:**
- Create: `src/findajob/web/routes/__init__.py`
- Create: `src/findajob/web/routes/materials.py`
- Create: `src/findajob/web/routes/healthz.py`
- Create: `src/findajob/web/routes/board.py` (empty stub)
- Create: `src/findajob/web/routes/landing.py` (empty stub)
- Delete: `src/findajob/web/routes.py`
- Modify: `src/findajob/web/app.py` (import path)
- Create: `tests/test_web_routes_package.py`

Goal of this task: restructure without changing URLs. After this task, `/`, `/healthz`, `/materials/{fp}`, `/materials/{fp}/{file}` all still resolve to the same handlers; the renamed / restructured URLs come in later tasks.

- [ ] **Step 1: Write failing test for the package aggregator.**
  Create `tests/test_web_routes_package.py`:
  ```python
  """Router package aggregates all sub-module routers and exposes a single `router`."""
  from findajob.web.routes import router as aggregated

  def test_router_is_apirouter():
      from fastapi import APIRouter
      assert isinstance(aggregated, APIRouter)

  def test_routes_include_healthz_and_materials_and_landing():
      paths = [r.path for r in aggregated.routes]
      assert "/healthz" in paths
      assert "/" in paths  # materials_index, pre-rename
      assert "/materials/{fingerprint}" in paths
      assert "/materials/{fingerprint}/{filename}" in paths
  ```

- [ ] **Step 2: Run the test — expect failure (ModuleNotFoundError).**
  ```
  python3 -m pytest tests/test_web_routes_package.py -v
  ```
  Expected: `ModuleNotFoundError: No module named 'findajob.web.routes'`

- [ ] **Step 3: Create `routes/materials.py` extracting the three current materials handlers.**
  Copy `index`, `folder_view`, `file_serve`, `_render_markdown`, and `get_db` stub from the current `src/findajob/web/routes.py` verbatim. Replace `router = APIRouter()` header with `router = APIRouter()`. The `get_db` stub must stay — `app.py`'s override targets `findajob.web.routes.materials.get_db`.

  Content (full file):
  ```python
  """Materials viewer routes: /, /materials/{fp}, /materials/{fp}/{file}."""
  from __future__ import annotations

  import re
  import sqlite3
  from pathlib import Path

  import markdown as md_lib
  from fastapi import APIRouter, Depends, HTTPException, Request
  from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse

  from findajob.web.folder_resolver import resolve_folder

  router = APIRouter()


  def get_db() -> sqlite3.Connection:  # pragma: no cover — overridden in app factory
      raise NotImplementedError("DB dependency must be overridden by create_app()")


  def _render_markdown(text: str) -> str:
      html = md_lib.markdown(text, extensions=["fenced_code", "tables"], output_format="html")
      html = re.sub(r' class="[^"]*"', "", html)
      html = re.sub(r"<(/?script)", r"&lt;\1", html, flags=re.IGNORECASE)
      return html


  _INDEX_QUERY_SECTIONS = [
      ("In flight", "stage IN ('materials_drafted', 'prep_in_progress')", "created_at DESC"),
      ("Applied", "stage IN ('applied', 'interview', 'offer')", "COALESCE(stage_updated, created_at) DESC"),
      ("Waitlisted", "stage = 'waitlisted'", "created_at DESC"),
  ]
  _REJECTED_CLAUSE = "stage IN ('rejected', 'not_selected')"
  _PER_SECTION_CAP = 50


  def _fetch_section(db: sqlite3.Connection, where: str, order: str) -> list[sqlite3.Row]:
      return db.execute(
          f"SELECT fingerprint, title, company, stage, fit_score, created_at, stage_updated "
          f"FROM jobs WHERE {where} ORDER BY {order} LIMIT {_PER_SECTION_CAP + 1}"
      ).fetchall()


  @router.get("/", response_class=HTMLResponse)
  def index(request: Request, db: sqlite3.Connection = Depends(get_db)) -> HTMLResponse:  # noqa: B008
      sections = []
      for name, where, order in _INDEX_QUERY_SECTIONS:
          rows = _fetch_section(db, where, order)
          overflow = len(rows) > _PER_SECTION_CAP
          sections.append({"name": name, "rows": rows[:_PER_SECTION_CAP], "overflow": overflow})
      rejected_rows = _fetch_section(db, _REJECTED_CLAUSE, "created_at DESC")
      rejected = {
          "rows": rejected_rows[:_PER_SECTION_CAP],
          "overflow": len(rejected_rows) > _PER_SECTION_CAP,
          "count": len(rejected_rows) if len(rejected_rows) <= _PER_SECTION_CAP else f"{_PER_SECTION_CAP}+",
      }
      templates = request.app.state.templates
      return templates.TemplateResponse(
          request=request,
          name="index.html",
          context={"sections": sections, "rejected": rejected},
      )


  @router.get("/materials/{fingerprint}", response_class=HTMLResponse)
  def folder_view(
      fingerprint: str,
      request: Request,
      db: sqlite3.Connection = Depends(get_db),  # noqa: B008
  ) -> HTMLResponse:
      root: Path = request.app.state.companies_root
      folder = resolve_folder(fingerprint, db, root)
      if folder is None:
          raise HTTPException(status_code=404, detail="folder not found")
      row = db.execute("SELECT title, company, stage FROM jobs WHERE fingerprint = ?", (fingerprint,)).fetchone()
      files = sorted(p.name for p in folder.iterdir() if p.is_file())
      templates = request.app.state.templates
      return templates.TemplateResponse(
          request=request,
          name="folder.html",
          context={
              "fingerprint": fingerprint,
              "folder_name": folder.name,
              "title": row["title"] if row else "",
              "company": row["company"] if row else "",
              "stage": row["stage"] if row else "",
              "files": files,
          },
      )


  @router.get("/materials/{fingerprint}/{filename}")
  def file_serve(
      fingerprint: str,
      filename: str,
      request: Request,
      db: sqlite3.Connection = Depends(get_db),  # noqa: B008
  ):
      root: Path = request.app.state.companies_root
      folder = resolve_folder(fingerprint, db, root)
      if folder is None:
          raise HTTPException(status_code=404, detail="folder not found")
      candidate = (folder / filename).resolve()
      try:
          candidate.relative_to(folder.resolve())
      except ValueError:
          raise HTTPException(status_code=404, detail="invalid filename") from None
      if not candidate.is_file():
          raise HTTPException(status_code=404, detail="file not found")
      ext = candidate.suffix.lower()
      if ext == ".md":
          body = candidate.read_text(encoding="utf-8", errors="replace")
          templates = request.app.state.templates
          return templates.TemplateResponse(
              request=request,
              name="base.html",
              context={"_rendered_md": _render_markdown(body)},
              headers={"content-type": "text/html; charset=utf-8"},
          )
      if ext == ".txt":
          return PlainTextResponse(content=candidate.read_text(encoding="utf-8", errors="replace"))
      return FileResponse(
          path=candidate,
          filename=candidate.name,
          headers={"content-disposition": f'attachment; filename="{candidate.name}"'},
      )
  ```

- [ ] **Step 4: Create `routes/healthz.py`.**
  ```python
  """Health check endpoint."""
  from pathlib import Path

  from fastapi import APIRouter, Request
  from fastapi.responses import Response

  router = APIRouter()


  @router.get("/healthz", response_class=Response)
  def healthz(request: Request) -> Response:
      root: Path = request.app.state.companies_root
      if not root.is_dir():
          return Response(content="companies/ missing", status_code=503, media_type="text/plain")
      return Response(content="ok", status_code=200, media_type="text/plain")
  ```

- [ ] **Step 5: Create `routes/landing.py` and `routes/board.py` as empty stubs.**
  Each contains only:
  ```python
  """Stub — real handlers added in a later task."""
  from fastapi import APIRouter

  router = APIRouter()
  ```

- [ ] **Step 6: Create `routes/__init__.py` aggregating all sub-routers.**
  ```python
  """Aggregates all sub-module routers into a single `router` the app includes."""
  from fastapi import APIRouter

  from findajob.web.routes import board, healthz, landing, materials

  router = APIRouter()
  router.include_router(materials.router)
  router.include_router(healthz.router)
  router.include_router(landing.router)
  router.include_router(board.router)
  ```

- [ ] **Step 7: Update `src/findajob/web/app.py` to import from the package.**
  Replace the line `from findajob.web import routes` with `from findajob.web.routes import materials as _materials_routes, router as _aggregated_router`.
  Replace `app.dependency_overrides.setdefault(routes.get_db, get_db)` with `app.dependency_overrides.setdefault(_materials_routes.get_db, get_db)`.
  Replace `app.include_router(routes.router)` with `app.include_router(_aggregated_router)`.

- [ ] **Step 8: Delete `src/findajob/web/routes.py`.**
  ```
  git rm src/findajob/web/routes.py
  ```

- [ ] **Step 9: Run all web tests.**
  ```
  python3 -m pytest tests/test_web_app.py tests/test_web_routes.py tests/test_web_routes_package.py tests/test_web_folder_resolver.py -v
  ```
  Expected: all pass.

- [ ] **Step 10: Commit.**
  ```
  git add src/findajob/web/routes/ src/findajob/web/app.py tests/test_web_routes_package.py
  git rm src/findajob/web/routes.py
  git commit -m "refactor(web): split routes.py into routes/ package (#60)"
  ```

---

## Task 3: Create base.html shell, _nav.html, app.css, and wire static mount

**Files:**
- Create: `src/findajob/web/static/app.css`
- Create: `src/findajob/web/templates/base.html`
- Create: `src/findajob/web/templates/_nav.html`
- Modify: `src/findajob/web/app.py` (mount StaticFiles)
- Create: `tests/test_web_nav.py`

- [ ] **Step 1: Write failing test for `_nav.html` active-link highlighting.**
  Create `tests/test_web_nav.py`:
  ```python
  """_nav.html partial highlights the current route."""
  import sqlite3
  from pathlib import Path

  import pytest
  from fastapi.testclient import TestClient

  from findajob.web.app import create_app


  @pytest.fixture
  def client(tmp_path: Path) -> TestClient:
      db = tmp_path / "pipeline.db"
      conn = sqlite3.connect(db)
      conn.execute(
          "CREATE TABLE jobs (fingerprint TEXT, title TEXT, company TEXT, stage TEXT, "
          "fit_score REAL, created_at TEXT, stage_updated TEXT)"
      )
      conn.commit()
      conn.close()
      companies = tmp_path / "companies"
      companies.mkdir()
      app = create_app(companies_root=companies, db_path=db)
      return TestClient(app)


  def test_nav_present_on_landing(client: TestClient) -> None:
      r = client.get("/")
      assert r.status_code == 200
      # Will pass once landing handler is wired in Task 6; for now materials index at /
      # still renders, and _nav.html is included in base.html.
      assert 'href="/"' in r.text
      assert 'href="/materials/"' in r.text
      assert 'href="/board/dashboard"' in r.text
      assert 'href="/ingest/"' in r.text
      assert 'href="/tools/"' in r.text
      assert 'href="/config/"' in r.text
      assert 'href="/docs/"' in r.text
  ```

- [ ] **Step 2: Run the test — expect failure.**
  ```
  python3 -m pytest tests/test_web_nav.py -v
  ```
  Expected: FAIL (nav links not present because base.html doesn't include `_nav.html` yet).

- [ ] **Step 3: Create `src/findajob/web/static/app.css`.**
  ```css
  /* Design tokens matching the Google Sheet's conditional formatting palette. */
  :root {
    --color-applied-fresh: #c6e6b9;  /* 0–6 days, green */
    --color-applied-week:  #fff3b0;  /* 7–13 days, yellow */
    --color-applied-stale: #f4b7b0;  /* 14–20 days, red */
    --color-applied-cold:  #d6d6d6;  /* 21+ days, gray */
    --color-offer:         #ffd700;  /* gold */
    --color-interviewing:  #c8a2d8;  /* purple */
    --color-ghosted:       #d6d6d6;  /* gray */
    --color-contact-amber: #ffbf00;
  }

  /* Apply via Tailwind arbitrary-value utilities: bg-[var(--color-applied-fresh)] */

  .row-applied-fresh  { background-color: var(--color-applied-fresh); }
  .row-applied-week   { background-color: var(--color-applied-week); }
  .row-applied-stale  { background-color: var(--color-applied-stale); }
  .row-applied-cold   { background-color: var(--color-applied-cold); }
  .row-offer          { background-color: var(--color-offer); }
  .row-interviewing   { background-color: var(--color-interviewing); }
  .row-ghosted        { background-color: var(--color-ghosted); }
  .cell-contact-amber { background-color: var(--color-contact-amber); }
  ```

- [ ] **Step 4: Create `src/findajob/web/templates/_nav.html`.**
  ```html
  {# Top navigation. Highlights the active group via aria-current="page". #}
  {% set groups = [
    ("/", "Home"),
    ("/board/dashboard", "Board"),
    ("/materials/", "Materials"),
    ("/ingest/", "Ingest"),
    ("/tools/", "Tools"),
    ("/config/", "Config"),
    ("/docs/", "Docs"),
  ] %}
  <nav class="bg-slate-800 text-slate-100 px-4 py-2 shadow-sm">
    <ul class="flex gap-4 items-center">
      <li class="font-bold mr-4">findajob</li>
      {% for href, label in groups %}
        {% set active = request.url.path == href
             or (href != "/" and request.url.path.startswith(href)) %}
        <li>
          <a href="{{ href }}"
             {% if active %}aria-current="page"{% endif %}
             class="px-2 py-1 rounded {% if active %}bg-slate-600{% else %}hover:bg-slate-700{% endif %}">
            {{ label }}
          </a>
        </li>
      {% endfor %}
    </ul>
  </nav>
  ```

- [ ] **Step 5: Create `src/findajob/web/templates/base.html`.**
  ```html
  <!DOCTYPE html>
  <html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{% block title %}findajob{% endblock %}</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://unpkg.com/htmx.org@2" defer></script>
    <link rel="stylesheet" href="/static/app.css">
  </head>
  <body class="bg-slate-50 text-slate-900" hx-boost="true">
    {% block nav %}{% include "_nav.html" %}{% endblock %}
    <main class="max-w-6xl mx-auto px-4 py-6">
      {% if _rendered_md %}{{ _rendered_md | safe }}{% endif %}
      {% block content %}{% endblock %}
    </main>
  </body>
  </html>
  ```

- [ ] **Step 6: Mount StaticFiles in `app.py`.**
  In `create_app`, after `templates = Jinja2Templates(...)`, add:
  ```python
  from fastapi.staticfiles import StaticFiles
  static_dir = Path(__file__).parent / "static"
  app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
  ```
  Place the `from fastapi.staticfiles import StaticFiles` import at the top of the file with other imports.

- [ ] **Step 7: Run the nav test.**
  ```
  python3 -m pytest tests/test_web_nav.py -v
  ```
  Expected: PASS — all 7 nav hrefs appear in the rendered response for `/`.

- [ ] **Step 8: Run existing tests to confirm no regressions.**
  ```
  python3 -m pytest tests/test_web_app.py tests/test_web_routes.py tests/test_web_folder_resolver.py tests/test_web_nav.py -v
  ```
  Expected: all pass. Note: existing `index.html` still works because base.html exposes `_rendered_md` in the content block, but materials' `index.html` doesn't extend base yet — that's Task 4.

- [ ] **Step 9: Commit.**
  ```
  git add src/findajob/web/static/app.css src/findajob/web/templates/base.html src/findajob/web/templates/_nav.html src/findajob/web/app.py tests/test_web_nav.py
  git commit -m "feat(web): add base layout with top nav, Tailwind/HTMX CDNs, and static mount (#60)"
  ```

---

## Task 4: Move existing templates into materials/ subdirectory and extend base

**Files:**
- Create: `src/findajob/web/templates/materials/index.html`
- Create: `src/findajob/web/templates/materials/folder.html`
- Delete: `src/findajob/web/templates/index.html`
- Delete: `src/findajob/web/templates/folder.html`
- Modify: `src/findajob/web/routes/materials.py` (update `name=` args)

- [ ] **Step 1: Read the current `src/findajob/web/templates/index.html`** and wrap its body in `{% extends "base.html" %}{% block content %}...{% endblock %}`.
  Create `src/findajob/web/templates/materials/index.html` with the wrapped body — remove any `<html>`/`<head>`/`<body>` tags if present; keep everything inside the page's `<body>`.

- [ ] **Step 2: Do the same for `folder.html`** → create `src/findajob/web/templates/materials/folder.html`.

- [ ] **Step 3: Delete the flat-path originals.**
  ```
  git rm src/findajob/web/templates/index.html src/findajob/web/templates/folder.html
  ```

- [ ] **Step 4: Update `routes/materials.py`** — change `name="index.html"` → `name="materials/index.html"` and `name="folder.html"` → `name="materials/folder.html"`.

- [ ] **Step 5: Also update the `file_serve` markdown-render path** — `name="base.html"` in the `.md` branch stays as `base.html`.

- [ ] **Step 6: Run full web test suite.**
  ```
  python3 -m pytest tests/test_web_app.py tests/test_web_routes.py tests/test_web_routes_package.py tests/test_web_nav.py tests/test_web_folder_resolver.py -v
  ```
  Expected: all pass.

- [ ] **Step 7: Commit.**
  ```
  git add src/findajob/web/templates/materials/ src/findajob/web/routes/materials.py
  git rm src/findajob/web/templates/index.html src/findajob/web/templates/folder.html
  git commit -m "refactor(web): move materials templates under templates/materials/ (#60)"
  ```

---

## Task 5: Rename `/` materials route to `/materials/`

**Files:**
- Modify: `src/findajob/web/routes/materials.py` (path + handler name)
- Modify: `tests/test_web_routes.py` (update URL in existing tests)

- [ ] **Step 1: Write a test that `GET /` now returns something other than the materials index.**
  Add to `tests/test_web_nav.py`:
  ```python
  def test_materials_index_moved(client: TestClient) -> None:
      r = client.get("/materials/")
      assert r.status_code == 200
      # Content-wise, must still list lifecycle sections
      assert "In flight" in r.text or "Applied" in r.text or "Rejected" in r.text
  ```

- [ ] **Step 2: Run the test — expect failure (404 on /materials/).**
  ```
  python3 -m pytest tests/test_web_nav.py::test_materials_index_moved -v
  ```
  Expected: FAIL.

- [ ] **Step 3: Edit `routes/materials.py`** — change `@router.get("/", response_class=HTMLResponse)` to `@router.get("/materials/", response_class=HTMLResponse)`. Rename `def index(` to `def materials_index(` for clarity.

- [ ] **Step 4: Update `tests/test_web_routes.py`** — every reference to `client.get("/")` that was checking the materials index becomes `client.get("/materials/")`. Keep the deep-link tests on `/materials/{fp}` and `/materials/{fp}/{file}` as-is.

- [ ] **Step 5: Run full web suite.**
  ```
  python3 -m pytest tests/test_web_app.py tests/test_web_routes.py tests/test_web_routes_package.py tests/test_web_nav.py tests/test_web_folder_resolver.py -v
  ```
  Expected: all pass. `/` is now a 404 (no handler yet — landing comes in Task 6).

- [ ] **Step 6: Commit.**
  ```
  git add src/findajob/web/routes/materials.py tests/test_web_routes.py tests/test_web_nav.py
  git commit -m "refactor(web): move materials index from / to /materials/ (#60)"
  ```

---

## Task 6: Add new `/` landing page with stage counts

**Files:**
- Modify: `src/findajob/web/routes/landing.py`
- Create: `src/findajob/web/templates/landing.html`
- Create: `tests/test_web_landing.py`

- [ ] **Step 1: Write failing test for landing page stage counts.**
  Create `tests/test_web_landing.py`:
  ```python
  """Landing page shows stage counts."""
  import sqlite3
  from pathlib import Path

  import pytest
  from fastapi.testclient import TestClient

  from findajob.web.app import create_app


  @pytest.fixture
  def client(tmp_path: Path) -> TestClient:
      db = tmp_path / "pipeline.db"
      conn = sqlite3.connect(db)
      conn.execute(
          "CREATE TABLE jobs (fingerprint TEXT, title TEXT, company TEXT, stage TEXT, "
          "fit_score REAL, created_at TEXT, stage_updated TEXT)"
      )
      for stage, n in [("scored", 5), ("applied", 2), ("rejected", 3)]:
          for i in range(n):
              conn.execute(
                  "INSERT INTO jobs (fingerprint, title, company, stage, created_at) "
                  "VALUES (?, 't', 'c', ?, '2026-01-01')",
                  (f"fp-{stage}-{i}", stage),
              )
      conn.commit()
      conn.close()
      companies = tmp_path / "companies"
      companies.mkdir()
      app = create_app(companies_root=companies, db_path=db)
      return TestClient(app)


  def test_landing_shows_stage_counts(client: TestClient) -> None:
      r = client.get("/")
      assert r.status_code == 200
      # Each stage + its count appears in the page
      assert ">5<" in r.text and "scored" in r.text
      assert ">2<" in r.text and "applied" in r.text
      assert ">3<" in r.text and "rejected" in r.text


  def test_landing_nav_home_active(client: TestClient) -> None:
      r = client.get("/")
      assert r.status_code == 200
      # The Home nav link should carry aria-current="page"
      assert 'href="/" aria-current="page"' in r.text or 'aria-current="page"\n             class' in r.text
  ```

- [ ] **Step 2: Run — expect 404 on /.**
  ```
  python3 -m pytest tests/test_web_landing.py -v
  ```
  Expected: FAIL (404).

- [ ] **Step 3: Fill `routes/landing.py`.**
  ```python
  """Landing page at / and placeholder groups."""
  from __future__ import annotations

  import sqlite3

  from fastapi import APIRouter, Depends, Request
  from fastapi.responses import HTMLResponse

  from findajob.web.routes.materials import get_db

  router = APIRouter()


  _STAGES_ORDER = [
      "scored",
      "manual_review",
      "prep_in_progress",
      "materials_drafted",
      "applied",
      "interview",
      "offer",
      "waitlisted",
      "rejected",
      "not_selected",
  ]


  @router.get("/", response_class=HTMLResponse)
  def landing(
      request: Request,
      db: sqlite3.Connection = Depends(get_db),  # noqa: B008
  ) -> HTMLResponse:
      rows = db.execute("SELECT stage, COUNT(*) AS n FROM jobs GROUP BY stage").fetchall()
      counts = {r["stage"]: r["n"] for r in rows}
      ordered = [(s, counts.get(s, 0)) for s in _STAGES_ORDER]
      templates = request.app.state.templates
      return templates.TemplateResponse(
          request=request,
          name="landing.html",
          context={"ordered": ordered},
      )
  ```

- [ ] **Step 4: Create `src/findajob/web/templates/landing.html`.**
  ```html
  {% extends "base.html" %}
  {% block title %}findajob — pipeline{% endblock %}
  {% block content %}
  <h1 class="text-2xl font-semibold mb-4">Pipeline at a glance</h1>
  <div class="grid grid-cols-2 md:grid-cols-5 gap-3">
    {% for stage, n in ordered %}
      <div class="bg-white rounded-md shadow-sm p-4 flex flex-col items-center">
        <div class="text-3xl font-mono">{{ n }}</div>
        <div class="text-xs uppercase tracking-wide text-slate-500 mt-1">{{ stage }}</div>
      </div>
    {% endfor %}
  </div>
  {% endblock %}
  ```

- [ ] **Step 5: Re-run the landing test.**
  ```
  python3 -m pytest tests/test_web_landing.py -v
  ```
  Expected: PASS.

- [ ] **Step 6: Run full web suite.**
  ```
  python3 -m pytest tests/test_web_app.py tests/test_web_routes.py tests/test_web_routes_package.py tests/test_web_nav.py tests/test_web_landing.py tests/test_web_folder_resolver.py -v
  ```
  Expected: all pass.

- [ ] **Step 7: Commit.**
  ```
  git add src/findajob/web/routes/landing.py src/findajob/web/templates/landing.html tests/test_web_landing.py
  git commit -m "feat(web): landing page at / with stage counts (#60)"
  ```

---

## Task 7: Placeholder routes for /board/, /ingest/, /tools/, /config/, /docs/

**Files:**
- Modify: `src/findajob/web/routes/landing.py` (add placeholder handlers)
- Create: `src/findajob/web/templates/placeholders/coming_soon.html`
- Modify: `tests/test_web_landing.py` (extend)

- [ ] **Step 1: Write failing tests for each placeholder.**
  Append to `tests/test_web_landing.py`:
  ```python
  @pytest.mark.parametrize("path,label,issue", [
      ("/board/", "Board", "#60"),
      ("/ingest/", "Ingest", "#79"),
      ("/tools/", "Tools", ""),
      ("/config/", "Config", ""),
      ("/docs/", "Docs", ""),
  ])
  def test_placeholder_renders(client: TestClient, path: str, label: str, issue: str) -> None:
      r = client.get(path)
      assert r.status_code == 200
      assert "Coming soon" in r.text
      assert label in r.text
  ```

- [ ] **Step 2: Run — expect 404s.**
  ```
  python3 -m pytest tests/test_web_landing.py -v
  ```
  Expected: the 5 parametrized tests fail with 404.

- [ ] **Step 3: Create `src/findajob/web/templates/placeholders/coming_soon.html`.**
  ```html
  {% extends "base.html" %}
  {% block title %}{{ label }} — Coming soon{% endblock %}
  {% block content %}
  <h1 class="text-2xl font-semibold mb-2">{{ label }}</h1>
  <p class="text-slate-600">Coming soon. {{ hint }}
  {% if issue %}Tracking: <a class="underline" href="https://github.com/brockamer/findajob/issues/{{ issue[1:] }}">{{ issue }}</a>.{% endif %}
  </p>
  {% endblock %}
  ```

- [ ] **Step 4: Add placeholder handlers to `routes/landing.py`.**
  Append after `landing`:
  ```python
  _PLACEHOLDERS = [
      ("/board/", "Board", "Dashboard, Applied, Review, Waitlist, Archive will live here.", "#60"),
      ("/ingest/", "Ingest", "Manual job form and synthetic JD submission.", "#79"),
      ("/tools/", "Tools", "Doctor, stats, scoreboard.", ""),
      ("/config/", "Config", "Roles, prefilter rules, feedback tuning.", ""),
      ("/docs/", "Docs", "User-facing documentation.", ""),
  ]


  def _make_placeholder(path: str, label: str, hint: str, issue: str):
      @router.get(path, response_class=HTMLResponse)
      def _handler(request: Request) -> HTMLResponse:
          templates = request.app.state.templates
          return templates.TemplateResponse(
              request=request,
              name="placeholders/coming_soon.html",
              context={"label": label, "hint": hint, "issue": issue},
          )
      _handler.__name__ = f"placeholder_{label.lower()}"
      return _handler


  for _p, _l, _h, _i in _PLACEHOLDERS:
      _make_placeholder(_p, _l, _h, _i)
  ```

- [ ] **Step 5: Re-run tests.**
  ```
  python3 -m pytest tests/test_web_landing.py -v
  ```
  Expected: all PASS including the 5 parametrized placeholder tests.

- [ ] **Step 6: Commit.**
  ```
  git add src/findajob/web/routes/landing.py src/findajob/web/templates/placeholders/ tests/test_web_landing.py
  git commit -m "feat(web): coming-soon placeholders for /board, /ingest, /tools, /config, /docs (#60)"
  ```

---

## Task 8: Foundation docs updates

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `docs/setup/install-docker.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1:** Add a new [Unreleased] entry in `CHANGELOG.md` under `### Added`:
  ```markdown
  - Web viewer now has a top nav and landing page. Materials folder index moved from `/` to `/materials/`; deep links `/materials/{fingerprint}` and `/materials/{fingerprint}/{filename}` unchanged. Placeholder pages for board, ingest, tools, config, docs fill in as features land (#60).
  ```

- [ ] **Step 2:** Update `docs/setup/install-docker.md` — in the "Materials viewer port" section, add a paragraph:
  ```markdown
  The viewer has a top nav linking all feature groups. `/` is a pipeline-at-a-glance landing page; `/materials/` is the prep-folder index (previously served at `/`).
  ```

- [ ] **Step 3:** Add a new "Web Frontend Architecture" subsection to `CLAUDE.md` under "Key File Locations" (right before the closing of that section):
  ```markdown
  ### Web Frontend Architecture
  
  Live at `src/findajob/web/`. One file per URL group in `routes/` (e.g.
  `routes/materials.py`, `routes/board.py`, `routes/landing.py`). Shared
  partials (`_nav.html`, `_job_row.html`) live in `templates/`.
  
  Foundational decisions (from `docs/superpowers/specs/2026-04-21-web-frontend-14b-design.md`):
  - Server-rendered HTML + HTMX (no SPA)
  - Grouped URL IA — top-nav = `/`, `/board/`, `/materials/`, `/ingest/`, `/tools/`, `/config/`, `/docs/`
  - Tailwind via CDN + `static/app.css` design tokens
  - URL query params for UI state (not cookies/localStorage)
  - Alpine.js added only when ephemeral client state is needed
  ```

- [ ] **Step 4:** Run the pre-commit hook if present (PII check):
  ```
  git add CHANGELOG.md docs/setup/install-docker.md CLAUDE.md
  git status
  ```

- [ ] **Step 5:** Commit.
  ```
  git commit -m "docs(60): foundation — top nav, URL IA restructure, web-frontend architecture note"
  ```

---

## Task 9: PR 1 whole-feature verification + open PR

- [ ] **Step 1: Run the full pytest suite** (not just web tests — confirm no cross-cutting regressions).
  ```
  python3 -m pytest -q
  ```
  Expected: all pass. Fastapi is a dev dep; if the environment can't import it, skip the web tests but confirm with `--collect-only` they're discovered.

- [ ] **Step 2: Lint + typecheck.**
  ```
  python3 -m ruff check src/findajob/web/ tests/
  python3 -m ruff format --check src/findajob/web/ tests/
  python3 -m mypy src/findajob/web/
  ```
  Expected: all clean.

- [ ] **Step 3: Build and run the container locally, smoke the UI.**
  Option A (against current docker.lan stack):
  1. Push the branch to origin: `git push -u origin feat/60-web-foundation`
  2. On docker.lan, temporarily pin the `scheduler` image to the branch's `main-<sha>` tag after the `build-image.yml` GHA finishes.
  3. Open `http://docker.lan:8090/` in the browser; confirm the landing page shows stage counts.
  4. Click every nav link; confirm each renders (Board, Ingest, Tools, Config, Docs show "Coming soon").
  5. Click Materials → confirm the folder index renders at `/materials/`.
  6. Click a folder → confirm the folder viewer at `/materials/{fp}` still works.

  Option B (local dev host, no docker):
  ```
  python3 -m uvicorn findajob.web.app:default_app --factory --reload --port 8090
  ```
  Repeat the browser clicks above against `http://localhost:8090`.

- [ ] **Step 4: Open the PR.**
  ```
  gh pr create --title "feat(web): foundation — top nav + /materials move + routes/ package split (#60)" --body "$(cat <<'EOF'
  ## Summary
  - New top nav with 7 feature groups; landing page at `/` showing stage counts.
  - Materials folder index moved from `/` to `/materials/`. Deep links unchanged.
  - `routes.py` split into `routes/` package (`materials.py`, `healthz.py`, `landing.py`, `board.py`).
  - Tailwind + HTMX loaded from CDN in `base.html`; `static/app.css` holds Sheet-palette design tokens.
  - Placeholder pages for `/board/`, `/ingest/`, `/tools/`, `/config/`, `/docs/`.
  
  PR 1 of 2 for #60. PR 2 (board pages) follows after merge.
  
  Spec: `docs/superpowers/specs/2026-04-21-web-frontend-14b-design.md`.
  Plan: `docs/superpowers/plans/2026-04-21-web-frontend-14b.md`.
  
  ## Test plan
  - [ ] Full pytest suite green (including `test_web_nav.py`, `test_web_landing.py`, `test_web_routes_package.py`)
  - [ ] Ruff + mypy clean on `src/findajob/web/`
  - [ ] Manual smoke against docker.lan (or local uvicorn): landing shows stage counts, every nav link renders, `/materials/` index and `/materials/{fp}` folder viewer both work
  
  No `migration-required` — operators pull `:latest` and the new UI appears with no manual steps.
  EOF
  )"
  ```

- [ ] **Step 5: Monitor CI.** Wait for `ci.yml` green. If it fails, fix, push, repeat.

- [ ] **Step 6: After CI green, squash-merge when ready.**

---

# PR 2 — Board pages

## Task 10: Create PR 2 feature branch off post-merge `origin/main`

- [ ] **Step 1:** Ensure PR 1 has merged.
  ```
  git fetch origin
  git log origin/main --oneline | head -3
  ```
  Expected: top commit is the PR 1 merge.

- [ ] **Step 2:** Create PR 2 branch.
  ```
  git checkout -b feat/60-web-board origin/main
  ```

- [ ] **Step 3:** Confirm baseline tests pass.
  ```
  python3 -m pytest tests/test_web_app.py tests/test_web_routes.py tests/test_web_nav.py tests/test_web_landing.py -q
  ```
  Expected: all pass.

---

## Task 11: Shared constants module + sync_sheet.py refactor

**Files:**
- Create: `src/findajob/web/constants.py`
- Modify: `scripts/sync_sheet.py` (import `FOLDER_STAGES`)
- Modify: `tests/test_sync_sheet.py` (if imports changed)

- [ ] **Step 1: Write a failing test that both call sites import from the same source.**
  Create `tests/test_web_constants.py`:
  ```python
  """FOLDER_STAGES is the single source of truth for which stages have prep folders."""
  from findajob.web.constants import FOLDER_STAGES


  def test_folder_stages_is_frozen_tuple() -> None:
      assert isinstance(FOLDER_STAGES, tuple)
      expected = {
          "materials_drafted",
          "prep_in_progress",
          "applied",
          "interview",
          "offer",
          "waitlisted",
          "rejected",
          "not_selected",
      }
      assert set(FOLDER_STAGES) == expected


  def test_sync_sheet_uses_shared_constant() -> None:
      import scripts.sync_sheet as s  # noqa: WPS433
      # The hyperlink helper reads from the shared constant
      assert set(getattr(s, "_FOLDER_STAGES", set())) == set(FOLDER_STAGES) or \
          set(getattr(s, "FOLDER_STAGES", set())) == set(FOLDER_STAGES)
  ```

- [ ] **Step 2: Run — expect ImportError.**
  ```
  python3 -m pytest tests/test_web_constants.py -v
  ```
  Expected: FAIL (`findajob.web.constants` doesn't exist).

- [ ] **Step 3: Create `src/findajob/web/constants.py`.**
  ```python
  """Shared constants for the web app and call sites that need to mirror it."""

  FOLDER_STAGES: tuple[str, ...] = (
      "materials_drafted",
      "prep_in_progress",
      "applied",
      "interview",
      "offer",
      "waitlisted",
      "rejected",
      "not_selected",
  )
  """Stages for which a job has a prep folder on disk.
  Used by:
    - scripts/sync_sheet.py::_materials_company_cell — decides hyperlink vs plain text
    - src/findajob/web/templates/_job_row.html — same decision, rendered server-side
  Keep these two call sites in lockstep by importing from here, never hard-coding.
  """
  ```

- [ ] **Step 4: Refactor `scripts/sync_sheet.py`** — locate the function that decides hyperlink vs plain text for the company cell (added in #130). Replace the hard-coded stage tuple with an import:
  ```python
  from findajob.web.constants import FOLDER_STAGES
  ```
  and use `FOLDER_STAGES` in the stage check.

- [ ] **Step 5: Run tests.**
  ```
  python3 -m pytest tests/test_web_constants.py tests/test_sync_sheet.py -v
  ```
  Expected: all pass.

- [ ] **Step 6: Commit.**
  ```
  git add src/findajob/web/constants.py scripts/sync_sheet.py tests/test_web_constants.py
  git commit -m "refactor(web): extract FOLDER_STAGES into shared constants module (#60)"
  ```

---

## Task 12: Shared `_job_row.html` partial with conditional formatting + age classifier

**Files:**
- Create: `src/findajob/web/templates/_job_row.html`
- Create: `src/findajob/web/helpers.py` (`applied_age_bucket`, `stage_row_class`, `remote_cell_class`)
- Create: `tests/test_web_board_formatting.py`

- [ ] **Step 1: Write failing tests for the classifier functions.**
  Create `tests/test_web_board_formatting.py`:
  ```python
  """Conditional-formatting helpers for board rows."""
  from datetime import datetime, timezone, timedelta

  import pytest

  from findajob.web.helpers import applied_age_bucket, remote_cell_class, stage_row_class


  def _iso_days_ago(n: int) -> str:
      return (datetime.now(timezone.utc) - timedelta(days=n)).isoformat()


  @pytest.mark.parametrize("days,expected", [
      (0, "row-applied-fresh"),
      (6, "row-applied-fresh"),
      (7, "row-applied-week"),
      (13, "row-applied-week"),
      (14, "row-applied-stale"),
      (20, "row-applied-stale"),
      (21, "row-applied-cold"),
      (90, "row-applied-cold"),
  ])
  def test_applied_age_bucket(days: int, expected: str) -> None:
      assert applied_age_bucket(_iso_days_ago(days)) == expected


  def test_applied_age_bucket_none_returns_empty() -> None:
      assert applied_age_bucket(None) == ""


  @pytest.mark.parametrize("stage,expected", [
      ("offer", "row-offer"),
      ("interview", "row-interviewing"),
      ("applied", ""),
      ("scored", ""),
  ])
  def test_stage_row_class(stage: str, expected: str) -> None:
      assert stage_row_class(stage) == expected


  @pytest.mark.parametrize("remote,expected_contains", [
      ("Remote", "text-green"),
      ("Hybrid", "text-amber"),
      ("On-site", "text-slate"),
      ("", ""),
      (None, ""),
  ])
  def test_remote_cell_class(remote: str | None, expected_contains: str) -> None:
      result = remote_cell_class(remote)
      if expected_contains:
          assert expected_contains in result
      else:
          assert result == ""
  ```

- [ ] **Step 2: Run — expect ImportError.**
  ```
  python3 -m pytest tests/test_web_board_formatting.py -v
  ```

- [ ] **Step 3: Create `src/findajob/web/helpers.py`.**
  ```python
  """Pure helpers for board-row conditional formatting."""
  from __future__ import annotations

  from datetime import datetime, timezone


  def applied_age_bucket(applied_date_iso: str | None) -> str:
      if not applied_date_iso:
          return ""
      try:
          dt = datetime.fromisoformat(applied_date_iso.replace("Z", "+00:00"))
      except (TypeError, ValueError):
          return ""
      if dt.tzinfo is None:
          dt = dt.replace(tzinfo=timezone.utc)
      age_days = (datetime.now(timezone.utc) - dt).days
      if age_days <= 6:
          return "row-applied-fresh"
      if age_days <= 13:
          return "row-applied-week"
      if age_days <= 20:
          return "row-applied-stale"
      return "row-applied-cold"


  def stage_row_class(stage: str | None) -> str:
      if stage == "offer":
          return "row-offer"
      if stage == "interview":
          return "row-interviewing"
      return ""


  def remote_cell_class(remote_status: str | None) -> str:
      if not remote_status:
          return ""
      s = remote_status.strip().lower()
      if "remote" in s and "hybrid" not in s:
          return "text-green-700"
      if "hybrid" in s:
          return "text-amber-700"
      return "text-slate-600"
  ```

- [ ] **Step 4: Re-run helper tests.**
  ```
  python3 -m pytest tests/test_web_board_formatting.py -v
  ```
  Expected: PASS.

- [ ] **Step 5: Create `src/findajob/web/templates/_job_row.html`.**
  ```html
  {#
    Shared row partial for board tables. Inputs:
      row — a mapping with fields for the current tab's column list (see routes/board.py)
      columns — list of (display_name, field_name) tuples to render in order
      tab — "dashboard" | "applied" | "review" | "waitlist" | "archive"
      materials_base_url — optional URL for the materials viewer
    Applies tab-specific conditional formatting via findajob.web.helpers.
  #}
  {% set row_classes = [] %}
  {% if tab == "applied" %}
    {% set age_class = applied_age_bucket(row.applied_date) %}
    {% if age_class %}{% set _ = row_classes.append(age_class) %}{% endif %}
    {% set stage_class = stage_row_class(row.stage) %}
    {% if stage_class %}{% set _ = row_classes.append(stage_class) %}{% endif %}
  {% endif %}
  <tr class="{{ row_classes | join(' ') }}" data-fingerprint="{{ row.fingerprint }}">
    {% for display, field in columns %}
      <td class="px-3 py-1 align-top text-sm
                 {% if field == 'known_contacts' and row[field] %}cell-contact-amber{% endif %}
                 {% if field == 'remote' %}{{ remote_cell_class(row[field]) }}{% endif %}">
        {% if field == 'company' and tab == 'applied' and row.fingerprint and row.stage in folder_stages and materials_base_url %}
          <a class="underline" href="{{ materials_base_url }}/materials/{{ row.fingerprint }}">{{ row[field] }}</a>
        {% else %}
          {{ row[field] }}
        {% endif %}
      </td>
    {% endfor %}
  </tr>
  ```

- [ ] **Step 6: Wire helpers and FOLDER_STAGES into the Jinja environment.**
  In `src/findajob/web/app.py::create_app`, after `templates = Jinja2Templates(...)`, add:
  ```python
  from findajob.web.constants import FOLDER_STAGES
  from findajob.web.helpers import applied_age_bucket, remote_cell_class, stage_row_class

  templates.env.globals["folder_stages"] = set(FOLDER_STAGES)
  templates.env.globals["applied_age_bucket"] = applied_age_bucket
  templates.env.globals["remote_cell_class"] = remote_cell_class
  templates.env.globals["stage_row_class"] = stage_row_class
  ```

- [ ] **Step 7: Commit.**
  ```
  git add src/findajob/web/helpers.py src/findajob/web/templates/_job_row.html src/findajob/web/app.py tests/test_web_board_formatting.py
  git commit -m "feat(web): shared _job_row partial + conditional-formatting helpers (#60)"
  ```

---

## Task 13: `/board/dashboard` route + template

**Files:**
- Modify: `src/findajob/web/routes/board.py`
- Modify: `src/findajob/web/routes/landing.py` (drop `/board/` placeholder)
- Create: `src/findajob/web/templates/board/dashboard.html`
- Create: `tests/test_web_board_dashboard.py`

- [ ] **Step 1: Write failing test.**
  Create `tests/test_web_board_dashboard.py`:
  ```python
  """Board Dashboard tab."""
  import sqlite3
  from pathlib import Path

  import pytest
  from fastapi.testclient import TestClient

  from findajob.web.app import create_app


  @pytest.fixture
  def client(tmp_path: Path) -> TestClient:
      db = tmp_path / "pipeline.db"
      conn = sqlite3.connect(db)
      conn.execute(
          "CREATE TABLE jobs (fingerprint TEXT, title TEXT, company TEXT, stage TEXT, "
          "fit_score REAL, probability_score REAL, relevance_score INTEGER, "
          "location TEXT, remote_status TEXT, known_contacts TEXT, comp_estimate TEXT, "
          "ai_notes TEXT, created_at TEXT, stage_updated TEXT)"
      )
      # In scope: fit_score>=7 AND stage IN scored/manual_review; OR stage in prep_in_progress/materials_drafted
      conn.execute("INSERT INTO jobs (fingerprint, title, company, stage, fit_score) VALUES ('fp1','Senior DC Ops','Meta','scored',7.5)")
      conn.execute("INSERT INTO jobs (fingerprint, title, company, stage, fit_score) VALUES ('fp2','NPI PM','Google','materials_drafted',8.0)")
      # Out of scope: low score
      conn.execute("INSERT INTO jobs (fingerprint, title, company, stage, fit_score) VALUES ('fp3','Junior','Acme','scored',3.0)")
      conn.commit()
      conn.close()
      companies = tmp_path / "companies"
      companies.mkdir()
      return TestClient(create_app(companies_root=companies, db_path=db))


  def test_dashboard_shows_in_scope_jobs(client: TestClient) -> None:
      r = client.get("/board/dashboard")
      assert r.status_code == 200
      assert "Senior DC Ops" in r.text
      assert "NPI PM" in r.text
      assert "Junior" not in r.text  # filtered out by score<7
  ```

- [ ] **Step 2: Run — expect 200 with 'Coming soon' (stale placeholder); FAIL on assertion.**

- [ ] **Step 3: Drop the `/board/` placeholder from `routes/landing.py`'s `_PLACEHOLDERS` tuple list.** Remove the `("/board/", "Board", ...)` entry.

- [ ] **Step 4: Add Dashboard handler to `routes/board.py`.**
  ```python
  """Board tabs: /board/dashboard, /applied, /review, /waitlist, /archive."""
  from __future__ import annotations

  import os
  import sqlite3

  from fastapi import APIRouter, Depends, Query, Request
  from fastapi.responses import HTMLResponse

  from findajob.web.routes.materials import get_db

  router = APIRouter()

  _DASHBOARD_COLS = [
      ("Score",      "fit_score"),
      ("Prob",       "probability_score"),
      ("Rel",        "relevance_score"),
      ("Title",      "title"),
      ("Company",    "company"),
      ("Location",   "location"),
      ("Remote",     "remote_status"),
      ("Contacts",   "known_contacts"),
      ("Comp",       "comp_estimate"),
      ("Notes",      "ai_notes"),
      ("Date",       "created_at"),
  ]

  _DASHBOARD_SORTABLE = {c for _, c in _DASHBOARD_COLS}
  _DASHBOARD_DEFAULT_SORT = "fit_score"

  _DASHBOARD_WHERE = (
      "(fit_score >= 7 AND stage IN ('scored','manual_review')) "
      "OR stage IN ('prep_in_progress','materials_drafted')"
  )


  @router.get("/board/dashboard", response_class=HTMLResponse)
  def dashboard(
      request: Request,
      sort: str = Query(default=""),
      desc: int = Query(default=1),
      db: sqlite3.Connection = Depends(get_db),  # noqa: B008
  ) -> HTMLResponse:
      sort_col = sort if sort in _DASHBOARD_SORTABLE else _DASHBOARD_DEFAULT_SORT
      order = "DESC" if desc else "ASC"
      rows = db.execute(
          f"SELECT fingerprint, title, company, location, remote_status, known_contacts, "
          f"comp_estimate, ai_notes, fit_score, probability_score, relevance_score, "
          f"stage, created_at, stage_updated FROM jobs WHERE {_DASHBOARD_WHERE} "
          f"ORDER BY {sort_col} {order}"
      ).fetchall()
      materials_base_url = os.environ.get("FINDAJOB_MATERIALS_BASE_URL", "")
      templates = request.app.state.templates
      return templates.TemplateResponse(
          request=request,
          name="board/dashboard.html",
          context={
              "columns": _DASHBOARD_COLS,
              "rows": rows,
              "sort": sort_col,
              "desc": desc,
              "tab": "dashboard",
              "materials_base_url": materials_base_url,
          },
      )
  ```

- [ ] **Step 5: Create `src/findajob/web/templates/board/dashboard.html`.**
  ```html
  {% extends "base.html" %}
  {% block title %}Dashboard — findajob{% endblock %}
  {% block content %}
  <h1 class="text-2xl font-semibold mb-4">Dashboard</h1>
  {% include "_filters.html" ignore missing %}
  <table class="min-w-full bg-white shadow-sm rounded-sm">
    <thead class="bg-slate-100 text-left text-xs uppercase tracking-wide text-slate-600">
      <tr>
        {% for display, field in columns %}
        <th class="px-3 py-2">
          <a href="?sort={{ field }}&desc={% if sort == field and desc %}0{% else %}1{% endif %}">
            {{ display }}{% if sort == field %}{% if desc %} ▼{% else %} ▲{% endif %}{% endif %}
          </a>
        </th>
        {% endfor %}
      </tr>
    </thead>
    <tbody id="rows">
      {% for row in rows %}
        {% include "_job_row.html" %}
      {% else %}
        <tr><td colspan="{{ columns|length }}" class="px-3 py-4 text-slate-500">No jobs in this view right now.</td></tr>
      {% endfor %}
    </tbody>
  </table>
  {% endblock %}
  ```

- [ ] **Step 6: Run test.**
  ```
  python3 -m pytest tests/test_web_board_dashboard.py -v
  ```
  Expected: PASS.

- [ ] **Step 7: Commit.**
  ```
  git add src/findajob/web/routes/board.py src/findajob/web/routes/landing.py src/findajob/web/templates/board/dashboard.html tests/test_web_board_dashboard.py
  git commit -m "feat(web): /board/dashboard route + template (#60)"
  ```

---

## Task 14: `/board/applied` route with `applied_date` audit_log lookup

**Files:**
- Modify: `src/findajob/web/routes/board.py`
- Create: `src/findajob/web/templates/board/applied.html`
- Create: `tests/test_web_board_applied.py`

- [ ] **Step 1: Write failing test.**
  Create `tests/test_web_board_applied.py`:
  ```python
  """Board Applied tab — reads applied_date from audit_log, renders materials link."""
  import sqlite3
  from datetime import datetime, timezone, timedelta
  from pathlib import Path

  import pytest
  from fastapi.testclient import TestClient

  from findajob.web.app import create_app


  @pytest.fixture
  def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
      monkeypatch.setenv("FINDAJOB_MATERIALS_BASE_URL", "http://test:8090")
      db = tmp_path / "pipeline.db"
      conn = sqlite3.connect(db)
      conn.execute(
          "CREATE TABLE jobs (fingerprint TEXT, title TEXT, company TEXT, stage TEXT, "
          "location TEXT, remote_status TEXT, known_contacts TEXT, comp_estimate TEXT, "
          "ai_notes TEXT, user_notes TEXT, created_at TEXT, stage_updated TEXT)"
      )
      conn.execute(
          "CREATE TABLE audit_log (id INTEGER PRIMARY KEY, job_id TEXT, field_changed TEXT, "
          "old_value TEXT, new_value TEXT, changed_at TEXT, changed_by TEXT)"
      )
      ten_days_ago = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
      conn.execute("INSERT INTO jobs (fingerprint, title, company, stage) VALUES ('fp-app','Eng Mgr','Anthropic','applied')")
      conn.execute(
          "INSERT INTO audit_log (job_id, field_changed, old_value, new_value, changed_at, changed_by) "
          "VALUES ('fp-app','stage','materials_drafted','applied',?,'system')",
          (ten_days_ago,),
      )
      conn.commit()
      conn.close()
      companies = tmp_path / "companies"
      companies.mkdir()
      return TestClient(create_app(companies_root=companies, db_path=db))


  def test_applied_shows_row_with_age_class(client: TestClient) -> None:
      r = client.get("/board/applied")
      assert r.status_code == 200
      assert "Eng Mgr" in r.text
      assert "Anthropic" in r.text
      # 10-day-old row → yellow bucket
      assert "row-applied-week" in r.text
      # Materials link uses FINDAJOB_MATERIALS_BASE_URL
      assert 'href="http://test:8090/materials/fp-app"' in r.text
  ```

- [ ] **Step 2: Run — expect 404.**

- [ ] **Step 3: Add the handler to `routes/board.py`** (append):
  ```python
  _APPLIED_COLS = [
      ("Title",     "title"),
      ("Company",   "company"),
      ("Applied",   "applied_date"),
      ("Days",      "days_since_applied"),
      ("Stage",     "stage"),
      ("Notes",     "user_notes"),
      ("Contacts",  "known_contacts"),
      ("Location",  "location"),
      ("Remote",    "remote_status"),
      ("Comp",      "comp_estimate"),
      ("AI notes",  "ai_notes"),
  ]
  _APPLIED_SORTABLE = {c for _, c in _APPLIED_COLS if c not in {"applied_date", "days_since_applied"}} | {"applied_date"}
  _APPLIED_DEFAULT_SORT = "applied_date"


  @router.get("/board/applied", response_class=HTMLResponse)
  def applied(
      request: Request,
      sort: str = Query(default=""),
      desc: int = Query(default=1),
      db: sqlite3.Connection = Depends(get_db),  # noqa: B008
  ) -> HTMLResponse:
      sort_col = sort if sort in _APPLIED_SORTABLE else _APPLIED_DEFAULT_SORT
      order = "DESC" if desc else "ASC"
      # applied_date = earliest audit_log transition to 'applied' for each job
      sql = f"""
      SELECT j.fingerprint, j.title, j.company, j.stage, j.location, j.remote_status,
             j.known_contacts, j.comp_estimate, j.ai_notes, j.user_notes, j.created_at,
             al.applied_date,
             CAST((julianday('now') - julianday(al.applied_date)) AS INTEGER) AS days_since_applied
      FROM jobs j
      LEFT JOIN (
        SELECT job_id, MIN(changed_at) AS applied_date
        FROM audit_log
        WHERE field_changed = 'stage' AND new_value = 'applied'
        GROUP BY job_id
      ) al ON al.job_id = j.fingerprint OR al.job_id = j.rowid
      WHERE j.stage IN ('applied','interview','offer')
      ORDER BY {sort_col} {order}
      """
      rows = db.execute(sql).fetchall()
      import os
      materials_base_url = os.environ.get("FINDAJOB_MATERIALS_BASE_URL", "")
      templates = request.app.state.templates
      return templates.TemplateResponse(
          request=request,
          name="board/applied.html",
          context={
              "columns": _APPLIED_COLS,
              "rows": rows,
              "sort": sort_col,
              "desc": desc,
              "tab": "applied",
              "materials_base_url": materials_base_url,
          },
      )
  ```
  NOTE: `audit_log.job_id` may point at `jobs.id` (a UUID) rather than `jobs.fingerprint`; the LEFT JOIN tries both. In production the join column is `jobs.id`. Confirm by running the verification-gate query against the real DB; adjust if needed.

- [ ] **Step 4: Create `src/findajob/web/templates/board/applied.html`.**
  Copy `board/dashboard.html` verbatim; change the `<h1>` text to "Applied".

- [ ] **Step 5: Run test.**
  ```
  python3 -m pytest tests/test_web_board_applied.py -v
  ```
  Expected: PASS.

- [ ] **Step 6: Commit.**
  ```
  git add src/findajob/web/routes/board.py src/findajob/web/templates/board/applied.html tests/test_web_board_applied.py
  git commit -m "feat(web): /board/applied with audit_log applied_date lookup and materials link (#60)"
  ```

---

## Task 15: `/board/review` and `/board/waitlist` routes

**Files:**
- Modify: `src/findajob/web/routes/board.py`
- Create: `src/findajob/web/templates/board/review.html`
- Create: `src/findajob/web/templates/board/waitlist.html`
- Create: `tests/test_web_board_review.py`
- Create: `tests/test_web_board_waitlist.py`

- [ ] **Step 1: Write failing tests** (one file each, mirroring the dashboard test structure; Review asserts jobs with `stage='manual_review'` appear and others don't; Waitlist asserts `stage='waitlisted'` jobs appear and the computed `blocking_app` column renders).

- [ ] **Step 2: Run — expect 404.**

- [ ] **Step 3: Add handlers to `routes/board.py`.**
  ```python
  _REVIEW_COLS = [
      ("Title",      "title"),
      ("Company",    "company"),
      ("Flag reason","score_flag_reason"),
      ("Source",     "source"),
      ("Date",       "created_at"),
  ]
  _REVIEW_SORTABLE = {c for _, c in _REVIEW_COLS}
  _REVIEW_DEFAULT_SORT = "created_at"


  @router.get("/board/review", response_class=HTMLResponse)
  def review(request: Request, sort: str = Query(default=""), desc: int = Query(default=1),
             db: sqlite3.Connection = Depends(get_db)) -> HTMLResponse:  # noqa: B008
      sort_col = sort if sort in _REVIEW_SORTABLE else _REVIEW_DEFAULT_SORT
      order = "DESC" if desc else "ASC"
      rows = db.execute(
          f"SELECT fingerprint, title, company, score_flag_reason, source, created_at, stage "
          f"FROM jobs WHERE stage = 'manual_review' ORDER BY {sort_col} {order}"
      ).fetchall()
      import os
      templates = request.app.state.templates
      return templates.TemplateResponse(
          request=request, name="board/review.html",
          context={"columns": _REVIEW_COLS, "rows": rows, "sort": sort_col, "desc": desc,
                   "tab": "review", "materials_base_url": os.environ.get("FINDAJOB_MATERIALS_BASE_URL", "")},
      )


  _WAITLIST_COLS = [
      ("Title",        "title"),
      ("Company",      "company"),
      ("Rel",          "relevance_score"),
      ("Location",     "location"),
      ("Remote",       "remote_status"),
      ("AI notes",     "ai_notes"),
      ("Date",         "created_at"),
      ("Blocking app", "blocking_app"),
  ]
  _WAITLIST_SORTABLE = {c for _, c in _WAITLIST_COLS if c != "blocking_app"}
  _WAITLIST_DEFAULT_SORT = "created_at"


  @router.get("/board/waitlist", response_class=HTMLResponse)
  def waitlist(request: Request, sort: str = Query(default=""), desc: int = Query(default=1),
               db: sqlite3.Connection = Depends(get_db)) -> HTMLResponse:  # noqa: B008
      sort_col = sort if sort in _WAITLIST_SORTABLE else _WAITLIST_DEFAULT_SORT
      order = "DESC" if desc else "ASC"
      # blocking_app = for each waitlisted job, find the most recent active application at the same company (excluding this job)
      sql = f"""
      SELECT w.fingerprint, w.title, w.company, w.relevance_score, w.location, w.remote_status,
             w.ai_notes, w.created_at, w.stage,
             (SELECT j2.title || ' (' || j2.stage || ')'
                FROM jobs j2
               WHERE j2.company = w.company
                 AND j2.fingerprint != w.fingerprint
                 AND j2.stage IN ('applied','interview','offer','materials_drafted','prep_in_progress')
               ORDER BY j2.stage_updated DESC
               LIMIT 1) AS blocking_app
      FROM jobs w
      WHERE w.stage = 'waitlisted'
      ORDER BY {sort_col} {order}
      """
      rows = db.execute(sql).fetchall()
      import os
      templates = request.app.state.templates
      return templates.TemplateResponse(
          request=request, name="board/waitlist.html",
          context={"columns": _WAITLIST_COLS, "rows": rows, "sort": sort_col, "desc": desc,
                   "tab": "waitlist", "materials_base_url": os.environ.get("FINDAJOB_MATERIALS_BASE_URL", "")},
      )
  ```

- [ ] **Step 4: Create `review.html` and `waitlist.html`** (copy dashboard.html, change `<h1>`).

- [ ] **Step 5: Also drop the `/board/` placeholder from landing** (already done in Task 13; verify).

- [ ] **Step 6: Run tests.**
  ```
  python3 -m pytest tests/test_web_board_review.py tests/test_web_board_waitlist.py -v
  ```
  Expected: PASS.

- [ ] **Step 7: Commit.**
  ```
  git add src/findajob/web/routes/board.py src/findajob/web/templates/board/review.html src/findajob/web/templates/board/waitlist.html tests/test_web_board_review.py tests/test_web_board_waitlist.py
  git commit -m "feat(web): /board/review and /board/waitlist with blocking_app subquery (#60)"
  ```

---

## Task 16: `/board/archive` route + HTMX infinite scroll

**Files:**
- Modify: `src/findajob/web/routes/board.py`
- Create: `src/findajob/web/templates/board/archive.html`
- Create: `src/findajob/web/templates/board/_archive_rows.html`
- Create: `tests/test_web_board_archive.py`

- [ ] **Step 1: Write failing tests.**
  Create `tests/test_web_board_archive.py`:
  ```python
  """Archive tab: pagination, HTMX sentinel, filter."""
  import sqlite3
  from pathlib import Path

  import pytest
  from fastapi.testclient import TestClient

  from findajob.web.app import create_app


  @pytest.fixture
  def client(tmp_path: Path) -> TestClient:
      db = tmp_path / "pipeline.db"
      conn = sqlite3.connect(db)
      conn.execute(
          "CREATE TABLE jobs (fingerprint TEXT, title TEXT, company TEXT, stage TEXT, "
          "fit_score REAL, location TEXT, remote_status TEXT, source TEXT, url TEXT, "
          "created_at TEXT, stage_updated TEXT)"
      )
      # 150 rows for pagination test
      for i in range(150):
          conn.execute(
              "INSERT INTO jobs (fingerprint, title, company, stage, fit_score, created_at) "
              "VALUES (?, ?, ?, 'scored', ?, '2026-01-01')",
              (f"fp-{i:03}", f"Role {i}", f"Co {i}", 1.0 + i % 10),
          )
      conn.commit()
      conn.close()
      companies = tmp_path / "companies"
      companies.mkdir()
      return TestClient(create_app(companies_root=companies, db_path=db))


  def test_archive_first_page_100_rows_plus_sentinel(client: TestClient) -> None:
      r = client.get("/board/archive")
      assert r.status_code == 200
      assert r.text.count("<tr") >= 101  # 100 data rows + header row (+ possibly sentinel)
      assert "offset=100" in r.text


  def test_archive_second_page_via_rows_endpoint(client: TestClient) -> None:
      r = client.get("/board/archive/rows?offset=100")
      assert r.status_code == 200
      # Remaining 50 rows, no sentinel (end reached)
      assert r.text.count("<tr") == 50
      assert "offset=" not in r.text


  def test_archive_rows_endpoint_returns_fragment_not_full_page(client: TestClient) -> None:
      r = client.get("/board/archive/rows?offset=0")
      assert r.status_code == 200
      # No <html> / <body> — HTMX swaps a fragment
      assert "<body" not in r.text.lower()
  ```

- [ ] **Step 2: Run — expect 404.**

- [ ] **Step 3: Add archive handlers to `routes/board.py`.**
  ```python
  _ARCHIVE_COLS = [
      ("Score",    "fit_score"),
      ("Title",    "title"),
      ("Company",  "company"),
      ("Stage",    "stage"),
      ("Location", "location"),
      ("Remote",   "remote_status"),
      ("Date",     "created_at"),
      ("Source",   "source"),
      ("URL",      "url"),
  ]
  _ARCHIVE_SORTABLE = {c for _, c in _ARCHIVE_COLS}
  _ARCHIVE_DEFAULT_SORT = "created_at"
  _ARCHIVE_PAGE_SIZE = 100


  def _archive_select_sql(sort_col: str, order: str) -> str:
      return (
          "SELECT fingerprint, title, company, stage, fit_score, location, remote_status, "
          "source, url, created_at, stage_updated "
          f"FROM jobs ORDER BY {sort_col} {order} LIMIT ? OFFSET ?"
      )


  @router.get("/board/archive", response_class=HTMLResponse)
  def archive(request: Request, sort: str = Query(default=""), desc: int = Query(default=1),
              db: sqlite3.Connection = Depends(get_db)) -> HTMLResponse:  # noqa: B008
      sort_col = sort if sort in _ARCHIVE_SORTABLE else _ARCHIVE_DEFAULT_SORT
      order = "DESC" if desc else "ASC"
      rows = db.execute(_archive_select_sql(sort_col, order), (_ARCHIVE_PAGE_SIZE, 0)).fetchall()
      has_more = len(rows) == _ARCHIVE_PAGE_SIZE
      import os
      templates = request.app.state.templates
      return templates.TemplateResponse(
          request=request, name="board/archive.html",
          context={"columns": _ARCHIVE_COLS, "rows": rows, "sort": sort_col, "desc": desc,
                   "tab": "archive", "next_offset": _ARCHIVE_PAGE_SIZE if has_more else None,
                   "materials_base_url": os.environ.get("FINDAJOB_MATERIALS_BASE_URL", "")},
      )


  @router.get("/board/archive/rows", response_class=HTMLResponse)
  def archive_rows(request: Request, offset: int = Query(default=0),
                   sort: str = Query(default=""), desc: int = Query(default=1),
                   db: sqlite3.Connection = Depends(get_db)) -> HTMLResponse:  # noqa: B008
      sort_col = sort if sort in _ARCHIVE_SORTABLE else _ARCHIVE_DEFAULT_SORT
      order = "DESC" if desc else "ASC"
      rows = db.execute(_archive_select_sql(sort_col, order), (_ARCHIVE_PAGE_SIZE, offset)).fetchall()
      has_more = len(rows) == _ARCHIVE_PAGE_SIZE
      import os
      templates = request.app.state.templates
      return templates.TemplateResponse(
          request=request, name="board/_archive_rows.html",
          context={"columns": _ARCHIVE_COLS, "rows": rows, "tab": "archive",
                   "next_offset": offset + _ARCHIVE_PAGE_SIZE if has_more else None,
                   "sort": sort_col, "desc": desc,
                   "materials_base_url": os.environ.get("FINDAJOB_MATERIALS_BASE_URL", "")},
      )
  ```

- [ ] **Step 4: Create `board/archive.html`.**
  ```html
  {% extends "base.html" %}
  {% block title %}Archive — findajob{% endblock %}
  {% block content %}
  <h1 class="text-2xl font-semibold mb-4">Archive ({{ rows|length }}+)</h1>
  <table class="min-w-full bg-white shadow-sm rounded-sm">
    <thead class="bg-slate-100 text-left text-xs uppercase tracking-wide text-slate-600">
      <tr>
        {% for display, field in columns %}
        <th class="px-3 py-2">
          <a href="?sort={{ field }}&desc={% if sort == field and desc %}0{% else %}1{% endif %}">
            {{ display }}{% if sort == field %}{% if desc %} ▼{% else %} ▲{% endif %}{% endif %}
          </a>
        </th>
        {% endfor %}
      </tr>
    </thead>
    <tbody id="rows">
      {% include "board/_archive_rows.html" %}
    </tbody>
  </table>
  {% endblock %}
  ```

- [ ] **Step 5: Create `board/_archive_rows.html`.**
  ```html
  {% for row in rows %}
    {% include "_job_row.html" %}
  {% endfor %}
  {% if next_offset is not none %}
    <tr hx-get="/board/archive/rows?offset={{ next_offset }}&sort={{ sort }}&desc={{ desc }}"
        hx-trigger="revealed"
        hx-swap="outerHTML">
      <td colspan="{{ columns|length }}" class="px-3 py-2 text-xs text-slate-400">loading…</td>
    </tr>
  {% endif %}
  ```

- [ ] **Step 6: Run tests.**
  ```
  python3 -m pytest tests/test_web_board_archive.py -v
  ```
  Expected: PASS.

- [ ] **Step 7: Commit.**
  ```
  git add src/findajob/web/routes/board.py src/findajob/web/templates/board/archive.html src/findajob/web/templates/board/_archive_rows.html tests/test_web_board_archive.py
  git commit -m "feat(web): /board/archive with HTMX infinite-scroll pagination (#60)"
  ```

---

## Task 17: HTMX filter endpoint per tab

**Files:**
- Modify: `src/findajob/web/routes/board.py` (add `/board/<tab>/rows` endpoints for non-archive tabs)
- Create: `src/findajob/web/templates/_filters.html`
- Modify: each tab's template to include `_filters.html`
- Create: `tests/test_web_board_filter.py`

- [ ] **Step 1: Write failing test.**
  ```python
  # tests/test_web_board_filter.py
  import sqlite3
  from pathlib import Path

  import pytest
  from fastapi.testclient import TestClient

  from findajob.web.app import create_app


  @pytest.fixture
  def client(tmp_path: Path) -> TestClient:
      db = tmp_path / "pipeline.db"
      conn = sqlite3.connect(db)
      conn.execute(
          "CREATE TABLE jobs (fingerprint TEXT, title TEXT, company TEXT, stage TEXT, "
          "fit_score REAL, location TEXT, remote_status TEXT, known_contacts TEXT, "
          "comp_estimate TEXT, ai_notes TEXT, created_at TEXT, stage_updated TEXT, "
          "probability_score REAL, relevance_score INTEGER)"
      )
      for fp, title, company in [
          ("fp1", "NPI PM", "Meta"),
          ("fp2", "Staff Eng", "Anthropic"),
          ("fp3", "TPM", "Meta"),
      ]:
          conn.execute(
              "INSERT INTO jobs (fingerprint, title, company, stage, fit_score) "
              "VALUES (?, ?, ?, 'scored', 8.0)",
              (fp, title, company),
          )
      conn.commit()
      conn.close()
      companies = tmp_path / "companies"
      companies.mkdir()
      return TestClient(create_app(companies_root=companies, db_path=db))


  def test_dashboard_filter_narrows_by_company(client: TestClient) -> None:
      r = client.get("/board/dashboard/rows?q=meta")
      assert r.status_code == 200
      assert "NPI PM" in r.text
      assert "TPM" in r.text
      assert "Staff Eng" not in r.text


  def test_filter_fragment_has_no_body_tag(client: TestClient) -> None:
      r = client.get("/board/dashboard/rows?q=")
      assert r.status_code == 200
      assert "<body" not in r.text.lower()
  ```

- [ ] **Step 2: Run — expect 404.**

- [ ] **Step 3: Add filter endpoints to `routes/board.py`.** The pattern: each tab's main handler gets a sibling `/<tab>/rows` endpoint that accepts `q` (filter text), runs the same base WHERE plus `AND (title LIKE ? COLLATE NOCASE OR company LIKE ? COLLATE NOCASE)` when `q` is non-empty, and renders only the rows fragment.
  Add a helper:
  ```python
  def _filter_clause(q: str) -> tuple[str, list[str]]:
      if not q:
          return "", []
      like = f"%{q}%"
      return " AND (title LIKE ? COLLATE NOCASE OR company LIKE ? COLLATE NOCASE)", [like, like]
  ```
  Then for each of Dashboard/Applied/Review/Waitlist add an endpoint:
  ```python
  @router.get("/board/dashboard/rows", response_class=HTMLResponse)
  def dashboard_rows(request: Request, q: str = Query(default=""),
                     sort: str = Query(default=""), desc: int = Query(default=1),
                     db: sqlite3.Connection = Depends(get_db)) -> HTMLResponse:  # noqa: B008
      sort_col = sort if sort in _DASHBOARD_SORTABLE else _DASHBOARD_DEFAULT_SORT
      order = "DESC" if desc else "ASC"
      filter_sql, params = _filter_clause(q)
      rows = db.execute(
          f"SELECT fingerprint, title, company, location, remote_status, known_contacts, "
          f"comp_estimate, ai_notes, fit_score, probability_score, relevance_score, "
          f"stage, created_at, stage_updated FROM jobs WHERE ({_DASHBOARD_WHERE}) {filter_sql} "
          f"ORDER BY {sort_col} {order}",
          params,
      ).fetchall()
      import os
      templates = request.app.state.templates
      return templates.TemplateResponse(
          request=request, name="_job_rows_fragment.html",
          context={"columns": _DASHBOARD_COLS, "rows": rows, "tab": "dashboard",
                   "materials_base_url": os.environ.get("FINDAJOB_MATERIALS_BASE_URL", "")},
      )
  ```
  Mirror this for applied/review/waitlist, each with its own WHERE base and columns.

- [ ] **Step 4: Create shared fragment template `src/findajob/web/templates/_job_rows_fragment.html`.**
  ```html
  {% for row in rows %}
    {% include "_job_row.html" %}
  {% else %}
    <tr><td colspan="{{ columns|length }}" class="px-3 py-4 text-slate-500">No matches.</td></tr>
  {% endfor %}
  ```

- [ ] **Step 5: Create `_filters.html`.**
  ```html
  <form class="mb-3">
    <input type="text" name="q" placeholder="Filter by title or company..."
           class="border border-slate-300 rounded px-3 py-1 w-full md:w-1/3"
           hx-get="{{ request.url.path }}/rows"
           hx-trigger="keyup changed delay:200ms"
           hx-target="#rows"
           hx-swap="innerHTML"
           hx-include="[name='sort'],[name='desc']">
  </form>
  ```

- [ ] **Step 6: Run test.**
  ```
  python3 -m pytest tests/test_web_board_filter.py -v
  ```
  Expected: PASS.

- [ ] **Step 7: Commit.**
  ```
  git add src/findajob/web/routes/board.py src/findajob/web/templates/_filters.html src/findajob/web/templates/_job_rows_fragment.html tests/test_web_board_filter.py
  git commit -m "feat(web): HTMX filter per board tab via /board/<tab>/rows (#60)"
  ```

---

## Task 18: Sort smoke test across all tabs

**Files:**
- Create: `tests/test_web_board_sort.py`

- [ ] **Step 1: Write a parametrized test.**
  ```python
  """Sort via ?sort=<col>&desc=<0|1> works for each tab."""
  import pytest

  # Reuse the dashboard fixture pattern, extend to all tabs.
  # Insert 3 rows with distinct fit_score values; assert order reflects ?sort=fit_score&desc=1.
  # Repeat for the other tabs with their default sort columns.
  # ...
  ```
  Implementation mirrors previous tests; omit here for brevity but the test file must be complete — no placeholders.

- [ ] **Step 2: Run — expect PASS against the already-shipped sort handling.** If any tab fails, fix in `routes/board.py`.

- [ ] **Step 3: Commit.**
  ```
  git add tests/test_web_board_sort.py
  git commit -m "test(web): sort behavior across board tabs (#60)"
  ```

---

## Task 19: Board-level docs updates

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `docs/setup/install-docker.md`
- Modify: `CLAUDE.md`
- Modify: `docs/roadmap.md` (if present and tracks 14b)

- [ ] **Step 1:** Append to `CHANGELOG.md` [Unreleased] `### Added`:
  ```markdown
  - `/board/dashboard`, `/board/applied`, `/board/review`, `/board/waitlist`, `/board/archive` render the same content as the corresponding Google Sheet tabs, directly from the database. Archive page covers all 10,881+ jobs with HTMX infinite-scroll pagination (obsoleting Sheet1's archival filter). `sync_sheet.py` keeps updating Sheets in parallel during the 14b → 14c → 14d migration (#60).
  ```

- [ ] **Step 2:** Append a "Board pages" paragraph to `docs/setup/install-docker.md` in the Materials viewer section:
  ```markdown
  The viewer also serves five board pages under `/board/`: Dashboard, Applied, Review, Waitlist, Archive. These mirror the Google Sheet tabs, reading the same database. Use whichever surface you prefer; the Sheet and the web UI stay in sync because both read `state/data/pipeline.db`.
  ```

- [ ] **Step 3:** In `CLAUDE.md` §"Google Sheet Architecture", add at the top:
  ```markdown
  > The web UI at `/board/*` renders the same column sets directly from the database. `sync_sheet.py` and the web UI both read `state/data/pipeline.db`. `sync_sheet.py` will be retired in 14d (#14).
  ```

- [ ] **Step 4:** If `docs/roadmap.md` tracks 14b, check off the 14b milestone.

- [ ] **Step 5:** Commit.
  ```
  git add CHANGELOG.md docs/setup/install-docker.md CLAUDE.md docs/roadmap.md
  git commit -m "docs(60): board pages shipped — /board/* mirrors the Sheet"
  ```

---

## Task 20: PR 2 whole-feature verification + open PR

- [ ] **Step 1:** Full pytest, ruff, mypy.
  ```
  python3 -m pytest -q
  python3 -m ruff check src/findajob/web/ scripts/sync_sheet.py tests/
  python3 -m ruff format --check src/findajob/web/ tests/
  python3 -m mypy src/findajob/web/
  ```

- [ ] **Step 2:** Smoke against a copy of the real DB.
  Copy `state/data/pipeline.db` from docker.lan to a local path, run uvicorn pointing at it, then:
  1. Click every `/board/*` tab — confirm row counts match the current Google Sheet.
  2. Click a company cell on Applied — confirm the materials folder opens.
  3. Type "meta" in the Dashboard filter box — confirm narrowing happens live.
  4. Scroll the Archive page — confirm infinite scroll loads additional rows.
  5. Sort by clicking a column header — confirm the page reloads with rows in the new order.

- [ ] **Step 3:** Open the PR.
  ```
  gh pr create --title "feat(web): board pages — dashboard, applied, review, waitlist, archive (#60)" --body "$(cat <<'EOF'
  ## Summary
  - Five board pages under `/board/` reproducing the Google Sheet's Dashboard, Applied, Review, Waitlist, and a new Archive view.
  - Archive replaces Sheet1's archival filter with proper pagination (100/page, HTMX infinite scroll). Shows every job in the DB.
  - HTMX filter per tab (`?q=<text>` against title + company).
  - URL-param sort (`?sort=<col>&desc=<0|1>`); column headers toggle direction.
  - Conditional formatting matches the Sheet: Applied row-age buckets, Offer gold, Interviewing purple, contacts amber.
  - Applied tab's company cell hyperlinks into `/materials/{fp}` when the job has a folder. Folder-stage list extracted to `findajob.web.constants.FOLDER_STAGES`; `sync_sheet.py` now imports from there.
  
  PR 2 of 2 for #60.
  
  Spec: `docs/superpowers/specs/2026-04-21-web-frontend-14b-design.md`.
  Plan: `docs/superpowers/plans/2026-04-21-web-frontend-14b.md`.
  
  ## Test plan
  - [ ] Full pytest suite green (new: dashboard, applied, review, waitlist, archive, filter, sort, formatting)
  - [ ] Ruff + mypy clean
  - [ ] Smoke against docker.lan DB copy: tab row counts match Sheet, materials link opens folder, filter narrows live, archive paginates
  
  No `migration-required` — foundation landed in PR 1; board pages appear on `:latest` with no manual steps.
  EOF
  )"
  ```

- [ ] **Step 4:** Monitor CI. Squash-merge when green.

---

# Documentation Impact

Every documentation surface the two PRs touch, explicit:

- `CHANGELOG.md` — one [Unreleased] entry per PR (foundation, then board pages). Neither is `migration-required`.
- `docs/setup/install-docker.md` — two additions: (1) top-nav mention in the Materials viewer section (PR 1); (2) Board pages paragraph (PR 2).
- `CLAUDE.md` — (1) new "Web Frontend Architecture" subsection under "Key File Locations" (PR 1) capturing the five foundational scope decisions; (2) cross-reference from the existing "Google Sheet Architecture" section to the web UI (PR 2).
- `docs/roadmap.md` — if present and tracks the 14 arc, check off 14b in PR 2.
- `docs/superpowers/specs/2026-04-21-web-frontend-14b-design.md` — the spec. If implementation diverges materially from the spec, amend via a "Decisions made during implementation" subsection in the same commit as the divergence (per plan-conventions.md).
- **In-code docstrings** — each new module (`routes/landing.py`, `routes/board.py`, `helpers.py`, `constants.py`) carries a module docstring explaining its role and who its callers are.
- **Followed-up docs** — post-PR 2 follow-up issue covers: retire `sync_sheet.py::Sheet1` writes; drop "Sheet1 > 1000 rows" health check; update CLAUDE.md's "Google Sheet Architecture" section to remove Sheet1.

No README changes — the README points at `docs/setup/install-docker.md` which is where user-facing install docs live.

---

# Verification gate (whole-feature)

Before each PR merges, the operator (or a subagent running on docker.lan) executes these checks end-to-end:

### Foundation PR (PR 1)
1. `python3 -m pytest -q` → all green.
2. `python3 -m ruff check src/findajob/web/ tests/` and `mypy src/findajob/web/` → all clean.
3. Against docker.lan (via `main-<sha>` tag or local uvicorn):
   - `/` renders landing with stage counts.
   - Top nav shows 7 links; current page is highlighted.
   - `/materials/` renders the old folder index (same folders as before).
   - `/materials/{fp}` still renders the folder viewer from #59.
   - `/board/`, `/ingest/`, `/tools/`, `/config/`, `/docs/` each render "Coming soon".
   - `/healthz` returns `ok`.

### Board PR (PR 2)
1. `python3 -m pytest -q` → all green (new tests + existing).
2. Ruff + mypy clean.
3. Against docker.lan:
   - `/board/dashboard` row count matches the current Google Sheet Dashboard tab (modulo poller's 10-min window).
   - `/board/applied` row count matches the Applied tab.
   - `/board/review` row count matches the Review tab.
   - `/board/waitlist` row count matches the Waitlist tab.
   - `/board/archive` first page shows 100 rows; scrolling loads more.
   - Clicking a company cell on `/board/applied` opens the materials folder.
   - Typing "meta" in the Dashboard filter narrows rows live.
   - Clicking a sort header reloads with the new sort order.
   - Applied row aged ≥ 21 days visibly rendered with gray background (`row-applied-cold` class).
   - Offer-stage row has gold background; Interviewing has purple.

If any gate item fails, fix on the branch before merging.

---

# Self-review checklist

After writing the final task, map every spec section to the tasks implementing it. Fix any gaps.

## Spec section → implementing task(s)

| Spec section | Implementing task(s) |
|---|---|
| §Overview | covered by goal + scope above |
| §Scope decisions 1–5 | locked in by file structure and task design (HTMX, grouped URL, Tailwind CDN, URL-param state); CLAUDE.md docs Task 8 |
| §Deferred | explicitly out-of-scope; no tasks |
| §PR boundary | Tasks 1–9 = PR 1; Tasks 10–20 = PR 2 |
| §File structure | Tasks 2, 3, 4, 6, 7, 11, 12 (creates/moves); Task 2 deletes monolithic routes.py |
| §PR 1 components 1 (base.html) | Task 3 |
| §PR 1 components 2 (_nav.html) | Task 3 |
| §PR 1 components 3 (landing) | Task 6 |
| §PR 1 components 4 (URL IA migration) | Tasks 4, 5, 6 |
| §PR 1 components 5 (placeholders) | Task 7 |
| §PR 1 components 6 (static assets) | Task 3 |
| §PR 1 components 7 (HTMX bootstrap) | Task 3 |
| §PR 1 components 8 (route-module split) | Task 2 |
| §PR 1 tests | Tasks 2, 3, 5, 6, 7 each add tests |
| §PR 1 documentation impact | Task 8 |
| §PR 2 components 1 (5 routes + col sets) | Tasks 13, 14, 15, 16 |
| §PR 2 components 2 (`_job_row.html`) | Task 12 |
| §PR 2 components 3 (sort via URL params) | Tasks 13, 14, 15, 16 (baked into each); Task 18 verifies |
| §PR 2 components 4 (HTMX filter) | Task 17 |
| §PR 2 components 5 (archive pagination) | Task 16 |
| §PR 2 components 6 (conditional formatting) | Task 12 |
| §PR 2 components 7 (materials link) | Task 12 (helper), Task 14 (applied tab) |
| §PR 2 tests | Tasks 13, 14, 15, 16, 17, 18 |
| §PR 2 documentation impact | Task 19 |
| §Sheet1 and the archive page | Task 16 (archive implementation); follow-up tracked after merge (no task in this plan) |
| §Data flow | tasks reference same DB path, same read-only connection; verified in gate |
| §Error handling | Task 5/6 (404 for missing routes); Task 16 (pagination end); Task 17 (empty filter returns all) |
| §Testing strategy | unit tests per task; E2E in verification gate |
| §Open questions / risks | FOLDER_STAGES extraction in Task 11 addresses materials-link parity risk; CDN risk documented in Task 8 |

## Placeholder scan

Search the plan for `TBD`, `TODO`, `implement later`, `similar to Task N`, or bare references to functions not defined in any task. Fix any hits inline. The test-file stubs in Task 18 must be made concrete before execution; the execution subagent fills them using the pattern from earlier tasks.

## Type / contract consistency

- `get_db` is defined once in `routes/materials.py` and imported by every other router module. App-factory override targets `findajob.web.routes.materials.get_db`.
- `FOLDER_STAGES` is defined once in `findajob.web.constants`. `_job_row.html` reads it via `folder_stages` Jinja global (set in `app.py`). `sync_sheet.py` imports it.
- `applied_age_bucket`, `stage_row_class`, `remote_cell_class` live in `findajob.web.helpers`; Jinja env globals in `app.py` expose them under the same names to templates.
- All handlers accept `sort`, `desc` Query params with consistent whitelisting against each tab's `_*_SORTABLE` set.
- Filter endpoints (`/board/<tab>/rows`) render `_job_rows_fragment.html` — a single shared template.
- Archive paginator (`/board/archive/rows`) renders `board/_archive_rows.html` — includes sentinel logic.

---

# Open questions resolved during plan writing

1. **`audit_log.job_id` column contents.** Task 14 notes the JOIN must match `jobs.fingerprint` or `jobs.id`; confirm against real DB during the verification gate and narrow the JOIN if needed.
2. **CDN reliability from docker.lan.** Ships as-is; if testers report unstyled pages, bundle Tailwind locally (separate follow-up issue, not in scope here).
3. **`blocking_app` semantics.** Defined in Task 15 as "most recent active application at the same company excluding this job"; acceptable for 14b. Refine in 14c if user needs more nuance.
