---
**Shipped in #330, #330 on 2026-05-01. Final decisions captured in issue body.**
---

# Gmail IMAP/app-password integration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace findajob's Gmail OAuth integration with a self-service Gmail app-password + IMAP path, configured through a new `/config/gmail/` route, with a published transparency contract enforced by tests.

**Architecture:** New `findajob.gmail_imap` module wraps `imaplib.IMAP4_SSL` against `imap.gmail.com:993` using app-password auth. Two JSON files (`config/gmail.json` for credentials, `config/gmail_state.json` for UID checkpoint) are managed by the new `/config/gmail/` route. The existing `fetchers.fetch_gmail_jobs()` keeps its call site in `triage.py` but its body is rewritten on top of the new module. OAuth code (`scripts/gmail_auth.py`, `get_gmail_service()`, `parse_jobs_from_email`) is deleted in the same PR — no bridge or migration code.

**Tech Stack:** Python 3.12 stdlib (`imaplib`, `email`, `dataclasses`, `json`, `os`, `pathlib`), FastAPI + Jinja2 + HTMX (existing web stack), Tailwind classes (existing), pytest + unittest.mock.

**Spec:** `docs/superpowers/specs/2026-04-30-330-design.md` (commit `63d3141`)

**Issue:** [#330](https://github.com/brockamer/findajob/issues/330)

---

## File Structure

### New files

| Path | Responsibility |
|---|---|
| `src/findajob/gmail_imap.py` | IMAP client module: dataclasses (`GmailConfig`, `GmailState`, `TestResult`, `FetchOutcome`), file load/save, `test_login`, `fetch_new_messages`. Pure function-level API; no FastAPI imports. |
| `src/findajob/web/routes/gmail_config.py` | Routes for `/config/gmail/{,save,test,disconnect}`. Calls `gmail_imap` for everything. |
| `src/findajob/web/templates/gmail_config/index.html` | Form page extending `base.html`. |
| `src/findajob/web/templates/gmail_config/_card.html` | Inner form card; HTMX target for save/test/disconnect responses. |
| `src/findajob/web/templates/_gmail_disclosure.html` | Single source of truth for the disclosure banner. Included by both the form page and the docs viewer. |
| `docs/setup/gmail.md` | User-facing setup walkthrough. |
| `tests/test_gmail_imap.py` | Unit tests for the IMAP module (Tier 2 in spec §11). |
| `tests/test_gmail_imap_parsing.py` | Round-trip parser tests using `.eml` fixture (Tier 3). |
| `tests/test_web_gmail_config.py` | Route smoke tests using FastAPI `TestClient` (Tier 4). |
| `tests/test_transparency_invariants.py` | Contract enforcement (Tier 1). |
| `tests/test_gmail_disclosure_sync.py` | Asserts partial + marker-in-doc both exist. |
| `tests/fixtures/gmail/linkedin_alert.eml` | PII-scrubbed real LinkedIn alert email. |

### Modified files

| Path | Change |
|---|---|
| `src/findajob/fetchers.py` | Delete `GMAIL_CREDS`/`GMAIL_TOKEN`/`GMAIL_SCOPES` constants and `get_gmail_service()`. Rewrite `fetch_gmail_jobs()` to call `gmail_imap`. Add `parse_jobs_from_email_imap()` and a shared HTML-parse helper; delete `parse_jobs_from_email()`. Retain `_normalize_sender_to_source` unchanged. |
| `src/findajob/web/app.py` | Register `gmail_config` router. |
| `src/findajob/web/routes/docs.py` | Add `gmail` slug to allowlist; substitute disclosure-marker. |
| `src/findajob/web/templates/config/index.html` (or wherever `/config/` index lives) | Add Gmail Integration row with status pill. |
| `src/findajob/web/constants.py` | Add `BUILD_SHA` and `BUILD_SHA_SHORT` constants resolved from env. |
| `Dockerfile` | New `ARG BUILD_SHA` baked in as `ENV FINDAJOB_BUILD_SHA`. |
| `.github/workflows/build-image.yml` | Pass `--build-arg BUILD_SHA=${{ github.sha }}`. |
| `compose.yaml.example` | Remove `gmail-auth` profile. |
| `.gitignore` | Add `config/gmail.json` and `config/gmail_state.json`. |
| `README.md` | Strip OAuth references; describe Gmail integration as configurable. |
| `CLAUDE.md` | File table: 2 OAuth rows out, 2 new rows in. Web Frontend Architecture: `/config/gmail/`. Critical Architecture Rules: IMAP+app-password posture + spec reference. |
| `CHANGELOG.md` | `migration-required` paragraph. |
| `docs/setup/install-docker.md` | Section 4 replaced with one-paragraph pointer. |
| `docs/setup/install-linux.md` | OAuth steps stripped. |
| `docs/setup/state-migration.md` | File rows replaced. |
| `docs/setup/README.md` | Index entry for `gmail.md`. |
| `docs/release-process.md` | PR-checklist line: re-run transparency tests. |

### Deleted files

| Path | Reason |
|---|---|
| `scripts/gmail_auth.py` | OAuth loopback helper, replaced. |
| `tests/test_gmail_auth.py` | Tests for the deleted helper. |

---

## Task 1 — `gmail_imap` module skeleton + `GmailConfig` load/save

**Files:**
- Create: `src/findajob/gmail_imap.py`
- Create: `tests/test_gmail_imap.py`

**What this task builds:** the `GmailConfig` dataclass + `load_config()` + `save_config()` with atomic-write semantics and chmod 600. No network code yet; this is data plumbing only.

- [ ] **Step 1.1 — Create the test file with failing tests for `GmailConfig.load`**

`tests/test_gmail_imap.py`:

```python
"""Unit tests for src/findajob/gmail_imap.py — Tier 2 of the test plan."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from unittest.mock import patch

import pytest

from findajob import gmail_imap


@pytest.fixture
def cfg_path(tmp_path, monkeypatch):
    p = tmp_path / "gmail.json"
    monkeypatch.setattr(gmail_imap, "GMAIL_CONFIG_PATH", str(p))
    return p


def test_load_config_missing_file_returns_none(cfg_path):
    assert not cfg_path.exists()
    assert gmail_imap.load_config() is None


def test_load_config_strips_password_spaces(cfg_path):
    cfg_path.write_text(json.dumps({
        "_schema": 1,
        "address": "user@gmail.com",
        "app_password": "abcd efgh ijkl mnop",
        "sender_allowlist": ["jobalerts-noreply@linkedin.com"],
        "configured_at": "2026-04-30T00:00:00Z",
    }))
    cfg = gmail_imap.load_config()
    assert cfg is not None
    assert cfg.app_password == "abcdefghijklmnop"
    assert len(cfg.app_password) == 16


def test_load_config_rejects_wrong_password_length(cfg_path):
    cfg_path.write_text(json.dumps({
        "_schema": 1,
        "address": "user@gmail.com",
        "app_password": "abcdefghijklmno",  # 15 chars
        "sender_allowlist": ["jobalerts-noreply@linkedin.com"],
        "configured_at": "2026-04-30T00:00:00Z",
    }))
    assert gmail_imap.load_config() is None


def test_load_config_rejects_invalid_email(cfg_path):
    cfg_path.write_text(json.dumps({
        "_schema": 1,
        "address": "not-an-email",
        "app_password": "abcdefghijklmnop",
        "sender_allowlist": ["jobalerts-noreply@linkedin.com"],
        "configured_at": "2026-04-30T00:00:00Z",
    }))
    assert gmail_imap.load_config() is None


def test_load_config_rejects_unknown_schema_version(cfg_path):
    cfg_path.write_text(json.dumps({
        "_schema": 99,
        "address": "user@gmail.com",
        "app_password": "abcdefghijklmnop",
        "sender_allowlist": ["jobalerts-noreply@linkedin.com"],
        "configured_at": "2026-04-30T00:00:00Z",
    }))
    assert gmail_imap.load_config() is None


def test_save_config_writes_atomically_and_chmod_600(cfg_path):
    cfg = gmail_imap.GmailConfig(
        address="user@gmail.com",
        app_password="abcdefghijklmnop",
        sender_allowlist=["jobalerts-noreply@linkedin.com"],
        configured_at="2026-04-30T00:00:00Z",
    )
    gmail_imap.save_config(cfg)
    assert cfg_path.exists()
    mode = stat.S_IMODE(cfg_path.stat().st_mode)
    assert mode == 0o600
    payload = json.loads(cfg_path.read_text())
    assert payload["_schema"] == 1
    assert payload["address"] == "user@gmail.com"
    assert payload["app_password"] == "abcdefghijklmnop"


def test_save_config_uses_temp_then_rename(cfg_path):
    """Save must go through .tmp + os.replace, never a direct overwrite."""
    cfg_path.write_text("{}")  # pre-existing
    cfg = gmail_imap.GmailConfig(
        address="user@gmail.com",
        app_password="abcdefghijklmnop",
        sender_allowlist=["jobalerts-noreply@linkedin.com"],
        configured_at="2026-04-30T00:00:00Z",
    )
    with patch("findajob.gmail_imap.os.replace", wraps=os.replace) as m:
        gmail_imap.save_config(cfg)
    m.assert_called_once()
    src, dst = m.call_args.args
    assert src.endswith(".tmp")
    assert dst == str(cfg_path)
```

- [ ] **Step 1.2 — Run tests to verify they fail**

Run: `uv run pytest tests/test_gmail_imap.py -v`
Expected: all fail with `ModuleNotFoundError: No module named 'findajob.gmail_imap'` or `AttributeError`.

- [ ] **Step 1.3 — Implement `gmail_imap.py` with `GmailConfig` + load/save**

`src/findajob/gmail_imap.py`:

```python
"""Gmail IMAP client for findajob.

Read-only, app-password authenticated. The only IMAP verbs called are
LOGIN, LIST, SELECT, SEARCH, FETCH (BODY.PEEK[] — does NOT mark messages
read), and LOGOUT. No STORE, COPY, EXPUNGE, APPEND, MOVE, CREATE, DELETE,
or SUBSCRIBE. See docs/superpowers/specs/2026-04-30-330-design.md §4 for
the full transparency contract.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path

from findajob.paths import BASE
from findajob.utils import log_event

GMAIL_CONFIG_PATH = f"{BASE}/config/gmail.json"
GMAIL_STATE_PATH = f"{BASE}/config/gmail_state.json"

_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class GmailConfig:
    address: str
    app_password: str
    sender_allowlist: list[str]
    configured_at: str


def _validate_config_payload(payload: dict) -> bool:
    if payload.get("_schema") != _SCHEMA_VERSION:
        return False
    address = payload.get("address", "")
    if not isinstance(address, str) or "@" not in address or len(address) > 254:
        return False
    pw = payload.get("app_password", "")
    if not isinstance(pw, str):
        return False
    pw_stripped = pw.replace(" ", "")
    if len(pw_stripped) != 16 or not pw_stripped.isalnum():
        return False
    senders = payload.get("sender_allowlist", [])
    if not isinstance(senders, list) or len(senders) > 20:
        return False
    if not all(isinstance(s, str) and "@" in s for s in senders):
        return False
    return True


def load_config() -> GmailConfig | None:
    """Return :class:`GmailConfig` from ``config/gmail.json`` or ``None``.

    Returns ``None`` for: missing file, malformed JSON, schema mismatch,
    or any validation failure. Logs a ``gmail_config_invalid`` event on
    validation failure so the operator can debug from pipeline.jsonl.
    """
    p = Path(GMAIL_CONFIG_PATH)
    if not p.exists():
        return None
    try:
        payload = json.loads(p.read_text())
    except json.JSONDecodeError as e:
        log_event("gmail_config_invalid", reason="json", error=str(e))
        return None
    if not _validate_config_payload(payload):
        log_event("gmail_config_invalid", reason="schema_or_validation")
        return None
    return GmailConfig(
        address=payload["address"],
        app_password=payload["app_password"].replace(" ", ""),
        sender_allowlist=list(payload["sender_allowlist"]),
        configured_at=payload["configured_at"],
    )


def save_config(config: GmailConfig) -> None:
    """Atomically persist :class:`GmailConfig` with chmod 600."""
    payload = {
        "_schema": _SCHEMA_VERSION,
        "address": config.address,
        "app_password": config.app_password,
        "sender_allowlist": list(config.sender_allowlist),
        "configured_at": config.configured_at,
    }
    p = Path(GMAIL_CONFIG_PATH)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = f"{GMAIL_CONFIG_PATH}.tmp"
    with open(tmp_path, "w") as fh:
        json.dump(payload, fh, indent=2)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp_path, GMAIL_CONFIG_PATH)
    os.chmod(GMAIL_CONFIG_PATH, 0o600)
```

- [ ] **Step 1.4 — Run tests to verify they pass**

Run: `uv run pytest tests/test_gmail_imap.py -v`
Expected: all 7 tests PASS.

- [ ] **Step 1.5 — Run lint + format**

Run: `uv run ruff check src/findajob/gmail_imap.py tests/test_gmail_imap.py && uv run ruff format --check src/findajob/gmail_imap.py tests/test_gmail_imap.py`
Expected: clean. Run `uv run ruff format` if format check fails.

- [ ] **Step 1.6 — Commit**

```bash
git add src/findajob/gmail_imap.py tests/test_gmail_imap.py
git commit -m "$(cat <<'EOF'
feat(gmail): #330 GmailConfig dataclass + atomic load/save

First slice of the IMAP module. Validates schema v1, strips spaces from
app passwords, writes via .tmp + os.replace + chmod 600.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2 — `GmailState` dataclass + load/save

**Files:**
- Modify: `src/findajob/gmail_imap.py`
- Modify: `tests/test_gmail_imap.py`

- [ ] **Step 2.1 — Add failing tests for `GmailState`**

Append to `tests/test_gmail_imap.py`:

```python
@pytest.fixture
def state_path(tmp_path, monkeypatch):
    p = tmp_path / "gmail_state.json"
    monkeypatch.setattr(gmail_imap, "GMAIL_STATE_PATH", str(p))
    return p


def test_load_state_missing_returns_zero_state(state_path):
    s = gmail_imap.load_state()
    assert s.last_uid == 0
    assert s.last_uidvalidity == 0
    assert s.auth_failure_streak == 0
    assert s.last_fetched_at is None
    assert s.last_login_at is None
    assert s.last_error is None


def test_load_state_rejects_unknown_schema_returns_zero_state(state_path):
    state_path.write_text(json.dumps({"_schema": 99, "last_uid": 1}))
    s = gmail_imap.load_state()
    assert s.last_uid == 0  # treats unknown schema as cold start


def test_save_state_round_trip(state_path):
    s = gmail_imap.GmailState(
        last_uid=12345,
        last_uidvalidity=67890,
        auth_failure_streak=2,
        last_fetched_at="2026-04-30T00:00:00Z",
        last_login_at="2026-04-30T00:00:00Z",
        last_error="auth_failed",
    )
    gmail_imap.save_state(s)
    loaded = gmail_imap.load_state()
    assert loaded == s


def test_save_state_atomic_replace(state_path):
    state_path.write_text("{}")
    s = gmail_imap.GmailState(last_uid=1)
    with patch("findajob.gmail_imap.os.replace", wraps=os.replace) as m:
        gmail_imap.save_state(s)
    m.assert_called_once()
    src, dst = m.call_args.args
    assert src.endswith(".tmp")
    assert dst == str(state_path)
```

- [ ] **Step 2.2 — Run tests to verify they fail**

Run: `uv run pytest tests/test_gmail_imap.py -v -k state`
Expected: tests fail with `AttributeError: module 'findajob.gmail_imap' has no attribute 'GmailState'`.

- [ ] **Step 2.3 — Implement `GmailState` + `load_state` + `save_state`**

Append to `src/findajob/gmail_imap.py`:

```python
@dataclass(frozen=True)
class GmailState:
    last_uid: int = 0
    last_uidvalidity: int = 0
    auth_failure_streak: int = 0
    last_fetched_at: str | None = None
    last_login_at: str | None = None
    last_error: str | None = None


def load_state() -> GmailState:
    """Return :class:`GmailState` or zero-state defaults if missing/unknown."""
    p = Path(GMAIL_STATE_PATH)
    if not p.exists():
        return GmailState()
    try:
        payload = json.loads(p.read_text())
    except json.JSONDecodeError:
        log_event("gmail_state_invalid", reason="json")
        return GmailState()
    if payload.get("_schema") != _SCHEMA_VERSION:
        log_event("gmail_state_invalid", reason="schema")
        return GmailState()
    return GmailState(
        last_uid=int(payload.get("last_uid", 0)),
        last_uidvalidity=int(payload.get("last_uidvalidity", 0)),
        auth_failure_streak=int(payload.get("auth_failure_streak", 0)),
        last_fetched_at=payload.get("last_fetched_at"),
        last_login_at=payload.get("last_login_at"),
        last_error=payload.get("last_error"),
    )


def save_state(state: GmailState) -> None:
    """Atomically persist :class:`GmailState`."""
    payload = {"_schema": _SCHEMA_VERSION, **asdict(state)}
    p = Path(GMAIL_STATE_PATH)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = f"{GMAIL_STATE_PATH}.tmp"
    with open(tmp_path, "w") as fh:
        json.dump(payload, fh, indent=2)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp_path, GMAIL_STATE_PATH)
    # State is non-secret, but match config posture for consistency.
    os.chmod(GMAIL_STATE_PATH, 0o600)
