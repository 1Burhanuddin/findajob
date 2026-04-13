#!/usr/bin/env python3
"""
validate_resume.py — mechanical format checker for tailored_resume_DRAFT.md files.

Checks every rule in the resume_tailor FORMAT LAW and HARD LIMITS sections.
Use this to establish a baseline before/after prompt changes, and to catch
regressions when the resume_tailor role is updated.

Usage:
    python3 scripts/diag/validate_resume.py path/to/tailored_resume_DRAFT.md
    python3 scripts/diag/validate_resume.py companies/          # scan all folders
    python3 scripts/diag/validate_resume.py --json              # machine-readable output

Returns exit code 0 if no HIGH violations, 1 if any HIGH violations found.
"""

import json
import os
import re
import sys

# ── Constants ─────────────────────────────────────────────────────────────────

PRIMARY_ROLE_MAX_BULLETS = 8
OTHER_ROLE_MAX_BULLETS = 4
MIN_BULLETS_PER_ROLE = 2
SUMMARY_MIN_SENTENCES = 3
SUMMARY_MAX_SENTENCES = 4
MAX_ESTIMATED_PAGES = 2.0
LINES_PER_PAGE = 48  # approximate for dense resume content


# ── Violation dataclass (dict for simplicity) ─────────────────────────────────


def violation(severity, rule, detail, line_num=None):
    v = {"severity": severity, "rule": rule, "detail": detail}
    if line_num:
        v["line"] = line_num
    return v


# ── Parse markdown into role blocks ──────────────────────────────────────────


def parse_sections(lines):
    """Return dict of section_name -> list of (line_num, line_text) for h2 sections."""
    sections = {}
    current = None
    for i, line in enumerate(lines):
        if line.startswith("## "):
            current = line[3:].strip()
            sections[current] = []
        elif current is not None:
            sections[current].append((i + 1, line))
    return sections


def parse_role_blocks(lines):
    """
    Return list of role blocks. Each block:
      {
        'header': str,          # "### Employer — Title" line
        'header_line': int,     # 1-based line number
        'lines': [(lineno, text), ...]  # all lines until next ### or ##
      }
    """
    blocks = []
    current = None
    for i, line in enumerate(lines):
        if line.startswith("### "):
            if current:
                blocks.append(current)
            current = {
                "header": line.strip(),
                "header_line": i + 1,
                "lines": [],
            }
        elif line.startswith("## "):
            # Entering a new h2 section — end any open role block
            if current:
                blocks.append(current)
                current = None
        elif current is not None:
            current["lines"].append((i + 1, line))
    if current:
        blocks.append(current)
    return blocks


# ── Individual rule checks ────────────────────────────────────────────────────


def check_core_competencies(sections):
    """Core Competencies section must exist."""
    violations = []
    found = any("core competencies" in k.lower() for k in sections)
    if not found:
        violations.append(violation("MED", "core_competencies_missing", 'No "## Core Competencies" section found'))
    return violations


def check_summary(sections):
    """Summary must be 3-4 sentences."""
    violations = []
    summary_key = next((k for k in sections if "summary" in k.lower()), None)
    if not summary_key:
        return violations
    text = " ".join(line for _, line in sections[summary_key] if line.strip())
    # Count sentence-ending punctuation (rough but reliable for resume summaries)
    sentences = len(re.findall(r"[.!?](?:\s|$)", text))
    if sentences < SUMMARY_MIN_SENTENCES:
        violations.append(
            violation(
                "LOW", "summary_too_short", f"Summary has ~{sentences} sentence(s); minimum is {SUMMARY_MIN_SENTENCES}"
            )
        )
    elif sentences > SUMMARY_MAX_SENTENCES:
        violations.append(
            violation(
                "LOW", "summary_too_long", f"Summary has ~{sentences} sentences; maximum is {SUMMARY_MAX_SENTENCES}"
            )
        )
    return violations


