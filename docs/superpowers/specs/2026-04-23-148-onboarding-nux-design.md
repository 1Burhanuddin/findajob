# Onboarding NUX + Interview → Config Injection — Design Spec

## Issue(s)
#148 — Web UI: onboarding NUX + interview → config injection pipeline

**Date:** 2026-04-23
**Status:** Approved for implementation.
**Depends on:** #60 (web UI exists), #61 (write workflows). Both Done.
**Blocks:** #11 (setup guide cannot accurately describe first-run until this lands).

---

## Problem

The onboarding interviewer role (`config/roles/onboarding_interviewer.md`) emits seven delimited config files today, but getting those files from the LLM chat into a running stack is a manual step the operator performs by hand. A fresh stack exposes an empty pipeline with no guidance — a user who deploys the image sees a blank Board and has no path forward.

This spec delivers:

1. A first-run **NUX** that redirects an unconfigured stack to an onboarding page.
2. A **paste-back injector** that parses the interview's delimited emission and writes the seven files to their canonical paths.
3. A `/tools/` entry that makes the full interview re-triggerable with a backup-first guarantee.

---

## Architecture decision

**Paste-back (external LLM + structured paste form), styled with link-out to the user's chosen LLM where the platform supports pre-filled prompts.**

Alternatives considered and rejected:

- **In-UI embedded LLM chat.** Rejected because (a) it requires an Anthropic API key configured before onboarding — the chicken-and-egg that onboarding is supposed to solve; (b) it couples every interview-prompt tweak to a stack redeploy, regressing the current "edit → test on claude.ai → commit" loop; (c) the user is already paying for a Pro-tier reasoning LLM per `docs/onboarding-prework-checklist.md`, making it cheaper and more capable for them to run the interview there than routing through our key.
- **Progressive paste (seven fields, filled as the interview gates through files).** Rejected because it couples the user's workflow to keeping our tab open for 90 minutes; one-shot paste is more resilient.

Coherent with **#150** (/tools/ page), which already chose paste-back + link-out for its Phase 1.

---

## Paste form shape

One textarea. The user pastes the full chat transcript, or just the seven delimited blocks, or anything in between. The parser scans for the delimiters and extracts only what it needs.

---

## Re-run semantics

- **Full re-run only.** Partial updates (e.g., "just refresh my exclusions") are #150's territory — they require separate curated prompts and are explicitly out of scope here.
- **Backup-then-overwrite.** Every re-run copies existing destinations to `{base_root}/.backups/{UTC-ISO-basic}/` before injecting. (On the host: `state/.backups/...`. Inside the container: `/app/.backups/...`.)

---

## Components

Seven pieces, all FastAPI-side:

1. **`/onboarding/` landing page** — new route. Renders prework checklist inline, "Open in Claude / ChatGPT / Gemini" buttons (pre-filled where the platform URL-scheme supports it), a "copy the prompt" button that serves `config/roles/onboarding_interviewer.md` verbatim, and the paste form. `?mode=rerun` flips the page to show a backup warning banner.
2. **`/onboarding/inject` POST** — new route. Takes the pasted blob, runs parser + injector + derivation + sentinel, redirects to `/board/` on success or re-renders the form on failure.
3. **`findajob.onboarding.parser`** — new module, pure functions. `parse_emission(blob: str) -> ParsedEmission` returns `(found: dict[str, str], missing: list[str], unknown: list[str])`. No FastAPI import.
4. **`findajob.onboarding.injector`** — new module, pure functions. `backup_existing(base_root, stamp) -> Path`, `write_files(base_root, files)` (atomic staging then os.replace), `derive_companies_of_interest(target_companies_md: str) -> str`, `mark_complete(base_root) -> None`, `is_complete(base_root) -> bool`.
5. **NUX guard** — FastAPI dependency attached to the `board`, `materials`, and `stats` router includes. Redirects 307 → `/onboarding/` when the sentinel is absent. Sentinel presence cached in `app.state.onboarding_complete` for the fast path; reset in the inject handler.
6. **`/tools/` update** — add an "Run onboarding interview" card above the existing "Edit config files" entry on `templates/tools/index.html`. Links to `/onboarding/?mode=rerun`.
7. **`findajob.web.config_files` update** — extend `EDITABLE_CATEGORIES` so `config/target_companies.md` and `config/business_sector_employers_reference.md` are editable via `/config/` post-injection.

