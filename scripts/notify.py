#!/usr/bin/env python3
# ~/JobSearchPipeline/scripts/notify.py
"""
ntfy push notification suite for the JobSearchPipeline.

Usage:
  notify.py daily-stats      — morning stats: queue depth, recent activity
  notify.py health-check     — surface errors from logs, confirm automations ran
  notify.py issues-ping      — open issues from ISSUES.md (run every other day)
  notify.py apply-reminder   — humorous daily nudge to submit at least one application
  notify.py feedback-review  — alert when feedback_log has enough data to be useful

ntfy topic is read from NTFY_TOPIC in data/.env, or falls back to NTFY_TOPIC env var.
"""

import json
import os
import re
import sqlite3
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from findajob.paths import BASE
from findajob.utils import load_env

DB_PATH = f"{BASE}/data/pipeline.db"
LOG_PATH = f"{BASE}/logs/pipeline.jsonl"
ISSUES_PATH = f"{BASE}/docs/ISSUES.md"

# ── Load ntfy topic ────────────────────────────────────────────────────────────
_env = load_env()
NTFY_TOPIC = _env.get("NTFY_TOPIC") or os.environ.get("NTFY_TOPIC", "jobsearch-pipeline")
NTFY_URL = f"https://ntfy.sh/{NTFY_TOPIC}"


def send(title, body, priority="default", tags=None):
    """Send a push notification via ntfy.sh."""
    headers = [
        "-H",
        f"Title: {title}",
        "-H",
        f"Priority: {priority}",
    ]
    if tags:
        headers += ["-H", f"Tags: {tags}"]
    subprocess.run(
        ["curl", "-s", "-X", "POST", NTFY_URL, "-H", "Content-Type: text/plain; charset=utf-8", *headers, "-d", body],
        check=False,
        capture_output=True,
    )


# ── Helpers ────────────────────────────────────────────────────────────────────
def db_connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def recent_log_events(hours=25):
    """Return log entries from the last N hours."""
    cutoff = (datetime.now(UTC) - timedelta(hours=hours)).isoformat()
    events = []
    try:
        with open(LOG_PATH) as f:
            for line in f:
                try:
                    e = json.loads(line)
                    if e.get("ts", "") >= cutoff:
                        events.append(e)
                except json.JSONDecodeError:
                    pass
    except FileNotFoundError:
        pass
    return events


def open_issues():
    """Parse ISSUES.md and return list of open (unchecked) issue titles."""
    issues = []
    try:
        with open(ISSUES_PATH) as f:
            for line in f:
                m = re.match(r"- \[ \] \*\*(.+?)\*\*", line)
                if m:
                    issues.append(m.group(1))
    except FileNotFoundError:
        pass
    return issues


# ── Commands ───────────────────────────────────────────────────────────────────
def cmd_daily_stats():
    conn = db_connect()

    # Dashboard queue (score>=7 unprepped, plus all materials_drafted)
    queue_count = conn.execute("""
        SELECT COUNT(*) FROM jobs
        WHERE (dupe_of = '' OR dupe_of IS NULL)
          AND (
            (relevance_score >= 7 AND stage IN ('scored', 'manual_review'))
            OR stage = 'materials_drafted'
          )
    """).fetchone()[0]

    # Jobs flagged but not yet prepped
    flagged_unprepped = conn.execute("""
        SELECT COUNT(*) FROM jobs
        WHERE apply_flag = 1
          AND stage NOT IN ('materials_drafted', 'applied', 'rejected', 'withdrawn')
    """).fetchone()[0]

    # Jobs prepped
    prepped = conn.execute("SELECT COUNT(*) FROM jobs WHERE stage = 'materials_drafted'").fetchone()[0]

    # Jobs applied
    applied = conn.execute("SELECT COUNT(*) FROM jobs WHERE stage = 'applied'").fetchone()[0]

    # Jobs rejected via dashboard
    rejected = conn.execute("SELECT COUNT(*) FROM jobs WHERE stage = 'rejected'").fetchone()[0]

    # New jobs scored in last 24h
    cutoff_24h = (datetime.now(UTC) - timedelta(hours=24)).isoformat()
    new_today = conn.execute(
        """
        SELECT COUNT(*) FROM jobs
        WHERE relevance_score IS NOT NULL
          AND updated_at >= ?
          AND stage IN ('scored', 'manual_review')
    """,
        (cutoff_24h,),
    ).fetchone()[0]

    # Total in DB
    total = conn.execute("SELECT COUNT(*) FROM jobs WHERE dupe_of = '' OR dupe_of IS NULL").fetchone()[0]

    conn.close()

    lines = [
        f"Queue (score≥7, unprepped): {queue_count} jobs",
        f"Flagged, awaiting prep:     {flagged_unprepped}",
        f"Materials drafted:          {prepped}",
        f"Applied:                    {applied}",
        f"Rejected via dashboard:     {rejected}",
        f"New jobs scored today:      {new_today}",
        f"Total in pipeline:          {total}",
    ]
    body = "\n".join(lines)
    send("JSP Daily Stats", body, priority="default", tags="bar_chart")


