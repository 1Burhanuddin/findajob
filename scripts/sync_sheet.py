#!/usr/bin/env python3
# ~/JobSearchPipeline/scripts/sync_sheet.py
"""
Sync SQLite → Google Sheets.
  Sheet1:    Filtered job archive (score>=5, lifecycle stages, <14d old, or target company).
  Dashboard: Actionable queue (score>=7 scored/manual_review, or materials_drafted).
  Review:    Manual review triage queue (stage=manual_review, null-score scorer failures).
             poll_flags.py reads STATUS + REJECT_REASON from Dashboard and Review tabs.
"""
import os, sys, sqlite3, json
from datetime import datetime, timezone
from googleapiclient.discovery import build
from pathlib import Path
from google.oauth2 import service_account

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from paths import BASE
from scorer_prefilter import _is_tier1
from utils import log_event
DB_PATH = f'{BASE}/data/pipeline.db'
SA_FILE = f'{BASE}/config/gsheets_creds.json'
with open(f'{BASE}/config/sheet_id.txt') as f:
    SHEET_ID = f.read().strip()

SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

# ── Sheet1: full archive ──────────────────────────────────────────────────────
# Col A: fingerprint (hidden), Col B: APPLY_FLAG, then data columns.
S1_HEADERS = [
    'fingerprint', 'APPLY_FLAG',
    'relevance_score', 'title', 'company', 'location', 'remote_status',
    'stage', 'known_contacts', 'comp_estimate', 'ai_notes',
    'date_found', 'source', 'url',
]
S1_COL_MAP = {
    'fingerprint': 'fingerprint', 'apply_flag': 'APPLY_FLAG',
    'relevance_score': 'relevance_score', 'title': 'title',
    'company': 'company', 'location': 'location', 'remote_status': 'remote_status',
    'stage': 'stage', 'known_contacts': 'known_contacts',
    'comp_estimate': 'comp_estimate', 'ai_notes': 'ai_notes',
    'created_at': 'date_found', 'source': 'source', 'url': 'url',
}
S1_LOOKUP = {sh: sc for sc, sh in S1_COL_MAP.items()}

# ── Dashboard: actionable queue ───────────────────────────────────────────────
# Col A: APPLY_FLAG (checkbox), Col B: REJECT_REASON (dropdown), Col C: fingerprint (hidden).
# Title column is rendered as =HYPERLINK(url, title) — no separate URL column.
DASH_HEADERS = [
    'APPLY_FLAG', 'REJECT_REASON', 'fingerprint',
    'fit_score', 'probability_score', 'relevance_score',
    'title', 'company', 'location', 'remote_status',
    'known_contacts', 'comp_estimate', 'ai_notes', 'date_found',
]
DASH_COL_MAP = {
    'apply_flag': 'APPLY_FLAG', 'reject_reason': 'REJECT_REASON', 'fingerprint': 'fingerprint',
    'fit_score': 'fit_score', 'probability_score': 'probability_score',
    'relevance_score': 'relevance_score', 'title': 'title',
    'company': 'company', 'location': 'location', 'remote_status': 'remote_status',
    'known_contacts': 'known_contacts', 'comp_estimate': 'comp_estimate',
    'ai_notes': 'ai_notes', 'created_at': 'date_found',
}
DASH_LOOKUP = {sh: sc for sc, sh in DASH_COL_MAP.items()}


def hyperlink(url, label):
    """Return a Sheets HYPERLINK formula. Escapes double quotes in both args."""
    safe_url   = str(url   or '').replace('"', '%22')
    safe_label = str(label or '').replace('"', '""')
    if not safe_url:
        return safe_label
    return f'=HYPERLINK("{safe_url}","{safe_label}")'


def safe_str(val):
    """Escape leading formula trigger characters to prevent formula injection.

    Google Sheets interprets strings starting with =, +, -, or @ as formulas
    when valueInputOption='USER_ENTERED'. Prefix with a single quote to force
    literal text storage. The apostrophe is consumed by Sheets and not displayed.
    """
    s = '' if val is None else str(val)
    if s and s[0] in ('=', '+', '-', '@'):
        return "'" + s
    return s


