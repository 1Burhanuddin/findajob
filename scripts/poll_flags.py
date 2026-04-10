#!/usr/bin/env python3
# ~/JobSearchPipeline/scripts/poll_flags.py
"""Poll Google Sheet for APPLY_FLAG + REJECT_REASON changes. Mirror to SQLite. Trigger prep."""
import os, sys, subprocess, sqlite3, json, shutil, re
from datetime import datetime, timezone
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.oauth2 import service_account

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from paths import BASE, RCLONE
DB_PATH = f'{BASE}/data/pipeline.db'
LOG_PATH = f'{BASE}/logs/pipeline.jsonl'
SA_FILE = f'{BASE}/config/gsheets_creds.json'
with open(f'{BASE}/config/sheet_id.txt') as f:
    SHEET_ID = f.read().strip()

SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']

# Job board aggregators that should never trigger prep — the "company" is the board, not the employer
AGGREGATOR_PREFIXES = (
    'jobs via ',
    'job via ',
    'posted via ',
    'staffmark',
    'adecco',
    'manpower',
    'randstad',
    'insight global',
    'robert half',
    'kforce',
    'dice',
)

def is_valid_company(company):
    """Return False if company is blank or a known aggregator/job-board wrapper."""
    if not company or not company.strip():
        return False
    c = company.strip().lower()
    return not any(c.startswith(prefix) for prefix in AGGREGATOR_PREFIXES)

def log_event(event_type, **kwargs):
    entry = {'ts': datetime.now(timezone.utc).isoformat(), 'event': event_type, **kwargs}
    with open(LOG_PATH, 'a') as f:
        f.write(json.dumps(entry) + '\n')

def write_audit(conn, job_id, field_changed, old_value, new_value):
    """Write a stage/field transition to audit_log."""
    conn.execute(
        'INSERT INTO audit_log (job_id, field_changed, old_value, new_value) VALUES (?, ?, ?, ?)',
        (job_id, field_changed, str(old_value) if old_value is not None else None, str(new_value))
    )
    conn.commit()

RCLONE_CMD = [
    RCLONE, 'bisync',
    f'{BASE}/companies/',
    'gdrive:01 PROJECTS/Jobs To Apply For',
]


def handle_rejection(conn, job, reason):
    """Store rejection in DB, write to feedback_log, and move company folder to _rejected.
    Drops a marker file named {reason}_{date}.txt inside the moved folder.
    Returns True if a folder was moved (caller should trigger rclone)."""
    now = datetime.now(timezone.utc).isoformat()
    old_stage = job['stage']
    conn.execute(
        'UPDATE jobs SET stage=?, reject_reason=?, updated_at=? WHERE id=?',
        ('rejected', reason, now, job['id'])
    )
    # jd_excerpt: first 500 chars of raw_jd_text for post-hoc analysis
    jd = conn.execute('SELECT raw_jd_text, prep_folder_path FROM jobs WHERE id=?', (job['id'],)).fetchone()
    jd_excerpt = (jd['raw_jd_text'] or '')[:500] if jd and jd['raw_jd_text'] else ''
    conn.execute(
        '''INSERT INTO feedback_log (job_id, title, company, relevance_score, reject_reason, jd_excerpt)
           VALUES (?, ?, ?, ?, ?, ?)''',
        (job['id'], job['title'], job['company'], job['relevance_score'], reason, jd_excerpt)
    )

    # Move company folder to _rejected if it exists
    folder_moved = False
    folder = jd['prep_folder_path'] if jd else None
    if folder and os.path.isdir(folder):
        rejected_dir = os.path.join(BASE, 'companies', '_rejected')
        os.makedirs(rejected_dir, exist_ok=True)
        dest = os.path.join(rejected_dir, os.path.basename(folder))
        shutil.move(folder, dest)
        # Drop a marker file: filesystem-safe reason + date
        safe_reason = re.sub(r'[^\w\s-]', '', reason).strip().replace(' ', '_')[:60]
        date_str = datetime.now().strftime('%Y-%m-%d')
        open(os.path.join(dest, f'REJECTED_{safe_reason}_{date_str}.txt'), 'w').close()
        conn.execute('UPDATE jobs SET prep_folder_path=? WHERE id=?', (dest, job['id']))
        log_event('folder_moved_to_rejected', job_id=job['id'], folder=os.path.basename(folder),
                  reason=reason)
        folder_moved = True

    conn.commit()
    write_audit(conn, job['id'], 'stage', old_stage, 'rejected')
    write_audit(conn, job['id'], 'reject_reason', '', reason)
    log_event('job_rejected', job_id=job['id'], company=job['company'],
              title=job['title'], reason=reason)
    return folder_moved