---

## Data flow

### First run

```
GET /board/  (user's first visit to the stack)
  → NUX guard: sentinel missing
  → 307 /onboarding/

GET /onboarding/
  → renders: prework, link-out buttons, "copy prompt" action, paste form

[user runs the 90-minute interview in claude.ai / ChatGPT / Gemini]

POST /onboarding/inject  with body=<pasted blob>
  → parse_emission(blob) → (found=7 files, missing=[], unknown=[])
  → backup_existing(base_root, "20260423T180530Z") → {base_root}/.backups/20260423T180530Z/ (empty on first run)
  → write_files (atomic: stage all 7 to tempfiles, then os.replace in order)
  → derive_companies_of_interest(found["target_companies.md"]) → write config/companies_of_interest.txt
  → mark_complete() → write {base_root}/data/.onboarding-complete with UTC timestamp
  → app.state.onboarding_complete = True
  → 303 redirect to /board/

GET /board/  (second request)
  → NUX guard: sentinel present → pass through
```

### Re-run from /tools/

```
GET /tools/ → user clicks "Run onboarding interview"
GET /onboarding/?mode=rerun
  → page renders with warning banner:
    "Existing config will be backed up to {base_root}/.backups/<ts>/ before overwrite.
     For partial updates (e.g., add an exclusion category), use /config/ directly."
  → paste form, same endpoint

POST /onboarding/inject
  → parser / backup / inject / derive / sentinel (all the same)
  → backup_existing this time copies the 7 existing files + companies_of_interest.txt + sentinel
```

### Parse failure

```
POST /onboarding/inject with blob missing one block
  → parse_emission → found=6, missing=["in_domain_patterns.yaml"], unknown=[]
  → NO backup, NO writes, NO sentinel changes
  → re-render /onboarding/ with:
    - original textarea content preserved
    - red error box: "The paste is missing in_domain_patterns.yaml. Go back to your
      chat, find the <<<FILE: in_domain_patterns.yaml>>> block, and paste again."
  → HTTP 400
```

---

## Parser spec

`findajob.onboarding.parser.parse_emission(blob: str) -> ParsedEmission`

**Data class:**

```python
@dataclass(frozen=True)
class ParsedEmission:
    found: dict[str, str]       # filename -> raw content
    missing: list[str]          # required filenames not present
    unknown: list[str]          # filenames in delimiters but not in the allowlist
```

**Delimiter regex:**

```
<<<FILE:\s*(?P<name>[^>]+?)\s*>>>\r?\n(?P<body>.*?)\r?\n<<<END FILE:\s*(?P=name)\s*>>>
```

Flags: `re.DOTALL` (so `.*?` spans newlines).

**Tolerant of:**

