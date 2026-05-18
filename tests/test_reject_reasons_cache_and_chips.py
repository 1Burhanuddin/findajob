"""End-to-end regression: save_reject_reasons() → next request reflects.

Pins the contract: after save_reject_reasons() is called the next HTTP
request against both the board reject-reason dropdown
(Jinja global reject_reason_options, /board/dashboard) and the
/board/rejected/ filter chip values (ColumnSpec.resolved_enum_values)
returns the updated reasons — with NO restart, cache reset, or
_reset_cache() call. (#490)
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from findajob.onboarding import mark_complete
from findajob.web.app import create_app
from tests.conftest import init_test_db


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    # 1. Point _REJECT_REASONS_PATH at a tmpdir YAML before create_app().
    yaml_path = tmp_path / "reject_reasons.yaml"
    yaml_path.write_text("reasons:\n  - Initial Reason\n")
    from findajob import config_loader

    monkeypatch.setattr(config_loader, "_REJECT_REASONS_PATH", yaml_path)

    # 2. Schema via production migration runner.
    db = tmp_path / "pipeline.db"
    init_test_db(db)
    conn = sqlite3.connect(db)
    # A high-scoring dashboard row (score >= 7 passes the default floor).
    conn.execute(
        "INSERT INTO jobs (id, fingerprint, url, title, company, source, stage, relevance_score) "
        "VALUES ('id-dash','fp-dash','https://example.com/j1','Staff Eng','Meta','test','scored',9)"
    )
    # A rejected row — ensures /board/rejected/ renders filter chips even with data.
    # Use a reject_reason value that is NOT one of the YAML reasons being tested
    # so that row-data text doesn't interfere with chip-value assertions.
    conn.execute(
        "INSERT INTO jobs (id, fingerprint, url, title, company, source, stage, reject_reason) "
        "VALUES ('id-rej','fp-rej','https://example.com/j2','Old Role','Acme','test','rejected','Geography')"
    )
    conn.execute(
        "INSERT INTO audit_log (job_id, field_changed, old_value, new_value, "
        "changed_at, changed_by) "
        "VALUES ('id-rej','stage','scored','rejected','2026-01-01 00:00:00','user')"
    )
    conn.commit()
    conn.close()

    companies = tmp_path / "companies"
    companies.mkdir()
    mark_complete(tmp_path)

    return TestClient(create_app(companies_root=companies, db_path=db, base_root=tmp_path))


def test_dropdown_reflects_save_without_restart(client: TestClient, tmp_path: Path) -> None:
    """Save → board reject-reason dropdown reflects on next request."""
    resp = client.get("/board/dashboard")
    assert resp.status_code == 200
    assert "Initial Reason" in resp.text

    from findajob.config_loader import save_reject_reasons

    save_reject_reasons(("Brand New Reason",), frozenset())

    # Same client, no restart, no _reset_cache. Next request must reflect.
    resp = client.get("/board/dashboard")
    assert resp.status_code == 200
    assert "Brand New Reason" in resp.text
    assert "Initial Reason" not in resp.text


def test_filter_chips_reflect_save_without_restart(client: TestClient, tmp_path: Path) -> None:
    """Save → /board/rejected filter chip values reflect on next request."""
    resp = client.get("/board/rejected")
    assert resp.status_code == 200
    assert "Initial Reason" in resp.text

    from findajob.config_loader import save_reject_reasons

    save_reject_reasons(("Updated Reason",), frozenset())

    resp = client.get("/board/rejected")
    assert resp.status_code == 200
    assert "Updated Reason" in resp.text
    assert "Initial Reason" not in resp.text