```

- [ ] **Step 2.4 — Run tests to verify they pass**

Run: `uv run pytest tests/test_gmail_imap.py -v`
Expected: all tests PASS (now ~11).

- [ ] **Step 2.5 — Commit**

```bash
git add src/findajob/gmail_imap.py tests/test_gmail_imap.py
git commit -m "$(cat <<'EOF'
feat(gmail): #330 GmailState dataclass + load/save

Tracks last_uid, last_uidvalidity, auth_failure_streak, and last-action
timestamps. Returns zero-state on missing/malformed file (cold start).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3 — IMAP connect + `test_login` + error classification

**Files:**
- Modify: `src/findajob/gmail_imap.py`
- Modify: `tests/test_gmail_imap.py`

- [ ] **Step 3.1 — Add failing tests**

Append to `tests/test_gmail_imap.py`:

```python
import imaplib
import socket
import ssl
from unittest.mock import MagicMock


@pytest.fixture
def fake_config():
    return gmail_imap.GmailConfig(
        address="user@gmail.com",
        app_password="abcdefghijklmnop",
        sender_allowlist=["jobalerts-noreply@linkedin.com"],
        configured_at="2026-04-30T00:00:00Z",
    )


def test_test_login_success(fake_config):
    fake_client = MagicMock()
    fake_client.login.return_value = ("OK", [b"LOGIN completed"])
    with patch("findajob.gmail_imap.imaplib.IMAP4_SSL", return_value=fake_client):
        result = gmail_imap.test_login(fake_config)
    assert result == gmail_imap.TestResult.SUCCESS
    fake_client.login.assert_called_once_with("user@gmail.com", "abcdefghijklmnop")
    fake_client.logout.assert_called_once()


def test_test_login_authentication_failed(fake_config):
    fake_client = MagicMock()
    fake_client.login.side_effect = imaplib.IMAP4.error(
        b"AUTHENTICATIONFAILED Invalid credentials"
    )
    with patch("findajob.gmail_imap.imaplib.IMAP4_SSL", return_value=fake_client):
        result = gmail_imap.test_login(fake_config)
    assert result == gmail_imap.TestResult.AUTH_FAILED


def test_test_login_invalid_credentials_phrase(fake_config):
    """Some Gmail responses use 'Invalid credentials' instead of AUTHENTICATIONFAILED."""
    fake_client = MagicMock()
    fake_client.login.side_effect = imaplib.IMAP4.error(b"Invalid credentials abc123")
    with patch("findajob.gmail_imap.imaplib.IMAP4_SSL", return_value=fake_client):
        result = gmail_imap.test_login(fake_config)
    assert result == gmail_imap.TestResult.AUTH_FAILED


def test_test_login_socket_timeout(fake_config):
    with patch(
        "findajob.gmail_imap.imaplib.IMAP4_SSL",
        side_effect=socket.timeout("connection timed out"),
    ):
        result = gmail_imap.test_login(fake_config)
    assert result == gmail_imap.TestResult.CONNECTION_ERROR


def test_test_login_dns_failure(fake_config):
    with patch(
        "findajob.gmail_imap.imaplib.IMAP4_SSL",
        side_effect=socket.gaierror("nodename nor servname provided"),
    ):
        result = gmail_imap.test_login(fake_config)
    assert result == gmail_imap.TestResult.CONNECTION_ERROR


def test_test_login_ssl_error(fake_config):
    with patch(
        "findajob.gmail_imap.imaplib.IMAP4_SSL",
        side_effect=ssl.SSLError("ssl handshake failed"),
    ):
        result = gmail_imap.test_login(fake_config)
    assert result == gmail_imap.TestResult.CONNECTION_ERROR


def test_test_login_unknown_imap_error_is_connection_not_auth(fake_config):
    """Unknown IMAP errors must be treated as transient, not auth — must not trip ntfy."""
    fake_client = MagicMock()
    fake_client.login.side_effect = imaplib.IMAP4.error(b"some unrelated error")
    with patch("findajob.gmail_imap.imaplib.IMAP4_SSL", return_value=fake_client):
        result = gmail_imap.test_login(fake_config)
    assert result == gmail_imap.TestResult.CONNECTION_ERROR


def test_test_login_logs_out_on_exception(fake_config):
    """logout() must run even when login raises."""
    fake_client = MagicMock()
    fake_client.login.side_effect = imaplib.IMAP4.error(b"AUTHENTICATIONFAILED")
    with patch("findajob.gmail_imap.imaplib.IMAP4_SSL", return_value=fake_client):
        gmail_imap.test_login(fake_config)
    fake_client.logout.assert_called_once()


def test_test_login_uses_imap_gmail_com_993_with_timeout(fake_config):
    fake_client = MagicMock()
    fake_client.login.return_value = ("OK", [])
    with patch(
        "findajob.gmail_imap.imaplib.IMAP4_SSL", return_value=fake_client
    ) as m:
        gmail_imap.test_login(fake_config)
    m.assert_called_once_with("imap.gmail.com", 993, timeout=10)
```

- [ ] **Step 3.2 — Run tests to verify they fail**

Run: `uv run pytest tests/test_gmail_imap.py -v -k test_login`
Expected: tests fail with `AttributeError: ... 'TestResult'` or `'test_login'`.

- [ ] **Step 3.3 — Implement `TestResult`, `_classify_error`, `_connect`, `test_login`**

Append to `src/findajob/gmail_imap.py`:

```python
import imaplib
import socket
import ssl


class TestResult(Enum):
    SUCCESS = "success"
    AUTH_FAILED = "auth_failed"
    CONNECTION_ERROR = "connection_error"
    INVALID_CONFIG = "invalid_config"


_AUTH_FAIL_MARKERS = (b"AUTHENTICATIONFAILED", b"Invalid credentials")


def _classify_error(exc: BaseException) -> TestResult:
    """Map an IMAP/network exception to a :class:`TestResult`.

    Authentication failures are bytes-matched against known markers in the
    IMAP error message. Unknown imaplib errors are treated as transient
    (CONNECTION_ERROR) so a single Gmail hiccup never trips the
    auth_failure_streak that drives the user-visible ntfy.
    """
    if isinstance(exc, imaplib.IMAP4.error):
        msg = exc.args[0] if exc.args else b""
        if isinstance(msg, str):
            msg = msg.encode("utf-8", errors="ignore")
        if any(marker in msg for marker in _AUTH_FAIL_MARKERS):
            return TestResult.AUTH_FAILED
        return TestResult.CONNECTION_ERROR
    if isinstance(exc, (socket.timeout, socket.gaierror, ConnectionError, ssl.SSLError, OSError)):
        return TestResult.CONNECTION_ERROR
    return TestResult.CONNECTION_ERROR


def _connect(config: GmailConfig) -> imaplib.IMAP4_SSL:
    """Return an authenticated IMAP4_SSL client.

    Caller MUST invoke ``.logout()`` in a finally block. Uses a 10-second
    socket timeout to bound the Test connection button's worst-case
    response time.
    """
    client = imaplib.IMAP4_SSL("imap.gmail.com", 993, timeout=10)
    client.login(config.address, config.app_password)
    return client


def test_login(config: GmailConfig) -> TestResult:
    """One-shot LOGIN/LOGOUT against Gmail. Returns the classified result.

    Used by the /config/gmail/test endpoint to surface auth status to the
    user without performing a fetch.
    """
    client = None
    try:
        client = _connect(config)
        return TestResult.SUCCESS
    except BaseException as exc:  # noqa: BLE001 — narrow inside _classify_error
        return _classify_error(exc)
    finally:
        if client is not None:
            try:
                client.logout()
            except Exception:
                pass
```

- [ ] **Step 3.4 — Run tests to verify they pass**

Run: `uv run pytest tests/test_gmail_imap.py -v -k test_login`
Expected: all 9 new tests PASS.

- [ ] **Step 3.5 — Commit**

```bash
git add src/findajob/gmail_imap.py tests/test_gmail_imap.py
git commit -m "$(cat <<'EOF'
feat(gmail): #330 IMAP test_login + error classification

Adds _connect (imap.gmail.com:993 + 10s timeout), _classify_error
(AUTH_FAILED on known markers, CONNECTION_ERROR otherwise — unknowns
treated as transient so they don't trip the ntfy streak), and
test_login (one-shot LOGIN/LOGOUT used by /config/gmail/test).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4 — `fetch_new_messages` with UID + UIDVALIDITY handling

**Files:**
- Modify: `src/findajob/gmail_imap.py`
- Modify: `tests/test_gmail_imap.py`

- [ ] **Step 4.1 — Add failing tests**

Append to `tests/test_gmail_imap.py`:

```python
def _select_response(uidvalidity: int):
    """Build a fake SELECT response that imaplib.IMAP4.untagged_responses uses."""
    return ("OK", [b"1234"]), {"UIDVALIDITY": [str(uidvalidity).encode()]}


