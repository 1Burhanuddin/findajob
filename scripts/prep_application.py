#!/usr/bin/env python3
# ~/JobSearchPipeline/scripts/prep_application.py
# Args: company, title, url, job_id
"""Generate draft application materials for a flagged job."""
import os, sys, subprocess, json, sqlite3, time, re
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from paths import BASE, AICHAT, PANDOC, RCLONE
DB_PATH = f'{BASE}/data/pipeline.db'
LOG_PATH = f'{BASE}/logs/pipeline.jsonl'
PROFILE_PATH = f'{BASE}/config/profile.md'
MASTER_RESUME_PATH = f'{BASE}/rag_sources/master_resume.md'

# Load env
def load_env(path):
    with open(os.path.expanduser(path)) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, val = line.split('=', 1)
                os.environ[key.strip()] = val.strip().strip("'\"")
load_env(f'{BASE}/data/.env')

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

def aichat(role, prompt, model_override=None, timeout=300):
    """Call aichat-ng and return stdout. No RAG — all context injected directly."""
    cmd = [AICHAT, '--role', role]
    if model_override:
        cmd += ['-m', model_override]
    cmd += ['-S', prompt]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return result.stdout.strip()

def abbrev_title(title, max_words=3):
    """Return a folder-safe abbreviated title: first N significant words joined with underscores."""
    title = re.sub(r'\s*\(.*?\)', '', title)          # strip parentheticals
    title = re.sub(r'[^\w\s-]', '', title)             # remove punctuation
    words = [w for w in title.split() if w][:max_words]
    return '_'.join(words) if words else 'Job'


def notify(message):
    topic_path = f'{BASE}/config/ntfy_topic.txt'
    try:
        with open(topic_path) as f:
            topic = f.read().strip()
        subprocess.run(['curl', '-s', '-d', message, f'https://ntfy.sh/{topic}'],
                       capture_output=True, timeout=10)
    except Exception:
        pass