def build_row(row, headers, lookup, status_override=None, reject_override=None, use_status=False):
    sheet_row = []
    for header in headers:
        sqlite_col = lookup.get(header)
        val = row[sqlite_col] if sqlite_col and sqlite_col in row.keys() else ''
        if header == 'APPLY_FLAG':
            if use_status:
                # Dashboard: derive status from DB state; user overrides preserved via status_override
                if status_override is not None:
                    sheet_row.append(status_override)
                elif row['stage'] == 'materials_drafted':
                    sheet_row.append('Ready to Apply')
                elif bool(val):  # apply_flag=1, prep not yet run
                    sheet_row.append('Flag for Prep')
                else:
                    sheet_row.append('')
            else:
                # Sheet1: write TRUE/FALSE for the checkbox
                sheet_row.append('TRUE' if bool(val) else 'FALSE')
        elif header == 'REJECT_REASON':
            sheet_row.append(safe_str(reject_override if reject_override is not None else (val or '')))
        else:
            sheet_row.append(safe_str(val))
    return sheet_row


SHEET1_ARCHIVE_DAYS = 14  # jobs younger than this always appear regardless of score

def sync_sheet1(svc, conn):
    # Archival filter: only sync rows that are actionable or worth a glance.
    # Low-score old jobs from non-target companies stay in DB only.
    rows = conn.execute('''
        SELECT * FROM jobs
        WHERE (dupe_of = '' OR dupe_of IS NULL)
          AND (
            relevance_score >= 5
            OR stage IN ('manual_review', 'prep_in_progress', 'materials_drafted',
                         'applied', 'interview', 'offer', 'withdrawn')
            OR julianday('now') - julianday(created_at) <= ?
          )
        ORDER BY
            CASE WHEN relevance_score IS NOT NULL THEN relevance_score ELSE 0 END DESC,
            created_at DESC
    ''', (SHEET1_ARCHIVE_DAYS,)).fetchall()

    # Safety net: also include target-company jobs regardless of score/age
    target_ids = {r['id'] for r in rows}
    all_rows = conn.execute('''
        SELECT * FROM jobs
        WHERE (dupe_of = '' OR dupe_of IS NULL)
          AND relevance_score IS NOT NULL
          AND relevance_score < 5
          AND stage NOT IN ('manual_review', 'prep_in_progress', 'materials_drafted',
                            'applied', 'interview', 'offer', 'withdrawn')
          AND julianday('now') - julianday(created_at) > ?
    ''', (SHEET1_ARCHIVE_DAYS,)).fetchall()
    target_extras = [r for r in all_rows if r['id'] not in target_ids and _is_tier1(r['company'])]

    combined = list(rows) + target_extras
    # Highest score first, then newest first within same score (ISO dates sort lexically)
    combined.sort(key=lambda r: r['created_at'] or '', reverse=True)
    combined.sort(key=lambda r: -(r['relevance_score'] if r['relevance_score'] is not None else 0))

    sheet_rows = [S1_HEADERS] + [build_row(r, S1_HEADERS, S1_LOOKUP) for r in combined]

    svc.spreadsheets().values().clear(
        spreadsheetId=SHEET_ID, range='Sheet1!A2:N10000'
    ).execute()
    svc.spreadsheets().values().update(
        spreadsheetId=SHEET_ID, range='Sheet1!A1',
        valueInputOption='USER_ENTERED', body={'values': sheet_rows}
    ).execute()
    total_db = conn.execute('SELECT count(*) FROM jobs WHERE dupe_of = "" OR dupe_of IS NULL').fetchone()[0]
    n_synced = len(sheet_rows) - 1
    print(f'Sheet1: {n_synced} rows synced ({total_db - n_synced} archived from view)')
    return n_synced


