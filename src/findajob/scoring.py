"""Job scoring: deterministic prefilter + LLM scoring via aichat-ng."""

import sqlite3
import subprocess
import time

from findajob.paths import AICHAT, BASE
from findajob.scorer_prefilter import _hard_reject_match, prefilter_score
from findajob.utils import jd_is_usable, log_event, validate_llm_json

DB_PATH = f"{BASE}/data/pipeline.db"
SCHEMA_PATH = f"{BASE}/config/scoring_schema.json"


def _build_feedback_block():
    """Query feedback_log and return a compact rejection-history block for the scorer prompt.
    Returns empty string if no feedback exists."""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""
            SELECT reject_reason, title, relevance_score
            FROM feedback_log
            WHERE reject_reason NOT IN ('Stale/Closed', 'Already Applied', 'Other')
            ORDER BY reject_reason, title
        """).fetchall()
        conn.close()
    except Exception:
        return ""

    if not rows:
        return ""

    # Cluster by reject_reason
    clusters = {}
    for r in rows:
        reason = r["reject_reason"]
        clusters.setdefault(reason, []).append(r["title"])

    lines = ["", "---", "", "USER REJECTION HISTORY (from manual feedback — consider when scoring similar jobs):"]
    for reason, titles in sorted(clusters.items(), key=lambda x: -len(x[1])):
        # Dedupe and truncate title list
        unique = list(dict.fromkeys(titles))
        sample = ", ".join(t[:40] for t in unique[:6])
        if len(unique) > 6:
            sample += f", ... (+{len(unique) - 6} more)"
        lines.append(f'- {len(unique)}x "{reason}": {sample}')

    lines.append(
        "If this job closely matches rejected patterns above, reduce your score by 2-3 points. "
        "The user has explicitly rejected similar jobs. Minimum score is always 1."
    )
    return "\n".join(lines)


def score_job(title, company, location, jd_text, candidate_profile="", feedback_block=""):
    """Score a job via deterministic prefilter, then LLM if needed.

    Args:
        title: Job title string.
        company: Company name string.
        location: Location string.
        jd_text: Job description text.
        candidate_profile: Contents of profile.md for the LLM prompt.
        feedback_block: Pre-built feedback history string (from _build_feedback_block).

    Returns:
        Tuple of (score_dict, latency_ms).
    """
    usable = jd_is_usable(jd_text)

    # Stage 1 & 2: deterministic pre-filter — no LLM call
    pre, reason = prefilter_score(title, company, usable)
    if pre is not None:
        log_event("score_prefilter", title=title, company=company, reason=reason, score=pre.get("relevance_score"))
        return pre, 0

    # Stage 3: LLM scoring
    effective_jd = jd_text if usable else "[Job description unavailable — score from title and company only]"
    prompt = f"""CANDIDATE PROFILE:
{candidate_profile}
{feedback_block}

---

Evaluate this job posting for the candidate described above.
Job: {title} at {company}
Location: {location}
JD:
{effective_jd[:6000]}"""

    start = time.time()
    try:
        result = subprocess.run(
            [AICHAT, "--role", "job_scorer", "-S", prompt], capture_output=True, text=True, timeout=60
        )
    except subprocess.TimeoutExpired:
        latency_ms = int((time.time() - start) * 1000)
        log_event("score_error", reason="timeout", title=title, company=company, latency_ms=latency_ms)
        return {
            "score_status": "manual_review",
            "score_flag_reason": "Scorer timeout",
            "relevance_score": None,
            "interview_likelihood": None,
            "strengths_alignment": None,
            "industry_sector": "",
            "comp_estimate": "",
            "ai_notes": "Scorer timed out after 60s",
            "remote_status": "Unknown",
        }, latency_ms
    latency_ms = int((time.time() - start) * 1000)

    if result.returncode != 0 or not result.stdout.strip():
        log_event(
            "score_error",
            reason="subprocess_failed",
            returncode=result.returncode,
            stderr=result.stderr.strip()[:200],
            title=title,
            company=company,
        )
        return {
            "score_status": "manual_review",
            "score_flag_reason": f"Scorer failed (rc={result.returncode})",
            "relevance_score": None,
            "interview_likelihood": None,
            "strengths_alignment": None,
            "industry_sector": "",
            "comp_estimate": "",
            "ai_notes": "Scorer subprocess failed or returned empty output",
            "remote_status": "Unknown",
        }, latency_ms

    parsed, error = validate_llm_json(result.stdout, SCHEMA_PATH)

    if error:
        log_event("score_validation_failed", error=error, title=title, company=company)
        # Stage 1.5: if LLM failed AND title matches a hard reject pattern, auto-reject
        # instead of cluttering the manual_review queue with obvious mismatches
        if _hard_reject_match(title):
            return {
                "score_status": "scored",
                "score_flag_reason": f"Validation: {error}",
                "relevance_score": 1,
                "interview_likelihood": 1,
                "strengths_alignment": "LLM failed + title is outside candidate domain.",
                "industry_sector": "",
                "comp_estimate": "",
                "ai_notes": "LLM validation failed; hard-reject title pattern matched",
                "remote_status": "Unknown",
            }, latency_ms
        return {
            "score_status": "manual_review",
            "score_flag_reason": f"Validation: {error}",
            "relevance_score": None,
            "interview_likelihood": None,
            "strengths_alignment": None,
            "industry_sector": "",
            "comp_estimate": "",
            "ai_notes": "Scorer output failed validation",
            "remote_status": "Unknown",
        }, latency_ms

    if parsed.get("relevance_score") is None:
        log_event("score_error", reason="null_score", title=title, company=company)

    return parsed, latency_ms
