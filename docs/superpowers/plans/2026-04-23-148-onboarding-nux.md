# Onboarding NUX + Config Injection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the first-run onboarding experience at `/onboarding/` and the paste-back interview → config injection pipeline. A fresh stack redirects the user to the onboarding page, walks them through running the interview in their chosen LLM, and turns the pasted emission into seven config files plus a derived `companies_of_interest.txt`. Also re-triggerable from `/tools/` for full re-runs. Closes GitHub issue #148.

**Architecture:** Paste-back (no in-UI LLM chat). One Python package `findajob.onboarding` with two pure modules (`parser`, `injector`) containing all business logic — no FastAPI imports, unit-testable without TestClient. A web sub-package `findajob.web.routes.onboarding` provides `GET /onboarding/` and `POST /onboarding/inject`. A tiny guard module `findajob.web.onboarding_guard` exposes a FastAPI dependency attached to the `/board/*`, `/materials/*`, and `/stats/*` router includes that redirects 307 → `/onboarding/` when the sentinel file is missing. See `docs/superpowers/specs/2026-04-23-148-onboarding-nux-design.md` for the full design rationale.

**Tech Stack:** FastAPI + Jinja2 + HTMX (all existing). Python stdlib only for new code — `re`, `shutil`, `tempfile`, `pathlib`, `datetime`. No new dependencies.

**Execution environment:** Feature branch `feat/148-onboarding-nux` branched off `origin/main`. PR flow per `CLAUDE.md` "Commit Flow" (pipeline code + web behavior → PR). Rebase / `git fetch` before every new plan session.

---

## Scope

**In scope:**
- `/onboarding/` GET landing page with prework, "copy prompt" + "open in LLM" actions, and the paste form
- `/onboarding/inject` POST endpoint: parse → backup → write 7 files → derive `companies_of_interest.txt` → write sentinel
- NUX guard redirecting unconfigured stacks from `/board/*`, `/materials/*`, `/stats/*` to `/onboarding/`
- `/tools/` card pointing at `/onboarding/?mode=rerun`
- `/config/` editor allowlist extension for `config/target_companies.md` and `config/business_sector_employers_reference.md`
- Committed realistic fixture under `tests/fixtures/onboarding/alice-doe-clean-emission.txt` for route-level and E2E tests
- Docs updates in the same change: CLAUDE.md, `docs/onboarding-prework-checklist.md`, `config/roles/onboarding_interviewer.md` closing note, `CHANGELOG.md` Unreleased entry

**Out of scope (deferred):**
- Partial re-runs / single-category updates — owned by issue #150
- In-UI embedded LLM chat — rejected per spec architecture decision
- Retiring `config/companies_of_interest.txt` in favor of reading `target_companies.md` Tier 1 directly — follow-up issue filed by Task 12
- Emitting `feed_urls.txt` from the interview — follow-up issue filed by Task 12
- Onboarding API keys / populating `data/.env` — that's setup docs (#11 territory)
- Auth on `/onboarding/` — Wireguard-perimeter model, consistent with `/config/`

---

## File Structure

**New files:**

| File | Responsibility |
|---|---|
| `src/findajob/onboarding/__init__.py` | Marker + public re-exports (`parse_emission`, `inject`, `is_complete`) |
| `src/findajob/onboarding/parser.py` | Pure function `parse_emission(blob: str) -> ParsedEmission`. Delimiter-tolerant regex scan. No FastAPI/stdlib side effects beyond `re`. |
| `src/findajob/onboarding/injector.py` | Pure functions `backup_existing`, `inject`, `derive_companies_of_interest`, `mark_complete`, `is_complete`. Filesystem side effects only within the passed `base_root`. |
| `src/findajob/web/routes/onboarding.py` | `GET /onboarding/` + `POST /onboarding/inject`. Calls into the `findajob.onboarding` package. |
| `src/findajob/web/onboarding_guard.py` | Defines `require_onboarding_complete(request)` FastAPI dependency. |
| `src/findajob/web/templates/onboarding/index.html` | Landing page template — prework, LLM-open buttons, "copy prompt" button, paste form. Extends `base.html`. |
| `src/findajob/web/templates/onboarding/_paste_form.html` | HTMX partial for the paste textarea + its error box (re-rendered on parse failure so the textarea content is preserved). |
| `tests/fixtures/onboarding/alice-doe-clean-emission.txt` | Realistic emission fixture — uses Alice Doe public handle + fabricated non-PII data for the generalization beta. |
| `tests/test_onboarding_parser.py` | Unit tests for `parser.parse_emission`. |
| `tests/test_onboarding_injector.py` | Unit tests for every public fn in `injector.py`. |
| `tests/test_web_onboarding_routes.py` | TestClient integration tests for `GET /onboarding/`, `POST /onboarding/inject`, the `?mode=rerun` branch. |
| `tests/test_web_onboarding_guard.py` | TestClient integration tests for the guard: redirects when sentinel missing, passes through when present, does not gate ungated routes. |
| `tests/test_config_files_onboarding.py` | Unit test that `target_companies.md` and `business_sector_employers_reference.md` are on the `/config/` editor allowlist; `companies_of_interest.txt` is NOT. |
| `tests/test_onboarding_e2e.py` | Whole-feature verification: fresh base_root → redirect → paste → inject → files on disk → guard cleared. Uses the committed fixture. |

**Modified files:**

| File | Change |
|---|---|
| `src/findajob/web/config_files.py` | Add `config/target_companies.md` and `config/business_sector_employers_reference.md` to `EDITABLE_CATEGORIES["Search config"]`. |
| `src/findajob/web/routes/__init__.py` | Import `onboarding` route module; include its router. Attach `Depends(require_onboarding_complete)` to `board`, `materials`, `stats` router includes. |
| `src/findajob/web/templates/tools/index.html` | Add "Run onboarding interview" card above the existing "Edit config files" entry. |
| `src/findajob/web/templates/_nav.html` | Add `/onboarding/` to the nav only when sentinel is missing (optional — otherwise it stays off nav). Decision below in Task 6. |
| `CLAUDE.md` | Add `/onboarding/` route + sentinel + `.backups/` to "Web Frontend Architecture"; add onboarding modules to "Key File Locations"; add `/app/.backups/` to "Container Context" table. |
| `docs/onboarding-prework-checklist.md` | Update "Running the interview" section: replace "instance operator will extract each block" with "return to your stack's `/onboarding/` page and paste the full transcript." |
| `config/roles/onboarding_interviewer.md` | Update the closing "After the interview" section to reference `/onboarding/` paste-back instead of operator extraction. |
| `CHANGELOG.md` | Add `[Unreleased]` → `Added` entry. |

**Module-level invariants (frozen by this plan):**

- All paths in the plan and the onboarding package are relative to `base_root`. On the host: `state/`. In the container: `/app/`.
- The sentinel file is `{base_root}/data/.onboarding-complete` (UTF-8, a single ISO-8601 UTC timestamp line ending in `Z`).
- The backup directory is `{base_root}/.backups/{stamp}/` where `stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")`.
- The seven allowlisted emission filenames are (in the order the interview emits them): `profile.md`, `master_resume.md`, `target_companies.md`, `business_sector_employers_reference.md`, `jsearch_queries.txt`, `prefilter_rules.yaml`, `in_domain_patterns.yaml`.
- Atomic writes: write to `tempfile.mkstemp` in the destination dir, then `os.replace` only after every tempfile is staged.

---

## Setup Task: Branch

- [ ] **Step 1: Fetch latest and branch off `origin/main`**

Run:
```
git fetch origin && git checkout -b feat/148-onboarding-nux origin/main
```

Expected: new branch `feat/148-onboarding-nux` checked out, working tree clean.

- [ ] **Step 2: Verify branch starting point**

Run: `git log --oneline -1`
Expected: matches `git log --oneline -1 origin/main` (tip of origin/main).

---

## Task 1 — Parser module (pure, TDD)

**Files:**
- Create: `src/findajob/onboarding/__init__.py`
- Create: `src/findajob/onboarding/parser.py`
- Test: `tests/test_onboarding_parser.py`

- [ ] **Step 1: Write the failing unit tests**

Create `tests/test_onboarding_parser.py`:

```python
"""Unit tests for the onboarding emission parser (#148)."""

from __future__ import annotations

import pytest

from findajob.onboarding.parser import ALLOWED_FILENAMES, parse_emission


def _wrap(name: str, body: str) -> str:
    return f"<<<FILE: {name}>>>\n{body}\n<<<END FILE: {name}>>>"


_CLEAN_BLOCKS = {
    "profile.md": "# Profile\nAlice Doe\n",
    "master_resume.md": "# Resume\n## Contact\nAlice Doe\n",
    "target_companies.md": "## Tier 1 — Active Focus\n- Acme\n- Example Corp\n",
    "business_sector_employers_reference.md": "## Categories\n### Foo\n",
    "jsearch_queries.txt": "senior backend engineer\n",
    "prefilter_rules.yaml": "hard_rejects:\n  spam:\n    - '\\bspam\\b'\n",
    "in_domain_patterns.yaml": "positive:\n  - '\\bbackend\\s+engineer\\b'\n",
}


def _clean_emission() -> str:
    return "\n\n".join(_wrap(n, b) for n, b in _CLEAN_BLOCKS.items())


def test_allowed_filenames_are_exactly_seven() -> None:
    assert len(ALLOWED_FILENAMES) == 7
    assert set(ALLOWED_FILENAMES) == set(_CLEAN_BLOCKS)


def test_clean_emission_all_seven_found() -> None:
    result = parse_emission(_clean_emission())
    assert set(result.found) == set(_CLEAN_BLOCKS)
    assert result.missing == []
    assert result.unknown == []
    for name, body in _CLEAN_BLOCKS.items():
        assert result.found[name] == body


def test_embedded_in_transcript_is_still_parsed() -> None:
    blob = (
        "User: paste the emission please\n"
        "Assistant: Here we go.\n\n"
        + _clean_emission()
        + "\n\nReply **next** to continue.\n"
    )
    result = parse_emission(blob)
    assert set(result.found) == set(_CLEAN_BLOCKS)
    assert result.missing == []


def test_missing_block_is_reported() -> None:
    partial_blocks = {k: v for k, v in _CLEAN_BLOCKS.items() if k != "in_domain_patterns.yaml"}
    blob = "\n\n".join(_wrap(n, b) for n, b in partial_blocks.items())
    result = parse_emission(blob)
    assert "in_domain_patterns.yaml" in result.missing
    assert len(result.found) == 6


def test_duplicate_last_wins() -> None:
    blob = (
        _wrap("profile.md", "first draft\n")
        + "\n\n"
        + "\n\n".join(_wrap(n, b) for n, b in _CLEAN_BLOCKS.items() if n != "profile.md")
        + "\n\n"
        + _wrap("profile.md", "second draft\n")
    )
    result = parse_emission(blob)
    assert result.found["profile.md"] == "second draft\n"
    assert result.missing == []


def test_unknown_filename_goes_to_unknown() -> None:
    blob = _clean_emission() + "\n\n" + _wrap("secrets.env", "API_KEY=...\n")
    result = parse_emission(blob)
    assert "secrets.env" in result.unknown
    assert "secrets.env" not in result.found
    assert set(result.found) == set(_CLEAN_BLOCKS)


def test_code_fence_wrapping_is_stripped() -> None:
    body = "## Profile\ncontent\n"
    fenced = f"```markdown\n{body}```"
    blob = _wrap("profile.md", fenced) + "\n\n" + "\n\n".join(
        _wrap(n, b) for n, b in _CLEAN_BLOCKS.items() if n != "profile.md"
    )
    result = parse_emission(blob)
    assert result.found["profile.md"].strip() == body.strip()


def test_crlf_line_endings_parse() -> None:
    blob = _clean_emission().replace("\n", "\r\n")
    result = parse_emission(blob)
    assert set(result.found) == set(_CLEAN_BLOCKS)
    assert result.missing == []


def test_dangling_open_delimiter_is_missing() -> None:
    partial = _wrap("profile.md", "ok\n")
    # Dangling open for master_resume with no close
    dangling = "<<<FILE: master_resume.md>>>\nstarted but not finished\n"
    blob = partial + "\n\n" + dangling + "\n\n" + "\n\n".join(
        _wrap(n, b) for n, b in _CLEAN_BLOCKS.items()
        if n not in ("profile.md", "master_resume.md")
    )
    result = parse_emission(blob)
    assert "master_resume.md" in result.missing
    assert "profile.md" in result.found


def test_blank_input_returns_all_missing() -> None:
    result = parse_emission("")
    assert result.found == {}
    assert set(result.missing) == set(_CLEAN_BLOCKS)
    assert result.unknown == []
```

