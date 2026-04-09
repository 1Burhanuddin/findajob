#!/usr/bin/env python3
# ~/JobSearchPipeline/scripts/rescore_all.py
"""
Re-score all jobs in the DB that have JD text.
Useful after switching scorer model or updating the job_scorer role prompt.
Run manually — not a launchd agent.
"""
import os, sys, json, subprocess, time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from paths import BASE, AICHAT
from scorer_prefilter import prefilter_score

DB_PATH = f'{BASE}/data/pipeline.db'
LOG_PATH = f'{BASE}/logs/pipeline.jsonl'
SCHEMA_PATH = f'{BASE}/config/scoring_schema.json'
PROFILE_PATH = f'{BASE}/config/profile.md'

def load_env(path):
    with open(os.path.expanduser(path)) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, val = line.split('=', 1)
                os.environ[key.strip()] = val.strip().strip("'\"")

load_env(f'{BASE}/data/.env')

import sqlite3

def log_event(event_type, **kwargs):
    entry = {'ts': datetime.now(timezone.utc).isoformat(), 'event': event_type, **kwargs}
    with open(LOG_PATH, 'a') as f:
        f.write(json.dumps(entry) + '\n')

def write_audit(conn, job_id, field_changed, old_value, new_value):
    conn.execute(
        'INSERT INTO audit_log (job_id, field_changed, old_value, new_value) VALUES (?, ?, ?, ?)',
        (job_id, field_changed, str(old_value) if old_value is not None else None, str(new_value))
    )
    conn.commit()

def validate_llm_json(raw_output, schema_path):
    import jsonschema
    text = raw_output.strip()
    if text.startswith('```'):
        text = '\n'.join(text.split('\n')[1:])
    if text.endswith('```'):
        text = text[:text.rfind('```')]
    text = text.strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as e:
        return None, f"JSON parse: {e}"
    try:
        with open(schema_path) as f:
            schema = json.load(f)
        jsonschema.validate(parsed, schema)
    except jsonschema.ValidationError as e:
        return None, f"Schema: {e.message}"
    return parsed, None

_JD_WALL_SIGNALS = [
    'you need to enable javascript',
    'enable javascript to run this app',
    '403 forbidden',
    'cross-site request forgeries',
    'we\'re signing you in',
    'sign in to',
    'access denied',
    'job not found',
    'this job may have been',
    'our careers site has moved',
]

def jd_is_usable(jd_text):
    if not jd_text or len(jd_text.strip()) < 30:
        return False
    lower = jd_text.lower()
    return not any(s in lower for s in _JD_WALL_SIGNALS)

def score_job(title, company, location, jd_text, candidate_profile=''):
    usable = jd_is_usable(jd_text)

    # Stage 1 & 2: deterministic pre-filter — no LLM call
    pre, reason = prefilter_score(title, company, usable)
    if pre is not None:
        log_event('rescore_prefilter', title=title, company=company, reason=reason,
                  score=pre.get('relevance_score'))
        return pre, 0

    # Stage 3: LLM scoring
    effective_jd = jd_text if usable else '[Job description unavailable — score from title and company only]'
    prompt = f"""CANDIDATE PROFILE:
{candidate_profile}

---

Evaluate this job posting for the candidate described above.
Job: {title} at {company}
Location: {location}
JD:
{effective_jd[:6000]}"""

    start = time.time()
    result = subprocess.run(
        [AICHAT, '--role', 'job_scorer', '-S', prompt],
        capture_output=True, text=True, timeout=60
    )
    latency_ms = int((time.time() - start) * 1000)

    parsed, error = validate_llm_json(result.stdout, SCHEMA_PATH)
    if error:
        log_event('rescore_validation_failed', error=error, title=title, company=company)
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

    return parsed, latency_ms

def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL')

    # Fetch all jobs that have JD text — skip jobs with no JD (can't score)
    rows = conn.execute('''
        SELECT id, title, company, location, raw_jd_text, stage, score_status
        FROM jobs
        WHERE raw_jd_text IS NOT NULL AND raw_jd_text != ''
        ORDER BY created_at DESC
    ''').fetchall()

    # Load candidate profile for direct injection
    with open(PROFILE_PATH) as f:
        candidate_profile = f.read()

    total = len(rows)
    print(f"Jobs to rescore: {total}")
    log_event('rescore_started', total=total)

    scored_count = 0
    manual_count = 0
    error_count = 0
    prefilter_count = 0

    for i, row in enumerate(rows, 1):
        job_id = row['id']
        title = row['title']
        company = row['company'] or ''
        location = row['location'] or ''
        jd_text = row['raw_jd_text']
        old_stage = row['stage']

        print(f"[{i}/{total}] {title} @ {company}", flush=True)

        try:
            scored, latency_ms = score_job(title, company, location, jd_text, candidate_profile)
        except Exception as e:
            print(f"  ERROR: {e}")
            log_event('rescore_error', job_id=job_id, error=str(e))
            error_count += 1
            continue

        now = datetime.now(timezone.utc).isoformat()
        new_stage = 'manual_review' if scored.get('score_status') == 'manual_review' else 'scored'
        new_status = 'manual_review' if new_stage == 'manual_review' else 'active'

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
            new_stage, now, new_status, now, job_id
        ))
        conn.commit()

        if old_stage != new_stage:
            write_audit(conn, job_id, 'stage', old_stage, new_stage)

        conn.execute('''
            INSERT INTO cost_log (job_id, operation, model, latency_ms, success)
            VALUES (?, 'rescore', 'openrouter:deepseek/deepseek-v3.2', ?, 1)
        ''', (job_id, latency_ms))
        conn.commit()

        score = scored.get('relevance_score')
        prefiltered = latency_ms == 0
        if prefiltered:
            prefilter_count += 1
        print(f"  score={score} stage={new_stage} [{latency_ms}ms]{'  [prefilter]' if prefiltered else ''}", flush=True)

        if new_stage == 'manual_review':
            manual_count += 1
        else:
            scored_count += 1

        if not prefiltered:
            time.sleep(0.3)  # Rate limit only applies to LLM calls

    conn.close()

    print(f"\nDone. scored={scored_count} manual_review={manual_count} errors={error_count} prefiltered={prefilter_count}")
    log_event('rescore_complete', total=total, scored=scored_count,
              manual_review=manual_count, errors=error_count, prefiltered=prefilter_count)

    # Sync sheet
    print("Syncing to Sheet...")
    subprocess.run([sys.executable, f'{BASE}/scripts/sync_sheet.py'], check=False)
    print("Done.")

if __name__ == '__main__':
    main()
