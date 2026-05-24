"""Phase B failure behavior tests (post-#840 refactor).

Extracted from the #738 Phase B progress test suite. The per-step ntfy
progress pings and ``.phase_b_step`` sidecar writes were removed in #840;
the failure-path tests survive because they pin real behavioral contracts:

1. Phase B subprocess failure resets stage to ``briefing_ready``.
2. Phase B failure fires exactly one failure notification (not duplicate).
"""

from __future__ import annotations

import sqlite3
import subprocess
from pathlib import Path

import pytest

from tests.test_prep_phase_split import (
    COMPANY,
    FAKE_JD,
    FAKE_MASTER_RESUME,
    FAKE_PROFILE,
    FP,
    JOB_ID,
    SCHEMA,
    TITLE,
    URL,
    _fake_run_role,
)


@pytest.fixture()
def isolated_base(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    candidate = tmp_path / "candidate_context"
    candidate.mkdir()
    (candidate / "profile.md").write_text(FAKE_PROFILE)
    (candidate / "master_resume.md").write_text(FAKE_MASTER_RESUME)
    (tmp_path / "companies").mkdir()
    (tmp_path / "data").mkdir()
    db_path = tmp_path / "data" / "pipeline.db"

    conn = sqlite3.connect(str(db_path))
    conn.executescript(SCHEMA)
    conn.close()

    import findajob.prep.orchestrator as orch

    monkeypatch.setattr(orch, "BASE", str(tmp_path))
    monkeypatch.setattr(orch, "DB_PATH", str(db_path))
    monkeypatch.setattr(orch, "PROFILE_PATH", str(candidate / "profile.md"))
    monkeypatch.setattr(orch, "MASTER_RESUME_PATH", str(candidate / "master_resume.md"))
    return tmp_path


@pytest.fixture()
def mocked_orchestrator(monkeypatch: pytest.MonkeyPatch) -> None:
    import findajob.prep.orchestrator as orch

    monkeypatch.setattr(orch, "run_role", _fake_run_role)
    monkeypatch.setattr(orch, "render_md_to_docx", lambda *args, **kwargs: None)
    monkeypatch.setattr(orch, "_add_cover_letter_spacing", lambda *args, **kwargs: None)
    monkeypatch.setattr(orch, "_linkify_contact_info", lambda s: s)
    monkeypatch.setattr(orch, "ntfy_send", lambda *args, **kwargs: None)
    monkeypatch.setattr(orch, "load_voice_samples", lambda: "")
    monkeypatch.setattr(orch, "read_file_prefix", lambda: "TST")
    monkeypatch.setattr(orch, "quarantine_stale_prep_folders", lambda *args, **kwargs: None)

    real_subprocess_run = subprocess.run

    def _fake_subprocess_run(cmd, *args, **kwargs):
        if isinstance(cmd, list) and len(cmd) > 1 and "find_contacts.py" in str(cmd[1]):
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=b"", stderr=b"")
        if isinstance(cmd, list) and len(cmd) > 1 and "validate_resume.py" in str(cmd[1]):
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=b"", stderr=b"")
        return real_subprocess_run(cmd, *args, **kwargs)

    monkeypatch.setattr(orch.subprocess, "run", _fake_subprocess_run)


@pytest.fixture()
def isolate_event_log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    log_path = tmp_path / "pipeline.jsonl"
    monkeypatch.setattr("findajob.audit.LOG_PATH", str(log_path))
    return log_path


def _seed_briefing_ready_job(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO jobs (id, fingerprint, url, title, company, source, stage, raw_jd_text) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (JOB_ID, FP, URL, TITLE, COMPANY, "test", "prep_in_progress", FAKE_JD),
    )
    conn.commit()
    conn.close()


def _stand_up_briefing_folder(base: Path, job_id: str) -> Path:
    folder = base / "companies" / "Acme" / f"prep-{job_id}"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "briefing.md").write_text("# Briefing\n\nContext.\n\n## Overall Recommendation\n\nApply.\n")

    db_path = base / "data" / "pipeline.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "UPDATE jobs SET prep_folder_path=?, fit_score=80, probability_score=60 WHERE id=?",
        (str(folder), job_id),
    )
    conn.commit()
    conn.close()
    return folder


def test_phase_b_failure_resets_stage_to_briefing_ready(
    isolated_base, mocked_orchestrator, isolate_event_log, monkeypatch
) -> None:
    import findajob.prep.orchestrator as orch
    from findajob.prep.orchestrator import _run_prep_phase_b

    db_path = str(isolated_base / "data" / "pipeline.db")
    _seed_briefing_ready_job(db_path)
    _stand_up_briefing_folder(isolated_base, JOB_ID)

    def _failing_subprocess_run(cmd, *args, **kwargs):
        if isinstance(cmd, list) and len(cmd) > 1 and "find_contacts.py" in str(cmd[1]):
            raise subprocess.CalledProcessError(1, cmd)
        if isinstance(cmd, list) and len(cmd) > 1 and "validate_resume.py" in str(cmd[1]):
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=b"", stderr=b"")
        raise RuntimeError(f"unexpected subprocess call: {cmd}")

    monkeypatch.setattr(orch.subprocess, "run", _failing_subprocess_run)

    with pytest.raises(SystemExit):
        _run_prep_phase_b(COMPANY, TITLE, URL, JOB_ID)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT stage FROM jobs WHERE id=?", (JOB_ID,)).fetchone()
    conn.close()
    assert row["stage"] == "briefing_ready", f"failure must reset stage to briefing_ready; got {row['stage']!r}"


def test_phase_b_failure_fires_single_notification(
    isolated_base, mocked_orchestrator, isolate_event_log, monkeypatch
) -> None:
    """Phase B failure must fire exactly one prep_failure notification."""
    import findajob.prep.orchestrator as orch
    from findajob.prep.orchestrator import _run_prep_phase_b

    db_path = str(isolated_base / "data" / "pipeline.db")
    _seed_briefing_ready_job(db_path)
    _stand_up_briefing_folder(isolated_base, JOB_ID)

    notif_spy: list[tuple] = []
    monkeypatch.setattr(orch, "ntfy_send", lambda *args, **kwargs: notif_spy.append((args, kwargs)))

    def _failing_subprocess_run(cmd, *args, **kwargs):
        if isinstance(cmd, list) and len(cmd) > 1 and "find_contacts.py" in str(cmd[1]):
            raise subprocess.CalledProcessError(1, cmd)
        if isinstance(cmd, list) and len(cmd) > 1 and "validate_resume.py" in str(cmd[1]):
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=b"", stderr=b"")
        raise RuntimeError(f"unexpected subprocess call: {cmd}")

    monkeypatch.setattr(orch.subprocess, "run", _failing_subprocess_run)

    with pytest.raises(SystemExit):
        _run_prep_phase_b(COMPANY, TITLE, URL, JOB_ID)

    failure_notifs = [
        (a, kw) for a, kw in notif_spy if kw.get("kind") == "prep_failure"
    ]
    assert len(failure_notifs) == 1, (
        f"failure must fire exactly one prep_failure notif; got {len(failure_notifs)}: {failure_notifs}"
    )