- [ ] **Step 2: Run tests, confirm they fail**

Run: `uv run pytest tests/test_onboarding_parser.py -v`
Expected: ModuleNotFoundError for `findajob.onboarding.parser`.

- [ ] **Step 3: Create the package marker**

Create `src/findajob/onboarding/__init__.py`:

```python
"""findajob onboarding pipeline: interview emission parser + config injector.

Public surface:

- :func:`parse_emission` — parse an interview emission into files to inject.
- :func:`inject` — write parsed files atomically; return the backup dir or None.
- :func:`is_complete` — True iff the sentinel file exists under ``base_root``.
"""

from __future__ import annotations

from findajob.onboarding.injector import inject, is_complete, mark_complete
from findajob.onboarding.parser import ALLOWED_FILENAMES, ParsedEmission, parse_emission

__all__ = [
    "ALLOWED_FILENAMES",
    "ParsedEmission",
    "inject",
    "is_complete",
    "mark_complete",
    "parse_emission",
]
```

Note: this will fail to import until Task 2 lands `injector.py`. We resolve that in Task 2. For now, create a **stub** so Task 1's tests can run:

Temporarily create `src/findajob/onboarding/__init__.py` with only the parser re-exports:

```python
"""findajob onboarding pipeline: interview emission parser + config injector."""

from __future__ import annotations

from findajob.onboarding.parser import ALLOWED_FILENAMES, ParsedEmission, parse_emission

__all__ = ["ALLOWED_FILENAMES", "ParsedEmission", "parse_emission"]
```

(Task 2 replaces this with the full re-export.)

- [ ] **Step 4: Implement the parser**

Create `src/findajob/onboarding/parser.py`:

```python
"""Onboarding emission parser (#148).

Scans a pasted blob for ``<<<FILE: name>>> ... <<<END FILE: name>>>`` blocks,
validates each filename against :data:`ALLOWED_FILENAMES`, and returns a
:class:`ParsedEmission` describing what was found, what's missing, and what
had an unrecognized filename.

Pure module: imports only ``re`` and ``dataclasses``. No filesystem access,
no FastAPI import.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

ALLOWED_FILENAMES: tuple[str, ...] = (
    "profile.md",
    "master_resume.md",
    "target_companies.md",
    "business_sector_employers_reference.md",
    "jsearch_queries.txt",
    "prefilter_rules.yaml",
    "in_domain_patterns.yaml",
)


_BLOCK_RE = re.compile(
    r"<<<FILE:\s*(?P<name>[^>\s]+)\s*>>>\r?\n(?P<body>.*?)\r?\n<<<END FILE:\s*(?P=name)\s*>>>",
    re.DOTALL,
)

_FENCE_OPEN_RE = re.compile(r"\A```[^\n]*\r?\n")
_FENCE_CLOSE_RE = re.compile(r"\r?\n```\Z")


@dataclass(frozen=True)
class ParsedEmission:
    """Result of parsing an emission blob.

    ``found`` maps allowlisted filenames to their raw body content.
    ``missing`` is the subset of :data:`ALLOWED_FILENAMES` that were not
    present. ``unknown`` holds any filenames that appeared in delimiters
    but are not on the allowlist.
    """

    found: dict[str, str] = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)
    unknown: list[str] = field(default_factory=list)


def _strip_code_fences(body: str) -> str:
    body = _FENCE_OPEN_RE.sub("", body, count=1)
    body = _FENCE_CLOSE_RE.sub("", body, count=1)
    return body


def parse_emission(blob: str) -> ParsedEmission:
    """Parse ``blob`` and return a :class:`ParsedEmission`.

    Tolerant of blocks embedded in a larger chat transcript. Last occurrence
    of any given filename wins (the interview may emit a ``redo`` sequence).
    """
    found: dict[str, str] = {}
    unknown: list[str] = []
    for match in _BLOCK_RE.finditer(blob):
        name = match.group("name").strip()
        body = _strip_code_fences(match.group("body"))
        if name in ALLOWED_FILENAMES:
            found[name] = body
        else:
            if name not in unknown:
                unknown.append(name)
    missing = [n for n in ALLOWED_FILENAMES if n not in found]
    return ParsedEmission(found=found, missing=missing, unknown=unknown)
```

- [ ] **Step 5: Run tests, confirm they pass**

Run: `uv run pytest tests/test_onboarding_parser.py -v`
Expected: 10 passed.

- [ ] **Step 6: Lint**

Run: `uv run ruff check src/findajob/onboarding/ tests/test_onboarding_parser.py && uv run ruff format --check src/findajob/onboarding/ tests/test_onboarding_parser.py`
Expected: clean.

- [ ] **Step 7: Commit**

```
git add src/findajob/onboarding/__init__.py src/findajob/onboarding/parser.py tests/test_onboarding_parser.py
git commit -m "feat(onboarding): add parser for interview emission blocks (#148)

