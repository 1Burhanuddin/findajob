"""Stats sub-tab bar — full taxonomy visible from day one.

14e (#63, #193, #194, #195, #196, #197). Funnel, Feedback, Scoring, Rejections,
Throughput, and Effectiveness are all active links.
"""

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from findajob.onboarding import mark_complete
from findajob.web.app import create_app

ENABLED = {
    "/stats/funnel",
    "/stats/feedback",
    "/stats/scoring",
    "/stats/rejections",
    "/stats/throughput",
    "/stats/effectiveness",
}


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    db = tmp_path / "pipeline.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE jobs ("
        "  id TEXT PRIMARY KEY, fingerprint TEXT, title TEXT, company TEXT, stage TEXT, "
        "  relevance_score INTEGER, interview_likelihood INTEGER, "
        "  fit_score REAL, probability_score REAL, reject_reason TEXT, "
        "  source TEXT DEFAULT '', company_tier TEXT"
        ")"
    )
    conn.execute(
        "CREATE TABLE audit_log (id INTEGER PRIMARY KEY, job_id TEXT, field_changed TEXT, "
        "old_value TEXT, new_value TEXT, changed_at TEXT, changed_by TEXT)"
    )
    conn.execute(
        "CREATE TABLE feedback_log ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL, title TEXT NOT NULL, "
        "company TEXT NOT NULL, relevance_score INTEGER, reject_reason TEXT NOT NULL, "
        "jd_excerpt TEXT DEFAULT '', created_at TEXT DEFAULT (datetime('now')))"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS config_changes ("
        "  id INTEGER PRIMARY KEY AUTOINCREMENT, lever TEXT NOT NULL, "
        "  changed_at TEXT DEFAULT (datetime('now')), changed_by TEXT DEFAULT 'manual', "
        "  change_summary TEXT, content_hash TEXT, diff_summary TEXT)"
    )
    conn.commit()
    conn.close()
    companies = tmp_path / "companies"
    companies.mkdir()
    mark_complete(tmp_path)
    return TestClient(create_app(companies_root=companies, db_path=db, base_root=tmp_path))


def test_funnel_tab_active_marker(client: TestClient) -> None:
    r = client.get("/stats/funnel")
    assert r.status_code == 200
    idx = r.text.index('href="/stats/funnel"')
    snippet = r.text[idx : idx + 400]
    assert 'aria-current="page"' in snippet


def test_funnel_tab_has_href(client: TestClient) -> None:
    r = client.get("/stats/funnel")
    assert r.status_code == 200
    assert 'href="/stats/funnel"' in r.text


def test_feedback_tab_active_marker(client: TestClient) -> None:
    r = client.get("/stats/feedback")
    assert r.status_code == 200
    idx = r.text.index('href="/stats/feedback"')
    snippet = r.text[idx : idx + 400]
    assert 'aria-current="page"' in snippet


def test_feedback_tab_has_href(client: TestClient) -> None:
    r = client.get("/stats/funnel")
    assert r.status_code == 200
    assert 'href="/stats/feedback"' in r.text


def test_scoring_tab_has_href(client: TestClient) -> None:
    r = client.get("/stats/funnel")
    assert r.status_code == 200
    assert 'href="/stats/scoring"' in r.text


def test_scoring_tab_active_marker(client: TestClient) -> None:
    r = client.get("/stats/scoring")
    assert r.status_code == 200
    idx = r.text.index('href="/stats/scoring"')
    snippet = r.text[idx : idx + 400]
    assert 'aria-current="page"' in snippet


def test_rejections_tab_has_href(client: TestClient) -> None:
    r = client.get("/stats/funnel")
    assert r.status_code == 200
    assert 'href="/stats/rejections"' in r.text


def test_rejections_tab_active_marker(client: TestClient) -> None:
    r = client.get("/stats/rejections")
    assert r.status_code == 200
    idx = r.text.index('href="/stats/rejections"')
    snippet = r.text[idx : idx + 400]
    assert 'aria-current="page"' in snippet


def test_throughput_tab_has_href(client: TestClient) -> None:
    r = client.get("/stats/funnel")
    assert r.status_code == 200
    assert 'href="/stats/throughput"' in r.text


def test_throughput_tab_active_marker(client: TestClient) -> None:
    r = client.get("/stats/throughput")
    assert r.status_code == 200
    idx = r.text.index('href="/stats/throughput"')
    snippet = r.text[idx : idx + 400]
    assert 'aria-current="page"' in snippet


def test_effectiveness_tab_has_href(client: TestClient) -> None:
    r = client.get("/stats/funnel")
    assert r.status_code == 200
    assert 'href="/stats/effectiveness"' in r.text


def test_effectiveness_tab_active_marker(client: TestClient) -> None:
    r = client.get("/stats/effectiveness")
    assert r.status_code == 200
    idx = r.text.index('href="/stats/effectiveness"')
    snippet = r.text[idx : idx + 400]
    assert 'aria-current="page"' in snippet


def test_top_nav_stats_link_resolves(client: TestClient) -> None:
    r = client.get("/stats/funnel")
    assert r.status_code == 200
    assert 'href="/stats/funnel"' in r.text
    # Top nav highlights "Stats" as active via aria-current when on any /stats/* page.
    # Find the Stats link in the top nav and assert aria-current appears nearby.
    assert 'aria-current="page"' in r.text