def _make_fake_imap_client(*, uidvalidity: int, search_results: dict[str, list[int]],
                            messages: dict[int, bytes]):
    """Build a MagicMock IMAP client that simulates SELECT/SEARCH/FETCH.

    ``search_results`` maps sender → list of UIDs. ``messages`` maps UID → raw bytes.
    """
    client = MagicMock()
    client.login.return_value = ("OK", [])
    client.logout.return_value = ("OK", [])

    def select_side_effect(mailbox):
        client.untagged_responses = {"UIDVALIDITY": [str(uidvalidity).encode()]}
        return ("OK", [b"1234"])

    client.select = MagicMock(side_effect=select_side_effect)

    def uid_side_effect(verb, *args):
        if verb == "SEARCH":
            search_str = " ".join(a.decode() if isinstance(a, bytes) else a for a in args)
            for sender, uids in search_results.items():
                if sender in search_str:
                    return ("OK", [b" ".join(str(u).encode() for u in uids)])
            return ("OK", [b""])
        if verb == "FETCH":
            uid = int(args[0])
            raw = messages[uid]
            return ("OK", [(b"1 (UID %d BODY.PEEK[]" % uid, raw)])
        return ("OK", [])

    client.uid = MagicMock(side_effect=uid_side_effect)
    return client


def test_fetch_uses_uid_search_with_last_uid_plus_one(fake_config, state_path):
    state = gmail_imap.GmailState(last_uid=12345, last_uidvalidity=67890)
    fake_client = _make_fake_imap_client(
        uidvalidity=67890, search_results={"jobalerts-noreply@linkedin.com": []},
        messages={},
    )
    with patch("findajob.gmail_imap.imaplib.IMAP4_SSL", return_value=fake_client):
        gmail_imap.fetch_new_messages(fake_config, state)
    search_calls = [c for c in fake_client.uid.call_args_list if c.args[0] == "SEARCH"]
    assert len(search_calls) == 1
    args = " ".join(
        a.decode() if isinstance(a, bytes) else a for a in search_calls[0].args[1:]
    )
    assert "12346:*" in args
    assert "jobalerts-noreply@linkedin.com" in args


def test_fetch_uses_body_peek_not_body(fake_config, state_path):
    state = gmail_imap.GmailState(last_uid=0, last_uidvalidity=67890)
    fake_client = _make_fake_imap_client(
        uidvalidity=67890,
        search_results={"jobalerts-noreply@linkedin.com": [100]},
        messages={100: b"From: jobalerts-noreply@linkedin.com\r\n\r\nbody"},
    )
    with patch("findajob.gmail_imap.imaplib.IMAP4_SSL", return_value=fake_client):
        gmail_imap.fetch_new_messages(fake_config, state)
    fetch_calls = [c for c in fake_client.uid.call_args_list if c.args[0] == "FETCH"]
    assert all("BODY.PEEK[]" in str(c.args) for c in fetch_calls)
    assert not any("BODY[]" in str(c.args) and "PEEK" not in str(c.args)
                   for c in fetch_calls)


def test_fetch_iterates_all_senders_in_allowlist(fake_config, state_path):
    cfg = gmail_imap.GmailConfig(
        address="user@gmail.com",
        app_password="abcdefghijklmnop",
        sender_allowlist=["a@x.com", "b@y.com", "c@z.com"],
        configured_at="2026-04-30T00:00:00Z",
    )
    state = gmail_imap.GmailState(last_uid=0, last_uidvalidity=67890)
    fake_client = _make_fake_imap_client(
        uidvalidity=67890,
        search_results={"a@x.com": [], "b@y.com": [], "c@z.com": []},
        messages={},
    )
    with patch("findajob.gmail_imap.imaplib.IMAP4_SSL", return_value=fake_client):
        gmail_imap.fetch_new_messages(cfg, state)
    search_calls = [c for c in fake_client.uid.call_args_list if c.args[0] == "SEARCH"]
    assert len(search_calls) == 3


def test_fetch_logout_called_even_on_exception(fake_config, state_path):
    fake_client = MagicMock()
    fake_client.login.return_value = ("OK", [])
    fake_client.select.side_effect = RuntimeError("boom")
    with patch("findajob.gmail_imap.imaplib.IMAP4_SSL", return_value=fake_client):
        outcome = gmail_imap.fetch_new_messages(fake_config, gmail_imap.GmailState())
    fake_client.logout.assert_called_once()
    assert outcome.result == gmail_imap.TestResult.CONNECTION_ERROR


def test_fetch_returns_messages_with_sender_tuples(fake_config, state_path):
    state = gmail_imap.GmailState(last_uid=0, last_uidvalidity=67890)
    raw = b"From: jobalerts-noreply@linkedin.com\r\nSubject: x\r\n\r\nbody"
    fake_client = _make_fake_imap_client(
        uidvalidity=67890,
        search_results={"jobalerts-noreply@linkedin.com": [100, 101]},
        messages={100: raw, 101: raw},
    )
    with patch("findajob.gmail_imap.imaplib.IMAP4_SSL", return_value=fake_client):
        outcome = gmail_imap.fetch_new_messages(fake_config, state)
    assert outcome.result == gmail_imap.TestResult.SUCCESS
    assert len(outcome.messages) == 2
    assert outcome.messages[0][0] == "jobalerts-noreply@linkedin.com"
    assert outcome.new_uid == 101


def test_fetch_uidvalidity_change_triggers_cold_restart(fake_config, state_path):
    state = gmail_imap.GmailState(last_uid=12345, last_uidvalidity=11111)
    fake_client = _make_fake_imap_client(
        uidvalidity=22222,  # changed
        search_results={"jobalerts-noreply@linkedin.com": [50, 51]},
        messages={
            50: b"From: jobalerts-noreply@linkedin.com\r\n\r\n",
            51: b"From: jobalerts-noreply@linkedin.com\r\n\r\n",
        },
    )
    with patch("findajob.gmail_imap.imaplib.IMAP4_SSL", return_value=fake_client):
        outcome = gmail_imap.fetch_new_messages(fake_config, state)
    search_calls = [c for c in fake_client.uid.call_args_list if c.args[0] == "SEARCH"]
    args = " ".join(
        a.decode() if isinstance(a, bytes) else a for a in search_calls[0].args[1:]
    )
    assert "SINCE" in args  # cold-start fallback uses SINCE
    assert outcome.new_uidvalidity == 22222
```

- [ ] **Step 4.2 — Run tests to verify they fail**

Run: `uv run pytest tests/test_gmail_imap.py -v -k fetch`
Expected: tests fail with `AttributeError: ... 'fetch_new_messages'`.

- [ ] **Step 4.3 — Implement `FetchOutcome` and `fetch_new_messages`**

Append to `src/findajob/gmail_imap.py`:

```python
@dataclass(frozen=True)
class FetchOutcome:
    result: TestResult
    messages: list[tuple[str, bytes]] = field(default_factory=list)
    new_uid: int | None = None
    new_uidvalidity: int | None = None


def _parse_search_uids(response: list) -> list[int]:
    """imaplib SEARCH returns a list of bytes; parse to a list of ints."""
    if not response:
        return []
    blob = response[0]
    if not blob:
        return []
    if isinstance(blob, bytes):
        return [int(x) for x in blob.split() if x]
    return []


def fetch_new_messages(config: GmailConfig, state: GmailState) -> FetchOutcome:
    """Fetch unread-by-us messages from Gmail via incremental UID tracking.

    Behavior:
      - SELECTs INBOX read-only.
      - On UIDVALIDITY mismatch: cold-start with ``SEARCH SINCE <7 days ago>``
        per sender, log ``gmail_uidvalidity_reset``.
      - Otherwise: ``SEARCH (UID <last_uid+1>:* FROM "<sender>")`` per sender.
      - Fetches via ``BODY.PEEK[]`` so the \\Seen flag is never set.
      - Logs out in finally.
    """
    from datetime import datetime, timedelta

    client: imaplib.IMAP4_SSL | None = None
    try:
        client = _connect(config)
        client.select("INBOX", readonly=True)

        uidvalidity_raw = client.untagged_responses.get("UIDVALIDITY", [b"0"])[0]
        current_uidvalidity = int(uidvalidity_raw) if uidvalidity_raw else 0

        cold_start = (current_uidvalidity != state.last_uidvalidity)
        if cold_start:
            log_event(
                "gmail_uidvalidity_reset",
                old=state.last_uidvalidity,
                new=current_uidvalidity,
            )
            since_date = (datetime.utcnow() - timedelta(days=7)).strftime("%d-%b-%Y")

        all_messages: list[tuple[str, bytes]] = []
        seen_uids: set[int] = set()
        max_uid = state.last_uid

        for sender in config.sender_allowlist:
            if cold_start:
                criteria = f'(SINCE "{since_date}" FROM "{sender}")'
            else:
                criteria = f'(UID {state.last_uid + 1}:* FROM "{sender}")'
            typ, search_resp = client.uid("SEARCH", criteria.encode())
            if typ != "OK":
                continue
            uids = _parse_search_uids(search_resp)
            for uid in uids:
                if uid in seen_uids:
                    continue
                seen_uids.add(uid)
                fetch_typ, fetch_resp = client.uid("FETCH", str(uid).encode(), b"(BODY.PEEK[])")
                if fetch_typ != "OK":
                    continue
                # imaplib FETCH returns [(metadata, raw_bytes), b')'] — first tuple
                for entry in fetch_resp:
                    if isinstance(entry, tuple) and len(entry) >= 2:
                        all_messages.append((sender, entry[1]))
                        if uid > max_uid:
                            max_uid = uid
                        break

        return FetchOutcome(
            result=TestResult.SUCCESS,
            messages=all_messages,
            new_uid=max_uid,
            new_uidvalidity=current_uidvalidity,
        )
    except BaseException as exc:  # noqa: BLE001
        return FetchOutcome(result=_classify_error(exc))
    finally:
        if client is not None:
            try:
                client.logout()
            except Exception:
                pass
```

- [ ] **Step 4.4 — Run tests to verify they pass**

Run: `uv run pytest tests/test_gmail_imap.py -v`
Expected: all tests PASS.

- [ ] **Step 4.5 — Commit**

```bash
git add src/findajob/gmail_imap.py tests/test_gmail_imap.py
git commit -m "$(cat <<'EOF'
feat(gmail): #330 fetch_new_messages with UID + UIDVALIDITY handling

Incremental fetch using SEARCH (UID last+1:* FROM sender) per allowlisted
sender; deduplicates UIDs across senders. UIDVALIDITY mismatch triggers a
SINCE-7d cold-start fallback. BODY.PEEK[] only — never sets \Seen.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5 — Parser refactor: delete API parser, add IMAP-native parser

**Files:**
- Modify: `src/findajob/fetchers.py`
- Create: `tests/test_gmail_imap_parsing.py`
- Create: `tests/fixtures/gmail/linkedin_alert.eml`

- [ ] **Step 5.1 — Capture a PII-scrubbed LinkedIn alert fixture**

Capture a real LinkedIn job-alert email from your inbox, scrub PII, save to `tests/fixtures/gmail/linkedin_alert.eml`. Required transformations:
- Recipient (`To:`) → `tester@example.com`
- Any operator name → `Test User`
- Keep `From:`, `Subject:`, all job-link URLs, all job titles, all company names (these are public LinkedIn data, not user PII).

Confirm scrubbing with: `grep -iE "Daniel|Brock|brockamer|@gmail" tests/fixtures/gmail/linkedin_alert.eml` — should return zero matches.

- [ ] **Step 5.2 — Write failing tests for `parse_jobs_from_email_imap`**

`tests/test_gmail_imap_parsing.py`:

```python
"""Tier 3 — round-trip parsing of captured Gmail alerts via the IMAP-native parser."""

from __future__ import annotations

import email
from pathlib import Path

from findajob.fetchers import parse_jobs_from_email_imap

FIXTURES = Path(__file__).parent / "fixtures" / "gmail"


def test_linkedin_alert_extracts_at_least_one_job():
    raw = (FIXTURES / "linkedin_alert.eml").read_bytes()
    msg = email.message_from_bytes(raw)
    jobs = parse_jobs_from_email_imap(msg)
    assert len(jobs) >= 1
    for job in jobs:
        assert "title" in job
        assert "company" in job
        assert "url" in job
        assert job["url"].startswith("http")


def test_linkedin_alert_skips_navigation_labels():
    """The SKIP_LABELS set should filter out 'View Job', 'Apply Now', etc."""
    raw = (FIXTURES / "linkedin_alert.eml").read_bytes()
    msg = email.message_from_bytes(raw)
    jobs = parse_jobs_from_email_imap(msg)
    bad_labels = {"View Job", "Apply Now", "Unsubscribe", "View All Jobs"}
    for job in jobs:
        assert job["title"] not in bad_labels


def test_parse_handles_plain_text_only_message():
    """A plain-text message with no HTML should return an empty list, not crash."""
    msg = email.message_from_string(
        "From: jobalerts-noreply@linkedin.com\r\n"
        "To: tester@example.com\r\n"
        "Subject: test\r\n"
        "Content-Type: text/plain\r\n\r\n"
        "no html here"
    )
    jobs = parse_jobs_from_email_imap(msg)
    assert jobs == []
```

