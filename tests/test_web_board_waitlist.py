"""Board Waitlist tab — shows waitlisted jobs and computes blocking_app subquery."""

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
    # Meta has two jobs: one waitlisted (with all scores), one actively applied
    conn.execute(
        "INSERT INTO jobs (id, fingerprint, url, title, company, source, "
        "stage, relevance_score, fit_score, probability_score, "
        "interview_likelihood, stage_updated) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "id-wait",
            "fp-wait",
            "https://x.test/wait",
            "Ops Lead",
            "Meta",
            "test",
            "waitlisted",
            8,
            72.0,
            55.0,
            8,
            "2026-04-18",
        ),
    )
    conn.execute(
        "INSERT INTO jobs (id, fingerprint, url, title, company, source, stage, stage_updated) "
        "VALUES ('id-blocker','fp-blocker','https://x.test/blocker','NPI PM','Meta','test','applied','2026-04-20')"
    )
    # Anthropic has only a waitlisted job with NULL fit/prob scores — should render a dash
    conn.execute(
        "INSERT INTO jobs (id, fingerprint, url, title, company, source, stage, relevance_score) "
        "VALUES ('id-solo','fp-solo','https://x.test/solo','Eng','Anthropic','test','waitlisted',6)"
    )
    conn.commit()
    conn.close()
    companies = tmp_path / "companies"
    companies.mkdir()
    mark_complete(tmp_path)
    return TestClient(create_app(companies_root=companies, db_path=db, base_root=tmp_path))


def test_waitlist_shows_waitlisted_and_blocking_app(client: TestClient) -> None:
    r = client.get("/board/waitlist")
    assert r.status_code == 200
    assert "Ops Lead" in r.text
    assert "Eng" in r.text
    # Meta's blocking app appears in the same row
    assert "NPI PM" in r.text
    assert "applied" in r.text


def test_waitlist_shows_fit_and_likelihood_scores(client: TestClient) -> None:
    """#237/#273: waitlist view surfaces fit_score + interview_likelihood for triage ranking.
    probability_score is now default_visible=False (hidden-by-default); interview_likelihood
    replaces it as the default-visible scoring column on Waitlist."""
    r = client.get("/board/waitlist")
    assert r.status_code == 200
    # Meta 'Ops Lead' row has fit_score=72.0, interview_likelihood=55.0 — both render.
    assert "72" in r.text
    assert "55" in r.text


def test_waitlist_renders_dash_for_null_scores(client: TestClient) -> None:
    """#237: NULL fit/prob scores render as '—' dash, not 0, so zero-signal rows don't
    get mistaken for real zeros. Anthropic 'Eng' row has NULL in both columns."""
    r = client.get("/board/waitlist")
    assert r.status_code == 200
    # Scope the check to the Anthropic <tr> so nav/header em-dashes don't leak in.
    anthropic_idx = r.text.find("Anthropic")
    assert anthropic_idx > 0, "Anthropic row not rendered"
    row_end = r.text.find("</tr>", anthropic_idx)
    assert row_end > anthropic_idx, "malformed HTML — no </tr> after Anthropic"
    row = r.text[anthropic_idx:row_end]
    # Expect at least two em-dashes in the row — one for NULL fit_score, one for NULL probability_score
    assert row.count("—") >= 2, f"expected >=2 em-dashes in Anthropic row, got {row.count('—')}: {row[:500]}"
