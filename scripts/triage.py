#!/usr/bin/env python3
# ~/JobSearchPipeline/scripts/triage.py
"""
Daily triage pipeline. Fetches jobs, deduplicates, enriches, scores,
and writes results to SQLite. Sheet sync is a separate script called at the end.
"""

import csv
import os
import shutil
import signal
import sqlite3
import subprocess
import sys
import time
import uuid
from datetime import UTC, datetime

from findajob.cleaning import fingerprint
from findajob.fetchers import fetch_gmail_jobs, fetch_greenhouse_jobs, fetch_jd, fetch_jobsapi_jobs
from findajob.paths import BASE
from findajob.scoring import _build_feedback_block, score_job
from findajob.utils import (
    is_aggregator_company,
    is_ingest_noise_title,
    load_env,
    log_event,
    write_audit,
)


# ── Signal handler: log a termination event before exiting ───────────────────
# systemd sends SIGTERM when the service hits TimeoutStartSec (default: 30min).
# Without this handler the process dies silently and pipeline_complete never
# fires, causing notify.py health-check to miss a real failure.
def _on_sigterm(signum, frame):
    log_event("pipeline_terminated", signal="SIGTERM", note="Received SIGTERM — likely systemd timeout or manual stop.")
    sys.exit(143)  # 128 + SIGTERM(15)


signal.signal(signal.SIGTERM, _on_sigterm)

DB_PATH = f"{BASE}/data/pipeline.db"
CONNECTIONS = f"{BASE}/data/connections.csv"
PROFILE_PATH = f"{BASE}/config/profile.md"


def _role_model(role_name):
    """Read the model: field from a role's YAML frontmatter."""
    role_path = f"{BASE}/config/roles/{role_name}.md"
    try:
        with open(role_path) as f:
            in_front = False
            for line in f:
                if line.strip() == "---":
                    in_front = not in_front
                    continue
                if in_front and line.startswith("model:"):
                    return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return "unknown"


SCORER_MODEL = _role_model("job_scorer")

load_env()

# Cache feedback block at module load — rebuilt each triage run
_FEEDBACK_BLOCK = _build_feedback_block()


# ── Contact Lookup ──
def find_contacts(company):
    contacts = []
    if not company or not company.strip():
        return contacts
    try:
        with open(CONNECTIONS) as f:
            for row in csv.DictReader(f):
                contact_co = row.get("Company", "").strip()
                if not contact_co:
                    continue  # guard: '' in 'anything' is True in Python
                if company.lower() in contact_co.lower():
                    contacts.append(f"{row['First Name']} {row['Last Name']} ({row['Position']})")
    except Exception:
        pass
    return contacts


