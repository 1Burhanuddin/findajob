# JD Quality Improvement Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Strip trailing boilerplate from JD text, raise the 8k char cap to 16k, and backfill ~280 recoverable truncated JDs so scoring and prep work off more complete job descriptions.

**Architecture:** A new `strip_jd_boilerplate()` function in `utils.py` detects and removes trailing EEO/legal/benefits paragraphs. A `JD_MAX_CHARS` constant replaces the 6 hardcoded `[:8000]` truncation sites. The existing `backfill_jd.py` gets a `--truncated` mode to re-fetch JDs that hit the old cap.

**Tech Stack:** Python 3, sqlite3, subprocess (curl, pandoc), requests (RapidAPI)

**Spec:** `docs/superpowers/specs/2026-04-10-jd-quality-design.md`

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `scripts/utils.py` | Modify | Add `JD_MAX_CHARS`, `strip_jd_boilerplate()` |
| `scripts/triage.py` | Modify (lines 122, 163, 193, 205, 208) | Replace 5 `[:8000]` sites |
| `scripts/backfill_jd.py` | Modify | Add `--truncated` mode, use stripping + new cap |
| `scripts/prep_application.py` | Modify (line 103) | Replace `[:8000]` with `[:JD_MAX_CHARS]` |

---

### Task 1: Add `JD_MAX_CHARS` and `strip_jd_boilerplate()` to utils.py

**Files:**
- Modify: `scripts/utils.py` (append after `jd_is_usable()` at line 97)

- [ ] **Step 1: Add the constant and boilerplate patterns**

Add to the end of `scripts/utils.py`:

```python
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
```

- [ ] **Step 2: Add the `strip_jd_boilerplate()` function**

Add immediately after the regex:

```python
def strip_jd_boilerplate(text):
    """Remove trailing EEO/legal/benefits boilerplate from JD text.

    Works backwards from the end, paragraph by paragraph. Stops trimming
    when a paragraph doesn't match any boilerplate pattern. Never removes
    more than 40% of the text or drops below 200 chars retained.
    """
    if not text or len(text) < 200:
        return text or ''

    import re as _re

    # Split into paragraphs on double-newline or blank lines
    paragraphs = _re.split(r'\n\s*\n', text)
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
```

- [ ] **Step 3: Add `import re` to utils.py imports if not present**

Check the imports at the top of `utils.py`. Currently it imports `os, json`. Add `re`:

```python
import os, json, re
```

- [ ] **Step 4: Verify the function works on a sample**

Run an inline test against the actual DB:

```bash
python3 -c "
import sqlite3
from scripts.utils import strip_jd_boilerplate

conn = sqlite3.connect('data/pipeline.db')
# Grab 5 JDs that are exactly 8000 chars (truncated)
rows = conn.execute('SELECT id, LENGTH(raw_jd_text) as len, raw_jd_text FROM jobs WHERE LENGTH(raw_jd_text) = 8000 LIMIT 5').fetchall()
for job_id, orig_len, jd in rows:
    stripped = strip_jd_boilerplate(jd)
    print(f'{job_id}: {orig_len} -> {len(stripped)} ({orig_len - len(stripped)} chars removed)')
    # Show last 100 chars of stripped version
    print(f'  tail: ...{stripped[-100:]}')
    print()
conn.close()
"
```

Expected: some JDs shrink (boilerplate at tail removed), some stay the same (truncation cut off mid-content, no trailing boilerplate). No errors.

- [ ] **Step 5: Also test on a full-length JD with known boilerplate**

```bash
python3 -c "
import sqlite3
from scripts.utils import strip_jd_boilerplate

conn = sqlite3.connect('data/pipeline.db')
# Grab a JD that contains 'equal opportunity employer' near the end
rows = conn.execute('''
    SELECT id, raw_jd_text FROM jobs
    WHERE raw_jd_text LIKE '%equal opportunity employer%'
      AND LENGTH(raw_jd_text) BETWEEN 3000 AND 7000
    LIMIT 3
''').fetchall()
for job_id, jd in rows:
    stripped = strip_jd_boilerplate(jd)
    removed = len(jd) - len(stripped)
    pct = round(removed / len(jd) * 100, 1) if removed else 0
    print(f'{job_id}: {len(jd)} -> {len(stripped)} ({removed} chars, {pct}% removed)')
conn.close()
"
```

