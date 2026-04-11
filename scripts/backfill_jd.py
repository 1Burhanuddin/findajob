#!/usr/bin/env python3
# ~/JobSearchPipeline/scripts/backfill_jd.py
"""
One-time backfill: fetch missing LinkedIn JD text for gmail_linkedin jobs.
The /comm/ regex bug meant extract_linkedin_job_id() never matched gmail URLs,
so all gmail_linkedin jobs were scored without JD. This script fetches JDs
via the RapidAPI LinkedIn get endpoint and updates the DB.

Also backfills blank company names from the API response.

Usage:
    python3 scripts/backfill_jd.py          # fetch JDs only
    python3 scripts/backfill_jd.py --rescore # fetch JDs then rescore affected jobs
"""
import os, sys, re, sqlite3, json, time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from paths import BASE
from utils import log_event, load_env

DB_PATH = f'{BASE}/data/pipeline.db'

load_env()

_LINKEDIN_JOB_ID_RE = re.compile(r'linkedin\.com/(?:comm/)?jobs/view/(\d+)', re.IGNORECASE)

def extract_job_id(url):
    m = _LINKEDIN_JOB_ID_RE.search(url or '')
    return m.group(1) if m else None

def clean_company(raw):
    """Minimal company cleaning — strip trailing metadata."""
    if not raw:
        return ''
    raw = re.sub(r'\s*\d[\d,]+ followers\s*$', '', raw, flags=re.IGNORECASE)
    raw = re.sub(r'\s*·.*$', '', raw)
    return raw.strip()

def fetch_linkedin_jd(api_id):
    """Fetch JD and company from LinkedIn API. Returns (description, company) or (None, None)."""
    import requests as req
    api_key = os.environ.get('RAPIDAPI_KEY', '')
    if not api_key or not api_id:
        return None, None
    try:
        response = req.get(
            'https://jobs-api14.p.rapidapi.com/v2/linkedin/get',
            headers={
                'x-rapidapi-host': 'jobs-api14.p.rapidapi.com',
                'x-rapidapi-key': api_key,
            },
            params={'id': str(api_id)},
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()
        if data.get('hasError'):
            return None, None
        payload = data.get('data', {})
        description = payload.get('description', '') or ''
        company = (
            payload.get('companyName') or
            payload.get('company') or
            payload.get('organizationName') or
            (payload.get('hiringOrganization') or {}).get('name') or
            ''
        )
        desc = description[:8000] if description else None
        co = clean_company(company) if company else None
        return desc, co
    except Exception as e:
        return None, None


def main():
    rescore = '--rescore' in sys.argv

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL')

    rows = conn.execute('''
        SELECT id, url, title, company, raw_jd_text, stage
        FROM jobs
        WHERE source = 'gmail_linkedin'
          AND (dupe_of = '' OR dupe_of IS NULL)
          AND stage != 'rejected'
    ''').fetchall()

    # Filter to jobs with extractable IDs and missing/unusable JD
    candidates = []
    for r in rows:
        api_id = extract_job_id(r['url'])
        if not api_id:
            continue
        jd = r['raw_jd_text'] or ''
        if jd.strip() and len(jd.strip()) >= 50 and 'unavailable' not in jd.lower():
            continue  # already has good JD
        candidates.append((r, api_id))

    print(f"Jobs to backfill: {len(candidates)}")
    log_event('backfill_jd_started', total=len(candidates))

    fetched = 0
    failed = 0
    company_updated = 0
    backfilled_ids = []

    for i, (row, api_id) in enumerate(candidates, 1):
        print(f"[{i}/{len(candidates)}] {row['title'][:50]} @ {row['company'] or '(blank)'}", end='', flush=True)

        desc, company = fetch_linkedin_jd(api_id)

        if desc and len(desc.strip()) >= 30:
            now = datetime.now(timezone.utc).isoformat()
            conn.execute('UPDATE jobs SET raw_jd_text=?, updated_at=? WHERE id=?',
                         (desc, now, row['id']))
            # Backfill blank company if API returned one
            if company and not row['company']:
                conn.execute('UPDATE jobs SET company=? WHERE id=?', (company, row['id']))
                company_updated += 1
            conn.commit()
            fetched += 1
            backfilled_ids.append(row['id'])
            print(f"  ✓ {len(desc)} chars" + (f" +company={company}" if company and not row['company'] else ''))
        else:
            failed += 1
            print(f"  ✗ no JD returned")

        time.sleep(0.3)  # rate limit

    print(f"\nBackfill complete: {fetched} fetched, {failed} failed, {company_updated} companies updated")
    log_event('backfill_jd_complete', fetched=fetched, failed=failed,
              company_updated=company_updated)

    conn.close()

    if rescore and backfilled_ids:
        print(f"\nRescoring {fetched} backfilled jobs...")
        import subprocess
        subprocess.run([sys.executable, f'{BASE}/scripts/rescore_all.py'], check=False)


if __name__ == '__main__':
    main()