def check_role_block(block, is_primary):
    """Check a single role block for all FORMAT LAW violations."""
    violations = []
    role_label = block["header"]
    header_line = block["header_line"]
    role_lines = block["lines"]

    # Count bullets
    bullet_lines = [(n, line) for n, line in role_lines if re.match(r"^- ", line)]
    bullet_count = len(bullet_lines)
    max_bullets = PRIMARY_ROLE_MAX_BULLETS if is_primary else OTHER_ROLE_MAX_BULLETS

    if bullet_count > max_bullets:
        sev = "HIGH" if is_primary else "MED"
        violations.append(
            violation(
                sev, "excess_bullets", f'"{role_label}" has {bullet_count} bullets (limit: {max_bullets})', header_line
            )
        )

    if bullet_count < MIN_BULLETS_PER_ROLE:
        violations.append(
            violation(
                "MED",
                "too_few_bullets",
                f'"{role_label}" has {bullet_count} bullet(s); minimum is {MIN_BULLETS_PER_ROLE}',
                header_line,
            )
        )

    # After header line, find the date/location line (first non-empty line).
    # Everything after that (before first bullet) is suspect prose.
    non_bullet_non_blank = [(n, line) for n, line in role_lines if line.strip() and not re.match(r"^- ", line)]

    # First non-blank line is expected to be the date/location line
    date_location_seen = False
    for lineno, line in non_bullet_non_blank:
        stripped = line.strip()

        if not date_location_seen:
            # This should be the date/location line — skip it
            date_location_seen = True
            continue

        # Any subsequent non-bullet, non-blank line before bullets is a violation
        # Check: italic context sentence (starts with * but not **)
        if re.match(r"^\*[^*]", stripped):
            violations.append(
                violation("HIGH", "italic_prose", f'Italic context sentence in "{role_label}": {stripped[:80]}', lineno)
            )
        # Check: bold group label (starts with ** followed by capital or common label)
        elif re.match(r"^\*\*[A-Z]", stripped):
            violations.append(
                violation("HIGH", "bold_group_label", f'Bold thematic label in "{role_label}": {stripped[:80]}', lineno)
            )
        # Check: bold/italic subtitle (starts with _ or __ not a bullet)
        elif re.match(r"^_{1,2}[A-Z]", stripped):
            violations.append(
                violation("HIGH", "italic_subtitle", f'Italic subtitle in "{role_label}": {stripped[:80]}', lineno)
            )
        # Check: plain prose paragraph (non-empty, none of the above, not a bullet)
        elif stripped and not re.match(r"^[-*_#|]", stripped):
            violations.append(
                violation("MED", "prose_paragraph", f'Prose paragraph in "{role_label}": {stripped[:80]}', lineno)
            )

    return violations


def check_length(lines):
    """Estimate page count; flag if over 2 pages."""
    violations = []
    non_blank = sum(1 for line in lines if line.strip())
    pages = non_blank / LINES_PER_PAGE
    if pages > MAX_ESTIMATED_PAGES:
        violations.append(
            violation("MED", "too_long", f"Estimated length {pages:.1f} pages (max {MAX_ESTIMATED_PAGES})")
        )
    return violations


def check_em_dashes(lines):
    """Flag em dashes in the resume (telltale LLM sign)."""
    violations = []
    count = 0
    for i, line in enumerate(lines):
        if "\u2014" in line:
            count += 1
            if count <= 3:  # report first 3 occurrences
                violations.append(violation("MED", "em_dash", f"Em dash found: {line.strip()[:80]}", i + 1))
    if count > 3:
        violations.append(violation("MED", "em_dash", f"{count} total em dashes found (showing first 3 above)"))
    return violations


def _expected_name_from_profile():
    """Read the candidate name from the profile.md Identity section. Returns None if not found."""
    # Resolve profile.md relative to this script's location
    here = os.path.dirname(os.path.abspath(__file__))
    profile_path = os.path.join(here, "..", "..", "candidate_context", "profile.md")
    try:
        with open(profile_path) as f:
            for line in f:
                # Match "Name: Something" at the start of a line
                m = re.match(r"^\s*Name:\s*(.+?)\s*$", line)
                if m:
                    return m.group(1).strip()
    except (FileNotFoundError, OSError):
        pass
    return None


def check_name(lines):
    """Flag incorrect name formatting on the resume H1.

    Looks up the expected name from config/profile.md. Flags:
      - First name or surname duplicated (e.g., "Smith Smith")
      - H1 does not match the profile name exactly
    If profile.md is missing, falls back to detecting any duplicated word in the H1.
    """
    violations = []
    expected = _expected_name_from_profile()

    for i, line in enumerate(lines):
        if line.startswith("# "):
            name = line[2:].strip()
            # Always flag duplicated words regardless of profile
            words = name.split()
            if len(words) >= 2:
                lower = [w.lower() for w in words]
                for j in range(len(lower) - 1):
                    if lower[j] == lower[j + 1]:
                        violations.append(
                            violation("HIGH", "wrong_name", f'Duplicated name word in H1: "{name}"', i + 1)
                        )
                        break
            # If we know the expected name from profile, enforce exact match
            if expected and name != expected:
                violations.append(
                    violation("HIGH", "wrong_name", f'H1 should be "{expected}" (from profile.md), not "{name}"', i + 1)
                )
            break
    return violations


# ── Main check function ───────────────────────────────────────────────────────