Expected: 5-25% removal for JDs with EEO tails.

- [ ] **Step 6: Commit**

```bash
git add scripts/utils.py
git commit -m "Add strip_jd_boilerplate() and JD_MAX_CHARS to utils.py

Strips trailing EEO/legal/benefits paragraphs from JD text. Walks backwards
from the end, paragraph by paragraph. Safety: never removes >40% or drops
below 200 chars. JD_MAX_CHARS=16000 replaces the old hardcoded 8000 limit.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Replace `[:8000]` truncation sites in triage.py

**Files:**
- Modify: `scripts/triage.py` (lines 122, 163, 193, 205, 208)

- [ ] **Step 1: Add import**

At the top of `triage.py`, the existing import from `utils` is on line 13:

```python
from utils import log_event, write_audit, load_env, validate_llm_json, jd_is_usable, _JD_WALL_SIGNALS
```

Add `strip_jd_boilerplate` and `JD_MAX_CHARS`:

```python
from utils import log_event, write_audit, load_env, validate_llm_json, jd_is_usable, _JD_WALL_SIGNALS, strip_jd_boilerplate, JD_MAX_CHARS
```

- [ ] **Step 2: Fix `fetch_jd_curl()` (line 122)**

Change line 122 from:
```python
        return text[:8000]
```
To:
```python
        return strip_jd_boilerplate(text)[:JD_MAX_CHARS]