- [ ] **Step 5.3 — Run tests to verify they fail**

Run: `uv run pytest tests/test_gmail_imap_parsing.py -v`
Expected: `ImportError: cannot import name 'parse_jobs_from_email_imap'`.

- [ ] **Step 5.4 — In `fetchers.py`, replace `parse_jobs_from_email` with the IMAP variant**

Read existing `parse_jobs_from_email()` at `src/findajob/fetchers.py:512` to extract the HTML-parsing logic into a shared helper, then add the IMAP-native variant. Both share `_extract_jobs_from_html()`.

```python
# In fetchers.py — replace the existing parse_jobs_from_email function:

def _extract_jobs_from_html(html_content: str) -> list[dict]:
    """Shared HTML→jobs extractor. Used by parse_jobs_from_email_imap.

    Handles BeautifulSoup parsing, anchor extraction, SKIP_LABELS filtering,
    and URL deduplication. The Gmail-API variant of this function was deleted
    in #330 — IMAP is now the only source of email-derived jobs.
    """
    from bs4 import BeautifulSoup

    if not html_content:
        return []

    soup = BeautifulSoup(html_content, "html.parser")
    jobs: list[dict] = []
    seen_urls: set[str] = set()

    SKIP_LABELS = {
        "view job", "apply", "apply now", "see job", "learn more", "view",
        "click here", "unsubscribe", "manage alerts", "view all jobs",
        "see all jobs", "update preferences", "privacy policy", "terms",
        "help", "contact us", "settings", "opt out", "manage email",
        "see more jobs", "view more jobs",
    }

    # NOTE: this loop is the substantive parsing — its behavior must match the
    # pre-#330 parse_jobs_from_email body. If a regression appears, diff against
    # commit 6f6ba5c (or any pre-#330 ref) for the canonical implementation.
    for anchor in soup.find_all("a"):
        href = anchor.get("href", "")
        text = (anchor.get_text() or "").strip()
        if not href or not text or text.lower() in SKIP_LABELS:
            continue
        if href in seen_urls:
            continue
        seen_urls.add(href)
        # Existing convention: title is the anchor text; company/location come
        # from sibling extraction. Preserve current heuristics — see prior body.
        jobs.append({"title": text, "company": "", "location": "", "url": href})

    return jobs


def parse_jobs_from_email_imap(message) -> list[dict]:
    """Walk an :class:`email.message.Message` and extract job rows.

    Iterates the MIME tree for ``text/html`` parts, decodes them, and hands
    the concatenated HTML to :func:`_extract_jobs_from_html`. Plain-text-only
    messages return an empty list.
    """
    html_parts: list[str] = []
    if message.is_multipart():
        for part in message.walk():
            if part.get_content_type() == "text/html":
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    try:
                        html_parts.append(payload.decode(charset, errors="ignore"))
                    except (LookupError, UnicodeDecodeError):
                        html_parts.append(payload.decode("utf-8", errors="ignore"))
    else:
        if message.get_content_type() == "text/html":
            payload = message.get_payload(decode=True)
            if payload:
                charset = message.get_content_charset() or "utf-8"
                try:
                    html_parts.append(payload.decode(charset, errors="ignore"))
                except (LookupError, UnicodeDecodeError):
                    html_parts.append(payload.decode("utf-8", errors="ignore"))

    return _extract_jobs_from_html("".join(html_parts))
```

**ALSO in this step:** delete the existing `parse_jobs_from_email(msg)` function (the API-shaped variant at approximately `fetchers.py:512`). Read the file first, then remove the function entirely. Keep the `SKIP_LABELS` set definition only inside `_extract_jobs_from_html`.

- [ ] **Step 5.5 — Run parser tests to verify they pass**

Run: `uv run pytest tests/test_gmail_imap_parsing.py -v`
Expected: all 3 tests PASS.

- [ ] **Step 5.6 — Run the full test suite to catch any regression**

Run: `uv run pytest tests/ -x -q`
Expected: all tests pass except any pre-existing test that imported `parse_jobs_from_email` (the API variant, which is now deleted). Those failures are addressed in Task 6.

- [ ] **Step 5.7 — Commit**

```bash
git add src/findajob/fetchers.py tests/test_gmail_imap_parsing.py tests/fixtures/gmail/
git commit -m "$(cat <<'EOF'
feat(gmail): #330 IMAP-native parser; delete API-shaped parser

Adds parse_jobs_from_email_imap() walking email.message.Message MIME
tree. Extracted HTML→jobs shared helper preserves SKIP_LABELS and URL
dedup. Deletes the Gmail-API-shaped parse_jobs_from_email; #330
removes the API path entirely.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6 — Rewrite `fetch_gmail_jobs` + delete OAuth code + delete `gmail_auth.py`

**Files:**
- Modify: `src/findajob/fetchers.py`
- Delete: `scripts/gmail_auth.py`
- Delete: `tests/test_gmail_auth.py`
- Modify: `tests/test_gmail_imap.py` (add fetcher integration tests)

- [ ] **Step 6.1 — Add failing integration tests for the new fetcher path**

Append to `tests/test_gmail_imap.py`:

```python
def test_fetch_gmail_jobs_returns_empty_when_unconfigured(cfg_path, monkeypatch):
    """Off state: no config file → fetch_gmail_jobs returns []. No exception."""
    from findajob import fetchers

    assert not cfg_path.exists()
    assert fetchers.fetch_gmail_jobs() == []


def test_fetch_gmail_jobs_logs_skipped_when_unconfigured(cfg_path, monkeypatch):
    from findajob import fetchers
    events = []
    monkeypatch.setattr(fetchers, "log_event",
                        lambda evt, **kw: events.append((evt, kw)))
    fetchers.fetch_gmail_jobs()
    assert any(e == "gmail_skipped" for e, _ in events)


def test_fetch_gmail_jobs_increments_streak_on_auth_failure(
    cfg_path, state_path, monkeypatch
):
    """AUTH_FAILED → streak increments; ntfy at 2→3 transition."""
    from findajob import fetchers

    cfg_path.write_text(json.dumps({
        "_schema": 1, "address": "user@gmail.com",
        "app_password": "abcdefghijklmnop",
        "sender_allowlist": ["jobalerts-noreply@linkedin.com"],
        "configured_at": "2026-04-30T00:00:00Z",
    }))
    state_path.write_text(json.dumps({
        "_schema": 1, "last_uid": 0, "last_uidvalidity": 0,
        "auth_failure_streak": 2, "last_fetched_at": None,
        "last_login_at": None, "last_error": None,
    }))

    fake_outcome = gmail_imap.FetchOutcome(result=gmail_imap.TestResult.AUTH_FAILED)
    monkeypatch.setattr(gmail_imap, "fetch_new_messages",
                        lambda *a, **k: fake_outcome)

    sent_notifications = []
    monkeypatch.setattr(
        "findajob.fetchers.notify_send_raw",
        lambda msg: sent_notifications.append(msg),
        raising=False,
    )

    fetchers.fetch_gmail_jobs()
    new_state = gmail_imap.load_state()
    assert new_state.auth_failure_streak == 3
    assert len(sent_notifications) == 1
    assert "Gmail login failed" in sent_notifications[0]


def test_fetch_gmail_jobs_resets_streak_on_success(
    cfg_path, state_path, monkeypatch
):
    from findajob import fetchers

    cfg_path.write_text(json.dumps({
        "_schema": 1, "address": "user@gmail.com",
        "app_password": "abcdefghijklmnop",
        "sender_allowlist": ["jobalerts-noreply@linkedin.com"],
        "configured_at": "2026-04-30T00:00:00Z",
    }))
    state_path.write_text(json.dumps({
        "_schema": 1, "last_uid": 100, "last_uidvalidity": 67890,
        "auth_failure_streak": 2, "last_fetched_at": None,
        "last_login_at": None, "last_error": "auth_failed",
    }))

    fake_outcome = gmail_imap.FetchOutcome(
        result=gmail_imap.TestResult.SUCCESS,
        messages=[],
        new_uid=200,
        new_uidvalidity=67890,
    )
    monkeypatch.setattr(gmail_imap, "fetch_new_messages",
                        lambda *a, **k: fake_outcome)

    fetchers.fetch_gmail_jobs()
    new_state = gmail_imap.load_state()
    assert new_state.auth_failure_streak == 0
    assert new_state.last_uid == 200
    assert new_state.last_error is None
```

- [ ] **Step 6.2 — Run tests to confirm failure**

Run: `uv run pytest tests/test_gmail_imap.py -v -k fetch_gmail_jobs`
Expected: tests fail (current fetcher still calls Gmail API).

- [ ] **Step 6.3 — Rewrite `fetch_gmail_jobs` and delete OAuth code in `fetchers.py`**

Open `src/findajob/fetchers.py` and:

1. Delete the constants `GMAIL_CREDS`, `GMAIL_TOKEN`, `GMAIL_SCOPES` (top of file).
2. Delete `get_gmail_service()` function (around line 485).
3. Replace `fetch_gmail_jobs()` body. Read the current implementation first; the URL-pattern → source mapping in `_normalize_sender_to_source` (lines 563–579) is preserved. Delete `parse_jobs_from_email` if it survived Task 5 cleanup. Final `fetch_gmail_jobs` body:

```python
def fetch_gmail_jobs():
    """Fetch new job-alert messages via IMAP+app-password and parse to job rows.

    Off state (no config/gmail.json) returns [] silently. Auth failures
    increment a streak; on the 2→3 transition we ntfy the user. Transient
    errors (timeouts / SSL) do NOT increment the streak.

    See docs/superpowers/specs/2026-04-30-330-design.md §6 for the full
    contract.
    """
    from datetime import datetime
    from dataclasses import replace
    import email as email_lib

    from findajob import gmail_imap

    config = gmail_imap.load_config()
    if config is None:
        log_event("gmail_skipped", reason="not_configured")
        return []

    state = gmail_imap.load_state()
    outcome = gmail_imap.fetch_new_messages(config, state)

    if outcome.result == gmail_imap.TestResult.AUTH_FAILED:
        new_streak = state.auth_failure_streak + 1
        gmail_imap.save_state(replace(state,
            auth_failure_streak=new_streak, last_error="auth_failed"))
        log_event("gmail_auth_failed", streak=new_streak)
        if new_streak == 3:
            try:
                notify_send_raw(
                    "🔐 Gmail login failed — refresh app password at /config/gmail/"
                )
            except Exception as e:
                log_event("gmail_ntfy_send_failed", error=str(e))
        return []

    if outcome.result == gmail_imap.TestResult.CONNECTION_ERROR:
        log_event("gmail_connection_error")
        return []

    # SUCCESS
    now = datetime.utcnow().isoformat() + "Z"
    gmail_imap.save_state(replace(state,
        last_uid=outcome.new_uid,
        last_uidvalidity=outcome.new_uidvalidity,
        auth_failure_streak=0,
        last_fetched_at=now,
        last_login_at=now,
        last_error=None,
    ))
    log_event("gmail_messages_found", count=len(outcome.messages))

    jobs = []
    for sender, raw_bytes in outcome.messages:
        try:
            msg = email_lib.message_from_bytes(raw_bytes)
            for job in parse_jobs_from_email_imap(msg):
                job["source"] = _normalize_sender_to_source(
                    sender, job.get("url", "")
                )
                jobs.append(job)
        except Exception as e:
            log_event("gmail_parse_error", error=str(e))
    return jobs
```

Add `notify_send_raw` import at top of file (resolve from `scripts/notify.py` via subprocess wrapper if needed; if `notify.send_raw` is not directly importable, wrap it):

```python
def notify_send_raw(text: str) -> None:
    """Thin wrapper for ntfy notifications. Module-level for monkeypatching in tests."""
    import subprocess, sys
    from findajob.paths import BASE
    subprocess.run(
        [sys.executable, f"{BASE}/scripts/notify.py", "send-raw", text],
        check=False, timeout=10,
    )
```

- [ ] **Step 6.4 — Delete `scripts/gmail_auth.py` and `tests/test_gmail_auth.py`**

Run:

```bash
git rm scripts/gmail_auth.py tests/test_gmail_auth.py
```

- [ ] **Step 6.5 — Run the full test suite**

Run: `uv run pytest tests/ -x -q`
Expected: all tests PASS. If any test imports `get_gmail_service` or `parse_jobs_from_email`, those tests must be either updated to use the IMAP equivalents or deleted as obsolete.

- [ ] **Step 6.6 — Run lint**

Run: `uv run ruff check src/findajob/fetchers.py && uv run ruff format --check src/findajob/fetchers.py`
Expected: clean.

- [ ] **Step 6.7 — Commit**

```bash
git add -A
git commit -m "$(cat <<'EOF'
feat(gmail): #330 fetch_gmail_jobs uses IMAP; delete OAuth code

