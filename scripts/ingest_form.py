#!/usr/bin/env python3
# ~/JobSearchPipeline/scripts/ingest_form.py
"""
Poll a Google Form responses sheet and inject new jobs into the pipeline DB.

Setup (one-time):
  1. Create a Google Form with these fields (in order):
       Q1: Job URL           (short answer, required)
       Q2: Company Name      (short answer, required)
       Q3: Job Title         (short answer, required)
       Q4: Location          (short answer, optional)
       Q5: Remote Status     (multiple choice: Remote / Hybrid / On-site / Unknown)
       Q6: Notes / Why interested  (paragraph, optional)
       Q7: Known contacts    (short answer, optional)
       Q8: Generate company folder immediately  (multiple choice: Yes / No)
  2. In the form: Responses → Link to Sheets → create a new spreadsheet.
  3. Share that spreadsheet with: jobsearch-pipeline@jobsearchpipeline.iam.gserviceaccount.com (Editor)
  4. Copy the spreadsheet ID and save it:
       echo 'YOUR_SHEET_ID' > ~/JobSearchPipeline/config/form_responses_sheet_id.txt

The script writes 'Processed: <timestamp>' to col J (column 10) of each handled row.
Run manually or add to the poller launchd agent.
"""
import os, sys, sqlite3, subprocess, hashlib, json
from datetime import datetime, timezone
from googleapiclient.discovery import build
from google.oauth2 import service_account

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from paths import BASE
DB_PATH = f'{BASE}/data/pipeline.db'
LOG_PATH = f'{BASE}/logs/pipeline.jsonl'
SA_FILE = f'{BASE}/config/gsheets_creds.json'
FORM_SHEET_ID_FILE = f'{BASE}/config/form_responses_sheet_id.txt'

SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

# Column indices in the form responses sheet (0-based, after the Timestamp col A)
COL_TIMESTAMP  = 0   # A — auto-added by Google Forms
COL_URL        = 1   # B — Q1: Job URL
COL_COMPANY    = 2   # C — Q2: Company Name
COL_TITLE      = 3   # D — Q3: Job Title
COL_LOCATION   = 4   # E — Q4: Location
COL_REMOTE     = 5   # F — Q5: Remote Status
COL_NOTES      = 6   # G — Q6: Notes / Why interested
COL_CONTACTS   = 7   # H — Q7: Known contacts
COL_GEN_FOLDER = 8   # I — Q8: Generate company folder immediately
COL_PROCESSED  = 9   # J — written by this script


def load_env():
    env = {}
    try:
        with open(f'{BASE}/data/.env') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, _, v = line.partition('=')
                    env[k.strip()] = v.strip().strip('"').strip("'")
    except FileNotFoundError:
        pass
    return env


def log_event(event_type, **kwargs):
    entry = {'ts': datetime.now(timezone.utc).isoformat(), 'event': event_type, **kwargs}
    with open(LOG_PATH, 'a') as f:
        f.write(json.dumps(entry) + '\n')


def clean(s):
    return (s or '').strip()


def make_fingerprint(url, company, title):
    key = f'{url}|{company}|{title}'.lower()
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def main():
    if not os.path.exists(FORM_SHEET_ID_FILE):
        print(f'ERROR: {FORM_SHEET_ID_FILE} not found.')
        print('See setup instructions at the top of this script.')
        sys.exit(1)

    with open(FORM_SHEET_ID_FILE) as f:
        form_sheet_id = f.read().strip()

    creds = service_account.Credentials.from_service_account_file(SA_FILE, scopes=SCOPES)
    svc   = build('sheets', 'v4', credentials=creds)

    # Read all form responses (row 1 is the header, data starts at row 2)
    result = svc.spreadsheets().values().get(
        spreadsheetId=form_sheet_id,
        range='Form Responses 1!A2:J10000',
    ).execute()
    rows = result.get('values', [])

    if not rows:
        print('No form responses found.')
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    env = load_env()

    processed_count = 0
    updates = []  # (row_index, processed_timestamp) to write back

    for i, row in enumerate(rows):
        # Pad to at least COL_PROCESSED columns
        while len(row) <= COL_PROCESSED:
            row.append('')

        # Skip already processed
        if row[COL_PROCESSED]:
            continue

        url      = clean(row[COL_URL]      if len(row) > COL_URL      else '')
        company  = clean(row[COL_COMPANY]  if len(row) > COL_COMPANY  else '')
        title    = clean(row[COL_TITLE]    if len(row) > COL_TITLE    else '')
        location = clean(row[COL_LOCATION] if len(row) > COL_LOCATION else '')
        remote   = clean(row[COL_REMOTE]   if len(row) > COL_REMOTE   else 'Unknown')
        notes    = clean(row[COL_NOTES]    if len(row) > COL_NOTES    else '')
        contacts = clean(row[COL_CONTACTS] if len(row) > COL_CONTACTS else '')
        gen_folder = clean(row[COL_GEN_FOLDER] if len(row) > COL_GEN_FOLDER else 'No')

        if not url or not company or not title:
            print(f'Row {i+2}: skipping (missing required fields)')
            continue

        fp = make_fingerprint(url, company, title)
        now = datetime.now(timezone.utc).isoformat()

        # Check for duplicate
        existing = conn.execute('SELECT id FROM jobs WHERE fingerprint=?', (fp,)).fetchone()
        if existing:
            print(f'Row {i+2}: duplicate — {company} / {title} already in DB')
            updates.append((i + 2, f'Duplicate: already in DB as {existing["id"]}'))
            continue

        job_id = f'form-{fp}'
        conn.execute('''
            INSERT INTO jobs (
                id, fingerprint, url, title, company, location, source,
                remote_status, known_contacts, ai_notes,
                relevance_score, stage, apply_flag,
                created_at, updated_at, dupe_of
            ) VALUES (?, ?, ?, ?, ?, ?, 'manual_form', ?, ?, ?, 8, 'scored', 0, ?, ?, '')
        ''', (job_id, fp, url, title, company, location,
              remote or 'Unknown', contacts, notes, now, now))
        conn.commit()

        log_event('form_job_ingested', job_id=job_id, company=company, title=title, url=url)
        print(f'Row {i+2}: ingested — {company} / {title} (id={job_id})')
        processed_count += 1

        if gen_folder.lower() in ('yes', 'y', 'true'):
            print(f'  → Generating company folder...')
            subprocess.run([
                sys.executable,
                f'{BASE}/scripts/prep_application.py',
                company, title, url, job_id,
            ], check=False)

        updates.append((i + 2, f'Processed: {now}'))

    conn.close()

    # Write processed timestamps back to form sheet col J
    if updates:
        body_values = []
        # Find the row range — we'll write to each row individually via batch
        batch_data = []
        for row_num, status in updates:
            batch_data.append({
                'range': f'Form Responses 1!J{row_num}',
                'values': [[status]],
            })
        svc.spreadsheets().values().batchUpdate(
            spreadsheetId=form_sheet_id,
            body={'valueInputOption': 'RAW', 'data': batch_data},
        ).execute()

    # Trigger sync_sheet to push new jobs to the Dashboard
    if processed_count > 0:
        subprocess.run([sys.executable, f'{BASE}/scripts/sync_sheet.py'],
                       check=False)
        print(f'\nDone. {processed_count} new job(s) ingested and synced to Dashboard.')
    else:
        print('No new submissions to process.')


if __name__ == '__main__':
    main()
