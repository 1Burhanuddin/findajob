# #414 PR1 — Shared RapidAPI Key + Indeed Adapter Restoration

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make all RapidAPI-flavored adapters share a single account-level credential (`RAPIDAPI_KEY`) with per-adapter env var fallbacks for legacy stacks, and restore Indeed coverage via a new `JobsApi14IndeedAdapter` tuned with `sortType=date` + post-fetch keyword filter to compensate for jobs-api14's missing recency/level/type filters on Indeed.

**Architecture:** New small module `_keys.py` under `fetchers/adapters/` exports `resolve_rapidapi_key(*candidate_env_vars)` returning the first non-empty env var value (canonical-first order). Both existing adapters (`JobsApi14Adapter`, `JSearchAdapter`) refactor to use it. New adapter `JobsApi14IndeedAdapter` follows the same `JobSourceAdapter` Protocol — separate file, separate class, shares the host + auth shape with `JobsApi14Adapter` but has its own `_params()` (sortType=date, countryCode=us) and `_parse_rows()` (writes inline `description`, no separate `/get` call). Registered in `REGISTERED_ADAPTERS`. Testers' stacks unchanged behavior via env var fallback; new onboardings use `RAPIDAPI_KEY` only.

**Tech Stack:** Python 3.13, FastAPI (no web changes here), pytest, ruff, mypy, requests, uv.

---

## Pre-flight

- [ ] **Step P1: Branch off origin/main**

```bash
cd /home/brockamer/Code/findajob
git fetch origin
git checkout -b feat/414-shared-key-and-indeed origin/main
```

Expected: `Switched to a new branch 'feat/414-shared-key-and-indeed'`. New branch tracks the freshest origin/main, not local main (per memory rule `feedback_git_branch_off_origin`).

- [ ] **Step P2: Verify clean baseline**

```bash
uv run pytest tests/ -x -q 2>&1 | tail -5
uv run ruff check src/ tests/ 2>&1 | tail -3
uv run ruff format --check src/ tests/ 2>&1 | tail -3
uv run mypy src/ 2>&1 | tail -3
```

Expected: all four exit 0. If any fail, baseline is broken — stop and investigate before adding new work.

---

## Task 1: Shared key resolver helper

**Files:**
- Create: `src/findajob/fetchers/adapters/_keys.py`
- Test: `tests/test_adapter_shared_key.py`

- [ ] **Step 1.1: Write the failing test**

Create `tests/test_adapter_shared_key.py`:

```python
"""Tests for the shared RapidAPI key resolver (#414)."""

from __future__ import annotations

import pytest

from findajob.fetchers.adapters._keys import resolve_rapidapi_key


@pytest.fixture(autouse=True)
def _scrub_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("RAPIDAPI_KEY", "JOBS_API14_KEY", "JSEARCH_API_KEY"):
        monkeypatch.delenv(var, raising=False)


def test_returns_empty_when_no_vars_set() -> None:
    assert resolve_rapidapi_key("RAPIDAPI_KEY", "JOBS_API14_KEY") == ""


def test_returns_canonical_when_only_canonical_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RAPIDAPI_KEY", "shared-1234")
    assert resolve_rapidapi_key("RAPIDAPI_KEY", "JOBS_API14_KEY") == "shared-1234"


def test_returns_dedicated_when_only_dedicated_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JOBS_API14_KEY", "legacy-1234")
    assert resolve_rapidapi_key("RAPIDAPI_KEY", "JOBS_API14_KEY") == "legacy-1234"


def test_canonical_wins_over_dedicated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RAPIDAPI_KEY", "shared-1234")
    monkeypatch.setenv("JOBS_API14_KEY", "legacy-1234")
    assert resolve_rapidapi_key("RAPIDAPI_KEY", "JOBS_API14_KEY") == "shared-1234"


def test_treats_empty_string_as_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RAPIDAPI_KEY", "")
    monkeypatch.setenv("JOBS_API14_KEY", "legacy-1234")
    assert resolve_rapidapi_key("RAPIDAPI_KEY", "JOBS_API14_KEY") == "legacy-1234"


def test_treats_whitespace_only_as_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RAPIDAPI_KEY", "   ")
    monkeypatch.setenv("JOBS_API14_KEY", "legacy-1234")
    assert resolve_rapidapi_key("RAPIDAPI_KEY", "JOBS_API14_KEY") == "legacy-1234"


def test_argument_order_defines_priority(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RAPIDAPI_KEY", "shared-1234")
    monkeypatch.setenv("JOBS_API14_KEY", "legacy-1234")
    # Reversed order: dedicated first should win
    assert resolve_rapidapi_key("JOBS_API14_KEY", "RAPIDAPI_KEY") == "legacy-1234"
```

- [ ] **Step 1.2: Run test to verify it fails**

```bash
uv run pytest tests/test_adapter_shared_key.py -v 2>&1 | tail -15
```

Expected: `ModuleNotFoundError: No module named 'findajob.fetchers.adapters._keys'`.

- [ ] **Step 1.3: Write minimal implementation**

Create `src/findajob/fetchers/adapters/_keys.py`:

```python
"""Shared RapidAPI key resolver (#414).

Both `JobsApi14Adapter` and `JSearchAdapter` (and any future RapidAPI-flavored
adapter) accept the SAME account-level X-RapidAPI-Key — the per-adapter env
var separation in #408 was based on a wrong premise (that each API has its
own credential). This helper looks up a list of candidate env vars and
returns the first non-empty value, treating whitespace-only as unset.

Convention: callers pass the canonical name (`RAPIDAPI_KEY`) first, then any
legacy per-adapter names as fallbacks (e.g. `JOBS_API14_KEY`). New
onboardings write only the canonical; existing tester stacks keep working
via fallback without code-side migration.
"""

from __future__ import annotations

import os


def resolve_rapidapi_key(*candidate_env_vars: str) -> str:
    """Return the first non-empty value among the candidate env vars.

    Whitespace-only values are treated as unset. Returns "" if none set.
    """
    for var in candidate_env_vars:
        value = os.environ.get(var, "").strip()
        if value:
            return value
    return ""
```

