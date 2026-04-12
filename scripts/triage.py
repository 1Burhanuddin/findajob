#!/usr/bin/env python3
# ~/JobSearchPipeline/scripts/triage.py
"""
Daily triage pipeline. Fetches jobs, deduplicates, enriches, scores,
and writes results to SQLite. Sheet sync is a separate script called at the end.
"""
import os, sys, json, hashlib, html, re, csv, signal, subprocess, time, uuid, shutil
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from paths import BASE, PANDOC, AICHAT
from scorer_prefilter import prefilter_score
from utils import (
    log_event, write_audit, load_env, validate_llm_json, jd_is_usable,
    _JD_WALL_SIGNALS, strip_jd_boilerplate, JD_MAX_CHARS,
    is_aggregator_company, is_ingest_noise_title,
)


# ── Signal handler: log a termination event before exiting ───────────────────
# systemd sends SIGTERM when the service hits TimeoutStartSec (default: 30min).
# Without this handler the process dies silently and pipeline_complete never
# fires, causing notify.py health-check to miss a real failure.
def _on_sigterm(signum, frame):
    log_event('pipeline_terminated', signal='SIGTERM',
              note='Received SIGTERM — likely systemd timeout or manual stop.')
    sys.exit(143)  # 128 + SIGTERM(15)

signal.signal(signal.SIGTERM, _on_sigterm)

DB_PATH = f'{BASE}/data/pipeline.db'
CONNECTIONS = f'{BASE}/data/connections.csv'
SCHEMA_PATH = f'{BASE}/config/scoring_schema.json'
PROFILE_PATH = f'{BASE}/config/profile.md'

def _role_model(role_name):
    """Read the model: field from a role's YAML frontmatter."""
    role_path = f'{BASE}/config/roles/{role_name}.md'
    try:
        with open(role_path) as f:
            in_front = False
            for line in f:
                if line.strip() == '---':
                    in_front = not in_front
                    continue
                if in_front and line.startswith('model:'):
                    return line.split(':', 1)[1].strip()
    except OSError:
        pass
    return 'unknown'

SCORER_MODEL = _role_model('job_scorer')
GMAIL_CREDS = f'{BASE}/config/gmail_oauth_client.json'
GMAIL_TOKEN = f'{BASE}/config/gmail_token.json'
GMAIL_SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

load_env()

import sqlite3

# ── Normalization & Dedup ──
ABBREVIATIONS = {
    r'\bsr\.?\b': 'senior', r'\bjr\.?\b': 'junior', r'\bmgr\.?\b': 'manager',
    r'\bdir\.?\b': 'director', r'\beng\.?\b': 'engineer', r'\bengr\.?\b': 'engineer',
    r'\bops\.?\b': 'operations', r'\binfra\.?\b': 'infrastructure',
    r'\bvp\b': 'vice president', r'\bsvp\b': 'senior vice president',
    r'\bhw\b': 'hardware', r'\bsw\b': 'software', r'\bdc\b': 'data center',
    r'\bmfg\b': 'manufacturing', r'\bpgm\b': 'program', r'\btpm\b': 'technical program manager',
}

def normalize(text):
    text = text.lower().strip()
    for pattern, replacement in ABBREVIATIONS.items():
        text = re.sub(pattern, replacement, text)
    text = re.sub(r'[^a-z0-9 ]', ' ', text)
    return re.sub(r'\s+', ' ', text).strip()

def fingerprint(title, company, location=''):
    key = normalize(title) + '|' + normalize(company) + '|' + normalize(location)
    return hashlib.sha256(key.encode()).hexdigest()[:16]

# ── Title Cleaning ──
# Job boards (especially Indeed via Jobs API) append metadata directly to the title field:
# board name, location, salary, time-ago, badges. Strip everything after these markers.
_TITLE_SPLIT_PATTERNS = re.compile(
    r'(?:'
    r'Jobs via \w[\w ]*·'          # "Jobs via Dice ·"
    r'|\bvia \w[\w ]*·'            # "via LinkedIn ·"
    r'|\s·\s'                      # generic " · " separator
    r'|\s[-–]\s(?:Remote|Hybrid|On-?site|Contract|Full.?time|Part.?time)'
    r'|\$[\d,]+[Kk]?\s*[-–]'      # salary range start "$140K -"
    r'|\d+\s*(?:hour|day|week|month)s?\s+ago'  # "2 days ago"
    r'|(?:Easy|Quick)\s+Apply'
    r'|Actively\s+recruiting'
    r'|Fast\s+growing'
    r')',
    re.IGNORECASE
)

def clean_title(raw_title):
    """Strip job board metadata appended to title field by Indeed/Jobs API."""
    m = _TITLE_SPLIT_PATTERNS.search(raw_title)
    if m:
        raw_title = raw_title[:m.start()]
    return raw_title.strip(' ·-–')