SHEET1_ROW_WARN = 1000  # warn if Sheet1 would sync more than this many rows
REVIEW_BACKLOG_WARN = 100  # warn if manual_review backlog exceeds this
TARGET_LOWSCORE_DAYS = 7  # check for mis-scored target company jobs within this window


def cmd_health_check():
    events = recent_log_events(hours=25)

    # Check triage ran (triage.py logs 'pipeline_complete')
    triage_events = [e for e in events if e.get("event") == "pipeline_complete"]
    triage_ok = bool(triage_events)

    # Check if triage was terminated (SIGTERM from systemd timeout or manual stop)
    triage_terminated = [e for e in events if e.get("event") == "pipeline_terminated"]

    # Check poller ran
    poll_events = [e for e in events if e.get("event") == "poll_flags"]
    poll_ok = bool(poll_events)

    # Check sync_sheet ran
    sync_events = [e for e in events if e.get("event") == "sync_complete"]
    sync_ok = bool(sync_events)
    sync_failures = [e for e in events if e.get("event") == "sync_failed"]

    # Error events
    error_events = [
        e for e in events if any(k in e for k in ("error", "exception", "failed")) or "error" in e.get("event", "")
    ]

    # score=None events
    null_score = [e for e in events if e.get("score") is None and "job_scored" in e.get("event", "")]

    issues = []
    if triage_terminated:
        issues.append(
            "ERROR: triage was terminated (SIGTERM) — likely systemd timeout. "
            "Check TimeoutStartSec on findajob-triage.service."
        )
        for e in triage_terminated[:2]:
            issues.append(f"  • {e.get('ts', '?')}: {e.get('note', '?')}")
    elif not triage_ok:
        issues.append("WARN: pipeline_complete not seen in last 25h")
    if not poll_ok:
        issues.append("WARN: poll_flags not seen in last 25h")
    if not sync_ok:
        issues.append("WARN: sync_complete not seen in last 25h")
    if sync_failures:
        issues.append(f"ERROR: {len(sync_failures)} sync_sheet failure(s) in last 25h")
        for e in sync_failures[:2]:
            issues.append(f"  • {e.get('error', 'unknown')}")
    if error_events:
        issues.append(f"ERRORS: {len(error_events)} error events in log")
        for e in error_events[:3]:
            issues.append(f"  • [{e.get('event', '?')}] {e.get('error', e.get('note', ''))}")
    if null_score:
        issues.append(f"INFO: {len(null_score)} jobs scored None (likely LLM timeout)")

    # Check rclone sync health
    rclone_failures = [e for e in events if e.get("event") == "rclone_failed"]
    if rclone_failures:
        issues.append(f"WARN: {len(rclone_failures)} rclone sync failure(s) in last 25h")
        for e in rclone_failures[:2]:
            issues.append(f"  • {e.get('reason', '?')} exit={e.get('exit_code', '?')}")

    # ── Sheet / queue health checks ──────────────────────────────────────
    conn = db_connect()

    # Sheet1 row count (approximate — same filter as sync_sheet.py)
    sheet1_count = conn.execute("""
        SELECT COUNT(*) FROM jobs
        WHERE (dupe_of = '' OR dupe_of IS NULL)
          AND (
            relevance_score >= 5
            OR stage IN ('manual_review', 'materials_drafted', 'waitlisted',
                         'applied', 'interview', 'offer', 'withdrawn')
            OR julianday('now') - julianday(created_at) <= 14
          )
    """).fetchone()[0]
    if sheet1_count > SHEET1_ROW_WARN:
        issues.append(f"WARN: Sheet1 has ~{sheet1_count} rows (threshold: {SHEET1_ROW_WARN})")

    # Manual review backlog
    review_count = conn.execute("SELECT COUNT(*) FROM jobs WHERE stage = 'manual_review'").fetchone()[0]
    if review_count > REVIEW_BACKLOG_WARN:
        issues.append(f"WARN: {review_count} jobs in manual_review backlog (threshold: {REVIEW_BACKLOG_WARN})")

    # Target company jobs scored 3-6 in the last N days (potential mis-scores worth reviewing).
    # Score 1-2 are excluded — prefilter hard rejects or clear mismatches, not actionable.
    from findajob.scorer_prefilter import TIER1

    cutoff = (datetime.now(UTC) - timedelta(days=TARGET_LOWSCORE_DAYS)).isoformat()
    low_target = conn.execute(
        """
        SELECT title, company, relevance_score FROM jobs
        WHERE relevance_score BETWEEN 3 AND 6
          AND created_at >= ?
          AND stage IN ('scored', 'manual_review')
    """,
        (cutoff,),
    ).fetchall()
    # Filter in Python since TIER1 check is a substring match
    mis_scored = [
        (r["title"], r["company"], r["relevance_score"])
        for r in low_target
        if r["company"] and any(t in r["company"].lower() for t in TIER1)
    ]
    if mis_scored:
        issues.append(f"REVIEW: {len(mis_scored)} target-company job(s) scored 3-6 in last {TARGET_LOWSCORE_DAYS}d:")
        for title, company, score in mis_scored[:5]:
            issues.append(f"  • {company}: {title} (score={score})")

    # ── Duplicate company folders ────────────────────────────────────────────
    companies_dir = os.path.join(BASE, "companies")
    folder_names = [
        d for d in os.listdir(companies_dir) if not d.startswith("_") and os.path.isdir(os.path.join(companies_dir, d))
    ]
    # Strip timestamp suffix to find duplicates (same company_title_date, different HHMMSS)
    from collections import Counter

    prefixes = [name.rsplit("_", 1)[0] for name in folder_names]
    dupes = {p: n for p, n in Counter(prefixes).items() if n > 1}
    if dupes:
        issues.append(f"WARN: {len(dupes)} duplicate company folder set(s):")
        for prefix, count in list(dupes.items())[:5]:
            issues.append(f"  • {prefix} ({count} copies)")

    # ── Stuck prep_in_progress jobs ──────────────────────────────────────────
    stuck_cutoff = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    stuck = conn.execute(
        """
        SELECT title, company, stage_updated FROM jobs
        WHERE stage = 'prep_in_progress' AND stage_updated < ?
    """,
        (stuck_cutoff,),
    ).fetchall()
    if stuck:
        issues.append(f"WARN: {len(stuck)} job(s) stuck in prep_in_progress >1h:")
        for r in stuck[:5]:
            issues.append(f"  • {r['company']}: {r['title']}")

    # ── Orphaned prep_folder_path (DB points to missing dir) ─────────────────
    prepped = conn.execute("""
        SELECT title, company, prep_folder_path FROM jobs
        WHERE prep_folder_path IS NOT NULL AND prep_folder_path != ''
          AND stage NOT IN ('rejected', 'withdrawn')
    """).fetchall()
    orphaned = [r for r in prepped if not Path(r["prep_folder_path"]).is_dir()]
    if orphaned:
        issues.append(f"WARN: {len(orphaned)} job(s) have prep_folder_path pointing to missing dir:")
        for r in orphaned[:5]:
            issues.append(f"  • {r['company']}: {r['title']}")

    conn.close()

    if not issues:
        body = "All systems nominal.\nTriage ran. Poller ran. Sheet synced. No errors in last 25h."
        priority = "low"
        tags = "white_check_mark"
    else:
        body = "\n".join(issues)
        priority = "high" if any("ERROR" in i for i in issues) else "default"
        tags = "warning"

    send("JSP Health Check", body, priority=priority, tags=tags)