- [ ] **Step 1.4: Run tests to verify they pass**

```bash
uv run pytest tests/test_adapter_shared_key.py -v 2>&1 | tail -15
```

Expected: 7 passed.

- [ ] **Step 1.5: Commit**

```bash
git add src/findajob/fetchers/adapters/_keys.py tests/test_adapter_shared_key.py
git commit -m "feat(adapters): #414 shared RapidAPI key resolver

Single helper for both adapters to look up a canonical RAPIDAPI_KEY first,
falling back to the per-adapter env var (JOBS_API14_KEY / JSEARCH_API_KEY).
The #408 design assumed each API had its own credential; one RapidAPI
account key actually covers every API the user has subscribed to."
```

---

## Task 2: Refactor `JobsApi14Adapter` to use shared resolver

**Files:**
- Modify: `src/findajob/fetchers/adapters/jobs_api14.py:31-37`
- Modify: `tests/test_jobs_api14_adapter.py:35-38`

- [ ] **Step 2.1: Update existing test that asserts no fallback**

Edit `tests/test_jobs_api14_adapter.py`. Replace the body of `test_is_configured_does_not_fall_back_to_rapidapi_key` (and rename it) to assert the OPPOSITE — the helper now provides fallback. Locate lines 35-38:

```python
def test_is_configured_does_not_fall_back_to_rapidapi_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """No production-code fallback. Migration handles RAPIDAPI_KEY at entrypoint."""
    monkeypatch.setenv("RAPIDAPI_KEY", "old-key-1234")
    assert JobsApi14Adapter().is_configured() is False
```

Replace with:

```python
def test_is_configured_falls_back_to_rapidapi_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Shared RAPIDAPI_KEY backs JobsApi14Adapter when JOBS_API14_KEY is unset (#414)."""
    monkeypatch.setenv("RAPIDAPI_KEY", "shared-1234")
    assert JobsApi14Adapter().is_configured() is True


def test_is_configured_dedicated_var_wins_over_canonical(monkeypatch: pytest.MonkeyPatch) -> None:
    """RAPIDAPI_KEY is canonical, but if both are set, RAPIDAPI_KEY wins (#414)."""
    monkeypatch.setenv("RAPIDAPI_KEY", "shared-1234")
    monkeypatch.setenv("JOBS_API14_KEY", "legacy-1234")
    # Both adapters use canonical-first lookup; canonical wins
    assert JobsApi14Adapter().is_configured() is True
```

- [ ] **Step 2.2: Run the modified tests — they should fail (and the new "falls back" test should fail)**

```bash
uv run pytest tests/test_jobs_api14_adapter.py::test_is_configured_falls_back_to_rapidapi_key tests/test_jobs_api14_adapter.py::test_is_configured_dedicated_var_wins_over_canonical -v 2>&1 | tail -10
```