# Company field from LinkedIn API often has location/metadata appended:
# "Google – Multiple Sites4 days ago", "Google · Sunnyvale, CA, US 12 connections"
_COMPANY_SPLIT_PATTERNS = re.compile(
    r'(?:'
    r'\s[·–—-]\s'                     # " · " or " – " separator before location
    r'|\d+\s+connections?'            # "12 connections"
    r'|\d+\s*(?:hour|day|week|month)s?\s+ago'  # "3 days ago"
    r'|(?:Easy|Quick)\s+Apply'
    r'|Actively\s+recruiting'
    r'|,\s*[A-Z][a-z]+,\s*(?:United States|US|Canada|UK)'  # ", Sunnyvale, United States"
    r')',
    re.IGNORECASE
)

def clean_company(raw_company):
    """Strip location/metadata appended to company field by LinkedIn/Indeed API."""
    if not raw_company:
        return ''
    m = _COMPANY_SPLIT_PATTERNS.search(raw_company)
    if m:
        raw_company = raw_company[:m.start()]
    return raw_company.strip(' ·-–,')

# ── JD Fetching ──
def fetch_jd_curl(url):
    """Fetch JD by curling a public URL (Greenhouse/RSS/Lever sources)."""
    try:
        raw = subprocess.run(['curl', '-sL', '--max-time', '10', url],
            capture_output=True, text=True).stdout
        text = subprocess.run([PANDOC, '-f', 'html', '-t', 'plain'],
            input=raw, capture_output=True, text=True).stdout
        return strip_jd_boilerplate(text)[:JD_MAX_CHARS]
    except Exception as e:
        return f'[ERROR fetching JD: {e}]'