def sync_dashboard(svc, conn):
    # Read current Dashboard state so we don't clobber user-set values since last poll.
    # Dashboard: col A = APPLY_FLAG, col B = REJECT_REASON, col C = fingerprint
    try:
        current = svc.spreadsheets().values().get(
            spreadsheetId=SHEET_ID, range='Dashboard!A2:C10000'
        ).execute().get('values', [])
        # Preserve user-set status strings (non-empty, valid values only) not yet polled
        # Only preserve user-driven statuses not yet polled.
        # 'Ready to Apply' is system-derived (from stage=materials_drafted) — don't preserve.
        # 'Flag for Prep' is preserved so user actions survive the next sync before poll runs.
        VALID_STATUSES = {'Flag for Prep', 'Applied', 'Interviewing', 'Offer', 'Withdrew'}
        pending_statuses = {r[2]: r[0] for r in current
                            if len(r) >= 3 and r[0] in VALID_STATUSES}
        pending_rejects  = {r[2]: r[1] for r in current if len(r) >= 3 and r[1]}
    except Exception:
        pending_statuses = {}
        pending_rejects  = {}

    rows = conn.execute('''
        SELECT * FROM jobs
        WHERE (dupe_of = '' OR dupe_of IS NULL)
          AND (
            (relevance_score >= 7 AND stage IN ('scored', 'manual_review'))
            OR stage IN ('prep_in_progress', 'materials_drafted')
          )
        ORDER BY
            CASE stage WHEN 'materials_drafted' THEN 0 ELSE 1 END,
            CASE WHEN probability_score IS NOT NULL THEN probability_score ELSE 0 END DESC,
            CASE WHEN fit_score IS NOT NULL THEN fit_score ELSE 0 END DESC,
            CASE WHEN relevance_score IS NOT NULL THEN relevance_score ELSE 0 END DESC,
            created_at DESC
    ''').fetchall()

    sheet_rows = [DASH_HEADERS]
    for row in rows:
        fp = row['fingerprint']
        # Skip materials_drafted jobs whose folder no longer exists on disk
        # (moved to _applied/_rejected without DB update, or manually deleted)
        if row['stage'] == 'materials_drafted':
            folder = row['prep_folder_path']
            if not folder or not Path(folder).is_dir():
                continue
        # Prefer the value the user set in the sheet (not yet polled) over the DB state.
        # Exception: once stage=materials_drafted, system-derived "Ready to Apply" wins
        # over stale "Flag for Prep" (prep has completed, user needs to review materials).
        # Pass None (not '') so build_row falls through to stage-derived logic.
        pending = pending_statuses.get(fp)
        if pending and not (pending == 'Flag for Prep' and row['stage'] == 'materials_drafted'):
            status_override = pending
        else:
            status_override = None
        # Prefer pending (user-set) reject reason; fall back to DB value
        reject_override = pending_rejects.get(fp, row['reject_reason'] or '')
        sheet_row = build_row(row, DASH_HEADERS, DASH_LOOKUP,
                              status_override=status_override,
                              reject_override=reject_override,
                              use_status=True)
        # Replace plain title with a HYPERLINK formula pointing to the JD URL
        title_idx = DASH_HEADERS.index('title')
        sheet_row[title_idx] = hyperlink(row['url'], row['title'])
        # If materials have been prepped and we have a Drive folder URL, turn the
        # company cell into a HYPERLINK to the Drive folder for quick access.
        gdrive_url = row['gdrive_folder_url'] if 'gdrive_folder_url' in row.keys() else None
        if (row['stage'] == 'materials_drafted' and gdrive_url
                and str(gdrive_url).startswith('http')):
            company_idx = DASH_HEADERS.index('company')
            sheet_row[company_idx] = hyperlink(gdrive_url, row['company'])
        sheet_rows.append(sheet_row)

    svc.spreadsheets().values().clear(
        spreadsheetId=SHEET_ID, range='Dashboard!A2:N10000'
    ).execute()
    svc.spreadsheets().values().update(
        spreadsheetId=SHEET_ID, range='Dashboard!A1',
        valueInputOption='USER_ENTERED', body={'values': sheet_rows}
    ).execute()
    n_prepped = sum(1 for r in rows if r['stage'] == 'materials_drafted')
    n_queued  = len(rows) - n_prepped
    n_dash = len(sheet_rows) - 1
    print(f'Dashboard: {n_dash} jobs ({n_queued} queued, {n_prepped} prepped/pending apply)')
    return n_dash


