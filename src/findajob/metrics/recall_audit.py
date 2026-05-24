"""Recall-audit module: weekly sampling + re-scoring of hard-rejected and
low-scored jobs to detect recall degradation.

Cron entry point: ``scripts/recall_audit.py`` (weekly, Sunday after triage).
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

from findajob.llm.openrouter import complete
from findajob.notifications.ntfy import send

log = logging.getLogger(__name__)

SAMPLE_HARD_REJECTED = 20
SAMPLE_LOW_SCORED = 20
UPGRADE_ALERT_THRESHOLD = 0.10
AUDITOR_ROLE = "recall_auditor"
_LOOKBACK_DAYS = 7


def _sample_candidates(
    conn: sqlite3.Connection,
    lookback_days: int = _LOOKBACK_DAYS,
) -> list[dict]:
    cutoff = (datetime.now(UTC) - timedelta(days=lookback_days)).strftime("%Y-%m-%d %H:%M:%S")

    hard_rejected = conn.execute(
        """
        SELECT j.id, j.fingerprint, j.title, j.company, j.location,
               j.relevance_score, j.scored_by, j.jd_text
        FROM jobs j
        JOIN audit_log a ON a.job_id = j.id
          AND a.field_changed = 'stage' AND a.new_value = 'rejected'
          AND a.changed_at >= ?
        WHERE j.stage = 'rejected'
          AND j.relevance_score <= 3
          AND j.synthetic = 0
        ORDER BY RANDOM()
        LIMIT ?
        """,
        (cutoff, SAMPLE_HARD_REJECTED),
    ).fetchall()

    low_scored = conn.execute(
        """
        SELECT j.id, j.fingerprint, j.title, j.company, j.location,
               j.relevance_score, j.scored_by, j.jd_text
        FROM jobs j
        JOIN audit_log a ON a.job_id = j.id
          AND a.field_changed = 'stage' AND a.new_value = 'scored'
          AND a.changed_at >= ?
        WHERE j.stage = 'scored'
          AND j.relevance_score BETWEEN 3 AND 6
          AND j.synthetic = 0
        ORDER BY RANDOM()
        LIMIT ?
        """,
        (cutoff, SAMPLE_LOW_SCORED),
    ).fetchall()

    candidates = []
    for row in list(hard_rejected) + list(low_scored):
        candidates.append(
            {
                "id": row["id"] if isinstance(row, sqlite3.Row) else row[0],
                "fingerprint": row["fingerprint"] if isinstance(row, sqlite3.Row) else row[1],
                "title": row["title"] if isinstance(row, sqlite3.Row) else row[2],
                "company": row["company"] if isinstance(row, sqlite3.Row) else row[3],
                "location": row["location"] if isinstance(row, sqlite3.Row) else row[4],
                "original_score": row["relevance_score"] if isinstance(row, sqlite3.Row) else row[5],
                "scored_by": row["scored_by"] if isinstance(row, sqlite3.Row) else row[6],
                "jd_text": row["jd_text"] if isinstance(row, sqlite3.Row) else row[7],
            }
        )
    return candidates


def _rescore_job(candidate: dict, roles_dir: Path | None = None) -> dict:
    """Re-score a single job using the auditor role."""
    jd_snippet = (candidate.get("jd_text") or "")[:3000]

    prompt = (
        f"Title: {candidate['title']}\n"
        f"Company: {candidate['company']}\n"
        f"Location: {candidate['location']}\n\n"
        f"Job description (truncated):\n{jd_snippet}\n\n"
        "Score this job on a 1-10 relevance scale. Return ONLY a JSON object: "
        '{"score": <int>, "reasoning": "<one sentence>"}'
    )

    try:
        result = complete(
            AUDITOR_ROLE,
            prompt,
            job_id=candidate["id"],
            roles_dir=roles_dir,
        )
        parsed = json.loads(result.text.strip())
        return {
            "score": int(parsed["score"]),
            "notes": parsed.get("reasoning", ""),
            "model": result.model,
        }
    except (json.JSONDecodeError, KeyError, ValueError) as exc:
        log.warning("recall-audit: failed to parse response for %s: %s", candidate["id"], exc)
        return {"score": None, "notes": str(exc), "model": "unknown"}


def run_audit(
    conn: sqlite3.Connection,
    *,
    roles_dir: Path | None = None,
    dry_run: bool = False,
) -> dict:
    """Execute one recall-audit cycle. Returns summary stats."""
    candidates = _sample_candidates(conn)
    if not candidates:
        log.info("recall-audit: no candidates in lookback window")
        return {"total": 0, "upgrades": 0, "upgrade_rate": 0.0}

    upgrades = 0
    total = 0
    model_used = "unknown"

    for c in candidates:
        result = _rescore_job(c, roles_dir=roles_dir)
        if result["score"] is None:
            continue

        total += 1
        model_used = result["model"]
        upgraded = 1 if result["score"] > c["original_score"] + 1 else 0
        if upgraded:
            upgrades += 1

        if not dry_run:
            conn.execute(
                """
                INSERT INTO recall_audit
                    (job_id, original_score, original_scored_by, auditor_model,
                     audited_score, upgraded, audit_notes)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    c["id"],
                    c["original_score"],
                    c["scored_by"],
                    result["model"],
                    result["score"],
                    upgraded,
                    result["notes"],
                ),
            )
    if not dry_run:
        conn.commit()

    rate = upgrades / total if total > 0 else 0.0

    if rate > UPGRADE_ALERT_THRESHOLD and not dry_run:
        send(
            title="Recall audit: upgrade rate above threshold",
            body=(
                f"Recall audit completed: {upgrades}/{total} jobs "
                f"({rate:.0%}) scored higher on re-evaluation. "
                f"Review at /stats/recall-audit"
            ),
            priority="high",
            tags="warning",
            kind="recall_audit_alert",
            cta_url="/stats/recall-audit",
        )

    log.info(
        "recall-audit: %d/%d upgrades (%.1f%%), model=%s",
        upgrades,
        total,
        rate * 100,
        model_used,
    )
    return {"total": total, "upgrades": upgrades, "upgrade_rate": rate}
