"""Board Review tab."""

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from findajob.onboarding import mark_complete
from findajob.web.app import create_app
from tests.conftest import init_test_db


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    db = tmp_path / "pipeline.db"
    init_test_db(db)
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO jobs (id, fingerprint, url, title, company, "
        "stage, score_flag_reason, source, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "jid-rev",
            "fp-rev",
            "https://x.test/rev",
            "Ambiguous Title",
            "Meta",
            "manual_review",
            "target company bump",
            "greenhouse",
            "2026-04-20",
        ),
    )
    conn.execute(
        "INSERT INTO jobs (id, fingerprint, url, title, company, source, stage) "
        "VALUES ('jid-sc','fp-scored','https://x.test/sc','Other','Acme','test','scored')"
    )
    conn.commit()
    conn.close()
    companies = tmp_path / "companies"
    companies.mkdir()
    mark_complete(tmp_path)
    return TestClient(create_app(companies_root=companies, db_path=db, base_root=tmp_path))


def test_review_shows_manual_review_only(client: TestClient) -> None:
    r = client.get("/board/review")
    assert r.status_code == 200
    assert "Ambiguous Title" in r.text
    # fp-scored isn't in manual_review, so its row should not render.
    # Match the fingerprint attribute — "Other" as a bare word now appears in
    # the reject-reason dropdown for every rendered row.
    assert 'data-fingerprint="fp-scored"' not in r.text
    assert "target company bump" in r.text