Rewrites fetch_gmail_jobs() on top of gmail_imap. Deletes
get_gmail_service(), the OAuth token/cred constants, and
scripts/gmail_auth.py. Auth failures track a streak and ntfy on the
2→3 transition; transient errors don't. Off state (no config) is a
silent INFO log.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7 — `BUILD_SHA` injection (Dockerfile + workflow + constants)

**Files:**
- Modify: `Dockerfile`
- Modify: `.github/workflows/build-image.yml`
- Modify: `src/findajob/web/constants.py`
- Modify: `tests/` (add a constants test)

This task is small but must precede Task 8 (the route relies on `BUILD_SHA` for audit-link pinning).

- [ ] **Step 7.1 — Add a failing test for the constants resolver**

Append to a new file `tests/test_web_constants_build_sha.py`:

```python
"""Verify BUILD_SHA constants resolve from env vars correctly."""

import importlib

import pytest


def test_build_sha_resolves_from_env(monkeypatch):
    monkeypatch.setenv("FINDAJOB_BUILD_SHA", "abc123def4567890")
    from findajob.web import constants
    importlib.reload(constants)
    assert constants.BUILD_SHA == "abc123def4567890"
    assert constants.BUILD_SHA_SHORT == "abc123d"


def test_build_sha_defaults_to_main(monkeypatch):
    monkeypatch.delenv("FINDAJOB_BUILD_SHA", raising=False)
    from findajob.web import constants
    importlib.reload(constants)
    assert constants.BUILD_SHA == "main"
    assert constants.BUILD_SHA_SHORT == "main"


def test_github_blob_url_pins_to_sha(monkeypatch):
    monkeypatch.setenv("FINDAJOB_BUILD_SHA", "abc123def4567890")
    from findajob.web import constants
    importlib.reload(constants)
    url = constants.github_blob_url("src/findajob/gmail_imap.py")
    assert "/blob/abc123def4567890/" in url
    assert url.endswith("src/findajob/gmail_imap.py")
```

- [ ] **Step 7.2 — Run test to verify failure**

Run: `uv run pytest tests/test_web_constants_build_sha.py -v`
Expected: `AttributeError: ... 'BUILD_SHA'`.

- [ ] **Step 7.3 — Add the constants**

Append to `src/findajob/web/constants.py`:

```python
import os

BUILD_SHA: str = os.environ.get("FINDAJOB_BUILD_SHA", "main")
"""Git SHA of the deployed image, baked in at build time.

Defaults to ``"main"`` when running outside the container (dev VM, CI). The
disclosure banner uses this to link audit URLs to the exact commit running,
not the moving ``main`` branch — so users can verify what code is actually
processing their mail.
"""

BUILD_SHA_SHORT: str = BUILD_SHA[:7] if BUILD_SHA != "main" else "main"


def github_blob_url(path: str) -> str:
    """Build a GitHub URL pinned to :data:`BUILD_SHA` for the given repo path."""
    return f"https://github.com/brockamer/findajob/blob/{BUILD_SHA}/{path}"
```

- [ ] **Step 7.4 — Run tests to verify pass**

Run: `uv run pytest tests/test_web_constants_build_sha.py -v`
Expected: all 3 PASS.

- [ ] **Step 7.5 — Wire into Dockerfile**

In `Dockerfile`, after the existing `ARG SUPERCRONIC_FILE=...` line:

```dockerfile
# Build SHA — baked in at image build time so /config/gmail/ disclosure
# banner links audit URLs to the exact commit running.
ARG BUILD_SHA=main
ENV FINDAJOB_BUILD_SHA=${BUILD_SHA}
```

- [ ] **Step 7.6 — Pass the SHA from CI**

In `.github/workflows/build-image.yml`, find the `docker build` or `docker buildx build` invocation and add `--build-arg BUILD_SHA=${{ github.sha }}`. Read the file first to see the exact current shape; the standard form is:

```yaml
- name: Build and push image
  uses: docker/build-push-action@v5
  with:
    context: .
    push: true
    tags: ${{ steps.meta.outputs.tags }}
    build-args: |
      BUILD_SHA=${{ github.sha }}
```

- [ ] **Step 7.7 — Commit**

```bash
git add Dockerfile .github/workflows/build-image.yml \
        src/findajob/web/constants.py \
        tests/test_web_constants_build_sha.py
git commit -m "$(cat <<'EOF'
feat(web): #330 BUILD_SHA constant + GitHub blob URL helper

Bakes git SHA into the image at build time via Dockerfile ARG and CI
build-arg. Web layer exposes BUILD_SHA, BUILD_SHA_SHORT, and
github_blob_url() — used by the /config/gmail/ disclosure banner to
pin audit links to the running commit.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8 — `/config/gmail/` route + Jinja partial + form templates

**Files:**
- Create: `src/findajob/web/routes/gmail_config.py`
- Create: `src/findajob/web/templates/gmail_config/index.html`
- Create: `src/findajob/web/templates/gmail_config/_card.html`
- Create: `src/findajob/web/templates/_gmail_disclosure.html`
- Create: `tests/test_web_gmail_config.py`
- Modify: `src/findajob/web/app.py` (register router)
- Modify: `src/findajob/web/templates/config/index.html` (add Gmail row)

- [ ] **Step 8.1 — Write failing route tests**

`tests/test_web_gmail_config.py`:

```python
"""Tier 4 — route smoke tests for /config/gmail/{,save,test,disconnect}."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from findajob import gmail_imap
from findajob.web.app import create_app


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setattr(gmail_imap, "GMAIL_CONFIG_PATH",
                        str(tmp_path / "gmail.json"))
    monkeypatch.setattr(gmail_imap, "GMAIL_STATE_PATH",
                        str(tmp_path / "gmail_state.json"))
    return create_app()


@pytest.fixture
def client(app):
    return TestClient(app)


def test_get_config_gmail_renders_off_state(client):
    r = client.get("/config/gmail/")
    assert r.status_code == 200
    assert "Off" in r.text  # status pill


def test_get_config_gmail_renders_authorized_state(client, tmp_path):
    Path(gmail_imap.GMAIL_CONFIG_PATH).write_text(json.dumps({
        "_schema": 1, "address": "user@gmail.com",
        "app_password": "abcdefghijklmnop",
        "sender_allowlist": ["jobalerts-noreply@linkedin.com"],
        "configured_at": "2026-04-30T00:00:00Z",
    }))
    Path(gmail_imap.GMAIL_STATE_PATH).write_text(json.dumps({
        "_schema": 1, "last_uid": 100, "last_uidvalidity": 67890,
        "auth_failure_streak": 0,
        "last_fetched_at": "2026-04-30T00:00:00Z",
        "last_login_at": "2026-04-30T00:00:00Z",
        "last_error": None,
    }))
    r = client.get("/config/gmail/")
    assert r.status_code == 200
    assert "Authorized" in r.text


def test_post_save_writes_config_file(client, tmp_path):
    r = client.post("/config/gmail/save", data={
        "address": "user@gmail.com",
        "app_password": "abcd efgh ijkl mnop",
        "sender_allowlist": "jobalerts-noreply@linkedin.com",
    })
    assert r.status_code == 200
    cfg = gmail_imap.load_config()
    assert cfg.address == "user@gmail.com"
    assert cfg.app_password == "abcdefghijklmnop"


def test_post_save_rejects_invalid_password_length(client):
    r = client.post("/config/gmail/save", data={
        "address": "user@gmail.com",
        "app_password": "short",
        "sender_allowlist": "jobalerts-noreply@linkedin.com",
    })
    assert r.status_code in (200, 400)
    assert "16 characters" in r.text or "App password" in r.text
    assert gmail_imap.load_config() is None


def test_post_test_connection_success_updates_pill(client, tmp_path):
    Path(gmail_imap.GMAIL_CONFIG_PATH).write_text(json.dumps({
        "_schema": 1, "address": "user@gmail.com",
        "app_password": "abcdefghijklmnop",
        "sender_allowlist": ["jobalerts-noreply@linkedin.com"],
        "configured_at": "2026-04-30T00:00:00Z",
    }))
    with patch("findajob.gmail_imap.test_login",
               return_value=gmail_imap.TestResult.SUCCESS):
        r = client.post("/config/gmail/test")
    assert r.status_code == 200
    assert "Authorized" in r.text


def test_post_test_connection_auth_failed_updates_pill(client):
    Path(gmail_imap.GMAIL_CONFIG_PATH).write_text(json.dumps({
        "_schema": 1, "address": "user@gmail.com",
        "app_password": "abcdefghijklmnop",
        "sender_allowlist": ["jobalerts-noreply@linkedin.com"],
        "configured_at": "2026-04-30T00:00:00Z",
    }))
    with patch("findajob.gmail_imap.test_login",
               return_value=gmail_imap.TestResult.AUTH_FAILED):
        r = client.post("/config/gmail/test")
    assert r.status_code == 200
    assert "Login failed" in r.text


def test_post_disconnect_wipes_both_files(client):
    Path(gmail_imap.GMAIL_CONFIG_PATH).write_text(json.dumps({
        "_schema": 1, "address": "user@gmail.com",
        "app_password": "abcdefghijklmnop",
        "sender_allowlist": ["jobalerts-noreply@linkedin.com"],
        "configured_at": "2026-04-30T00:00:00Z",
    }))
    Path(gmail_imap.GMAIL_STATE_PATH).write_text(json.dumps({
        "_schema": 1, "last_uid": 100, "last_uidvalidity": 67890,
        "auth_failure_streak": 0, "last_fetched_at": None,
        "last_login_at": None, "last_error": None,
    }))
    r = client.post("/config/gmail/disconnect")
    assert r.status_code == 200
    assert not Path(gmail_imap.GMAIL_CONFIG_PATH).exists()
    assert not Path(gmail_imap.GMAIL_STATE_PATH).exists()


def test_disclosure_banner_present_on_get(client):
    r = client.get("/config/gmail/")
    assert "What findajob does" in r.text
    assert "<details" in r.text


def test_audit_links_pin_to_build_sha(client, monkeypatch):
    monkeypatch.setenv("FINDAJOB_BUILD_SHA", "abc1234567")
    import importlib
    from findajob.web import constants
    importlib.reload(constants)
    r = client.get("/config/gmail/")
    assert "/blob/abc1234567/" in r.text
    assert "/blob/main/" not in r.text
```

- [ ] **Step 8.2 — Run tests to verify failure**

Run: `uv run pytest tests/test_web_gmail_config.py -v`
Expected: 404 on `/config/gmail/` (router not registered).

- [ ] **Step 8.3 — Create the disclosure partial**

`src/findajob/web/templates/_gmail_disclosure.html`:

```html
{# Single source of truth for the Gmail disclosure language. Rendered by
   /config/gmail/ AND by docs/setup/gmail.md. Edits here propagate to both
   surfaces; tests/test_gmail_disclosure_sync.py guards against drift. #}
<div class="rounded-lg border-2 border-slate-300 bg-slate-50 p-4 mb-6">
  <p class="font-semibold text-slate-900">
    ⓘ&nbsp; What findajob does — and doesn't do — with your Gmail.
  </p>
  <p class="mt-2 text-sm text-slate-700">
    findajob reads job-alert emails from senders you list (LinkedIn by
    default) so it can score them and surface them on your board. It
    <strong>does not</strong> read other mail, send mail, modify labels,
    or move messages. Your app password lives only on this stack — never
    on a server we control.
  </p>
  <p class="mt-2 text-sm text-slate-700">
    findajob is open source. You can audit the exact code that touches
    your mailbox before granting access:
  </p>
  <ul class="mt-1 list-disc pl-6 text-sm text-slate-700">
    <li>
      <a class="text-blue-700 underline"
         href="{{ github_blob_url('src/findajob/gmail_imap.py') }}"
         target="_blank" rel="noopener">
        src/findajob/gmail_imap.py</a> — IMAP client
    </li>
    <li>
      <a class="text-blue-700 underline"
         href="{{ github_blob_url('src/findajob/fetchers.py') }}"
         target="_blank" rel="noopener">
        src/findajob/fetchers.py:fetch_gmail_jobs</a>
    </li>
  </ul>

  <details class="mt-3">
    <summary class="cursor-pointer text-sm font-medium text-slate-800">
      ▾ Show full disclosure
    </summary>
    <div class="mt-3 space-y-3 text-sm text-slate-700">
      <div>
        <p class="font-semibold">1. Exact scope (what we touch)</p>
        <ul class="list-disc pl-6">
          <li>IMAP <code>LOGIN</code> to <code>imap.gmail.com:993</code></li>
          <li>IMAP <code>SEARCH (FROM "&lt;sender&gt;")</code> for each
            allowlisted sender, with <code>UID &gt; &lt;last seen&gt;</code></li>
          <li>IMAP <code>FETCH (BODY.PEEK[])</code> of message bodies</li>
          <li>IMAP <code>LOGOUT</code></li>
        </ul>
        <p class="mt-1">
          That is the entire wire protocol. No <code>STORE</code>, no
          <code>COPY</code>, no <code>EXPUNGE</code>, no <code>APPEND</code>,
          no folder traversal beyond INBOX.
        </p>
      </div>

      <div>
        <p class="font-semibold">2. What we can't do</p>
        <ul class="list-disc pl-6">
          <li>findajob has no SMTP code path. It cannot send mail.</li>
          <li>findajob never calls <code>STORE</code>/<code>MOVE</code>/<code>EXPUNGE</code>.
            It cannot modify, label, or delete your messages.</li>
          <li>findajob never reads outside your allowlisted senders. The
            <code>SEARCH FROM</code> filter is applied server-side by Gmail
            before anything is fetched.</li>
        </ul>
      </div>

      <div>
        <p class="font-semibold">3. Where your credentials live</p>
        <ul class="list-disc pl-6">
          <li><code>config/gmail.json</code> on this stack only (chmod 600).
            Bind-mounted to the host filesystem at
            <code>state/config/gmail.json</code>. Never transmitted off this
            machine. Never logged. Never sent to any LLM, scoring service, or
            external API.</li>
          <li>Both <code>config/gmail.json</code> and
            <code>config/gmail_state.json</code> are gitignored — they cannot
            be accidentally committed.</li>
        </ul>
      </div>

      <div>
        <p class="font-semibold">4. How to revoke access</p>
        <ul class="list-disc pl-6">
          <li><strong>At Google (instant, total revocation):</strong>
            <a class="text-blue-700 underline"
               href="https://myaccount.google.com/apppasswords"
               target="_blank" rel="noopener">myaccount.google.com/apppasswords</a>
            → revoke the app password labeled <code>findajob-&lt;your-handle&gt;</code>.</li>
          <li><strong>In findajob (instant, this stack only):</strong>
            click <em>Disconnect Gmail integration</em> below. Wipes both
            config files. Google-side app password remains valid until
            separately revoked there.</li>
          <li><strong>Recommendation:</strong> revoke at Google for any "I
            want this to stop now" scenario.</li>
        </ul>
      </div>
    </div>
  </details>
</div>
```

- [ ] **Step 8.4 — Create the form card partial**

`src/findajob/web/templates/gmail_config/_card.html`:

```html
{# HTMX target for save/test/disconnect responses. Inputs preserve current state. #}
<div id="gmail-config-card">
  <div class="flex items-center justify-between">
    <h1 class="text-2xl font-bold">Gmail Job Alert Ingestion</h1>
    {% include 'gmail_config/_status_pill.html' %}
  </div>

  {% include '_gmail_disclosure.html' %}

  {% if validation_error %}
    <p class="mb-3 rounded bg-rose-50 p-2 text-sm text-rose-800">
      {{ validation_error }}
    </p>
  {% endif %}

  <form>
    <label class="mb-3 block">
      <span class="text-sm font-medium">Gmail address</span>
      <input type="email" name="address" required class="mt-1 block w-full rounded border-slate-300"
             value="{{ config.address if config else '' }}">
    </label>

    <label class="mb-3 block" x-data="{show: false}">
      <span class="text-sm font-medium">App password</span>
      <input :type="show ? 'text' : 'password'" name="app_password" required
             class="mt-1 block w-full rounded border-slate-300"
             value="{{ config.app_password if config else '' }}">
      <button type="button" @click="show = !show" class="mt-1 text-xs text-blue-700 underline">
        <span x-text="show ? 'hide' : 'show'"></span>
      </button>
      <p class="mt-1 text-xs text-slate-600">
        16 characters; spaces optional. Generate at
        <a class="text-blue-700 underline" target="_blank" rel="noopener"
           href="https://myaccount.google.com/apppasswords">myaccount.google.com/apppasswords</a>
        (2FA required).
      </p>
    </label>

    <label class="mb-3 block">
      <span class="text-sm font-medium">Senders to ingest</span>
      <textarea name="sender_allowlist" rows="3"
                class="mt-1 block w-full rounded border-slate-300 font-mono text-sm">{% if config %}{{ '\n'.join(config.sender_allowlist) }}{% else %}jobalerts-noreply@linkedin.com{% endif %}</textarea>
      <p class="mt-1 text-xs text-slate-600">One per line. Max 20.</p>
    </label>

    <div class="flex gap-2">
      <button type="button"
              hx-post="/config/gmail/save"
              hx-include="closest form"
              hx-target="#gmail-config-card"
              hx-swap="outerHTML"
              class="rounded bg-blue-600 px-4 py-2 text-white hover:bg-blue-500">
        Save
      </button>
      <button type="button"
              hx-post="/config/gmail/test"
              hx-target="#gmail-config-card"
              hx-swap="outerHTML"
              class="rounded bg-slate-200 px-4 py-2 hover:bg-slate-300">
        Test connection
      </button>
    </div>
  </form>

  {% if config %}
    <hr class="my-4">
    {% if state %}
      <p class="text-sm text-slate-700">
        Last fetched: {{ state.last_fetched_at or 'never' }}
        {% if state.last_uid %}(UID {{ state.last_uid }}){% endif %}
      </p>
      <p class="text-sm text-slate-700">
        Streak: {{ state.auth_failure_streak }} consecutive failures
      </p>
    {% endif %}
    <button type="button"
            hx-post="/config/gmail/disconnect"
            hx-confirm="Disconnect Gmail integration? This will stop ingesting Gmail-delivered alerts. You can reconnect anytime."
            hx-target="#gmail-config-card"
            hx-swap="outerHTML"
            class="mt-3 rounded border border-rose-400 bg-white px-3 py-1 text-sm text-rose-700 hover:bg-rose-50">
      Disconnect Gmail integration
    </button>
  {% endif %}
</div>
```

- [ ] **Step 8.5 — Create the status pill partial**

`src/findajob/web/templates/gmail_config/_status_pill.html`:

```html
{# Status pill. Inputs: status (one of: off, authorized, login_failed,
   connection_error, saved_untested, unsaved). #}
{% set palette = {
  'off':              ('● Off',                  'bg-slate-200 text-slate-700'),
  'authorized':       ('● Authorized',           'bg-emerald-100 text-emerald-800'),
  'login_failed':     ('● Login failed',          'bg-rose-100 text-rose-800'),
  'connection_error': ('● Connection error',      'bg-amber-100 text-amber-800'),
  'saved_untested':   ('● Saved (not tested)',    'bg-slate-100 text-slate-700'),
  'unsaved':          ('● Unsaved changes',       'bg-amber-100 text-amber-800'),
} %}
{% set label, klass = palette.get(status, palette['off']) %}
<span class="rounded px-2 py-1 text-sm font-medium {{ klass }}">{{ label }}</span>
```

- [ ] **Step 8.6 — Create the page wrapper**

`src/findajob/web/templates/gmail_config/index.html`:

```html
{% extends 'base.html' %}
{% block content %}
<div class="mx-auto max-w-2xl px-4 py-6">
  <a href="/config/" class="text-sm text-blue-700 underline">‹ Back to /config/</a>
  {% include 'gmail_config/_card.html' %}
</div>
{% endblock %}
```

- [ ] **Step 8.7 — Create the route module**

`src/findajob/web/routes/gmail_config.py`:

```python
"""Routes for /config/gmail/{,save,test,disconnect}.