Expected: both fail (the implementation doesn't yet do fallback).

- [ ] **Step 2.3: Refactor `JobsApi14Adapter` to use the resolver**

Edit `src/findajob/fetchers/adapters/jobs_api14.py`. Replace lines 31-37 (the `is_configured` + the start of `fetch`):

Current:

```python
    def is_configured(self) -> bool:
        return bool(os.environ.get("JOBS_API14_KEY", ""))

    def fetch(self, queries: list[str]) -> list[dict]:
        api_key = os.environ.get("JOBS_API14_KEY", "")
        if not api_key:
            log_event("jobsapi_error", error="JOBS_API14_KEY not set in .env")
            return []
```

Replace with:

```python
    def is_configured(self) -> bool:
        return bool(self._api_key())

    def _api_key(self) -> str:
        return resolve_rapidapi_key("RAPIDAPI_KEY", "JOBS_API14_KEY")

    def fetch(self, queries: list[str]) -> list[dict]:
        api_key = self._api_key()
        if not api_key:
            log_event("jobsapi_error", error="No RAPIDAPI_KEY or JOBS_API14_KEY set in .env")
            return []
```

Then locate the `live_test()` method (around line 60) and replace its first env-var read:

Current:

```python
    def live_test(self, queries: list[str]) -> LiveTestResult:
        api_key = os.environ.get("JOBS_API14_KEY", "")
        if not api_key:
            return LiveTestResult(
                ok=False,
                bucket="auth",
                per_query=[],
                auth_error="No API key configured.",
            )
```

Replace with:

```python
    def live_test(self, queries: list[str]) -> LiveTestResult:
        api_key = self._api_key()
        if not api_key:
            return LiveTestResult(
                ok=False,
                bucket="auth",
                per_query=[],
                auth_error="No API key configured.",
            )
```

Add the import at the top of the file (alongside the existing imports):

```python
from ._keys import resolve_rapidapi_key
```

- [ ] **Step 2.4: Run all jobs_api14 tests**

```bash
uv run pytest tests/test_jobs_api14_adapter.py -v 2>&1 | tail -25
```

Expected: all pass (existing tests continue to work because `JOBS_API14_KEY`-only stacks still resolve via fallback; new fallback tests pass).

- [ ] **Step 2.5: Commit**

```bash
git add src/findajob/fetchers/adapters/jobs_api14.py tests/test_jobs_api14_adapter.py
git commit -m "refactor(adapters): #414 JobsApi14Adapter uses shared RAPIDAPI_KEY resolver

Reads canonical RAPIDAPI_KEY first, falls back to legacy JOBS_API14_KEY for
existing stacks. Updates the inverse test that asserted no-fallback (the
#408 design); the new design IS fallback."
```

---

## Task 3: Refactor `JSearchAdapter` to use shared resolver

**Files:**
- Modify: `src/findajob/fetchers/adapters/jsearch.py:30-36`
- Modify: `tests/test_jsearch_adapter.py` (whichever test asserts no-fallback — locate via grep)

- [ ] **Step 3.1: Locate any existing no-fallback assertion in JSearch tests**

```bash
grep -n "fall_back\|not.*RAPIDAPI\|RAPIDAPI.*KEY" tests/test_jsearch_adapter.py
```

If a `test_is_configured_does_not_fall_back_to_rapidapi_key` (or similar) exists, edit it the same way as Task 2.1. If absent, skip ahead — JSearchAdapter probably never had the explicit no-fallback test (only JobsApi14Adapter did, because of the env_migrate path).

- [ ] **Step 3.2: Add fallback test to `tests/test_jsearch_adapter.py`**

Add at end of `tests/test_jsearch_adapter.py`:

```python


def test_is_configured_falls_back_to_rapidapi_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Shared RAPIDAPI_KEY backs JSearchAdapter when JSEARCH_API_KEY is unset (#414)."""
    monkeypatch.delenv("JSEARCH_API_KEY", raising=False)
    monkeypatch.setenv("RAPIDAPI_KEY", "shared-1234")
    assert JSearchAdapter().is_configured() is True


def test_is_configured_canonical_wins_over_dedicated(monkeypatch: pytest.MonkeyPatch) -> None:
    """RAPIDAPI_KEY is canonical; if both set, RAPIDAPI_KEY wins (#414)."""
    monkeypatch.setenv("RAPIDAPI_KEY", "shared-1234")
    monkeypatch.setenv("JSEARCH_API_KEY", "legacy-1234")
    assert JSearchAdapter().is_configured() is True
```

- [ ] **Step 3.3: Run new tests — they should fail**

```bash
uv run pytest tests/test_jsearch_adapter.py::test_is_configured_falls_back_to_rapidapi_key tests/test_jsearch_adapter.py::test_is_configured_canonical_wins_over_dedicated -v 2>&1 | tail -10
```

Expected: both fail.

- [ ] **Step 3.4: Refactor `JSearchAdapter` to use the resolver**

Edit `src/findajob/fetchers/adapters/jsearch.py`. Replace lines 30-36:

Current:

```python
    def is_configured(self) -> bool:
        return bool(os.environ.get("JSEARCH_API_KEY", ""))

    def fetch(self, queries: list[str]) -> list[dict]:
        api_key = os.environ.get("JSEARCH_API_KEY", "")
        if not api_key:
            log_event("jsearch_error", error="JSEARCH_API_KEY not set in .env")
            return []
```

Replace with:

```python
    def is_configured(self) -> bool:
        return bool(self._api_key())

    def _api_key(self) -> str:
        return resolve_rapidapi_key("RAPIDAPI_KEY", "JSEARCH_API_KEY")

    def fetch(self, queries: list[str]) -> list[dict]:
        api_key = self._api_key()
        if not api_key:
            log_event("jsearch_error", error="No RAPIDAPI_KEY or JSEARCH_API_KEY set in .env")
            return []
```

Locate `live_test()` (around line 76) and replace its first env-var read:

Current:

```python
    def live_test(self, queries: list[str]) -> LiveTestResult:
        api_key = os.environ.get("JSEARCH_API_KEY", "")
```

Replace with:

```python
    def live_test(self, queries: list[str]) -> LiveTestResult:
        api_key = self._api_key()
```

Add import at the top:

```python
from ._keys import resolve_rapidapi_key
```

- [ ] **Step 3.5: Run all jsearch tests**

```bash
uv run pytest tests/test_jsearch_adapter.py -v 2>&1 | tail -25
```

Expected: all pass.

- [ ] **Step 3.6: Commit**

```bash
git add src/findajob/fetchers/adapters/jsearch.py tests/test_jsearch_adapter.py
git commit -m "refactor(adapters): #414 JSearchAdapter uses shared RAPIDAPI_KEY resolver

Same shape as JobsApi14Adapter: canonical-first, dedicated-var fallback.
Existing tester stacks with only JSEARCH_API_KEY set continue to work."
```

---

## Task 4: New `JobsApi14IndeedAdapter`

**Files:**
- Create: `src/findajob/fetchers/adapters/jobs_api14_indeed.py`
- Create: `tests/test_jobs_api14_indeed_adapter.py`

Indeed endpoint shape (confirmed from operator-pasted Postman collection in #414 comments): `GET /v2/indeed/search` with params `query`, `location`, `countryCode` (required), `sortType`, `radius`, `radiusType`, `token`. Response: `data: [{title, applyUrl, company.name, location.location, description, id, ...}]`. Returns 20 jobs/page. Inline `description` (no separate `/get` call needed).

To compensate for missing recency / experience-level / employment-type filters, the adapter:
1. Sends `sortType=date` (most-recent first).
2. Sends `countryCode=us` + `location="United States"`.
3. Applies a post-fetch title regex filter — drops rows whose `title` doesn't match the operator-tunable allow-pattern. Reuses the same kind of logic as `scorer_prefilter` Stage 1 but as inclusion, not rejection.

For PR1 the post-fetch filter is built in but the regex is hardcoded conservatively (a small allow-list pattern matching `engineer`, `manager`, `director`, `lead`, `architect`, `analyst`, `program`, `operations`, `infrastructure`, `data center`, `hardware`, `npi` — case-insensitive). A follow-up issue can move it to a config file once the right shape is clear.

- [ ] **Step 4.1: Write the failing tests**

Create `tests/test_jobs_api14_indeed_adapter.py`:

```python
"""Tests for JobsApi14IndeedAdapter — restored Indeed coverage (#414)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from findajob.fetchers.adapters.jobs_api14_indeed import JobsApi14IndeedAdapter


@pytest.fixture(autouse=True)
def _scrub_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("RAPIDAPI_KEY", "JOBS_API14_KEY", "JSEARCH_API_KEY"):
        monkeypatch.delenv(var, raising=False)


def test_class_attributes() -> None:
    adapter = JobsApi14IndeedAdapter()
    assert adapter.name == "jobs-api14-indeed"
    assert adapter.display_name == "Jobs API — Indeed (jobs-api14)"
    assert adapter.source_label == "jobsapi_indeed"  # matches retired-but-not-purged DB rows
    assert adapter.required_env_vars == ("JOBS_API14_KEY",)


def test_is_configured_with_canonical_rapidapi_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RAPIDAPI_KEY", "shared-1234")
    assert JobsApi14IndeedAdapter().is_configured() is True


def test_is_configured_with_dedicated_jobs_api14_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JOBS_API14_KEY", "legacy-1234")
    assert JobsApi14IndeedAdapter().is_configured() is True


def test_is_configured_false_when_unset() -> None:
    assert JobsApi14IndeedAdapter().is_configured() is False


def test_fetch_returns_empty_when_unconfigured() -> None:
    assert JobsApi14IndeedAdapter().fetch(["data center engineer"]) == []


def test_fetch_hits_indeed_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JOBS_API14_KEY", "test-key")
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = {"hasError": False, "data": []}
    fake_response.raise_for_status.return_value = None

    with patch("findajob.fetchers.adapters.jobs_api14_indeed.requests.get", return_value=fake_response) as mock_get:
        JobsApi14IndeedAdapter().fetch(["data center engineer"])

    args, kwargs = mock_get.call_args
    assert args[0] == "https://jobs-api14.p.rapidapi.com/v2/indeed/search"
    assert kwargs["headers"]["x-rapidapi-host"] == "jobs-api14.p.rapidapi.com"
    assert kwargs["headers"]["x-rapidapi-key"] == "test-key"
    assert kwargs["params"]["query"] == "data center engineer"
    assert kwargs["params"]["sortType"] == "date"
    assert kwargs["params"]["countryCode"] == "us"
    assert kwargs["params"]["location"] == "United States"


def test_fetch_parses_indeed_response_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JOBS_API14_KEY", "test-key")
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.raise_for_status.return_value = None
    fake_response.json.return_value = {
        "hasError": False,
        "data": [
            {
                "id": "abc123",
                "title": "Data Center Engineer",
                "company": {"name": "Acme Corp", "addresses": [], "image": ""},
                "location": {"country": "United States", "countryCode": "US", "location": "Reston, VA"},
                "applyUrl": "https://example.com/apply/abc123",
                "description": "Job description body...",
            },
        ],
        "meta": {"count": 1, "nextToken": "tok456", "position": 0},
    }

    with patch("findajob.fetchers.adapters.jobs_api14_indeed.requests.get", return_value=fake_response):
        rows = JobsApi14IndeedAdapter().fetch(["data center"])

    assert len(rows) == 1
    row = rows[0]
    assert row["title"] == "Data Center Engineer"
    assert row["company"] == "Acme Corp"
    assert row["location"] == "Reston, VA"
    assert row["url"] == "https://example.com/apply/abc123"
    assert row["api_id"] == "abc123"
    assert row["source"] == "jobsapi_indeed"
    assert row["query"] == "data center"
    assert row["description"] == "Job description body..."  # inline JD


def test_fetch_drops_rows_with_no_title_or_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JOBS_API14_KEY", "test-key")
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.raise_for_status.return_value = None
    fake_response.json.return_value = {
        "hasError": False,
        "data": [
            {"id": "x", "title": "", "company": {"name": "A"}, "location": {"location": "X"}, "applyUrl": "u", "description": "d"},
            {"id": "y", "title": "Engineer", "company": {"name": "A"}, "location": {"location": "X"}, "applyUrl": "", "description": "d"},
            {"id": "z", "title": "Engineer", "company": {"name": "A"}, "location": {"location": "X"}, "applyUrl": "u", "description": "d"},
        ],
        "meta": {"count": 3},
    }

    with patch("findajob.fetchers.adapters.jobs_api14_indeed.requests.get", return_value=fake_response):
        rows = JobsApi14IndeedAdapter().fetch(["q"])

    # Only the third row should survive (has both title and url)
    assert len(rows) == 1
    assert rows[0]["api_id"] == "z"


def test_fetch_post_filter_drops_titles_outside_allowlist(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JOBS_API14_KEY", "test-key")
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.raise_for_status.return_value = None
    fake_response.json.return_value = {
        "hasError": False,
        "data": [
            {"id": "1", "title": "Cashier", "company": {"name": "A"}, "location": {"location": "X"}, "applyUrl": "u1", "description": "d"},
            {"id": "2", "title": "Senior Data Center Engineer", "company": {"name": "A"}, "location": {"location": "X"}, "applyUrl": "u2", "description": "d"},
            {"id": "3", "title": "Operations Manager", "company": {"name": "A"}, "location": {"location": "X"}, "applyUrl": "u3", "description": "d"},
            {"id": "4", "title": "Bartender", "company": {"name": "A"}, "location": {"location": "X"}, "applyUrl": "u4", "description": "d"},
        ],
        "meta": {"count": 4},
    }

    with patch("findajob.fetchers.adapters.jobs_api14_indeed.requests.get", return_value=fake_response):
        rows = JobsApi14IndeedAdapter().fetch(["q"])

    titles = [r["title"] for r in rows]
    assert "Senior Data Center Engineer" in titles
    assert "Operations Manager" in titles
    assert "Cashier" not in titles
    assert "Bartender" not in titles


def test_fetch_handles_429_with_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JOBS_API14_KEY", "test-key")
    rate_limited = MagicMock(status_code=429, headers={"Retry-After": "1"})
    rate_limited.json.return_value = {"hasError": False, "data": []}
    success = MagicMock(status_code=200, headers={})
    success.json.return_value = {"hasError": False, "data": []}
    success.raise_for_status.return_value = None

    with (
        patch("findajob.fetchers.adapters.jobs_api14_indeed.requests.get", side_effect=[rate_limited, success]) as mock_get,
        patch("findajob.fetchers.adapters.jobs_api14_indeed.time.sleep") as mock_sleep,
    ):
        JobsApi14IndeedAdapter().fetch(["engineer"])

    assert mock_get.call_count == 2
    assert mock_sleep.called


def test_fetch_handles_haserror_response(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JOBS_API14_KEY", "test-key")
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.raise_for_status.return_value = None
    fake_response.json.return_value = {"hasError": True, "errors": [{"message": "boom"}], "data": []}

    with patch("findajob.fetchers.adapters.jobs_api14_indeed.requests.get", return_value=fake_response):
        rows = JobsApi14IndeedAdapter().fetch(["engineer"])

    assert rows == []


def test_live_test_auth_failure_with_no_key() -> None:
    result = JobsApi14IndeedAdapter().live_test(["engineer"])
    assert result.ok is False
    assert result.bucket == "auth"


def test_live_test_success_returns_per_query_counts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JOBS_API14_KEY", "test-key")
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = {
        "hasError": False,
        "data": [
            {"id": "1", "title": "Engineer", "company": {"name": "A"}, "location": {"location": "X"}, "applyUrl": "u", "description": "d"},
        ],
    }

    with patch("findajob.fetchers.adapters.jobs_api14_indeed.requests.get", return_value=fake_response):
        result = JobsApi14IndeedAdapter().live_test(["engineer"])

    assert result.ok is True
    assert result.bucket == "success"
    assert len(result.per_query) == 1
    assert result.per_query[0].count == 1
```

- [ ] **Step 4.2: Run tests to verify they fail**

```bash
uv run pytest tests/test_jobs_api14_indeed_adapter.py -v 2>&1 | tail -10
```

Expected: `ModuleNotFoundError: No module named 'findajob.fetchers.adapters.jobs_api14_indeed'`.

- [ ] **Step 4.3: Implement `JobsApi14IndeedAdapter`**

Create `src/findajob/fetchers/adapters/jobs_api14_indeed.py`:

```python
"""JobsApi14IndeedAdapter — restored Indeed coverage via jobs-api14 (#414).

Indeed endpoint exposes no recency / experience-level / employment-type
filters (unlike LinkedIn), so the legacy fetcher (retired pre-#408) returned
~89% off-target rows. This adapter compensates with three knobs:

1. sortType=date — most-recent first, daily triage captures fresh jobs.
2. countryCode=us + location="United States" — geo-narrow.
3. Adapter-side title regex post-filter — inclusion allowlist before storing.

Per-page count is 20 (vs LinkedIn's 10). Description is inline in the
search response, so no separate /v2/linkedin/get-equivalent call needed.

Shares JOBS_API14_KEY / RAPIDAPI_KEY with `JobsApi14Adapter` via the
shared resolver (#414); both adapters are subscriptions on the same
RapidAPI account.
"""

from __future__ import annotations

import re
import time
from typing import ClassVar

import requests

from findajob.cleaning import clean_company, clean_title
from findajob.utils import log_event

from ._keys import resolve_rapidapi_key
from .base import LiveTestResult, QueryResult

__all__ = ("JobsApi14IndeedAdapter",)


# Title-allowlist regex — case-insensitive. Tuned for ops / infrastructure /
# program-mgmt / NPI / hardware / data-center title families. Tighter than
# scorer_prefilter Stage 1's REJECT pattern; this is INCLUSION, applied
# pre-storage to compensate for Indeed's missing server-side filters.
_TITLE_ALLOW_PATTERN: re.Pattern[str] = re.compile(
    r"\b("
    r"engineer|manager|director|lead|architect|analyst|program|"
    r"operations|infrastructure|data\s*center|hardware|npi|"
    r"technician|specialist|coordinator|supervisor|administrator"
    r")\b",
    re.IGNORECASE,
)


class JobsApi14IndeedAdapter:
    """jobs-api14 /v2/indeed/search adapter, tuned for the missing-filter problem."""

    name: ClassVar[str] = "jobs-api14-indeed"
    display_name: ClassVar[str] = "Jobs API — Indeed (jobs-api14)"
    source_label: ClassVar[str] = "jobsapi_indeed"  # preserves DB row continuity
    required_env_vars: ClassVar[tuple[str, ...]] = ("JOBS_API14_KEY",)

    _ENDPOINT: ClassVar[str] = "https://jobs-api14.p.rapidapi.com/v2/indeed/search"
    _HOST: ClassVar[str] = "jobs-api14.p.rapidapi.com"

    def is_configured(self) -> bool:
        return bool(self._api_key())

    def _api_key(self) -> str:
        return resolve_rapidapi_key("RAPIDAPI_KEY", "JOBS_API14_KEY")

    def fetch(self, queries: list[str]) -> list[dict]:
        api_key = self._api_key()
        if not api_key:
            log_event("jobsapi_indeed_error", error="No RAPIDAPI_KEY or JOBS_API14_KEY set in .env")
            return []

        headers = self._headers(api_key)
        rows: list[dict] = []
        last_idx = len(queries) - 1
        for i, query in enumerate(queries):
            data = self._call_with_retry(headers, self._params(query), query)
            if data is None:
                continue
            new_rows = self._parse_rows(data, query)
            rows.extend(new_rows)
            log_event("jobsapi_indeed_fetched", query=query, count=len(new_rows))
            if i < last_idx:
                time.sleep(0.6)
        return rows

    def live_test(self, queries: list[str]) -> LiveTestResult:
        api_key = self._api_key()
        if not api_key:
            return LiveTestResult(
                ok=False,
                bucket="auth",
                per_query=[],
                auth_error="No API key configured.",
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

            # Apply the same post-filter so live-test counts reflect what would actually ingest
            parsed = self._parse_rows(data, query)
            per_query.append(QueryResult(query=query, count=len(parsed)))

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

    def _params(self, query: str) -> dict[str, str]:
        # Indeed has no datePosted / experienceLevels / employmentTypes filters.
        # Compensating: sortType=date (recency-as-filter) + countryCode=us +
        # location filter. The remaining off-target rows are dropped by the
        # title regex post-filter in _parse_rows.
        return {
            "query": query,
            "location": "United States",
            "countryCode": "us",
            "sortType": "date",
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
                log_event("jobsapi_indeed_error", query=query, errors=data.get("errors"))
                return None
            return data
        except requests.RequestException as e:
            log_event("jobsapi_indeed_error", query=query, error=str(e))
            return None

    def _parse_rows(self, data: dict, query: str) -> list[dict]:
        rows: list[dict] = []
        for job in data.get("data", []) or []:
            raw_title = job.get("title", "")
            title = clean_title(raw_title)
            if not title:
                continue
            # Inclusion post-filter — drop titles outside the allowlist
            if not _TITLE_ALLOW_PATTERN.search(title):
                continue

            raw_company = job.get("company", {})
            if isinstance(raw_company, dict):
                raw_company = raw_company.get("name", "")
            company = clean_company(raw_company)

            loc = job.get("location", "")
            location = loc.get("location", "") if isinstance(loc, dict) else loc

            url = job.get("applyUrl", "")
            if not url:
                continue

            rows.append(
                {
                    "title": title,
                    "company": company,
                    "location": location,
                    "url": url,
                    "api_id": str(job.get("id", "")),
                    "source": self.source_label,
                    "query": query,
                    "description": job.get("description", ""),  # inline JD
                }
            )
        return rows
```

- [ ] **Step 4.4: Run all new adapter tests**

```bash
uv run pytest tests/test_jobs_api14_indeed_adapter.py -v 2>&1 | tail -25
```

Expected: all pass.

- [ ] **Step 4.5: Commit**

```bash
git add src/findajob/fetchers/adapters/jobs_api14_indeed.py tests/test_jobs_api14_indeed_adapter.py
git commit -m "feat(adapters): #414 restore JobsApi14IndeedAdapter

Brings Indeed coverage back via jobs-api14 /v2/indeed/search. Compensates
for the missing recency/level/type filters (the original retirement
reason) with sortType=date, geo-narrow, and an inclusion title regex
applied pre-storage. Inline JD ingestion (no separate /get call needed),
20 jobs/page (2x LinkedIn), source_label='jobsapi_indeed' preserves
historical DB rows."
```

---

## Task 5: Register `JobsApi14IndeedAdapter` in `REGISTERED_ADAPTERS`

**Files:**
- Modify: `src/findajob/fetchers/adapters/registry.py`
- Modify: `tests/test_adapter_registry.py` (extend with assertion that the new adapter is registered)

- [ ] **Step 5.1: Add registration test**

Add to `tests/test_adapter_registry.py` (at end of file):

```python


def test_jobs_api14_indeed_adapter_is_registered() -> None:
    """JobsApi14IndeedAdapter (#414) ships in the registry alongside its sibling."""
    from findajob.fetchers.adapters.jobs_api14_indeed import JobsApi14IndeedAdapter
    from findajob.fetchers.adapters.registry import REGISTERED_ADAPTERS

    assert JobsApi14IndeedAdapter in REGISTERED_ADAPTERS
```

- [ ] **Step 5.2: Run new test — should fail**

```bash
uv run pytest tests/test_adapter_registry.py::test_jobs_api14_indeed_adapter_is_registered -v 2>&1 | tail -5
```

Expected: AssertionError.

- [ ] **Step 5.3: Register the adapter**

Edit `src/findajob/fetchers/adapters/registry.py`. After line 13 (`from .jsearch import JSearchAdapter`), add:

```python
from .jobs_api14_indeed import JobsApi14IndeedAdapter
```

Then update the `REGISTERED_ADAPTERS` list (lines 15-18):

Current:

```python
REGISTERED_ADAPTERS: list[type[JobSourceAdapter]] = [
    JobsApi14Adapter,  # type: ignore[list-item]
    JSearchAdapter,  # type: ignore[list-item]
]
```

Replace with:

```python
REGISTERED_ADAPTERS: list[type[JobSourceAdapter]] = [
    JobsApi14Adapter,  # type: ignore[list-item]
    JobsApi14IndeedAdapter,  # type: ignore[list-item]
    JSearchAdapter,  # type: ignore[list-item]
]
```

- [ ] **Step 5.4: Run registry tests**

```bash
uv run pytest tests/test_adapter_registry.py -v 2>&1 | tail -15
```

Expected: all pass.

- [ ] **Step 5.5: Commit**

```bash
git add src/findajob/fetchers/adapters/registry.py tests/test_adapter_registry.py
git commit -m "feat(adapters): #414 register JobsApi14IndeedAdapter

Now stacks with 'jobs-api14-indeed' in active_sources.txt will pick up
the new adapter automatically. Default behavior (no active_sources.txt)
unchanged — still falls back to ['jobs-api14'] only."
```

---

## Task 6: Update `data/.env.example` and `docs/setup/api-keys.md`

**Files:**
- Modify: `data/.env.example`
- Modify: `docs/setup/api-keys.md`

- [ ] **Step 6.1: Update `data/.env.example`**

Read current state first:

```bash
grep -B1 -A1 "JOBS_API14_KEY\|JSEARCH_API_KEY" data/.env.example
```

Then edit `data/.env.example`. Find the section with `JOBS_API14_KEY=` and `# JSEARCH_API_KEY=`. Replace with (keeping any surrounding context):

```
# RapidAPI account-level key. ONE key authorizes every API you've subscribed
# to under your RapidAPI account (jobs-api14, JSearch, etc). New stacks set
# only this; legacy stacks may still set the per-adapter vars below as
# fallback (#414).
RAPIDAPI_KEY=

# Legacy per-adapter env vars (#408). Still read as fallback when
# RAPIDAPI_KEY is unset. Don't set these unless you genuinely have separate
# RapidAPI accounts for different APIs (rare).
# JOBS_API14_KEY=
# JSEARCH_API_KEY=
```

(If your file structure has a different layout, preserve it — only the keys section changes shape.)

- [ ] **Step 6.2: Update `docs/setup/api-keys.md`**

Read the current shape:

```bash
grep -B2 -A4 "JOBS_API14_KEY\|JSEARCH_API_KEY\|RAPIDAPI" docs/setup/api-keys.md
```

Edit the table that lists per-adapter env vars (around the `JOBS_API14_KEY` / `JSEARCH_API_KEY` rows) to add a row at top:

```markdown
| Env var | Purpose | Notes |
|---|---|---|
| `RAPIDAPI_KEY` | Canonical RapidAPI account key — covers every API you've subscribed to | New stacks set only this. The two per-adapter vars below are legacy fallbacks (#414). |
```

Update any prose that says "writes it to `data/.env` as `JOBS_API14_KEY`" or "writes it to `data/.env` as `JSEARCH_API_KEY`" to instead say "writes it to `data/.env` as `RAPIDAPI_KEY` — the canonical name covers every RapidAPI feed (#414)."

- [ ] **Step 6.3: Commit**

```bash
git add data/.env.example docs/setup/api-keys.md
git commit -m "docs: #414 document RAPIDAPI_KEY as canonical RapidAPI credential

Per-adapter JOBS_API14_KEY / JSEARCH_API_KEY remain valid as fallbacks
for existing stacks, but new installs use the canonical name."
```

---

## Task 7: Update `CLAUDE.md` Pipeline Context Table

**Files:**
- Modify: `CLAUDE.md` (Pipeline Context Table row for "Job ingestion")

- [ ] **Step 7.1: Locate current row**

```bash
grep -B1 -A2 "Job ingestion" CLAUDE.md | head -20
```

- [ ] **Step 7.2: Update the row**

The current row reads (approximately): "Pluggable via `JobSourceAdapter` (`src/findajob/fetchers/adapters/`); jobs-api14 + JSearch ship in v0.14; per-stack active list in `config/active_sources.txt`. Greenhouse / Ashby / Lever / Gmail still function-style — migration tracked in #410."

Append a sentence:

> "v0.15 adds `JobsApi14IndeedAdapter` (Indeed via jobs-api14 with sortType=date + post-filter, restoring pre-#408 coverage) and consolidates RapidAPI credentials to a shared `RAPIDAPI_KEY` env var (legacy `JOBS_API14_KEY` / `JSEARCH_API_KEY` work as fallbacks) (#414)."

Edit the row in `CLAUDE.md` to include that addition.

- [ ] **Step 7.3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(CLAUDE.md): #414 reflect Indeed restore + shared RAPIDAPI_KEY"
```

---

## Task 8: Update `CHANGELOG.md`

**Files:**
- Modify: `CHANGELOG.md` (the `## [Unreleased]` section)

- [ ] **Step 8.1: Add entries to `## [Unreleased]`**

Edit `CHANGELOG.md`. Replace the existing `## [Unreleased]` line with:

```markdown
## [Unreleased]

### Added
- `JobsApi14IndeedAdapter` — Indeed coverage via jobs-api14 `/v2/indeed/search`. Restores pre-#408 Indeed pulls, tuned with `sortType=date` + adapter-side title-allowlist regex to compensate for the missing recency / experience-level / employment-type filters. 20 jobs/page (2× LinkedIn), inline JD ingestion. `source_label='jobsapi_indeed'` preserves DB row continuity. Active when `'jobs-api14-indeed'` is listed in `config/active_sources.txt` (#414)
- Shared `RAPIDAPI_KEY` env var as the canonical RapidAPI credential. Both `JobsApi14Adapter` and `JSearchAdapter` (and the new Indeed adapter) read it first, falling back to the legacy per-adapter vars (`JOBS_API14_KEY`, `JSEARCH_API_KEY`) if unset. Reflects the reality that RapidAPI uses one account-level key per user, not per-API (#414)

### Migration required
- **Existing stacks pulling next minor:** legacy `JOBS_API14_KEY` / `JSEARCH_API_KEY` continue to work — no action required to keep current adapter configs running. To start using `RAPIDAPI_KEY` as the canonical name, copy the existing legacy var's value to `RAPIDAPI_KEY=` in `data/.env` (operators can also remove the legacy vars once migrated, but they're harmless if left).
- **To enable the new Indeed adapter:** add `jobs-api14-indeed` as a new line in `config/active_sources.txt` and restart the stack. No new credentials needed (shares jobs-api14's account).
```

- [ ] **Step 8.2: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs(changelog): #414 add Indeed restore + shared RAPIDAPI_KEY entries"
```

---

## Whole-feature verification gate

These checks gate readiness for PR open. Each must pass before pushing.

- [ ] **Step W1: Full test suite**

```bash
uv run pytest tests/ -q 2>&1 | tail -5
```

Expected: all pass, exit 0. If any pre-existing test now fails, audit whether it was relying on the old "no fallback" behavior (`grep -rn "RAPIDAPI" tests/` to find candidates).

- [ ] **Step W2: Linting**

```bash
uv run ruff check src/ tests/ 2>&1 | tail -3
uv run ruff format --check src/ tests/ 2>&1 | tail -3
```

Expected: both exit 0. If `ruff format --check` flags files, run `uv run ruff format src/ tests/` and recommit (per memory rule `feedback_ruff_format_check`).

- [ ] **Step W3: Type check**

```bash
uv run mypy src/ 2>&1 | tail -3
```

Expected: `Success: no issues found`.

- [ ] **Step W4: Verify the new adapter is wired into `iter_configured_adapters()` end-to-end**

Run a one-shot smoke check that `iter_configured_adapters()` yields the Indeed adapter when (a) `RAPIDAPI_KEY` is set, (b) `active_sources.txt` lists `jobs-api14-indeed`:

```bash
RAPIDAPI_KEY=fake uv run python -c "
import os, tempfile, pathlib
from findajob.fetchers.adapters import registry

# Write a temp active_sources.txt
tmpdir = pathlib.Path(tempfile.mkdtemp())
asf = tmpdir / 'active_sources.txt'
asf.write_text('jobs-api14-indeed\njsearch\n')

# Monkeypatch registry to read our temp file
orig = registry._active_sources_path
registry._active_sources_path = lambda: asf
try:
    instances = list(registry.iter_configured_adapters())
    names = sorted(i.name for i in instances)
    print('Active adapters:', names)
    assert 'jobs-api14-indeed' in names, 'Indeed adapter not active'
    assert 'jsearch' in names, 'JSearch adapter not active'
finally:
    registry._active_sources_path = orig
"
```

Expected: `Active adapters: ['jobs-api14-indeed', 'jsearch']` (and assertions pass — exit 0).

- [ ] **Step W5: Commit log review**

```bash
git log origin/main..HEAD --oneline
```

Expected: 8 small commits (one per task). Each commit message starts with `feat(...)`, `refactor(...)`, or `docs(...)`. Each commit references #414. Audit that every change is intentional — no accidentally staged scratch files.

---

## PR open

- [ ] **Step PR1: Push branch**

```bash
git push -u origin feat/414-shared-key-and-indeed
```

- [ ] **Step PR2: Open the PR**

```bash
gh pr create --title "feat(adapters): #414 shared RAPIDAPI_KEY + JobsApi14IndeedAdapter restore" --body "$(cat <<'EOF'
## Summary

- Adds shared `RAPIDAPI_KEY` env var as the canonical RapidAPI credential. Both `JobsApi14Adapter` and `JSearchAdapter` now read it first, fall back to legacy `JOBS_API14_KEY` / `JSEARCH_API_KEY` for existing stacks. Reflects the reality that RapidAPI uses one account-level key per user, not per-API.
- Restores `JobsApi14IndeedAdapter` (`source_label='jobsapi_indeed'`, preserving DB row continuity) — Indeed coverage via jobs-api14 `/v2/indeed/search`. Tuned with `sortType=date` + adapter-side title-allowlist regex to compensate for the missing recency/level/type filters that drove the original retirement.

Closes part of #414. Multi-page knobs and JSearch billing-probe follow in subsequent PRs.

## Test plan

- [ ] `uv run pytest tests/ -q` — full suite passes
- [ ] `uv run ruff check src/ tests/` — clean
- [ ] `uv run ruff format --check src/ tests/` — clean
- [ ] `uv run mypy src/` — clean
- [ ] Existing tester stacks (alice, papa, dave, judy, tango) — no behavior change, since `JOBS_API14_KEY` fallback covers them.
- [ ] After merge + deploy on operator's stack: write `config/active_sources.txt` with `jobs-api14`, `jobs-api14-indeed`, `jsearch`; set `RAPIDAPI_KEY` from existing `JOBS_API14_KEY` value via `sudo sed -i`; restart stack; confirm `pipeline.jsonl` shows `jobsapi_indeed_fetched` and `jsearch_fetched` events on next triage run.

## Migration required

- Existing stacks' legacy env vars keep working — no required action to maintain current behavior.
- To use new canonical `RAPIDAPI_KEY`, copy legacy value into `RAPIDAPI_KEY=` line in `data/.env`.
- To enable Indeed: add `jobs-api14-indeed` line to `config/active_sources.txt`, restart stack.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)" --label migration-required
```

Add the `migration-required` label per CLAUDE.md release-notes pipeline.

- [ ] **Step PR3: Save PR URL for the deploy step**

Note the PR URL from the `gh pr create` output. After merge, the deploy step (write `active_sources.txt` + add `RAPIDAPI_KEY` on operator's stack) is a separate operation — not included in this plan because it's an operational follow-up, not code.

---

## Documentation Impact

| Surface | What changes | Task |
|---|---|---|
| `data/.env.example` | New `RAPIDAPI_KEY=` line as canonical; per-adapter vars commented as legacy fallback | Task 6 |
| `docs/setup/api-keys.md` | New canonical-credential row at top of env-var table; prose updated to recommend `RAPIDAPI_KEY` | Task 6 |
| `CLAUDE.md` (Pipeline Context Table → Job ingestion row) | Note Indeed restore + shared key | Task 7 |
| `CHANGELOG.md` | Two `### Added` entries + `### Migration required` entry under `## [Unreleased]` | Task 8 |
| Per-adapter docstrings (`jobs_api14.py`, `jsearch.py`, `jobs_api14_indeed.py`) | Reflect the shared-key model where the docstring discusses credentials | Done inline in Tasks 2/3/4 |
| `docs/superpowers/specs/...` | None — this work has no separate spec doc; the design lives in #414 issue comments + this plan | n/a |

---

## Self-review checklist

Map every spec/requirement section to its implementing task:

| Requirement (from #414 design comments) | Implementing task |
|---|---|
| Shared RapidAPI key, canonical name `RAPIDAPI_KEY` | Tasks 1, 2, 3 |
| Per-adapter env vars stay valid as fallback | Tasks 2, 3 (test coverage) |
| New `JobsApi14IndeedAdapter` with `sortType=date` | Task 4 |
| Adapter-side title regex post-filter (89%-rejection killer) | Task 4 (`_parse_rows()` + `test_fetch_post_filter_drops_titles_outside_allowlist`) |
| Inline JD ingestion (no separate `/get` call) | Task 4 (`description` in row dict) |
| `source_label='jobsapi_indeed'` to preserve DB continuity | Task 4 (assertion + class attribute) |
| Adapter registered in `REGISTERED_ADAPTERS` | Task 5 |
| `active_sources.txt` is the on/off toggle (already exists; no code change needed) | n/a — existing registry behavior unchanged |
| Operator-stack `RAPIDAPI_KEY` + `active_sources.txt` deployment | NOT in PR — explicit deploy step in Step PR2 test plan + post-merge ops |
| Backwards compat for tester stacks (no behavior change without their action) | Tasks 2, 3, 5 (default `_DEFAULT_ACTIVE_SOURCES = ['jobs-api14']` unchanged) |
| Picker UX simplification (one credential field) | OUT OF SCOPE — separate issue (#410-adjacent) |
| Multi-page on `JobsApi14Adapter` (LinkedIn nextToken loop) | OUT OF SCOPE — `PR2` later |
| `num_pages` configurability on `JSearchAdapter` | OUT OF SCOPE — `PR3` later (pending billing probe) |
| Bing endpoint as separate adapter | OUT OF SCOPE — separate issue |

All in-scope items have a task. Out-of-scope items are explicitly noted as deferred and have a path forward.

---

## Notes for the implementer

- Branch off `origin/main`, NOT local `main` — see memory `feedback_git_branch_off_origin`.
- Don't print `data/.env` values to chat at any point — see memory `feedback_never_print_secrets`. The deploy step (Step PR2 test plan) uses `sudo sed -i` patterns specifically for this reason.
- Run `ruff check` AND `ruff format --check` BOTH locally before push — CI runs both, see memory `feedback_ruff_format_check`.
- This PR is `migration-required` even though tester stacks need no action; the new canonical-name path is the migration. Releases notes pipeline depends on this label.
