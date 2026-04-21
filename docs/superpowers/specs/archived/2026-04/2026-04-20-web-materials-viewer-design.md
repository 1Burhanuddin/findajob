---
**Shipped in #14, #59 on 2026-04-21. Final decisions captured in issue body.**
---

# Web Materials Viewer — Design (14a / #59)

First ship of Phase 4. Replace Google Drive folder-browsing with a bare HTTP viewer that serves prep-application folder contents from local disk, and rip out rclone + `jobsync` in the same release.

## Issue(s)

- #59 — Web frontend 14a: materials viewer (retires rclone/Drive). In Up Next.
- Parent: #14 — Web dashboard to replace Google Sheets (closed; 14a–14f sub-phases track execution).

## Context

Today, prep folders land in `companies/<folder>/` on the docker.lan host. rclone syncs them to Google Drive every 15 minutes so that the operator can click "open in Docs", edit, and export as PDF. The sync layer has four known pain points (#29): lag, duplicates, stale folders, and `.path1/.path2` conflict artifacts. It also requires per-tester Drive OAuth, which is the same wall blocking #115 for Gmail.

14a retires this entirely. The operator opens `http://docker.lan:<port>/` on the LAN (or via Wireguard from anywhere) and browses the prep folders directly. Markdown renders inline; `.docx` downloads for local edit. Edits land back in the app in 14c (#61).

## Decisions

1. **Per-stack host port, no LAN reverse proxy.** Matches the pattern every other service on docker.lan already uses (dozzle, portainer, archivebox). Synology handles the internet edge for services that need it; findajob stays LAN-only. URL shape: `http://docker.lan:8090/materials/<fp>`. Each stack assigns its own port via `FINDAJOB_MATERIALS_PORT` in its `.env`.
2. **FastAPI + Jinja2 + uvicorn.** The phase-4 arc will want async later (SSE in 14c, stats endpoints in 14e); starting with FastAPI avoids a framework migration. Size cost over Flask is negligible for the 14a scope.
3. **Index groups by lifecycle stage.** Four sections: In flight / Applied / Waitlisted / Rejected. Rejected is collapsed under `<details>` at the bottom (HTML-native, no JS). Per-section cap at 50 rows with "…and N more" string; no pagination in 14a.
4. **Full rclone rip in 14a, `migration-required` label.** Feature-flag-first was considered and rejected — the flag would just delay cleanup. The one real use-case for Drive (open .docx in Google Docs to edit) is replaced by a browser download. Alice never had rclone enabled, so her migration is trivial. Operator's existing Drive folders are left untouched; operator deletes manually if desired.
5. **No Google Docs integration.** A "Download" button on `.docx` files; user drags into Drive if they want to edit in Docs. Drive-upload via API was considered (option B in brainstorm) and rejected — OAuth cost is out of scope for 14a, and would duplicate the auth wall currently blocking #115. No follow-up issue; keep minimal.

## Architecture

New FastAPI service runs inside the existing `findajob` container. Entrypoint stays a single command. Order:

```
init_db.py → seed aichat-ng config → launch uvicorn in background → exec supercronic
```

Supercronic remains PID 1 so compose's `restart: unless-stopped` watches the right process. A bash `trap` on SIGTERM forwards to uvicorn's PID so the app shuts down cleanly on `docker compose down`.

Uvicorn is not auto-restarted if it crashes; the pipeline keeps running regardless. `/healthz` is the outside-observable signal. If the viewer is down, operator restarts the container. In-container supervisor (s6, foreman) is out of scope for 14a.

Hard-coded listener inside the container: `0.0.0.0:8090`. Externalization happens at the compose `ports:` mapping — the app itself is config-free.

No new container. No DB writes. No reverse proxy. No auth. Wireguard is the perimeter.

### File layout

```
src/findajob/web/
  __init__.py
  app.py                  FastAPI app factory, Jinja2 config, startup hook
  routes.py               /, /materials/{fp}, /materials/{fp}/{file}, /healthz
  folder_resolver.py      fingerprint → filesystem path + path-traversal guards
  templates/
    base.html
    index.html
    folder.html
```

## Routes

```
GET /                           Index page (stage-grouped list, see below).
GET /materials/{fingerprint}    Folder view — lists files in the matching companies/ folder.
GET /materials/{fingerprint}/{filename}
                                File serve. Content headers vary by extension:
                                  .md   → text/html, rendered inline (Python-Markdown)
                                  .txt  → text/plain, inline
                                  .docx → attachment (browser Download)
                                  other → attachment
GET /healthz                    200 "ok" if /app/companies/ exists; 503 otherwise.
```

### Fingerprint resolution

`jobs.fingerprint` → `jobs.prep_folder` via one SQLite query per request. `prep_folder` holds the folder name including any prefix (`_applied/Meta_SWE_...`, `_waitlisted/...`, or bare active folder). The resolver joins `BASE/companies/` + `prep_folder` and resolves symlinks; result must be a descendant of `BASE/companies/` or request returns 404.

### 404 policy

- Unknown fingerprint → 404 with a plain-HTML message.
- Fingerprint exists in DB but folder doesn't exist on disk → 404 with one-line diagnostic ("expected folder X, not found on disk").
- `filename` that isn't a direct child of the resolved folder → 404.

## Index page

Four sections, HTML-native:

```
## In flight     jobs.stage IN ('materials_drafted', 'prep_in_progress')
## Applied       jobs.stage IN ('applied', 'interview', 'offer')
## Waitlisted    jobs.stage = 'waitlisted'

<details>
  <summary>Rejected (N)</summary>
  jobs.stage IN ('rejected', 'not_selected')
</details>
```

Row format (single line per job):

```
{Company} — {Title}  [score]  ({stage})  {applied_date if set}  → /materials/{fp}
```

Sort: Applied section newest-first by `applied_date`; all others by `created_at` desc. Per-section cap at 50 with "…and N more" sentinel.

Styling: one inline `<style>` block in `base.html`. No external CSS, no JS, no framework. Desktop-first; phone-usable but not responsive.

## rclone retirement

Full rip in the same PR. Tagged `migration-required`.

### Files modified or deleted

```
ops/crontab                  remove */15 rclone entry (line 17)
ops/compose.yaml.example     remove ./state/rclone volume; add ports: "${FINDAJOB_MATERIALS_PORT}:8090"
ops/entrypoint.sh            drop /app/.config/rclone from chown loop; launch uvicorn
ops/stack.env.example        drop FINDAJOB_JOBSYNC_* vars; add FINDAJOB_MATERIALS_PORT
Dockerfile                   drop `rclone` from apt install (saves ~50 MB); add Python web deps
src/findajob/paths.py        drop RCLONE export
scripts/poll_flags.py        delete _rclone_sync / _rclone_delete / _rclone_move + call sites
scripts/prep_application.py  drop rclone_immediate_push + Drive hyperlink cell formula
scripts/notify.py            drop rclone health checks
scripts/sync_sheet.py        company column becomes plain text (was Drive hyperlink); simplify
tests/test_poll_flags.py     drop rclone-related tests
tests/test_prep_pipeline.py  drop rclone-related tests
pyproject.toml               add fastapi, uvicorn[standard], jinja2, markdown
```

### Operator migration (one-time, documented)

```
docker compose down
rm -rf state/rclone
# Edit .env:  add FINDAJOB_MATERIALS_PORT=8090 (pick a free port)
# Edit compose.yaml: remove state/rclone volume; add ports: "${FINDAJOB_MATERIALS_PORT}:8090"
docker compose pull
docker compose up -d
```

### Drive folder cleanup

- Operator stack: existing Drive folders left untouched. Operator deletes manually if desired.
- Alice Doe and future testers: `FINDAJOB_JOBSYNC_ENABLED=false` was already the default, so nothing in Drive. Just the empty `state/rclone/` bind-mount directory to remove.

## Testing

### Unit — `tests/test_web_materials.py` (new)

- Fingerprint → folder path resolution across active / `_applied/` / `_waitlisted/` / `_rejected/`.
- Path-traversal guard: reject `../foo`, absolute paths, symlinks pointing outside `companies/`.
- Content-Type and Content-Disposition by extension.
- 404 on unknown fingerprint.
- 404 on known fingerprint with missing folder on disk.
- Markdown rendering: h1, code block, link work; raw HTML in source is escaped (no stored XSS).
- Index query: correct `stage` → section mapping.

### Integration — `tests/test_web_integration.py` (new)

FastAPI `TestClient` against a tmpdir `companies/` tree and a scratch SQLite seeded with representative rows across all four stage groups.

- `GET /` → 200, contains each section header, correct row counts per section.
- `GET /materials/<fp>` → 200, lists expected files.
- `GET /materials/<fp>/<file>.md` → 200, rendered HTML.
- `GET /materials/<fp>/<file>.docx` → 200 with `Content-Disposition: attachment`.
- `GET /healthz` → 200.

### Container integration — `scripts/test_container_integration.sh` (extend)

After the existing fresh-install smoke:

- `curl http://localhost:${MATERIALS_PORT}/healthz` returns 200.
- `curl http://localhost:${MATERIALS_PORT}/` returns 200 and contains "In flight".
- `docker exec <container> which rclone` returns non-zero (binary gone).

### Manual verification (on docker.lan, post-deploy)

- `http://docker.lan:8090/` (operator) and `http://docker.lan:8091/` (Alice) both render.
- Click into one folder; markdown renders.
- `.docx` downloads cleanly.
- Confirm rclone is absent from the image.

### CI

Existing ruff + mypy + pytest pass. No new linters, no new CI jobs (except the extended container smoke, which already runs in `.github/workflows/ci.yml` per #124's follow-up).

## Deployment

### Compose diff (per stack)

```diff
 services:
   scheduler:
     image: ghcr.io/brockamer/findajob:${FINDAJOB_IMAGE_TAG:-v0.1}
+    ports:
+      - "${FINDAJOB_MATERIALS_PORT}:8090"
     environment:
       TZ: ${FINDAJOB_TZ:-America/New_York}
       ...
-      FINDAJOB_JOBSYNC_ENABLED: ${FINDAJOB_JOBSYNC_ENABLED:-false}
     volumes:
       - ./state/data:/app/data
       - ./state/config:/app/config
       - ./state/candidate_context:/app/candidate_context
       - ./state/companies:/app/companies
       - ./state/logs:/app/logs
       - ./state/aichat_ng:/app/.config/aichat_ng
-      - ./state/rclone:/app/.config/rclone
```

### Port allocation convention

Documented in `docs/setup/install-docker.md`. Port allocations are recorded per-stack starting at 8090 and incrementing; each new tester takes the next free port. (Specific current allocations live in the operator's private config, not this spec.)

## Documentation impact

| Surface | Change |
|---|---|
| `docs/setup/install-docker.md` | Document `FINDAJOB_MATERIALS_PORT`; replace rclone/Drive sections with materials-viewer access; update install order. |
| `docs/setup/state-migration.md` | New subsection: operator one-time cleanup (`rm -rf state/rclone`, edit compose). |
| `docs/operations.md` | Remove jobsync references; document materials viewer as part of the deployed surface. |
| `docs/architecture.md` | Remove rclone/Drive layer from diagrams; add viewer to the container process shape. |
| `README.md` | Update any rclone/Drive mentions. |
| `CHANGELOG.md` | Entry under `[Unreleased]`: "Web materials viewer replaces Google Drive browsing; rclone removed (migration-required)." |
| `CLAUDE.md` | §"Container Context" adds materials viewer process; binary paths section no longer mentions rclone. |
| `docs/roadmap.md` | Mark 14a shipped. |

## Non-goals (explicit)

- Editing, upload, or any write operation. (→ 14c / #61)
- Auth, login, sessions, tokens.
- Dashboard / Applied / Waitlist / Review UI. (→ 14b / #60)
- Search, filter, sort controls.
- Stats, trending, history. (→ 14e / #63)
- Manual JD ingest form. (→ 14d / #62)
- Google Docs / Drive integration (no follow-up issue).
- Internet exposure (Synology edge handles any future need).
- Server-side PDF generation or LibreOffice headless.
- Mobile-responsive styling.
- Pagination or virtual scrolling controls.
