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
import os, sys, sqlite3, json, subprocess, re
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from paths import BASE
DB_PATH = f'{BASE}/data/pipeline.db'
LOG_PATH = f'{BASE}/logs/pipeline.jsonl'
ISSUES_PATH = f'{BASE}/docs/ISSUES.md'
ENV_PATH = f'{BASE}/data/.env'

# ── Load ntfy topic ────────────────────────────────────────────────────────────
def load_env():
    env = {}
    try:
        with open(ENV_PATH) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, _, v = line.partition('=')
                    env[k.strip()] = v.strip().strip('"').strip("'")
    except FileNotFoundError:
        pass
    return env

_env = load_env()
NTFY_TOPIC = _env.get('NTFY_TOPIC') or os.environ.get('NTFY_TOPIC', 'jobsearch-pipeline')
NTFY_URL   = f'https://ntfy.sh/{NTFY_TOPIC}'


def send(title, body, priority='default', tags=None):
    """Send a push notification via ntfy.sh."""
    headers = [
        '-H', f'Title: {title}',
        '-H', f'Priority: {priority}',
    ]
    if tags:
        headers += ['-H', f'Tags: {tags}']
    subprocess.run(
        ['curl', '-s', '-X', 'POST', NTFY_URL,
         '-H', 'Content-Type: text/plain; charset=utf-8',
         *headers,
         '-d', body],
        check=False, capture_output=True
    )


# ── Helpers ────────────────────────────────────────────────────────────────────
def db_connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def recent_log_events(hours=25):
    """Return log entries from the last N hours."""
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    events = []
    try:
        with open(LOG_PATH) as f:
            for line in f:
                try:
                    e = json.loads(line)
                    if e.get('ts', '') >= cutoff:
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
                m = re.match(r'- \[ \] \*\*(.+?)\*\*', line)
                if m:
                    issues.append(m.group(1))
    except FileNotFoundError:
        pass
    return issues


# ── Commands ───────────────────────────────────────────────────────────────────
def cmd_daily_stats():
    conn = db_connect()

    # Dashboard queue (score>=7 unprepped, plus all materials_drafted)
    queue_count = conn.execute('''
        SELECT COUNT(*) FROM jobs
        WHERE (dupe_of = '' OR dupe_of IS NULL)
          AND (
            (relevance_score >= 7 AND stage IN ('scored', 'manual_review'))
            OR stage = 'materials_drafted'
          )
    ''').fetchone()[0]

    # Jobs flagged but not yet prepped
    flagged_unprepped = conn.execute('''
        SELECT COUNT(*) FROM jobs
        WHERE apply_flag = 1
          AND stage NOT IN ('materials_drafted', 'applied', 'rejected', 'withdrawn')
    ''').fetchone()[0]

    # Jobs prepped
    prepped = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE stage = 'materials_drafted'"
    ).fetchone()[0]

    # Jobs applied
    applied = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE stage = 'applied'"
    ).fetchone()[0]

    # Jobs rejected via dashboard
    rejected = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE stage = 'rejected'"
    ).fetchone()[0]

    # New jobs scored in last 24h
    cutoff_24h = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    new_today = conn.execute('''
        SELECT COUNT(*) FROM jobs
        WHERE relevance_score IS NOT NULL
          AND updated_at >= ?
          AND stage IN ('scored', 'manual_review')
    ''', (cutoff_24h,)).fetchone()[0]

    # Total in DB
    total = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE dupe_of = '' OR dupe_of IS NULL"
    ).fetchone()[0]

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
    body = '\n'.join(lines)
    send('JSP Daily Stats', body, priority='default', tags='bar_chart')


def cmd_health_check():
    events = recent_log_events(hours=25)

    # Check triage ran (triage.py logs 'pipeline_complete')
    triage_events = [e for e in events if e.get('event') == 'pipeline_complete']
    triage_ok = bool(triage_events)

    # Check poller ran
    poll_events = [e for e in events if e.get('event') == 'poll_flags']
    poll_ok = bool(poll_events)

    # Error events
    error_events = [e for e in events
                    if any(k in e for k in ('error', 'exception', 'failed'))
                    or 'error' in e.get('event', '')]

    # score=None events
    null_score = [e for e in events if e.get('score') is None and 'job_scored' in e.get('event', '')]

    issues = []
    if not triage_ok:
        issues.append('WARN: triage_complete not seen in last 25h')
    if not poll_ok:
        issues.append('WARN: poll_flags not seen in last 25h')
    if error_events:
        issues.append(f'ERRORS: {len(error_events)} error events in log')
        for e in error_events[:3]:
            issues.append(f'  • [{e.get("event","?")}] {e.get("error", e.get("note", ""))}')
    if null_score:
        issues.append(f'INFO: {len(null_score)} jobs scored None (likely LLM timeout)')

    if not issues:
        body = 'All systems nominal.\nTriage ran. Poller ran. No errors in last 25h.'
        priority = 'low'
        tags = 'white_check_mark'
    else:
        body = '\n'.join(issues)
        priority = 'high' if any('ERROR' in i for i in issues) else 'default'
        tags = 'warning'

    send('JSP Health Check', body, priority=priority, tags=tags)


def cmd_issues_ping():
    issues = open_issues()
    if not issues:
        body = 'No open issues in ISSUES.md.'
        tags = 'white_check_mark'
    else:
        lines = [f'{len(issues)} open issue(s):']
        for i, iss in enumerate(issues, 1):
            lines.append(f'{i}. {iss}')
        body = '\n'.join(lines)
        tags = 'memo'
    send('JSP Open Issues', body, priority='default', tags=tags)


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
    import random
    # Rotate by day-of-year so it's deterministic per day but varies daily
    day_index = datetime.now().timetuple().tm_yday % len(QUIPS)
    quip = QUIPS[day_index]
    send('Apply To Something Today', quip, priority='default', tags='rocket')


def cmd_feedback_review():
    conn = db_connect()
    count = conn.execute('SELECT COUNT(*) FROM feedback_log').fetchone()[0]
    conn.close()

    THRESHOLD = 10
    if count < THRESHOLD:
        print(f'feedback_log has {count} entries — below threshold ({THRESHOLD}). No ping sent.')
        return

    body = (
        f'feedback_log has {count} rejection entries.\n'
        f'Time to review: are the AI scores predicting your rejections?\n'
        f'Run: sqlite3 data/pipeline.db "SELECT reject_reason, COUNT(*) FROM feedback_log GROUP BY reject_reason ORDER BY 2 DESC"'
    )
    send('JSP Feedback Log Ready for Review', body, priority='default', tags='magnifying')


# ── Dispatch ───────────────────────────────────────────────────────────────────
COMMANDS = {
    'daily-stats':     cmd_daily_stats,
    'health-check':    cmd_health_check,
    'issues-ping':     cmd_issues_ping,
    'apply-reminder':  cmd_apply_reminder,
    'feedback-review': cmd_feedback_review,
}

if __name__ == '__main__':
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(f'Usage: notify.py [{"|".join(COMMANDS)}]')
        sys.exit(1)
    COMMANDS[sys.argv[1]]()
