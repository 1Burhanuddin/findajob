---
**Shipped in #2, #310, #310, #408 on 2026-05-02. Final decisions captured in issue body.**
---

# #408 curated RapidAPI feed picker + JobSourceAdapter framework — Implementation Plan

## Issue

- #408
- #310 (closed by this plan)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introduce a pluggable `JobSourceAdapter` framework for RapidAPI-flavored job sources (jobs-api14 + JSearch as the first two), add a per-stack active-source registry, and a profile-grounded picker step in the onboarding interview that recommends the right feed for each candidate's field. Closes #310 (JSearch adapter ships as Adapter #2 validating the framework).

**Architecture:** Convert `src/findajob/fetchers.py` to a package (`fetchers/__init__.py`). Add `fetchers/adapters/` subpackage with a `JobSourceAdapter` Protocol, `JobsApi14Adapter` (refactor of existing fetcher), `JSearchAdapter` (new), and an explicit registry. `triage.py` iterates `iter_configured_adapters()` instead of calling hardcoded fetcher functions for RapidAPI feeds. Onboarding interview prompt gains a Section 3h picker step that reads `config/rapidapi_feeds.yaml` and emits `<<<FILE: rapidapi_feed.txt>>>`. Injector writes the choice to `config/active_sources.txt`. New web route `/onboarding/feed-config/{session_id}` collects per-feed credentials when the existing key fails the live test. Idempotent entrypoint migration `RAPIDAPI_KEY` → `JOBS_API14_KEY` keeps existing stacks working.

**Tech Stack:** Python 3.13, FastAPI, pytest, ruff, mypy, Jinja2 templates, HTMX. PyYAML for the curation file. Test pattern: `uv run pytest tests/...`.

**Spec:** [`docs/superpowers/specs/2026-05-02-408-design.md`](../specs/2026-05-02-408-design.md)

**Spawned follow-ons:** see issue body for follow-on tracking.

---

## Pre-flight: branch setup

Per memory rule "Git — branch off origin/main" (local main drifts from origin/main via squash-merge).

```bash
cd /home/brockamer/Code/findajob
git fetch origin main
git checkout -b feat/408-rapidapi-feed-picker origin/main
git status
```

Expected: clean working tree on `feat/408-rapidapi-feed-picker`.

---

## File Structure

**Created:**
- `src/findajob/fetchers/__init__.py` — re-exports existing functions (replaces `fetchers.py`)
- `src/findajob/fetchers/adapters/__init__.py` — package init, re-exports registry entry point
- `src/findajob/fetchers/adapters/base.py` — `JobSourceAdapter` Protocol + `LiveTestResult` dataclass + `QueryResult` dataclass
- `src/findajob/fetchers/adapters/jobs_api14.py` — `JobsApi14Adapter`
- `src/findajob/fetchers/adapters/jsearch.py` — `JSearchAdapter`
- `src/findajob/fetchers/adapters/registry.py` — `REGISTERED_ADAPTERS`, `iter_configured_adapters()`, `_read_active_sources()`
- `src/findajob/fetchers/adapters/curation.py` — `config/rapidapi_feeds.yaml` loader + `recommend_for_class()`
- `src/findajob/onboarding/env_migrate.py` — `migrate_rapidapi_key_env()` helper
- `src/findajob/web/routes/onboarding_feed_config.py` — GET/POST `/onboarding/feed-config/{session_id}` + finish endpoint
- `src/findajob/web/templates/onboarding_feed_config/index.html` — form
- `src/findajob/web/templates/onboarding_feed_config/_live_test_result.html` — result partial (switches on bucket)
- `config/rapidapi_feeds.yaml.example` — operator-curated table (gitignored real)
- `config/active_sources.txt.example` — single-line example
- `tests/test_adapter_base.py`
- `tests/test_jobs_api14_adapter.py`
- `tests/test_jsearch_adapter.py`
- `tests/test_adapter_registry.py`
- `tests/test_active_sources_parser.py`
- `tests/test_rapidapi_feeds_yaml.py`
- `tests/test_env_migrate.py`
- `tests/test_onboarding_feed_config_route.py`
- `tests/test_triage_with_multiple_adapters.py`
- `tests/test_onboarding_picker_emission.py` — parser + injector recognition of `rapidapi_feed.txt`

**Modified:**
- `src/findajob/onboarding/parser.py` — add `rapidapi_feed.txt` to `OPTIONAL_FILENAMES`
- `src/findajob/onboarding/injector.py` — write `config/active_sources.txt`; sentinel-or-redirect decision
- `src/findajob/web/app.py` — register new route; call `migrate_rapidapi_key_env()` at startup
- `scripts/triage.py:24-30, 220-237` — replace hardcoded `fetch_jobsapi_jobs()` call with `iter_configured_adapters()` loop
- `config/roles/onboarding_interviewer.md` — Section 3h added; Section 3g extended; Phase 5 emission list updated
- `data/.env.example` — `RAPIDAPI_KEY` → `JOBS_API14_KEY`; add commented `JSEARCH_API_KEY`
- `.gitignore` — add `config/rapidapi_feeds.yaml`, `config/active_sources.txt`
- `CLAUDE.md` — Pipeline Context Table, Container Context, Critical Architecture Rules, Key File Locations
- `docs/setup/configure.md` — new section
- `docs/setup/api-keys.md` — RapidAPI section rewrite
- `docs/setup/install-docker.md` — `data/.env` template + migration note
- `docs/usage.md` — picker step mention
- `CHANGELOG.md` — `[0.14.0]` Added/Changed + `### Migration required` bullet

**Deleted:**
- `src/findajob/fetchers.py` — content moves into `fetchers/__init__.py` (or `fetchers/_legacy.py`)

---

## Task 1: Convert `fetchers.py` to a package — no behavior change

Foundation task. Pure refactor: existing imports keep working; no logic changes. Must land first because `fetchers/adapters/` is a subpackage of the new `fetchers/` package.

**Files:**
- Create: `src/findajob/fetchers/__init__.py`
- Delete: `src/findajob/fetchers.py`

### Steps

- [ ] **Step 1: Run the existing fetchers test suite as the baseline**

```bash
cd /home/brockamer/Code/findajob
uv run pytest tests/test_fetchers_greenhouse_slug.py tests/test_fetchers_linkedin_rate_limit.py tests/test_fetchers_date_posted.py tests/test_gmail_imap.py tests/test_gmail_imap_parsing.py -v
```

Expected: all pass on main. Record the count. After Task 1, the same set must pass — that's the regression guard for the package conversion.

- [ ] **Step 2: Create the new package layout**

```bash
mkdir -p src/findajob/fetchers
git mv src/findajob/fetchers.py src/findajob/fetchers/__init__.py
git status
```

Expected: `R  src/findajob/fetchers.py -> src/findajob/fetchers/__init__.py` shown.

- [ ] **Step 3: Re-run the test suite to confirm the rename was clean**

```bash
uv run pytest tests/test_fetchers_greenhouse_slug.py tests/test_fetchers_linkedin_rate_limit.py tests/test_fetchers_date_posted.py tests/test_gmail_imap.py tests/test_gmail_imap_parsing.py -v
```

Expected: identical pass count to Step 1. If anything changes, revert and investigate before proceeding (likely a Python import-cache issue resolved by deleting `__pycache__` directories under `src/findajob/`).

- [ ] **Step 4: Run lint + type check**

```bash
uv run ruff check src/findajob/fetchers/ tests/
uv run ruff format --check src/findajob/fetchers/
uv run mypy src/findajob/fetchers/
```

Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add src/findajob/fetchers/__init__.py
git commit -m "refactor(fetchers): convert module to package — no behavior change

Pre-#408 foundation. Moves src/findajob/fetchers.py to
src/findajob/fetchers/__init__.py so the fetchers/adapters/
subpackage can land. All existing import paths
(from findajob.fetchers import ...) continue to work."
```

---

## Task 2: Define `JobSourceAdapter` Protocol + `LiveTestResult` + `QueryResult`

The contract every adapter implements. Pure types — no runtime behavior to test except construction and `runtime_checkable` semantics.

**Files:**
- Create: `src/findajob/fetchers/adapters/__init__.py` (empty for now; populated when registry lands)
- Create: `src/findajob/fetchers/adapters/base.py`
- Create: `tests/test_adapter_base.py`

### Steps

- [ ] **Step 1: Create the empty package init**

```bash
touch src/findajob/fetchers/adapters/__init__.py
```

- [ ] **Step 2: Write the failing test for the Protocol contract**

Create `tests/test_adapter_base.py`:

```python
"""Tests for the JobSourceAdapter Protocol and result dataclasses (#408)."""
from __future__ import annotations

import pytest

from findajob.fetchers.adapters.base import (
    JobSourceAdapter,
    LiveTestResult,
    QueryResult,
)


class _DummyAdapter:
    name = "dummy"
    display_name = "Dummy Adapter"
    source_label = "dummy"
    required_env_vars: tuple[str, ...] = ("DUMMY_KEY",)

    def is_configured(self) -> bool:
        return True

    def fetch(self, queries: list[str]) -> list[dict]:
        return []

    def live_test(self, queries: list[str]) -> LiveTestResult:
        return LiveTestResult(ok=True, bucket="success", per_query=[], auth_error=None)


def test_dummy_adapter_satisfies_protocol() -> None:
    """A class with the right shape passes runtime_checkable isinstance check."""
    adapter = _DummyAdapter()
    assert isinstance(adapter, JobSourceAdapter)


def test_query_result_dataclass() -> None:
    qr = QueryResult(query="engineer", count=5, error=None)
    assert qr.query == "engineer"
    assert qr.count == 5
    assert qr.error is None


def test_live_test_result_success_bucket() -> None:
    result = LiveTestResult(
        ok=True,
        bucket="success",
        per_query=[QueryResult(query="a", count=3, error=None)],
        auth_error=None,
    )
    assert result.ok is True
    assert result.bucket == "success"
    assert len(result.per_query) == 1


def test_live_test_result_auth_failure_bucket() -> None:
    result = LiveTestResult(
        ok=False,
        bucket="auth",
        per_query=[],
        auth_error="HTTP 401: invalid key",
    )
    assert result.ok is False
    assert result.bucket == "auth"
    assert result.auth_error is not None


def test_live_test_result_invalid_bucket_rejected() -> None:
    """Bucket must be one of the documented values."""
    valid_buckets = {"success", "mixed", "zero_rows", "auth", "rate_limit", "server", "network"}
    # If we accidentally typo, the type system catches it. This test asserts the
    # documented bucket set so anyone changing it has to update this list too.
    for bucket in valid_buckets:
        LiveTestResult(ok=True, bucket=bucket, per_query=[], auth_error=None)