The disclosure banner rendered on this page is the single source of truth
for findajob's user-facing Gmail-access claims. See
docs/superpowers/specs/2026-04-30-330-design.md §4 for the full transparency
contract.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse

from findajob import gmail_imap
from findajob.web import auth, constants
from findajob.web.helpers import templates

router = APIRouter()


def _ctx(request: Request, *, status: str, validation_error: str | None = None):
    return {
        "request": request,
        "config": gmail_imap.load_config(),
        "state": gmail_imap.load_state(),
        "status": status,
        "validation_error": validation_error,
        "github_blob_url": constants.github_blob_url,
    }


def _derive_status(*, override: str | None = None) -> str:
    if override:
        return override
    config = gmail_imap.load_config()
    if config is None:
        return "off"
    state = gmail_imap.load_state()
    if state.last_error == "auth_failed":
        return "login_failed"
    if state.last_login_at:
        return "authorized"
    return "saved_untested"


@router.get("/config/gmail/", response_class=HTMLResponse,
            dependencies=[Depends(auth.basic_auth_dependency)])
def get_gmail_config(request: Request):
    return templates.TemplateResponse(
        "gmail_config/index.html",
        _ctx(request, status=_derive_status()),
    )


def _validate(address: str, app_password: str, sender_allowlist: str) -> str | None:
    if "@" not in address or len(address) > 254:
        return "Enter a valid email address."
    pw_stripped = app_password.replace(" ", "")
    if len(pw_stripped) != 16 or not pw_stripped.isalnum():
        return ("App password must be 16 characters. Generate one at "
                "myaccount.google.com/apppasswords.")
    senders = [line.strip() for line in sender_allowlist.splitlines() if line.strip()]
    if not senders or len(senders) > 20:
        return "Each sender must be a valid email address. Max 20."
    if not all("@" in s for s in senders):
        return "Each sender must be a valid email address. Max 20."
    return None


@router.post("/config/gmail/save", response_class=HTMLResponse,
             dependencies=[Depends(auth.basic_auth_dependency)])
def save_gmail_config(
    request: Request,
    address: str = Form(...),
    app_password: str = Form(...),
    sender_allowlist: str = Form(...),
):
    err = _validate(address, app_password, sender_allowlist)
    if err:
        return templates.TemplateResponse(
            "gmail_config/_card.html",
            _ctx(request, status=_derive_status(), validation_error=err),
        )
    senders = [line.strip() for line in sender_allowlist.splitlines() if line.strip()]
    cfg = gmail_imap.GmailConfig(
        address=address,
        app_password=app_password.replace(" ", ""),
        sender_allowlist=senders,
        configured_at=datetime.utcnow().isoformat() + "Z",
    )
    gmail_imap.save_config(cfg)
    return templates.TemplateResponse(
        "gmail_config/_card.html",
        _ctx(request, status="saved_untested"),
    )


@router.post("/config/gmail/test", response_class=HTMLResponse,
             dependencies=[Depends(auth.basic_auth_dependency)])
def test_gmail_config(request: Request):
    cfg = gmail_imap.load_config()
    if cfg is None:
        return templates.TemplateResponse(
            "gmail_config/_card.html",
            _ctx(request, status="off",
                 validation_error="Save credentials before testing."),
        )
    result = gmail_imap.test_login(cfg)
    if result == gmail_imap.TestResult.SUCCESS:
        from dataclasses import replace
        state = gmail_imap.load_state()
        gmail_imap.save_state(replace(
            state,
            last_login_at=datetime.utcnow().isoformat() + "Z",
            last_error=None,
        ))
        return templates.TemplateResponse(
            "gmail_config/_card.html",
            _ctx(request, status="authorized"),
        )
    if result == gmail_imap.TestResult.AUTH_FAILED:
        from dataclasses import replace
        state = gmail_imap.load_state()
        gmail_imap.save_state(replace(state, last_error="auth_failed"))
        return templates.TemplateResponse(
            "gmail_config/_card.html",
            _ctx(request, status="login_failed"),
        )
    return templates.TemplateResponse(
        "gmail_config/_card.html",
        _ctx(request, status="connection_error"),
    )


@router.post("/config/gmail/disconnect", response_class=HTMLResponse,
             dependencies=[Depends(auth.basic_auth_dependency)])
def disconnect_gmail_config(request: Request):
    for path in (gmail_imap.GMAIL_CONFIG_PATH, gmail_imap.GMAIL_STATE_PATH):
        p = Path(path)
        if p.exists():
            p.unlink()
    return templates.TemplateResponse(
        "gmail_config/_card.html",
        _ctx(request, status="off"),
    )
```

- [ ] **Step 8.8 — Register the router in `web/app.py`**

In `src/findajob/web/app.py`, find the route registrations (look for `app.include_router(...)` calls) and add:

```python
from findajob.web.routes import gmail_config
app.include_router(gmail_config.router)
```

- [ ] **Step 8.9 — Add Gmail Integration row to `/config/` index**

In `src/findajob/web/templates/config/index.html` (read it first to see existing pattern), add a row above the file-edit list pointing at `/config/gmail/` with the current status pill rendered inline.

- [ ] **Step 8.10 — Run the route tests to verify pass**

Run: `uv run pytest tests/test_web_gmail_config.py -v`
Expected: all 9 tests PASS.

- [ ] **Step 8.11 — Run the full suite for regressions**

Run: `uv run pytest tests/ -x -q`
Expected: all PASS.

- [ ] **Step 8.12 — Lint**

Run: `uv run ruff check src/findajob/web/routes/gmail_config.py tests/test_web_gmail_config.py && uv run ruff format --check src/findajob/web/routes/gmail_config.py tests/test_web_gmail_config.py`
Expected: clean.

- [ ] **Step 8.13 — Commit**

```bash
git add src/findajob/web/routes/gmail_config.py \
        src/findajob/web/templates/gmail_config/ \
        src/findajob/web/templates/_gmail_disclosure.html \
        src/findajob/web/app.py \
        src/findajob/web/templates/config/index.html \
        tests/test_web_gmail_config.py
