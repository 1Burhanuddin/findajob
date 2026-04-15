#!/usr/bin/env python3
# ~/JobSearchPipeline/scripts/prep_application.py
# Args: company, title, url, job_id
"""Generate draft application materials for a flagged job."""

import json
import os
import re
import sqlite3
import subprocess
import sys
from datetime import UTC, datetime

from findajob.paths import AICHAT, BASE, PANDOC, RCLONE
from findajob.utils import (
    JD_MAX_CHARS,
    build_prep_filenames,
    load_env,
    log_event,
    read_file_prefix,
    write_audit,
)

DB_PATH = f"{BASE}/data/pipeline.db"
PROFILE_PATH = f"{BASE}/candidate_context/profile.md"
MASTER_RESUME_PATH = f"{BASE}/candidate_context/master_resume.md"

load_env()


def aichat(role, prompt, model_override=None, timeout=300):
    """Call aichat-ng and return stdout. No RAG — all context injected directly."""
    cmd = [AICHAT, "--role", role]
    if model_override:
        cmd += ["-m", model_override]
    cmd += ["-S", prompt]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    output = result.stdout.strip()
    if result.returncode != 0 or not output:
        log_event("aichat_failure", role=role, returncode=result.returncode, stderr=result.stderr.strip()[:500])
    # Strip <think>...</think> blocks that leak from :thinking models
    output = re.sub(r"<think>.*?</think>", "", output, flags=re.DOTALL).strip()
    return output


def abbrev_title(title, max_words=3):
    """Return a folder-safe abbreviated title: first N significant words joined with underscores."""
    title = re.sub(r"\s*\(.*?\)", "", title)  # strip parentheticals
    title = re.sub(r"[^\w\s-]", "", title)  # remove punctuation
    words = [w for w in title.split() if w][:max_words]
    return "_".join(words) if words else "Job"


def notify(message):
    topic = None
    try:
        with open(f"{BASE}/config/ntfy_topic.txt") as f:
            topic = f.read().strip()
    except FileNotFoundError:
        pass
    if not topic:
        # Fall back to data/.env NTFY_TOPIC
        try:
            with open(f"{BASE}/data/.env") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("NTFY_TOPIC") and "=" in line:
                        topic = line.split("=", 1)[1].strip().strip("'\"")
                        break
        except Exception:
            pass
    if not topic:
        return
    try:
        subprocess.run(["curl", "-s", "-d", message, f"https://ntfy.sh/{topic}"], capture_output=True, timeout=10)
    except Exception:
        pass


