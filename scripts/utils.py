#!/usr/bin/env python3
"""Shared utilities for the JobSearchPipeline."""
import os, json
from datetime import datetime, timezone

from paths import BASE

LOG_PATH = f'{BASE}/logs/pipeline.jsonl'

# ── Logging ──────────────────────────────────────────────────────────────────

def log_event(event_type, **kwargs):
    entry = {
        'ts': datetime.now(timezone.utc).isoformat(),
        'event': event_type,
        **kwargs
    }
    with open(LOG_PATH, 'a') as f:
        f.write(json.dumps(entry) + '\n')


# ── Audit log ────────────────────────────────────────────────────────────────

def write_audit(conn, job_id, field_changed, old_value, new_value):
    conn.execute(
        'INSERT INTO audit_log (job_id, field_changed, old_value, new_value) VALUES (?, ?, ?, ?)',
        (job_id, field_changed, str(old_value) if old_value is not None else None, str(new_value))
    )
    conn.commit()


# ── Environment loading ──────────────────────────────────────────────────────

def load_env(path=None):
    """Load key=value pairs from a .env file into os.environ. Returns dict."""
    if path is None:
        path = f'{BASE}/data/.env'
    env = {}
    try:
        with open(os.path.expanduser(path)) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, _, val = line.partition('=')
                    key = key.strip()
                    val = val.strip().strip("'\"")
                    os.environ[key] = val
                    env[key] = val
    except FileNotFoundError:
        pass
    return env


# ── LLM JSON validation ─────────────────────────────────────────────────────

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


# ── JD quality check ─────────────────────────────────────────────────────────

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