def check_violations(filepath):
    """
    Run all checks on a resume file. Returns list of violation dicts.
    """
    try:
        with open(filepath, encoding="utf-8") as f:
            raw = f.read()
    except FileNotFoundError:
        return [violation("HIGH", "file_missing", f"File not found: {filepath}")]

    if not raw.strip():
        return [violation("HIGH", "empty_file", "Resume file is empty (0 bytes of content)")]

    lines = raw.splitlines()
    sections = parse_sections(lines)
    role_blocks = parse_role_blocks(lines)

    all_violations = []

    # Section-level checks
    all_violations += check_core_competencies(sections)
    all_violations += check_summary(sections)
    all_violations += check_length(lines)
    all_violations += check_em_dashes(lines)
    all_violations += check_name(lines)

    # Role-level checks
    # Primary = the role with the most bullets (not necessarily the first).
    # In resumes where a past employer is the crown jewel (e.g. long Meta tenure
    # followed by brief consulting), the model correctly gives it 8 bullets even
    # though it appears later in reverse-chron order.
    if role_blocks:
        bullet_counts = [sum(1 for _, line in b["lines"] if re.match(r"^- ", line)) for b in role_blocks]
        primary_idx = bullet_counts.index(max(bullet_counts))
    else:
        primary_idx = 0

    for i, block in enumerate(role_blocks):
        is_primary = i == primary_idx
        all_violations += check_role_block(block, is_primary)

    return all_violations


# ── Reporting ─────────────────────────────────────────────────────────────────

SEVERITY_ORDER = {"HIGH": 0, "MED": 1, "LOW": 2}
SEVERITY_COLOR = {"HIGH": "\033[91m", "MED": "\033[93m", "LOW": "\033[94m"}
RESET = "\033[0m"


def report(filepath, violations, use_color=True):
    high = [v for v in violations if v["severity"] == "HIGH"]
    med = [v for v in violations if v["severity"] == "MED"]
    low = [v for v in violations if v["severity"] == "LOW"]

    print(f"\nRESUME: {filepath}")
    if not violations:
        ok = "\033[92mPASS\033[0m" if use_color else "PASS"
        print(f"  {ok} — No violations found")
        return

    total = len(violations)
    print(f"  VIOLATIONS ({total}): {len(high)} HIGH, {len(med)} MED, {len(low)} LOW")
    for v in sorted(violations, key=lambda x: SEVERITY_ORDER[x["severity"]]):
        sev = v["severity"]
        color = SEVERITY_COLOR.get(sev, "") if use_color else ""
        loc = f" (line {v['line']})" if "line" in v else ""
        print(f"  {color}[{sev}]{RESET} {v['rule']}: {v['detail']}{loc}")


def scan_folder(folder):
    """Find all tailored_resume_DRAFT.md files under folder (non-recursive into _DONE)."""
    results = []
    for root, dirs, files in os.walk(folder):
        # Don't scan _DONE for baseline comparison (those are old files)
        dirs[:] = [d for d in dirs if d != "_DONE"]
        for f in files:
            if f == "tailored_resume_DRAFT.md":
                results.append(os.path.join(root, f))
    return sorted(results)


# ── Entry point ───────────────────────────────────────────────────────────────


def main():
    use_json = "--json" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]

    if not args:
        print(f"Usage: {sys.argv[0]} <resume.md|folder> [--json]")
        sys.exit(1)

    targets = []
    for arg in args:
        if os.path.isdir(arg):
            found = scan_folder(arg)
            if not found:
                print(f"No tailored_resume_DRAFT.md files found under {arg}")
            targets.extend(found)
        elif os.path.isfile(arg):
            targets.append(arg)
        else:
            print(f"Not found: {arg}")

    if not targets:
        sys.exit(1)

    all_results = {}
    any_high = False

    for filepath in targets:
        viols = check_violations(filepath)
        all_results[filepath] = viols
        if any(v["severity"] == "HIGH" for v in viols):
            any_high = True

    if use_json:
        print(json.dumps(all_results, indent=2))
    else:
        use_color = sys.stdout.isatty()
        for filepath, viols in all_results.items():
            report(filepath, viols, use_color=use_color)

        # Summary line when scanning multiple files
        if len(targets) > 1:
            print(f"\nSCANNED: {len(targets)} resume(s)")
            total_high = sum(1 for v in all_results.values() for viol in v if viol["severity"] == "HIGH")
            clean = sum(1 for v in all_results.values() if not v)
            print(f"CLEAN: {clean}  WITH HIGH VIOLATIONS: {total_high}")

    sys.exit(1 if any_high else 0)


if __name__ == "__main__":
    main()
