"""Regression test for #628 — route-raised HTTPException(>=500) logs to pipeline.jsonl.

Without the app-level exception handler, FastAPI emits the detail string only
to the client and the operator sees just "500 Internal Server Error" in
container logs. The handler in ``findajob.web.app.create_app`` logs path +
status + detail to ``log_event("http_5xx", ...)``, then delegates rendering
to FastAPI's default so response shape is unchanged.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from findajob.web.app import create_app

_MINIMAL_SCHEMA = """
CREATE TABLE jobs (
    id TEXT,
    fingerprint TEXT,
    title TEXT,
    company TEXT,
    stage TEXT,
    relevance_score INTEGER,
    fit_score REAL,
    probability_score REAL,
    interview_likelihood INTEGER,
    location TEXT,
    remote_status TEXT,
    known_contacts TEXT,
    comp_estimate TEXT,
    ai_notes TEXT,
    created_at TEXT,
    stage_updated TEXT,
    url TEXT,
    prep_folder_path TEXT,
    synthetic INTEGER NOT NULL DEFAULT 0
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

    async def _raise_500() -> None:
        raise HTTPException(status_code=500, detail="boom")

    async def _raise_503() -> None:
        raise HTTPException(status_code=503, detail="upstream gone")

    async def _raise_404() -> None:
        raise HTTPException(status_code=404, detail="missing")

    app.add_api_route("/__test_500", _raise_500, methods=["GET"])
    app.add_api_route("/__test_503", _raise_503, methods=["GET"])
    app.add_api_route("/__test_404", _raise_404, methods=["GET"])
    return TestClient(app)


def test_500_logs_structured_http_5xx_event(client: TestClient) -> None:
    with patch("findajob.web.app.log_event") as mock_log:
        resp = client.get("/__test_500")
    assert resp.status_code == 500
    assert resp.json() == {"detail": "boom"}
    mock_log.assert_called_once_with(
        "http_5xx",
        path="/__test_500",
        status=500,
        detail="boom",
    )


def test_503_also_logs_http_5xx(client: TestClient) -> None:
    with patch("findajob.web.app.log_event") as mock_log:
        resp = client.get("/__test_503")
    assert resp.status_code == 503
    mock_log.assert_called_once()
    args, kwargs = mock_log.call_args
    assert args == ("http_5xx",)
    assert kwargs["status"] == 503
    assert kwargs["detail"] == "upstream gone"


def test_404_does_not_log_http_5xx(client: TestClient) -> None:
    """AC #4: 4xx must not spam the log."""
    with patch("findajob.web.app.log_event") as mock_log:
        resp = client.get("/__test_404")
    assert resp.status_code == 404
    mock_log.assert_not_called()