def main():
    creds = service_account.Credentials.from_service_account_file(SA_FILE, scopes=SCOPES)
    svc = build('sheets', 'v4', credentials=creds)

    # Read APPLY_FLAG (col A), REJECT_REASON (col B), fingerprint (col C) from Dashboard
    try:
        result = svc.spreadsheets().values().get(
            spreadsheetId=SHEET_ID, range='Dashboard!A2:C10000'
        ).execute()
        rows = result.get('values', [])
    except HttpError as e:
        if e.resp.status == 400:
            log_event('poll_flags', found=0, note='sheet_empty_or_range_exceeded')
            return
        raise

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    flagged_jobs   = []
    rejected_count = 0
    applied_count  = 0
    folders_moved  = 0

    for row in rows:
        if len(row) < 3:
            # Need at least col A, B, C. Rows with < 3 cols have no fingerprint — skip.
            # But check if len==1 or 2 for APPLY_FLAG with missing reject/fp
            if len(row) < 1:
                continue
            flag_val   = row[0] if len(row) >= 1 else ''
            reject_val = row[1] if len(row) >= 2 else ''
            fp         = row[2] if len(row) >= 3 else ''
            if not fp:
                continue
        else:
            flag_val   = row[0]
            reject_val = row[1]
            fp         = row[2]

        if not fp:
            continue

        # STATUS dropdown: "Flag for Prep" triggers prep; others update DB stage
        is_flagged  = (flag_val == 'Flag for Prep')
        is_rejected = bool(reject_val and reject_val.strip())

        STATUS_STAGE_MAP = {
            'Applied':      'applied',
            'Interviewing': 'interview',
            'Offer':        'offer',
            'Withdrew':     'withdrawn',
        }

        job = conn.execute('''
            SELECT id, title, company, url, stage, apply_flag, reject_reason, relevance_score
            FROM jobs WHERE fingerprint = ?
        ''', (fp,)).fetchone()

        if not job:
            continue

        # ── Rejection takes priority ─────────────────────────────────────
        if is_rejected and job['stage'] != 'rejected':
            if handle_rejection(conn, job, reject_val.strip()):
                folders_moved += 1
            rejected_count += 1
            continue  # don't also trigger prep for this job

        # ── Post-application status updates (Applied / Interviewing / Offer / Withdrew) ──
        if flag_val in STATUS_STAGE_MAP:
            new_stage = STATUS_STAGE_MAP[flag_val]
            if job['stage'] != new_stage:
                now = datetime.now(timezone.utc).isoformat()
                conn.execute('UPDATE jobs SET stage=?, updated_at=? WHERE id=?',
                             (new_stage, now, job['id']))
                conn.commit()
                write_audit(conn, job['id'], 'stage', job['stage'], new_stage)
                log_event('job_stage_updated', job_id=job['id'], company=job['company'],
                          title=job['title'], stage=new_stage)

                # Move prep folder to _applied when marked Applied
                if new_stage == 'applied':
                    jd = conn.execute('SELECT prep_folder_path FROM jobs WHERE id=?',
                                      (job['id'],)).fetchone()
                    folder = jd['prep_folder_path'] if jd else None
                    if folder and os.path.isdir(folder):
                        applied_dir = os.path.join(BASE, 'companies', '_applied')
                        os.makedirs(applied_dir, exist_ok=True)
                        dest = os.path.join(applied_dir, os.path.basename(folder))
                        shutil.move(folder, dest)
                        conn.execute('UPDATE jobs SET prep_folder_path=? WHERE id=?',
                                     (dest, job['id']))
                        conn.commit()
                        log_event('folder_moved_to_applied', job_id=job['id'],
                                  folder=os.path.basename(folder))
                        folders_moved += 1
                    applied_count += 1

            continue  # don't trigger prep for these statuses

        # ── Flag for Prep handling ───────────────────────────────────────
        if is_flagged and not job['apply_flag']:
            conn.execute('UPDATE jobs SET apply_flag=1, updated_at=? WHERE id=?',
                        (datetime.now(timezone.utc).isoformat(), job['id']))
            conn.commit()
            write_audit(conn, job['id'], 'apply_flag', '0', '1')

        if is_flagged and job['stage'] in ('scored', 'manual_review', 'enriched'):
            if not is_valid_company(job['company']):
                log_event('poll_flags_skipped', reason='invalid_company',
                          company=job['company'], title=job['title'], job_id=job['id'])
                continue
            flagged_jobs.append({
                'id': job['id'], 'title': job['title'],
                'company': job['company'], 'url': job['url']
            })

    conn.close()

    if rejected_count:
        log_event('poll_flags_rejections', count=rejected_count, folders_moved=folders_moved)
        subprocess.Popen([sys.executable, f'{BASE}/scripts/sync_sheet.py'])

    if applied_count:
        log_event('poll_flags_applied', count=applied_count, folders_moved=folders_moved)
        subprocess.Popen([sys.executable, f'{BASE}/scripts/sync_sheet.py'])

    # Trigger rclone bisync immediately if any folders were moved
    if folders_moved:
        log_event('rclone_triggered', reason='folder_move', count=folders_moved)
        subprocess.Popen(RCLONE_CMD)  # fire-and-forget, don't block the poller

    if not flagged_jobs:
        log_event('poll_flags', found=0, rejections=rejected_count)
        return

    log_event('poll_flags', found=len(flagged_jobs), rejections=rejected_count,
              jobs=[f"{j['company']} - {j['title']}" for j in flagged_jobs])

    # Trigger prep for each flagged job — fire-and-forget so the poller
    # doesn't block for the duration of prep (resume + cover letter + briefing
    # can take several minutes; blocking here hangs the entire poll cycle).
    for job in flagged_jobs:
        subprocess.Popen([
            sys.executable, f'{BASE}/scripts/prep_application.py',
            job['company'], job['title'], job['url'], job['id']
        ])

if __name__ == '__main__':
    main()