def test_protocol_rejects_missing_method() -> None:
    """An object missing fetch() doesn't satisfy the Protocol."""

    class _Incomplete:
        name = "incomplete"
        display_name = "Incomplete"
        source_label = "incomplete"
        required_env_vars: tuple[str, ...] = ()

        def is_configured(self) -> bool:
            return True

        # missing fetch() and live_test()

    assert not isinstance(_Incomplete(), JobSourceAdapter)
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
uv run pytest tests/test_adapter_base.py -v
```

Expected: ImportError — `findajob.fetchers.adapters.base` doesn't exist yet.

- [ ] **Step 4: Create `src/findajob/fetchers/adapters/base.py`**

```python
"""JobSourceAdapter Protocol + result dataclasses (#408).

Every job-source adapter implements this Protocol. The framework is
source-agnostic by design — RapidAPI-flavored adapters (jobs-api14,
jsearch) ship in #408; future direct adapters (Workday CXS #248,
Gem GraphQL #249) implement the same contract.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol, runtime_checkable

LiveTestBucket = Literal[
    "success",      # all queries returned 200 + ≥1 row
    "mixed",        # some queries returned rows, some empty (no errors)
    "zero_rows",    # all queries returned 200 but 0 rows
    "auth",         # call 1 hit 401/403 — bad key or inactive subscription
    "rate_limit",   # call 1 succeeded, later call hit 429
    "server",       # 5xx response from the API
    "network",      # DNS/TCP/TLS failure or timeout
]


@dataclass(frozen=True)
class QueryResult:
    """Per-query result from a live test.

    `count` is the number of jobs returned for `query`. `error` is None
    on success, or a short human-language string on per-query failure
    (rare — usually the whole live test fails together).
    """
    query: str
    count: int
    error: str | None = None


@dataclass(frozen=True)
class LiveTestResult:
    """Structured result of `JobSourceAdapter.live_test()`.

    The form renders different cards based on `bucket`. `ok` is True
    if the connection works (success / mixed / zero_rows); False if a
    failure prevented completion (auth / rate_limit / server / network).
    """
    ok: bool
    bucket: LiveTestBucket
    per_query: list[QueryResult] = field(default_factory=list)
    auth_error: str | None = None


@runtime_checkable
class JobSourceAdapter(Protocol):
    """Source-agnostic adapter contract.

    Adapters declare their identity (name, display_name, source_label)
    and required env vars as class attributes. Three methods drive
    runtime behavior: is_configured (env var presence check), fetch
    (production call, returns raw row dicts), live_test (onboarding-time
    connection check, returns structured LiveTestResult).
    """
    name: str
    display_name: str
    source_label: str
    required_env_vars: tuple[str, ...]

    def is_configured(self) -> bool: ...
    def fetch(self, queries: list[str]) -> list[dict]: ...
    def live_test(self, queries: list[str]) -> LiveTestResult: ...
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
uv run pytest tests/test_adapter_base.py -v
```

Expected: 6 tests pass.

- [ ] **Step 6: Lint + type check**

```bash
uv run ruff check src/findajob/fetchers/adapters/ tests/test_adapter_base.py
uv run ruff format --check src/findajob/fetchers/adapters/ tests/test_adapter_base.py
uv run mypy src/findajob/fetchers/adapters/
```

Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add src/findajob/fetchers/adapters/ tests/test_adapter_base.py
git commit -m "feat(adapters): JobSourceAdapter Protocol + result dataclasses (#408)

Source-agnostic adapter contract. Reusable by future direct
adapters (Workday #248, Gem #249) — not RapidAPI-specific."
```

---

## Task 3: Implement `JobsApi14Adapter` — refactor of existing `fetch_jobsapi_jobs`

Wraps the current `fetch_jobsapi_jobs` body inside an adapter class. Reads `JOBS_API14_KEY` (NOT `RAPIDAPI_KEY` — the migration that handles existing stacks lives in Task 7). Same HTTP shape, response parsing, 429 retry, `_date_posted_for_install()` widening as before.

**Files:**
- Create: `src/findajob/fetchers/adapters/jobs_api14.py`
- Create: `tests/test_jobs_api14_adapter.py`

### Steps

- [ ] **Step 1: Skim the existing implementation**

```bash
sed -n '375,505p' src/findajob/fetchers/__init__.py
```

Read carefully — the new adapter must preserve every behavior in this block: env var check, query-file loading skipped (queries come in as a list now), header construction, retry-on-429 with `Retry-After`, `hasError` check, response parsing into the row dict shape, `log_event` calls. The adapter takes `queries: list[str]` directly instead of a `queries_path` (the caller does the file read).

- [ ] **Step 2: Write failing tests**

Create `tests/test_jobs_api14_adapter.py`:

```python
"""Tests for JobsApi14Adapter (#408 refactor of fetch_jobsapi_jobs)."""
from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from findajob.fetchers.adapters.base import LiveTestResult
from findajob.fetchers.adapters.jobs_api14 import JobsApi14Adapter


@pytest.fixture(autouse=True)
def _scrub_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("JOBS_API14_KEY", raising=False)
    monkeypatch.delenv("RAPIDAPI_KEY", raising=False)


def test_class_attributes() -> None:
    adapter = JobsApi14Adapter()
    assert adapter.name == "jobs-api14"
    assert adapter.display_name == "Jobs API (jobs-api14)"
    assert adapter.source_label == "jobsapi_linkedin"  # preserves existing DB rows
    assert adapter.required_env_vars == ("JOBS_API14_KEY",)


def test_is_configured_false_when_env_unset() -> None:
    assert JobsApi14Adapter().is_configured() is False


def test_is_configured_true_when_env_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JOBS_API14_KEY", "test-key-1234")
    assert JobsApi14Adapter().is_configured() is True


def test_is_configured_does_not_fall_back_to_rapidapi_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """No production-code fallback. Migration handles RAPIDAPI_KEY at entrypoint."""
    monkeypatch.setenv("RAPIDAPI_KEY", "old-key-1234")
    assert JobsApi14Adapter().is_configured() is False


def test_fetch_returns_empty_when_unconfigured() -> None:
    adapter = JobsApi14Adapter()
    assert adapter.fetch(["engineer"]) == []


def test_fetch_hits_correct_endpoint_with_correct_headers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JOBS_API14_KEY", "test-key")
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = {"hasError": False, "data": []}
    fake_response.raise_for_status.return_value = None

    with patch("findajob.fetchers.adapters.jobs_api14.requests.get", return_value=fake_response) as mock_get:
        JobsApi14Adapter().fetch(["data center engineer"])

    args, kwargs = mock_get.call_args
    assert args[0] == "https://jobs-api14.p.rapidapi.com/v2/linkedin/search"
    assert kwargs["headers"]["x-rapidapi-host"] == "jobs-api14.p.rapidapi.com"
    assert kwargs["headers"]["x-rapidapi-key"] == "test-key"
    assert kwargs["params"]["query"] == "data center engineer"


def test_fetch_retries_on_429(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JOBS_API14_KEY", "test-key")
    rate_limited = MagicMock(status_code=429, headers={"Retry-After": "1"})
    rate_limited.json.return_value = {"hasError": False, "data": []}
    success = MagicMock(status_code=200, headers={})
    success.json.return_value = {"hasError": False, "data": []}
    success.raise_for_status.return_value = None

    with patch("findajob.fetchers.adapters.jobs_api14.requests.get", side_effect=[rate_limited, success]) as mock_get, \
         patch("findajob.fetchers.adapters.jobs_api14.time.sleep") as mock_sleep:
        JobsApi14Adapter().fetch(["engineer"])

    assert mock_get.call_count == 2
    assert mock_sleep.called


def test_fetch_returns_parsed_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JOBS_API14_KEY", "test-key")
    fake_response = MagicMock(status_code=200, headers={})
    fake_response.json.return_value = {
        "hasError": False,
        "data": [
            {
                "id": "ext-1",
                "title": "Senior Data Center Engineer",
                "company": "Acme Corp",
                "location": "Seattle, WA",
                "linkedinUrl": "https://www.linkedin.com/jobs/view/123",
            },
        ],
    }
    fake_response.raise_for_status.return_value = None

    with patch("findajob.fetchers.adapters.jobs_api14.requests.get", return_value=fake_response):
        rows = JobsApi14Adapter().fetch(["engineer"])

    assert len(rows) == 1
    assert rows[0]["title"] == "Senior Data Center Engineer"
    assert rows[0]["company"] == "Acme Corp"
    assert "linkedin.com/jobs/view/123" in rows[0]["url"]


def test_live_test_auth_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JOBS_API14_KEY", "bad-key")
    fake_response = MagicMock(status_code=401, headers={})
    fake_response.raise_for_status.side_effect = Exception("401")

    with patch("findajob.fetchers.adapters.jobs_api14.requests.get", return_value=fake_response):
        result = JobsApi14Adapter().live_test(["engineer"])

    assert result.ok is False
    assert result.bucket == "auth"
    assert result.auth_error is not None


def test_live_test_zero_rows_everywhere(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JOBS_API14_KEY", "good-key")
    fake_response = MagicMock(status_code=200, headers={})
    fake_response.json.return_value = {"hasError": False, "data": []}
    fake_response.raise_for_status.return_value = None

    with patch("findajob.fetchers.adapters.jobs_api14.requests.get", return_value=fake_response):
        result = JobsApi14Adapter().live_test(["engineer", "manager"])

    assert result.ok is True
    assert result.bucket == "zero_rows"
    assert all(qr.count == 0 for qr in result.per_query)


def test_live_test_mixed_results(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JOBS_API14_KEY", "good-key")
    one_row = MagicMock(status_code=200, headers={})
    one_row.json.return_value = {"hasError": False, "data": [{"title": "X", "company": "Y"}]}
    one_row.raise_for_status.return_value = None
    no_rows = MagicMock(status_code=200, headers={})
    no_rows.json.return_value = {"hasError": False, "data": []}
    no_rows.raise_for_status.return_value = None

    with patch(
        "findajob.fetchers.adapters.jobs_api14.requests.get",
        side_effect=[one_row, no_rows],
    ):
        result = JobsApi14Adapter().live_test(["engineer", "manager"])

    assert result.ok is True
    assert result.bucket == "mixed"
    assert result.per_query[0].count == 1
    assert result.per_query[1].count == 0


def test_live_test_rate_limit_mid_test(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JOBS_API14_KEY", "good-key")
    success = MagicMock(status_code=200, headers={})
    success.json.return_value = {"hasError": False, "data": [{"title": "X", "company": "Y"}]}
    success.raise_for_status.return_value = None
    rate_limit = MagicMock(status_code=429, headers={"Retry-After": "60"})
    rate_limit.raise_for_status.side_effect = Exception("429")

    with patch(
        "findajob.fetchers.adapters.jobs_api14.requests.get",
        side_effect=[success, rate_limit],
    ):
        result = JobsApi14Adapter().live_test(["engineer", "manager"])

    assert result.ok is True
    assert result.bucket == "rate_limit"
    assert result.per_query[0].count == 1
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
uv run pytest tests/test_jobs_api14_adapter.py -v
```

Expected: ImportError on `findajob.fetchers.adapters.jobs_api14`.

- [ ] **Step 4: Create `src/findajob/fetchers/adapters/jobs_api14.py`**

```python
"""JobsApi14Adapter — refactor of fetch_jobsapi_jobs (#408)."""
from __future__ import annotations

import os
import time
from typing import ClassVar

import requests

from findajob.utils import log_event

from .base import JobSourceAdapter, LiveTestResult, QueryResult

# Bind module-level imports so tests can patch them via the public path
__all__ = ("JobsApi14Adapter",)


class JobsApi14Adapter:
    """LinkedIn ingestion via jobs-api14 (RapidAPI)."""

    name: ClassVar[str] = "jobs-api14"
    display_name: ClassVar[str] = "Jobs API (jobs-api14)"
    source_label: ClassVar[str] = "jobsapi_linkedin"
    required_env_vars: ClassVar[tuple[str, ...]] = ("JOBS_API14_KEY",)

    _ENDPOINT: ClassVar[str] = "https://jobs-api14.p.rapidapi.com/v2/linkedin/search"
    _HOST: ClassVar[str] = "jobs-api14.p.rapidapi.com"

    def is_configured(self) -> bool:
        return bool(os.environ.get("JOBS_API14_KEY", ""))

    def fetch(self, queries: list[str]) -> list[dict]:
        api_key = os.environ.get("JOBS_API14_KEY", "")
        if not api_key:
            log_event("jobs_api14_error", error="JOBS_API14_KEY not set in .env")
            return []

        date_posted = _date_posted_for_install()
        log_event("jobs_api14_date_posted", value=date_posted)

        headers = self._headers(api_key)
        rows: list[dict] = []
        for query in queries:
            params = self._params(query, date_posted)
            data = self._call_with_retry(headers, params, query)
            if data is None:
                continue
            rows.extend(self._parse_rows(data, query))
        return rows

    def live_test(self, queries: list[str]) -> LiveTestResult:
        api_key = os.environ.get("JOBS_API14_KEY", "")
        if not api_key:
            return LiveTestResult(
                ok=False,
                bucket="auth",
                per_query=[],
                auth_error="No API key configured.",
            )

        date_posted = _date_posted_for_install()
        headers = self._headers(api_key)
        per_query: list[QueryResult] = []
        rate_limited = False
        for i, query in enumerate(queries):
            params = self._params(query, date_posted)
            try:
                response = requests.get(self._ENDPOINT, headers=headers, params=params, timeout=30)
            except requests.RequestException as e:
                if i == 0:
                    return LiveTestResult(ok=False, bucket="network", per_query=[], auth_error=str(e))
                rate_limited = True
                break

            if response.status_code in (401, 403):
                return LiveTestResult(
                    ok=False,
                    bucket="auth",
                    per_query=[],
                    auth_error=f"HTTP {response.status_code}: invalid key or subscription not active.",
                )
            if response.status_code == 429:
                if i == 0:
                    return LiveTestResult(
                        ok=False,
                        bucket="rate_limit",
                        per_query=[],
                        auth_error="Rate limited on first call.",
                    )
                rate_limited = True
                break
            if 500 <= response.status_code < 600:
                return LiveTestResult(
                    ok=False,
                    bucket="server",
                    per_query=[],
                    auth_error=f"HTTP {response.status_code}: server error.",
                )

            try:
                data = response.json()
            except ValueError:
                return LiveTestResult(
                    ok=False,
                    bucket="server",
                    per_query=[],
                    auth_error="Invalid JSON response.",
                )

            if data.get("hasError"):
                return LiveTestResult(
                    ok=False,
                    bucket="auth",
                    per_query=[],
                    auth_error=f"API reported error: {data.get('errors')}.",
                )

            per_query.append(QueryResult(query=query, count=len(data.get("data", []))))

        if rate_limited:
            return LiveTestResult(ok=True, bucket="rate_limit", per_query=per_query, auth_error=None)

        total = sum(qr.count for qr in per_query)
        if total == 0:
            return LiveTestResult(ok=True, bucket="zero_rows", per_query=per_query, auth_error=None)
        if any(qr.count == 0 for qr in per_query):
            return LiveTestResult(ok=True, bucket="mixed", per_query=per_query, auth_error=None)
        return LiveTestResult(ok=True, bucket="success", per_query=per_query, auth_error=None)

    # ------------------------- internal helpers -------------------------

    def _headers(self, api_key: str) -> dict[str, str]:
        return {
            "x-rapidapi-host": self._HOST,
            "x-rapidapi-key": api_key,
            "Content-Type": "application/json",
        }

    def _params(self, query: str, date_posted: str) -> dict[str, str]:
        return {
            "query": query,
            "location": "United States",
            "datePosted": date_posted,
            "employmentTypes": "fulltime",
            "experienceLevels": "midSenior;director",
        }

    def _call_with_retry(
        self,
        headers: dict[str, str],
        params: dict[str, str],
        query: str,
    ) -> dict | None:
        try:
            response = requests.get(self._ENDPOINT, headers=headers, params=params, timeout=30)
            if response.status_code == 429:
                wait = min(int(response.headers.get("Retry-After", "10")), 60)
                log_event("rapidapi_rate_limit", source=self.name, query=query, wait=wait)
                time.sleep(wait)
                response = requests.get(self._ENDPOINT, headers=headers, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            if data.get("hasError"):
                log_event("jobs_api14_error", source=self.name, query=query, errors=data.get("errors"))
                return None
            return data
        except requests.RequestException as e:
            log_event("jobs_api14_error", source=self.name, query=query, error=str(e))
            return None

    def _parse_rows(self, data: dict, query: str) -> list[dict]:
        rows: list[dict] = []
        for job in data.get("data", []):
            rows.append({
                "title": job.get("title", ""),
                "company": job.get("company", ""),
                "location": job.get("location", ""),
                "url": job.get("linkedinUrl", ""),
                "api_id": job.get("id", ""),
                "source": self.source_label,
                "query": query,
            })
        return rows


def _date_posted_for_install() -> str:
    """LinkedIn datePosted widened from `day` to `month` for first 30 days post-onboarding."""
    from findajob.paths import BASE

    _NEW_INSTALL_DAYS = 30
    try:
        age_days = (time.time() - os.path.getmtime(f"{BASE}/data/.onboarding-complete")) / 86400
    except OSError:
        return "day"
    return "month" if age_days < _NEW_INSTALL_DAYS else "day"
```

- [ ] **Step 5: Run the new tests**

```bash
uv run pytest tests/test_jobs_api14_adapter.py -v
```

Expected: all 12 tests pass.

- [ ] **Step 6: Run the existing fetcher tests to make sure the adapter doesn't break them (the old function-style code is still in `fetchers/__init__.py` for now)**

```bash
uv run pytest tests/test_fetchers_linkedin_rate_limit.py tests/test_fetchers_date_posted.py -v
```

Expected: same pass count as before.

- [ ] **Step 7: Lint + type check**

```bash
uv run ruff check src/findajob/fetchers/adapters/jobs_api14.py tests/test_jobs_api14_adapter.py
uv run ruff format --check src/findajob/fetchers/adapters/jobs_api14.py tests/test_jobs_api14_adapter.py
uv run mypy src/findajob/fetchers/adapters/jobs_api14.py
```

- [ ] **Step 8: Commit**

```bash
git add src/findajob/fetchers/adapters/jobs_api14.py tests/test_jobs_api14_adapter.py
git commit -m "feat(adapters): JobsApi14Adapter — refactor of fetch_jobsapi_jobs (#408)

Reads JOBS_API14_KEY (no fallback — migration handles legacy
RAPIDAPI_KEY at entrypoint, see Task 7). Same HTTP shape, response
parsing, 429 retry, _date_posted_for_install widening as before.
source_label='jobsapi_linkedin' preserves historical DB rows."
```

---

## Task 4: Implement `JSearchAdapter`

JSearch's API: `GET https://jsearch.p.rapidapi.com/search?query={q}&page=1&num_pages=1&country=us` (verify against the live RapidAPI docs during implementation; this is the canonical shape per JSearch's public listing). Response: `{ "data": [ { ... } ] }` with one row per job. Closes #310 — adds `"jsearch"` to the board filter dropdown enum.

**Files:**
- Create: `src/findajob/fetchers/adapters/jsearch.py`
- Create: `tests/test_jsearch_adapter.py`
- Modify: `src/findajob/web/filters/registry.py` (add `jsearch` to source-filter enum if there's an explicit list)

### Steps

- [ ] **Step 1: Inspect the source-filter registry to know whether to update it**

```bash
grep -n "source\|jobsapi_linkedin\|gmail_linkedin" src/findajob/web/filters/registry.py | head -20
```

Note any explicit source-value enum that needs `"jsearch"` added.

- [ ] **Step 2: Write the failing tests**

Create `tests/test_jsearch_adapter.py`:

```python
"""Tests for JSearchAdapter (#408 / closes #310)."""
from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from findajob.fetchers.adapters.base import LiveTestResult
from findajob.fetchers.adapters.jsearch import JSearchAdapter


@pytest.fixture(autouse=True)
def _scrub_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("JSEARCH_API_KEY", raising=False)


def test_class_attributes() -> None:
    adapter = JSearchAdapter()
    assert adapter.name == "jsearch"
    assert adapter.display_name == "JSearch"
    assert adapter.source_label == "jsearch"
    assert adapter.required_env_vars == ("JSEARCH_API_KEY",)


def test_is_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    assert JSearchAdapter().is_configured() is False
    monkeypatch.setenv("JSEARCH_API_KEY", "k")
    assert JSearchAdapter().is_configured() is True


def test_fetch_hits_correct_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JSEARCH_API_KEY", "test-key")
    fake = MagicMock(status_code=200, headers={})
    fake.json.return_value = {"data": []}
    fake.raise_for_status.return_value = None
    with patch("findajob.fetchers.adapters.jsearch.requests.get", return_value=fake) as mock_get:
        JSearchAdapter().fetch(["nurse practitioner"])
    args, kwargs = mock_get.call_args
    assert args[0] == "https://jsearch.p.rapidapi.com/search"
    assert kwargs["headers"]["x-rapidapi-host"] == "jsearch.p.rapidapi.com"
    assert kwargs["headers"]["x-rapidapi-key"] == "test-key"
    assert kwargs["params"]["query"] == "nurse practitioner"


def test_fetch_parses_jsearch_response_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    """JSearch returns {data: [{job_title, employer_name, job_city, job_state, job_apply_link, job_id}, ...]}."""
    monkeypatch.setenv("JSEARCH_API_KEY", "test-key")
    fake = MagicMock(status_code=200, headers={})
    fake.json.return_value = {
        "data": [
            {
                "job_id": "ext-1",
                "job_title": "Registered Nurse",
                "employer_name": "Acme Hospital",
                "job_city": "Seattle",
                "job_state": "WA",
                "job_apply_link": "https://acme.com/apply/123",
            },
        ],
    }
    fake.raise_for_status.return_value = None
    with patch("findajob.fetchers.adapters.jsearch.requests.get", return_value=fake):
        rows = JSearchAdapter().fetch(["nurse"])
    assert len(rows) == 1
    assert rows[0]["title"] == "Registered Nurse"
    assert rows[0]["company"] == "Acme Hospital"
    assert "Seattle" in rows[0]["location"]
    assert rows[0]["source"] == "jsearch"


def test_live_test_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JSEARCH_API_KEY", "good-key")
    fake = MagicMock(status_code=200, headers={})
    fake.json.return_value = {"data": [{"job_title": "RN", "employer_name": "X"}]}
    fake.raise_for_status.return_value = None
    with patch("findajob.fetchers.adapters.jsearch.requests.get", return_value=fake):
        result = JSearchAdapter().live_test(["nurse"])
    assert result.ok is True
    assert result.bucket == "success"


def test_live_test_auth_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JSEARCH_API_KEY", "bad-key")
    fake = MagicMock(status_code=403, headers={})
    fake.raise_for_status.side_effect = Exception("403")
    with patch("findajob.fetchers.adapters.jsearch.requests.get", return_value=fake):
        result = JSearchAdapter().live_test(["nurse"])
    assert result.ok is False
    assert result.bucket == "auth"


def test_live_test_zero_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JSEARCH_API_KEY", "good-key")
    fake = MagicMock(status_code=200, headers={})
    fake.json.return_value = {"data": []}
    fake.raise_for_status.return_value = None
    with patch("findajob.fetchers.adapters.jsearch.requests.get", return_value=fake):
        result = JSearchAdapter().live_test(["nurse", "doctor"])
    assert result.ok is True
    assert result.bucket == "zero_rows"
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
uv run pytest tests/test_jsearch_adapter.py -v
```

Expected: ImportError.

- [ ] **Step 4: Create `src/findajob/fetchers/adapters/jsearch.py`**

The structure is parallel to `jobs_api14.py` but with JSearch's request/response shape. Key differences: endpoint is `/search` not `/v2/linkedin/search`; response uses `job_title` not `title`, `employer_name` not `company`, etc.

```python
"""JSearchAdapter — multi-board aggregator via JSearch (RapidAPI). Bundles #310 (#408)."""
from __future__ import annotations

import os
from typing import ClassVar

import requests

from findajob.utils import log_event

from .base import JobSourceAdapter, LiveTestResult, QueryResult

__all__ = ("JSearchAdapter",)


class JSearchAdapter:
    """Multi-board aggregator (LinkedIn + Indeed + Glassdoor + ZipRecruiter)."""

    name: ClassVar[str] = "jsearch"
    display_name: ClassVar[str] = "JSearch"
    source_label: ClassVar[str] = "jsearch"
    required_env_vars: ClassVar[tuple[str, ...]] = ("JSEARCH_API_KEY",)

    _ENDPOINT: ClassVar[str] = "https://jsearch.p.rapidapi.com/search"
    _HOST: ClassVar[str] = "jsearch.p.rapidapi.com"

    def is_configured(self) -> bool:
        return bool(os.environ.get("JSEARCH_API_KEY", ""))

    def fetch(self, queries: list[str]) -> list[dict]:
        api_key = os.environ.get("JSEARCH_API_KEY", "")
        if not api_key:
            log_event("jsearch_error", error="JSEARCH_API_KEY not set in .env")
            return []
        headers = self._headers(api_key)
        rows: list[dict] = []
        for query in queries:
            try:
                response = requests.get(self._ENDPOINT, headers=headers, params=self._params(query), timeout=30)
                response.raise_for_status()
                data = response.json()
            except (requests.RequestException, ValueError) as e:
                log_event("jsearch_error", query=query, error=str(e))
                continue
            rows.extend(self._parse_rows(data, query))
        return rows

    def live_test(self, queries: list[str]) -> LiveTestResult:
        api_key = os.environ.get("JSEARCH_API_KEY", "")
        if not api_key:
            return LiveTestResult(
                ok=False, bucket="auth", per_query=[], auth_error="No API key configured."
            )
        headers = self._headers(api_key)
        per_query: list[QueryResult] = []
        rate_limited = False
        for i, query in enumerate(queries):
            try:
                response = requests.get(self._ENDPOINT, headers=headers, params=self._params(query), timeout=30)
            except requests.RequestException as e:
                if i == 0:
                    return LiveTestResult(ok=False, bucket="network", per_query=[], auth_error=str(e))
                rate_limited = True
                break

            if response.status_code in (401, 403):
                return LiveTestResult(
                    ok=False, bucket="auth", per_query=[],
                    auth_error=f"HTTP {response.status_code}: invalid key or subscription not active.",
                )
            if response.status_code == 429:
                if i == 0:
                    return LiveTestResult(
                        ok=False, bucket="rate_limit", per_query=[],
                        auth_error="Rate limited on first call.",
                    )
                rate_limited = True
                break
            if 500 <= response.status_code < 600:
                return LiveTestResult(
                    ok=False, bucket="server", per_query=[],
                    auth_error=f"HTTP {response.status_code}: server error.",
                )
            try:
                data = response.json()
            except ValueError:
                return LiveTestResult(
                    ok=False, bucket="server", per_query=[], auth_error="Invalid JSON response.",
                )
            per_query.append(QueryResult(query=query, count=len(data.get("data", []))))

        if rate_limited:
            return LiveTestResult(ok=True, bucket="rate_limit", per_query=per_query, auth_error=None)
        total = sum(qr.count for qr in per_query)
        if total == 0:
            return LiveTestResult(ok=True, bucket="zero_rows", per_query=per_query, auth_error=None)
        if any(qr.count == 0 for qr in per_query):
            return LiveTestResult(ok=True, bucket="mixed", per_query=per_query, auth_error=None)
        return LiveTestResult(ok=True, bucket="success", per_query=per_query, auth_error=None)

    def _headers(self, api_key: str) -> dict[str, str]:
        return {
            "x-rapidapi-host": self._HOST,
            "x-rapidapi-key": api_key,
        }

    def _params(self, query: str) -> dict[str, str]:
        return {
            "query": query,
            "page": "1",
            "num_pages": "1",
            "country": "us",
        }

    def _parse_rows(self, data: dict, query: str) -> list[dict]:
        rows: list[dict] = []
        for job in data.get("data", []) or []:
            location_parts = [job.get("job_city", ""), job.get("job_state", "")]
            location = ", ".join([p for p in location_parts if p])
            rows.append({
                "title": job.get("job_title", ""),
                "company": job.get("employer_name", ""),
                "location": location,
                "url": job.get("job_apply_link", ""),
                "api_id": job.get("job_id", ""),
                "source": self.source_label,
                "query": query,
            })
        return rows
```

- [ ] **Step 5: Run tests to verify pass**

```bash
uv run pytest tests/test_jsearch_adapter.py -v
```

Expected: all 7 tests pass.

- [ ] **Step 6: If `web/filters/registry.py` has an explicit source-value enum, add `"jsearch"` to it**

If Step 1's grep showed an explicit list, edit it. Add a one-line test in `tests/test_filters_registry.py` confirming `"jsearch"` is filterable.

- [ ] **Step 7: Lint + type check**

```bash
uv run ruff check src/findajob/fetchers/adapters/jsearch.py tests/test_jsearch_adapter.py
uv run ruff format --check src/findajob/fetchers/adapters/jsearch.py tests/test_jsearch_adapter.py
uv run mypy src/findajob/fetchers/adapters/jsearch.py
```

- [ ] **Step 8: Commit**

```bash
git add src/findajob/fetchers/adapters/jsearch.py tests/test_jsearch_adapter.py src/findajob/web/filters/registry.py tests/test_filters_registry.py 2>/dev/null
git commit -m "feat(adapters): JSearchAdapter — multi-board aggregator (#408, closes #310)

Second adapter validating the JobSourceAdapter framework. Same
contract as JobsApi14Adapter; JSearch-specific endpoint shape
and response parsing. Adds 'jsearch' to the source filter
dropdown enum."
```

---

## Task 5: Adapter registry + `iter_configured_adapters` + `_read_active_sources`

The runtime entry point used by `triage.py`. Reads `config/active_sources.txt`, filters `REGISTERED_ADAPTERS`, yields configured instances.

**Files:**
- Create: `src/findajob/fetchers/adapters/registry.py`
- Modify: `src/findajob/fetchers/adapters/__init__.py` (re-export `iter_configured_adapters`)
- Create: `tests/test_adapter_registry.py`
- Create: `tests/test_active_sources_parser.py`

### Steps

- [ ] **Step 1: Write failing tests for `_read_active_sources`**

Create `tests/test_active_sources_parser.py`:

```python
"""Tests for config/active_sources.txt parsing (#408)."""
from __future__ import annotations

from pathlib import Path

import pytest

from findajob.fetchers.adapters.registry import _read_active_sources


def test_default_when_missing(tmp_path: Path) -> None:
    """Missing file → backwards-compat default ['jobs-api14']."""
    assert _read_active_sources(tmp_path / "missing.txt") == ["jobs-api14"]


def test_single_entry(tmp_path: Path) -> None:
    f = tmp_path / "active.txt"
    f.write_text("jsearch\n")
    assert _read_active_sources(f) == ["jsearch"]


def test_multiple_entries(tmp_path: Path) -> None:
    f = tmp_path / "active.txt"
    f.write_text("jobs-api14\njsearch\n")
    assert _read_active_sources(f) == ["jobs-api14", "jsearch"]


def test_comments_stripped(tmp_path: Path) -> None:
    f = tmp_path / "active.txt"
    f.write_text("# comment line\njobs-api14\n# another\njsearch\n")
    assert _read_active_sources(f) == ["jobs-api14", "jsearch"]


def test_blank_lines_stripped(tmp_path: Path) -> None:
    f = tmp_path / "active.txt"
    f.write_text("\njobs-api14\n\n\njsearch\n")
    assert _read_active_sources(f) == ["jobs-api14", "jsearch"]


def test_whitespace_trimmed(tmp_path: Path) -> None:
    f = tmp_path / "active.txt"
    f.write_text("  jobs-api14  \n\tjsearch\n")
    assert _read_active_sources(f) == ["jobs-api14", "jsearch"]


def test_empty_file_falls_back_to_default(tmp_path: Path) -> None:
    """Empty file (only comments / blank) is treated like missing — default applies."""
    f = tmp_path / "active.txt"
    f.write_text("# nothing\n\n# nothing\n")
    assert _read_active_sources(f) == ["jobs-api14"]
```

- [ ] **Step 2: Write failing tests for the registry**

Create `tests/test_adapter_registry.py`:

```python
"""Tests for the adapter registry (#408)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from findajob.fetchers.adapters import iter_configured_adapters
from findajob.fetchers.adapters.registry import REGISTERED_ADAPTERS


def test_registry_contains_both_adapters() -> None:
    names = {cls.name for cls in REGISTERED_ADAPTERS}
    assert "jobs-api14" in names
    assert "jsearch" in names


def test_iter_configured_adapters_filters_by_active_list(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JOBS_API14_KEY", "k")
    monkeypatch.setenv("JSEARCH_API_KEY", "k")
    active = tmp_path / "active.txt"
    active.write_text("jobs-api14\n")
    with patch("findajob.fetchers.adapters.registry._active_sources_path", return_value=active):
        names = [a.name for a in iter_configured_adapters()]
    assert names == ["jobs-api14"]


def test_iter_configured_adapters_skips_unconfigured(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Adapter listed in active_sources.txt but missing env var → skipped, logged."""
    monkeypatch.delenv("JOBS_API14_KEY", raising=False)
    monkeypatch.setenv("JSEARCH_API_KEY", "k")
    active = tmp_path / "active.txt"
    active.write_text("jobs-api14\njsearch\n")
    with patch("findajob.fetchers.adapters.registry._active_sources_path", return_value=active):
        names = [a.name for a in iter_configured_adapters()]
    assert names == ["jsearch"]


def test_iter_configured_adapters_skips_unknown(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Adapter name in active_sources.txt that isn't registered is silently skipped."""
    monkeypatch.setenv("JOBS_API14_KEY", "k")
    active = tmp_path / "active.txt"
    active.write_text("jobs-api14\nworkday\n")  # workday not registered in this PR
    with patch("findajob.fetchers.adapters.registry._active_sources_path", return_value=active):
        names = [a.name for a in iter_configured_adapters()]
    assert names == ["jobs-api14"]


def test_iter_configured_adapters_default_when_file_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JOBS_API14_KEY", "k")
    nonexistent = tmp_path / "missing.txt"
    with patch("findajob.fetchers.adapters.registry._active_sources_path", return_value=nonexistent):
        names = [a.name for a in iter_configured_adapters()]
    assert names == ["jobs-api14"]
```

- [ ] **Step 3: Run tests — expect ImportError**

```bash
uv run pytest tests/test_active_sources_parser.py tests/test_adapter_registry.py -v
```

- [ ] **Step 4: Create `src/findajob/fetchers/adapters/registry.py`**

```python
"""Adapter registry + active-source resolution (#408)."""
from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from findajob.paths import BASE
from findajob.utils import log_event

from .base import JobSourceAdapter
from .jobs_api14 import JobsApi14Adapter
from .jsearch import JSearchAdapter

REGISTERED_ADAPTERS: list[type[JobSourceAdapter]] = [
    JobsApi14Adapter,
    JSearchAdapter,
]

_DEFAULT_ACTIVE_SOURCES: list[str] = ["jobs-api14"]


def _active_sources_path() -> Path:
    return Path(BASE) / "config" / "active_sources.txt"


def _read_active_sources(path: Path | None = None) -> list[str]:
    """Return the list of adapter names active for this stack.

    Backwards-compat: if the file is missing or empty, returns ['jobs-api14'].
    """
    target = path or _active_sources_path()
    if not target.exists():
        return list(_DEFAULT_ACTIVE_SOURCES)
    names: list[str] = []
    for raw in target.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        names.append(line)
    return names if names else list(_DEFAULT_ACTIVE_SOURCES)


def iter_configured_adapters() -> Iterator[JobSourceAdapter]:
    """Yield adapter instances active for this stack and properly configured."""
    active_names = _read_active_sources()
    for cls in REGISTERED_ADAPTERS:
        if cls.name not in active_names:
            continue
        instance = cls()
        if not instance.is_configured():
            log_event("adapter_not_configured", adapter=cls.name)
            continue
        yield instance
```

- [ ] **Step 5: Update `src/findajob/fetchers/adapters/__init__.py`**

```python
"""findajob.fetchers.adapters — pluggable JobSourceAdapter framework (#408)."""
from .base import JobSourceAdapter, LiveTestResult, QueryResult
from .registry import REGISTERED_ADAPTERS, iter_configured_adapters

__all__ = (
    "JobSourceAdapter",
    "LiveTestResult",
    "QueryResult",
    "REGISTERED_ADAPTERS",
    "iter_configured_adapters",
)
```

- [ ] **Step 6: Run all tests for the framework so far**

```bash
uv run pytest tests/test_adapter_base.py tests/test_jobs_api14_adapter.py tests/test_jsearch_adapter.py tests/test_adapter_registry.py tests/test_active_sources_parser.py -v
```

Expected: all pass.

- [ ] **Step 7: Lint + type check**

```bash
uv run ruff check src/findajob/fetchers/adapters/ tests/test_adapter_registry.py tests/test_active_sources_parser.py
uv run ruff format --check src/findajob/fetchers/adapters/ tests/test_adapter_registry.py tests/test_active_sources_parser.py
uv run mypy src/findajob/fetchers/adapters/
```

- [ ] **Step 8: Commit**

```bash
git add src/findajob/fetchers/adapters/registry.py src/findajob/fetchers/adapters/__init__.py tests/test_adapter_registry.py tests/test_active_sources_parser.py
git commit -m "feat(adapters): registry + iter_configured_adapters + active-sources parser (#408)

Reads config/active_sources.txt; filters REGISTERED_ADAPTERS;
skips unconfigured adapters with log_event. Backwards-compat
default ['jobs-api14'] when file missing or empty."
```

---

## Task 6: `migrate_rapidapi_key_env()` — idempotent entrypoint migration

Runs at app startup. Copies `RAPIDAPI_KEY` → `JOBS_API14_KEY` in `data/.env`. Removes the old line. Idempotent — safe to run on every boot.

**Files:**
- Create: `src/findajob/onboarding/env_migrate.py`
- Modify: `src/findajob/web/app.py` (call at startup)
- Create: `tests/test_env_migrate.py`

### Steps

- [ ] **Step 1: Write failing tests**

Create `tests/test_env_migrate.py`:

```python
"""Tests for migrate_rapidapi_key_env (#408)."""
from __future__ import annotations

from pathlib import Path

from findajob.onboarding.env_migrate import migrate_rapidapi_key_env


def test_no_op_when_jobs_api14_key_already_present(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("JOBS_API14_KEY=new-value\nOTHER=x\n")
    migrate_rapidapi_key_env(env)
    assert env.read_text() == "JOBS_API14_KEY=new-value\nOTHER=x\n"


def test_no_op_when_neither_key_set(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("OTHER=x\n")
    migrate_rapidapi_key_env(env)
    assert env.read_text() == "OTHER=x\n"


def test_renames_rapidapi_key_to_jobs_api14_key(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("RAPIDAPI_KEY=secret-value\nOTHER=x\n")
    migrate_rapidapi_key_env(env)
    out = env.read_text()
    assert "RAPIDAPI_KEY=" not in out
    assert "JOBS_API14_KEY=secret-value" in out
    assert "OTHER=x" in out


def test_idempotent(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("RAPIDAPI_KEY=secret-value\n")
    migrate_rapidapi_key_env(env)
    after_first = env.read_text()
    migrate_rapidapi_key_env(env)
    after_second = env.read_text()
    assert after_first == after_second


def test_both_present_keeps_jobs_api14_value_drops_old(tmp_path: Path) -> None:
    """If both are set, the new var wins; the old var is removed."""
    env = tmp_path / ".env"
    env.write_text("RAPIDAPI_KEY=old\nJOBS_API14_KEY=new\n")
    migrate_rapidapi_key_env(env)
    out = env.read_text()
    assert "RAPIDAPI_KEY=" not in out
    assert "JOBS_API14_KEY=new" in out


def test_missing_file_no_op(tmp_path: Path) -> None:
    """Migration does not create the .env file if it doesn't exist."""
    env = tmp_path / "missing.env"
    migrate_rapidapi_key_env(env)
    assert not env.exists()


def test_preserves_quotes_and_comments(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    original = '# Comment\nRAPIDAPI_KEY="quoted-value"\n# Another\nOTHER=x\n'
    env.write_text(original)
    migrate_rapidapi_key_env(env)
    out = env.read_text()
    assert "# Comment" in out
    assert "# Another" in out
    assert 'JOBS_API14_KEY="quoted-value"' in out
    assert "RAPIDAPI_KEY=" not in out
```

- [ ] **Step 2: Run — expect ImportError**

```bash
uv run pytest tests/test_env_migrate.py -v
```

- [ ] **Step 3: Create `src/findajob/onboarding/env_migrate.py`**

```python
"""Idempotent migration of legacy env-var names in data/.env (#408).

Runs at every app startup. Safe to call multiple times — it only
rewrites the file when there's a stale name to remove.
"""
from __future__ import annotations

from pathlib import Path

from findajob.utils import log_event


def migrate_rapidapi_key_env(env_path: Path) -> None:
    """Rename RAPIDAPI_KEY → JOBS_API14_KEY in data/.env.

    No-op if:
    - The file doesn't exist.
    - JOBS_API14_KEY is already set (we don't overwrite a tester's later edit).
    - RAPIDAPI_KEY isn't present.

    If both are set, JOBS_API14_KEY wins and RAPIDAPI_KEY is removed.
    """
    if not env_path.exists():
        return

    lines = env_path.read_text().splitlines(keepends=True)
    has_old = any(_is_assignment_for(line, "RAPIDAPI_KEY") for line in lines)
    has_new = any(_is_assignment_for(line, "JOBS_API14_KEY") for line in lines)

    if not has_old:
        return  # nothing to migrate

    new_lines: list[str] = []
    captured_value: str | None = None
    for line in lines:
        if _is_assignment_for(line, "RAPIDAPI_KEY"):
            if not has_new and captured_value is None:
                captured_value = _value_of(line)
            continue  # always drop the old line
        new_lines.append(line)

    if captured_value is not None:
        ending = "\n" if not new_lines or new_lines[-1].endswith("\n") else ""
        new_lines.append(f"JOBS_API14_KEY={captured_value}{ending}")

    env_path.write_text("".join(new_lines))
    log_event(
        "env_migrate_rapidapi_key",
        renamed=captured_value is not None,
        had_both=has_old and has_new,
    )


def _is_assignment_for(line: str, var: str) -> bool:
    stripped = line.lstrip()
    if stripped.startswith("#"):
        return False
    return stripped.startswith(f"{var}=")


def _value_of(line: str) -> str:
    stripped = line.lstrip().rstrip("\n").rstrip("\r")
    _, _, value = stripped.partition("=")
    return value
```

- [ ] **Step 4: Run tests — expect pass**

```bash
uv run pytest tests/test_env_migrate.py -v
```

Expected: all 7 tests pass.

- [ ] **Step 5: Wire into web app startup**

Edit `src/findajob/web/app.py`. Add to the FastAPI lifespan or startup hook:

```python
# Near the top of create_app() or in the lifespan event:
from findajob.onboarding.env_migrate import migrate_rapidapi_key_env
from findajob.paths import BASE

# In the startup section:
migrate_rapidapi_key_env(Path(BASE) / "data" / ".env")
```

(Locate the existing startup pattern and follow it. There's a structure for app-startup work — likely either FastAPI's `lifespan` context manager or a `@app.on_event("startup")` decorator.)

- [ ] **Step 6: Run web tests to verify startup still works**

```bash
uv run pytest tests/test_web_app.py tests/test_web_app_factory.py -v 2>/dev/null || uv run pytest tests/ -k "test_web_app" -v
```

Expected: all pass.

- [ ] **Step 7: Lint + type check**

```bash
uv run ruff check src/findajob/onboarding/env_migrate.py src/findajob/web/app.py tests/test_env_migrate.py
uv run ruff format --check src/findajob/onboarding/env_migrate.py src/findajob/web/app.py tests/test_env_migrate.py
uv run mypy src/findajob/onboarding/env_migrate.py
```

- [ ] **Step 8: Commit**

```bash
git add src/findajob/onboarding/env_migrate.py src/findajob/web/app.py tests/test_env_migrate.py
git commit -m "feat(onboarding): migrate_rapidapi_key_env at entrypoint (#408)

Idempotent rename of RAPIDAPI_KEY → JOBS_API14_KEY in data/.env.
Runs on every web-app startup. Existing v0.13 stacks pulling
v0.14 are migrated transparently; new installs already use
the new name."
```

---

## Task 7: Wire registry into `triage.py`

Replace the hardcoded `fetch_jobsapi_jobs(...)` call with the registry-iteration pattern.

**Files:**
- Modify: `scripts/triage.py:24-30` (imports), `scripts/triage.py:217-237` (fetch loop)
- Create: `tests/test_triage_with_multiple_adapters.py`

### Steps

- [ ] **Step 1: Read the current triage fetch block**

```bash
sed -n '215,240p' scripts/triage.py
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_triage_with_multiple_adapters.py`:

```python
"""Integration test: triage.py uses the adapter registry (#408)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest


def test_triage_iterates_configured_adapters(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Both registered adapters run when both are active and configured."""
    monkeypatch.setenv("JOBS_API14_KEY", "k")
    monkeypatch.setenv("JSEARCH_API_KEY", "k")
    active = tmp_path / "active_sources.txt"
    active.write_text("jobs-api14\njsearch\n")

    called: list[str] = []

    class _FakeAdapter:
        def __init__(self, name: str) -> None:
            self.name = name
            self.source_label = name

        def is_configured(self) -> bool:
            return True

        def fetch(self, queries: list[str]) -> list[dict]:
            called.append(self.name)
            return []

    fakes = [_FakeAdapter("jobs-api14"), _FakeAdapter("jsearch")]
    with patch("findajob.fetchers.adapters.registry._active_sources_path", return_value=active), \
         patch("findajob.fetchers.adapters.iter_configured_adapters", return_value=iter(fakes)):
        from findajob.fetchers.adapters import iter_configured_adapters
        adapters = list(iter_configured_adapters())
        for a in adapters:
            a.fetch(["q1", "q2"])

    assert called == ["jobs-api14", "jsearch"]
```

- [ ] **Step 3: Run — expect failure (likely the patch path; iterate)**

```bash
uv run pytest tests/test_triage_with_multiple_adapters.py -v
```

- [ ] **Step 4: Edit `scripts/triage.py:24-30` — imports**

Change:

```python
from findajob.fetchers import (
    fetch_ashby_jobs,
    fetch_gmail_jobs,
    fetch_greenhouse_jobs,
    fetch_jd,
    fetch_jobsapi_jobs,
    fetch_lever_jobs,
)
```

to:

```python
from findajob.fetchers import (
    fetch_ashby_jobs,
    fetch_gmail_jobs,
    fetch_greenhouse_jobs,
    fetch_jd,
    fetch_lever_jobs,
)
from findajob.fetchers.adapters import iter_configured_adapters
```

- [ ] **Step 5: Edit `scripts/triage.py:217-237` — replace `fetch_jobsapi_jobs` call with registry iteration**

Change the block:

```python
greenhouse_jobs = fetch_greenhouse_jobs(feed_urls)
ashby_jobs = fetch_ashby_jobs(feed_urls)
lever_jobs = fetch_lever_jobs(feed_urls)
api_jobs = fetch_jobsapi_jobs(f"{BASE}/config/jsearch_queries.txt")
gmail_jobs = fetch_gmail_jobs()
raw_jobs = greenhouse_jobs + ashby_jobs + lever_jobs + api_jobs + gmail_jobs
log_event(
    "jobs_fetched",
    count=len(raw_jobs),
    greenhouse=len(greenhouse_jobs),
    ashby=len(ashby_jobs),
    lever=len(lever_jobs),
    jobsapi=len(api_jobs),
    gmail=len(gmail_jobs),
    attempt=attempt,
)
```

to:

```python
greenhouse_jobs = fetch_greenhouse_jobs(feed_urls)
ashby_jobs = fetch_ashby_jobs(feed_urls)
lever_jobs = fetch_lever_jobs(feed_urls)
gmail_jobs = fetch_gmail_jobs()

# Adapter-driven RapidAPI ingestion (#408)
queries_path = Path(f"{BASE}/config/jsearch_queries.txt")
queries = (
    [line.strip() for line in queries_path.read_text().splitlines() if line.strip() and not line.startswith("#")]
    if queries_path.exists() else []
)
adapter_jobs: list[dict] = []
adapter_counts: dict[str, int] = {}
for adapter in iter_configured_adapters():
    rows = adapter.fetch(queries)
    adapter_jobs.extend(rows)
    adapter_counts[adapter.name] = len(rows)

raw_jobs = greenhouse_jobs + ashby_jobs + lever_jobs + adapter_jobs + gmail_jobs
log_event(
    "jobs_fetched",
    count=len(raw_jobs),
    greenhouse=len(greenhouse_jobs),
    ashby=len(ashby_jobs),
    lever=len(lever_jobs),
    adapters=adapter_counts,
    gmail=len(gmail_jobs),
    attempt=attempt,
)
```

Add `from pathlib import Path` to the import block at the top of `triage.py` if it's not already there.

- [ ] **Step 6: Run the integration test + the broader triage tests**

```bash
uv run pytest tests/test_triage_with_multiple_adapters.py tests/test_triage*.py -v 2>/dev/null || uv run pytest tests/ -k "test_triage" -v
```

Expected: all pass.

- [ ] **Step 7: Lint + type check**

```bash
uv run ruff check scripts/triage.py tests/test_triage_with_multiple_adapters.py
uv run ruff format --check scripts/triage.py tests/test_triage_with_multiple_adapters.py
uv run mypy scripts/triage.py
```

- [ ] **Step 8: Commit**

```bash
git add scripts/triage.py tests/test_triage_with_multiple_adapters.py
git commit -m "feat(triage): use adapter registry for RapidAPI ingestion (#408)

Replaces hardcoded fetch_jobsapi_jobs() call with iteration over
iter_configured_adapters(). Adding a new RapidAPI feed is now
one new adapter file + one registry entry, no triage edit.
Greenhouse/Ashby/Lever/Gmail fetchers stay function-style
(migrated under #410)."
```

---

## Task 8: Curation YAML loader

Reads `config/rapidapi_feeds.yaml`. Exposes `recommend_for_class(class_name) -> AdapterMetadata` and `default_adapter() -> AdapterMetadata`. Used by Section 3h prompt — but it's read by Python helpers the prompt invokes via the interview's tool channel? **No** — the interview prompt receives the YAML content directly inline (or as a system-prompt block). The Python loader exists for: (a) the feed-config form's signup-walkthrough copy, (b) injector validation that the chosen adapter exists in the curation, (c) tests.

**Files:**
- Create: `src/findajob/fetchers/adapters/curation.py`
- Create: `tests/test_rapidapi_feeds_yaml.py`

### Steps

- [ ] **Step 1: Confirm PyYAML is installed**

```bash
grep -n "pyyaml\|PyYAML" pyproject.toml
```

If missing, add to dependencies:

```bash
uv add pyyaml
```

- [ ] **Step 2: Write failing tests**

Create `tests/test_rapidapi_feeds_yaml.py`:

```python
"""Tests for the rapidapi_feeds.yaml curation loader (#408)."""
from __future__ import annotations

from pathlib import Path

import pytest

from findajob.fetchers.adapters.curation import (
    CurationLoadError,
    load_curation,
    recommend_for_class,
    default_adapter,
)

_VALID_YAML = """
default: jobs-api14

classes:
  - name: corporate-tech
    description: Corporate / tech / professional services
    recommended_adapter: jobs-api14
    rationale: LinkedIn-heavy

  - name: skilled-trades-regional
    description: Trades, regional employers
    recommended_adapter: jsearch
    rationale: Multi-board

adapters:
  - name: jobs-api14
    display_name: "Jobs API (jobs-api14)"
    rapidapi_url: https://rapidapi.com/Pat92/api/jobs-api14
    free_tier: 150 calls / month
    paid_tier: $5-25 / month
    required_env_var: JOBS_API14_KEY
    coverage:
      best_for: Corporate / tech
      worst_for: Trades / regional

  - name: jsearch
    display_name: JSearch
    rapidapi_url: https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch
    free_tier: 200 calls / month
    paid_tier: $25 / month
    required_env_var: JSEARCH_API_KEY
    coverage:
      best_for: Multi-board aggregation
      worst_for: LinkedIn-only employers
"""


def _write(tmp_path: Path, content: str) -> Path:
    f = tmp_path / "rapidapi_feeds.yaml"
    f.write_text(content)
    return f


def test_load_valid_curation(tmp_path: Path) -> None:
    f = _write(tmp_path, _VALID_YAML)
    cur = load_curation(f)
    assert cur.default_name == "jobs-api14"
    assert len(cur.classes) == 2
    assert len(cur.adapters) == 2


def test_recommend_for_class_match(tmp_path: Path) -> None:
    f = _write(tmp_path, _VALID_YAML)
    cur = load_curation(f)
    rec = recommend_for_class(cur, "skilled-trades-regional")
    assert rec.name == "jsearch"
    assert rec.display_name == "JSearch"


def test_recommend_for_class_unknown_falls_back_to_default(tmp_path: Path) -> None:
    f = _write(tmp_path, _VALID_YAML)
    cur = load_curation(f)
    rec = recommend_for_class(cur, "no-such-class")
    assert rec.name == "jobs-api14"  # the default


def test_default_adapter(tmp_path: Path) -> None:
    f = _write(tmp_path, _VALID_YAML)
    cur = load_curation(f)
    assert default_adapter(cur).name == "jobs-api14"


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(CurationLoadError):
        load_curation(tmp_path / "missing.yaml")


def test_malformed_yaml_raises(tmp_path: Path) -> None:
    f = _write(tmp_path, "this is not: valid: yaml: [")
    with pytest.raises(CurationLoadError):
        load_curation(f)


def test_missing_default_field_raises(tmp_path: Path) -> None:
    f = _write(tmp_path, "classes: []\nadapters: []\n")
    with pytest.raises(CurationLoadError):
        load_curation(f)


def test_default_pointing_at_unknown_adapter_raises(tmp_path: Path) -> None:
    f = _write(tmp_path, "default: ghost\nclasses: []\nadapters:\n  - name: jobs-api14\n    display_name: X\n")
    with pytest.raises(CurationLoadError):
        load_curation(f)


def test_class_pointing_at_unknown_adapter_raises(tmp_path: Path) -> None:
    bad = """
default: jobs-api14
classes:
  - name: corporate-tech
    description: x
    recommended_adapter: ghost
    rationale: x
adapters:
  - name: jobs-api14
    display_name: X
"""
    f = _write(tmp_path, bad)
    with pytest.raises(CurationLoadError):
        load_curation(f)
```

- [ ] **Step 3: Run — expect ImportError**

```bash
uv run pytest tests/test_rapidapi_feeds_yaml.py -v
```

- [ ] **Step 4: Create `src/findajob/fetchers/adapters/curation.py`**

```python
"""Loader for config/rapidapi_feeds.yaml (#408)."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


class CurationLoadError(Exception):
    """Raised when rapidapi_feeds.yaml is missing or malformed."""


@dataclass(frozen=True)
class AdapterMetadata:
    name: str
    display_name: str
    rapidapi_url: str = ""
    free_tier: str = ""
    paid_tier: str = ""
    required_env_var: str = ""
    best_for: str = ""
    worst_for: str = ""


@dataclass(frozen=True)
class CandidateClass:
    name: str
    description: str
    recommended_adapter: str  # adapter name
    rationale: str


@dataclass(frozen=True)
class Curation:
    default_name: str
    classes: list[CandidateClass] = field(default_factory=list)
    adapters: list[AdapterMetadata] = field(default_factory=list)

    def adapter_by_name(self, name: str) -> AdapterMetadata | None:
        return next((a for a in self.adapters if a.name == name), None)


def load_curation(path: Path) -> Curation:
    if not path.exists():
        raise CurationLoadError(f"Curation file not found: {path}")
    try:
        raw = yaml.safe_load(path.read_text())
    except yaml.YAMLError as e:
        raise CurationLoadError(f"Malformed YAML in {path}: {e}") from e
    if not isinstance(raw, dict):
        raise CurationLoadError(f"Top-level YAML must be a mapping in {path}")
    if "default" not in raw:
        raise CurationLoadError(f"Missing required 'default' field in {path}")

    adapters = [
        AdapterMetadata(
            name=a["name"],
            display_name=a.get("display_name", a["name"]),
            rapidapi_url=a.get("rapidapi_url", ""),
            free_tier=a.get("free_tier", ""),
            paid_tier=a.get("paid_tier", ""),
            required_env_var=a.get("required_env_var", ""),
            best_for=(a.get("coverage") or {}).get("best_for", ""),
            worst_for=(a.get("coverage") or {}).get("worst_for", ""),
        )
        for a in raw.get("adapters", []) or []
    ]
    adapter_names = {a.name for a in adapters}

    default_name = raw["default"]
    if default_name not in adapter_names:
        raise CurationLoadError(
            f"default '{default_name}' not in adapters list ({adapter_names}) in {path}"
        )

    classes = []
    for c in raw.get("classes", []) or []:
        if c["recommended_adapter"] not in adapter_names:
            raise CurationLoadError(
                f"class '{c['name']}' recommends '{c['recommended_adapter']}' which is not in adapters list"
            )
        classes.append(
            CandidateClass(
                name=c["name"],
                description=c.get("description", ""),
                recommended_adapter=c["recommended_adapter"],
                rationale=c.get("rationale", ""),
            )
        )

    return Curation(default_name=default_name, classes=classes, adapters=adapters)


def recommend_for_class(curation: Curation, class_name: str) -> AdapterMetadata:
    """Return the recommended adapter metadata for a class, falling back to default."""
    match = next((c for c in curation.classes if c.name == class_name), None)
    if match is None:
        return default_adapter(curation)
    adapter = curation.adapter_by_name(match.recommended_adapter)
    if adapter is None:
        # Should be impossible after load_curation validates, but defensive
        return default_adapter(curation)
    return adapter


def default_adapter(curation: Curation) -> AdapterMetadata:
    adapter = curation.adapter_by_name(curation.default_name)
    if adapter is None:
        raise CurationLoadError(f"Default adapter '{curation.default_name}' not found")
    return adapter
```

- [ ] **Step 5: Run tests — expect pass**

```bash
uv run pytest tests/test_rapidapi_feeds_yaml.py -v
```

- [ ] **Step 6: Lint + type check**

```bash
uv run ruff check src/findajob/fetchers/adapters/curation.py tests/test_rapidapi_feeds_yaml.py
uv run ruff format --check src/findajob/fetchers/adapters/curation.py tests/test_rapidapi_feeds_yaml.py
uv run mypy src/findajob/fetchers/adapters/curation.py
```

- [ ] **Step 7: Commit**

```bash
git add src/findajob/fetchers/adapters/curation.py tests/test_rapidapi_feeds_yaml.py pyproject.toml uv.lock 2>/dev/null
git commit -m "feat(adapters): rapidapi_feeds.yaml curation loader (#408)

Schema-validated loader for the operator-curated feed-recommendations
table. Used by Section 3h prompt + feed-config form's signup
walkthrough. Future #411 (Sonar live recommender) replaces this
loader's role at runtime; static curation stays as the failure-open
fallback."
```

---

## Task 9: Ship `config/rapidapi_feeds.yaml.example` + `config/active_sources.txt.example` + update `data/.env.example` + `.gitignore`

The actual curation table content. Five candidate classes per the spec.

**Files:**
- Create: `config/rapidapi_feeds.yaml.example`
- Create: `config/active_sources.txt.example`
- Modify: `data/.env.example`
- Modify: `.gitignore`

### Steps

- [ ] **Step 1: Create `config/rapidapi_feeds.yaml.example`**

```yaml
# config/rapidapi_feeds.yaml — operator-curated feed recommendations per
# candidate class. Read by the onboarding interviewer at Section 3h
# (when the candidate picks 'a' in 3g) and by the feed-config form's
# signup walkthrough copy.
#
# Ships as .yaml.example; gitignored real file. Operators can edit
# without touching the prompt — the prompt references this file by
# name and trusts its content.
#
# Replace each class's recommended_adapter as you learn from
# production hit-rate data. #411 (Sonar live recommender) will
# eventually consume this same schema dynamically.

default: jobs-api14

classes:
  - name: corporate-tech
    description: |
      Corporate, technology, professional services. Roles posted heavily
      on LinkedIn — programs, engineering, product, data.
    recommended_adapter: jobs-api14
    rationale: |
      Pulls LinkedIn directly. Strong recall for the corporate / tech tier.
      Free tier covers ~150 calls / month — enough for daily polling.

  - name: healthcare-clinical
    description: |
      Healthcare, clinical, hospital systems, allied health.
    recommended_adapter: jobs-api14
    rationale: |
      No specialty-tuned adapter shipped today. jobs-api14's LinkedIn
      coverage is OK for hospital systems and large clinical employers,
      weaker for community / regional clinics. Watch hit-rate after a
      few weeks; consider widening to JSearch if recall is thin.

  - name: skilled-trades-regional
    description: |
      Trades, blue-collar, regional employers. Light LinkedIn presence.
    recommended_adapter: jsearch
    rationale: |
      JSearch aggregates LinkedIn + Indeed + Glassdoor + ZipRecruiter
      under one feed — broader coverage for fields where Indeed is the
      dominant board.

  - name: social-services-nonprofit-education
    description: |
      Social services, non-profits, education, public sector roles.
    recommended_adapter: jsearch
    rationale: |
      Same multi-board coverage rationale. Indeed is the dominant board
      for these fields; JSearch's aggregation captures it.

  - name: remote-only-digital-nomad
    description: |
      Remote-only or geography-flexible roles across any field.
    recommended_adapter: jsearch
    rationale: |
      Multi-board aggregation gives the broadest remote-only filtering
      surface.

adapters:
  - name: jobs-api14
    display_name: Jobs API (jobs-api14)
    rapidapi_url: https://rapidapi.com/Pat92/api/jobs-api14
    free_tier: 150 calls / month
    paid_tier: $5-25 / month for higher quotas
    required_env_var: JOBS_API14_KEY
    coverage:
      best_for: Corporate, tech, professional services, white-collar roles posted to LinkedIn
      worst_for: Trades, regional employers, social services, healthcare-niche roles

  - name: jsearch
    display_name: JSearch
    rapidapi_url: https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch
    free_tier: 200 calls / month
    paid_tier: $25 / month (Pro tier)
    required_env_var: JSEARCH_API_KEY
    coverage:
      best_for: Multi-board aggregation; Indeed-dominant fields; trades, social services, education
      worst_for: LinkedIn-only employers (use jobs-api14 instead)
```

- [ ] **Step 2: Create `config/active_sources.txt.example`**

```
# config/active_sources.txt — registered job-source adapters active for
# this stack. One adapter name per line. Comments and blank lines OK.
# Default if file missing: ["jobs-api14"] (preserves pre-v0.14 behavior).
#
# Adapter names match registry identifiers in
# src/findajob/fetchers/adapters/registry.py — currently:
#   - jobs-api14   # Jobs API (RapidAPI)
#   - jsearch      # JSearch (RapidAPI)

jobs-api14
```

- [ ] **Step 3: Update `data/.env.example`**

Inspect first:

```bash
grep -n "RAPIDAPI" data/.env.example
```

Replace `RAPIDAPI_KEY=...` with:

```
# Per-adapter API keys (#408). Each registered adapter declares its
# own env var. Set the one(s) that match the active feed(s) listed
# in config/active_sources.txt. Adapters with blank env vars are
# silently skipped at triage time.

# Jobs API (jobs-api14) — LinkedIn-skewed; default for v0.14+
JOBS_API14_KEY=

# JSearch — multi-board aggregator (LinkedIn + Indeed + Glassdoor + ZipRecruiter)
# JSEARCH_API_KEY=
```

If the file currently has both `RAPIDAPI_KEY` references (host vs container, etc.), update them all consistently.

- [ ] **Step 4: Update `.gitignore`**

```bash
grep -n "rapidapi_feeds\|active_sources" .gitignore
```

Add (if not present):

```
# Per-stack pipeline config — gitignored, .example tracked
config/rapidapi_feeds.yaml
config/active_sources.txt
```

- [ ] **Step 5: Sanity-check the curation file loads**

```bash
uv run python -c "from findajob.fetchers.adapters.curation import load_curation; from pathlib import Path; print(load_curation(Path('config/rapidapi_feeds.yaml.example')))"
```

Expected: a `Curation(...)` repr with 5 classes and 2 adapters.

- [ ] **Step 6: Commit**

```bash
git add config/rapidapi_feeds.yaml.example config/active_sources.txt.example data/.env.example .gitignore
git commit -m "feat(config): rapidapi_feeds.yaml + active_sources.txt examples (#408)

Five candidate classes (corporate-tech, healthcare-clinical,
skilled-trades-regional, social-services-nonprofit-education,
remote-only-digital-nomad) each mapped to a recommended adapter.
default: jobs-api14 for no-confident-class fallback.

Renames RAPIDAPI_KEY → JOBS_API14_KEY in data/.env.example;
adds commented-out JSEARCH_API_KEY."
```

---

## Task 10: Parser — add `rapidapi_feed.txt` to `OPTIONAL_FILENAMES`

Mechanical extension of #283's existing OPTIONAL pattern.

**Files:**
- Modify: `src/findajob/onboarding/parser.py`
- Modify: `tests/test_onboarding_parser.py`

### Steps

- [ ] **Step 1: Read current parser state**

```bash
grep -n "OPTIONAL_FILENAMES\|ALLOWED_FILENAMES" src/findajob/onboarding/parser.py
```

- [ ] **Step 2: Write failing test**

Append to `tests/test_onboarding_parser.py`:

```python
def test_rapidapi_feed_txt_recognized_as_optional() -> None:
    """#408: rapidapi_feed.txt is a new OPTIONAL filename emitted by Section 3h."""
    blocks = dict(_CLEAN_BLOCKS)
    blocks["rapidapi_feed.txt"] = "jsearch\n"
    blob = "\n\n".join(_wrap(n, b) for n, b in blocks.items())
    result = parse_emission(blob)
    assert "rapidapi_feed.txt" in result.found
    assert result.found["rapidapi_feed.txt"].strip() == "jsearch"
    assert result.unknown == []
```

- [ ] **Step 3: Run test — expect failure (`rapidapi_feed.txt` shows as unknown)**

```bash
uv run pytest tests/test_onboarding_parser.py::test_rapidapi_feed_txt_recognized_as_optional -v
```

- [ ] **Step 4: Add `"rapidapi_feed.txt"` to `OPTIONAL_FILENAMES` tuple in `src/findajob/onboarding/parser.py`**

- [ ] **Step 5: Run all parser tests**

```bash
uv run pytest tests/test_onboarding_parser.py -v
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add src/findajob/onboarding/parser.py tests/test_onboarding_parser.py
git commit -m "feat(onboarding/parser): recognize rapidapi_feed.txt as OPTIONAL (#408)"
```

---

## Task 11: Injector — write `config/active_sources.txt` from `rapidapi_feed.txt`

Extends the injector's existing per-file write loop. The block content is a single registry name (e.g. `jsearch`) on one line.

**Files:**
- Modify: `src/findajob/onboarding/injector.py`
- Create: `tests/test_onboarding_picker_emission.py`

### Steps

- [ ] **Step 1: Skim the injector's existing per-file write logic**

```bash
grep -n "OPTIONAL\|destination\|write_text\|active_sources" src/findajob/onboarding/injector.py | head -30
```

- [ ] **Step 2: Write failing test**

Create `tests/test_onboarding_picker_emission.py`:

```python
"""Tests for picker emission and active_sources.txt write (#408)."""
from __future__ import annotations

from pathlib import Path

import pytest

from findajob.onboarding.injector import inject_emission
from findajob.onboarding.parser import parse_emission


def _emission_with_picker(adapter_name: str) -> str:
    return f"""<<<FILE: profile.md>>>
# Profile
<<<END>>>

<<<FILE: master_resume.md>>>
# Master resume
<<<END>>>

<<<FILE: target_companies.md>>>
## Target companies
<<<END>>>

<<<FILE: business_sector_employers_reference.md>>>
## Reference
<<<END>>>

<<<FILE: prefilter_rules.yaml>>>
patterns: []
<<<END>>>

<<<FILE: in_domain_patterns.yaml>>>
patterns: []
<<<END>>>

<<<FILE: display_name.txt>>>
Test Candidate
<<<END>>>

<<<FILE: timezone.txt>>>
America/Los_Angeles
<<<END>>>

<<<FILE: ntfy_topic.txt>>>
test-topic
<<<END>>>

<<<FILE: rapidapi_feed.txt>>>
{adapter_name}
<<<END>>>
"""


def test_picker_emission_writes_active_sources_txt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("findajob.onboarding.injector.BASE", str(tmp_path))
    (tmp_path / "config").mkdir()
    (tmp_path / "data").mkdir()
    (tmp_path / "candidate_context").mkdir()

    parsed = parse_emission(_emission_with_picker("jsearch"))
    inject_emission(parsed, dry_run=False)

    active_sources = tmp_path / "config" / "active_sources.txt"
    assert active_sources.exists()
    assert active_sources.read_text().strip() == "jsearch"


def test_picker_emission_jobs_api14(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("findajob.onboarding.injector.BASE", str(tmp_path))
    (tmp_path / "config").mkdir()
    (tmp_path / "data").mkdir()
    (tmp_path / "candidate_context").mkdir()

    parsed = parse_emission(_emission_with_picker("jobs-api14"))
    inject_emission(parsed, dry_run=False)

    assert (tmp_path / "config" / "active_sources.txt").read_text().strip() == "jobs-api14"


def test_no_picker_emission_no_active_sources_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """If the candidate didn't pick 'a' in 3g, no rapidapi_feed.txt is emitted, no active_sources.txt is written."""
    monkeypatch.setattr("findajob.onboarding.injector.BASE", str(tmp_path))
    (tmp_path / "config").mkdir()
    (tmp_path / "data").mkdir()
    (tmp_path / "candidate_context").mkdir()

    # emission without rapidapi_feed.txt (drop the trailing block)
    no_picker = _emission_with_picker("jobs-api14").rsplit("<<<FILE: rapidapi_feed.txt>>>", 1)[0]
    parsed = parse_emission(no_picker)
    inject_emission(parsed, dry_run=False)

    assert not (tmp_path / "config" / "active_sources.txt").exists()
```

(NB: this test calls into `inject_emission` — match the existing public surface in `injector.py`. If the actual entry point is named differently, adjust the import.)

- [ ] **Step 3: Run — expect failure**

```bash
uv run pytest tests/test_onboarding_picker_emission.py -v
```

- [ ] **Step 4: Edit `src/findajob/onboarding/injector.py`**

Find where the injector's existing destinations table is defined (e.g. `_OPTIONAL_DESTINATIONS` from #283). Add an entry mapping `"rapidapi_feed.txt"` → `f"{BASE}/config/active_sources.txt"`. The injector's existing write loop will pick it up.

If the injector uses a different mechanism (e.g. an explicit `if "rapidapi_feed.txt" in parsed:` block), follow whatever pattern is already there — don't introduce a new pattern just for this file.

- [ ] **Step 5: Run tests — expect pass**

```bash
uv run pytest tests/test_onboarding_picker_emission.py -v
```

- [ ] **Step 6: Run the broader injector test suite**

```bash
uv run pytest tests/test_onboarding_injector.py -v
```

Expected: no regressions.

- [ ] **Step 7: Lint + type check**

```bash
uv run ruff check src/findajob/onboarding/injector.py tests/test_onboarding_picker_emission.py
uv run ruff format --check src/findajob/onboarding/injector.py tests/test_onboarding_picker_emission.py
uv run mypy src/findajob/onboarding/injector.py
```

- [ ] **Step 8: Commit**

```bash
git add src/findajob/onboarding/injector.py tests/test_onboarding_picker_emission.py
git commit -m "feat(onboarding/injector): write config/active_sources.txt from rapidapi_feed.txt (#408)"
```

---

## Task 12: Onboarding interview prompt — Section 3h

Plain-text edits to `config/roles/onboarding_interviewer.md`. No tests for prompt content directly (covered by walkthrough at Task 17), but a small fixture-based parser test to confirm the file's structure is intact after edits.

**Files:**
- Modify: `config/roles/onboarding_interviewer.md`

### Steps

- [ ] **Step 1: Read the existing 3g section to find insertion point**

```bash
sed -n '345,410p' config/roles/onboarding_interviewer.md
```

- [ ] **Step 2: Append a new sub-phase 3h after the 3g block**

After the 3g conditional-emission rules (around line 405), insert:

````markdown

### 3h. Pick the RapidAPI feed (only if 3g includes 'a')

Run this sub-phase **only if** the candidate's 3g selection included `a`
(paid job-search service). Skip entirely otherwise.

The pipeline supports multiple RapidAPI-flavored feeds; the candidate's
field determines which one will give them useful recall. Don't ask
them to pick blind — recommend, then let them confirm or override.

#### What you have access to

The file `config/rapidapi_feeds.yaml` lists the curated table:

- `default:` — the registry name to use when no class matches confidently.
- `classes:` — five candidate classes with descriptions, recommended
  adapters, and rationale. Today's classes:
    - `corporate-tech` — corporate / tech / professional services
    - `healthcare-clinical` — healthcare / clinical / hospital systems
    - `skilled-trades-regional` — trades / blue-collar / regional employers
    - `social-services-nonprofit-education` — social services / non-profits / education
    - `remote-only-digital-nomad` — remote-first across any field
- `adapters:` — catalog of registered adapters with display name, RapidAPI
  URL, free / paid tier, env var, and best-for / worst-for prose.

**Only recommend adapters listed in this file. Do not invent.** If the
candidate's profile doesn't fit any class confidently, fall back to
`default:`.

#### How to recommend

Say something like:

> Now let me recommend which RapidAPI feed to use. Based on what you've
> told me, your work fits best in the **{class name}** bucket. For
> that, I'd recommend **{display_name}**.
>
> Here's why: {one-paragraph rationale, drawn from the YAML's `rationale`
> field plus the adapter's `coverage.best_for`}.
>
> {If a clear runner-up exists, mention it briefly: "The other option,
> **{other display_name}**, is great for {its best_for} — but lighter
> for {what your candidate's targeting}."}
>
> **{display_name} costs:**
> - Free tier: {free_tier} (enough for daily checking)
> - Paid: {paid_tier} if you ever need more
>
> You'll need to sign up at rapidapi.com (free), subscribe to
> **{display_name}** (also free at the basic tier), and grab the key.
> Want to go with **{display_name}**, or pick something different from
> the list? You can also reply "skip" if you'd rather not use a paid
> service for now.

Adapt the wording to the candidate's voice. Keep it plain — no
technical jargon (no "X-RapidAPI-Key", no "subscription endpoint").

#### Capture and emit

- If the candidate confirms or picks an alternative listed adapter →
  emit `<<<FILE: rapidapi_feed.txt>>>` with the chosen adapter's
  registry name (e.g. `jsearch` or `jobs-api14`) on a single line.
- If the candidate says "skip" or otherwise declines → do **not** emit
  `rapidapi_feed.txt`. The 3g selection effectively collapses from
  `a, ...` to whatever else they picked. The pipeline will run without
  RapidAPI on this stack.

#### Phase 5 update

Add `rapidapi_feed.txt` to the conditional-emission rules. Specifically:
- 3g selection includes `a` AND 3h confirmed → emit `rapidapi_feed.txt` (single-line content: chosen adapter registry name).
- Otherwise → do not emit.

````

- [ ] **Step 3: Update Section 3g's conditional-emission table to mention `rapidapi_feed.txt`**

Find the existing 3g conditional-emission rules (around line 395–404) and add a note:

```diff
 - `a` (RapidAPI) selected → emit `<<<FILE: jsearch_queries.txt>>>`
+  AND continue to sub-phase 3h to pick which RapidAPI feed; that
+  sub-phase emits `<<<FILE: rapidapi_feed.txt>>>`.
```

- [ ] **Step 4: Update Phase 5's emission list with the new conditional**

Find the Phase 5 file-list (around lines 580–680) and add `rapidapi_feed.txt` to the OPTIONAL emission list with a conditional note "emit only if 3g includes `a` AND 3h confirmed."

- [ ] **Step 5: Update Section 0's RapidAPI educational layer (#283 carryover)**

The closing note in Phase 1 about RapidAPI says:

> Note: today the pipeline uses one specific RapidAPI service. A future version will help you pick the one that best fits your field and walk you through the signup.

Update to reflect the post-#408 reality:

> Note: the pipeline supports several RapidAPI services; we'll pick the right one for your field at the end of this phase.

- [ ] **Step 6: Sanity-check the file is still valid Markdown and contains the new section**

```bash
grep -n "^### 3h\." config/roles/onboarding_interviewer.md
grep -n "rapidapi_feed.txt" config/roles/onboarding_interviewer.md
wc -l config/roles/onboarding_interviewer.md
```

Expected: one match for `### 3h.`, multiple matches for `rapidapi_feed.txt`, file is ~50–80 lines longer than before.

- [ ] **Step 7: Commit**

```bash
git add config/roles/onboarding_interviewer.md
git commit -m "feat(onboarding/prompt): Section 3h RapidAPI feed picker (#408)

Adds Section 3h that fires when the candidate picks 'a' in 3g.
Reads config/rapidapi_feeds.yaml; recommends an adapter for the
candidate's class; emits <<<FILE: rapidapi_feed.txt>>>. Updates
Section 3g's conditional emission rules and Phase 5's file list.
Updates Section 0's educational close-note from 'a future version
will help you pick' to reflect the post-#408 reality."
```

---

## Task 13: Web route — `/onboarding/feed-config/{session_id}` GET (form render)

The feed-config form. Initial GET renders. POST (Task 14) runs the live test.

**Files:**
- Create: `src/findajob/web/routes/onboarding_feed_config.py`
- Create: `src/findajob/web/templates/onboarding_feed_config/index.html`
- Create: `src/findajob/web/templates/onboarding_feed_config/_live_test_result.html` (created in Task 14)
- Modify: `src/findajob/web/app.py` (register route)
- Create: `tests/test_onboarding_feed_config_route.py`

### Steps

- [ ] **Step 1: Skim an existing route for the FastAPI + Jinja pattern used in this codebase**

```bash
grep -n "router\|@app\|TemplateResponse" src/findajob/web/routes/onboarding.py | head -10
sed -n '1,50p' src/findajob/web/routes/onboarding.py
```

- [ ] **Step 2: Write failing GET tests**

Create `tests/test_onboarding_feed_config_route.py`:

```python
"""Tests for /onboarding/feed-config/{session_id} (#408)."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from findajob.web.app import create_app


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr("findajob.paths.BASE", str(tmp_path))
    (tmp_path / "config").mkdir()
    (tmp_path / "data").mkdir()
    # write a minimal curation file so the route can read it
    (tmp_path / "config" / "rapidapi_feeds.yaml").write_text(
        Path("config/rapidapi_feeds.yaml.example").read_text()
    )
    # active source = jsearch (the candidate just picked it)
    (tmp_path / "config" / "active_sources.txt").write_text("jsearch\n")
    return TestClient(create_app())


def test_get_renders_form_with_adapter_specific_walkthrough(client: TestClient) -> None:
    response = client.get("/onboarding/feed-config/test-session-id")
    assert response.status_code == 200
    body = response.text
    assert "JSearch" in body
    assert "rapidapi.com" in body
    assert "API key" in body or "Key" in body  # form label


def test_get_404_when_no_active_sources_pending(client: TestClient, tmp_path: Path) -> None:
    """If there's no active_sources.txt, there's no feed to config."""
    (tmp_path / "config" / "active_sources.txt").unlink()
    response = client.get("/onboarding/feed-config/test-session-id")
    assert response.status_code == 404
```

- [ ] **Step 3: Run — expect 404 (route doesn't exist)**

```bash
uv run pytest tests/test_onboarding_feed_config_route.py::test_get_renders_form_with_adapter_specific_walkthrough -v
```

- [ ] **Step 4: Create the route module**

Create `src/findajob/web/routes/onboarding_feed_config.py`:

```python
"""GET/POST /onboarding/feed-config/{session_id} (#408)."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from findajob.fetchers.adapters.curation import (
    AdapterMetadata,
    CurationLoadError,
    load_curation,
)
from findajob.fetchers.adapters.registry import REGISTERED_ADAPTERS, _read_active_sources
from findajob.paths import BASE

router = APIRouter(prefix="/onboarding/feed-config", tags=["onboarding"])

_templates = Jinja2Templates(directory=str(Path(BASE) / "src" / "findajob" / "web" / "templates"))


def _curation_path() -> Path:
    return Path(BASE) / "config" / "rapidapi_feeds.yaml"


def _adapter_metadata_for_active() -> AdapterMetadata:
    """Resolve the metadata for the (single) currently-active adapter that needs configuring."""
    active = _read_active_sources()
    if not active:
        raise HTTPException(status_code=404, detail="No active source pending configuration.")
    cur = load_curation(_curation_path())
    # Pick the first active adapter that's a known registered adapter
    registered_names = {cls.name for cls in REGISTERED_ADAPTERS}
    for name in active:
        if name not in registered_names:
            continue
        meta = cur.adapter_by_name(name)
        if meta is not None:
            return meta
    raise HTTPException(status_code=404, detail="No matching adapter metadata found.")


@router.get("/{session_id}", response_class=HTMLResponse)
def get_feed_config_form(session_id: str, request: Request) -> HTMLResponse:
    try:
        meta = _adapter_metadata_for_active()
    except CurationLoadError as e:
        raise HTTPException(status_code=500, detail=f"Curation load failed: {e}") from e
    return _templates.TemplateResponse(
        "onboarding_feed_config/index.html",
        {
            "request": request,
            "session_id": session_id,
            "adapter": meta,
        },
    )
```

- [ ] **Step 5: Create the template `src/findajob/web/templates/onboarding_feed_config/index.html`**

```html
{% extends "base.html" %}
{% block content %}
<div class="max-w-2xl mx-auto py-8 px-4">
  <h1 class="text-2xl font-semibold mb-2">One last setup step</h1>
  <p class="text-gray-700 mb-6">
    You picked <strong>{{ adapter.display_name }}</strong> as your job-search service.
    To finish, we need your API key from rapidapi.com.
  </p>

  <ol class="list-decimal pl-6 space-y-2 text-gray-700 mb-8">
    <li>Open <a href="{{ adapter.rapidapi_url }}" target="_blank" rel="noopener" class="text-blue-600 hover:underline">{{ adapter.rapidapi_url }}</a> and sign in (or sign up — it's free).</li>
    <li>Click <strong>Subscribe to Test</strong>, then choose the <strong>Basic (free)</strong> plan.</li>
    <li>On the API page, look for the <strong>X-RapidAPI-Key</strong> field in the code samples — copy that value.</li>
    <li>Paste it below.</li>
  </ol>

  <form method="post" action="/onboarding/feed-config/{{ session_id }}" class="space-y-4">
    <div>
      <label for="api_key" class="block font-medium mb-1">Your {{ adapter.display_name }} API key</label>
      <input id="api_key" name="api_key" type="password" autocomplete="off" required
             placeholder="50-character key from RapidAPI"
             class="w-full font-mono px-3 py-2 border rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500">
    </div>

    <div class="flex gap-3">
      <button type="submit" class="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700">Save and test connection</button>
      <button type="submit" name="skip" value="1" class="px-4 py-2 bg-gray-100 text-gray-800 rounded-md hover:bg-gray-200">Skip for now</button>
    </div>

    <p class="text-sm text-gray-500 mt-6 pt-4 border-t">
      Stuck? You can always come back to <strong>/config/</strong> later and add the key, or re-run onboarding.
    </p>
  </form>
</div>
{% endblock %}
```

- [ ] **Step 6: Register the route in `src/findajob/web/app.py`**

Add the import + router include alongside the existing route registrations:

```python
from findajob.web.routes.onboarding_feed_config import router as onboarding_feed_config_router
# ...
app.include_router(onboarding_feed_config_router)
```

- [ ] **Step 7: Run tests — expect pass**

```bash
uv run pytest tests/test_onboarding_feed_config_route.py::test_get_renders_form_with_adapter_specific_walkthrough -v
uv run pytest tests/test_onboarding_feed_config_route.py::test_get_404_when_no_active_sources_pending -v
```

- [ ] **Step 8: Lint + type check**

```bash
uv run ruff check src/findajob/web/routes/onboarding_feed_config.py
uv run ruff format --check src/findajob/web/routes/onboarding_feed_config.py
uv run mypy src/findajob/web/routes/onboarding_feed_config.py
```

- [ ] **Step 9: Commit**

```bash
git add src/findajob/web/routes/onboarding_feed_config.py src/findajob/web/templates/onboarding_feed_config/ src/findajob/web/app.py tests/test_onboarding_feed_config_route.py
git commit -m "feat(web): GET /onboarding/feed-config/{session_id} (#408)

Renders the per-adapter signup walkthrough form. Pulls
display_name, rapidapi_url, free_tier from config/rapidapi_feeds.yaml;
key paste captured into a password-input outside the LLM transcript."
```

---

## Task 14: Web route — POST handler + live test + result rendering

POST writes the key into `data/.env`, runs `adapter.live_test(queries)`, renders the result partial.

**Files:**
- Modify: `src/findajob/web/routes/onboarding_feed_config.py`
- Create: `src/findajob/web/templates/onboarding_feed_config/_live_test_result.html`
- Modify: `tests/test_onboarding_feed_config_route.py` (POST tests)

### Steps

- [ ] **Step 1: Write failing POST tests**

Append to `tests/test_onboarding_feed_config_route.py`:

```python
def test_post_skip_writes_sentinel_no_key_change(client: TestClient, tmp_path: Path) -> None:
    response = client.post(
        "/onboarding/feed-config/test-session-id",
        data={"skip": "1"},
        follow_redirects=False,
    )
    assert response.status_code == 200
    assert "skip" in response.text.lower() or "configure later" in response.text.lower()
    # Sentinel was NOT written here — only on /finish (which is the next click)


def test_post_runs_live_test_and_writes_key_on_success(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A successful POST writes the key into data/.env and renders the success card."""
    monkeypatch.setattr("findajob.paths.BASE", str(tmp_path))
    (tmp_path / "data" / ".env").write_text("OTHER=x\n")
    (tmp_path / "config" / "jsearch_queries.txt").write_text("nurse\nteacher\n")

    # Patch live_test to return a synthetic success result
    from findajob.fetchers.adapters.base import LiveTestResult, QueryResult

    fake_result = LiveTestResult(
        ok=True,
        bucket="success",
        per_query=[
            QueryResult(query="nurse", count=12),
            QueryResult(query="teacher", count=8),
        ],
        auth_error=None,
    )
    monkeypatch.setattr(
        "findajob.fetchers.adapters.jsearch.JSearchAdapter.live_test",
        lambda self, queries: fake_result,
    )

    response = client.post(
        "/onboarding/feed-config/test-session-id",
        data={"api_key": "test-key-50-chars"},
    )
    assert response.status_code == 200
    body = response.text
    assert "12" in body  # nurse count
    assert "8" in body   # teacher count
    assert "JSEARCH_API_KEY=test-key-50-chars" in (tmp_path / "data" / ".env").read_text()


def test_post_auth_failure_does_not_write_key(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("findajob.paths.BASE", str(tmp_path))
    (tmp_path / "data" / ".env").write_text("OTHER=x\n")
    (tmp_path / "config" / "jsearch_queries.txt").write_text("nurse\n")

    from findajob.fetchers.adapters.base import LiveTestResult

    fake_result = LiveTestResult(
        ok=False,
        bucket="auth",
        per_query=[],
        auth_error="HTTP 401",
    )
    monkeypatch.setattr(
        "findajob.fetchers.adapters.jsearch.JSearchAdapter.live_test",
        lambda self, queries: fake_result,
    )

    response = client.post(
        "/onboarding/feed-config/test-session-id",
        data={"api_key": "bad-key"},
    )
    assert response.status_code == 200
    body = response.text
    assert "couldn't connect" in body.lower() or "didn't recognize" in body.lower()
    # Key was NOT written
    assert "JSEARCH_API_KEY" not in (tmp_path / "data" / ".env").read_text()
```

- [ ] **Step 2: Run — expect failure (no POST handler yet)**

```bash
uv run pytest tests/test_onboarding_feed_config_route.py -v
```

- [ ] **Step 3: Add the POST handler in `src/findajob/web/routes/onboarding_feed_config.py`**

Append to the route module:

```python
from fastapi import Form

from findajob.fetchers.adapters.registry import REGISTERED_ADAPTERS

# Map adapter name → adapter class for instantiation
_ADAPTER_CLASSES = {cls.name: cls for cls in REGISTERED_ADAPTERS}


def _read_queries() -> list[str]:
    queries_path = Path(BASE) / "config" / "jsearch_queries.txt"
    if not queries_path.exists():
        return []
    return [
        line.strip()
        for line in queries_path.read_text().splitlines()
        if line.strip() and not line.startswith("#")
    ]


def _write_env_var(env_path: Path, var_name: str, value: str) -> None:
    """Set or overwrite VAR=value in data/.env atomically."""
    if not env_path.exists():
        env_path.write_text(f"{var_name}={value}\n")
        return
    lines = env_path.read_text().splitlines(keepends=True)
    out: list[str] = []
    replaced = False
    for line in lines:
        stripped = line.lstrip()
        if not stripped.startswith("#") and stripped.startswith(f"{var_name}="):
            out.append(f"{var_name}={value}\n")
            replaced = True
        else:
            out.append(line)
    if not replaced:
        ending = "" if out and out[-1].endswith("\n") else "\n"
        out.append(f"{ending}{var_name}={value}\n")
    env_path.write_text("".join(out))


@router.post("/{session_id}", response_class=HTMLResponse)
def post_feed_config(
    session_id: str,
    request: Request,
    api_key: str | None = Form(default=None),
    skip: str | None = Form(default=None),
) -> HTMLResponse:
    meta = _adapter_metadata_for_active()

    if skip:
        return _templates.TemplateResponse(
            "onboarding_feed_config/_live_test_result.html",
            {
                "request": request,
                "session_id": session_id,
                "adapter": meta,
                "skipped": True,
                "result": None,
            },
        )

    if not api_key:
        raise HTTPException(status_code=400, detail="API key is required (or use 'Skip for now').")

    # Locate the adapter class
    adapter_cls = _ADAPTER_CLASSES.get(meta.name)
    if adapter_cls is None:
        raise HTTPException(status_code=500, detail=f"Adapter {meta.name} not registered.")

    # Set the env var in-process (so the adapter can pick it up) and persist
    import os
    env_path = Path(BASE) / "data" / ".env"
    os.environ[meta.required_env_var] = api_key

    queries = _read_queries()
    adapter = adapter_cls()
    result = adapter.live_test(queries)

    if result.ok:
        # Live test succeeded — write the key for next session
        _write_env_var(env_path, meta.required_env_var, api_key)
    else:
        # Failure — do NOT persist the key. Roll back env mutation.
        os.environ.pop(meta.required_env_var, None)

    return _templates.TemplateResponse(
        "onboarding_feed_config/_live_test_result.html",
        {
            "request": request,
            "session_id": session_id,
            "adapter": meta,
            "skipped": False,
            "result": result,
        },
    )


@router.post("/{session_id}/finish", response_class=HTMLResponse)
def post_finish(session_id: str, request: Request) -> HTMLResponse:
    """Write the onboarding sentinel and redirect to /board/."""
    sentinel = Path(BASE) / "data" / ".onboarding-complete"
    sentinel.touch()
    from fastapi.responses import RedirectResponse
    return RedirectResponse("/board/", status_code=303)
```

- [ ] **Step 4: Create the result-rendering template**

Create `src/findajob/web/templates/onboarding_feed_config/_live_test_result.html`:

```html
{% extends "base.html" %}
{% block content %}
<div class="max-w-2xl mx-auto py-8 px-4">

{% if skipped %}
  <div class="p-4 bg-amber-50 border-l-4 border-amber-600 rounded-md">
    <h3 class="text-amber-900 font-semibold mb-1">Skipped for now</h3>
    <p class="text-amber-900">No problem. You can come back to <a href="/config/" class="underline">/config/</a> any time and add your key. The pipeline will run without {{ adapter.display_name }} until you do.</p>
  </div>
  <form method="post" action="/onboarding/feed-config/{{ session_id }}/finish" class="mt-6">
    <button type="submit" class="px-4 py-2 bg-green-600 text-white rounded-md hover:bg-green-700">Finish onboarding</button>
  </form>

{% elif result.bucket in ("success", "mixed", "zero_rows") %}
  <h2 class="text-xl font-semibold mb-4">Test results</h2>
  <div class="p-4 bg-gray-50 rounded-md font-mono text-sm space-y-1 mb-6">
    {% for qr in result.per_query %}
      <div class="text-green-700">✓ "{{ qr.query }}" — found {{ qr.count }} jobs{% if qr.count == 0 %} <span class="text-gray-500">(narrow search; that's normal)</span>{% endif %}</div>
    {% endfor %}
  </div>

  {% if result.bucket == "zero_rows" %}
    <div class="p-4 bg-amber-50 border-l-4 border-amber-600 rounded-md">
      <h3 class="text-amber-900 font-semibold mb-1">Connected — but no matches today</h3>
      <p class="text-amber-900">Your connection is working, but none of your search terms matched any active jobs today. That can happen with narrow searches. Job postings turn over daily, so we'll keep checking. If your daily fetch stays empty for a week, you may want to broaden your terms in <strong>config/jsearch_queries.txt</strong>.</p>
      <p class="text-amber-900 mt-2">For now, this is a successful setup.</p>
    </div>
  {% else %}
    <div class="p-4 bg-green-50 border-l-4 border-green-600 rounded-md">
      <h3 class="text-green-900 font-semibold mb-1">Connected to {{ adapter.display_name }}.</h3>
      <p class="text-green-900">Across your {{ result.per_query|length }} search terms, today returned <strong>{{ result.per_query|sum(attribute="count") }} jobs</strong> total.</p>
      <p class="text-green-900 mt-2">Your full first batch lands tomorrow morning — that's the real test, since job postings turn over each day.</p>
    </div>
  {% endif %}

  <form method="post" action="/onboarding/feed-config/{{ session_id }}/finish" class="mt-6">
    <button type="submit" class="px-4 py-2 bg-green-600 text-white rounded-md hover:bg-green-700">Finish onboarding</button>
  </form>

{% else %}
  {# Failure buckets: auth, rate_limit, server, network #}
  <div class="p-4 bg-red-50 border-l-4 border-red-600 rounded-md">
    {% if result.bucket == "auth" %}
      <h3 class="text-red-900 font-semibold mb-1">Couldn't connect</h3>
      <p class="text-red-900">{{ adapter.display_name }} didn't recognize your key. The most common cause is that your subscription isn't active yet.</p>
      <p class="text-red-900 mt-2"><strong>Try this:</strong> go back to <a href="{{ adapter.rapidapi_url }}" target="_blank" rel="noopener" class="underline">rapidapi.com</a>, find {{ adapter.display_name }}, and make sure the <strong>Basic (free)</strong> plan shows as Subscribed.</p>
    {% elif result.bucket == "rate_limit" %}
      <h3 class="text-red-900 font-semibold mb-1">Rate limited</h3>
      <p class="text-red-900">{{ adapter.display_name }} is rate-limiting requests right now — common on the free tier. Try again in a few minutes, or skip and we'll retry at the next daily fetch.</p>
    {% elif result.bucket == "server" %}
      <h3 class="text-red-900 font-semibold mb-1">{{ adapter.display_name }} is having trouble responding</h3>
      <p class="text-red-900">Try again in a few minutes, or skip and we'll retry at the next daily fetch.</p>
    {% else %}
      <h3 class="text-red-900 font-semibold mb-1">Couldn't reach RapidAPI</h3>
      <p class="text-red-900">Check your internet connection or skip — we'll retry tomorrow.</p>
    {% endif %}
  </div>

  <div class="mt-6 flex gap-3">
    <a href="/onboarding/feed-config/{{ session_id }}" class="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700">Try again</a>
    <form method="post" action="/onboarding/feed-config/{{ session_id }}" class="inline">
      <input type="hidden" name="skip" value="1">
      <button type="submit" class="px-4 py-2 bg-gray-100 text-gray-800 rounded-md hover:bg-gray-200">Skip for now</button>
    </form>
  </div>
{% endif %}

</div>
{% endblock %}
```

- [ ] **Step 5: Run all feed-config tests**

```bash
uv run pytest tests/test_onboarding_feed_config_route.py -v
```

Expected: all pass.

- [ ] **Step 6: Lint + type check**

```bash
uv run ruff check src/findajob/web/routes/onboarding_feed_config.py
uv run ruff format --check src/findajob/web/routes/onboarding_feed_config.py
uv run mypy src/findajob/web/routes/onboarding_feed_config.py
```

- [ ] **Step 7: Commit**

```bash
git add src/findajob/web/routes/onboarding_feed_config.py src/findajob/web/templates/onboarding_feed_config/_live_test_result.html tests/test_onboarding_feed_config_route.py
git commit -m "feat(web): POST /onboarding/feed-config + live-test result rendering (#408)

POST writes key, runs adapter.live_test(queries), renders bucket-
discriminated card (success / mixed / zero_rows / auth / rate_limit /
server / network). Failure buckets do NOT persist the key.
/finish endpoint writes the onboarding sentinel + redirects to /board/."
```

---

## Task 15: Injector — sentinel-or-redirect decision

After the interview emission completes, decide whether to write the sentinel directly (existing key works) or redirect through `/onboarding/feed-config/`.

**Files:**
- Modify: `src/findajob/onboarding/injector.py`
- Modify: `tests/test_onboarding_picker_emission.py`

### Steps

- [ ] **Step 1: Locate the existing sentinel-write path**

```bash
grep -n "onboarding-complete\|sentinel" src/findajob/onboarding/injector.py
```

- [ ] **Step 2: Write failing test**

Append to `tests/test_onboarding_picker_emission.py`:

```python
def test_inject_skips_sentinel_when_active_adapter_unconfigured(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If active adapter's env var is blank, sentinel is NOT written; gate to feed-config."""
    monkeypatch.setattr("findajob.onboarding.injector.BASE", str(tmp_path))
    monkeypatch.delenv("JSEARCH_API_KEY", raising=False)
    (tmp_path / "config").mkdir()
    (tmp_path / "data").mkdir()
    (tmp_path / "candidate_context").mkdir()

    parsed = parse_emission(_emission_with_picker("jsearch"))
    decision = inject_emission(parsed, dry_run=False)

    sentinel = tmp_path / "data" / ".onboarding-complete"
    assert not sentinel.exists()
    assert decision.gate_to_feed_config is True
    assert decision.pending_adapter == "jsearch"


def test_inject_writes_sentinel_when_active_adapter_configured(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If active adapter's env var is set, sentinel is written immediately."""
    monkeypatch.setattr("findajob.onboarding.injector.BASE", str(tmp_path))
    monkeypatch.setenv("JOBS_API14_KEY", "existing-key")
    (tmp_path / "config").mkdir()
    (tmp_path / "data").mkdir()
    (tmp_path / "candidate_context").mkdir()

    parsed = parse_emission(_emission_with_picker("jobs-api14"))
    decision = inject_emission(parsed, dry_run=False)

    sentinel = tmp_path / "data" / ".onboarding-complete"
    assert sentinel.exists()
    assert decision.gate_to_feed_config is False
```

- [ ] **Step 3: Run — expect failure (no decision return value yet)**

```bash
uv run pytest tests/test_onboarding_picker_emission.py -v
```

- [ ] **Step 4: Update `inject_emission()` in `src/findajob/onboarding/injector.py`**

Add a return-value dataclass and the gate logic. Specifically:

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class InjectionDecision:
    gate_to_feed_config: bool
    pending_adapter: str | None  # adapter name to configure, if gating

def inject_emission(parsed: ParsedEmission, dry_run: bool = False) -> InjectionDecision:
    # ... existing file-write logic ...

    # After all files are written: decide whether to gate to feed-config
    active_path = Path(BASE) / "config" / "active_sources.txt"
    if not active_path.exists():
        # No picker emission → existing behavior (write sentinel)
        _write_sentinel()
        return InjectionDecision(gate_to_feed_config=False, pending_adapter=None)

    from findajob.fetchers.adapters.registry import REGISTERED_ADAPTERS
    active = [n.strip() for n in active_path.read_text().splitlines() if n.strip() and not n.startswith("#")]
    classes_by_name = {c.name: c for c in REGISTERED_ADAPTERS}
    needs_gate = False
    pending: str | None = None
    for name in active:
        if name not in classes_by_name:
            continue
        instance = classes_by_name[name]()
        if not instance.is_configured():
            needs_gate = True
            pending = name
            break

    if needs_gate:
        return InjectionDecision(gate_to_feed_config=True, pending_adapter=pending)

    _write_sentinel()
    return InjectionDecision(gate_to_feed_config=False, pending_adapter=None)
```

(Match the existing function signature — if `inject_emission` already returns something else, extend it appropriately. If it returns `None` today, the test above expects a new return value; update callers accordingly.)

- [ ] **Step 5: Update callers**

Find every caller of `inject_emission`:

```bash
grep -rn "inject_emission" src/ tests/ scripts/
```

Update the onboarding interview's "complete the interview" handler to inspect `InjectionDecision` and redirect to `/onboarding/feed-config/{session_id}` when `gate_to_feed_config=True`. The `session_id` is the existing `OnboardingSession.session_id` value already in scope at the call site.

- [ ] **Step 6: Run all injector + onboarding tests**

```bash
uv run pytest tests/test_onboarding_picker_emission.py tests/test_onboarding_injector.py tests/test_onboarding_interview.py -v 2>/dev/null
```

Expected: pass.

- [ ] **Step 7: Lint + type check**

```bash
uv run ruff check src/findajob/onboarding/injector.py
uv run ruff format --check src/findajob/onboarding/injector.py
uv run mypy src/findajob/onboarding/injector.py
```

- [ ] **Step 8: Commit**

```bash
git add src/findajob/onboarding/injector.py tests/test_onboarding_picker_emission.py
# also any caller files updated in step 5
git commit -m "feat(onboarding/injector): gate sentinel on active-adapter is_configured (#408)

Returns InjectionDecision; callers redirect to /onboarding/feed-config/
when the chosen adapter's env var isn't set yet. Existing behavior
preserved when active_sources.txt is missing (sentinel writes
immediately, like pre-#408)."
```

---

## Task 16: Documentation Impact updates

Per spec §9. Every doc surface that becomes stale updates in this task.

**Files (all modified):**
- `CLAUDE.md`
- `docs/setup/configure.md`
- `docs/setup/api-keys.md`
- `docs/setup/install-docker.md`
- `docs/usage.md`
- `CHANGELOG.md`
- `docs/release-process.md` (audit + update if needed)

### Steps

- [ ] **Step 1: Update `CLAUDE.md` — Pipeline Context Table "Job ingestion" row**

Find the row currently reading something like `| Job ingestion | jobs-api14 (RapidAPI) — LinkedIn only ... |` and replace with:

```
| Job ingestion | Pluggable via `JobSourceAdapter` (`src/findajob/fetchers/adapters/`); jobs-api14 + JSearch ship in v0.14; per-stack active list in `config/active_sources.txt`. Greenhouse / Ashby / Lever / Gmail still function-style — migration tracked in #410. |
```

Also update Container Context references to `RAPIDAPI_KEY` → `JOBS_API14_KEY`. Update Key File Locations to add `src/findajob/fetchers/adapters/`, `config/active_sources.txt`, `config/rapidapi_feeds.yaml`.

- [ ] **Step 2: Add "Source adapters are pluggable" rule to Critical Architecture Rules**

Insert a new rule after "RAG Policy":

```markdown
### Source Adapters are Pluggable
Every RapidAPI-flavored job source implements `JobSourceAdapter`
(`src/findajob/fetchers/adapters/base.py`). Adding a new feed = one new
adapter file + one entry in `REGISTERED_ADAPTERS`. `triage.py` iterates
the registry; no per-source code paths in triage. Each adapter declares
its own env var (`JOBS_API14_KEY`, `JSEARCH_API_KEY`, etc.) — there is no
global `RAPIDAPI_KEY`. The `JobSourceAdapter` Protocol is source-agnostic
by design — direct fetchers (Workday CXS #248, Gem GraphQL #249) implement
the same contract.
```

- [ ] **Step 3: Update `docs/setup/configure.md`**

Add a new section "Choosing your job-search service" describing the picker step (Section 3h of the interview) and what the candidate sees. Replace any `RAPIDAPI_KEY` references with `JOBS_API14_KEY`.

- [ ] **Step 4: Update `docs/setup/api-keys.md`**

The RapidAPI section currently describes "the RapidAPI key." Rewrite to:
- The pipeline supports multiple RapidAPI feeds (jobs-api14, JSearch, with more coming).
- Each feed has its own env var (`JOBS_API14_KEY`, `JSEARCH_API_KEY`).
- Onboarding's Section 3h recommends a feed for your field; the feed-config form walks you through signup.
- Per-feed signup walkthroughs for jobs-api14 and JSearch (a few sentences each pointing at the RapidAPI listing).

- [ ] **Step 5: Update `docs/setup/install-docker.md`**

Update `data/.env` template references to use the new env var names. Add an "Upgrading from v0.13" section noting the migration is automatic.

- [ ] **Step 6: Update `docs/usage.md`**

Brief paragraph mentioning the picker step and the `/onboarding/feed-config/` form.

- [ ] **Step 7: Audit `docs/release-process.md`**

```bash
grep -n "jobs-api14\|RAPIDAPI_KEY\|fetcher" docs/release-process.md
```

If any references assume single hardcoded fetcher, update them.

- [ ] **Step 8: Update `CHANGELOG.md` — `[0.14.0]` entry**

Add under `## [Unreleased]` (or `## [0.14.0]` if cutting now):

```markdown
### Added
- Pluggable `JobSourceAdapter` framework (`src/findajob/fetchers/adapters/`) for RapidAPI-flavored job sources (#408)
- JSearch adapter — multi-board aggregator (LinkedIn + Indeed + Glassdoor + ZipRecruiter) (#408, closes #310)
- Onboarding picker for RapidAPI feeds — Section 3h reads `config/rapidapi_feeds.yaml` and recommends a feed for the candidate's field (#408)
- `/onboarding/feed-config/{session_id}` form with live connection test exercising every query in `config/jsearch_queries.txt` (#408)
- `config/active_sources.txt` per-stack active-source list (#408)

### Changed
- `RAPIDAPI_KEY` env var renamed to `JOBS_API14_KEY` for clarity; `triage.py` now iterates `iter_configured_adapters()` instead of calling hardcoded fetcher functions for RapidAPI feeds (#408)

### Migration required
- **Existing stacks pulling v0.14:** the entrypoint auto-migrates `RAPIDAPI_KEY` to `JOBS_API14_KEY` in `data/.env` on first boot. No manual action needed.
- Existing stacks without `config/active_sources.txt` keep the pre-v0.14 behavior automatically (jobs-api14 active by default).
- To pick a different feed, re-run `/onboarding/?mode=rerun` — Section 3h presents the picker.
```

- [ ] **Step 9: Run lint on docs**

```bash
uv run ruff check docs/ 2>/dev/null || true
ls docs/setup/configure.md docs/setup/api-keys.md docs/setup/install-docker.md docs/usage.md CHANGELOG.md
```

- [ ] **Step 10: Commit**

```bash
git add CLAUDE.md docs/ CHANGELOG.md
git commit -m "docs: #408 — JobSourceAdapter framework + picker + migration

Updates Pipeline Context Table, adds 'Source Adapters are Pluggable'
architecture rule, rewrites RapidAPI sections of configure.md/
api-keys.md/install-docker.md to reflect the picker UX, adds
CHANGELOG entry with ### Migration required bullet."
```

---

## Task 17: Walkthrough on `findajob-test`

Manual verification per spec §8.3. This is the only walkthrough we run for #408 — the handoff prompt's anti-target ("don't run another `findajob-test` walkthrough until prompt-revising") allows it because Section 3h is a prompt revision.

### Steps

- [ ] **Step 1: Push the feature branch and build a `:pr-NNN` image**

Follow the existing release-process.md pattern. Likely:

```bash
git push -u origin feat/408-rapidapi-feed-picker
# Open the PR; the CI builds :pr-NNN
```

- [ ] **Step 2: Update `findajob-test`'s compose to pin the new image**

```bash
ssh docker.lan 'sudo sed -i "s|image: ghcr.io/brockamer/findajob:.*|image: ghcr.io/brockamer/findajob:pr-NNN|" /opt/stacks/findajob-test/compose.yaml && cd /opt/stacks/findajob-test && sudo docker compose pull && sudo docker compose up -d'
```

(Replace `NNN` with the actual PR number from Step 1.)

- [ ] **Step 3: Walk through onboarding from scratch**

Open `https://findajob-test.<operator-domain>/onboarding/`. Step 1 (keys), then Step 2 (interview). At Section 3g pick `a`. Observe Section 3h's recommendation. Confirm the chosen adapter. Watch the emission complete; observe redirect to `/onboarding/feed-config/{session_id}`. Paste a test JSearch key. Watch the live test stream (per-query results). Click Finish. Verify redirect to `/board/` and that `/board/` loads.

- [ ] **Step 4: Verify file state on `findajob-test`**

```bash
ssh docker.lan 'sudo cat /opt/stacks/findajob-test/state/config/active_sources.txt'
ssh docker.lan 'sudo grep -E "JOBS_API14_KEY|JSEARCH_API_KEY|RAPIDAPI_KEY" /opt/stacks/findajob-test/state/data/.env'
ssh docker.lan 'sudo ls -la /opt/stacks/findajob-test/state/data/.onboarding-complete'
```

Expected: `active_sources.txt` contains the chosen adapter; `.env` has the new env var(s) and no `RAPIDAPI_KEY`; sentinel exists.

- [ ] **Step 5: Verify operator-stack migration**

After this PR's image is on the operator's stack (post-merge, post-tag), verify the migration ran successfully against whichever stack tracks `:latest`:

```bash
ssh docker.lan 'sudo grep -E "JOBS_API14_KEY|RAPIDAPI_KEY" /opt/stacks/findajob-<operator-handle>/state/data/.env'
```

Expected: `JOBS_API14_KEY` populated, no `RAPIDAPI_KEY` line. The operator stack's next triage cycle pulls jobs successfully.

- [ ] **Step 6: Document the walkthrough outcome on the PR**

Comment on the PR with the `findajob-test` walkthrough result, confirming all spec acceptance criteria from §11 are met.

---

## Task 18: Stale-issue reconciliation

Per spec §10. Posted before merge.

### Steps

- [ ] **Step 1: Comment on #310 and close it**

```bash
gh issue comment 310 --body "JSearch ships as Adapter #2 in #408 (PR #NNN), validating the new \`JobSourceAdapter\` framework. Closing this as fully delivered by #408. Adzuna scope, originally bundled here, lives in a future issue when an Adzuna key is provisioned."
gh issue close 310 --reason completed --comment "Closed via #408 / PR #NNN."
```

- [ ] **Step 2: Comment on #274 (leave open)**

```bash
gh issue comment 274 --body "#408's per-class curation table at \`config/rapidapi_feeds.yaml\` is the architectural answer to the diagnostic this issue posed — the LinkedIn-skewed jobs-api14 default is replaced with field-appropriate feeds via the picker. Leaving this issue open because the empirical 'did rotation help?' question is still active across the tester cohort and will inform future curation tuning."
```

- [ ] **Step 3: Comment on #247**

```bash
gh issue comment 247 --body "Side-effect knowledge from #408's RapidAPI feed survey: {fill in based on what the survey actually found about LinkedIn-recs RapidAPI adapters — either 'no quality adapter exists today, parking this issue until one launches' or 'X adapter looks promising, see comment for details'}."
```

(Replace the placeholder with the actual finding when running this task.)

- [ ] **Step 4: Comment on #225**

```bash
gh issue comment 225 --body "#408 implements per-adapter env vars (\`JOBS_API14_KEY\`, \`JSEARCH_API_KEY\`) for the RapidAPI-flavored sources — one concrete instance of the broader per-role credential cascade this issue tracks. #225 stays open as the broader work covering all roles + the formal cascade design. The pattern from #408 (each adapter declares its own env var via a class attribute) is a candidate building block."
```

- [ ] **Step 5: Comment on #372**

```bash
gh issue comment 372 --body "#408 settles the per-tenant fetcher-config-file convention: \`config/<file>.txt\` (not \`candidate_context/\`). \`active_sources.txt\` follows the \`feed_urls.txt\` pattern — operator-editable per-stack config the fetcher layer reads at runtime. #372's \`target_locations.txt\` should inherit the same shape."
```

- [ ] **Step 6: Comment on #150**

```bash
gh issue comment 150 --body "Reserve a tile slot in the planned tools list for **'Re-pick RapidAPI feed'** — points at \`/onboarding/?mode=rerun\` (or a future dedicated \`/tools/feed-picker/\` route). Useful for testers who want to switch feeds after a few weeks of hit-rate data without re-running the full interview. Doesn't have to ship in #150's first PR."
```

- [ ] **Step 7: No commit (these are GitHub comments, not file changes)**

---

## Task 19: Open the PR + close-out

### Steps

- [ ] **Step 1: Push and open the PR**

```bash
git push origin feat/408-rapidapi-feed-picker
gh pr create --title "feat(onboarding): #408 curated RapidAPI feed picker + JobSourceAdapter framework (closes #310)" --body "$(cat <<'EOF'
## Summary

- Pluggable `JobSourceAdapter` framework for RapidAPI-flavored job sources
- Onboarding picker (Section 3h) recommends a feed for the candidate's field from `config/rapidapi_feeds.yaml`
- `/onboarding/feed-config/{session_id}` form with live connection test exercising every query
- Bundles #310 — JSearch ships as Adapter #2 validating the framework
- Hard-migration `RAPIDAPI_KEY` → `JOBS_API14_KEY` at entrypoint (idempotent)

## Test plan

- [x] Unit tests pass (adapter base, registry, jobs-api14, jsearch, env-migrate, curation, parser)
- [x] Integration tests pass (triage with multiple adapters, feed-config route, picker emission)
- [x] Walkthrough on `findajob-test` per spec §8.3
- [x] Operator-stack migration verified post-merge
- [x] Documentation updates landed in same PR (CLAUDE.md, docs/setup/*, CHANGELOG)
- [x] Stale-issue comments posted (#310 closed, #274/#247/#225/#372/#150 commented)
- [x] migration-required label applied (RAPIDAPI_KEY → JOBS_API14_KEY rename)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 2: Add the `migration-required` label to the PR**

```bash
gh pr edit --add-label migration-required
```

(Per CLAUDE.md release management — schema/config/crontab/mount/compose-down changes get this label at PR-open time so release notes surface them.)

- [ ] **Step 3: Wait for CI to pass**

```bash
gh pr checks --watch
```

- [ ] **Step 4: Merge after operator review**

(Operator merges via UI or CLI; not in scope for the implementing engineer.)

---

## Self-review checklist

After completing the plan, the implementing agent should walk through:

1. **Spec coverage** — every section of `docs/superpowers/specs/2026-05-02-408-design.md` maps to at least one task:
   - §4.1 architecture → Tasks 1–7
   - §4.4 curation → Tasks 8–9
   - §4.5 prompt → Task 12
   - §4.6 parser/injector → Tasks 10, 11, 15
   - §4.7 web route → Tasks 13, 14
   - §4.3 migration → Task 6
   - §9 docs → Task 16
   - §10 reconciliation → Task 18
   - §11 acceptance criteria → cross-referenced throughout
   - §12 migration → Task 6 + Task 16 CHANGELOG entry

2. **Placeholder scan** — no `TBD` / `TODO` / "fill in details" in any task. Every code block is complete. Every command is exact.

3. **Type consistency** — adapter class names match between Tasks 3, 4, 5, 11, 14: `JobsApi14Adapter`, `JSearchAdapter`. Registry name strings match: `jobs-api14`, `jsearch`. Env var names match: `JOBS_API14_KEY`, `JSEARCH_API_KEY`. `LiveTestResult.bucket` values match between adapter implementations and template renderer.

4. **Spec acceptance criteria coverage** (16 items in spec §11):
   1. Protocol + registry → Tasks 2, 5
   2. JobsApi14Adapter + JSearchAdapter registered → Tasks 3, 4
   3. triage.py uses registry → Task 7
   4. Section 3h prompt → Task 12
   5. Parser + injector recognize file → Tasks 10, 11
   6. Feed-config route → Tasks 13, 14
   7. Live test exercises every query → Task 14 + tests in Tasks 3, 4
   8. Hard migration at entrypoint → Task 6
   9. `rapidapi_feeds.yaml.example` → Task 9
   10. `data/.env.example` updated → Task 9
   11. Backwards-compat default → Task 5
   12. CHANGELOG `### Migration required` → Task 16
   13. Documentation updates → Task 16
   14. Stale-issue reconciliation → Task 18
   15. Walkthrough on `findajob-test` → Task 17
   16. JSearch closes #310 → Task 18

If anything is missing, add the task before starting implementation.