def fetch_linkedin_job_data(job_id):
    """
    Fetch full job data via LinkedIn get endpoint.
    Returns {'description': str|None, 'company': str|None}.
    LinkedIn job URLs require auth — curling them always returns "Job not found".
    The API get endpoint is the only reliable path.
    """
    import requests as req
    api_key = os.environ.get('RAPIDAPI_KEY', '')
    if not api_key or not job_id:
        return {'description': None, 'company': None}
    try:
        response = req.get(
            'https://jobs-api14.p.rapidapi.com/v2/linkedin/get',
            headers={
                'x-rapidapi-host': 'jobs-api14.p.rapidapi.com',
                'x-rapidapi-key': api_key,
            },
            params={'id': str(job_id)},
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()
        if data.get('hasError'):
            log_event('linkedin_get_error', job_id=job_id, errors=data.get('errors'))
            return {'description': None, 'company': None}
        payload = data.get('data', {})
        description = payload.get('description', '') or ''
        # Company name field varies across API versions — try all known keys
        company = (
            payload.get('companyName') or
            payload.get('company') or
            payload.get('organizationName') or
            (payload.get('hiringOrganization') or {}).get('name') or
            ''
        )
        return {
            'description': strip_jd_boilerplate(description)[:JD_MAX_CHARS] if description else None,
            'company': clean_company(company) if company else None,
        }
    except Exception as e:
        log_event('linkedin_get_error', job_id=job_id, error=str(e))
        return {'description': None, 'company': None}

# Regex to extract numeric LinkedIn job ID from job URLs
# Matches: linkedin.com/jobs/view/1234567890 and linkedin.com/comm/jobs/view/1234567890
_LINKEDIN_JOB_ID_RE = re.compile(r'linkedin\.com/(?:comm/)?jobs/view/(\d+)', re.IGNORECASE)

def extract_linkedin_job_id(url):
    """Extract numeric job ID from a LinkedIn job URL. Returns str or None."""
    m = _LINKEDIN_JOB_ID_RE.search(url or '')
    return m.group(1) if m else None

def fetch_jd(job):
    """
    Fetch JD text for a job dict. Strategy by source:
      - jobsapi_indeed:   inline description already in job dict from search response
      - jobsapi_linkedin: call /v2/linkedin/get using stored api_id
      - gmail_linkedin:   call /v2/linkedin/get using api_id extracted from URL
                          (company enrichment handled separately in main)
      - everything else:  curl the URL (Greenhouse, Lever, other Gmail sources)
    """
    source = job.get('source', '')

    if source == 'jobsapi_indeed':
        desc = job.get('description', '')
        if desc and len(desc.strip()) > 30:
            return strip_jd_boilerplate(desc)[:JD_MAX_CHARS]
        # No inline description — do NOT curl; Indeed apply URLs are JS-rendered SPAs
        # that always return unusable content. Return sentinel instead.
        return '[No description available]'

    if source == 'greenhouse_json':
        desc = job.get('description', '')
        if desc and len(desc.strip()) > 30:
            try:
                plain = subprocess.run(
                    [PANDOC, '-f', 'html', '-t', 'plain'],
                    input=desc, capture_output=True, text=True, timeout=10
                ).stdout
                plain = strip_jd_boilerplate(plain)[:JD_MAX_CHARS]
                return plain if plain.strip() else '[No description available]'
            except Exception:
                return strip_jd_boilerplate(desc)[:JD_MAX_CHARS]
        return '[No description available]'

    if source in ('jobsapi_linkedin', 'gmail_linkedin'):
        api_id = job.get('api_id', '')
        if api_id:
            result = fetch_linkedin_job_data(api_id)
            # Cache resolved company in job dict so the main loop can use it
            # without a second API call (only relevant for gmail_linkedin blank-company case).
            if source == 'gmail_linkedin' and result.get('company'):
                job['_linkedin_company'] = result['company']
            if result['description']:
                return result['description']
        log_event('linkedin_jd_missing', title=job.get('title'), api_id=api_id)
        return '[LinkedIn JD unavailable — no api_id or get request failed]'

    url = job.get('url', '')
    if url:
        return fetch_jd_curl(url)

    return '[No URL available]'

# ── Contact Lookup ──
def find_contacts(company):
    contacts = []
    if not company or not company.strip():
        return contacts
    try:
        with open(CONNECTIONS) as f:
            for row in csv.DictReader(f):
                contact_co = row.get('Company', '').strip()
                if not contact_co:
                    continue  # guard: '' in 'anything' is True in Python
                if company.lower() in contact_co.lower():
                    contacts.append(f"{row['First Name']} {row['Last Name']} ({row['Position']})")
    except Exception:
        pass
    return contacts

# ── Scoring ──

def _build_feedback_block():
    """Query feedback_log and return a compact rejection-history block for the scorer prompt.
    Returns empty string if no feedback exists."""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        rows = conn.execute('''
            SELECT reject_reason, title, relevance_score
            FROM feedback_log
            WHERE reject_reason NOT IN ('Stale/Closed', 'Already Applied', 'Other')
            ORDER BY reject_reason, title
        ''').fetchall()
        conn.close()
    except Exception:
        return ''

    if not rows:
        return ''

    # Cluster by reject_reason
    clusters = {}
    for r in rows:
        reason = r['reject_reason']
        clusters.setdefault(reason, []).append(r['title'])

    lines = ['', '---', '',
             'USER REJECTION HISTORY (from manual feedback — consider when scoring similar jobs):']
    for reason, titles in sorted(clusters.items(), key=lambda x: -len(x[1])):
        # Dedupe and truncate title list
        unique = list(dict.fromkeys(titles))
        sample = ', '.join(t[:40] for t in unique[:6])
        if len(unique) > 6:
            sample += f', ... (+{len(unique)-6} more)'
        lines.append(f'- {len(unique)}x "{reason}": {sample}')

    lines.append('If this job closely matches rejected patterns above, reduce your score by 2-3 points. '
                 'The user has explicitly rejected similar jobs. Minimum score is always 1.')
    return '\n'.join(lines)

# Cache feedback block at module load — rebuilt each triage run
_FEEDBACK_BLOCK = _build_feedback_block()


def score_job(title, company, location, jd_text, candidate_profile=''):
    usable = jd_is_usable(jd_text)

    # Stage 1 & 2: deterministic pre-filter — no LLM call
    pre, reason = prefilter_score(title, company, usable)
    if pre is not None:
        log_event('score_prefilter', title=title, company=company, reason=reason,
                  score=pre.get('relevance_score'))
        return pre, 0

    # Stage 3: LLM scoring
    effective_jd = jd_text if usable else '[Job description unavailable — score from title and company only]'
    prompt = f"""CANDIDATE PROFILE:
{candidate_profile}
{_FEEDBACK_BLOCK}

---

Evaluate this job posting for the candidate described above.
Job: {title} at {company}
Location: {location}
JD:
{effective_jd[:6000]}"""

    start = time.time()
    try:
        result = subprocess.run(
            [AICHAT, '--role', 'job_scorer', '-S', prompt],
            capture_output=True, text=True, timeout=60
        )
    except subprocess.TimeoutExpired:
        latency_ms = int((time.time() - start) * 1000)
        log_event('score_error', reason='timeout', title=title, company=company,
                  latency_ms=latency_ms)
        return {
            'score_status': 'manual_review',
            'score_flag_reason': 'Scorer timeout',
            'relevance_score': None,
            'interview_likelihood': None,
            'strengths_alignment': None,
            'industry_sector': '',
            'comp_estimate': '',
            'ai_notes': 'Scorer timed out after 60s',
            'remote_status': 'Unknown',
        }, latency_ms
    latency_ms = int((time.time() - start) * 1000)

    if result.returncode != 0 or not result.stdout.strip():
        log_event('score_error', reason='subprocess_failed', returncode=result.returncode,
                  stderr=result.stderr.strip()[:200], title=title, company=company)
        return {
            'score_status': 'manual_review',
            'score_flag_reason': f'Scorer failed (rc={result.returncode})',
            'relevance_score': None,
            'interview_likelihood': None,
            'strengths_alignment': None,
            'industry_sector': '',
            'comp_estimate': '',
            'ai_notes': 'Scorer subprocess failed or returned empty output',
            'remote_status': 'Unknown',
        }, latency_ms

    parsed, error = validate_llm_json(result.stdout, SCHEMA_PATH)

    if error:
        log_event('score_validation_failed', error=error, title=title, company=company)
        # Stage 1.5: if LLM failed AND title matches a hard reject pattern, auto-reject
        # instead of cluttering the manual_review queue with obvious mismatches
        from scorer_prefilter import _hard_reject_match
        if _hard_reject_match(title):
            return {
                'score_status': 'scored',
                'score_flag_reason': f'Validation: {error}',
                'relevance_score': 1,
                'interview_likelihood': 1,
                'strengths_alignment': 'LLM failed + title is outside candidate domain.',
                'industry_sector': '',
                'comp_estimate': '',
                'ai_notes': f'LLM validation failed; hard-reject title pattern matched',
                'remote_status': 'Unknown',
            }, latency_ms
        return {
            'score_status': 'manual_review',
            'score_flag_reason': f'Validation: {error}',
            'relevance_score': None,
            'interview_likelihood': None,
            'strengths_alignment': None,
            'industry_sector': '',
            'comp_estimate': '',
            'ai_notes': 'Scorer output failed validation',
            'remote_status': 'Unknown',
        }, latency_ms

    if parsed.get('relevance_score') is None:
        log_event('score_error', reason='null_score', title=title, company=company)

    return parsed, latency_ms

# ── Job Source Fetching ──
def fetch_greenhouse_jobs(feed_urls_path):
    """
    Fetch jobs via Greenhouse public JSON API.
    Replaces fetch_rss_jobs() — Greenhouse deprecated all RSS feeds.
    Parses slugs from existing greenhouse URL entries in feed_urls.txt.
    JD content is included inline; pandoc conversion deferred to fetch_jd()
    so it only runs for jobs that pass dedup (not all jobs fetched).
    """
    import requests as req

    jobs = []
    try:
        with open(feed_urls_path) as f:
            urls = [line.strip() for line in f if line.strip() and not line.startswith('#')]
    except FileNotFoundError:
        return jobs

    slug_re = re.compile(r'boards(?:\.eu)?\.greenhouse\.io/([^/]+)/')
    seen_slugs = set()
    slugs = []
    for url in urls:
        m = slug_re.search(url)
        if m:
            slug = m.group(1)
            is_eu = '.eu.' in url
            if slug not in seen_slugs:
                seen_slugs.add(slug)
                slugs.append((slug, is_eu))

    for slug, is_eu in slugs:
        # Greenhouse API host is always boards-api.greenhouse.io regardless of
        # board subdomain (boards.eu.greenhouse.io is the web board only).
        api_url = f'https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true'
        try:
            resp = req.get(api_url, timeout=15)
            if resp.status_code != 200:
                log_event('greenhouse_fetch_skip', slug=slug, status=resp.status_code)
                continue
            gh_jobs = resp.json().get('jobs', [])
            for j in gh_jobs:
                jobs.append({
                    'title': j.get('title', ''),
                    'company': clean_company(j.get('company_name', '') or slug),
                    'url': j.get('absolute_url', ''),
                    'location': (j.get('location') or {}).get('name', ''),
                    'source': 'greenhouse_json',
                    'description': html.unescape(j.get('content', '') or ''),
                })
            log_event('greenhouse_fetch', slug=slug, count=len(gh_jobs))
        except Exception as e:
            log_event('greenhouse_fetch_error', slug=slug, error=str(e))
        time.sleep(0.3)

    return jobs

def fetch_jobsapi_jobs(queries_path):
    """
    Fetch jobs via Jobs API (jobs-api14, RapidAPI).
    LinkedIn: stores api_id for /v2/linkedin/get JD fetch.
    Indeed: stores inline description from search response.
    """
    import requests as req

    api_key = os.environ.get('RAPIDAPI_KEY', '')
    if not api_key:
        log_event('jobsapi_error', error='RAPIDAPI_KEY not set in .env')
        return []

    try:
        with open(queries_path) as f:
            queries = [line.strip() for line in f if line.strip() and not line.startswith('#')]
    except FileNotFoundError:
        log_event('jobsapi_error', error=f'queries file not found: {queries_path}')
        return []

    headers = {
        'x-rapidapi-host': 'jobs-api14.p.rapidapi.com',
        'x-rapidapi-key': api_key,
        'Content-Type': 'application/json',
    }

    sources = [
        {
            'name': 'linkedin',
            'url': 'https://jobs-api14.p.rapidapi.com/v2/linkedin/search',
            'params': lambda q: {
                'query': q,
                'location': 'United States',
                'datePosted': 'day',
                'employmentTypes': 'fulltime',
                'experienceLevels': 'midSenior;director',
            },
            'url_field': 'linkedinUrl',
        },
        {
            'name': 'indeed',
            'url': 'https://jobs-api14.p.rapidapi.com/v2/indeed/search',
            'params': lambda q: {
                'query': q,
                'countryCode': 'us',
                'sortType': 'date',
            },
            'url_field': 'applyUrl',
        },
    ]

    jobs = []
    for query in queries:
        for source in sources:
            try:
                response = req.get(
                    source['url'],
                    headers=headers,
                    params=source['params'](query),
                    timeout=30,
                )
                response.raise_for_status()
                data = response.json()

                if data.get('hasError'):
                    log_event('jobsapi_error', source=source['name'], query=query,
                              errors=data.get('errors'))
                    continue

                count = 0
                for job in data.get('data', []):
                    raw_title = job.get('title', '')
                    title = clean_title(raw_title)
                    url = job.get(source['url_field'], '') or job.get('linkedinUrl', '')
                    company = clean_company(job.get('companyName', '') or job.get('company', {}).get('name', ''))
                    loc = job.get('location', '')
                    location = loc.get('location', '') if isinstance(loc, dict) else loc

                    if not title or not url:
                        continue

                    job_dict = {
                        'title': title,
                        'company': company,
                        'url': url,
                        'location': location,
                        'source': f"jobsapi_{source['name']}",
                    }

                    if source['name'] == 'linkedin':
                        job_dict['api_id'] = str(job.get('id', ''))
                    elif source['name'] == 'indeed':
                        job_dict['description'] = job.get('description', '')

                    jobs.append(job_dict)
                    count += 1

                log_event('jobsapi_fetched', source=source['name'], query=query, count=count)
                time.sleep(0.6)

            except Exception as e:
                log_event('jobsapi_error', source=source['name'], query=query, error=str(e))

    return jobs

# ── Gmail Ingestion ──
def get_gmail_service():
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    creds = None
    if os.path.exists(GMAIL_TOKEN):
        creds = Credentials.from_authorized_user_file(GMAIL_TOKEN, GMAIL_SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(GMAIL_TOKEN, 'w') as f:
                f.write(creds.to_json())
        else:
            if not sys.stdin.isatty():
                log_event('gmail_auth_skipped',
                          reason='No token and no TTY — run triage.py manually once to authorize')
                return None
            flow = InstalledAppFlow.from_client_secrets_file(GMAIL_CREDS, GMAIL_SCOPES)
            creds = flow.run_local_server(port=0)
            with open(GMAIL_TOKEN, 'w') as f:
                f.write(creds.to_json())

    return build('gmail', 'v1', credentials=creds)


def parse_jobs_from_email(msg):
    import base64
    from bs4 import BeautifulSoup

    html = ''

    def extract_parts(part):
        nonlocal html
        mime = part.get('mimeType', '')
        if mime == 'text/html':
            data = part.get('body', {}).get('data', '')
            if data:
                padded = data + '=' * (4 - len(data) % 4)
                html += base64.urlsafe_b64decode(padded).decode('utf-8', errors='ignore')
        for subpart in part.get('parts', []):
            extract_parts(subpart)

    extract_parts(msg.get('payload', {}))
    if not html:
        return []

    soup = BeautifulSoup(html, 'html.parser')
    jobs = []
    seen_urls = set()

    SKIP_LABELS = {
        'view job', 'apply', 'apply now', 'see job', 'learn more', 'view',
        'click here', 'unsubscribe', 'manage alerts', 'view all jobs',
        'see all jobs', 'update preferences', 'privacy policy', 'terms',
        'help', 'contact us', 'settings', 'opt out', 'manage email',
        'see more jobs', 'view more jobs', 'all jobs',
    }

    JOB_URL_PATTERNS = [
        ('linkedin.com/jobs',          'gmail_linkedin'),
        ('linkedin.com/comm/jobs',     'gmail_linkedin'),
        ('lnkd.in/',                   'gmail_linkedin'),
        ('indeed.com/viewjob',         'gmail_indeed'),
        ('indeed.com/rc/clk',          'gmail_indeed'),
        ('indeed.com/pagead',          'gmail_indeed'),
        ('r.indeed.com',               'gmail_indeed'),
        ('ziprecruiter.com/jobs',      'gmail_ziprecruiter'),
        ('ziprecruiter.com/c/',        'gmail_ziprecruiter'),
        ('careers.google.com',         'gmail_google'),
        ('google.com/about/careers',   'gmail_google'),
    ]

    for a in soup.find_all('a', href=True):
        href = a['href']
        # LinkedIn/Indeed emails often pack "Title\nCompany" in one <a> tag.
        # Split on newline first so company doesn't get concatenated into title.
        raw_text = a.get_text(separator='\n', strip=True)
        text_lines = [l.strip() for l in raw_text.split('\n') if l.strip()]
        title = clean_title(text_lines[0]) if text_lines else ''
        anchor_company = text_lines[1] if len(text_lines) > 1 else ''  # may be overridden below

        if not title or len(title) < 6 or title.lower() in SKIP_LABELS:
            continue
        # Skip LinkedIn digest subject lines misread as job titles
        title_lower = title.lower()
        if (title_lower.startswith('jobs similar to') or
                title_lower.startswith('jobs at ') or
                title_lower.startswith('jobs in ')):
            continue
        if href in seen_urls:
            continue
        if len(title) > 140:
            continue

        source = None
        for pattern, src in JOB_URL_PATTERNS:
            if pattern in href:
                source = src
                break

        if not source:
            continue

        company = ''
        parent = a.find_parent()
        if parent:
            for sib in parent.find_next_siblings(limit=4):
                txt = sib.get_text(strip=True)
                if txt and 6 < len(txt) < 120 and txt.lower() not in SKIP_LABELS:
                    company = txt
                    break
            if not company:
                full_text = parent.get_text(separator=' ', strip=True)
                parts = full_text.split(title, 1)
                if len(parts) > 1:
                    candidate = parts[1].strip().split('\n')[0][:100].strip()
                    if candidate and candidate.lower() not in SKIP_LABELS:
                        company = candidate
        # Last resort: use the second line of anchor text (stripped of skip labels)
        if not company and anchor_company and anchor_company.lower() not in SKIP_LABELS:
            company = anchor_company

        company = clean_company(company)
        job_dict = {'title': title, 'company': company, 'url': href,
                    'location': '', 'source': source}
        # For LinkedIn URLs, extract job ID so fetch_jd can use the API path
        if source == 'gmail_linkedin':
            api_id = extract_linkedin_job_id(href)
            if api_id:
                job_dict['api_id'] = api_id
        jobs.append(job_dict)
        seen_urls.add(href)

    return jobs


def fetch_gmail_jobs():
    if not os.path.exists(GMAIL_CREDS):
        log_event('gmail_skipped', reason='gmail_oauth_client.json not found')
        return []

    try:
        service = get_gmail_service()
        if service is None:
            return []
    except Exception as e:
        log_event('gmail_error', stage='auth', error=str(e))
        return []

    query = (
        '(from:jobalerts-noreply@linkedin.com OR from:jobs-noreply@linkedin.com '
        'OR from:indeedjobs@indeed.com OR from:alert@indeed.com '
        'OR from:careers-noreply@google.com OR from:alerts@ziprecruiter.com '
        'OR from:noreply@ziprecruiter.com) newer_than:30d'
    )

    jobs = []
    try:
        results = service.users().messages().list(
            userId='me', q=query, maxResults=50
        ).execute()
        messages = results.get('messages', [])
        log_event('gmail_messages_found', count=len(messages))

        for msg_ref in messages:
            try:
                msg = service.users().messages().get(
                    userId='me', id=msg_ref['id'], format='full'
                ).execute()
                extracted = parse_jobs_from_email(msg)
                jobs.extend(extracted)
            except Exception as e:
                log_event('gmail_parse_error', msg_id=msg_ref['id'], error=str(e))

    except Exception as e:
        log_event('gmail_error', stage='fetch', error=str(e))

    log_event('gmail_fetched', count=len(jobs))
    return jobs

# ── Main Pipeline ──
def main():
    log_event('pipeline_started')

    if os.path.exists(DB_PATH):
        shutil.copy2(DB_PATH, f'{DB_PATH}.bak')

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL')

    with open(PROFILE_PATH) as f:
        candidate_profile = f.read()

    greenhouse_jobs = fetch_greenhouse_jobs(f'{BASE}/config/feed_urls.txt')
    api_jobs = fetch_jobsapi_jobs(f'{BASE}/config/jsearch_queries.txt')
    gmail_jobs = fetch_gmail_jobs()
    raw_jobs = greenhouse_jobs + api_jobs + gmail_jobs
    log_event('jobs_fetched', count=len(raw_jobs),
              greenhouse=len(greenhouse_jobs), api=len(api_jobs), gmail=len(gmail_jobs))

    if not raw_jobs:
        log_event('pipeline_complete', new=0, dupes=0, scored=0)
        conn.close()
        return

    new_count = 0
    dupe_count = 0
    scored_count = 0
    noise_count = 0

    for job in raw_jobs:
        if not job.get('title') or not job.get('url'):
            continue

        # ── Ingest noise filters ──
        # 1. LinkedIn "Jobs similar to" recommendations-carousel items.
        #    These aren't real jobs — the API returned a UI element.
        if is_ingest_noise_title(job.get('title', '')):
            log_event('ingest_skipped', reason='jobs_similar_to',
                      title=job.get('title', '')[:80], company=job.get('company', '')[:80])
            noise_count += 1
            continue
        # 2. Aggregator / recruiter wrappers (Jobs via Dice, Robert Half, etc.).
        #    The "company" is the board, not the actual employer — unactionable.
        if is_aggregator_company(job.get('company', '')):
            log_event('ingest_skipped', reason='aggregator_company',
                      title=job.get('title', '')[:80], company=job.get('company', '')[:80])
            noise_count += 1
            continue

        fp = fingerprint(job['title'], job.get('company', ''), job.get('location', ''))

        existing = conn.execute(
            'SELECT id FROM jobs WHERE fingerprint = ?', (fp,)
        ).fetchone()

        if existing:
            conn.execute(
                'INSERT OR IGNORE INTO duplicate_groups (canonical_fingerprint, duplicate_job_id) VALUES (?, ?)',
                (fp, job.get('url', ''))
            )
            dupe_count += 1
            continue

        job_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        conn.execute('''
            INSERT INTO jobs (id, fingerprint, url, title, company, location, source, stage, stage_updated, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'discovered', ?, ?)
        ''', (job_id, fp, job['url'], job['title'], job.get('company', ''),
              job.get('location', ''), job.get('source', 'rss'), now, now))
        conn.commit()
        write_audit(conn, job_id, 'stage', None, 'discovered')
        new_count += 1

        jd_text = fetch_jd(job)

        # For gmail_linkedin jobs: if company was blank after HTML heuristics,
        # fetch_jd already called the LinkedIn API and cached the company — reuse it.
        if job.get('source') == 'gmail_linkedin' and not job.get('company'):
            resolved = job.get('_linkedin_company')
            if resolved:
                job['company'] = resolved
                # Recompute fingerprint with resolved company and check for dupes
                new_fp = fingerprint(job['title'], job['company'], job.get('location', ''))
                existing_resolved = conn.execute(
                    'SELECT id FROM jobs WHERE fingerprint = ? AND id != ?', (new_fp, job_id)
                ).fetchone()
                if existing_resolved:
                    # A copy with the resolved company already exists — mark this one as dupe
                    conn.execute(
                        'UPDATE jobs SET dupe_of=?, stage=?, stage_updated=?, updated_at=? WHERE id=?',
                        (existing_resolved['id'], 'rejected', now, now, job_id))
                    conn.commit()
                    write_audit(conn, job_id, 'stage', 'discovered', 'rejected')
                    log_event('dupe_after_enrichment', job_id=job_id, title=job['title'],
                              company=job['company'], dupe_of=existing_resolved['id'])
                    dupe_count += 1
                    continue
                # No dupe — update company and fingerprint on the inserted row
                conn.execute('UPDATE jobs SET company=?, fingerprint=? WHERE id=?',
                             (job['company'], new_fp, job_id))
                conn.commit()
            else:
                # Company unresolvable — reject immediately, don't waste a scorer call
                conn.execute('''
                    UPDATE jobs SET stage='rejected', stage_updated=?, status='rejected',
                           reject_reason='Blank Company', updated_at=?
                    WHERE id=?
                ''', (now, now, job_id))
                conn.commit()
                write_audit(conn, job_id, 'stage', 'discovered', 'rejected')
                log_event('blank_company_rejected', job_id=job_id, title=job['title'],
                          source='gmail_linkedin')
                continue

        contacts = find_contacts(job.get('company', ''))
        network_depth = min(len(contacts), 2)
        known_contacts = ', '.join(contacts[:3])

        conn.execute('''
            UPDATE jobs SET raw_jd_text=?, network_depth=?, known_contacts=?,
                   stage='enriched', stage_updated=?, updated_at=?
            WHERE id=?
        ''', (jd_text, network_depth, known_contacts, now, now, job_id))
        conn.commit()
        write_audit(conn, job_id, 'stage', 'discovered', 'enriched')

        scored, latency_ms = score_job(
            job['title'], job.get('company', ''), job.get('location', ''), jd_text, candidate_profile
        )

        stage = 'manual_review' if scored.get('score_status') == 'manual_review' else 'scored'
        status = 'manual_review' if stage == 'manual_review' else 'active'

        conn.execute('''
            UPDATE jobs SET
                relevance_score=?, interview_likelihood=?, strengths_alignment=?,
                industry_sector=?, comp_estimate=?, ai_notes=?,
                score_status=?, score_flag_reason=?, remote_status=?,
                stage=?, stage_updated=?, status=?, updated_at=?
            WHERE id=?
        ''', (
            scored.get('relevance_score'), scored.get('interview_likelihood'),
            scored.get('strengths_alignment'), scored.get('industry_sector', ''),
            scored.get('comp_estimate', ''), scored.get('ai_notes', ''),
            scored.get('score_status', 'manual_review'),
            scored.get('score_flag_reason', ''),
            scored.get('remote_status', 'Unknown'),
            stage, now, status, now, job_id
        ))
        conn.commit()
        write_audit(conn, job_id, 'stage', 'enriched', stage)
        scored_count += 1

        conn.execute('''
            INSERT INTO cost_log (job_id, operation, model, latency_ms, success)
            VALUES (?, 'score', ?, ?, 1)
        ''', (job_id, SCORER_MODEL, latency_ms))
        conn.commit()

        log_event('job_processed', job_id=job_id, title=job['title'],
                  company=job.get('company', ''), stage=stage,
                  score=scored.get('relevance_score'))

        time.sleep(0.5)

    # ── Orphan recovery: rescue any rows stuck in 'enriched' stage ──
    # If a prior run crashed mid-scoring (SIGTERM from systemd timeout, etc.),
    # jobs that were enriched but not yet scored get stranded. Pick them up
    # here on the next run so they don't sit in DB limbo forever.
    orphan_scored = 0
    orphans = conn.execute('''
        SELECT id, title, company, location, raw_jd_text FROM jobs
        WHERE stage = 'enriched'
          AND (dupe_of = '' OR dupe_of IS NULL)
    ''').fetchall()
    if orphans:
        log_event('orphan_recovery_started', count=len(orphans))
        for row in orphans:
            try:
                scored, latency_ms = score_job(
                    row['title'], row['company'] or '', row['location'] or '',
                    row['raw_jd_text'] or '', candidate_profile,
                )
                now = datetime.now(timezone.utc).isoformat()
                new_stage = 'manual_review' if scored.get('score_status') == 'manual_review' else 'scored'
                conn.execute('''
                    UPDATE jobs SET
                        relevance_score=?, interview_likelihood=?, strengths_alignment=?,
                        industry_sector=?, comp_estimate=?, ai_notes=?,
                        score_status=?, score_flag_reason=?, remote_status=?,
                        stage=?, stage_updated=?, updated_at=?
                    WHERE id=?
                ''', (
                    scored.get('relevance_score'), scored.get('interview_likelihood'),
                    scored.get('strengths_alignment'), scored.get('industry_sector', ''),
                    scored.get('comp_estimate', ''), scored.get('ai_notes', ''),
                    scored.get('score_status', 'manual_review'),
                    scored.get('score_flag_reason', ''),
                    scored.get('remote_status', 'Unknown'),
                    new_stage, now, now, row['id']
                ))
                conn.commit()
                orphan_scored += 1
            except Exception as e:
                log_event('orphan_recovery_error', job_id=row['id'], error=str(e))
        log_event('orphan_recovery_complete', total=len(orphans), scored=orphan_scored)

    conn.close()
    log_event('pipeline_complete', new=new_count, dupes=dupe_count,
              scored=scored_count, noise_skipped=noise_count,
              orphans_recovered=orphan_scored)

    subprocess.run([sys.executable, f'{BASE}/scripts/sync_sheet.py'], check=False)
    notify(f"Triage done: {new_count} new, {dupe_count} dupes, {scored_count} scored")

def notify(message):
    topic = None
    try:
        with open(f'{BASE}/config/ntfy_topic.txt') as f:
            topic = f.read().strip()
    except FileNotFoundError:
        pass
    if not topic:
        # Fall back to data/.env NTFY_TOPIC
        try:
            with open(f'{BASE}/data/.env') as f:
                for line in f:
                    line = line.strip()
                    if line.startswith('NTFY_TOPIC') and '=' in line:
                        topic = line.split('=', 1)[1].strip().strip("'\"")
                        break
        except Exception:
            pass
    if not topic:
        return
    try:
        subprocess.run(['curl', '-s', '-d', message, f'https://ntfy.sh/{topic}'],
                       capture_output=True, timeout=10)
    except Exception:
        pass

if __name__ == '__main__':
    main()