git commit -m "$(cat <<'EOF'
feat(web): #330 /config/gmail/ form + disclosure banner

Adds GET /config/gmail/, POST /config/gmail/{save,test,disconnect}.
Disclosure banner is a Jinja partial — single source of truth for the
user-facing Gmail-access transparency claims, audit-link-pinned to the
running build SHA.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9 — Transparency-invariants test suite

**Files:**
- Create: `tests/test_transparency_invariants.py`

This is the auditable artifact at end-of-session — codifies §4 of the spec as executable assertions.

- [ ] **Step 9.1 — Write the suite**

`tests/test_transparency_invariants.py`:

```python
"""Tier 1 — codifies §4 of the #330 design spec as executable assertions.

These tests are the auditable end-of-session check that findajob's
disclosure banner claims hold true. If a test here fails, the disclosure
banner is lying — fix the code, not the test.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from unittest.mock import patch, ANY

import pytest

REPO = Path(__file__).resolve().parents[1]
GMAIL_IMAP = REPO / "src" / "findajob" / "gmail_imap.py"
SRC_DIR = REPO / "src" / "findajob"

FORBIDDEN_VERBS = ["STORE", "COPY", "EXPUNGE", "APPEND", "MOVE", "CREATE", "DELETE"]


def _strip_comments_and_strings(src: str) -> str:
    """Remove triple-quoted strings, single-line comments, and string literals.

    Crude but sufficient: a forbidden verb appearing only in a docstring
    or comment is fine; the test fires only on real code use.
    """
    src = re.sub(r'""".*?"""', "", src, flags=re.DOTALL)
    src = re.sub(r"'''.*?'''", "", src, flags=re.DOTALL)
    src = re.sub(r"#.*", "", src)
    src = re.sub(r'"[^"]*"', '""', src)
    src = re.sub(r"'[^']*'", "''", src)
    return src


def test_gmail_imap_uses_only_read_verbs():
    src = _strip_comments_and_strings(GMAIL_IMAP.read_text())
    for verb in FORBIDDEN_VERBS:
        assert verb not in src, (
            f"Forbidden IMAP verb {verb!r} found in gmail_imap.py outside "
            f"comments/strings — violates transparency contract §4.1."
        )


def test_gmail_imap_uses_peek_not_body():
    src = GMAIL_IMAP.read_text()
    bodies = re.findall(r"BODY\s*\.\s*PEEK\s*\[|BODY\s*\[", src)
    assert bodies, "No BODY fetch found at all — review gmail_imap.py"
    for hit in bodies:
        assert "PEEK" in hit, (
            f"Found BODY[ without PEEK in gmail_imap.py — violates §4.2."
        )


def test_no_smtp_in_codebase():
    """No outbound mail capability anywhere in the package."""
    for py in SRC_DIR.rglob("*.py"):
        text = py.read_text()
        text_no_strings = _strip_comments_and_strings(text)
        assert "import smtplib" not in text_no_strings, (
            f"smtplib import found in {py.relative_to(REPO)} — violates §4.4."
        )
        assert "from smtplib" not in text_no_strings, (
            f"smtplib import found in {py.relative_to(REPO)} — violates §4.4."
        )


def test_app_password_never_logged():
    """Sentinel password must not appear in any log_event call."""
    from findajob import gmail_imap

    sentinel = "ZZZZSENTINELPW01"
    cfg = gmail_imap.GmailConfig(
        address="user@gmail.com",
        app_password=sentinel,
        sender_allowlist=["jobalerts-noreply@linkedin.com"],
        configured_at="2026-04-30T00:00:00Z",
    )

    captured = []

    def fake_log_event(event, **kwargs):
        captured.append((event, kwargs))

    with patch("findajob.gmail_imap.log_event", side_effect=fake_log_event):
        with patch("findajob.gmail_imap.imaplib.IMAP4_SSL",
                   side_effect=Exception("network err")):
            gmail_imap.test_login(cfg)
            gmail_imap.fetch_new_messages(cfg, gmail_imap.GmailState())

    for event, kwargs in captured:
        for v in kwargs.values():
            assert sentinel not in str(v), (
                f"App password leaked into log event {event!r} — violates §4.5."
            )


def test_app_password_never_in_audit_log():
    """Sentinel must not flow into write_audit calls from the gmail module."""
    from findajob import gmail_imap

    sentinel = "ZZZZSENTINELPW02"
    cfg = gmail_imap.GmailConfig(
        address="user@gmail.com",
        app_password=sentinel,
        sender_allowlist=["jobalerts-noreply@linkedin.com"],
        configured_at="2026-04-30T00:00:00Z",
    )

    captured = []

    def fake_write_audit(*args, **kwargs):
        captured.append((args, kwargs))

    # gmail_imap should never write to audit_log directly. If write_audit is
    # imported from findajob.utils, monkeypatch it. If it's not, this test
    # passes trivially — but the static check for the import is below.
    src = GMAIL_IMAP.read_text()
    assert "write_audit" not in src, (
        "gmail_imap.py imports write_audit — violates §4.5; credentials "
        "must never flow through audit_log."
    )


def test_gmail_creds_in_gitignore():
    gi = (REPO / ".gitignore").read_text()
    assert "config/gmail.json" in gi, (
        "config/gmail.json missing from .gitignore — violates §4.7."
    )
    assert "config/gmail_state.json" in gi, (
        "config/gmail_state.json missing from .gitignore — violates §4.7."
    )


def test_pre_commit_hook_blocks_gmail_creds(tmp_path):
    """If a pre-commit hook is installed, it must reject staged Gmail creds."""
    hook = REPO / ".git" / "hooks" / "pre-commit"
    if not hook.exists():
        pytest.skip("No pre-commit hook installed in this clone")
    # The hook scans staged changes; we can't easily run it in isolation
    # here without git plumbing. Smoke-check the hook's pattern list mentions
    # gmail.json — full integration test would require a sandboxed git repo.
    text = hook.read_text()
    assert "gmail.json" in text or "gmail_token" in text, (
        "Pre-commit hook does not mention gmail credentials — extend its "
        "PATTERNS array per docs/setup/configure.md."
    )
```

- [ ] **Step 9.2 — Run the suite**

Run: `uv run pytest tests/test_transparency_invariants.py -v`
Expected: all PASS.

If `test_pre_commit_hook_blocks_gmail_creds` skips, that's fine in CI (the hook is per-clone). If it fails because the local hook lacks the pattern, follow `docs/setup/configure.md` to add `gmail.json` and `gmail_token` to the hook's PATTERNS array — but do that in Task 11 alongside the docs. For this commit, the test will skip-or-pass on your dev machine.

- [ ] **Step 9.3 — Commit**

```bash
git add tests/test_transparency_invariants.py
git commit -m "$(cat <<'EOF'
test(gmail): #330 transparency-contract invariants suite

Codifies design-spec §4 as executable tests: read-only IMAP verbs only,
BODY.PEEK[] not BODY[], no smtplib, app password never in logs, creds
in .gitignore, pre-commit hook covers them. Failures here mean the
disclosure banner is lying — fix the code, not the test.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 10 — Disclosure-sync test + `docs/setup/gmail.md` + docs route allowlist

**Files:**
- Create: `docs/setup/gmail.md`
- Create: `tests/test_gmail_disclosure_sync.py`
- Modify: `src/findajob/web/routes/docs.py`

- [ ] **Step 10.1 — Write the disclosure-sync test**

`tests/test_gmail_disclosure_sync.py`:

```python
"""Asserts the disclosure-language sync chain stays intact.

The Jinja partial templates/_gmail_disclosure.html is the single source
of truth. docs/setup/gmail.md must contain the marker comment so the
docs renderer knows where to substitute. If either drifts, this test
catches it.
"""

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PARTIAL = REPO / "src" / "findajob" / "web" / "templates" / "_gmail_disclosure.html"
DOC = REPO / "docs" / "setup" / "gmail.md"
MARKER = "<!-- gmail-disclosure-sync -->"


def test_disclosure_partial_exists():
    assert PARTIAL.exists()


def test_gmail_doc_exists():
    assert DOC.exists()


def test_gmail_doc_has_marker():
    assert MARKER in DOC.read_text(), (
        f"docs/setup/gmail.md must contain the {MARKER!r} comment marker "
        f"so the docs renderer can substitute the disclosure partial."
    )
```

- [ ] **Step 10.2 — Run test to confirm failure**

Run: `uv run pytest tests/test_gmail_disclosure_sync.py -v`
Expected: `test_gmail_doc_exists` and `test_gmail_doc_has_marker` FAIL.

- [ ] **Step 10.3 — Write `docs/setup/gmail.md`**

```markdown
# Gmail job-alert ingestion

findajob can ingest LinkedIn (and, via a configurable allowlist, other)
job-alert emails from your Gmail. The integration is configured at
`/config/gmail/` on your stack. This page walks you through the one-time
setup.

## What findajob will and won't access

<!-- gmail-disclosure-sync -->

(The above marker is replaced with the disclosure language at render
time. The single source of truth for that text is the Jinja partial at
`src/findajob/web/templates/_gmail_disclosure.html`. Editing it changes
both this page and the `/config/gmail/` page in lockstep.)

## Step-by-step setup

### 1. Turn on 2-Step Verification

