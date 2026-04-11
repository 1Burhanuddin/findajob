#!/usr/bin/env python3
"""Shared utilities for the JobSearchPipeline."""
import os, json, re
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


# ── JD boilerplate stripping ───────────────────────────────────────────────

JD_MAX_CHARS = 16000

_BOILERPLATE_PATTERNS = [
    # EEO
    r'equal\s+opportunity\s+employer',
    r'equal\s+employment\s+opportunity',
    r'we\s+do\s+not\s+discriminate',
    r'without\s+regard\s+to\s+race',
    r'affirmative\s+action',
    r'all\s+qualified\s+applicants\s+will\s+receive\s+consideration',
    # Legal / compliance
    r'reasonable\s+accommodation',
    r'e-verify',
    r'employment\s+eligibility\s+verification',
    r'right\s+to\s+work',
    r'protected\s+veteran',
    r'drug[- ]free\s+workplace',
    # Disclaimers
    r'this\s+(?:job\s+)?posting\s+is\s+not',
    r'salary\s+ranges?\s+may\s+vary',
    r'the\s+above\s+is\s+intended\s+to\s+describe',
    r'nothing\s+in\s+this\s+job\s+(?:posting|description)',
    r'this\s+(?:job\s+)?description\s+(?:is\s+not|does\s+not)',
    # Application boilerplate
    r'how\s+to\s+apply',
    r'to\s+apply,?\s+please',
    r'apply\s+now\s+at',
    # Benefits headers (start-of-paragraph)
    r'^benefits\s*:',
    r'^what\s+we\s+offer\s*:',
    r'^our\s+benefits\s+include',
    r'^perks\s+(?:&|and)\s+benefits',
    r'^total\s+rewards',
    r'^compensation\s+(?:&|and)\s+benefits',
]

_BOILERPLATE_RE = re.compile('|'.join(_BOILERPLATE_PATTERNS), re.IGNORECASE | re.MULTILINE)


def strip_jd_boilerplate(text):
    """Remove trailing EEO/legal/benefits boilerplate from JD text.

    Works backwards from the end, paragraph by paragraph. Stops trimming
    when a paragraph doesn't match any boilerplate pattern. Never removes
    more than 40% of the text or drops below 200 chars retained.
    """
    if not text or len(text) < 200:
        return text or ''

    # Split into paragraphs on double-newline or blank lines
    paragraphs = re.split(r'\n\s*\n', text)
    if len(paragraphs) <= 1:
        return text  # single block — don't risk stripping it

    original_len = len(text)
    min_retain = max(200, int(original_len * 0.6))  # never strip more than 40%

    # Walk backwards, marking trailing boilerplate paragraphs for removal
    trim_from = len(paragraphs)  # index to trim from (exclusive of kept content)
    for i in range(len(paragraphs) - 1, 0, -1):  # never trim paragraph 0
        para = paragraphs[i].strip()
        if not para:
            continue  # skip empty paragraphs
        if _BOILERPLATE_RE.search(para):
            trim_from = i
        else:
            break  # hit real content — stop trimming

    if trim_from >= len(paragraphs):
        return text  # nothing to trim

    kept = '\n\n'.join(paragraphs[:trim_from]).rstrip()

    if len(kept) < min_retain:
        return text  # safety: would remove too much

    chars_removed = original_len - len(kept)
    if chars_removed > 0 and chars_removed / original_len > 0.30:
        log_event('jd_boilerplate_warning', removed_pct=round(chars_removed / original_len * 100, 1),
                  original_len=original_len, kept_len=len(kept))

    return kept