# ── Review: manual_review triage queue ────────────────────────────────────────
# Col A: STATUS (Promote / blank), Col B: REJECT_REASON, Col C: fingerprint (hidden).
REVIEW_HEADERS = [
    'STATUS', 'REJECT_REASON', 'fingerprint',
    'title', 'company', 'score_flag_reason', 'source', 'date_found',
]
REVIEW_LOOKUP = {
    'STATUS': None, 'REJECT_REASON': 'reject_reason', 'fingerprint': 'fingerprint',
    'title': 'title', 'company': 'company', 'score_flag_reason': 'score_flag_reason',
    'source': 'source', 'date_found': 'created_at',
}


def sync_review(svc, conn):
    """Sync stage=manual_review jobs to the Review tab for human triage."""
    # Read current Review tab state to preserve user-set values not yet polled
    try:
        current = svc.spreadsheets().values().get(
            spreadsheetId=SHEET_ID, range='Review!A2:C10000'
        ).execute().get('values', [])
        pending_statuses = {r[2]: r[0] for r in current
                           if len(r) >= 3 and r[0].strip()}
        pending_rejects  = {r[2]: r[1] for r in current
                           if len(r) >= 3 and r[1].strip()}
    except Exception:
        pending_statuses = {}
        pending_rejects  = {}

    rows = conn.execute('''
        SELECT * FROM jobs
        WHERE (dupe_of = '' OR dupe_of IS NULL)
          AND stage = 'manual_review'
        ORDER BY
            CASE WHEN company IS NOT NULL AND company != '' THEN 0 ELSE 1 END,
            company, created_at DESC
    ''').fetchall()

    sheet_rows = [REVIEW_HEADERS]
    for row in rows:
        fp = row['fingerprint']
        sheet_row = []
        for header in REVIEW_HEADERS:
            sqlite_col = REVIEW_LOOKUP.get(header)
            if header == 'STATUS':
                sheet_row.append(pending_statuses.get(fp, ''))
            elif header == 'REJECT_REASON':
                sheet_row.append(safe_str(pending_rejects.get(fp, row['reject_reason'] or '')))
            elif header == 'title':
                sheet_row.append(hyperlink(row['url'], row['title']))
            else:
                val = row[sqlite_col] if sqlite_col and sqlite_col in row.keys() else ''
                sheet_row.append(safe_str(val))
        sheet_rows.append(sheet_row)

    svc.spreadsheets().values().clear(
        spreadsheetId=SHEET_ID, range='Review!A2:H10000'
    ).execute()
    svc.spreadsheets().values().update(
        spreadsheetId=SHEET_ID, range='Review!A1',
        valueInputOption='USER_ENTERED', body={'values': sheet_rows}
    ).execute()
    n_review = len(sheet_rows) - 1
    print(f'Review: {n_review} manual_review jobs synced')
    return n_review


def main():
    creds = service_account.Credentials.from_service_account_file(SA_FILE, scopes=SCOPES)
    svc = build('sheets', 'v4', credentials=creds)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    try:
        n_sheet1 = sync_sheet1(svc, conn)
        n_dash = sync_dashboard(svc, conn)
        n_review = sync_review(svc, conn)
        log_event('sync_complete', sheet1=n_sheet1, dashboard=n_dash, review=n_review)
    except Exception as e:
        log_event('sync_failed', error=str(e))
        raise

    conn.close()


if __name__ == '__main__':
    main()