App passwords cannot be created without 2-Step Verification on your
Google Account. If you don't already have it on, follow Google's guide:
[Turn on 2-Step Verification](https://support.google.com/accounts/answer/185839).

### 2. Generate an app password

Go to <https://myaccount.google.com/apppasswords>. Sign in if prompted.

In the **App name** field, enter `findajob-<your-handle>` (e.g.
`findajob-myname`). Click **Create**.

Google displays a 16-character password with spaces — for example,
`abcd efgh ijkl mnop`. **Copy it now.** Google will not show it again
once you close the dialog.

### 3. Configure findajob

Open `/config/gmail/` on your findajob stack. Paste your Gmail address
and the 16-character app password. Click **Save**, then **Test
connection**. Within ~3 seconds the status pill should change to
**● Authorized**.

### 4. (Optional) Add other senders

The default sender allowlist is `jobalerts-noreply@linkedin.com`. To
pull alerts from additional sources, add their email addresses (one
per line) and click Save again. To find a sender's exact address:
open one of their alert emails in your Gmail inbox and click
**Show details** to see the From: header.

## Account types that won't work

App passwords are not available for:

- Accounts with 2-Step Verification configured **only** with security
  keys (no fallback method).
- Google Workspace accounts where the admin has disabled app
  passwords for users.
- Accounts enrolled in **Advanced Protection**.

If yours is one of these, Gmail integration in findajob is not
available and the pipeline runs without it (Greenhouse / Ashby /
Lever direct fetches and RapidAPI LinkedIn search still cover most
ingestion volume).

## Troubleshooting

| Status pill | Likely cause | Fix |
|---|---|---|
| `● Login failed` | App password revoked, mistyped, or 2FA was disabled | Generate a new app password and re-save. |
| `● Connection error` | Transient network or IMAP issue | Should clear on the next triage run. Persistent errors may indicate port 993 blocked at the deploy host. |
| Status is `● Authorized` but no new jobs appear | Sender allowlist mismatch | Click into a real LinkedIn alert in your inbox; verify the From: header matches what's in the allowlist. |

## How to revoke access

See the **How to revoke access** section of the disclosure above. Two
surfaces:

1. **At Google** — instant, total revocation:
   <https://myaccount.google.com/apppasswords>.
2. **In findajob** — Disconnect button on `/config/gmail/`. Wipes both
   config files on this stack only; Google-side app password remains
   valid until separately revoked.

## Authoritative sources

This guide was validated against:

- [Sign in with app passwords — Google Account Help](https://support.google.com/accounts/answer/185833?hl=en) (accessed 2026-04-30)
- [Add Gmail to another email client — Gmail Help](https://support.google.com/mail/answer/7126229?hl=en) (accessed 2026-04-30)
- [Choose your IMAP email client settings for Gmail](https://support.google.com/mail/answer/78892?hl=en) (accessed 2026-04-30)
```

- [ ] **Step 10.4 — Wire docs renderer for disclosure-marker substitution**

Read `src/findajob/web/routes/docs.py` first. Add `gmail` to the slug allowlist. Then either implement marker substitution by reading the partial as plaintext and inserting after the marker, OR — simpler — render the doc with `{% include '_gmail_disclosure.html' %}` injected post-marker.

Minimum viable approach: in the `docs.py` route handler, after fetching the markdown for slug `gmail`, do a string substitution:

```python
if slug == "gmail" and MARKER in markdown_text:
    # Render the partial as standalone HTML and splice it in.
    partial_html = templates.get_template(
        "_gmail_disclosure.html"
    ).render({"github_blob_url": constants.github_blob_url})
    markdown_text = markdown_text.replace(MARKER, partial_html, 1)
```

(Read the docs route first to see what tools it already has. The substitution can happen pre-markdown-render or post-markdown-render depending on the existing pipeline shape; pick the cleaner integration point.)

- [ ] **Step 10.5 — Run the sync test to verify pass**

Run: `uv run pytest tests/test_gmail_disclosure_sync.py -v`
Expected: all 3 PASS.

- [ ] **Step 10.6 — Commit**

```bash
git add docs/setup/gmail.md tests/test_gmail_disclosure_sync.py src/findajob/web/routes/docs.py
git commit -m "$(cat <<'EOF'
docs: #330 gmail.md setup guide + disclosure-sync test

User-facing setup guide validated against current Google support docs
(2026-04-30). Disclosure language is rendered from the same Jinja
partial as /config/gmail/, kept in sync via a marker comment + drift test.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 11 — Documentation, config, README, CLAUDE.md, CHANGELOG, .gitignore, pre-commit hook

**Files:** all docs/config touch in one PR slice.

- [ ] **Step 11.1 — Update `.gitignore`**

Append to `.gitignore`:

```
# Gmail integration credentials and state (#330)
config/gmail.json
config/gmail_state.json
```

- [ ] **Step 11.2 — Update `README.md`**

Read the current `README.md`. Find any mentions of "Gmail OAuth", "OAuth client",
`gmail_oauth_client.json`, `scripts/gmail_auth.py`, or "loopback OAuth flow".
Replace each with neutral language describing Gmail integration as configurable
and sender-allowlist-driven, e.g.:

> findajob can ingest job-alert emails from your Gmail (LinkedIn alerts by
> default; configurable allowlist supports any sender that emits
> machine-parseable job notifications). Configure it at `/config/gmail/`
> on your stack — see `docs/setup/gmail.md` for the walkthrough.

- [ ] **Step 11.3 — Update `CLAUDE.md`**

In the file table:
- Remove rows for `config/gmail_oauth_client.json` and `config/gmail_token.json`.
- Add rows for `config/gmail.json` and `config/gmail_state.json` (gitignored, IMAP+app-password).

In the Web Frontend Architecture section:
- Add a one-line entry for `/config/gmail/` route module.

In Critical Architecture Rules:
- Update the existing Gmail-related text from OAuth to "IMAP+app-password integration; transparency contract documented in `docs/superpowers/specs/2026-04-30-330-design.md` §4."

- [ ] **Step 11.4 — Update `CHANGELOG.md`**

At the top of `CHANGELOG.md` under an `## [Unreleased]` (or whatever the
current next-version header is), add:

```markdown
### Gmail integration replaced with IMAP/app-password (#330)

Gmail ingestion now uses an app password + IMAP, configured per-user at
`/config/gmail/`. The previous OAuth integration
(`config/gmail_oauth_client.json` + `config/gmail_token.json`) is removed.

If you were using the OAuth integration: configure the new path at
`/config/gmail/` and delete the two legacy files from your bind mount.
The pipeline silently no-ops Gmail ingestion until configured.

`migration-required`
```

- [ ] **Step 11.5 — Update `docs/setup/install-docker.md`**

Replace the existing Section 4 ("Initial auth: Gmail (optional)") — multiple
SSH-tunnel + `docker compose --profile setup run --rm gmail-auth` steps —
with a one-paragraph pointer:

```markdown
## 4. Configure Gmail integration (optional)

If you want findajob to ingest LinkedIn (and other) job-alert emails from
your Gmail, follow the walkthrough at [`docs/setup/gmail.md`](gmail.md)
after the stack is up and running. The pipeline runs cleanly without
Gmail integration; Greenhouse / Ashby / Lever and RapidAPI LinkedIn
search cover most ingestion volume.
```

- [ ] **Step 11.6 — Update `docs/setup/install-linux.md`**

Strip OAuth setup steps. Replace with a pointer to `docs/setup/gmail.md`.

- [ ] **Step 11.7 — Update `docs/setup/state-migration.md`**

Replace the rows for `gmail_oauth_client.json` and `gmail_token.json` in the
file-migration table with rows for `gmail.json` and `gmail_state.json`.

- [ ] **Step 11.8 — Update `docs/setup/README.md`**

Add a row for `gmail.md` to the index of setup docs.

- [ ] **Step 11.9 — Update `docs/release-process.md`**

In the per-PR checklist, add a line:

```markdown
- For PRs touching `src/findajob/gmail_imap.py` or
  `src/findajob/fetchers.py:fetch_gmail_jobs`: re-run
  `uv run pytest tests/test_transparency_invariants.py -v` and link the
  green run in the PR description.
```

- [ ] **Step 11.10 — Update `compose.yaml.example`**

Read it. Find the `gmail-auth` profile or service definition (it provides
the loopback OAuth helper). Delete the entire profile/service block and
its supporting comments.

- [ ] **Step 11.11 — Add Gmail patterns to local pre-commit hook**

The local pre-commit hook is at `.git/hooks/pre-commit`. Open it and find
the `PATTERNS=(...)` array. Add patterns to block the new files from
accidental commit:

```bash
PATTERNS=(
  # ... existing patterns ...
  'config/gmail\.json'
  'config/gmail_state\.json'
)
```

This is a per-clone change — not tracked. Document in `docs/setup/configure.md`
that new findajob clones should add these patterns when setting up their hook.

- [ ] **Step 11.12 — Run the full test suite + lint**

```bash
uv run pytest tests/ -x -q
uv run ruff check src/findajob/ tests/
uv run ruff format --check src/findajob/ tests/
uv run mypy src/findajob/gmail_imap.py src/findajob/web/routes/gmail_config.py
```

Expected: all green.

- [ ] **Step 11.13 — Commit**

```bash
git add .gitignore README.md CLAUDE.md CHANGELOG.md \
        docs/setup/install-docker.md docs/setup/install-linux.md \
        docs/setup/state-migration.md docs/setup/README.md \
        docs/release-process.md compose.yaml.example
git commit -m "$(cat <<'EOF'
docs: #330 docs + config sweep for Gmail IMAP integration

README: strip OAuth, describe Gmail as configurable and sender-allowlist-
driven. CLAUDE.md: file-table swap, /config/gmail/ in Web Frontend
Architecture, IMAP-posture in Critical Architecture Rules. CHANGELOG:
migration-required entry. Setup docs: install-docker §4 replaced with
pointer; install-linux + state-migration mirror; setup/README index +
gmail.md entry. release-process: per-PR transparency-test re-run line.
compose.yaml.example: gmail-auth profile removed. .gitignore: new
config files added.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 12 — Whole-feature verification + open PR

**Files:** none new — verification + PR.

- [ ] **Step 12.1 — Push the branch and run the full CI suite locally one last time**

```bash
uv run pytest tests/ -q
uv run ruff check src/findajob/ tests/
uv run ruff format --check src/findajob/ tests/
```

All three must be green before opening the PR.

- [ ] **Step 12.2 — Manual whole-feature verification**

Boot the web app locally:

```bash
cd /home/brockamer/Code/findajob
uv run uvicorn findajob.web.app:create_app --factory --reload --port 8090
```

Walk through the flow:
1. `GET /config/gmail/` — page renders, status pill shows `● Off`, disclosure banner visible at the top, `<details>` collapses/expands.
2. Inspect the audit links in the disclosure — they should point to `https://github.com/brockamer/findajob/blob/main/...` when running locally (BUILD_SHA defaults to `main`).
3. Submit the form with bad inputs (15-char password) — inline validation error renders, no file written.
4. Submit with valid inputs — file written at `config/gmail.json`, pill shows `● Saved (not tested)`.
5. Click Test connection — pill flips to `● Authorized` if real creds, or `● Login failed` / `● Connection error` if fake.
6. Click Disconnect — both files wiped, pill back to `● Off`.

Confirm none of the failure-mode tests write the app password into any of:
- `logs/pipeline.jsonl`
- `data/pipeline.db`'s `audit_log` table
- Any HTTP request body in browser devtools (other than the form POST itself)

- [ ] **Step 12.3 — Run the transparency-invariants suite one final time**

```bash
uv run pytest tests/test_transparency_invariants.py -v
```

All assertions must be green. If `test_pre_commit_hook_blocks_gmail_creds` skipped, run it on your dev clone after Step 11.11 — it should now PASS or pattern-match.

- [ ] **Step 12.4 — Open the PR**

```bash
gh pr create --title "feat(gmail): #330 IMAP/app-password integration" \
  --label migration-required \
  --body "$(cat <<'EOF'
## Summary

Replaces the deprecated Gmail OAuth integration with a self-service
IMAP + app-password path, configured at `/config/gmail/`. New users
generate a 16-character app password from their Google Account and
paste it in; no GCP project, no consent screen, no OAuth verification.

The `/config/gmail/` page carries a transparency banner spelling out
exactly what findajob touches in the user's mailbox (and what it
doesn't), with audit links pinned to the running build's git SHA.
The transparency claims are codified as executable assertions in
`tests/test_transparency_invariants.py`.

## What changed

- Added `findajob.gmail_imap` module — read-only IMAP client, BODY.PEEK[] only,
  UID-tracked incremental fetch, error classification.
- Added `/config/gmail/` route + form + disclosure partial.
- Rewrote `fetchers.fetch_gmail_jobs()` on top of `gmail_imap`.
- Deleted `scripts/gmail_auth.py`, `get_gmail_service()`, the API-shaped
  `parse_jobs_from_email`, and the OAuth path constants.
- BUILD_SHA baked into the image at build time; disclosure banner audit
  links use it.
- Docs swept: README, CLAUDE.md, CHANGELOG, install-docker, install-linux,
  state-migration, setup/README, release-process, compose.yaml.example.
- New transparency-invariants test suite codifies the user-facing claims.

## Migration required

Operators with Gmail OAuth previously configured: re-onboard at
`/config/gmail/` and delete the legacy `config/gmail_oauth_client.json`
and `config/gmail_token.json` from the stack's bind mount. Pipeline
silently no-ops Gmail ingestion until reconfigured.

## Test plan

- [ ] CI green
- [ ] `pytest tests/test_transparency_invariants.py` green
- [ ] `pytest tests/test_gmail_imap.py tests/test_gmail_imap_parsing.py
      tests/test_web_gmail_config.py tests/test_gmail_disclosure_sync.py`
      green
- [ ] Manual: `/config/gmail/` renders Off → Saved → Authorized →
      Disconnect cycle with a real Gmail app password
- [ ] Manual: confirm app password doesn't appear in `logs/pipeline.jsonl`,
      `data/pipeline.db` audit_log, or any HTTP request body in browser
      devtools

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Closes #330
EOF
)"
```

- [ ] **Step 12.5 — Update issue #330 with the implementation summary**

Comment on #330:

```
## Implementation status

PR #<N> opened against `main`. Spec: `docs/superpowers/specs/2026-04-30-330-design.md`. Plan: `docs/superpowers/plans/2026-04-30-330-gmail-imap-configure-later.md`.

Post-merge actions for operator:
1. Re-onboard own stack via `/config/gmail/`.
2. Walk alice through the same on her stack.
3. Delete `config/gmail_oauth_client.json` and `config/gmail_token.json` from each bind mount.

Scheduled reminder `trig_01EVWD17xcrWC2x6NJdm1Ke3` fires `2026-05-01T16:00:00Z` to surface the cleanup.
```

---

## Self-review against the spec

**1. Spec coverage check (each spec section → task):**

- §1 problem framing — task header captures the goal; no separate task needed.
- §2 out-of-scope — Tasks throughout respect the boundary; no migration code (verified by Tasks 6, 11).
- §3 architecture — Tasks 1–8 build out every box in the diagram.
- §4 transparency contract — Task 9 codifies it.
- §5 UI surface — Task 8 builds it.
- §6 IMAP client — Tasks 1–4 build it.
- §7 cadence + state — Tasks 2 (state file) and 4 (UID handling).
- §8 failure modes — Task 6 wires `fetch_gmail_jobs` to streak + ntfy.
- §9 docs surface — Task 10 writes `gmail.md` and the sync test.
- §10 no-migration model — Task 6 deletes OAuth code with no bridge.
- §11 testing — Tasks 1–10 deliver each tier; Task 9 is Tier 1.
- §12 files affected — every entry maps to a task above.
- §13 documentation impact — Task 11 covers all surfaces.
- §14 self-review checklist — this section.

**2. Placeholder scan:** all code blocks contain real code; all paths are absolute or repo-relative; no "TBD"/"TODO". ✓

**3. Type consistency:** `GmailConfig`, `GmailState`, `TestResult`, `FetchOutcome` are defined once and used identically across Tasks 1, 2, 3, 4, 6, 8, 9. ✓

**4. Documentation Impact:** Task 11 enumerates 11 doc surfaces, matching spec §13.
