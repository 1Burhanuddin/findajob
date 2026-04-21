# Web Materials Viewer Implementation Plan (14a / #59)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the web materials viewer for #59 and rip rclone/Drive sync in the same PR. View-only; edits land in 14c.

**Architecture:** New FastAPI service inside the existing `findajob` container, serving `http://docker.lan:<port>/` per stack. Reads `/app/companies/` on disk plus a single `jobs` query for fingerprint→folder resolution. No DB writes, no auth, no LAN proxy (Synology handles the internet edge for services that need it). Supercronic remains PID 1; uvicorn launches from entrypoint as a background process with a SIGTERM trap.

**Tech Stack:** FastAPI, uvicorn[standard], Jinja2, Python-Markdown. SQLite via stdlib for reads. Python 3.12. pytest + FastAPI TestClient for tests.

---

## Spec reference

This plan implements `docs/superpowers/specs/2026-04-20-web-materials-viewer-design.md` (commit `5514b44` on `main`). Read the spec first if anything below is ambiguous. All five brainstorm decisions (per-stack host port, FastAPI, stage-grouped index, full rclone rip, no Drive integration) are resolved in the spec and are not revisited here.

## Issues

- #59 — Web frontend 14a: materials viewer (retires rclone/Drive). In Up Next.

## Branch discipline

Per memory `feedback_git_branch_off_origin`, every branch is created from `origin/main`, never from local `main`. Task 1 fetches from origin and creates the feature branch.

## File structure

New:

```
src/findajob/web/__init__.py
src/findajob/web/app.py                    FastAPI factory, Jinja env, startup hook
src/findajob/web/routes.py                 route handlers
src/findajob/web/folder_resolver.py        fingerprint → path, traversal guards
src/findajob/web/templates/base.html
src/findajob/web/templates/index.html
src/findajob/web/templates/folder.html
tests/test_web_folder_resolver.py
tests/test_web_routes.py
tests/test_web_integration.py
```

Modified:

```
pyproject.toml                             +fastapi +uvicorn[standard] +jinja2 +markdown
ops/entrypoint.sh                          launch uvicorn + SIGTERM trap + drop rclone chown
ops/crontab                                remove */15 rclone entry
ops/compose.yaml.example                   +ports, -rclone volume, -FINDAJOB_JOBSYNC_ENABLED
ops/stack.env.example                      +FINDAJOB_MATERIALS_PORT, -jobsync vars
Dockerfile                                 -rclone from apt install
src/findajob/paths.py                      -RCLONE export
scripts/poll_flags.py                      -_rclone_* helpers and call sites
scripts/prep_application.py                -rclone_immediate_push + Drive hyperlink formula
scripts/notify.py                          -rclone health checks
scripts/sync_sheet.py                      company column becomes plain text
tests/test_poll_flags.py                   drop rclone tests
tests/test_prep_pipeline.py                drop rclone tests
scripts/test_container_integration.sh     +viewer smoke + rclone-absent check
docs/setup/install-docker.md               rewrite rclone sections; add MATERIALS_PORT
docs/setup/state-migration.md              operator one-time cleanup
docs/operations.md                         -jobsync; +viewer
docs/architecture.md                       -rclone/Drive layer; +viewer process
README.md                                  remove rclone/Drive mentions
CHANGELOG.md                               [Unreleased] entry, migration-required
CLAUDE.md                                  §"Container Context" updates
```

## File responsibilities

- **`folder_resolver.py`**: single-purpose module for `fingerprint → absolute folder path` with traversal guards. Pure, testable without FastAPI, no SQLite — takes DB connection as argument.
- **`routes.py`**: thin handlers only. Business logic lives in `folder_resolver.py` (path resolution) or stays inline where it's 2-3 lines (stage queries).
- **`app.py`**: FastAPI factory + Jinja config + DB dependency. No route logic here.
- **Templates**: presentation only, no branching logic beyond loops.

---

## Task 1: Branch, issue housekeeping

**Files:**
- Create: new branch `feat/59-web-materials-viewer`
- Modify: issue #59 body (add `## Planning` section)

- [ ] **Step 1: Fetch origin and create feature branch off `origin/main`**

```bash
git fetch origin
git checkout -b feat/59-web-materials-viewer origin/main
```

- [ ] **Step 2: Add `## Planning` section to #59**

Fetch current body, append a Planning section pointing to spec + plan, write back:

```bash
gh issue view 59 --json body --jq .body > /tmp/59body.md
cat >> /tmp/59body.md <<'EOF'

## Planning

- Spec: [`docs/superpowers/specs/2026-04-20-web-materials-viewer-design.md`](../blob/main/docs/superpowers/specs/2026-04-20-web-materials-viewer-design.md)
- Plan: [`docs/superpowers/plans/2026-04-20-web-materials-viewer.md`](../blob/main/docs/superpowers/plans/2026-04-20-web-materials-viewer.md)
EOF
gh issue edit 59 --body-file /tmp/59body.md
```

Expected: the issue now has a `## Planning` section with links.

- [ ] **Step 3: Move #59 to In Progress on the project board**

```bash
gh api graphql -f query='mutation { updateProjectV2ItemFieldValue(input:{projectId:"PVT_kwHOAgGulc4BUtxZ", itemId:"PVTI_lAHOAgGulc4BUtxZzgqM5-k", fieldId:"PVTSSF_lAHOAgGulc4BUtxZzhCOoMM", value:{singleSelectOptionId:"87411b49"}}) { projectV2Item { id } } }'
```

- [ ] **Step 4: Commit the branch-start state**

Nothing to commit yet; this task ends after housekeeping. No commit.

---

## Task 2: Add web dependencies and package skeleton

**Files:**
- Modify: `pyproject.toml`
- Create: `src/findajob/web/__init__.py` (empty marker)

- [ ] **Step 1: Add web dependencies to `pyproject.toml`**

In the `[project]` → `dependencies` array, append:

```toml
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.32.0",
    "jinja2>=3.1.0",
    "markdown>=3.7",
```

Full modified block:

```toml
dependencies = [
    "google-api-python-client>=2.194.0",
    "google-auth-httplib2>=0.3.1",
    "google-auth-oauthlib>=1.3.1",
    "requests>=2.31.0",
    "jsonschema>=4.26.0",
    "beautifulsoup4>=4.14.0",
    "pyyaml>=6.0",
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.32.0",
    "jinja2>=3.1.0",
    "markdown>=3.7",
]
```

- [ ] **Step 2: Install deps locally**

```bash
pip3 install --break-system-packages -e .
```

Expected: installs fastapi, uvicorn, jinja2, markdown without error.

- [ ] **Step 3: Create the web package marker**

Create `src/findajob/web/__init__.py`:

```python
"""FastAPI web materials viewer. Ships in 14a (#59)."""
```

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml src/findajob/web/__init__.py
git commit -m "feat(web): scaffold web package and add FastAPI deps"
```

---

## Task 3: Folder resolver — fingerprint → path (TDD)

**Files:**
- Test: `tests/test_web_folder_resolver.py`
- Create: `src/findajob/web/folder_resolver.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_web_folder_resolver.py`:

```python
"""Tests for fingerprint → folder path resolution."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from findajob.web.folder_resolver import resolve_folder


@pytest.fixture
def companies_root(tmp_path: Path) -> Path:
    (tmp_path / "Meta_SWE_2026-04-20_120000").mkdir()
    (tmp_path / "_applied" / "Google_PM_2026-04-15_100000").mkdir(parents=True)
    (tmp_path / "_waitlisted" / "Stripe_DE_2026-04-10_090000").mkdir(parents=True)
    (tmp_path / "_rejected" / "X_SRE_2026-04-01_080000").mkdir(parents=True)
    return tmp_path


@pytest.fixture
def db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE jobs (fingerprint TEXT PRIMARY KEY, prep_folder_path TEXT, stage TEXT)"
    )
    return conn


def _seed(db: sqlite3.Connection, fp: str, folder: str, stage: str = "materials_drafted") -> None:
    db.execute(
        "INSERT INTO jobs (fingerprint, prep_folder_path, stage) VALUES (?, ?, ?)",
        (fp, folder, stage),
    )


def test_resolve_active_folder(companies_root: Path, db: sqlite3.Connection) -> None:
    _seed(db, "fp-active", str(companies_root / "Meta_SWE_2026-04-20_120000"))
    result = resolve_folder("fp-active", db, companies_root)
    assert result == companies_root / "Meta_SWE_2026-04-20_120000"


def test_resolve_applied_folder(companies_root: Path, db: sqlite3.Connection) -> None:
    _seed(
        db,
        "fp-applied",
        str(companies_root / "_applied" / "Google_PM_2026-04-15_100000"),
        stage="applied",
    )
    result = resolve_folder("fp-applied", db, companies_root)
    assert result == companies_root / "_applied" / "Google_PM_2026-04-15_100000"


def test_resolve_unknown_fingerprint_returns_none(
    companies_root: Path, db: sqlite3.Connection
) -> None:
    assert resolve_folder("fp-unknown", db, companies_root) is None


def test_resolve_folder_missing_on_disk_returns_none(
    companies_root: Path, db: sqlite3.Connection
) -> None:
    _seed(db, "fp-ghost", str(companies_root / "Ghost_Folder_Never_Existed"))
    assert resolve_folder("fp-ghost", db, companies_root) is None


def test_resolve_null_prep_folder_path_returns_none(
    companies_root: Path, db: sqlite3.Connection
) -> None:
    db.execute(
        "INSERT INTO jobs (fingerprint, prep_folder_path, stage) VALUES (?, NULL, 'scored')",
        ("fp-nopath",),
    )
    assert resolve_folder("fp-nopath", db, companies_root) is None
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_web_folder_resolver.py -v
```

Expected: ImportError / ModuleNotFoundError on `findajob.web.folder_resolver`.

- [ ] **Step 3: Implement `folder_resolver.py`**

Create `src/findajob/web/folder_resolver.py`:

```python
"""Fingerprint → folder path resolution with traversal guards.

Pure helper: no FastAPI, no I/O beyond filesystem existence checks.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path


def resolve_folder(
    fingerprint: str, db: sqlite3.Connection, companies_root: Path
) -> Path | None:
    """Resolve a fingerprint to its prep-folder path on disk.

    Returns None if:
      - fingerprint is not in the jobs table
      - jobs.prep_folder_path is NULL or empty
      - the resolved path does not exist on disk
      - the resolved path escapes companies_root (path-traversal guard)
    """
    row = db.execute(
        "SELECT prep_folder_path FROM jobs WHERE fingerprint = ?", (fingerprint,)
    ).fetchone()
    if row is None:
        return None
    raw = row["prep_folder_path"] if isinstance(row, sqlite3.Row) else row[0]
    if not raw:
        return None

    candidate = Path(raw).resolve()
    root = companies_root.resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None

    if not candidate.is_dir():
        return None
    return candidate
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/test_web_folder_resolver.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add src/findajob/web/folder_resolver.py tests/test_web_folder_resolver.py
git commit -m "feat(web): folder resolver with fingerprint → path lookup"
```

---

## Task 4: Path traversal guards (TDD)

Resolver already has the guard; extend tests to cover edge cases.

**Files:**
- Modify: `tests/test_web_folder_resolver.py`

- [ ] **Step 1: Add traversal guard tests**

Append to `tests/test_web_folder_resolver.py`:

```python
def test_rejects_absolute_path_outside_root(
    companies_root: Path, db: sqlite3.Connection, tmp_path_factory: pytest.TempPathFactory
) -> None:
    outside = tmp_path_factory.mktemp("outside")
    _seed(db, "fp-outside", str(outside))
    assert resolve_folder("fp-outside", db, companies_root) is None


def test_rejects_dotdot_traversal(
    companies_root: Path, db: sqlite3.Connection
) -> None:
    malicious = str(companies_root / ".." / "outside-root")
    _seed(db, "fp-traversal", malicious)
    assert resolve_folder("fp-traversal", db, companies_root) is None