def cmd_issues_ping():
    issues = open_issues()
    if not issues:
        body = "No open issues in ISSUES.md."
        tags = "white_check_mark"
    else:
        lines = [f"{len(issues)} open issue(s):"]
        for i, iss in enumerate(issues, 1):
            lines.append(f"{i}. {iss}")
        body = "\n".join(lines)
        tags = "memo"
    send("JSP Open Issues", body, priority="default", tags=tags)


def cmd_apply_reminder():
    QUIPS = [
        "The perfect resume is the enemy of the submitted one. Go click Apply.",
        "GPT-6 isn't submitting your application. You are. Open a tab.",
        "Somewhere a hiring manager is waiting for your resume. Don't keep them waiting.",
        "Every application you don't submit is a job you definitely didn't get.",
        "The pipeline doesn't apply for you. That's still a manual step. Do it.",
        "Your future self is staring at you. They look annoyed. Apply to something.",
        "DeepSeek scored it a 9. Your mouse is scored a 0. Click Apply.",
        "Reject the fear of rejection. Apply anyway. Preferably today.",
        "Fun fact: 0% of jobs you don't apply to result in interviews.",
        "The Dashboard is not an art installation. It has checkboxes for a reason.",
    ]
    # Rotate by day-of-year so it's deterministic per day but varies daily
    day_index = datetime.now().timetuple().tm_yday % len(QUIPS)
    quip = QUIPS[day_index]

    # Pull real counts for the daily checklist
    conn = db_connect()
    n_dashboard = conn.execute("""
        SELECT COUNT(*) FROM jobs
        WHERE (dupe_of = '' OR dupe_of IS NULL)
          AND relevance_score >= 7 AND stage IN ('scored', 'manual_review')
    """).fetchone()[0]
    n_ready = conn.execute("SELECT COUNT(*) FROM jobs WHERE stage = 'materials_drafted'").fetchone()[0]
    n_review = conn.execute("SELECT COUNT(*) FROM jobs WHERE stage = 'manual_review'").fetchone()[0]
    n_applied = conn.execute("SELECT COUNT(*) FROM jobs WHERE stage = 'applied'").fetchone()[0]
    n_waitlisted = conn.execute("SELECT COUNT(*) FROM jobs WHERE stage = 'waitlisted'").fetchone()[0]
    conn.close()

    checklist = (
        f"\n---\n"
        f"1. Dashboard: {n_dashboard} high-score jobs to Flag for Prep or Reject\n"
        f"2. Ready to Apply: {n_ready} jobs with materials drafted — review and submit\n"
        f"3. Review tab: {n_review} jobs in manual review — Promote or Reject\n"
        f"4. Scan Sheet1 for mis-scored target company jobs\n"
        f"5. Check ntfy health notification for pipeline warnings\n"
        f"---\n"
        f"Applied so far: {n_applied}\n"
        f"Waitlisted: {n_waitlisted} deferred jobs"
    )

    send("Apply To Something Today", quip + checklist, priority="default", tags="rocket")


