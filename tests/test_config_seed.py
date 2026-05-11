"""Tests for fresh-install runtime-config seeding (#627)."""

from __future__ import annotations

from pathlib import Path

from findajob.config_seed import seed_runtime_config


def test_seed_creates_rapidapi_feeds_from_example(tmp_path: Path) -> None:
    """Fresh install: only .example present, helper materializes the live file."""
    config = tmp_path / "config"
    config.mkdir()
    example_body = "default: jobs-api14\nadapters:\n  - name: jobs-api14\n"
    (config / "rapidapi_feeds.yaml.example").write_text(example_body)

    created = seed_runtime_config(tmp_path)

    live = config / "rapidapi_feeds.yaml"
    assert live.exists()
    assert live.read_text() == example_body
    assert created == [live]


def test_seed_does_not_overwrite_existing_live_file(tmp_path: Path) -> None:
    """Operator-edited live file survives container restarts — seed is one-shot."""
    config = tmp_path / "config"
    config.mkdir()
    (config / "rapidapi_feeds.yaml.example").write_text("default: jobs-api14\n")
    operator_body = "default: jsearch\n# operator picked a different default\n"
    (config / "rapidapi_feeds.yaml").write_text(operator_body)

    created = seed_runtime_config(tmp_path)

    assert (config / "rapidapi_feeds.yaml").read_text() == operator_body
    assert created == []


def test_seed_noop_when_example_missing(tmp_path: Path) -> None:
    """Hostile state (bundled-config didn't seed .example): helper returns
    cleanly rather than raising — entrypoint must remain idempotent."""
    config = tmp_path / "config"
    config.mkdir()

    created = seed_runtime_config(tmp_path)

    assert not (config / "rapidapi_feeds.yaml").exists()
    assert created == []


def test_seed_idempotent_on_second_run(tmp_path: Path) -> None:
    """Two back-to-back runs (e.g. a restart loop) must not double-write."""
    config = tmp_path / "config"
    config.mkdir()
    (config / "rapidapi_feeds.yaml.example").write_text("default: jobs-api14\n")

    first = seed_runtime_config(tmp_path)
    second = seed_runtime_config(tmp_path)

    assert len(first) == 1
    assert second == []


def test_feed_config_route_works_against_entrypoint_seeded_fixture(tmp_path: Path) -> None:
    """End-to-end: after the helper runs (mirroring entrypoint behavior on a
    fresh stack), GET /onboarding/feed-config/{sid} returns 200 instead of 500.

    This is the #627 reproducer — the test fails pre-fix because the route
    handler 500s with ``Curation file not found: .../rapidapi_feeds.yaml``.
    """
    import shutil
    import sqlite3

    from fastapi.testclient import TestClient

    from findajob.web.app import create_app

    repo_root = Path(__file__).parent.parent
    (tmp_path / "data").mkdir()
    (tmp_path / "companies").mkdir()
    (tmp_path / "candidate_context").mkdir()
    (tmp_path / "config").mkdir()

    # Mirror what the container does at start: bundled-config seeds the
    # .example into the bind-mount config dir.
    shutil.copy(
        repo_root / "config" / "rapidapi_feeds.yaml.example",
        tmp_path / "config" / "rapidapi_feeds.yaml.example",
    )
    # Onboarding has emitted active_sources.txt (the prior step).
    (tmp_path / "config" / "active_sources.txt").write_text("jsearch\n")

    # Schema for the app factory.
    from findajob.db.migrate import apply_pending

    conn = sqlite3.connect(tmp_path / "data" / "pipeline.db")
    try:
        apply_pending(conn)
    finally:
        conn.close()

    # ── The fix under test ──
    seed_runtime_config(tmp_path)

    app = create_app(
        companies_root=tmp_path / "companies",
        db_path=tmp_path / "data" / "pipeline.db",
        base_root=tmp_path,
    )
    client = TestClient(app, follow_redirects=False)
    resp = client.get("/onboarding/feed-config/test-session-id")
    assert resp.status_code == 200, resp.text
    # Sanity: the rendered form picked up the operator's chosen adapter.
    assert "JSearch" in resp.text