def test_rejects_symlink_escaping_root(
    companies_root: Path,
    db: sqlite3.Connection,
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    outside_target = tmp_path_factory.mktemp("outside_target")
    link = companies_root / "escape_link"
    link.symlink_to(outside_target)
    _seed(db, "fp-symlink", str(link))
    assert resolve_folder("fp-symlink", db, companies_root) is None
```

- [ ] **Step 2: Run tests**

```bash
pytest tests/test_web_folder_resolver.py -v
```

Expected: 8 passed (5 original + 3 new).

- [ ] **Step 3: Commit**

```bash
git add tests/test_web_folder_resolver.py
git commit -m "test(web): path traversal guards on folder resolver"
```

---

## Task 5: App factory + `/healthz` (TDD)

**Files:**
- Test: `tests/test_web_routes.py`
- Create: `src/findajob/web/app.py`
- Create: `src/findajob/web/routes.py`

- [ ] **Step 1: Write the failing healthz test**

Create `tests/test_web_routes.py`:

```python
"""Unit tests for the web viewer routes."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from findajob.web.app import create_app


@pytest.fixture
def companies_root(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    p = tmp_path / "pipeline.db"
    conn = sqlite3.connect(p)
    conn.execute(
        """CREATE TABLE jobs (
            fingerprint TEXT PRIMARY KEY,
            prep_folder_path TEXT,
            stage TEXT,
            title TEXT,
            company TEXT,
            score INTEGER,
            created_at TEXT,
            applied_date TEXT
        )"""
    )
    conn.commit()
    conn.close()
    return p


@pytest.fixture
def client(companies_root: Path, db_path: Path) -> TestClient:
    app = create_app(companies_root=companies_root, db_path=db_path)
    return TestClient(app)


def test_healthz_returns_ok(client: TestClient) -> None:
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.text == "ok"
```

- [ ] **Step 2: Run test to confirm failure**

```bash
pytest tests/test_web_routes.py -v
```

Expected: ImportError on `findajob.web.app`.

- [ ] **Step 3: Implement `app.py`**

Create `src/findajob/web/app.py`:

```python
"""FastAPI app factory for the materials viewer."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Generator

from fastapi import Depends, FastAPI
from fastapi.templating import Jinja2Templates

from findajob.web import routes


def create_app(*, companies_root: Path, db_path: Path) -> FastAPI:
    app = FastAPI(title="findajob materials viewer", docs_url=None, redoc_url=None)

    templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

    app.state.companies_root = companies_root
    app.state.db_path = db_path
    app.state.templates = templates

    def get_db() -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    app.dependency_overrides.setdefault(routes.get_db, get_db)
    app.include_router(routes.router)
    return app
```

- [ ] **Step 4: Implement `routes.py` with healthz**

Create `src/findajob/web/routes.py`:

```python
"""Route handlers for the materials viewer."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi import APIRouter, Request, Response

router = APIRouter()


def get_db() -> sqlite3.Connection:  # pragma: no cover — overridden in app factory
    raise NotImplementedError("DB dependency must be overridden by create_app()")


@router.get("/healthz", response_class=Response)
def healthz(request: Request) -> Response:
    root: Path = request.app.state.companies_root
    if not root.is_dir():
        return Response(content="companies/ missing", status_code=503, media_type="text/plain")
    return Response(content="ok", status_code=200, media_type="text/plain")
```

- [ ] **Step 5: Run test to confirm it passes**

```bash
pytest tests/test_web_routes.py -v
```

Expected: 1 passed.

- [ ] **Step 6: Commit**

```bash
git add src/findajob/web/app.py src/findajob/web/routes.py tests/test_web_routes.py
git commit -m "feat(web): app factory and /healthz route"
```

---

## Task 6: Folder listing route + template (TDD)

**Files:**
- Modify: `tests/test_web_routes.py`
- Modify: `src/findajob/web/routes.py`
- Create: `src/findajob/web/templates/base.html`
- Create: `src/findajob/web/templates/folder.html`

- [ ] **Step 1: Add failing test**

Append to `tests/test_web_routes.py`:

```python
def test_folder_route_lists_files(
    client: TestClient, companies_root: Path, db_path: Path
) -> None:
    folder = companies_root / "Meta_SWE_2026-04-20_120000"
    folder.mkdir()
    (folder / "tailored_resume.docx").write_bytes(b"docx-bytes")
    (folder / "cover_letter.md").write_text("# Hello\n")

    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO jobs (fingerprint, prep_folder_path, stage, title, company) "
        "VALUES (?, ?, 'materials_drafted', 'SWE', 'Meta')",
        ("fp-1", str(folder)),
    )
    conn.commit()
    conn.close()

    r = client.get("/materials/fp-1")
    assert r.status_code == 200
    assert "tailored_resume.docx" in r.text
    assert "cover_letter.md" in r.text


def test_folder_route_404_on_unknown_fingerprint(client: TestClient) -> None:
    r = client.get("/materials/fp-does-not-exist")
    assert r.status_code == 404
```

- [ ] **Step 2: Run test to confirm failure**

```bash
pytest tests/test_web_routes.py -v
```

Expected: 2 new tests fail.

- [ ] **Step 3: Add the folder route**

Modify `src/findajob/web/routes.py`. Replace the top `from fastapi import ...` line and add the new imports and route. Full file content now:

```python
"""Route handlers for the materials viewer."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import HTMLResponse

from findajob.web.folder_resolver import resolve_folder

router = APIRouter()


def get_db() -> sqlite3.Connection:  # pragma: no cover — overridden in app factory
    raise NotImplementedError("DB dependency must be overridden by create_app()")


@router.get("/healthz", response_class=Response)
def healthz(request: Request) -> Response:
    root: Path = request.app.state.companies_root
    if not root.is_dir():
        return Response(content="companies/ missing", status_code=503, media_type="text/plain")
    return Response(content="ok", status_code=200, media_type="text/plain")


@router.get("/materials/{fingerprint}", response_class=HTMLResponse)
def folder_view(
    fingerprint: str,
    request: Request,
    db: sqlite3.Connection = Depends(get_db),
) -> HTMLResponse:
    root: Path = request.app.state.companies_root
    folder = resolve_folder(fingerprint, db, root)
    if folder is None:
        raise HTTPException(status_code=404, detail="folder not found")

    row = db.execute(
        "SELECT title, company, stage FROM jobs WHERE fingerprint = ?", (fingerprint,)
    ).fetchone()

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
```

- [ ] **Step 4: Create the base template**

Create `src/findajob/web/templates/base.html`:

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{% block title %}findajob materials{% endblock %}</title>
  <style>
    body { font-family: -apple-system, system-ui, sans-serif; max-width: 960px; margin: 2em auto; padding: 0 1em; color: #222; }
    a { color: #0366d6; text-decoration: none; }
    a:hover { text-decoration: underline; }
    h1, h2 { border-bottom: 1px solid #eee; padding-bottom: 0.3em; }
    ul { padding-left: 1.2em; }
    li { margin: 0.3em 0; }
    .meta { color: #666; font-size: 0.9em; }
    .stage { color: #0366d6; }
    .score { color: #22863a; font-weight: 600; }
    details summary { cursor: pointer; color: #666; }
    pre, code { font-family: ui-monospace, monospace; background: #f6f8fa; }
    pre { padding: 1em; overflow-x: auto; }
    code { padding: 0.1em 0.3em; border-radius: 3px; }
  </style>
</head>
<body>
{% block body %}{% endblock %}
</body>
</html>
```

- [ ] **Step 5: Create the folder template**

Create `src/findajob/web/templates/folder.html`:

```html
{% extends "base.html" %}
{% block title %}{{ company }} — {{ title }}{% endblock %}
{% block body %}
<p><a href="/">← back to index</a></p>
<h1>{{ company }} — {{ title }}</h1>
<p class="meta">{{ folder_name }} · <span class="stage">{{ stage }}</span></p>
<ul>
  {% for name in files %}
    <li><a href="/materials/{{ fingerprint }}/{{ name }}">{{ name }}</a></li>
  {% endfor %}
</ul>
{% endblock %}
```

- [ ] **Step 6: Run tests**

```bash
pytest tests/test_web_routes.py -v
```

Expected: 3 passed.

- [ ] **Step 7: Commit**

```bash
git add src/findajob/web/routes.py src/findajob/web/templates/base.html src/findajob/web/templates/folder.html tests/test_web_routes.py
git commit -m "feat(web): folder listing route + templates"
```

---

## Task 7: File-serve route (TDD)

Handles `.md` (rendered HTML), `.txt` (inline plain), `.docx` (attachment), everything else (attachment).

**Files:**
- Modify: `tests/test_web_routes.py`
- Modify: `src/findajob/web/routes.py`

- [ ] **Step 1: Add failing tests**

Append to `tests/test_web_routes.py`:

```python
def test_file_serve_markdown_rendered_inline(
    client: TestClient, companies_root: Path, db_path: Path
) -> None:
    folder = companies_root / "Company_X_2026-04-20_130000"
    folder.mkdir()
    (folder / "notes.md").write_text("# Hello\n\n```python\nprint('hi')\n```\n")

    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO jobs (fingerprint, prep_folder_path, stage) VALUES ('fp-md', ?, 'materials_drafted')",
        (str(folder),),
    )
    conn.commit()
    conn.close()

    r = client.get("/materials/fp-md/notes.md")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert "<h1>Hello</h1>" in r.text
    assert "<code>print" in r.text


def test_file_serve_docx_as_attachment(
    client: TestClient, companies_root: Path, db_path: Path
) -> None:
    folder = companies_root / "Company_Y_2026-04-20_140000"
    folder.mkdir()
    (folder / "resume.docx").write_bytes(b"PK\x03\x04fake-docx-bytes")

    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO jobs (fingerprint, prep_folder_path, stage) VALUES ('fp-docx', ?, 'materials_drafted')",
        (str(folder),),
    )
    conn.commit()
    conn.close()

    r = client.get("/materials/fp-docx/resume.docx")
    assert r.status_code == 200
    assert "attachment" in r.headers.get("content-disposition", "")
    assert "resume.docx" in r.headers.get("content-disposition", "")


def test_file_serve_txt_inline(
    client: TestClient, companies_root: Path, db_path: Path
) -> None:
    folder = companies_root / "Company_Z_2026-04-20_150000"
    folder.mkdir()
    (folder / "raw.txt").write_text("plain text body\n")

    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO jobs (fingerprint, prep_folder_path, stage) VALUES ('fp-txt', ?, 'materials_drafted')",
        (str(folder),),
    )
    conn.commit()
    conn.close()

    r = client.get("/materials/fp-txt/raw.txt")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/plain")
    assert "plain text body" in r.text


def test_file_serve_404_on_unknown_filename(
    client: TestClient, companies_root: Path, db_path: Path
) -> None:
    folder = companies_root / "Company_W_2026-04-20_160000"
    folder.mkdir()
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO jobs (fingerprint, prep_folder_path, stage) VALUES ('fp-empty', ?, 'materials_drafted')",
        (str(folder),),
    )
    conn.commit()
    conn.close()

    r = client.get("/materials/fp-empty/nonexistent.md")
    assert r.status_code == 404


def test_file_serve_rejects_traversal(
    client: TestClient, companies_root: Path, db_path: Path
) -> None:
    folder = companies_root / "Company_T_2026-04-20_170000"
    folder.mkdir()
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO jobs (fingerprint, prep_folder_path, stage) VALUES ('fp-t', ?, 'materials_drafted')",
        (str(folder),),
    )
    conn.commit()
    conn.close()

    r = client.get("/materials/fp-t/..%2Fescape")
    assert r.status_code == 404


def test_file_serve_markdown_escapes_raw_html(
    client: TestClient, companies_root: Path, db_path: Path
) -> None:
    folder = companies_root / "Company_XSS_2026-04-20_180000"
    folder.mkdir()
    (folder / "bad.md").write_text("# Title\n\n<script>alert('x')</script>\n")

    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO jobs (fingerprint, prep_folder_path, stage) VALUES ('fp-xss', ?, 'materials_drafted')",
        (str(folder),),
    )
    conn.commit()
    conn.close()

    r = client.get("/materials/fp-xss/bad.md")
    assert r.status_code == 200
    assert "<script>" not in r.text
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_web_routes.py -v
```

Expected: 6 new tests fail.

- [ ] **Step 3: Add the file-serve route**

First, update the imports at the top of `src/findajob/web/routes.py`:

- Replace the single `from fastapi.responses import HTMLResponse` line with:

```python
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse
```

- Add, immediately below the FastAPI imports:

```python
import markdown as md_lib
```

Then append the helper and route to the bottom of the file:

```python
def _render_markdown(text: str) -> str:
    html = md_lib.markdown(text, extensions=["fenced_code", "tables"], output_format="html")
    return html


@router.get("/materials/{fingerprint}/{filename}")
def file_serve(
    fingerprint: str,
    filename: str,
    request: Request,
    db: sqlite3.Connection = Depends(get_db),
):
    root: Path = request.app.state.companies_root
    folder = resolve_folder(fingerprint, db, root)
    if folder is None:
        raise HTTPException(status_code=404, detail="folder not found")

    candidate = (folder / filename).resolve()
    try:
        candidate.relative_to(folder.resolve())
    except ValueError:
        raise HTTPException(status_code=404, detail="invalid filename")
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
    # Everything else (.docx, .pdf, unknown) → attachment
    return FileResponse(
        path=candidate,
        filename=candidate.name,
        headers={"content-disposition": f'attachment; filename="{candidate.name}"'},
    )
```

- [ ] **Step 4: Extend `base.html` to render markdown content when provided**

Modify `src/findajob/web/templates/base.html` — replace the body block:

```html
<body>
{% if _rendered_md is defined %}
  <p><a href="javascript:history.back()">← back</a></p>
  {{ _rendered_md | safe }}
{% else %}
  {% block body %}{% endblock %}
{% endif %}
</body>
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/test_web_routes.py -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/findajob/web/routes.py src/findajob/web/templates/base.html tests/test_web_routes.py
git commit -m "feat(web): file serve route with md rendering, txt inline, docx attachment"
```

---

## Task 8: Index route + template (TDD)

**Files:**
- Modify: `tests/test_web_routes.py`
- Modify: `src/findajob/web/routes.py`
- Create: `src/findajob/web/templates/index.html`

- [ ] **Step 1: Add failing tests**

Append to `tests/test_web_routes.py`:

```python
def test_index_groups_jobs_by_stage(
    client: TestClient, companies_root: Path, db_path: Path
) -> None:
    for folder_name in ("M1", "_applied/M2", "_waitlisted/M3", "_rejected/M4"):
        (companies_root / folder_name).mkdir(parents=True)

    conn = sqlite3.connect(db_path)
    conn.executemany(
        "INSERT INTO jobs (fingerprint, prep_folder_path, stage, title, company, score, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            ("fp-a", str(companies_root / "M1"), "materials_drafted", "SWE", "InFlightCo", 8, "2026-04-20"),
            ("fp-b", str(companies_root / "_applied" / "M2"), "applied", "PM", "AppliedCo", 7, "2026-04-15"),
            ("fp-c", str(companies_root / "_waitlisted" / "M3"), "waitlisted", "DE", "WaitCo", 6, "2026-04-10"),
            ("fp-d", str(companies_root / "_rejected" / "M4"), "rejected", "SRE", "RejCo", 5, "2026-04-01"),
        ],
    )
    conn.commit()
    conn.close()

    r = client.get("/")
    assert r.status_code == 200
    assert "In flight" in r.text
    assert "InFlightCo" in r.text
    assert "Applied" in r.text
    assert "AppliedCo" in r.text
    assert "Waitlisted" in r.text
    assert "WaitCo" in r.text
    # Rejected is in a <details>; content is still rendered
    assert "<details>" in r.text
    assert "RejCo" in r.text
```

- [ ] **Step 2: Run test to confirm failure**

```bash
pytest tests/test_web_routes.py::test_index_groups_jobs_by_stage -v
```

Expected: 404 on `/`.

- [ ] **Step 3: Add the index route**

Append to `src/findajob/web/routes.py`:

```python
_INDEX_QUERY_SECTIONS = [
    (
        "In flight",
        "stage IN ('materials_drafted', 'prep_in_progress')",
        "created_at DESC",
    ),
    (
        "Applied",
        "stage IN ('applied', 'interview', 'offer')",
        "COALESCE(applied_date, created_at) DESC",
    ),
    ("Waitlisted", "stage = 'waitlisted'", "created_at DESC"),
]
_REJECTED_CLAUSE = "stage IN ('rejected', 'not_selected')"
_PER_SECTION_CAP = 50


def _fetch_section(db: sqlite3.Connection, where: str, order: str) -> list[sqlite3.Row]:
    return db.execute(
        f"SELECT fingerprint, title, company, stage, score, created_at, applied_date "
        f"FROM jobs WHERE {where} ORDER BY {order} LIMIT {_PER_SECTION_CAP + 1}"
    ).fetchall()


@router.get("/", response_class=HTMLResponse)
def index(request: Request, db: sqlite3.Connection = Depends(get_db)) -> HTMLResponse:
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
```

- [ ] **Step 4: Create the index template**

Create `src/findajob/web/templates/index.html`:

```html
{% extends "base.html" %}
{% block title %}findajob — materials{% endblock %}
{% block body %}
<h1>findajob materials</h1>

{% for section in sections %}
<h2>{{ section.name }}</h2>
{% if section.rows %}
<ul>
  {% for row in section.rows %}
    <li>
      <a href="/materials/{{ row.fingerprint }}">{{ row.company }} — {{ row.title }}</a>
      {% if row.score %} <span class="score">[{{ row.score }}]</span>{% endif %}
      <span class="meta">
        (<span class="stage">{{ row.stage }}</span>)
        {% if row.applied_date %} · {{ row.applied_date }}{% endif %}
      </span>
    </li>
  {% endfor %}
</ul>
{% if section.overflow %}<p class="meta">…and more</p>{% endif %}
{% else %}
<p class="meta">None.</p>
{% endif %}
{% endfor %}

<details>
  <summary>Rejected ({{ rejected.count }})</summary>
  {% if rejected.rows %}
  <ul>
    {% for row in rejected.rows %}
      <li>
        <a href="/materials/{{ row.fingerprint }}">{{ row.company }} — {{ row.title }}</a>
        <span class="meta">· {{ row.stage }} · {{ row.created_at }}</span>
      </li>
    {% endfor %}
  </ul>
  {% if rejected.overflow %}<p class="meta">…and more</p>{% endif %}
  {% else %}
  <p class="meta">None.</p>
  {% endif %}
</details>
{% endblock %}
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/test_web_routes.py -v
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add src/findajob/web/routes.py src/findajob/web/templates/index.html tests/test_web_routes.py
git commit -m "feat(web): index route with stage-grouped listings"
```

---

## Task 9: Integration test — FastAPI TestClient end-to-end

**Files:**
- Create: `tests/test_web_integration.py`

- [ ] **Step 1: Write the integration tests**

Create `tests/test_web_integration.py`:

```python
"""End-to-end integration tests for the materials viewer.

Spins up a FastAPI TestClient against a tmpdir `companies/` tree and a
scratch SQLite. Validates all routes together.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from findajob.web.app import create_app


@pytest.fixture
def world(tmp_path: Path) -> dict:
    companies = tmp_path / "companies"
    companies.mkdir()

    active = companies / "Meta_SWE_2026-04-20_120000"
    active.mkdir()
    (active / "tailored_resume.docx").write_bytes(b"PK\x03\x04fake")
    (active / "cover_letter.md").write_text("# Cover\n\nBody.\n")

    applied = companies / "_applied" / "Google_PM_2026-04-15_100000"
    applied.mkdir(parents=True)
    (applied / "notes.txt").write_text("applied on 2026-04-15\n")

    db = tmp_path / "pipeline.db"
    conn = sqlite3.connect(db)
    conn.execute(
        """CREATE TABLE jobs (
            fingerprint TEXT PRIMARY KEY,
            prep_folder_path TEXT,
            stage TEXT,
            title TEXT,
            company TEXT,
            score INTEGER,
            created_at TEXT,
            applied_date TEXT
        )"""
    )
    conn.executemany(
        "INSERT INTO jobs VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            ("fp-active", str(active), "materials_drafted", "SWE", "Meta", 8, "2026-04-20", None),
            ("fp-applied", str(applied), "applied", "PM", "Google", 7, "2026-04-15", "2026-04-15"),
        ],
    )
    conn.commit()
    conn.close()

    app = create_app(companies_root=companies, db_path=db)
    return {"client": TestClient(app), "companies": companies, "db": db}


def test_full_flow(world: dict) -> None:
    client = world["client"]

    r = client.get("/healthz")
    assert r.status_code == 200

    r = client.get("/")
    assert r.status_code == 200
    assert "Meta" in r.text
    assert "Google" in r.text

    r = client.get("/materials/fp-active")
    assert r.status_code == 200
    assert "tailored_resume.docx" in r.text
    assert "cover_letter.md" in r.text

    r = client.get("/materials/fp-active/cover_letter.md")
    assert r.status_code == 200
    assert "<h1>Cover</h1>" in r.text

    r = client.get("/materials/fp-active/tailored_resume.docx")
    assert r.status_code == 200
    assert "attachment" in r.headers.get("content-disposition", "")

    r = client.get("/materials/fp-applied/notes.txt")
    assert r.status_code == 200
    assert "applied on 2026-04-15" in r.text
```

- [ ] **Step 2: Run tests**

```bash
pytest tests/test_web_integration.py -v
```

Expected: 1 passed.

- [ ] **Step 3: Run the full test suite to verify no regressions**

```bash
pytest -x
```

Expected: all existing tests still pass.

- [ ] **Step 4: Commit**

```bash
git add tests/test_web_integration.py
git commit -m "test(web): integration test for TestClient end-to-end flow"
```

---

## Task 10: Entrypoint launches uvicorn with SIGTERM trap

**Files:**
- Modify: `ops/entrypoint.sh`

- [ ] **Step 1: Read current entrypoint**

```bash
cat ops/entrypoint.sh
```

Note where the final `exec supercronic` line is. That line needs to be preceded by an uvicorn launch and wrapped so SIGTERM forwards.

- [ ] **Step 2: Add uvicorn launch + SIGTERM trap**

Modify `ops/entrypoint.sh`. Find the final `exec supercronic /app/crontab` line (or equivalent) and replace with:

```sh
# --- Launch materials viewer (uvicorn) in background ----------------------
# Supercronic stays PID 1 for compose restart tracking. Uvicorn runs as a
# child process. If it crashes, supercronic keeps running — /healthz is the
# outside signal. Operator restarts the container if needed.
su -s /bin/sh findajob -c "/usr/local/bin/python3 -m uvicorn findajob.web.app:create_app --factory --host 0.0.0.0 --port 8090 --log-level info" &
UVICORN_PID=$!

# Forward SIGTERM / SIGINT to uvicorn so docker compose down shuts it down cleanly.
trap 'kill -TERM "$UVICORN_PID" 2>/dev/null; exit 0' TERM INT

# --- Drop privileges and run supercronic in foreground --------------------
exec su -s /bin/sh findajob -c "/usr/local/bin/supercronic /app/crontab"
```

If the existing entrypoint doesn't use `su -s`, match its existing style for launching as the `findajob` user (look for how supercronic was being invoked and mirror it).

- [ ] **Step 3: Also remove the `rclone` config dir from the chown loop**

Find the chown loop that touches `/app/.config/rclone` (line ~73 based on earlier inspection) and delete that path from the loop.

Before:

```sh
for dir in /app/data /app/logs /app/companies /app/config /app/candidate_context /app/.config/rclone "$AICHAT_CFG_DIR"; do
```

After:

```sh
for dir in /app/data /app/logs /app/companies /app/config /app/candidate_context "$AICHAT_CFG_DIR"; do
```

- [ ] **Step 4: Smoke the entrypoint locally (syntax only, no docker)**

```bash
sh -n ops/entrypoint.sh
```

Expected: no output (syntax OK).

- [ ] **Step 5: Commit**

```bash
git add ops/entrypoint.sh
git commit -m "feat(ops): entrypoint launches uvicorn alongside supercronic"
```

---

## Task 11: Compose, env, Dockerfile — add viewer port, drop rclone

**Files:**
- Modify: `ops/compose.yaml.example`
- Modify: `ops/stack.env.example`
- Modify: `Dockerfile`

- [ ] **Step 1: Modify `ops/compose.yaml.example`**

Add `ports:` block after `restart:`. Remove the `./state/rclone:/app/.config/rclone` volume line. Remove the `FINDAJOB_JOBSYNC_ENABLED` environment line.

Diff:

```diff
 services:
   scheduler:
     image: ghcr.io/brockamer/findajob:${FINDAJOB_IMAGE_TAG:-v0.1}
     restart: unless-stopped
+    ports:
+      - "${FINDAJOB_MATERIALS_PORT:-8090}:8090"
     labels:
       - "com.centurylinklabs.watchtower.enable=false"
     env_file: ./state/data/.env
     environment:
       TZ: ${FINDAJOB_TZ:-America/New_York}
       PUID: ${PUID:-1000}
       PGID: ${PGID:-1000}
       JSP_BASE: /app
       HOME: /app
-      FINDAJOB_JOBSYNC_ENABLED: ${FINDAJOB_JOBSYNC_ENABLED:-false}
       FINDAJOB_TRIAGE_TIMEOUT: ${FINDAJOB_TRIAGE_TIMEOUT:-7200}
     volumes:
       - ./state/data:/app/data
       - ./state/config:/app/config
       - ./state/candidate_context:/app/candidate_context
       - ./state/companies:/app/companies
       - ./state/logs:/app/logs
       - ./state/aichat_ng:/app/.config/aichat_ng
-      - ./state/rclone:/app/.config/rclone
```

- [ ] **Step 2: Modify `ops/stack.env.example`**

Remove the rclone/jobsync instructions block. Add a `FINDAJOB_MATERIALS_PORT` entry.

Find the block that starts with "# Google Drive sync via rclone. Disabled by default..." and delete it entirely (through the `FINDAJOB_JOBSYNC_REMOTE` line).

Add at an appropriate location (near the other port/host settings if any):

```
# Web materials viewer — per-stack host port (each stack picks a unique port).
# Current allocation starts at 8090 and increments per stack.
FINDAJOB_MATERIALS_PORT=8090
```

- [ ] **Step 3: Modify `Dockerfile`**

Remove `rclone` from the apt install list.

Diff:

```diff
 RUN apt-get update && apt-get install -y --no-install-recommends \
         curl \
         ca-certificates \
-        rclone \
         pandoc \
         ...
```

- [ ] **Step 4: Commit**

```bash
git add ops/compose.yaml.example ops/stack.env.example Dockerfile
git commit -m "feat(ops): expose viewer port, drop rclone from compose/env/Dockerfile"
```

---

## Task 12: Rip rclone from crontab + paths + poll_flags

**Files:**
- Modify: `ops/crontab`
- Modify: `src/findajob/paths.py`
- Modify: `scripts/poll_flags.py`
- Modify: `tests/test_poll_flags.py`

- [ ] **Step 1: Remove the rclone cron entry**

In `ops/crontab`, delete the block:

```
# ── Google Drive sync (gated by env, disabled by default) ────────────────────
*/15 *   *  *  *   [ "$FINDAJOB_JOBSYNC_ENABLED" = "true" ] && rclone copy --update /app/companies/ "$FINDAJOB_JOBSYNC_REMOTE"
```

- [ ] **Step 2: Remove `RCLONE` export from `src/findajob/paths.py`**

Delete the line `RCLONE: str = _cfg.get("RCLONE", "/usr/bin/rclone")` and any surrounding blank lines.

- [ ] **Step 3: Remove rclone helpers from `scripts/poll_flags.py`**

Delete the three helpers `_rclone_sync`, `_rclone_delete`, `_rclone_move` (lines ~45–105). Delete the `from findajob.paths import BASE, RCLONE` import and replace with `from findajob.paths import BASE`. Search for remaining call sites (`_rclone_sync(`, `_rclone_delete(`, `_rclone_move(`, `RCLONE`) and remove them. The caller locations around lines 576–578 are the folder-move comment block — delete the rclone half, keep the folder move itself.

After this pass, `grep -n rclone scripts/poll_flags.py` must return no matches.

- [ ] **Step 4: Drop rclone tests and mocks from `tests/test_poll_flags.py`**

Remove the `monkeypatch.setattr(poll_flags_mod, "RCLONE", "/bin/true")` line (around line 178). Remove any test methods that exist solely to exercise rclone behavior. Remove the "Mocks Google Sheets API, rclone subprocess" phrasing from the module docstring.

After this pass, `grep -n -i rclone tests/test_poll_flags.py` must return no matches.

- [ ] **Step 5: Run the poll_flags tests**

```bash
pytest tests/test_poll_flags.py -v
```

Expected: all remaining tests pass.

- [ ] **Step 6: Commit**

```bash
git add ops/crontab src/findajob/paths.py scripts/poll_flags.py tests/test_poll_flags.py
git commit -m "refactor: rip rclone from crontab, paths, poll_flags"
```

---

## Task 13: Rip rclone from prep_application + notify + sync_sheet + tests

**Files:**
- Modify: `scripts/prep_application.py`
- Modify: `scripts/notify.py`
- Modify: `scripts/sync_sheet.py`
- Modify: `tests/test_prep_pipeline.py`

- [ ] **Step 1: Strip rclone from `scripts/prep_application.py`**

Change the import line:

```diff
-from findajob.paths import AICHAT, BASE, PANDOC, RCLONE
+from findajob.paths import AICHAT, BASE, PANDOC
```

Delete the two rclone blocks around lines 486–510:
- The `rclone_immediate_push` block (the `subprocess.run([RCLONE, "copy", "--update", ...])` call with its try/except and `log_event("rclone_immediate_push_failed", ...)`).
- The `rclone link` block (the `subprocess.run([RCLONE, "link", ...])` call). The Drive-URL-to-cell-formula logic that depended on its output: remove too. The cell for the company column becomes plain company name.

After this pass, `grep -n rclone scripts/prep_application.py` must return no matches.

- [ ] **Step 2: Strip rclone from `scripts/notify.py`**

Delete:
- Lines ~266–270: "Check rclone sync health" block.
- Lines ~366–372: rclone conflict-file check.
- Lines ~406–426: the `RCLONE = ...` lazy import and `rclone lsf` check.

After this pass, `grep -n -i rclone scripts/notify.py` must return no matches.

- [ ] **Step 3: Simplify the company column in `scripts/sync_sheet.py`**

Find wherever the company column value is built as a Google Drive hyperlink formula (search for `=HYPERLINK` or `rclone` in `sync_sheet.py`). Replace with a plain-text company name.

After this pass, `grep -n rclone scripts/sync_sheet.py` must return no matches.

- [ ] **Step 4: Drop rclone tests from `tests/test_prep_pipeline.py`**

Remove these tests (lines ~285–410):
- `test_rclone_link_success_stores_url`
- `test_rclone_link_failure_leaves_null`
- the `class TestRcloneLink` (or equivalent container class) if it exists

After this pass, `grep -n -i rclone tests/test_prep_pipeline.py` must return no matches.

- [ ] **Step 5: Run the test suite**

```bash
pytest -x
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add scripts/prep_application.py scripts/notify.py scripts/sync_sheet.py tests/test_prep_pipeline.py
git commit -m "refactor: rip rclone from prep_application, notify, sync_sheet, and tests"
```

---

## Task 14: Extend container smoke test

**Files:**
- Modify: `scripts/test_container_integration.sh`

- [ ] **Step 1: Add viewer smoke checks**

Read the existing `scripts/test_container_integration.sh` to understand its structure (it was rewritten as PR3 of v0.1.1 per #119). After the existing "triage produces scored jobs" check, add a block:

```bash
# ── Materials viewer smoke ─────────────────────────────────────────────────
echo "=== Materials viewer smoke ==="

# The compose fixture should publish 8090 on host port ${TEST_MATERIALS_PORT:-18090}.
VIEWER_PORT="${TEST_MATERIALS_PORT:-18090}"

HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:${VIEWER_PORT}/healthz" || echo "FAIL")
if [ "$HTTP_CODE" != "200" ]; then
  echo "FAIL: /healthz returned $HTTP_CODE (expected 200)"
  exit 1
fi
echo "PASS: /healthz returned 200"

BODY=$(curl -s "http://localhost:${VIEWER_PORT}/" || echo "FAIL")
if ! echo "$BODY" | grep -q "In flight"; then
  echo "FAIL: index did not contain 'In flight'"
  exit 1
fi
echo "PASS: index renders with expected sections"

# Verify rclone is not in the image
if docker compose exec -T "$SERVICE_NAME" which rclone >/dev/null 2>&1; then
  echo "FAIL: rclone is still in the image"
  exit 1
fi
echo "PASS: rclone absent from image"
```

Match the shell-variable names (`$SERVICE_NAME`, etc.) to whatever the existing script uses — read it first.

- [ ] **Step 2: Ensure the compose used by the smoke test exposes port 18090**

Look for the test-only compose override the smoke script uses (probably `scripts/fixtures/compose.test.yaml` or an inline `docker compose -f ...`). Add a port mapping so the viewer is reachable:

```yaml
    ports:
      - "${TEST_MATERIALS_PORT:-18090}:8090"
```

If the smoke script uses the bundled `ops/compose.yaml.example` and sets `FINDAJOB_MATERIALS_PORT=18090` in a test `.env`, that's equivalent — just make sure 18090 is the value.

- [ ] **Step 3: Syntax check**

```bash
sh -n scripts/test_container_integration.sh
```

Expected: no output.

- [ ] **Step 4: Commit**

```bash
git add scripts/test_container_integration.sh
git commit -m "test(container): extend fresh-install smoke with viewer + rclone-absent"
```

---

## Task 15: Docs update

**Files:**
- Modify: `docs/setup/install-docker.md`
- Modify: `docs/setup/state-migration.md`
- Modify: `docs/operations.md`
- Modify: `docs/architecture.md`
- Modify: `README.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: `docs/setup/install-docker.md`**

- Delete any "rclone", "jobsync", "Google Drive sync" sections.
- Add a subsection under "Configuration" (or create one) titled "Web materials viewer":
  - `FINDAJOB_MATERIALS_PORT` — per-stack host port for the viewer. Document that each stack picks a unique free port starting at 8090.
  - Access URL: `http://docker.lan:<port>/` from the LAN or via Wireguard.
- In any install-order sections, replace "configure rclone" steps with "set `FINDAJOB_MATERIALS_PORT` in your stack `.env`".

- [ ] **Step 2: `docs/setup/state-migration.md`**

Add a new section "Migrating from rclone/Drive to the materials viewer (v0.1.x → v0.2.0)":

```
# Migrating from rclone/Drive to the materials viewer

Applies to operator stacks that were running with `FINDAJOB_JOBSYNC_ENABLED=true`
on v0.1.x. Testers on fresh installs can skip this — they never had rclone enabled.

## Steps

1. Stop the stack:  docker compose down
2. Remove the now-unused bind mount:
     rm -rf state/rclone
3. Edit .env to add:
     FINDAJOB_MATERIALS_PORT=8090   # or next free port if 8090 is taken
4. Edit compose.yaml:
   - Remove the line:   - ./state/rclone:/app/.config/rclone
   - Remove the env:    FINDAJOB_JOBSYNC_ENABLED
   - Add a ports block:
       ports:
         - "${FINDAJOB_MATERIALS_PORT}:8090"
5. Pull and start:
     docker compose pull
     docker compose up -d
6. Verify:
     curl http://docker.lan:8090/healthz    # expect: ok
     open http://docker.lan:8090/           # browse materials

## What happens to existing Drive folders

Nothing automated. The Drive folders synced by rclone remain. Delete them
manually at drive.google.com if/when you want; findajob will never look at
them again.
```

- [ ] **Step 3: `docs/operations.md`**

Remove any reference to jobsync, rclone, or the `FINDAJOB_JOBSYNC_*` env vars. Add a brief note under a "Deployed surfaces" heading (or create one) that the container now publishes the materials viewer on the port configured by `FINDAJOB_MATERIALS_PORT`.

- [ ] **Step 4: `docs/architecture.md`**

Remove the rclone/Drive layer from any ASCII or mermaid diagrams. Add the materials viewer process to the container shape (uvicorn + supercronic inside one container).

- [ ] **Step 5: `README.md`**

Remove any "Google Drive" or "rclone" bullet from the feature list or setup instructions. If the README has a "Getting Started" section that mentions `FINDAJOB_JOBSYNC_ENABLED`, remove the mention.

- [ ] **Step 6: `CLAUDE.md`**

In §"Container Context", update the table:

- Add a row for the materials viewer process: "uvicorn findajob.web.app:create_app --factory" on port 8090 inside the container.
- Remove the rclone row.
- Update any path table entries that mention `/app/.config/rclone`.

In §"Key File Locations", remove any rclone-related entries. Add entries for `src/findajob/web/` and its submodules.

- [ ] **Step 7: Commit**

```bash
git add docs/setup/install-docker.md docs/setup/state-migration.md docs/operations.md docs/architecture.md README.md CLAUDE.md
git commit -m "docs: document materials viewer; remove rclone/Drive references"
```

---

## Task 16: CHANGELOG + whole-feature verification

**Files:**
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Add `[Unreleased]` entry**

At the top of `CHANGELOG.md`, under `## [Unreleased]` (create the section if missing), add:

```markdown
## [Unreleased]

### Added
- Web materials viewer (`#59`): local FastAPI service serves prep-folder contents
  on `http://docker.lan:<port>/`. Replaces Google Drive folder browsing.

### Removed
- rclone integration and Google Drive sync (`#29`, `#59`). `FINDAJOB_JOBSYNC_*`
  env vars deleted; `state/rclone/` bind mount no longer used; `rclone` removed
  from the container image (~50 MB smaller).

### Migration required

Operators on prior versions who had `FINDAJOB_JOBSYNC_ENABLED=true` must
perform a one-time stack update — see `docs/setup/state-migration.md` for
the exact commands. Testers on fresh installs are unaffected.
```

- [ ] **Step 2: Run the full test suite one more time**

```bash
pytest -x
```

Expected: all pass.

- [ ] **Step 3: Run ruff and mypy**

```bash
pip3 install --break-system-packages -e ".[dev]"
ruff check .
mypy src/findajob tests
```

Expected: both pass.

- [ ] **Step 4: Build the container locally and smoke it**

```bash
docker build -t findajob:test .
```

Then spin up a test compose with `FINDAJOB_MATERIALS_PORT=18090`, wait for supercronic to print its ready line, and verify:

```bash
curl -sf http://localhost:18090/healthz    # expect: ok
curl -s http://localhost:18090/ | grep "In flight"
docker run --rm findajob:test which rclone    # expect: non-zero exit
```

- [ ] **Step 5: Commit CHANGELOG**

```bash
git add CHANGELOG.md
git commit -m "docs(changelog): add unreleased entries for web viewer + rclone removal"
```

- [ ] **Step 6: Push branch and open PR**

```bash
git push -u origin feat/59-web-materials-viewer
gh pr create --title "feat: web materials viewer (14a / #59); rip rclone" --label migration-required --body "$(cat <<'EOF'
## Summary

- Ships `src/findajob/web/` — FastAPI viewer on per-stack host port.
- Retires rclone + Google Drive sync entirely (closes #29 as part of the same change).
- Tagged `migration-required`; one-time operator stack update documented in `docs/setup/state-migration.md`.

## Spec / Plan

- Spec: `docs/superpowers/specs/2026-04-20-web-materials-viewer-design.md`
- Plan: `docs/superpowers/plans/2026-04-20-web-materials-viewer.md`

## Test plan

- [x] `pytest -x` green
- [x] `ruff check .` green
- [x] `mypy` green
- [x] Container smoke (`scripts/test_container_integration.sh`) passes with the new viewer + rclone-absent checks
- [x] Local `docker compose up -d` → `curl http://localhost:<port>/healthz` returns 200
- [ ] Post-merge deploy: verify both stacks on docker.lan serve at their configured ports

EOF
)"
```

---

## Documentation impact

| Surface | Change | Task |
|---|---|---|
| `docs/setup/install-docker.md` | Add `FINDAJOB_MATERIALS_PORT` + access URL; remove rclone/Drive/jobsync sections | 15 |
| `docs/setup/state-migration.md` | New section: one-time operator cleanup (rm state/rclone, edit compose) | 15 |
| `docs/operations.md` | Remove jobsync references; add viewer under deployed surfaces | 15 |
| `docs/architecture.md` | Remove rclone/Drive layer; add uvicorn process to container shape | 15 |
| `README.md` | Remove Drive/rclone feature bullets and env-var mentions | 15 |
| `CLAUDE.md` §"Container Context" | Remove rclone rows; add materials-viewer process + paths | 15 |
| `CLAUDE.md` §"Key File Locations" | Add `src/findajob/web/`; remove rclone references | 15 |
| `CHANGELOG.md` [Unreleased] | "Added: viewer", "Removed: rclone", Migration required block | 16 |
| Issue #59 `## Planning` | Cite spec and plan | 1 |
| Spec docstring (already written) | References this plan path | (already in spec) |

## Whole-feature verification

After all 16 tasks are complete and the PR is in draft, run this gate (distinct from per-task checks) against `feat/59-web-materials-viewer`:

1. **`pytest -x`** — entire test suite green on the final commit.
2. **`ruff check . && mypy src/findajob tests`** — lint + type clean.
3. **`sh -n ops/entrypoint.sh`** — entrypoint is syntactically valid.
4. **`grep -r rclone src/ scripts/ ops/ tests/ Dockerfile pyproject.toml`** — **no matches**. This is the rip-completeness gate.
5. **Container build**: `docker build -t findajob:test .` succeeds; image is smaller than main's `:latest` by roughly the rclone package size (~50 MB).
6. **Container smoke**: `scripts/test_container_integration.sh` passes including the new viewer + rclone-absent checks.
7. **End-to-end on docker.lan (operator stack in dev)**: `FINDAJOB_MATERIALS_PORT=8090 docker compose up -d`; `curl http://docker.lan:8090/healthz` returns 200; browser navigation into a real folder renders markdown correctly; `.docx` downloads.
8. **Issue #59 board state**: Status=In Progress, `## Planning` section cites both spec and plan.

If any step fails, fix at the root rather than patching around. Do not mark the PR ready for review until all eight pass.

## Self-review checklist

This plan is complete against the spec if:

- [x] **Decision 1 (per-stack host port, no LAN proxy)** — Task 11 adds `ports:` to compose.example; Task 15 documents port-allocation convention.
- [x] **Decision 2 (FastAPI + Jinja2 + uvicorn)** — Task 2 adds deps; Tasks 5–9 build on FastAPI + Jinja2; Task 10 launches uvicorn.
- [x] **Decision 3 (stage-grouped index, rejected in `<details>`)** — Task 8 implements the grouping + `<details>`.
- [x] **Decision 4 (full rclone rip, `migration-required`)** — Tasks 11, 12, 13 rip all rclone; Task 16 adds the migration-required note + PR label.
- [x] **Decision 5 (no Google Docs integration)** — `.docx` served as attachment in Task 7; no Drive/Docs code added.

- [x] **Routes (/, /materials/{fp}, /materials/{fp}/{filename}, /healthz)** — Tasks 5, 6, 7, 8.
- [x] **Path-traversal guards** — Task 4 (unit tests on resolver) + Task 7 (filename guard in the route).
- [x] **Fingerprint resolution across active / `_applied/` / `_waitlisted/` / `_rejected/`** — Task 3 tests all four locations.
- [x] **404 policy (unknown fingerprint / missing folder / bad filename)** — Tasks 3, 6, 7.
- [x] **Markdown renders inline; `.docx` attachment; `.txt` inline; other attachment** — Task 7.
- [x] **Index page per-section cap at 50 with "and more"** — Task 8 implements the cap.
- [x] **Integration test (TestClient + tmpdir + scratch DB)** — Task 9.
- [x] **Container smoke extended with viewer + rclone-absent** — Task 14.
- [x] **Entrypoint launches uvicorn + SIGTERM trap + drops rclone chown** — Task 10.
- [x] **Compose / env / Dockerfile changes** — Task 11.
- [x] **rclone rip in crontab + paths + poll_flags + prep_application + notify + sync_sheet + tests** — Tasks 12, 13.
- [x] **Docs update (all surfaces in Documentation Impact table)** — Task 15.
- [x] **CHANGELOG [Unreleased] entry** — Task 16.
- [x] **Issue #59 gets `## Planning` section + moves to In Progress** — Task 1.

No spec section lacks an implementing task.