def cmd_feedback_review():
    import subprocess as sp

    THRESHOLD = 10

    conn = db_connect()
    count = conn.execute("SELECT COUNT(*) FROM feedback_log").fetchone()[0]
    conn.close()

    if count < THRESHOLD:
        print(f"feedback_log has {count} entries — below threshold ({THRESHOLD}). No ping sent.")
        return

    # Run analyze_feedback.py and capture key stats for the notification
    try:
        result = sp.run(
            [sys.executable, f"{BASE}/scripts/analyze_feedback.py", "--json"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        data = json.loads(result.stdout) if result.stdout else {}
    except Exception:
        data = {}

    if data and not data.get("error"):
        fp = data.get("false_positives", 0)
        fp_pct = data.get("fp_pct", 0)
        top_reason = data["by_reason"][0] if data.get("by_reason") else ("?", 0)
        top_company = data["company_fp_counts"][0] if data.get("company_fp_counts") else ("?", 0)
        bad_kws = [
            kw["keyword"] for kw in data.get("keyword_signals", []) if kw["ratio"] < 0.4 and kw["rejected_n"] >= 3
        ][:4]
        body = (
            f"{count} rejections in feedback_log\n"
            f"False positives (score 8+): {fp} ({fp_pct}%)\n"
            f"Top reason: {top_reason[0]} ({top_reason[1]})\n"
            f"Top FP company: {top_company[0]} ({top_company[1]} rejections)\n"
            + (f"Prefilter candidates: {', '.join(bad_kws)}\n" if bad_kws else "")
            + "Run: python3 scripts/analyze_feedback.py"
        )
    else:
        body = f"feedback_log has {count} rejection entries.\nRun: python3 scripts/analyze_feedback.py"

    send("JSP Feedback Analysis", body, priority="default", tags="magnifying")


def cmd_send_raw():
    """Send a raw notification. Usage: notify.py send-raw <title> <body>"""
    if len(sys.argv) < 4:
        print("Usage: notify.py send-raw <title> <body>")
        sys.exit(1)
    send(sys.argv[2], sys.argv[3], priority="default", tags="hourglass_flowing_sand")


# ── Dispatch ───────────────────────────────────────────────────────────────────
COMMANDS = {
    "daily-stats": cmd_daily_stats,
    "health-check": cmd_health_check,
    "issues-ping": cmd_issues_ping,
    "apply-reminder": cmd_apply_reminder,
    "feedback-review": cmd_feedback_review,
    "send-raw": cmd_send_raw,
}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(f"Usage: notify.py [{'|'.join(COMMANDS)}]")
        sys.exit(1)
    COMMANDS[sys.argv[1]]()