Pure module that scans a pasted blob for <<<FILE: name>>> blocks, returns
found/missing/unknown. Tolerant of transcript wrapping, code fences, CRLF,
and duplicate blocks (last wins). No FastAPI import."
```

---

## Task 2 — Injector module

**Files:**
- Modify: `src/findajob/onboarding/__init__.py`
- Create: `src/findajob/onboarding/injector.py`
- Test: `tests/test_onboarding_injector.py`

- [ ] **Step 1: Write the failing unit tests**

Create `tests/test_onboarding_injector.py`:

```python
"""Unit tests for the onboarding injector (#148)."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from findajob.onboarding.injector import (
    _ALL_DESTINATIONS,
    _COMPANIES_OF_INTEREST_DEST,
    _SENTINEL_RELPATH,
    backup_existing,
    derive_companies_of_interest,
    inject,
    is_complete,
    mark_complete,
)


_MIN_FILES = {
    "profile.md": "# Profile\n",
    "master_resume.md": "# Resume\n",
    "target_companies.md": (
        "# Generated by findajob onboarding interviewer v2 — 2026-04-20\n\n"
        "## Tier 1 — Active Focus\n"
        "- Acme Corp\n"
        "- Example Industries — would take a role there today\n"
        "- Sample Systems (public benefit corp)\n\n"
        "## Tier 2 — Strong Interest\n"
        "- Other Co\n\n"
        "## Notes\n"
        "These are hypothetical.\n"
    ),
    "business_sector_employers_reference.md": "## Categories\n",
    "jsearch_queries.txt": "senior backend engineer\n",
    "prefilter_rules.yaml": "hard_rejects:\n  spam:\n    - '\\bspam\\b'\n",
    "in_domain_patterns.yaml": "positive:\n  - '\\bbackend\\b'\n",
}


def test_all_destinations_map_seven_filenames(tmp_path: Path) -> None:
    assert set(_ALL_DESTINATIONS.keys()) == set(_MIN_FILES.keys())


def test_sentinel_and_companies_paths_are_stable() -> None:
    assert _SENTINEL_RELPATH == "data/.onboarding-complete"
    assert _COMPANIES_OF_INTEREST_DEST == "config/companies_of_interest.txt"


# ---- derive_companies_of_interest ----------------------------------------


def test_derive_tier1_strips_bullets_and_commentary() -> None:
    out = derive_companies_of_interest(_MIN_FILES["target_companies.md"])
    lines = [line for line in out.splitlines() if line]
    assert lines == ["Acme Corp", "Example Industries", "Sample Systems"]


def test_derive_ignores_tier2_and_beyond() -> None:
    md = (
        "## Tier 1 — Active Focus\n- A\n- B\n\n"
        "## Tier 2 — Strong Interest\n- C\n- D\n\n"
        "## Tier 3 — Opportunistic\n- E\n"
    )
    out = derive_companies_of_interest(md)
    assert out.splitlines() == ["A", "B"]


def test_derive_handles_star_bullets_and_numbered() -> None:
    md = (
        "## Tier 1 — Active Focus\n"
        "* Alpha Co\n"
        "1. Beta Inc\n"
        "- Gamma LLC\n"
    )
    out = derive_companies_of_interest(md)
    assert out.splitlines() == ["Alpha Co", "Beta Inc", "Gamma LLC"]


def test_derive_ends_with_newline() -> None:
    out = derive_companies_of_interest("## Tier 1\n- X\n")
    assert out.endswith("\n")


def test_derive_empty_when_no_tier1() -> None:
    assert derive_companies_of_interest("## Tier 2\n- Z\n") == ""


# ---- is_complete / mark_complete -----------------------------------------


def test_is_complete_false_on_empty_base(tmp_path: Path) -> None:
    assert is_complete(tmp_path) is False


def test_mark_and_is_complete_roundtrip(tmp_path: Path) -> None:
    mark_complete(tmp_path)
    assert is_complete(tmp_path) is True
    sentinel = tmp_path / "data" / ".onboarding-complete"
    assert sentinel.is_file()
    content = sentinel.read_text(encoding="utf-8").strip()
    # Parseable ISO 8601 UTC
    parsed = datetime.strptime(content, "%Y-%m-%dT%H:%M:%SZ")
    assert parsed.tzinfo is None  # naive from strptime; our write used Z


# ---- backup_existing ------------------------------------------------------


def test_backup_on_empty_base_creates_empty_dir(tmp_path: Path) -> None:
    dest = backup_existing(tmp_path, "20260423T120000Z")
    assert dest == tmp_path / ".backups" / "20260423T120000Z"
    assert dest.is_dir()
    assert list(dest.rglob("*")) == []


def test_backup_copies_existing_destinations(tmp_path: Path) -> None:
    (tmp_path / "candidate_context").mkdir()
    (tmp_path / "candidate_context" / "profile.md").write_text("old profile\n")
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "prefilter_rules.yaml").write_text("hard_rejects: {}\n")
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / ".onboarding-complete").write_text("2026-01-01T00:00:00Z\n")

    dest = backup_existing(tmp_path, "20260423T120000Z")
    assert (dest / "candidate_context" / "profile.md").read_text() == "old profile\n"
    assert (dest / "config" / "prefilter_rules.yaml").read_text() == "hard_rejects: {}\n"
    assert (dest / "data" / ".onboarding-complete").read_text() == "2026-01-01T00:00:00Z\n"


# ---- inject ---------------------------------------------------------------


def test_inject_writes_seven_files_and_sentinel_and_derivation(tmp_path: Path) -> None:
    backup = inject(tmp_path, _MIN_FILES)
    assert backup is not None  # returns the (possibly empty) backup dir
    # Seven canonical files
    assert (tmp_path / "candidate_context" / "profile.md").read_text() == _MIN_FILES["profile.md"]
    assert (tmp_path / "candidate_context" / "master_resume.md").read_text() == _MIN_FILES["master_resume.md"]
    assert (tmp_path / "config" / "target_companies.md").read_text() == _MIN_FILES["target_companies.md"]
    assert (
        tmp_path / "config" / "business_sector_employers_reference.md"
    ).read_text() == _MIN_FILES["business_sector_employers_reference.md"]
    assert (tmp_path / "config" / "jsearch_queries.txt").read_text() == _MIN_FILES["jsearch_queries.txt"]
    assert (tmp_path / "config" / "prefilter_rules.yaml").read_text() == _MIN_FILES["prefilter_rules.yaml"]
    assert (tmp_path / "config" / "in_domain_patterns.yaml").read_text() == _MIN_FILES["in_domain_patterns.yaml"]
    # Derived companies_of_interest
    coi = (tmp_path / "config" / "companies_of_interest.txt").read_text()
    assert "Acme Corp" in coi
    assert "Example Industries" in coi
    # Sentinel
    sentinel = tmp_path / "data" / ".onboarding-complete"
    assert sentinel.is_file()


def test_inject_staging_failure_rolls_back(tmp_path: Path) -> None:
    """If staging (tempfile write) fails, no existing files are mutated and
    no partial backup remains.

    We simulate by making ``tempfile.mkstemp`` raise on its 3rd call. Inject
    must propagate, and leave the pre-existing file untouched with no
    tempfile residue and no backup directory.
    """
    # Pre-existing state — must survive the failed inject
    (tmp_path / "candidate_context").mkdir()
    (tmp_path / "candidate_context" / "profile.md").write_text("pre-existing\n")
    original = (tmp_path / "candidate_context" / "profile.md").read_text()

    import findajob.onboarding.injector as inj_mod

    calls = {"n": 0}
    real_mkstemp = inj_mod.tempfile.mkstemp

    def flaky_mkstemp(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 3:
            raise OSError("simulated disk full")
        return real_mkstemp(*args, **kwargs)

    with patch.object(inj_mod.tempfile, "mkstemp", side_effect=flaky_mkstemp):
        with pytest.raises(OSError):
            inject(tmp_path, _MIN_FILES)

    # profile.md unchanged
    assert (tmp_path / "candidate_context" / "profile.md").read_text() == original
    # No sentinel
    assert not (tmp_path / "data" / ".onboarding-complete").exists()
    # No derived file
    assert not (tmp_path / "config" / "companies_of_interest.txt").exists()
    # No residual tempfiles
    residual = list((tmp_path / "candidate_context").glob("profile.md.*.tmp"))
    assert residual == []
    # No backup dir left behind
    backups = tmp_path / ".backups"
    assert not backups.exists() or not any(backups.iterdir())


def test_inject_creates_parent_dirs(tmp_path: Path) -> None:
    # Fresh base with no subdirs — inject must mkdir them
    inject(tmp_path, _MIN_FILES)
    assert (tmp_path / "candidate_context").is_dir()
    assert (tmp_path / "config").is_dir()
    assert (tmp_path / "data").is_dir()


def test_inject_raises_on_missing_file_in_parsed(tmp_path: Path) -> None:
    partial = {k: v for k, v in _MIN_FILES.items() if k != "profile.md"}
    with pytest.raises(ValueError, match="profile.md"):
        inject(tmp_path, partial)
```

- [ ] **Step 2: Run tests, confirm they fail**

Run: `uv run pytest tests/test_onboarding_injector.py -v`
Expected: ModuleNotFoundError for `findajob.onboarding.injector`.

- [ ] **Step 3: Implement `injector.py`**

Create `src/findajob/onboarding/injector.py`:

```python
"""Onboarding injector (#148).

Turns a parsed emission into seven files on disk plus a derived
``companies_of_interest.txt``, with backup-then-overwrite and a
sentinel file that gates the NUX redirect.

All writes are atomic: every tempfile is staged first, then
``os.replace`` commits them in order. Any staging failure rolls back
cleanly — zero mutations to existing files, no partial backup residue.

Pure module: imports ``os``, ``re``, ``shutil``, ``tempfile``,
``datetime``, ``pathlib``. No FastAPI import.
"""

from __future__ import annotations

import os
import re
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from findajob.onboarding.parser import ALLOWED_FILENAMES

# Maps emission filename -> destination relative path (relative to base_root).
_ALL_DESTINATIONS: dict[str, str] = {
    "profile.md": "candidate_context/profile.md",
    "master_resume.md": "candidate_context/master_resume.md",
    "target_companies.md": "config/target_companies.md",
    "business_sector_employers_reference.md": "config/business_sector_employers_reference.md",
    "jsearch_queries.txt": "config/jsearch_queries.txt",
    "prefilter_rules.yaml": "config/prefilter_rules.yaml",
    "in_domain_patterns.yaml": "config/in_domain_patterns.yaml",
}

_COMPANIES_OF_INTEREST_DEST = "config/companies_of_interest.txt"
_SENTINEL_RELPATH = "data/.onboarding-complete"
_BACKUP_ROOT = ".backups"

_TIER1_HEADING_RE = re.compile(r"^##\s+tier\s*1\b[^\n]*", re.IGNORECASE | re.MULTILINE)
_NEXT_H2_RE = re.compile(r"^##\s+\S", re.MULTILINE)
_BULLET_RE = re.compile(r"^\s*(?:[-*]\s+|\d+\.\s+)(.*)")
_SPLIT_COMMENTARY_RE = re.compile(r"\s+[—-]\s+|\s+\(")


def is_complete(base_root: Path) -> bool:
    """True iff the sentinel file exists under ``base_root``."""
    return (base_root / _SENTINEL_RELPATH).is_file()


def mark_complete(base_root: Path) -> None:
    """Write the sentinel file with the current UTC timestamp."""
    sentinel = base_root / _SENTINEL_RELPATH
    sentinel.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    sentinel.write_text(ts + "\n", encoding="utf-8")


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _backup_relpaths() -> list[str]:
    paths = list(_ALL_DESTINATIONS.values())
    paths.append(_COMPANIES_OF_INTEREST_DEST)
    paths.append(_SENTINEL_RELPATH)
    return paths


def backup_existing(base_root: Path, stamp: str) -> Path:
    """Copy any existing destinations to ``{base_root}/.backups/{stamp}/``.

    Returns the backup directory path (possibly empty). Preserves the
    relative path structure of every copied file.
    """
    dest_root = base_root / _BACKUP_ROOT / stamp
    dest_root.mkdir(parents=True, exist_ok=True)
    for relpath in _backup_relpaths():
        src = base_root / relpath
        if not src.is_file():
            continue
        target = dest_root / relpath
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, target)
    return dest_root


def derive_companies_of_interest(target_companies_md: str) -> str:
    """Extract Tier 1 company names from ``target_companies.md``.

    Returns one company per line, trailing newline. Empty string if no
    ``## Tier 1`` section is present.
    """
    match = _TIER1_HEADING_RE.search(target_companies_md)
    if not match:
        return ""
    section_start = match.end()
    remainder = target_companies_md[section_start:]
    next_h2 = _NEXT_H2_RE.search(remainder)
    section = remainder[: next_h2.start()] if next_h2 else remainder
    companies: list[str] = []
    for line in section.splitlines():
        bullet = _BULLET_RE.match(line)
        if not bullet:
            continue
        raw = bullet.group(1).strip()
        # Strip trailing commentary (everything from the first " — " or " - " or " (")
        parts = _SPLIT_COMMENTARY_RE.split(raw, maxsplit=1)
        name = parts[0].strip()
        if name:
            companies.append(name)
    if not companies:
        return ""
    return "\n".join(companies) + "\n"


def inject(base_root: Path, found: dict[str, str]) -> Path:
    """Backup, stage, commit. Returns the (possibly empty) backup dir.

    ``found`` must contain every filename in :data:`ALLOWED_FILENAMES`;
    otherwise raises :class:`ValueError` without touching disk.

    On any staging or commit error, all tempfiles and the backup dir
    created this run are removed, and the exception propagates.
    """
    missing = [n for n in ALLOWED_FILENAMES if n not in found]
    if missing:
        raise ValueError(f"inject(): parsed emission is missing: {missing}")

    # Ensure target directories exist
    for relpath in list(_ALL_DESTINATIONS.values()) + [_COMPANIES_OF_INTEREST_DEST]:
        (base_root / relpath).parent.mkdir(parents=True, exist_ok=True)
    (base_root / _SENTINEL_RELPATH).parent.mkdir(parents=True, exist_ok=True)

    stamp = _utc_stamp()
    backup_dir = backup_existing(base_root, stamp)

    tempfiles: list[tuple[str, Path]] = []  # (tmp_name, final_dest)
    try:
        # Stage the seven parsed files
        for name in ALLOWED_FILENAMES:
            dest = base_root / _ALL_DESTINATIONS[name]
            fd, tmp_name = tempfile.mkstemp(
                prefix=dest.name + ".", suffix=".tmp", dir=str(dest.parent)
            )
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
                fh.write(found[name])
            tempfiles.append((tmp_name, dest))

        # Stage the derived companies_of_interest.txt
        coi_body = derive_companies_of_interest(found["target_companies.md"])
        coi_dest = base_root / _COMPANIES_OF_INTEREST_DEST
        fd, tmp_name = tempfile.mkstemp(
            prefix=coi_dest.name + ".", suffix=".tmp", dir=str(coi_dest.parent)
        )
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
            fh.write(coi_body)
        tempfiles.append((tmp_name, coi_dest))

        # Commit: os.replace every staged tempfile into place
        for tmp_name, dest in tempfiles:
            os.replace(tmp_name, dest)
        tempfiles = []  # all committed

        # Finally, the sentinel
        mark_complete(base_root)
    except Exception:
        # Roll back: delete any remaining tempfiles + the backup dir created this run
        for tmp_name, _dest in tempfiles:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
        shutil.rmtree(backup_dir, ignore_errors=True)
        raise

    return backup_dir
```

- [ ] **Step 4: Update `__init__.py` to re-export injector**

Modify `src/findajob/onboarding/__init__.py`:

```python
"""findajob onboarding pipeline: interview emission parser + config injector.

Public surface:

- :func:`parse_emission` — parse an interview emission into files to inject.
- :func:`inject` — write parsed files atomically; return the backup dir.
- :func:`is_complete` — True iff the sentinel file exists under ``base_root``.
- :func:`mark_complete` — write the sentinel file with the current UTC timestamp.
"""

from __future__ import annotations

from findajob.onboarding.injector import inject, is_complete, mark_complete
from findajob.onboarding.parser import ALLOWED_FILENAMES, ParsedEmission, parse_emission

__all__ = [
    "ALLOWED_FILENAMES",
    "ParsedEmission",
    "inject",
    "is_complete",
    "mark_complete",
    "parse_emission",
]
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_onboarding_injector.py tests/test_onboarding_parser.py -v`
Expected: all pass.

- [ ] **Step 6: Lint**

Run: `uv run ruff check src/findajob/onboarding/ tests/test_onboarding_*.py && uv run ruff format --check src/findajob/onboarding/ tests/test_onboarding_*.py`
Expected: clean.

- [ ] **Step 7: mypy**

Run: `uv run mypy src/findajob/onboarding/`
Expected: no issues.

- [ ] **Step 8: Commit**

```
git add src/findajob/onboarding/ tests/test_onboarding_injector.py
git commit -m "feat(onboarding): add atomic injector with backup + Tier 1 derivation (#148)

Takes a parsed emission and writes seven canonical config files plus a
derived companies_of_interest.txt from target_companies.md Tier 1 section.
All writes are tempfile+os.replace with full rollback on staging failure.
Sentinel file at data/.onboarding-complete gates the NUX redirect.
Backups land under {base_root}/.backups/{UTC-stamp}/."
```

---

## Task 3 — Extend `/config/` editor allowlist

**Files:**
- Modify: `src/findajob/web/config_files.py`
- Test: `tests/test_config_files_onboarding.py`

- [ ] **Step 1: Write the failing unit test**

Create `tests/test_config_files_onboarding.py`:

```python
"""Verify #148 adds target_companies.md + business_sector reference to the /config/ editor.

companies_of_interest.txt is derived, not user-edited — it must NOT be editable.
"""

from __future__ import annotations

from findajob.web.config_files import EDITABLE_CATEGORIES, is_editable


def test_target_companies_is_editable() -> None:
    assert is_editable("config/target_companies.md") is True


def test_business_sector_reference_is_editable() -> None:
    assert is_editable("config/business_sector_employers_reference.md") is True


def test_companies_of_interest_is_not_editable() -> None:
    # Derived at injection time — editing it directly would drift.
    assert is_editable("config/companies_of_interest.txt") is False


def test_both_new_files_listed_under_search_config() -> None:
    search = EDITABLE_CATEGORIES["Search config"]
    assert isinstance(search, list)
    assert "config/target_companies.md" in search
    assert "config/business_sector_employers_reference.md" in search
```

- [ ] **Step 2: Run test, confirm it fails**

Run: `uv run pytest tests/test_config_files_onboarding.py -v`
Expected: first three tests fail (is_editable returns False); fourth test fails (entries missing).

- [ ] **Step 3: Update `config_files.py`**

Edit `src/findajob/web/config_files.py`, update `EDITABLE_CATEGORIES`:

```python
EDITABLE_CATEGORIES: dict[str, list[str] | str] = {
    "Candidate context": [
        "candidate_context/profile.md",
        "candidate_context/master_resume.md",
    ],
    "Search config": [
        "config/target_companies.md",
        "config/business_sector_employers_reference.md",
        "config/prefilter_rules.yaml",
        "config/in_domain_patterns.yaml",
        "config/jsearch_queries.txt",
        "config/feed_urls.txt",
    ],
    "Role prompts": "config/roles/*.md",
}
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_config_files_onboarding.py tests/test_web_config_files_allowlist.py -v`
Expected: all pass (the pre-existing allowlist tests should still pass — they don't assert the exact list).

- [ ] **Step 5: Commit**

```
git add src/findajob/web/config_files.py tests/test_config_files_onboarding.py
git commit -m "feat(web/config): allow target_companies + sector reference in editor (#148)

Adds the two interview-emitted files that are not yet in the editor
allowlist so users can edit them post-injection via /config/. Keeps
companies_of_interest.txt off the allowlist — it's derived, not edited."
```

---

## Task 4 — NUX guard dependency module

**Files:**
- Create: `src/findajob/web/onboarding_guard.py`
- Test: `tests/test_web_onboarding_guard.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_web_onboarding_guard.py`:

```python
"""Integration tests for the NUX guard dependency (#148)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from findajob.onboarding import mark_complete
from findajob.web.app import create_app

_MINIMAL_SCHEMA = """
CREATE TABLE jobs (
    id TEXT PRIMARY KEY,
    fingerprint TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    company TEXT NOT NULL,
    stage TEXT DEFAULT 'discovered',
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL,
    field_changed TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT,
    changed_at TEXT DEFAULT (datetime('now'))
);
"""


@pytest.fixture()
def unconfigured_client(tmp_path: Path) -> TestClient:
    """Stack with no sentinel = not yet onboarded."""
    db_path = tmp_path / "pipeline.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(_MINIMAL_SCHEMA)
    conn.close()
    (tmp_path / "companies").mkdir()
    app = create_app(
        companies_root=tmp_path / "companies",
        db_path=db_path,
        base_root=tmp_path,
    )
    return TestClient(app, follow_redirects=False)


@pytest.fixture()
def configured_client(tmp_path: Path) -> TestClient:
    """Stack with sentinel written = onboarded."""
    db_path = tmp_path / "pipeline.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(_MINIMAL_SCHEMA)
    conn.close()
    (tmp_path / "companies").mkdir()
    mark_complete(tmp_path)
    app = create_app(
        companies_root=tmp_path / "companies",
        db_path=db_path,
        base_root=tmp_path,
    )
    return TestClient(app, follow_redirects=False)


# ---- Gated routes redirect when unconfigured ----


@pytest.mark.parametrize("path", ["/board/dashboard", "/materials/", "/stats/funnel"])
def test_gated_routes_redirect_without_sentinel(unconfigured_client: TestClient, path: str) -> None:
    resp = unconfigured_client.get(path)
    assert resp.status_code == 307
    assert resp.headers["location"] == "/onboarding/"


# ---- Gated routes pass through when configured ----


@pytest.mark.parametrize("path", ["/board/dashboard", "/stats/funnel"])
def test_gated_routes_pass_with_sentinel(configured_client: TestClient, path: str) -> None:
    resp = configured_client.get(path)
    # 200 or a different redirect — anything NOT a 307 to /onboarding/
    assert not (resp.status_code == 307 and resp.headers.get("location") == "/onboarding/")


# ---- Ungated routes are always reachable ----


@pytest.mark.parametrize("path", ["/", "/healthz", "/config/", "/tools/", "/ingest/"])
def test_ungated_routes_reachable_without_sentinel(unconfigured_client: TestClient, path: str) -> None:
    resp = unconfigured_client.get(path)
    assert not (resp.status_code == 307 and resp.headers.get("location") == "/onboarding/")
```

- [ ] **Step 2: Run test, confirm it fails**

Run: `uv run pytest tests/test_web_onboarding_guard.py -v`
Expected: ModuleNotFoundError for `findajob.web.onboarding_guard` (the import doesn't exist yet, and even without a direct import, the gated routes won't redirect).

- [ ] **Step 3: Create `onboarding_guard.py`**

Create `src/findajob/web/onboarding_guard.py`:

```python
"""NUX guard dependency for the board/materials/stats routers (#148).

Redirects 307 → /onboarding/ when the sentinel is missing. Caches the
first True read on ``app.state.onboarding_complete`` so subsequent
requests skip the filesystem check until the inject handler resets it.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException, Request

from findajob.onboarding import is_complete


def require_onboarding_complete(request: Request) -> None:
    """Raise 307 to /onboarding/ if the stack is not yet configured.

    Attached via ``dependencies=[Depends(require_onboarding_complete)]`` on
    the board/materials/stats router includes.
    """
    cached = getattr(request.app.state, "onboarding_complete", None)
    if cached is True:
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

(Task 8 attaches this dependency to the router includes; Task 4 lands the guard module and keeps the test red until Task 8.)

- [ ] **Step 4: Run lint**

Run: `uv run ruff check src/findajob/web/onboarding_guard.py && uv run ruff format --check src/findajob/web/onboarding_guard.py`
Expected: clean.

- [ ] **Step 5: Commit (test still red — wired in Task 8)**

```
git add src/findajob/web/onboarding_guard.py tests/test_web_onboarding_guard.py
git commit -m "feat(web): add NUX guard dependency (test red until Task 8) (#148)

FastAPI dependency that raises 307 to /onboarding/ when the sentinel file
is missing. Caches the configured state on app.state to avoid per-request
filesystem checks once onboarded. Attached to board/materials/stats in
Task 8 of the #148 plan."
```

Note: this leaves the test suite transiently red between Tasks 4 and 8. That's intentional — Task 8 turns it green when it wires the dependency into the routers.

---

## Task 5 — Test fixture: Alice Doe clean emission

**Files:**
- Create: `tests/fixtures/onboarding/alice-doe-clean-emission.txt`
- Create: `tests/fixtures/onboarding/__init__.py` (empty, so pytest treats it as a package for discovery consistency)

- [ ] **Step 1: Create the fixture directory marker**

Create `tests/fixtures/onboarding/__init__.py`:

```python
```

(empty file)

- [ ] **Step 2: Create the fixture**

Create `tests/fixtures/onboarding/alice-doe-clean-emission.txt`:

```
User: please emit all seven files now
Assistant: Here they are.

<<<FILE: profile.md>>>
# Generated by findajob onboarding interviewer v2 — 2026-04-20

## Identity
Name: Alice Doe
Location: Greater Metro Area, USA
LinkedIn: https://example.com/in/alice-doe
Email: alice@example.com
Phone: 555-0100

## Target Role
Clinical social worker in adult community mental health; LCSW-eligible.
Open to: hybrid, on-site within 30 minutes of home
Not open to: corrections, child welfare, substitute roles

## What Makes You Unusual
Fifteen years bridging clinical practice with systems-level program design
for unhoused populations.

## Core Competencies
- Adult outpatient clinical care
- Program design for chronic homelessness
- Multi-agency case coordination

## Career Summary
Built and scaled two continuum-of-care programs serving a combined 2,400
adults annually. Led clinical supervision for teams of up to 18 across
three counties.

## Employer History (most recent first)
- Metro Continuum of Care — 2021–Present — Program Director, Adult Services
- Riverside Health Partners — 2015–2021 — Senior Clinical Social Worker
- Hillside Community Clinic — 2010–2015 — Case Manager

## Target Companies / Organizations
- Metro Health Authority
- Sample Benefit Corporation
- Community First Coalition

## Excluded Categories
No corrections, no child protective services, no substitute roles.

## What to Emphasize
Lead with outcomes: number of adults served, reduction in unsheltered days,
clinical supervision scope. Avoid activity-language.

## Things to Avoid Mentioning
None.

## Employer Formatting Rules
None.
<<<END FILE: profile.md>>>

Reply **next** to continue.

User: next
Assistant:

<<<FILE: master_resume.md>>>
# Generated by findajob onboarding interviewer v2 — 2026-04-20

## Contact
Alice Doe | alice@example.com | 555-0100
https://example.com/in/alice-doe | Greater Metro Area, USA

## Experience

### Program Director, Adult Services — Metro Continuum of Care (2021–Present)
- Led multi-site adult services program serving 2,400 clients annually.
- Cut unsheltered return rate by 38% through new coordinated entry workflow.
- Supervised clinical staff of 18 across three counties.

### Senior Clinical Social Worker — Riverside Health Partners (2015–2021)
- Managed 60-client caseload across two counties.
- Designed stepped-care protocol adopted as regional standard in 2019.

### Case Manager — Hillside Community Clinic (2010–2015)
- Navigated benefit access for 350+ adults experiencing homelessness.

## Skills
Clinical supervision, program design, multi-agency coordination, data-informed
practice, LCSW-eligible.

## Education
MSW, Sample University, 2010
<<<END FILE: master_resume.md>>>

Reply **next**.

User: next
Assistant:

<<<FILE: target_companies.md>>>
# Generated by findajob onboarding interviewer v2 — 2026-04-20

## Tier 1 — Active Focus
- Metro Health Authority
- Sample Benefit Corporation
- Community First Coalition

## Tier 2 — Strong Interest
- Regional Care Network
- Valley Wellness Alliance

## Tier 3 — Opportunistic
- Crossroads Services Group

## Notes
Tier 1 are the three largest mission-aligned adult-services employers in the metro.
<<<END FILE: target_companies.md>>>

Reply **next**.

User: next
Assistant:

<<<FILE: business_sector_employers_reference.md>>>
# Generated by findajob onboarding interviewer v2 — 2026-04-20

## Purpose
Target employers grouped by the kind of background each category calls for.

## Categories

### Public-sector adult services
**Why this background matters here:** Fifteen years bridging clinical practice
and systems-level program design — a rare fit for program-director roles that
need both a supervisor and a systems thinker.

Employers in this category:
- Metro Health Authority
- Community First Coalition

### Mission-driven benefit corporations
**Why this background matters here:** Outcomes framing (unsheltered-days
reduction) translates directly into the impact-report narrative these
employers expect from senior hires.

Employers in this category:
- Sample Benefit Corporation
<<<END FILE: business_sector_employers_reference.md>>>

Reply **next**.

User: next
Assistant:

<<<FILE: jsearch_queries.txt>>>
# Generated by findajob onboarding interviewer v2 — 2026-04-20
# 3-4 word natural phrases. One per line. 10 queries max.

clinical social worker
adult services director
community mental health
program director social
continuum of care
housing case management
<<<END FILE: jsearch_queries.txt>>>

Reply **next**.

User: next
Assistant:

<<<FILE: prefilter_rules.yaml>>>
# Generated by findajob onboarding interviewer v2 — 2026-04-20

hard_rejects:
  spam:
    - '^manage\s+job\s+alerts?\b'
    - '^your\s+job\s+alert\s+for\b'
    - '\bjoin\s+our\s+talent\s+network\b'

  corrections:
    - '\bcorrections?\s+(officer|counselor|case\s+manager)\b'
    - '\bprison\s+social\s+worker\b'

  child_welfare:
    - '\bchild\s+protective\s+services?\b'
    - '\bcps\s+case\s+worker\b'

  substitute:
    - '\bsubstitute\s+(teacher|counselor|social\s+worker)\b'
<<<END FILE: prefilter_rules.yaml>>>

Reply **next**.

User: next
Assistant:

<<<FILE: in_domain_patterns.yaml>>>
# Generated by findajob onboarding interviewer v2 — 2026-04-20

positive:
  - '\bclinical\s+social\s+worker\b'
  - '\blcsw\b'
  - '\bprogram\s+director\b.*\b(adult|community)\b'
  - '\bcase\s+manag(er|ement)\b'
  - '\bcontinuum\s+of\s+care\b'
<<<END FILE: in_domain_patterns.yaml>>>

That's all seven. Reply **next** for any final check, or let me know if any of them needs a redo.

User: thanks, got them.
```

(Do not commit trailing whitespace from copy-paste — `ruff format` has nothing to say about a txt fixture, but your editor might. Strip trailing spaces manually.)

- [ ] **Step 3: Commit the fixture**

```
git add tests/fixtures/onboarding/alice-doe-clean-emission.txt tests/fixtures/onboarding/__init__.py
git commit -m "test: add Alice Doe clean emission fixture for onboarding tests (#148)

Realistic interview emission in chat-transcript form containing all seven
delimited file blocks. Uses the public Alice Doe handle plus fully
fabricated non-PII data consistent with CLAUDE.md's domain-neutrality
rules. Used by route-level integration tests and the whole-feature E2E."
```

---

## Task 6 — `/onboarding/` GET route + landing template

**Files:**
- Create: `src/findajob/web/routes/onboarding.py`
- Create: `src/findajob/web/templates/onboarding/index.html`
- Create: `src/findajob/web/templates/onboarding/_paste_form.html`
- Modify: `src/findajob/web/routes/__init__.py`
- Test: `tests/test_web_onboarding_routes.py` (GET-only in this task; POST added in Task 7)

- [ ] **Step 1: Write the failing GET test**

Create `tests/test_web_onboarding_routes.py`:

```python
"""Integration tests for /onboarding/ routes (#148)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from findajob.web.app import create_app

_MINIMAL_SCHEMA = """
CREATE TABLE jobs (
    id TEXT PRIMARY KEY,
    fingerprint TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    company TEXT NOT NULL,
    stage TEXT DEFAULT 'discovered',
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL,
    field_changed TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT,
    changed_at TEXT DEFAULT (datetime('now'))
);
"""


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    db_path = tmp_path / "pipeline.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(_MINIMAL_SCHEMA)
    conn.close()
    (tmp_path / "companies").mkdir()
    app = create_app(
        companies_root=tmp_path / "companies",
        db_path=db_path,
        base_root=tmp_path,
    )
    return TestClient(app, follow_redirects=False)


def test_onboarding_index_returns_200(client: TestClient) -> None:
    resp = client.get("/onboarding/")
    assert resp.status_code == 200
    body = resp.text
    assert "onboarding" in body.lower()
    assert 'name="emission"' in body  # paste textarea
    assert "copy the prompt" in body.lower() or "Copy the prompt" in body


def test_rerun_mode_shows_backup_warning(client: TestClient) -> None:
    resp = client.get("/onboarding/?mode=rerun")
    assert resp.status_code == 200
    assert ".backups/" in resp.text
    assert "/config/" in resp.text  # pointer to editor for partial updates


def test_first_run_hides_backup_warning(client: TestClient) -> None:
    resp = client.get("/onboarding/")
    assert resp.status_code == 200
    # Backup path should NOT be prominent on first-run (there's nothing to back up)
    # Presence/absence is template-defined; this test asserts the specific
    # warning banner text is gated on ?mode=rerun.
    assert "Existing config will be backed up" not in resp.text


def test_onboarding_prompt_endpoint_returns_role_text(client: TestClient) -> None:
    resp = client.get("/onboarding/prompt")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/plain")
    # The interview role begins with this heading line
    assert "Onboarding Interviewer v2" in resp.text
```

- [ ] **Step 2: Run tests, confirm they fail**

Run: `uv run pytest tests/test_web_onboarding_routes.py -v`
Expected: all fail — no `/onboarding/` route exists.

- [ ] **Step 3: Create the route module**

Create `src/findajob/web/routes/onboarding.py`:

```python
"""Onboarding NUX: landing page + prompt endpoint + paste-back inject (#148).

Two GET routes land in this task; POST /onboarding/inject is added in Task 7.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, PlainTextResponse

router = APIRouter()


def _interview_prompt_path(base_root: Path) -> Path:
    return base_root / "config" / "roles" / "onboarding_interviewer.md"


@router.get("/onboarding/", response_class=HTMLResponse)
def onboarding_index(request: Request, mode: str = "") -> HTMLResponse:
    """Landing page. ``mode=rerun`` flips on the backup warning."""
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request=request,
        name="onboarding/index.html",
        context={
            "is_rerun": mode == "rerun",
            "paste_error": None,
            "paste_content": "",
        },
    )


@router.get("/onboarding/prompt", response_class=PlainTextResponse)
def onboarding_prompt(request: Request) -> PlainTextResponse:
    """Serve the interview role verbatim so the user can copy it.

    Delivered as ``text/plain; charset=utf-8`` so "copy to clipboard" UX
    is literal — the user pastes the exact bytes we ship.
    """
    base_root: Path = request.app.state.base_root
    prompt_path = _interview_prompt_path(base_root)
    text = prompt_path.read_text(encoding="utf-8")
    return PlainTextResponse(content=text, media_type="text/plain; charset=utf-8")
```

- [ ] **Step 4: Create the landing template**

Create `src/findajob/web/templates/onboarding/index.html`:

```html
{% extends "base.html" %}

{% block title %}Onboarding — findajob{% endblock %}

{% block content %}
<div class="max-w-3xl mx-auto p-6 space-y-6">
  <h1 class="text-2xl font-semibold">Set up your findajob pipeline</h1>

  {% if is_rerun %}
  <div class="border border-amber-300 bg-amber-50 text-amber-900 px-4 py-3 rounded">
    <p class="font-medium">Re-running onboarding</p>
    <p class="text-sm mt-1">
      Existing config will be backed up to <code>{base_root}/.backups/&lt;UTC-stamp&gt;/</code>
      before overwrite. For partial updates (e.g., add an exclusion category) use
      <a class="underline" href="/config/">/config/</a> directly — faster than a full re-run.
    </p>
  </div>
  {% endif %}

  <section class="bg-white border rounded p-4 space-y-3">
    <h2 class="font-semibold">How this works</h2>
    <ol class="list-decimal list-inside space-y-1 text-sm">
      <li>Open a new chat in your chosen LLM (paid reasoning tier required).</li>
      <li>Copy the full interview prompt and paste it into the chat.</li>
      <li>Work through the interview (~90 min; you can pause and resume).</li>
      <li>When the LLM emits the seven file blocks, copy the entire chat and paste it below.</li>
      <li>We'll parse the blocks and inject them into your stack's config.</li>
    </ol>
  </section>

  <section class="bg-white border rounded p-4 space-y-3">
    <h2 class="font-semibold">Before you start</h2>
    <ul class="list-disc list-inside space-y-1 text-sm">
      <li>Have your current resume (PDF or DOCX) ready to upload into the chat.</li>
      <li>Optional but helpful: recent performance reviews, 360s, prior cover letters.</li>
      <li>Pick a paid reasoning-grade LLM (see links below).</li>
    </ul>
    <p class="text-xs text-gray-600">
      Full prework checklist:
      <a class="underline" href="https://github.com/brockamer/findajob/blob/main/docs/onboarding-prework-checklist.md" target="_blank">
        docs/onboarding-prework-checklist.md
      </a>
    </p>
  </section>

  <section class="bg-white border rounded p-4 space-y-3">
    <h2 class="font-semibold">Step 1 — Copy the interview prompt</h2>
    <button type="button"
            class="inline-flex items-center gap-2 bg-slate-700 text-white px-3 py-1.5 rounded text-sm hover:bg-slate-600"
            onclick="window.__fjCopyPrompt()">
      Copy the interview prompt
    </button>
    <p class="text-xs text-gray-600">
      Or fetch it raw at <a class="underline" href="/onboarding/prompt">/onboarding/prompt</a>.
    </p>
  </section>

  <section class="bg-white border rounded p-4 space-y-3">
    <h2 class="font-semibold">Step 2 — Open a new chat</h2>
    <div class="flex flex-wrap gap-2">
      <a href="https://claude.ai/new" target="_blank"
         class="px-3 py-1.5 border rounded text-sm hover:bg-slate-50">Open Claude</a>
      <a href="https://chatgpt.com/" target="_blank"
         class="px-3 py-1.5 border rounded text-sm hover:bg-slate-50">Open ChatGPT</a>
      <a href="https://gemini.google.com/app" target="_blank"
         class="px-3 py-1.5 border rounded text-sm hover:bg-slate-50">Open Gemini</a>
    </div>
    <p class="text-xs text-gray-600">
      Paste the prompt from Step 1, upload your resume when asked, and work through the five phases.
    </p>
  </section>

  <section class="bg-white border rounded p-4 space-y-3">
    <h2 class="font-semibold">Step 3 — Paste the emission back</h2>
    {% include "onboarding/_paste_form.html" %}
  </section>
</div>

<script>
  window.__fjCopyPrompt = async function() {
    const resp = await fetch("/onboarding/prompt");
    const text = await resp.text();
    await navigator.clipboard.writeText(text);
    alert("Interview prompt copied. Paste it into your new chat.");
  };
</script>
{% endblock %}
```

- [ ] **Step 5: Create the paste form partial**

Create `src/findajob/web/templates/onboarding/_paste_form.html`:

```html
{# Paste form partial — re-rendered by POST /onboarding/inject on parse failure
   so `paste_content` and `paste_error` preserve the user's input. #}
<form method="post" action="/onboarding/inject" class="space-y-3">
  {% if paste_error %}
  <div class="border border-red-300 bg-red-50 text-red-900 px-4 py-3 rounded">
    <p class="font-medium">Couldn't parse your paste.</p>
    <p class="text-sm mt-1">{{ paste_error }}</p>
  </div>
  {% endif %}
  <label class="block text-sm font-medium" for="emission">
    Paste the full chat transcript (or just the seven delimited blocks):
  </label>
  <textarea name="emission" id="emission" rows="20"
            class="w-full border rounded p-2 font-mono text-xs"
            placeholder="Paste from your LLM chat here...">{{ paste_content }}</textarea>
  <button type="submit"
          class="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700">
    Inject config
  </button>
</form>
```

- [ ] **Step 6: Wire the router**

Edit `src/findajob/web/routes/__init__.py` — add onboarding import and include:

```python
"""Aggregates all sub-module routers into a single `router` the app includes."""

from fastapi import APIRouter

from findajob.web.routes import (
    board,
    board_actions,
    config,
    healthz,
    ingest,
    landing,
    materials,
    onboarding,
    stats,
    tools,
)

router = APIRouter()
router.include_router(materials.router)
router.include_router(healthz.router)
router.include_router(landing.router)
router.include_router(board.router)
router.include_router(board_actions.router)
router.include_router(ingest.router)
router.include_router(stats.router)
router.include_router(config.router)
router.include_router(tools.router)
router.include_router(onboarding.router)
```

(Guard dependencies are added to the board/materials/stats includes in Task 8.)

- [ ] **Step 7: Run tests**

Run: `uv run pytest tests/test_web_onboarding_routes.py -v`
Expected: 4 passed.

- [ ] **Step 8: Lint**

Run: `uv run ruff check src/findajob/web/routes/onboarding.py && uv run ruff format --check src/findajob/web/routes/onboarding.py src/findajob/web/routes/__init__.py`
Expected: clean.

- [ ] **Step 9: Commit**

```
git add src/findajob/web/routes/onboarding.py src/findajob/web/templates/onboarding/ src/findajob/web/routes/__init__.py tests/test_web_onboarding_routes.py
git commit -m "feat(web): add /onboarding/ landing page + prompt endpoint (#148)

GET /onboarding/ renders a five-step landing page (copy prompt, open LLM,
paste emission) with a rerun-mode banner gated on ?mode=rerun. GET
/onboarding/prompt serves the interview role prompt verbatim so the
browser clipboard button gets the exact bytes."
```

---

## Task 7 — `POST /onboarding/inject`

**Files:**
- Modify: `src/findajob/web/routes/onboarding.py`
- Test: append cases to `tests/test_web_onboarding_routes.py`

- [ ] **Step 1: Add the failing POST tests**

Append to `tests/test_web_onboarding_routes.py`:

```python
from pathlib import Path as _Path

_FIXTURE_DIR = _Path(__file__).parent / "fixtures" / "onboarding"


def _read_fixture(name: str) -> str:
    return (_FIXTURE_DIR / name).read_text(encoding="utf-8")


def test_inject_clean_emission_redirects_to_board(client: TestClient, tmp_path: Path) -> None:
    blob = _read_fixture("alice-doe-clean-emission.txt")
    resp = client.post("/onboarding/inject", data={"emission": blob})
    assert resp.status_code == 303
    assert resp.headers["location"] == "/board/dashboard"
    # Files on disk under the TestClient's base_root (tmp_path)
    assert (tmp_path / "candidate_context" / "profile.md").is_file()
    assert (tmp_path / "config" / "target_companies.md").is_file()
    assert (tmp_path / "config" / "companies_of_interest.txt").is_file()
    assert (tmp_path / "data" / ".onboarding-complete").is_file()


def test_inject_missing_block_rerenders_with_error(client: TestClient, tmp_path: Path) -> None:
    blob = _read_fixture("alice-doe-clean-emission.txt")
    # Strip one block
    lines = blob.splitlines(keepends=True)
    stripped = []
    skip = False
    for line in lines:
        if "<<<FILE: in_domain_patterns.yaml>>>" in line:
            skip = True
        if not skip:
            stripped.append(line)
        if "<<<END FILE: in_domain_patterns.yaml>>>" in line:
            skip = False
    broken = "".join(stripped)

    resp = client.post("/onboarding/inject", data={"emission": broken})
    assert resp.status_code == 400
    body = resp.text
    assert "in_domain_patterns.yaml" in body
    # Textarea content preserved
    assert "Metro Continuum of Care" in body
    # No sentinel written
    assert not (tmp_path / "data" / ".onboarding-complete").exists()
    # No files written
    assert not (tmp_path / "candidate_context" / "profile.md").exists()


def test_inject_empty_paste_rerenders_with_error(client: TestClient, tmp_path: Path) -> None:
    resp = client.post("/onboarding/inject", data={"emission": ""})
    assert resp.status_code == 400
    body = resp.text
    assert "missing" in body.lower()
    assert not (tmp_path / "data" / ".onboarding-complete").exists()


def test_inject_populates_companies_of_interest_from_tier1(client: TestClient, tmp_path: Path) -> None:
    blob = _read_fixture("alice-doe-clean-emission.txt")
    resp = client.post("/onboarding/inject", data={"emission": blob})
    assert resp.status_code == 303
    coi = (tmp_path / "config" / "companies_of_interest.txt").read_text()
    assert "Metro Health Authority" in coi
    assert "Sample Benefit Corporation" in coi
    assert "Community First Coalition" in coi
    # Tier 2 NOT included
    assert "Regional Care Network" not in coi
```

- [ ] **Step 2: Run tests, confirm they fail**

Run: `uv run pytest tests/test_web_onboarding_routes.py -v -k "inject"`
Expected: 4 new tests fail — no POST handler.

- [ ] **Step 3: Implement the POST handler**

Edit `src/findajob/web/routes/onboarding.py` — append:

```python
from fastapi import Form
from fastapi.responses import RedirectResponse

from findajob.onboarding import inject, parse_emission


@router.post("/onboarding/inject")
def onboarding_inject(
    request: Request,
    emission: str = Form(...),
) -> HTMLResponse | RedirectResponse:
    """Parse and inject an interview emission; redirect to /board/ on success."""
    result = parse_emission(emission)
    if result.missing:
        templates = request.app.state.templates
        return templates.TemplateResponse(
            request=request,
            name="onboarding/index.html",
            context={
                "is_rerun": False,
                "paste_content": emission,
                "paste_error": (
                    f"Your paste is missing: {', '.join(result.missing)}. "
                    "Scroll through your chat for any <<<FILE: name>>> block "
                    "that's not in your paste and include it."
                ),
            },
            status_code=400,
        )
    base_root: Path = request.app.state.base_root
    inject(base_root, result.found)
    # Clear cached guard state so the next /board/ request passes through
    request.app.state.onboarding_complete = True
    return RedirectResponse(url="/board/dashboard", status_code=303)
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_web_onboarding_routes.py -v`
Expected: 8 passed (4 GET + 4 POST).

- [ ] **Step 5: Lint**

Run: `uv run ruff check src/findajob/web/routes/onboarding.py && uv run ruff format --check src/findajob/web/routes/onboarding.py`
Expected: clean.

- [ ] **Step 6: Commit**

```
git add src/findajob/web/routes/onboarding.py tests/test_web_onboarding_routes.py
git commit -m "feat(web): POST /onboarding/inject — parse and write seven files (#148)

Success path: parse → inject (atomic, backup-first) → clear guard cache →
303 /board/dashboard. Failure path: 400 with re-rendered paste form,
textarea content preserved, named the missing file(s) in the error box.
No partial writes on failure."
```

---

## Task 8 — Attach guard to board / materials / stats

**Files:**
- Modify: `src/findajob/web/routes/__init__.py`
- Test: `tests/test_web_onboarding_guard.py` (already written in Task 4 — this task turns it green)

- [ ] **Step 1: Run guard tests, confirm they still fail**

Run: `uv run pytest tests/test_web_onboarding_guard.py -v`
Expected: gated-routes tests fail (currently 200, not 307).

- [ ] **Step 2: Wire the dependency onto each gated router include**

Edit `src/findajob/web/routes/__init__.py`:

```python
"""Aggregates all sub-module routers into a single `router` the app includes."""

from fastapi import APIRouter, Depends

from findajob.web.onboarding_guard import require_onboarding_complete
from findajob.web.routes import (
    board,
    board_actions,
    config,
    healthz,
    ingest,
    landing,
    materials,
    onboarding,
    stats,
    tools,
)

_guard = [Depends(require_onboarding_complete)]

router = APIRouter()
router.include_router(materials.router, dependencies=_guard)
router.include_router(healthz.router)
router.include_router(landing.router)
router.include_router(board.router, dependencies=_guard)
router.include_router(board_actions.router, dependencies=_guard)
router.include_router(ingest.router)
router.include_router(stats.router, dependencies=_guard)
router.include_router(config.router)
router.include_router(tools.router)
router.include_router(onboarding.router)
```

- [ ] **Step 3: Run guard tests**

Run: `uv run pytest tests/test_web_onboarding_guard.py -v`
Expected: all pass.

- [ ] **Step 4: Run full suite to catch guard collateral damage**

Run: `uv run pytest tests/ -v`
Expected: all pass. If anything in `test_web_board_*` breaks because the board dependency now requires a sentinel, update those tests to `mark_complete(tmp_path)` in the fixture setup (the tests are exercising board behavior, not the guard; they should come up with a configured stack).

- [ ] **Step 5: Commit**

```
git add src/findajob/web/routes/__init__.py
git commit -m "feat(web): attach onboarding guard to board/materials/stats (#148)

Adds Depends(require_onboarding_complete) to the three router includes
that make no sense before onboarding is done. Healthz, /, /onboarding/*,
/config/, /tools/, /ingest/ remain ungated.

Pre-existing board/materials/stats tests that instantiate create_app now
need a sentinel written in their fixture setup (otherwise they redirect
instead of returning 200)."
```

(If Step 4 exposes collateral-damage failures in pre-existing tests, fix them in a follow-up commit in this task. The fix pattern is: in each fixture that builds a `TestClient`, call `findajob.onboarding.mark_complete(tmp_path)` before `create_app(...)`.)

---

## Task 9 — `/tools/` card for re-run

**Files:**
- Modify: `src/findajob/web/templates/tools/index.html`
- Test: `tests/test_web_onboarding_routes.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_web_onboarding_routes.py`:

```python
def test_tools_page_links_to_onboarding_rerun(client: TestClient) -> None:
    resp = client.get("/tools/")
    assert resp.status_code == 200
    body = resp.text
    assert "/onboarding/?mode=rerun" in body
    assert "Run onboarding interview" in body
```

Note: `/tools/` is not gated by the guard, so this test should pass from an unconfigured stack.

- [ ] **Step 2: Run, confirm fails**

Run: `uv run pytest tests/test_web_onboarding_routes.py::test_tools_page_links_to_onboarding_rerun -v`
Expected: fails — the card isn't there yet.

- [ ] **Step 3: Update the template**

Edit `src/findajob/web/templates/tools/index.html`:

```html
{% extends "base.html" %}

{% block title %}Tools — findajob{% endblock %}

{% block content %}
<div class="max-w-4xl mx-auto p-6">
  <h1 class="text-2xl font-semibold mb-4">Tools</h1>
  <ul class="divide-y border rounded bg-white">
    <li class="px-4 py-3">
      <a href="/onboarding/?mode=rerun" class="text-blue-600 hover:underline font-medium">Run onboarding interview</a>
      <p class="text-sm text-gray-600">
        Initial setup or full re-run after a major role pivot. Backs up
        existing config before overwriting. For partial updates, use
        "Edit config files" below.
      </p>
    </li>
    <li class="px-4 py-3">
      <a href="/config/" class="text-blue-600 hover:underline font-medium">Edit config files</a>
      <p class="text-sm text-gray-600">Profile, master resume, search config, role prompts.</p>
    </li>
  </ul>
  <p class="text-xs text-gray-500 mt-4">
    More tools (doctor, scoreboard, feedback inspector) land here as they ship.
  </p>
</div>
{% endblock %}
```

- [ ] **Step 4: Run test**

Run: `uv run pytest tests/test_web_onboarding_routes.py::test_tools_page_links_to_onboarding_rerun -v`
Expected: passes.

- [ ] **Step 5: Commit**

```
git add src/findajob/web/templates/tools/index.html tests/test_web_onboarding_routes.py
git commit -m "feat(web/tools): link to onboarding re-run (#148)

Adds 'Run onboarding interview' card above the config editor link with
the backup-first explanation and pointer at /config/ for partial edits."
```

---

## Task 10 — Whole-feature end-to-end verification

**Files:**
- Create: `tests/test_onboarding_e2e.py`

- [ ] **Step 1: Write the E2E test**

Create `tests/test_onboarding_e2e.py`:

```python
"""Whole-feature verification for onboarding NUX + inject (#148).

Simulates a fresh stack: empty state/, no sentinel, config_loader sees nothing.
After one paste + redirect, the pipeline has everything it needs.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from findajob.web.app import create_app

_MINIMAL_SCHEMA = """
CREATE TABLE jobs (
    id TEXT PRIMARY KEY,
    fingerprint TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    company TEXT NOT NULL,
    stage TEXT DEFAULT 'discovered',
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL,
    field_changed TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT,
    changed_at TEXT DEFAULT (datetime('now'))
);
"""

_FIXTURE = (
    Path(__file__).parent / "fixtures" / "onboarding" / "alice-doe-clean-emission.txt"
)


def test_fresh_stack_end_to_end(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # --- fresh stack: empty state/, no sentinel ---
    db_path = tmp_path / "pipeline.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(_MINIMAL_SCHEMA)
    conn.close()
    (tmp_path / "companies").mkdir()
    # Role prompt must be reachable for GET /onboarding/prompt; copy from repo
    (tmp_path / "config" / "roles").mkdir(parents=True)
    role_src = Path(__file__).parent.parent / "config" / "roles" / "onboarding_interviewer.md"
    (tmp_path / "config" / "roles" / "onboarding_interviewer.md").write_text(
        role_src.read_text(encoding="utf-8"), encoding="utf-8"
    )

    app = create_app(
        companies_root=tmp_path / "companies",
        db_path=db_path,
        base_root=tmp_path,
    )
    client = TestClient(app, follow_redirects=False)

    # --- Step 1: GET /board/ redirects to /onboarding/ ---
    r = client.get("/board/dashboard")
    assert r.status_code == 307
    assert r.headers["location"] == "/onboarding/"

    # --- Step 2: /onboarding/ is reachable and renders paste form ---
    r = client.get("/onboarding/")
    assert r.status_code == 200
    assert 'name="emission"' in r.text

    # --- Step 3: paste the fixture ---
    blob = _FIXTURE.read_text(encoding="utf-8")
    r = client.post("/onboarding/inject", data={"emission": blob})
    assert r.status_code == 303
    assert r.headers["location"] == "/board/dashboard"

    # --- Step 4: seven canonical files on disk ---
    assert (tmp_path / "candidate_context" / "profile.md").is_file()
    assert (tmp_path / "candidate_context" / "master_resume.md").is_file()
    assert (tmp_path / "config" / "target_companies.md").is_file()
    assert (tmp_path / "config" / "business_sector_employers_reference.md").is_file()
    assert (tmp_path / "config" / "jsearch_queries.txt").is_file()
    assert (tmp_path / "config" / "prefilter_rules.yaml").is_file()
    assert (tmp_path / "config" / "in_domain_patterns.yaml").is_file()

    # --- Step 5: derivation populates companies_of_interest.txt correctly ---
    coi = (tmp_path / "config" / "companies_of_interest.txt").read_text()
    assert "Metro Health Authority" in coi

    # --- Step 6: sentinel present, timestamp parses ---
    sentinel = (tmp_path / "data" / ".onboarding-complete").read_text().strip()
    assert sentinel.endswith("Z")

    # --- Step 7: /board/ is now reachable ---
    r = client.get("/board/dashboard")
    assert r.status_code != 307 or r.headers.get("location") != "/onboarding/"

    # --- Step 8: config_loader sees the Tier 1 set ---
    # Temporarily point BASE at tmp_path and reload config_loader state
    monkeypatch.setenv("JSP_BASE", str(tmp_path))
    if "findajob.config_loader" in sys.modules:
        del sys.modules["findajob.config_loader"]
    # Also reload paths because BASE is computed at import time there
    if "findajob.paths" in sys.modules:
        del sys.modules["findajob.paths"]
    import findajob.paths  # noqa: F401 — re-import with new BASE
    from findajob.config_loader import load_companies_of_interest

    companies = load_companies_of_interest()
    assert companies, "companies_of_interest must be populated after injection"
    assert any("metro" in c for c in companies)
```

- [ ] **Step 2: Run the E2E test**

Run: `uv run pytest tests/test_onboarding_e2e.py -v`
Expected: passes.

- [ ] **Step 3: Commit**

```
git add tests/test_onboarding_e2e.py
git commit -m "test(onboarding): end-to-end verification of fresh-stack flow (#148)

Simulates empty state/, walks the full redirect → paste → inject →
files-on-disk → guard-cleared → config_loader-sees-companies chain.
Uses the committed Alice Doe fixture."
```

---

## Task 11 — Documentation updates

**Files:**
- Modify: `CLAUDE.md`
- Modify: `docs/onboarding-prework-checklist.md`
- Modify: `config/roles/onboarding_interviewer.md`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Update CLAUDE.md — Web Frontend Architecture section**

Edit `CLAUDE.md`. In the "Web Frontend Architecture" section, append a paragraph about `/onboarding/` and the sentinel:

Find the paragraph that starts with "Lives at `src/findajob/web/`..." and after the existing paragraph about `/config/`, add:

```markdown
`/onboarding/` is the first-run NUX + paste-back injector for the interview
emitted by `config/roles/onboarding_interviewer.md`. A FastAPI dependency on
the `/board/*`, `/materials/*`, and `/stats/*` router includes redirects to
`/onboarding/` when `{base_root}/data/.onboarding-complete` is missing. The
paste-back injector writes seven canonical config files (under
`candidate_context/` and `config/`) plus a derived
`config/companies_of_interest.txt`, and backs up any existing destinations
to `{base_root}/.backups/{UTC-stamp}/` first. Re-triggerable from `/tools/`
via `/onboarding/?mode=rerun`. See
`findajob.onboarding.parser`/`findajob.onboarding.injector`/
`findajob.web.onboarding_guard` for the implementation boundaries (#148).
```

- [ ] **Step 2: Update CLAUDE.md — Key File Locations**

Edit `CLAUDE.md`. In the "Key File Locations" fenced block, under the package section, add:

```
<repo>/src/findajob/onboarding/parser.py    # parse interview emission into files to inject (#148)
<repo>/src/findajob/onboarding/injector.py  # atomic write + backup + Tier-1 derivation + sentinel (#148)
<repo>/src/findajob/web/onboarding_guard.py # NUX guard dependency (#148)
<repo>/src/findajob/web/routes/onboarding.py # GET /onboarding/ + POST /onboarding/inject (#148)
```

- [ ] **Step 3: Update CLAUDE.md — Container Context table**

In the "Container Context" table, after the `candidate_context/` row, add:

```
| `{base_root}/.backups/{stamp}/` | N/A (new in #148) | `/app/.backups/` (bind-mount from `./state/.backups/`) |
| Onboarding sentinel | N/A | `/app/data/.onboarding-complete` (bind-mount from `./state/data/`) |
```

Also update the host-side compose bind-mount list in CLAUDE.local.md's "Platform" table if it enumerates `state/*` subdirs — add `state/.backups/` so the bind exists.

- [ ] **Step 4: Update `docs/onboarding-prework-checklist.md`**

Find the "Running the interview" section and replace the last two bullets:

Old:
```
- [ ] Paste the full contents of `config/roles/onboarding_interviewer.md`
      into the new chat and hit send.
- [ ] Follow the phase prompts. Upload your documents when asked.
- [ ] When the prompt emits files at the end, your instance operator will
      extract each block — you don't need to handle that yourself.
```

New:
```
- [ ] In your stack's web UI, visit `/onboarding/`. Click "Copy the
      interview prompt" and paste it into the new chat you opened.
- [ ] Follow the phase prompts. Upload your documents when asked.
- [ ] When the LLM has emitted all seven file blocks, copy the entire
      chat (or just the seven blocks — the parser handles either) and
      paste it into the text box at the bottom of `/onboarding/`.
      Click "Inject config". The pipeline is configured.
```

- [ ] **Step 5: Update `config/roles/onboarding_interviewer.md`**

Find the "## After the interview" section at the very bottom:

Old:
```
## After the interview

> Your instance operator will extract each emitted block to the correct file path on
> your findajob stack. You do not need to do this yourself.
```

New:
```
## After the interview

> When you've emitted all seven files, return to your findajob stack's
> `/onboarding/` page. Copy the entire chat (or just the seven delimited
> blocks) into the text box and click **Inject config**. The pipeline
> will parse the blocks, back up any existing config, write the new
> files, and land you on your Board. You don't need to handle file
> extraction by hand.
```

- [ ] **Step 6: Update `CHANGELOG.md`**

Find the `## [Unreleased]` section. Under `### Added` (creating the subsection if missing), add:

```
- Onboarding NUX at `/onboarding/`: first-run stacks are redirected from
  `/board/`, `/materials/`, and `/stats/` to a guided landing page that
  walks the user through running the interview in their chosen LLM and
  pastes the emission back for automatic injection. Re-triggerable from
  `/tools/` for full re-runs. Existing config is backed up to
  `{base_root}/.backups/{UTC-stamp}/` before overwrite (#148).
- `/config/` editor now exposes `config/target_companies.md` and
  `config/business_sector_employers_reference.md` for post-injection
  tuning (#148).
```

- [ ] **Step 7: Verify docs render cleanly**

Run: `uv run pytest tests/ -v`
Expected: all pass — including any existing CLAUDE.md lint / format check.

- [ ] **Step 8: Commit**

```
git add CLAUDE.md docs/onboarding-prework-checklist.md config/roles/onboarding_interviewer.md CHANGELOG.md
git commit -m "docs: update CLAUDE/prework/interview/CHANGELOG for #148

- CLAUDE.md: add /onboarding/ + sentinel + .backups/ to Web Frontend
  Architecture, Key File Locations, Container Context.
- docs/onboarding-prework-checklist.md: replace 'operator extracts' with
  'paste into /onboarding/'.
- config/roles/onboarding_interviewer.md: update closing note to match.
- CHANGELOG.md: Unreleased/Added entries for the NUX + editor allowlist
  extensions."
```

---

## Task 12 — File follow-up issues on the board

Neither follow-up is implementation work for this PR, but both need to exist on the board before the PR merges so the pre-existing drift identified in the spec doesn't get lost.

- [ ] **Step 1: File the `companies_of_interest.txt` retirement issue**

Run:
```
gh issue create --title "Retire config/companies_of_interest.txt; read target_companies.md Tier 1 directly" --body "$(cat <<'EOF'
Follow-up to #148. After the onboarding injector lands, `companies_of_interest.txt` is derived from `target_companies.md` Tier 1 at injection time. The cleaner end-state is to delete the derived file entirely and have `findajob.config_loader.is_company_of_interest()` parse `target_companies.md` directly each time it's called (cached).

## Scope

- Update `findajob.config_loader.load_companies_of_interest()` to read `config/target_companies.md` Tier 1 and return a frozenset of normalized company names.
- Remove the derivation step from `findajob.onboarding.injector.inject` — no longer needed.
- Remove `companies_of_interest.txt` from the `bootstrap.sh` copy step and from `.example` files.
- Delete `config/companies_of_interest.txt.example`.
- Update `docs/setup/configure.md` to stop mentioning the derived file.

## Depends on

#148 — injection must land first so the derivation is the only writer.

## Why separate

Keeps #148 focused on "get injection working" without touching the scoring read path. Separating the two also lets us ship #148 sooner and validate the onboarding flow without simultaneously changing scorer behavior.
EOF
)"
```

Then add to the board:

```
gh project item-add 1 --owner brockamer --url <url-printed-by-create>
```

- [ ] **Step 2: File the `feed_urls.txt` interview extension issue**

Run:
```
gh issue create --title "Onboarding interview v3: emit feed_urls.txt from Tier 1 Greenhouse slugs" --body "$(cat <<'EOF'
Follow-up to #148. The v2 interview emits seven files but not `config/feed_urls.txt` (Greenhouse company slugs). This is left to `bootstrap.sh`'s `.example` copy today, which is a degraded UX — most users won't figure out how to populate it.

## Scope

- Extend `config/roles/onboarding_interviewer.md` to Phase 5 emit an eighth file: `feed_urls.txt` derived from Tier 1 companies with public Greenhouse boards (best-effort; the interview asks the user to confirm each slug).
- Add `feed_urls.txt` to the onboarding injector's filename allowlist.
- Update `tests/fixtures/onboarding/alice-doe-clean-emission.txt` to include the new block.
- Update tests to assert eight files injected.

## Depends on

#148 — injection path must exist first.

## Why separate

Greenhouse slug discovery is an LLM-quality question (does the model reliably find slugs from company names?) that can be iterated separately from the injection plumbing.
EOF
)"
```

Then add to the board:

```
gh project item-add 1 --owner brockamer --url <url-printed-by-create>
```

- [ ] **Step 3: Confirm both issues are on the board with Backlog status + Low Priority**

Run:
```
gh project item-list 1 --owner brockamer --format json | grep -E "companies_of_interest|feed_urls" -A 1
```

Expected: both titles show up with a project item id. Set Priority: Low and Status: Backlog via `jared:jared-file` defaults or the raw `gh project item-edit` (field + option IDs are in `docs/project-board.md` "Fields quick reference").

---

## Whole-feature verification gate

Before opening the PR:

- [ ] `uv run pytest tests/ -v` — all tests pass (unit, integration, E2E).
- [ ] `uv run ruff check . && uv run ruff format --check .` — clean.
- [ ] `uv run mypy src/findajob/` — clean on touched modules.
- [ ] Manual local-stack smoke:
  1. Remove `state/data/.onboarding-complete` on docker.lan if present.
  2. Pull the branch's image (or rebuild locally via `docker compose build`).
  3. `curl -sI http://docker.lan:$PORT/board/dashboard | grep -i location` — expect `/onboarding/`.
  4. Open `/onboarding/` in a browser, click "Copy the interview prompt," confirm clipboard contains the role.
  5. Paste the Alice Doe fixture into the textarea, click Inject config, confirm redirect to Dashboard.
  6. `ls state/candidate_context state/config state/data/.onboarding-complete state/.backups/` — confirm layout.
  7. Go to `/config/`, click `target_companies.md`, confirm editor loads.
  8. Go to `/tools/`, click "Run onboarding interview," confirm `/onboarding/?mode=rerun` shows the backup-warning banner.
- [ ] Follow-up issues (Task 12) filed and on board with Priority.
- [ ] Open PR with the `migration-required` label? **No** — this feature adds `state/.backups/` and a sentinel file, but:
  - New files in bind-mounted dirs don't require operator action.
  - The sentinel is missing on existing stacks, which triggers the NUX for the operator once (harmless — their config is already present, the interview is optional).
  - However: existing stacks with config already in place will get redirected to `/onboarding/` on first request after this ships. **Add migration-required** and the release note text: "On upgrade, `state/data/.onboarding-complete` must be touched manually on any stack that is already configured, or operators must run the onboarding interview once to generate it."
  - Recommended post-merge step (in the release PR description): `docker compose exec scheduler python -c "from findajob.onboarding import mark_complete; from pathlib import Path; mark_complete(Path('/app'))"` — idempotent, one-liner for operators on already-configured stacks.

---

## Documentation Impact

Every surface this plan modifies for doc parity:

- **`CLAUDE.md`** — Task 11 Step 1/2/3: Web Frontend Architecture paragraph on `/onboarding/`; Key File Locations entries for the four new modules; Container Context rows for `/app/.backups/` and `/app/data/.onboarding-complete`.
- **`CLAUDE.local.md`** — Task 11 Step 3: add `state/.backups/` to the bind-mount list. (Gitignored; operator-local.)
- **`docs/onboarding-prework-checklist.md`** — Task 11 Step 4: replace "instance operator will extract" with "paste into /onboarding/".
- **`config/roles/onboarding_interviewer.md`** — Task 11 Step 5: update "After the interview" closing note.
- **`CHANGELOG.md`** — Task 11 Step 6: `[Unreleased]` → `### Added` entries for both the NUX + the editor allowlist extensions.
- **Spec doc `docs/superpowers/specs/2026-04-23-148-onboarding-nux-design.md`** — no changes expected. If implementation reveals a spec flaw, append a "Decisions made during implementation" section in the same PR rather than silently diverging.
- **Docstrings** — module-level docstrings on all four new modules (parser, injector, onboarding_guard, onboarding routes), as shown in their Task code blocks.
- **New user-facing doc** — none. The `/onboarding/` page itself carries the first-run instructions, and the prework checklist handles the pre-interview prep.
- **Release note (for the next `v*.*.*` tag)** — the CHANGELOG entries from Step 6 carry through via the release-notes generation flow. If this PR gets the `migration-required` label (see Whole-feature gate), also add the one-liner sentinel-touch command to the release notes.

---

## Self-review checklist

**Spec coverage** (every spec section → the task that implements it):

- [ ] Spec "Components" → Tasks 1, 2, 3, 4, 6, 7, 8, 9
- [ ] Spec "Data flow" first-run path → Tasks 6, 7, 8 + Task 10 E2E
- [ ] Spec "Data flow" re-run path → Tasks 6 (mode=rerun template branch), 7, 9 (/tools/ card)
- [ ] Spec "Data flow" parse-failure path → Task 7 (re-render with preserved textarea + error)
- [ ] Spec "Parser spec" → Task 1
- [ ] Spec "Injection spec" (target paths, Tier 1 derivation, backup, atomicity, sentinel) → Task 2
- [ ] Spec "NUX guard" → Tasks 4 + 8
- [ ] Spec "/tools/ integration" → Task 9
- [ ] Spec "/config/ editor allowlist update" → Task 3
- [ ] Spec "Testing" unit → Tasks 1, 2, 3, 4
- [ ] Spec "Testing" route-level → Tasks 6, 7, 8, 9
- [ ] Spec "Testing" whole-feature gate → Task 10
- [ ] Spec "Out of scope" — no implementation tasks; confirmed via Task 12 follow-ups
- [ ] Spec "Documentation Impact" → Task 11 (all bullets addressed)
- [ ] Spec "Follow-up issues" → Task 12
- [ ] Spec "Self-review checklist" for the plan → this section

**Placeholder scan:** no `TBD` / `TODO` / `FIXME` strings in this plan. Verified by `grep -n "TBD\|TODO\|FIXME" docs/superpowers/plans/2026-04-23-148-onboarding-nux.md` returning nothing.

**Type / identifier consistency across tasks:**

- `ParsedEmission` dataclass used in Task 1 definition and Task 7 handler.
- `ALLOWED_FILENAMES` exported from `parser.py` (Task 1), re-exported by `__init__.py` (Task 2), used by `injector.py` (Task 2).
- `inject(base_root, found)` signature stable from Task 2 → Task 7.
- `is_complete(base_root)` and `mark_complete(base_root)` signatures stable from Task 2 → Tasks 4, 7, 10.
- `require_onboarding_complete(request)` signature stable from Task 4 → Task 8.
- Destination paths (`_ALL_DESTINATIONS`), sentinel relpath (`data/.onboarding-complete`), backup root (`.backups`) defined once in `injector.py` (Task 2) and referenced nowhere else as string literals (except in tests, where they are asserted on).

**Scope drift check:** no task touches pipeline behavior beyond the onboarding flow. `config_loader` read path is explicitly NOT modified — follow-up #12 handles that.