```

- [ ] **Step 3: Fix `fetch_linkedin_job_data()` (line 163)**

Change line 162-163 from:
```python
        return {
            'description': description[:8000] if description else None,
```
To:
```python
        return {
            'description': strip_jd_boilerplate(description)[:JD_MAX_CHARS] if description else None,
```

- [ ] **Step 4: Fix `fetch_jd()` Indeed path (line 193)**

Change line 193 from:
```python
            return desc[:8000]
```
To:
```python
            return strip_jd_boilerplate(desc)[:JD_MAX_CHARS]
```

- [ ] **Step 5: Fix `fetch_jd()` Greenhouse pandoc path (line 205)**

Change line 201-205 from:
```python
            try:
                plain = subprocess.run(
                    [PANDOC, '-f', 'html', '-t', 'plain'],
                    input=desc, capture_output=True, text=True, timeout=10
                ).stdout[:8000]
```
To:
```python
            try:
                plain = subprocess.run(
                    [PANDOC, '-f', 'html', '-t', 'plain'],
                    input=desc, capture_output=True, text=True, timeout=10
                ).stdout
                plain = strip_jd_boilerplate(plain)[:JD_MAX_CHARS]
```

- [ ] **Step 6: Fix `fetch_jd()` Greenhouse fallback path (line 208)**

Change line 208 from:
```python
                return desc[:8000]
```
To:
```python
                return strip_jd_boilerplate(desc)[:JD_MAX_CHARS]
```

- [ ] **Step 7: Verify triage.py still parses cleanly**

```bash
python3 -c "import scripts.triage; print('OK')"
```

Expected: `OK` — no import errors or syntax issues.

- [ ] **Step 8: Commit**

```bash
git add scripts/triage.py
git commit -m "Replace [:8000] truncation with boilerplate stripping + 16k cap in triage.py

All 5 JD fetch paths now call strip_jd_boilerplate() before capping at
JD_MAX_CHARS (16000). Prevents mid-sentence truncation for 447 existing
jobs and all future ingests.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Update prep_application.py fallback path

**Files:**
- Modify: `scripts/prep_application.py` (line 103)

- [ ] **Step 1: Add import**

At the top of `prep_application.py`, add to the existing imports from utils/paths. After line 10:

```python
from utils import log_event, write_audit, load_env
```

Add `JD_MAX_CHARS`:

```python
from utils import log_event, write_audit, load_env, JD_MAX_CHARS
```

- [ ] **Step 2: Replace the truncation**

Change line 103 from:
```python
            jd_text = subprocess.run([PANDOC, '-f', 'html', '-t', 'plain'],
                                     input=raw, capture_output=True, text=True).stdout[:8000]
```
To:
```python
            jd_text = subprocess.run([PANDOC, '-f', 'html', '-t', 'plain'],
                                     input=raw, capture_output=True, text=True).stdout[:JD_MAX_CHARS]
```

Note: no boilerplate stripping here — this is a last-resort fallback path that rarely fires. The JD should already be stored stripped in the DB. The cap is just a safety net.

- [ ] **Step 3: Verify parse**

```bash
python3 -c "import scripts.prep_application; print('OK')"
```

- [ ] **Step 4: Commit**

```bash
git add scripts/prep_application.py
git commit -m "Use JD_MAX_CHARS in prep_application.py fallback curl path

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Add `--truncated` mode to backfill_jd.py

**Files:**
- Modify: `scripts/backfill_jd.py`

- [ ] **Step 1: Update imports and constants**

Replace the top section (lines 1-24) of `backfill_jd.py`. After the existing imports and path setup, add the new imports:

```python
from utils import log_event, load_env, strip_jd_boilerplate, JD_MAX_CHARS
```

This replaces the existing `from utils import log_event, load_env` on line 21.

- [ ] **Step 2: Update `fetch_linkedin_jd()` to use stripping and new cap**

Change line 69 from:
```python
        desc = description[:8000] if description else None
```
To:
```python
        desc = strip_jd_boilerplate(description)[:JD_MAX_CHARS] if description else None
```

- [ ] **Step 3: Add Greenhouse and curl re-fetch helpers**

Add these functions after `fetch_linkedin_jd()` (after line 73):

```python
def fetch_greenhouse_jd(url):
    """Re-fetch JD from a Greenhouse URL. Returns stripped text or None."""
    import subprocess as sp
    from paths import PANDOC
    try:
        raw = sp.run(['curl', '-sL', '--max-time', '15', url],
                     capture_output=True, text=True).stdout
        if not raw or len(raw.strip()) < 50:
            return None
        text = sp.run([PANDOC, '-f', 'html', '-t', 'plain'],
                      input=raw, capture_output=True, text=True, timeout=10).stdout
        text = strip_jd_boilerplate(text)[:JD_MAX_CHARS]
        return text if len(text.strip()) >= 50 else None
    except Exception:
        return None


def fetch_curl_jd(url):
    """Re-fetch JD by curling a public URL. Returns stripped text or None."""
    import subprocess as sp
    from paths import PANDOC
    try:
        raw = sp.run(['curl', '-sL', '--max-time', '15', url],
                     capture_output=True, text=True).stdout
        if not raw or len(raw.strip()) < 50:
            return None
        text = sp.run([PANDOC, '-f', 'html', '-t', 'plain'],
                      input=raw, capture_output=True, text=True, timeout=10).stdout
        text = strip_jd_boilerplate(text)[:JD_MAX_CHARS]
        return text if len(text.strip()) >= 50 else None
    except Exception:
        return None
```

- [ ] **Step 4: Add `backfill_truncated()` function**

Add after the new helpers:

```python
def backfill_truncated(dry_run=False):
    """Re-fetch JDs that were truncated at the old 8000-char cap."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL')

    rows = conn.execute('''
        SELECT id, url, title, company, source, raw_jd_text, stage
        FROM jobs
        WHERE LENGTH(raw_jd_text) BETWEEN 7900 AND 8000
          AND (dupe_of = '' OR dupe_of IS NULL)
          AND stage NOT IN ('rejected', 'withdrawn')
    ''').fetchall()

    print(f"Truncated JDs to backfill: {len(rows)}")

    # Tally by source
    from collections import Counter
    source_counts = Counter(r['source'] for r in rows)
    for src, cnt in source_counts.most_common():
        print(f"  {src}: {cnt}")

    if dry_run:
        print("\n--dry-run: no changes made.")
        conn.close()
        return

    log_event('backfill_truncated_started', total=len(rows),
              by_source=dict(source_counts))

    fetched = 0
    skipped = 0
    failed = 0

    for i, row in enumerate(rows, 1):
        source = row['source']
        old_len = len(row['raw_jd_text'])
        label = f"[{i}/{len(rows)}] {row['title'][:40]} @ {row['company'] or '(blank)'} ({source})"

        # Skip sources we can't re-fetch
        if source in ('jobsapi_indeed', 'manual', 'manual_form'):
            print(f"{label} — SKIP (no re-fetch path)")
            skipped += 1
            continue

        # Fetch by source
        new_jd = None
        if source == 'greenhouse_json':
            new_jd = fetch_greenhouse_jd(row['url'])
            time.sleep(0.1)
        elif source in ('jobsapi_linkedin', 'gmail_linkedin'):
            api_id = extract_job_id(row['url'])
            if api_id:
                new_jd, _ = fetch_linkedin_jd(api_id)
            time.sleep(0.3)
        elif source in ('gmail_google',):
            new_jd = fetch_curl_jd(row['url'])
            time.sleep(0.1)
        else:
            new_jd = fetch_curl_jd(row['url'])
            time.sleep(0.1)

        if new_jd and len(new_jd.strip()) > old_len:
            now = datetime.now(timezone.utc).isoformat()
            conn.execute('UPDATE jobs SET raw_jd_text=?, updated_at=? WHERE id=?',
                         (new_jd, now, row['id']))
            conn.commit()
            fetched += 1
            print(f"{label} — OK {old_len} -> {len(new_jd)}")
        elif new_jd:
            skipped += 1
            print(f"{label} — SKIP (new={len(new_jd)} <= old={old_len})")
        else:
            failed += 1
            print(f"{label} — FAIL (no JD returned)")

    print(f"\nDone: {fetched} updated, {skipped} skipped, {failed} failed")
    log_event('backfill_truncated_complete', fetched=fetched, skipped=skipped, failed=failed)
    conn.close()
    return fetched
```

- [ ] **Step 5: Update `main()` to handle new flags**

Replace the existing `main()` function (lines 76-146) with:

```python
def main():
    rescore = '--rescore' in sys.argv
    truncated = '--truncated' in sys.argv
    dry_run = '--dry-run' in sys.argv

    if truncated:
        count = backfill_truncated(dry_run=dry_run)
        if rescore and count and not dry_run:
            print(f"\nRescoring {count} backfilled jobs...")
            import subprocess
            subprocess.run([sys.executable, f'{BASE}/scripts/rescore_all.py'], check=False)
        return

    # Original behavior: backfill missing gmail_linkedin JDs
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
            print(f"  OK {len(desc)} chars" + (f" +company={company}" if company and not row['company'] else ''))
        else:
            failed += 1
            print(f"  FAIL no JD returned")

        time.sleep(0.3)  # rate limit

    print(f"\nBackfill complete: {fetched} fetched, {failed} failed, {company_updated} companies updated")
    log_event('backfill_jd_complete', fetched=fetched, failed=failed,
              company_updated=company_updated)

    conn.close()

    if rescore and backfilled_ids:
        print(f"\nRescoring {fetched} backfilled jobs...")
        import subprocess
        subprocess.run([sys.executable, f'{BASE}/scripts/rescore_all.py'], check=False)
```

- [ ] **Step 6: Update the module docstring**

Replace the docstring at the top of the file (lines 3-13):

```python
"""
Backfill job descriptions in the pipeline DB.

Modes:
    backfill_jd.py              — fetch missing JDs for gmail_linkedin jobs
    backfill_jd.py --truncated  — re-fetch JDs truncated at old 8k cap (all sources)

Flags:
    --rescore    rescore affected jobs after backfill
    --dry-run    report what would be fetched (--truncated mode only)
"""
```

- [ ] **Step 7: Verify parse**

```bash
python3 -c "import scripts.backfill_jd; print('OK')"
```

- [ ] **Step 8: Dry run**

```bash
python3 scripts/backfill_jd.py --truncated --dry-run
```

Expected: lists ~429 non-rejected truncated JDs by source, prints "no changes made."

- [ ] **Step 9: Commit**

```bash
git add scripts/backfill_jd.py
git commit -m "Add --truncated mode to backfill_jd.py, apply boilerplate stripping

--truncated re-fetches JDs that hit the old 8k cap from Greenhouse (free),
LinkedIn API (paid), and direct curl sources. Skips Indeed (no re-fetch
path). Applies strip_jd_boilerplate() and 16k cap to all fetched text.
--dry-run reports what would be fetched without making changes.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Run the backfill and verify results

- [ ] **Step 1: Run the truncated backfill for real**

```bash
python3 scripts/backfill_jd.py --truncated
```

Watch the output. Expect: ~178 Greenhouse fetches (free, fast), ~98 LinkedIn API fetches (paid, 0.3s each = ~30s), ~164 Indeed skips, a handful of failures for expired postings.

- [ ] **Step 2: Verify results**

```bash
python3 -c "
import sqlite3
conn = sqlite3.connect('data/pipeline.db')

# How many JDs are still at exactly 8000?
still_8k = conn.execute('SELECT COUNT(*) FROM jobs WHERE LENGTH(raw_jd_text) = 8000').fetchone()[0]
print(f'Still at 8000 chars: {still_8k}')

# How many are now >8000?
over_8k = conn.execute('SELECT COUNT(*) FROM jobs WHERE LENGTH(raw_jd_text) > 8000').fetchone()[0]
print(f'Now >8000 chars: {over_8k}')

# Average JD length now
avg = conn.execute('SELECT ROUND(AVG(LENGTH(raw_jd_text))) FROM jobs WHERE raw_jd_text IS NOT NULL AND LENGTH(raw_jd_text) > 50').fetchone()[0]
print(f'Average JD length: {avg}')

# New max
mx = conn.execute('SELECT MAX(LENGTH(raw_jd_text)) FROM jobs').fetchone()[0]
print(f'Max JD length: {mx}')

conn.close()
"
```

Expected: `still_8k` drops from 447 to ~164 (the Indeed jobs that can't be re-fetched). Some JDs are now >8000 chars. Average length increases.

- [ ] **Step 3: Spot-check 3 backfilled JDs**

```bash
python3 -c "
import sqlite3
conn = sqlite3.connect('data/pipeline.db')
# Find JDs that were updated today and are now > 8000 chars
rows = conn.execute('''
    SELECT id, title, company, LENGTH(raw_jd_text) as len,
           SUBSTR(raw_jd_text, -200) as tail
    FROM jobs
    WHERE LENGTH(raw_jd_text) > 8000
      AND updated_at >= date('now')
    LIMIT 3
''').fetchall()
for r in rows:
    print(f'{r[0]}: {r[2]} / {r[1]} ({r[3]} chars)')
    print(f'  tail: ...{r[4]}')
    print()
conn.close()
"
```

Expected: tails contain actual role content (qualifications, requirements), not EEO boilerplate.

- [ ] **Step 4: Verify new ingests work with a quick triage test**

No full triage run needed. Just verify the import chain works:

```bash
python3 -c "
from scripts.triage import fetch_jd_curl, fetch_jd
print('triage imports OK — fetch_jd_curl and fetch_jd available')
"
```

---

### Task 6: Update ISSUES.md and final commit

- [ ] **Step 1: Add a new closed item to ISSUES.md**

In `docs/ISSUES.md`, add under the Completed section:

```markdown
- [x] **JD text truncated at 8,000 chars — 16.6% of jobs affected** *(closed YYYY-MM-DD)*
  Root cause: `[:8000]` hardcoded in 6 fetch paths across `triage.py` and `backfill_jd.py`.
  447 JDs were cut mid-sentence, losing requirements/qualifications. Additionally, ~57% of
  JDs contained trailing EEO/legal boilerplate consuming ~17% of text.
  Fix: added `strip_jd_boilerplate()` to `utils.py` (removes trailing EEO/legal/benefits
  paragraphs). Raised cap to `JD_MAX_CHARS=16000`. Extended `backfill_jd.py --truncated` to
  re-fetch from Greenhouse (free) and LinkedIn API (~$1). 164 Indeed truncations are
  permanently lost (no re-fetch path). Design spec: `docs/superpowers/specs/2026-04-10-jd-quality-design.md`.
```

- [ ] **Step 2: Commit everything**

```bash
git add docs/ISSUES.md
git commit -m "Close JD truncation issue in ISSUES.md

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```