def main():
    company, title, url, job_id = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]

    # Guard: skip if prep already completed for this job
    conn_check = sqlite3.connect(DB_PATH, timeout=30)
    conn_check.row_factory = sqlite3.Row
    existing = conn_check.execute("SELECT prep_folder_path, stage FROM jobs WHERE id=?", (job_id,)).fetchone()
    conn_check.close()
    if existing and existing["prep_folder_path"] and existing["stage"] == "materials_drafted":
        log_event("prep_skipped_duplicate", company=company, title=title, job_id=job_id)
        print(f"PREP_SKIPPED: materials already drafted for {job_id}")
        return

    # Sanitize company for filesystem safety (title already goes through abbrev_title)
    safe_company = re.sub(r"[^\w\s\-&.,]", "_", company).strip()
    date = datetime.now().strftime("%Y-%m-%d")
    time_str = datetime.now().strftime("%H%M%S")
    outdir = f"{BASE}/companies/{safe_company}_{abbrev_title(title)}_{date}_{time_str}"
    os.makedirs(outdir, exist_ok=True)

    # Build per-file output paths using the candidate's file prefix (from profile.md).
    # Pattern: {Prefix} Resume - {Company} - {Title} - {YYYYMMDD-HHMMSS}.{ext}
    # See scripts/utils.py:build_prep_filenames for the full pattern.
    file_prefix = read_file_prefix()
    timestamp_fn = f"{date.replace('-', '')}-{time_str}"
    fn = build_prep_filenames(company, title, timestamp_fn, file_prefix)
    out = {k: os.path.join(outdir, v) for k, v in fn.items()}

    log_event("prep_started", company=company, title=title, job_id=job_id, file_prefix=file_prefix)

    # ── Step 1: Load JD from DB (already fetched during triage) ──
    # Do NOT re-curl — LinkedIn and many other URLs require auth and will return garbage.
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT raw_jd_text, stage FROM jobs WHERE id=?", (job_id,)).fetchone()
    jd_text = (row["raw_jd_text"] or "").strip() if row else ""

    if not jd_text or len(jd_text) < 50:
        # Fallback: try curling for Greenhouse/Lever/public URLs only
        try:
            raw = subprocess.run(["curl", "-sL", "--max-time", "15", url], capture_output=True, text=True).stdout
            jd_text = subprocess.run(
                [PANDOC, "-f", "html", "-t", "plain"], input=raw, capture_output=True, text=True
            ).stdout[:JD_MAX_CHARS]
        except Exception:
            jd_text = "[ERROR: Could not fetch JD]"

    with open(out["jd_txt"], "w") as f:
        f.write(jd_text)

    # ── Load profile and master resume — injected directly, never via RAG ──
    try:
        with open(PROFILE_PATH) as f:
            profile_text = f.read()
    except FileNotFoundError:
        profile_text = "[Profile not found]"
        log_event("prep_warning", msg="profile.md not found", job_id=job_id)

    try:
        with open(MASTER_RESUME_PATH) as f:
            master_text = f.read()
    except FileNotFoundError:
        master_text = "[Master resume not found]"
        log_event("prep_warning", msg="master_resume.md not found", job_id=job_id)

    # ── Step 2: Company briefing FIRST — gives all downstream steps rich context ──
    brief_prompt = f"Research {company} thoroughly.\nJob title: {title}\nJD excerpt:\n{jd_text[:2000]}"
    raw_briefing = aichat("company_researcher", brief_prompt, model_override="perplexity:sonar-reasoning-pro")

    # Pass raw research through briefing_writer with candidate context for stories
    formatted_brief_prompt = (
        f"Format the following company research into a structured briefing 1-pager "
        f"for {company}. Job: {title}.\n\n"
        f"RAW RESEARCH:\n{raw_briefing}\n\n"
        f"CANDIDATE PROFILE:\n{profile_text}\n\n"
        f"MASTER RESUME:\n{master_text}\n\n"
        f"JD:\n{jd_text[:3000]}"
    )
    briefing = aichat("briefing_writer", formatted_brief_prompt)

    # Fit analysis: multi-dimensional assessment appended to briefing
    fit_prompt = (
        f"Analyze the fit between this candidate and this role.\n\n"
        f"CANDIDATE PROFILE:\n{profile_text}\n\n"
        f"MASTER RESUME:\n{master_text}\n\n"
        f"Company: {company}\nTitle: {title}\n\n"
        f"JD:\n{jd_text[:3000]}\n\n"
        f"COMPANY BRIEFING:\n{briefing}"
    )
    fit_analysis = aichat("fit_analyst", fit_prompt, model_override="perplexity:sonar-reasoning-pro")

    # Combine briefing and fit analysis into one document
    full_briefing = briefing
    fit_score_avg = None
    prob_score_avg = None
    if fit_analysis:
        full_briefing += f"\n\n---\n\n# Fit Analysis\n\n{fit_analysis}"
        # Parse scores from fit analysis for DB storage
        # All scores are 0-100%. Fit Matrix section has 6 dimensions, Probability has 3.
        try:
            # Split on Probability Assessment heading to separate the two sections
            parts = re.split(r"##\s*🎯\s*Probability Assessment", fit_analysis, maxsplit=1)
            fit_section = parts[0] if parts else fit_analysis
            prob_section = parts[1] if len(parts) > 1 else ""
            fit_scores = [int(m.group(1)) for m in re.finditer(r":\s*(\d{1,3})%", fit_section)]
            prob_scores = [int(m.group(1)) for m in re.finditer(r":\s*(\d{1,3})%", prob_section)]
            if fit_scores:
                fit_score_avg = round(sum(fit_scores) / len(fit_scores), 1)
            if prob_scores:
                prob_score_avg = round(sum(prob_scores) / len(prob_scores), 1)
            log_event(
                "fit_analysis",
                company=company,
                title=title,
                fit_score=fit_score_avg,
                probability_score=prob_score_avg,
                fit_scores=fit_scores,
                prob_scores=prob_scores,
            )
        except Exception:
            pass

    with open(out["briefing_md"], "w") as f:
        f.write(full_briefing)
    subprocess.run(
        [
            PANDOC,
            "-f",
            "markdown-yaml_metadata_block",
            out["briefing_md"],
            "--lua-filter",
            f"{BASE}/config/strip-bookmarks.lua",
            "--reference-doc",
            f"{BASE}/config/reference.docx",
            "-o",
            out["briefing_docx"],
        ],
        check=False,
    )

    # ── Step 3: Resume — briefing context now available ──
    # Truncate briefing to key sections for prompt size management
    briefing_context = briefing[:3000] if briefing else ""
    resume_prompt = (
        f"MASTER RESUME:\n{master_text}\n\n"
        f"CANDIDATE PROFILE:\n{profile_text}\n\n"
        f"Company: {company}\nTitle: {title}\n\n"
        f"JD:\n{jd_text}\n\n"
        f"COMPANY BRIEFING (use to inform bullet selection and summary framing):\n{briefing_context}"
    )
    resume_md = aichat("resume_tailor", resume_prompt)
    # Strip [VERIFY: ...] lines that appear before the first # header
    rlines = resume_md.split("\n")
    first_hdr = next((i for i, line in enumerate(rlines) if line.startswith("#")), 0)
    rlines = [line for i, line in enumerate(rlines) if not (i < first_hdr and line.startswith("[VERIFY:"))]
    resume_md = "\n".join(rlines).strip()
    with open(out["resume_md"], "w") as f:
        f.write(resume_md)

    # Quality check — log violation counts for trend tracking
    try:
        qc = subprocess.run(
            [sys.executable, f"{BASE}/scripts/diag/validate_resume.py", "--json", out["resume_md"]],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if qc.stdout:
            viols_by_file = json.loads(qc.stdout)
            viols = list(viols_by_file.values())[0] if viols_by_file else []
            log_event(
                "resume_quality_check",
                company=company,
                title=title,
                violations=len(viols),
                high=sum(1 for v in viols if v["severity"] == "HIGH"),
                med=sum(1 for v in viols if v["severity"] == "MED"),
            )
    except Exception:
        pass  # quality check is informational only — never block prep

    subprocess.run(
        [
            PANDOC,
            out["resume_md"],
            "--lua-filter",
            f"{BASE}/config/strip-bookmarks.lua",
            "--reference-doc",
            f"{BASE}/config/reference.docx",
            "-o",
            out["resume_docx"],
        ],
        check=False,
    )

    # Generate change log
    changes_prompt = (
        f"ORIGINAL MASTER RESUME:\n{master_text}\n\nTAILORED RESUME:\n{resume_md}\n\nTARGET JD:\n{jd_text[:2000]}"
    )
    changes_md = aichat("resume_change_reviewer", changes_prompt)
    with open(out["changes_md"], "w") as f:
        f.write(changes_md)

    # ── Step 4: Cover letter — briefing context for specific company signals ──
    today_str = datetime.now().strftime("%B %d, %Y")
    cover_prompt = (
        f"CANDIDATE PROFILE:\n{profile_text}\n\n"
        f"MASTER RESUME:\n{master_text}\n\n"
        f"Company: {company}\nTitle: {title}\nDate: {today_str}\n\n"
        f"JD:\n{jd_text}\n\n"
        f"COMPANY BRIEFING (use for specific signals, news, and context about this company):\n{briefing_context}"
    )
    cover_md_text = aichat("cover_letter_writer", cover_prompt)
    with open(out["cover_md"], "w") as f:
        f.write(cover_md_text)
    subprocess.run(
        [
            PANDOC,
            out["cover_md"],
            "--lua-filter",
            f"{BASE}/config/strip-bookmarks.lua",
            "--reference-doc",
            f"{BASE}/config/reference.docx",
            "-o",
            out["cover_docx"],
        ],
        check=False,
    )

    # ── Step 5: Network outreach ──
    # Pass the file_prefix and timestamp so outreach files follow the same naming convention.
    subprocess.run(
        [
            sys.executable,
            f"{BASE}/scripts/find_contacts.py",
            company,
            jd_text[:2000],
            outdir,
            file_prefix,
            timestamp_fn,
        ],
        check=False,
    )

    # ── Step 6: Review checklist ──
    with open(out["checklist_md"], "w") as f:
        f.write(f"""# Review Checklist — {company} / {title}
Generated: {date}

## Before sending, complete these steps:
- [ ] Open `{fn["changes_md"]}` — review every flagged reorder/keyword add
- [ ] Open `{fn["resume_docx"]}` — fill any [MISSING: ...] placeholders
- [ ] Open `{fn["cover_docx"]}` — fill any [MISSING: ...] placeholders (expect 1-2 max)
- [ ] Read cover letter aloud — does it sound like you?
- [ ] Verify every factual claim in the cover letter (metrics, company names, titles)
- [ ] Check `{fn["briefing_docx"]}` — any red flags or new intel to weave in?
- [ ] Review outreach drafts if you plan to reach out before applying

## Files in this folder:
- `{fn["resume_docx"]}`    ← start here
- `{fn["changes_md"]}`    ← what the AI changed and why
- `{fn["cover_docx"]}`       ← fill placeholders before sending
- `{fn["briefing_docx"]}`
- `{fn["jd_txt"]}`    ← original JD for reference
- `{file_prefix} Outreach to *.txt`    ← network outreach drafts
""")

    # ── Step 7: Update SQLite (stage + scores) ──
    now = datetime.now(UTC).isoformat()
    old_stage = row["stage"] if row else "unknown"

    conn.execute(
        """
        UPDATE jobs SET stage='materials_drafted', stage_updated=?, prep_folder_path=?,
               fit_score=?, probability_score=?, updated_at=?
        WHERE id=?
    """,
        (now, outdir, fit_score_avg, prob_score_avg, now, job_id),
    )
    conn.commit()
    write_audit(conn, job_id, "stage", old_stage, "materials_drafted")

    log_event("prep_complete", company=company, title=title, folder=outdir)
    notify(f"Drafts ready: {company} — {title}\n{outdir}")

    # ── Step 8: Push new folder to Drive immediately ──
    # jobsync.timer runs rclone sync every 15 min as the steady-state mirror,
    # but we push the new folder now so Step 9 (rclone link) can fetch the URL.
    # Safe: jobsync uses rclone sync (not bisync), so no conflict copies.
    folder_name = os.path.basename(outdir)
    try:
        subprocess.run(
            [RCLONE, "copy", "--update", outdir, f"gdrive:01 PROJECTS/Jobs To Apply For/{folder_name}"],
            capture_output=True,
            text=True,
            timeout=300,
        )
    except Exception as e:
        log_event("rclone_immediate_push_failed", job_id=job_id, error=str(e))

    # ── Step 9: Fetch the Drive folder URL and store it ──
    # Used by sync_sheet.py to render the company name as a HYPERLINK to the Drive folder.
    # Failure is non-fatal: the cell stays plain text if rclone link fails.
    drive_url = None
    try:
        link_rc = subprocess.run(
            [RCLONE, "link", f"gdrive:01 PROJECTS/Jobs To Apply For/{folder_name}"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if link_rc.returncode == 0 and link_rc.stdout.strip().startswith("http"):
            drive_url = link_rc.stdout.strip()
            conn.execute("UPDATE jobs SET gdrive_folder_url=? WHERE id=?", (drive_url, job_id))
            conn.commit()
            log_event("gdrive_link_stored", job_id=job_id, url=drive_url)
        else:
            log_event(
                "gdrive_link_failed",
                job_id=job_id,
                exit_code=link_rc.returncode,
                stderr=link_rc.stderr[:200] if link_rc.stderr else "",
            )
    except Exception as e:
        log_event("gdrive_link_failed", job_id=job_id, error=str(e))

    conn.close()

    # ── Step 10: Sync sheets (single call, after everything is ready) ──
    subprocess.run([sys.executable, f"{BASE}/scripts/sync_sheet.py"], check=False)

    print(f"PREP_COMPLETE:{outdir}")


if __name__ == "__main__":
    main()
