#!/usr/bin/env python3
# ~/JobSearchPipeline/scripts/regen_resumes.py
"""
Re-run resume_tailor for every folder in ~/JobSearchPipeline/companies/.
Outputs tailored_resume_DRAFT_v2.md and .docx alongside existing files.
Works from folder contents only — no DB lookup required.
"""

import os
import subprocess

from findajob.paths import AICHAT, BASE, PANDOC

COMPANIES_DIR = f"{BASE}/companies"
MASTER_RESUME_PATH = f"{BASE}/candidate_context/master_resume.md"
PROFILE_PATH = f"{BASE}/candidate_context/profile.md"


def aichat(role, prompt, timeout=300):
    result = subprocess.run([AICHAT, "--role", role, "-S", prompt], capture_output=True, text=True, timeout=timeout)
    return result.stdout.strip()


def main():
    # Load master resume and profile — injected directly, never via RAG
    with open(MASTER_RESUME_PATH) as f:
        master_text = f.read()
    with open(PROFILE_PATH) as f:
        profile_text = f.read()

    folders = sorted([d for d in os.listdir(COMPANIES_DIR) if os.path.isdir(os.path.join(COMPANIES_DIR, d))])

    if not folders:
        print("No folders found in companies/")
        return

    print(f"Found {len(folders)} folder(s):\n")
    for f in folders:
        print(f"  {f}")
    print()

    for folder_name in folders:
        folder_path = os.path.join(COMPANIES_DIR, folder_name)
        print(f"{'=' * 60}")
        print(f"Processing: {folder_name}")

        # Skip if v2 already exists
        v2_path = os.path.join(folder_path, "tailored_resume_DRAFT_v2.md")
        if os.path.exists(v2_path):
            print("  SKIP — tailored_resume_DRAFT_v2.md already exists")
            continue

        # Load JD — prefer job_description.txt, fall back to any .txt
        jd_text = ""
        jd_file = os.path.join(folder_path, "job_description.txt")
        if os.path.exists(jd_file):
            with open(jd_file) as f:
                jd_text = f.read().strip()
        else:
            for fname in os.listdir(folder_path):
                if fname.endswith(".txt"):
                    with open(os.path.join(folder_path, fname)) as f:
                        jd_text = f.read().strip()
                    print(f"  JD source: {fname}")
                    break

        if not jd_text:
            print("  WARNING — no JD found, proceeding with title/company from folder name only")

        # Parse company and title hint from folder name: {company}_{date} or {company}_{date}_{time}
        # Best effort — folder name is the only reliable signal
        parts = folder_name.split("_")
        # Strip trailing date (YYYY-MM-DD) and optional time (HHMMSS)
        company_parts = []
        for p in parts:
            if len(p) == 10 and p[4] == "-" and p[7] == "-":
                break  # hit the date — stop
            company_parts.append(p)
        company_hint = " ".join(company_parts) if company_parts else folder_name

        # Try to get title from existing cover letter or checklist for context
        title_hint = ""
        checklist = os.path.join(folder_path, "REVIEW_CHECKLIST.md")
        if os.path.exists(checklist):
            with open(checklist) as f:
                for line in f:
                    if "—" in line and "Review Checklist" in line:
                        # Format: # Review Checklist — Company / Title
                        try:
                            title_hint = line.split("/")[-1].strip()
                        except Exception:
                            pass
                        break

        print(f"  Company: {company_hint}")
        print(f"  Title hint: {title_hint or '(none found)'}")
        print(f"  JD length: {len(jd_text)} chars")
        print("  Calling resume_tailor...")

        prompt = (
            f"MASTER RESUME:\n{master_text}\n\n"
            f"CANDIDATE PROFILE:\n{profile_text}\n\n"
            f"Company: {company_hint}\n"
            f"Title: {title_hint or '(see JD)'}\n\n"
            f"JD:\n{jd_text}"
        )

        try:
            resume_md = aichat("resume_tailor", prompt)
        except subprocess.TimeoutExpired:
            print("  ERROR — aichat-ng timed out")
            continue
        except Exception as e:
            print(f"  ERROR — {e}")
            continue

        if not resume_md or len(resume_md) < 100:
            print(f"  ERROR — output too short ({len(resume_md)} chars), skipping")
            continue

        # Write v2 markdown
        with open(v2_path, "w") as f:
            f.write(resume_md)

        # Convert to docx
        v2_docx = os.path.join(folder_path, "tailored_resume_DRAFT_v2.docx")
        subprocess.run(
            [
                PANDOC,
                v2_path,
                "--lua-filter",
                f"{BASE}/config/strip-bookmarks.lua",
                "--reference-doc",
                f"{BASE}/config/reference.docx",
                "-o",
                v2_docx,
            ],
            check=False,
        )

        print("  DONE → tailored_resume_DRAFT_v2.md + .docx")

    print(f"\n{'=' * 60}")
    print("All folders processed.")


if __name__ == "__main__":
    main()