# ── Main Pipeline ──
def main():
    log_event("pipeline_started")

    if os.path.exists(DB_PATH):
        shutil.copy2(DB_PATH, f"{DB_PATH}.bak")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")

    with open(PROFILE_PATH) as f:
        candidate_profile = f.read()

    # ── Fetch with retry ─────────────��────────────────────────────────────
    # The triage runs once daily. If DNS or network is down at run time,
    # all sources return 0 jobs and the day is lost. Retry up to 3 times
    # with 2-minute gaps (well within the 3600s systemd timeout).
    MAX_FETCH_ATTEMPTS = 3
    FETCH_RETRY_DELAY = 120  # seconds

    for attempt in range(1, MAX_FETCH_ATTEMPTS + 1):
        greenhouse_jobs = fetch_greenhouse_jobs(f"{BASE}/config/feed_urls.txt")
        api_jobs = fetch_jobsapi_jobs(f"{BASE}/config/jsearch_queries.txt")
        gmail_jobs = fetch_gmail_jobs()
        raw_jobs = greenhouse_jobs + api_jobs + gmail_jobs
        log_event(
            "jobs_fetched",
            count=len(raw_jobs),
            greenhouse=len(greenhouse_jobs),
            api=len(api_jobs),
            gmail=len(gmail_jobs),
            attempt=attempt,
        )

        if raw_jobs or attempt == MAX_FETCH_ATTEMPTS:
            break

        # Zero jobs — probe connectivity before retrying
        try:
            probe = subprocess.run(
                ["curl", "-s", "--max-time", "5", "-o", "/dev/null", "-w", "%{http_code}", "https://google.com"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            online = probe.stdout.strip().startswith(("2", "3"))
        except Exception:
            online = False

        if online:
            # Network is up but still 0 jobs — genuine empty day, stop retrying
            log_event("fetch_retry_skipped", reason="network_up_but_zero_jobs", attempt=attempt)
            break

        log_event(
            "fetch_retry", attempt=attempt, next_attempt_in=FETCH_RETRY_DELAY, reason="zero_jobs_and_network_down"
        )
        time.sleep(FETCH_RETRY_DELAY)

    if not raw_jobs:
        log_event("pipeline_complete", new=0, dupes=0, scored=0)
        conn.close()
        return

    new_count = 0
    dupe_count = 0
    scored_count = 0
    noise_count = 0

    for job in raw_jobs:
        if not job.get("title") or not job.get("url"):
            continue

        # ── Ingest noise filters ──
        # 1. LinkedIn "Jobs similar to" recommendations-carousel items.
        #    These aren't real jobs — the API returned a UI element.
        if is_ingest_noise_title(job.get("title", "")):
            log_event(
                "ingest_skipped",
                reason="jobs_similar_to",
                title=job.get("title", "")[:80],
                company=job.get("company", "")[:80],
            )
            noise_count += 1
            continue
        # 2. Aggregator / recruiter wrappers (Jobs via Dice, Robert Half, etc.).
        #    The "company" is the board, not the actual employer — unactionable.
        if is_aggregator_company(job.get("company", "")):
            log_event(
                "ingest_skipped",
                reason="aggregator_company",
                title=job.get("title", "")[:80],
                company=job.get("company", "")[:80],
            )
            noise_count += 1
            continue

        fp = fingerprint(job["title"], job.get("company", ""), job.get("location", ""))

        existing = conn.execute("SELECT id FROM jobs WHERE fingerprint = ?", (fp,)).fetchone()

        if existing:
            conn.execute(
                "INSERT OR IGNORE INTO duplicate_groups (canonical_fingerprint, duplicate_job_id) VALUES (?, ?)",
                (fp, job.get("url", "")),
            )
            dupe_count += 1
            continue

        job_id = str(uuid.uuid4())
        now = datetime.now(UTC).isoformat()

        conn.execute(
            """
            INSERT INTO jobs (id, fingerprint, url, title, company, location, source, stage, stage_updated, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'discovered', ?, ?)
        """,
            (
                job_id,
                fp,
                job["url"],
                job["title"],
                job.get("company", ""),
                job.get("location", ""),
                job.get("source", "rss"),
                now,
                now,
            ),
        )
        conn.commit()
        write_audit(conn, job_id, "stage", None, "discovered")
        new_count += 1

        jd_text = fetch_jd(job)

        # For gmail_linkedin jobs: if company was blank after HTML heuristics,
        # fetch_jd already called the LinkedIn API and cached the company — reuse it.
        if job.get("source") == "gmail_linkedin" and not job.get("company"):
            resolved = job.get("_linkedin_company")
            if resolved:
                job["company"] = resolved
                # Recompute fingerprint with resolved company and check for dupes
                new_fp = fingerprint(job["title"], job["company"], job.get("location", ""))
                existing_resolved = conn.execute(
                    "SELECT id FROM jobs WHERE fingerprint = ? AND id != ?", (new_fp, job_id)
                ).fetchone()
                if existing_resolved:
                    # A copy with the resolved company already exists — mark this one as dupe
                    conn.execute(
                        "UPDATE jobs SET dupe_of=?, stage=?, stage_updated=?, updated_at=? WHERE id=?",
                        (existing_resolved["id"], "rejected", now, now, job_id),
                    )
                    conn.commit()
                    write_audit(conn, job_id, "stage", "discovered", "rejected")
                    log_event(
                        "dupe_after_enrichment",
                        job_id=job_id,
                        title=job["title"],
                        company=job["company"],
                        dupe_of=existing_resolved["id"],
                    )
                    dupe_count += 1
                    continue
                # No dupe — update company and fingerprint on the inserted row
                conn.execute("UPDATE jobs SET company=?, fingerprint=? WHERE id=?", (job["company"], new_fp, job_id))
                conn.commit()
            else:
                # Company unresolvable — reject immediately, don't waste a scorer call
                conn.execute(
                    """
                    UPDATE jobs SET stage='rejected', stage_updated=?, status='rejected',
                           reject_reason='Blank Company', updated_at=?
                    WHERE id=?
                """,
                    (now, now, job_id),
                )
                conn.commit()
                write_audit(conn, job_id, "stage", "discovered", "rejected")
                log_event("blank_company_rejected", job_id=job_id, title=job["title"], source="gmail_linkedin")
                continue

        contacts = find_contacts(job.get("company", ""))
        network_depth = min(len(contacts), 2)
        known_contacts = ", ".join(contacts[:3])

        conn.execute(
            """
            UPDATE jobs SET raw_jd_text=?, network_depth=?, known_contacts=?,
                   stage='enriched', stage_updated=?, updated_at=?
            WHERE id=?
        """,
            (jd_text, network_depth, known_contacts, now, now, job_id),
        )
        conn.commit()
        write_audit(conn, job_id, "stage", "discovered", "enriched")

        scored, latency_ms = score_job(
            job["title"],
            job.get("company", ""),
            job.get("location", ""),
            jd_text,
            candidate_profile,
            feedback_block=_FEEDBACK_BLOCK,
        )

        stage = "manual_review" if scored.get("score_status") == "manual_review" else "scored"
        status = "manual_review" if stage == "manual_review" else "active"

        conn.execute(
            """
            UPDATE jobs SET
                relevance_score=?, interview_likelihood=?, strengths_alignment=?,
                industry_sector=?, comp_estimate=?, ai_notes=?,
                score_status=?, score_flag_reason=?, remote_status=?,
                stage=?, stage_updated=?, status=?, updated_at=?
            WHERE id=?
        """,
            (
                scored.get("relevance_score"),
                scored.get("interview_likelihood"),
                scored.get("strengths_alignment"),
                scored.get("industry_sector", ""),
                scored.get("comp_estimate", ""),
                scored.get("ai_notes", ""),
                scored.get("score_status", "manual_review"),
                scored.get("score_flag_reason", ""),
                scored.get("remote_status", "Unknown"),
                stage,
                now,
                status,
                now,
                job_id,
            ),
        )
        conn.commit()
        write_audit(conn, job_id, "stage", "enriched", stage)
        scored_count += 1

        conn.execute(
            """
            INSERT INTO cost_log (job_id, operation, model, latency_ms, success)
            VALUES (?, 'score', ?, ?, 1)
        """,
            (job_id, SCORER_MODEL, latency_ms),
        )
        conn.commit()

        log_event(
            "job_processed",
            job_id=job_id,
            title=job["title"],
            company=job.get("company", ""),
            stage=stage,
            score=scored.get("relevance_score"),
        )

        time.sleep(0.5)

    # ── Orphan recovery: rescue any rows stuck in 'enriched' stage ──
    # If a prior run crashed mid-scoring (SIGTERM from systemd timeout, etc.),
    # jobs that were enriched but not yet scored get stranded. Pick them up
    # here on the next run so they don't sit in DB limbo forever.
    orphan_scored = 0
    orphans = conn.execute("""
        SELECT id, title, company, location, raw_jd_text FROM jobs
        WHERE stage = 'enriched'
          AND (dupe_of = '' OR dupe_of IS NULL)
    """).fetchall()
    if orphans:
        log_event("orphan_recovery_started", count=len(orphans))
        for row in orphans:
            try:
                scored, latency_ms = score_job(
                    row["title"],
                    row["company"] or "",
                    row["location"] or "",
                    row["raw_jd_text"] or "",
                    candidate_profile,
                    feedback_block=_FEEDBACK_BLOCK,
                )
                now = datetime.now(UTC).isoformat()
                new_stage = "manual_review" if scored.get("score_status") == "manual_review" else "scored"
                conn.execute(
                    """
                    UPDATE jobs SET
                        relevance_score=?, interview_likelihood=?, strengths_alignment=?,
                        industry_sector=?, comp_estimate=?, ai_notes=?,
                        score_status=?, score_flag_reason=?, remote_status=?,
                        stage=?, stage_updated=?, updated_at=?
                    WHERE id=?
                """,
                    (
                        scored.get("relevance_score"),
                        scored.get("interview_likelihood"),
                        scored.get("strengths_alignment"),
                        scored.get("industry_sector", ""),
                        scored.get("comp_estimate", ""),
                        scored.get("ai_notes", ""),
                        scored.get("score_status", "manual_review"),
                        scored.get("score_flag_reason", ""),
                        scored.get("remote_status", "Unknown"),
                        new_stage,
                        now,
                        now,
                        row["id"],
                    ),
                )
                conn.commit()
                orphan_scored += 1
            except Exception as e:
                log_event("orphan_recovery_error", job_id=row["id"], error=str(e))
        log_event("orphan_recovery_complete", total=len(orphans), scored=orphan_scored)

    conn.close()
    log_event(
        "pipeline_complete",
        new=new_count,
        dupes=dupe_count,
        scored=scored_count,
        noise_skipped=noise_count,
        orphans_recovered=orphan_scored,
    )

    subprocess.run([sys.executable, f"{BASE}/scripts/sync_sheet.py"], check=False)
    notify(f"Triage done: {new_count} new, {dupe_count} dupes, {scored_count} scored")


def notify(message):
    topic = None
    try:
        with open(f"{BASE}/config/ntfy_topic.txt") as f:
            topic = f.read().strip()
    except FileNotFoundError:
        pass
    if not topic:
        # Fall back to data/.env NTFY_TOPIC
        try:
            with open(f"{BASE}/data/.env") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("NTFY_TOPIC") and "=" in line:
                        topic = line.split("=", 1)[1].strip().strip("'\"")
                        break
        except Exception:
            pass
    if not topic:
        return
    try:
        subprocess.run(["curl", "-s", "-d", message, f"https://ntfy.sh/{topic}"], capture_output=True, timeout=10)
    except Exception:
        pass


if __name__ == "__main__":
    main()