def main():
    company, title, url, job_id = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
    date = datetime.now().strftime('%Y-%m-%d')
    time_str = datetime.now().strftime('%H%M%S')
    outdir = f'{BASE}/companies/{company}_{abbrev_title(title)}_{date}_{time_str}'
    os.makedirs(outdir, exist_ok=True)

    log_event('prep_started', company=company, title=title, job_id=job_id)

    # ── Step 1: Load JD from DB (already fetched during triage) ──
    # Do NOT re-curl — LinkedIn and many other URLs require auth and will return garbage.
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute('SELECT raw_jd_text, stage FROM jobs WHERE id=?', (job_id,)).fetchone()
    jd_text = (row['raw_jd_text'] or '').strip() if row else ''

    if not jd_text or len(jd_text) < 50:
        # Fallback: try curling for Greenhouse/Lever/public URLs only
        try:
            raw = subprocess.run(['curl', '-sL', '--max-time', '15', url],
                                 capture_output=True, text=True).stdout
            jd_text = subprocess.run([PANDOC, '-f', 'html', '-t', 'plain'],
                                     input=raw, capture_output=True, text=True).stdout[:8000]
        except Exception:
            jd_text = '[ERROR: Could not fetch JD]'

    with open(f'{outdir}/job_description.txt', 'w') as f:
        f.write(jd_text)

    # ── Load profile and master resume — injected directly, never via RAG ──
    try:
        with open(PROFILE_PATH) as f:
            profile_text = f.read()
    except FileNotFoundError:
        profile_text = '[Profile not found]'
        log_event('prep_warning', msg='profile.md not found', job_id=job_id)

    try:
        with open(MASTER_RESUME_PATH) as f:
            master_text = f.read()
    except FileNotFoundError:
        master_text = '[Master resume not found]'
        log_event('prep_warning', msg='master_resume.md not found', job_id=job_id)

    # ── Step 2: Resume — two separate calls ──
    # Call 1: Generate tailored resume
    resume_prompt = (
        f"MASTER RESUME:\n{master_text}\n\n"
        f"CANDIDATE PROFILE:\n{profile_text}\n\n"
        f"Company: {company}\nTitle: {title}\n\n"
        f"JD:\n{jd_text}"
    )
    resume_md = aichat('resume_tailor', resume_prompt)
    with open(f'{outdir}/tailored_resume_DRAFT.md', 'w') as f:
        f.write(resume_md)

    subprocess.run([PANDOC, f'{outdir}/tailored_resume_DRAFT.md',
                    '--lua-filter', f'{BASE}/config/strip-bookmarks.lua',
                    '--reference-doc', f'{BASE}/config/reference.docx',
                    '-o', f'{outdir}/tailored_resume_DRAFT.docx'], check=False)

    # Call 2: Generate change log
    changes_prompt = (
        f"ORIGINAL MASTER RESUME:\n{master_text}\n\n"
        f"TAILORED RESUME:\n{resume_md}\n\n"
        f"TARGET JD:\n{jd_text[:2000]}"
    )
    changes_md = aichat('resume_change_reviewer', changes_prompt)
    with open(f'{outdir}/tailored_resume_CHANGES.md', 'w') as f:
        f.write(changes_md)

    # ── Step 3: Cover letter — profile and master injected directly, no RAG ──
    cover_prompt = (
        f"CANDIDATE PROFILE:\n{profile_text}\n\n"
        f"MASTER RESUME:\n{master_text}\n\n"
        f"Company: {company}\nTitle: {title}\n\n"
        f"JD:\n{jd_text}"
    )
    cover_md = aichat('cover_letter_writer', cover_prompt)
    with open(f'{outdir}/cover_letter_DRAFT.md', 'w') as f:
        f.write(cover_md)
    subprocess.run([PANDOC, f'{outdir}/cover_letter_DRAFT.md',
                    '--lua-filter', f'{BASE}/config/strip-bookmarks.lua',
                    '--reference-doc', f'{BASE}/config/reference.docx',
                    '-o', f'{outdir}/cover_letter_DRAFT.docx'], check=False)

    # ── Step 4: Company briefing — researcher then briefing_writer ──
    brief_prompt = (
        f"Research {company} thoroughly.\n"
        f"Job title: {title}\n"
        f"JD excerpt:\n{jd_text[:2000]}"
    )
    raw_briefing = aichat('company_researcher', brief_prompt,
                          model_override='perplexity:sonar-pro')

    # Pass raw research through briefing_writer to format as structured 1-pager
    formatted_brief_prompt = (
        f"Format the following company research into a structured briefing 1-pager "
        f"for {company}. Job: {title}.\n\n"
        f"RAW RESEARCH:\n{raw_briefing}"
    )
    briefing = aichat('briefing_writer', formatted_brief_prompt)

    with open(f'{outdir}/company_briefing.md', 'w') as f:
        f.write(briefing)
    subprocess.run([PANDOC, f'{outdir}/company_briefing.md',
                    '--lua-filter', f'{BASE}/config/strip-bookmarks.lua',
                    '--reference-doc', f'{BASE}/config/reference.docx',
                    '-o', f'{outdir}/company_briefing.docx'], check=False)

    # ── Step 5: Network outreach ──
    subprocess.run([sys.executable, f'{BASE}/scripts/find_contacts.py',
                    company, jd_text[:2000], outdir], check=False)

    # ── Step 6: Review checklist ──
    with open(f'{outdir}/REVIEW_CHECKLIST.md', 'w') as f:
        f.write(f"""# Review Checklist — {company} / {title}
Generated: {date}

## Before sending, complete these steps:
- [ ] Open tailored_resume_CHANGES.md — review every flagged reorder/keyword add
- [ ] Open tailored_resume_DRAFT.docx — fill any [MISSING: ...] placeholders
- [ ] Open cover_letter_DRAFT.docx — fill ALL [INSERT: ...] and [MISSING: ...] items
- [ ] Read cover letter aloud — does it sound like you?
- [ ] Verify every factual claim in the cover letter (metrics, company names, titles)
- [ ] Check company_briefing.docx — any red flags or new intel to weave in?
- [ ] Review outreach drafts if you plan to reach out before applying

## Files in this folder:
- tailored_resume_DRAFT.docx    ← start here
- tailored_resume_CHANGES.md    ← what the AI changed and why
- cover_letter_DRAFT.docx       ← fill placeholders before sending
- company_briefing.docx
- outreach_*.txt
""")

    # ── Step 7: Update SQLite ──
    now = datetime.now(timezone.utc).isoformat()
    old_stage = row['stage'] if row else 'unknown'

    conn.execute('''
        UPDATE jobs SET stage='materials_drafted', stage_updated=?, prep_folder_path=?, updated_at=?
        WHERE id=?
    ''', (now, outdir, now, job_id))
    conn.commit()
    write_audit(conn, job_id, 'stage', old_stage, 'materials_drafted')
    conn.close()

    subprocess.run([sys.executable, f'{BASE}/scripts/sync_sheet.py'], check=False)

    log_event('prep_complete', company=company, title=title, folder=outdir)
    notify(f"Drafts ready: {company} — {title}\n{outdir}")

    # ── Sync companies/ to Google Drive (bisync, both directions) ──
    subprocess.run([
        RCLONE, 'bisync',
        f'{BASE}/companies/', 'gdrive:01 PROJECTS/Jobs To Apply For',
        '--create-empty-src-dirs'
    ], check=False)

    print(f"PREP_COMPLETE:{outdir}")

if __name__ == '__main__':
    main()