- Blocks embedded in a larger transcript (text outside the delimiters is ignored).
- Code fences wrapping the blocks (` ``` ` at either edge — stripped from body).
- Whitespace padding around the filename inside the delimiter.
- Any line-ending style (CRLF / LF).

**Strict about:**

- The filename between `<<<FILE:` and `>>>` must match one of the seven allowlisted names exactly. Unknown names go into `unknown` — they are not silently dropped and not silently injected.
- Every opened `<<<FILE: name>>>` must have a matching `<<<END FILE: name>>>`. A dangling open tag means that block is not captured.
- Duplicate blocks for the same filename: last occurrence wins (the interview may emit a "redo" sequence).

**Allowlisted filenames** (exactly these seven):

```
profile.md
master_resume.md
target_companies.md
business_sector_employers_reference.md
jsearch_queries.txt
prefilter_rules.yaml
in_domain_patterns.yaml
```

---

## Injection spec

### Target paths

| Emitted file | Destination (relative to `base_root`) |
|---|---|
| `profile.md` | `candidate_context/profile.md` |
| `master_resume.md` | `candidate_context/master_resume.md` |
| `target_companies.md` | `config/target_companies.md` |
| `business_sector_employers_reference.md` | `config/business_sector_employers_reference.md` |
| `jsearch_queries.txt` | `config/jsearch_queries.txt` |
| `prefilter_rules.yaml` | `config/prefilter_rules.yaml` |
| `in_domain_patterns.yaml` | `config/in_domain_patterns.yaml` |

Plus derivation: `config/companies_of_interest.txt` ← Tier 1 section of `target_companies.md` (one company name per line, trimmed, no bullet marker, blank lines suppressed).

### Tier 1 derivation

Parse `target_companies.md` for the `## Tier 1` section (case-insensitive heading match, accept `## Tier 1` through the next `## ` heading or EOF). Strip leading `- `, `* `, or `1. ` bullet markers. Strip trailing parenthetical commentary (e.g., `Meta — would take today` → `Meta`: split on em-dash or hyphen-space, keep only the part before). Drop blank lines. Write to `config/companies_of_interest.txt`.

### Backup

Before any write, for each destination in the mapping (plus `config/companies_of_interest.txt` and the sentinel), if it exists, copy to `{base_root}/.backups/{stamp}/` preserving the full relative path (e.g., `candidate_context/profile.md` → `{base_root}/.backups/{stamp}/candidate_context/profile.md`). Stamp = `datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")`. Empty backup dir is acceptable (first run).

### Atomicity

Stage: write each of the seven target contents + derivation content to a tempfile in the destination's directory (same pattern `/config/` editor uses: `tempfile.mkstemp(prefix=name+".", suffix=".tmp", dir=parent_dir)`).

Commit: only after all eight tempfiles are staged cleanly do we `os.replace` them into place, then touch the sentinel.

Rollback: any staging error → delete every tempfile + the backup dir (if it was created this run), raise. Zero mutations to existing files.

### Sentinel

`{base_root}/data/.onboarding-complete`:

```
2026-04-23T18:05:30Z
```

Written last. Presence gates the NUX guard. Content is advisory (for humans / support).

---

## NUX guard

FastAPI dependency attached per-router-include:

```python
# src/findajob/web/onboarding_guard.py
def require_onboarding_complete(request: Request) -> None:
    if getattr(request.app.state, "onboarding_complete", None) is True:
        return
    base_root: Path = request.app.state.base_root
    if is_complete(base_root):
        request.app.state.onboarding_complete = True
        return
    raise HTTPException(
        status_code=307,
        headers={"Location": "/onboarding/"},
    )
```

Attached to:
- `/board/*`
- `/materials/*`
- `/stats/*`

Not attached to (must stay reachable):
- `/onboarding/*`
- `/config/*`
- `/tools/*`
- `/ingest/*`
- `/healthz`
- `/static/*`
- `/` (landing page)

Design note: dependency rather than middleware so the guard is localized, testable per-router, and doesn't coincidentally gate unrelated routes like healthz or static assets.

The inject handler sets `app.state.onboarding_complete = True` after successful sentinel write, so the guard's fast path starts working on the next request without a filesystem check.

---

## /tools/ integration

`templates/tools/index.html` gets a new `<li>` at the top of the list:

```html
<li class="px-4 py-3">
  <a href="/onboarding/?mode=rerun" class="text-blue-600 hover:underline font-medium">
    Run onboarding interview
  </a>
  <p class="text-sm text-gray-600">
    Initial setup or full re-run after a major role pivot. Backs up existing config
    before overwriting. For partial updates, use "Edit config files" below.
  </p>
</li>
```

No backend change to `/tools/` itself — the card is a link.

---

## `/config/` editor allowlist update

`src/findajob/web/config_files.py`:

```python
EDITABLE_CATEGORIES: dict[str, list[str] | str] = {
    "Candidate context": [
        "candidate_context/profile.md",
        "candidate_context/master_resume.md",
    ],
    "Search config": [
        "config/target_companies.md",                        # + new
        "config/business_sector_employers_reference.md",     # + new
        "config/prefilter_rules.yaml",
        "config/in_domain_patterns.yaml",
        "config/jsearch_queries.txt",
        "config/feed_urls.txt",
    ],
    "Role prompts": "config/roles/*.md",
}
```

`companies_of_interest.txt` is intentionally NOT added to the editor — it is derived from `target_companies.md` at injection time, and letting users edit it directly would cause drift. Editing the Tier 1 section of `target_companies.md` via `/config/` is the supported path; a follow-up issue handles "pipeline reads `target_companies.md` directly, retiring `companies_of_interest.txt` altogether."

---

## Testing

### Unit tests

- `tests/test_onboarding_parser.py`:
  - Clean emission (seven blocks, nothing else) → `found=7, missing=[], unknown=[]`.
  - Full-transcript paste (chat turns around the blocks) → same.
  - One block missing → correct missing list, `found` has the other six.
  - Duplicate block → last wins.
  - Unknown filename → goes into `unknown`, not `found`.
  - Blocks wrapped in triple-backtick code fences → body extracted with fences stripped.
  - CRLF line endings → parsed correctly.
  - Dangling open delimiter with no close → treated as missing.

- `tests/test_onboarding_injector.py` (tmpdir for `base_root`):
  - First-run backup is an empty directory.
  - Re-run backup contains existing files under correct subpaths.
  - Atomic staging: inject partial-write failure (mock os.replace on file 5) → zero writes, backup dir removed.
  - Tier 1 derivation: fixture `target_companies.md` with known companies → `companies_of_interest.txt` contains them one-per-line, no bullets, no parentheticals.
  - Sentinel contains a parseable ISO 8601 Zulu timestamp.
  - `is_complete()` returns True iff sentinel file exists.

- `tests/test_config_files_onboarding.py`:
  - `target_companies.md` and `business_sector_employers_reference.md` are `is_editable()==True`.
  - `companies_of_interest.txt` is `is_editable()==False` (not on the allowlist).

### Route-level tests

`tests/test_onboarding_routes.py`:

- `GET /onboarding/` → 200, contains prework text and paste form.
- `POST /onboarding/inject` with clean blob → 303 to `/board/`, seven files on disk, sentinel present.
- `POST /onboarding/inject` with missing block → HTTP 400, re-renders form with preserved textarea content + error message naming the missing file(s), zero disk writes.
- `GET /onboarding/?mode=rerun` → renders warning banner.
- NUX guard: `GET /board/` with sentinel absent → 307 Location `/onboarding/`.
- NUX guard: `GET /board/` with sentinel present → passes through (not 307).
- NUX guard does NOT gate `/onboarding/*`, `/config/`, `/tools/`, `/healthz`, `/static/*`.

### Whole-feature verification gate

One final plan task, distinct from per-task unit checks:

1. Stand up a scratch FastAPI instance with `base_root=tmp_path` and empty `state/`.
2. `GET /board/` → assert 307 to `/onboarding/`.
3. `POST /onboarding/inject` with `tests/fixtures/onboarding/alice-doe-clean-emission.txt`.
4. Assert all seven files present at canonical paths under `tmp_path`.
5. Assert `config/companies_of_interest.txt` non-empty and contains known Tier 1 companies from the fixture.
6. Assert `{base_root}/data/.onboarding-complete` exists with a valid ISO timestamp.
7. `GET /board/` → 200 (guard cleared).
8. Import `findajob.config_loader` with `BASE` pointed at `tmp_path`; `load_companies_of_interest()` returns the expected frozenset.

The fixture file lives at `tests/fixtures/onboarding/alice-doe-clean-emission.txt` — a committed, PII-scrubbed, realistic emission for Alice Doe (first beta tester's public handle), so the fixture also documents the interview's output shape.

---

## Out of scope

- Partial re-runs / updating one category → #150's scope.
- In-UI embedded LLM chat → deferred per architecture decision.
- Retiring `config/companies_of_interest.txt` → pre-existing drift, follow-up issue.
- Onboarding API keys / `data/.env` → setup docs (#11 territory), not the NUX.
- `feed_urls.txt` onboarding → Greenhouse slugs aren't interview-derivable; bootstrap copies `.example`.
- Auth on `/onboarding/` → Wireguard-perimeter model, consistent with `/config/`.
- Progress indicators mid-interview → the interview's own phase gating already provides this in the LLM chat; duplicating it on our side couples to tab-open.

---

## Follow-up issues to file after spec is committed

1. **Retire `config/companies_of_interest.txt`.** Change `findajob.config_loader.is_company_of_interest()` to parse `config/target_companies.md` Tier 1 section directly. Cleanup; no functional change. Removes the post-injection derivation step from #148's injector once shipped.
2. **Onboarding interview v3: emit `feed_urls.txt`.** Expand the interview's Phase 3 to elicit Greenhouse slugs for Tier 1 companies where public, and add it as the eighth emitted file. Future work — expands interview scope.

---

## Documentation Impact

Every surface touched by this spec:

- **`CLAUDE.md`** — add the `/onboarding/` route, the sentinel file location (`{base_root}/data/.onboarding-complete`), and the backup-root convention (`{base_root}/.backups/{stamp}/`) to the Web Frontend Architecture section; add the onboarding parser, injector, and route modules to the Key File Locations listing; add `/app/.backups/` to the Container Context paths table.
- **`docs/onboarding-prework-checklist.md`** — update the "Running the interview" section: replace "your instance operator will extract each block" with "when the interview finishes, come back to your stack's `/onboarding/` page and paste the full conversation."
- **`config/roles/onboarding_interviewer.md`** — update the closing note ("After the interview…") to match: user returns to `/onboarding/` and pastes.
- **`docs/setup/` (for #11)** — the setup README will reference `/onboarding/` as the post-deploy next step. This spec's existence unblocks that reference.
- **`CHANGELOG.md`** — `[Unreleased]` entry: "Added `/onboarding/` page and full interview → config injection flow; first-run stacks are now guided end-to-end."
- **New doc: none.** All updates are to existing files.
- **Docstrings** — `findajob.onboarding.parser`, `findajob.onboarding.injector`, `findajob.web.routes.onboarding`, and the guard module each get module-level docstrings consistent with the `/config/` editor's `findajob.web.config_files` style.

Plan must include one task that updates all of the above in the same change as the code, per the [Documentation Sync Rule](../../CLAUDE.md) feedback principle.

---

## Self-review checklist (for the implementing plan)

The plan that implements this spec must map every section above to specific tasks. At minimum:

- [ ] Parser module + unit tests — §Parser spec, §Testing (unit)
- [ ] Injector module + unit tests — §Injection spec, §Testing (unit)
- [ ] Config allowlist extension + unit test — §`/config/` editor allowlist update, §Testing (unit)
- [ ] `/onboarding/` landing route + template — §Components, §Data flow
- [ ] `/onboarding/inject` POST route — §Components, §Data flow, §Testing (route-level)
- [ ] NUX guard dependency + attachment to gated routers — §NUX guard, §Testing (route-level)
- [ ] `/tools/` template update — §/tools/ integration
- [ ] Whole-feature verification gate + committed fixture — §Testing (whole-feature)
- [ ] Documentation updates (CLAUDE.md, prework checklist, role prompt, CHANGELOG) in the same change — §Documentation Impact
- [ ] Follow-up issues filed before PR merges — §Follow-up issues

The plan's own Documentation Impact section must re-enumerate these surfaces and cannot say "None."
