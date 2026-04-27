# Scorer Role-Shape Mismatch Reduction — Implementation Plan

## Issue(s)
- #276 — Penalize role-shape mismatches (seniority, IC-vs-manager) against profile

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce false-positive rate in the scorer's 5–6 band by ≥60% on the operator's hand-graded pool, without dropping any previously-applied job below the apply threshold (≥7) or any operator-marked legit-shape sample below 6.

**Architecture:** Tracked code changes are minimal and field-agnostic — one new abstract section in `config/roles/job_scorer.md` plus a new field-agnostic test file. All operator-specific role-shape signal lives in the operator's gitignored `profile.md` (`## Title Calibration Notes` and an optional `## Role-Shape Calibration` section) and `prefilter_rules.yaml` (narrow level-word patterns). Locus split: title-deterministic = prefilter; JD-content = profile + prompt. See `docs/superpowers/specs/2026-04-25-scorer-role-shape-design.md` for design rationale.

**Tech Stack:** Python 3.12, FastAPI/Jinja2 (untouched here), SQLite, aichat-ng + OpenRouter (DeepSeek v3.2 for scoring), pytest, ruff, mypy.

**Reference paths used throughout:**
- Operator stack on docker.lan: `/opt/stacks/findajob-{operator-stack}/state/`
- Operator's gitignored profile: `state/candidate_context/profile.md`
- Operator's gitignored prefilter rules: `state/config/prefilter_rules.yaml`
- Operator's pipeline DB: `state/data/pipeline.db` (read via `sudo -u lad sqlite3 ...` per memory `feedback_docker_lan_db_query`)

---

## Task 1: Branch + working-state setup

**Files:**
- Create branch: `feat/276-scorer-role-shape`
- Verify: clean working tree before and after

- [ ] **Step 1: Confirm clean tree on main**

Run:
```bash
cd <repo-root> && git status --short
```
Expected: empty output (clean tree).

- [ ] **Step 2: Fetch origin and branch off origin/main**

Per memory `feedback_git_branch_off_origin` (local main can drift via squash-merge; always branch off origin/main):

Run:
```bash
git fetch origin && git checkout -b feat/276-scorer-role-shape origin/main
```
Expected: `Switched to a new branch 'feat/276-scorer-role-shape'`.

- [ ] **Step 3: Verify branch baseline**

Run:
```bash
git log --oneline -3
```
Expected: top commit is the spec commit (`docs(spec): scorer role-shape mismatch reduction (#276)`); branch is from origin/main.

---

## Task 2: Phase 0 — Pull operator config from docker.lan

**Files:**
- Read into Claude's context only (NOT committed): operator's `profile.md`, `prefilter_rules.yaml`, `in_domain_patterns.yaml`
- Output: none on disk

- [ ] **Step 1: Pull operator's profile.md**

Run:
```bash
ssh docker.lan 'sudo -u lad cat /opt/stacks/findajob-{operator-stack}/state/candidate_context/profile.md'
```
Expected: full profile content (PII-bearing — read into context, do not save to disk, do not echo into the plan).

- [ ] **Step 2: Pull operator's prefilter_rules.yaml**

Run:
```bash
ssh docker.lan 'sudo -u lad cat /opt/stacks/findajob-{operator-stack}/state/config/prefilter_rules.yaml'
```
Expected: existing rules — needed to confirm we're adding patterns, not duplicating.

- [ ] **Step 3: Pull operator's in_domain_patterns.yaml**

Run:
```bash
ssh docker.lan 'sudo -u lad cat /opt/stacks/findajob-{operator-stack}/state/config/in_domain_patterns.yaml'
```
Expected: existing in-domain patterns — needed to confirm Stage 2 prefilter behavior won't be perturbed by Stage 1 additions.

- [ ] **Step 4: Read profile sections and note section names that exist**

Identify which of these sections already exist in the operator's profile (write the list to scratch — not to disk):
- `## Excluded Categories`
- `## Title Calibration Notes`
- `## Role-Shape Calibration` (likely missing — we'll add)
- `## Career Summary`
- `## Employer History`

This list informs the wording of the new scorer prompt section in Task 5 (the prompt only references sections that actually exist in the operator's profile).

---

## Task 3: Phase 0 — Extract baseline samples from operator DB

**Files:**
- Create: `tmp/role_shape_hand_grade_pool.csv`
- Create: `tmp/role_shape_baseline.csv`

- [ ] **Step 1: Confirm jobs and audit_log schemas**

Run:
```bash
ssh docker.lan 'sudo -u lad sqlite3 /opt/stacks/findajob-{operator-stack}/state/data/pipeline.db ".schema jobs"' | head -40
ssh docker.lan 'sudo -u lad sqlite3 /opt/stacks/findajob-{operator-stack}/state/data/pipeline.db ".schema audit_log"'
```
Expected: column list. Confirm `audit_log` uses `field_changed`/`new_value`/`changed_at` (per the schema dump captured during the brainstorming session — not `field`/`new_value`/`ts`).

- [ ] **Step 2: Dump the 132+64 hand-grade pool**

Run a single ssh-piped query:
```bash
ssh docker.lan "sudo -u lad sqlite3 -header -separator $'\t' /opt/stacks/findajob-{operator-stack}/state/data/pipeline.db \"
SELECT id AS job_id, source, fingerprint, title, company, location, relevance_score,
       SUBSTR(COALESCE(jd_text,''), 1, 2000) AS jd_first_2000,
       score_status, ai_notes
FROM jobs
WHERE stage='scored' AND relevance_score IN (5,6)
ORDER BY relevance_score DESC, source, ingested_at DESC;
\"" > tmp/role_shape_hand_grade_pool.csv
```
Expected: ~196 rows (132 score-6 + 64 score-5). Verify with `wc -l tmp/role_shape_hand_grade_pool.csv` (should be 197 with header).

- [ ] **Step 3: Dump the stratified baseline + applied set**

Same ssh-piped pattern. Two parts unioned. Apply the recipe directly — don't try to be clever with random row selection in SQLite (use `ORDER BY RANDOM() LIMIT N` per cell, then UNION):
```bash
ssh docker.lan "sudo -u lad sqlite3 -header -separator $'\t' /opt/stacks/findajob-{operator-stack}/state/data/pipeline.db \"
WITH applied AS (
  SELECT j.id AS job_id, j.source, j.fingerprint, j.title, j.company, j.location,
         j.relevance_score,
         SUBSTR(COALESCE(j.jd_text,''), 1, 2000) AS jd_first_2000,
         j.score_status, j.ai_notes,
         1 AS in_applied,
         (SELECT MIN(changed_at) FROM audit_log a
            WHERE a.job_id=j.id AND a.field_changed='stage' AND a.new_value='applied') AS applied_date
  FROM jobs j
  WHERE EXISTS (SELECT 1 FROM audit_log a
                  WHERE a.job_id=j.id AND a.field_changed='stage' AND a.new_value='applied')
),
stratified AS (
  SELECT job_id, source, fingerprint, title, company, location, relevance_score,
         jd_first_2000, score_status, ai_notes, 0 AS in_applied, NULL AS applied_date
  FROM (
    SELECT id AS job_id, source, fingerprint, title, company, location, relevance_score,
           SUBSTR(COALESCE(jd_text,''), 1, 2000) AS jd_first_2000,
           score_status, ai_notes,
           ROW_NUMBER() OVER (PARTITION BY source, relevance_score ORDER BY RANDOM()) AS rn
    FROM jobs
    WHERE stage='scored'
      AND relevance_score IS NOT NULL
      AND ingested_at >= datetime('now', '-90 days')
  )
  WHERE rn <= 20
)
SELECT * FROM applied
UNION ALL
SELECT * FROM stratified WHERE job_id NOT IN (SELECT job_id FROM applied);
\"" > tmp/role_shape_baseline.csv
```
Expected: ~700–900 rows. Verify with `wc -l tmp/role_shape_baseline.csv`.

- [ ] **Step 4: Sanity-check distribution**

Run:
```bash
awk -F'\t' 'NR>1 {print $2"\t"$7}' tmp/role_shape_baseline.csv | sort | uniq -c | sort -rn | head -30
```
Expected: distribution shows multiple sources × multiple score bands. Cells with 0 jobs are fine; if any single (source × score) cell dominates >40% of the sample, re-run Step 3 with tighter `rn` limit.

- [ ] **Step 5: Confirm both CSVs are gitignored**

Run:
```bash
git check-ignore tmp/role_shape_hand_grade_pool.csv tmp/role_shape_baseline.csv
```
Expected: both paths echoed back (= ignored). If either passes through, the `tmp/` rule in `.gitignore` is broken — fix before continuing.

---

## Task 4: Phase 1 — Data-first analysis

**Files:**
- Create: `tmp/role_shape_observations.md`

- [ ] **Step 1: Cluster titles in the hand-grade pool**

Run a token-frequency pass over `tmp/role_shape_hand_grade_pool.csv` titles:
```bash
awk -F'\t' 'NR>1 {print tolower($4)}' tmp/role_shape_hand_grade_pool.csv \
  | tr -s '[:space:],/-' '\n' \
  | grep -E '^[a-z]{3,}$' \
  | sort | uniq -c | sort -rn | head -50
```
Expected: ranked token list. Note tokens that suggest role-shape mismatch (e.g., "technician", "junior", "associate", "intern", domain-IC tokens like "firmware", "rtl", "validation").

- [ ] **Step 2: Sample 20–30 mismatch JDs and 5–10 legit-shape JDs**

Open `tmp/role_shape_hand_grade_pool.csv` (use Read tool with `limit:` argument or pipe through `column -ts $'\t'` for legibility).

For 20–30 score-6 jobs whose titles look like role-shape mismatches (per the Phase 1 §1 issue body: DC technicians, IC HW/EE engineers, TPMs, forward-deployed leads), read the `jd_first_2000` field. Note common phrase patterns (IC contribution language: "you'll write", "you'll design", "hands-on with"; vs management language: "you'll lead", "you'll grow the team", "report to"; vs content-depth language: "deep expertise in GPU memory subsystems", "RTL/SystemVerilog", "firmware bring-up").

For 5–10 score-6 jobs whose titles look like legit-shape matches (Director-NPI, Production Manager, Sr PDM, Infrastructure Lead), read their JDs and note the language patterns that distinguish them.

- [ ] **Step 3: Write tmp/role_shape_observations.md**

Use Write tool. File template:
```markdown
# Phase 1 observations — scorer role-shape patterns

**Date:** 2026-04-25 (data extracted from operator's pipeline.db, hand-grade pool of 132+64)

## Title token clusters

[Top 30 tokens from Step 1, with notes on which are role-shape signal]

## Empirical phrase-pairs from JD sampling

### Mismatch signal (score conservatively when JD contains)
- "[exact phrase 1]" — observed in N of N JDs
- "[exact phrase 2]" — ...
[etc — aim for 5–10 phrases]

### Legit-shape signal (score normally when JD contains)
- "[exact phrase 1]" — observed in N of N JDs
[etc]

## Patterns this analysis suggests for the prompt change

[1–2 paragraphs synthesizing what the prompt's "Role-Shape Calibration" section should
reference in the candidate profile, framed abstractly — NO operator-specific titles.]

## Patterns this analysis suggests for the operator's profile.md

[Concrete content for `## Title Calibration Notes` and/or `## Role-Shape Calibration`
section. THIS SECTION CONTAINS OPERATOR-SPECIFIC LANGUAGE — by design, since profile.md
is gitignored. Phrases to be pasted into operator's profile in Task 7.]

## Patterns this analysis suggests for prefilter_rules.yaml

[Concrete regex patterns under `seniority_below_floor` and `clear_career_mismatch`
categories, plus any required `context_suppressors`. Drawn from Phase 1 token
clusters where the title alone unambiguously identifies a mismatch.]
```

- [ ] **Step 4: Confirm tmp/role_shape_observations.md is gitignored**

Run:
```bash
git check-ignore tmp/role_shape_observations.md
```
Expected: path echoed back. Same `tmp/` rule as Task 3 Step 5.

---

## Task 5: Phase 2 — Write the failing test for new prefilter pattern shapes (TDD)

**Files:**
- Create: `tests/test_scorer_role_shape.py`

- [ ] **Step 1: Read existing prefilter test to match patterns**

Run:
```bash
ls tests/ | grep -i prefilter
```
Expected: `test_scorer_prefilter.py` exists. Read it to see how the existing tests construct fixture configs and import from `findajob.config_loader`.

- [ ] **Step 2: Write tests/test_scorer_role_shape.py with failing tests**

Use Write tool. File content:

```python
"""Tests for new role-shape prefilter pattern shapes (#276).

These tests validate the *shape* of patterns we expect operators to add to
their gitignored prefilter_rules.yaml — they do not depend on any specific
operator's actual config. The fixture YAML below uses field-agnostic level-word
patterns; the operator-specific patterns live in their gitignored config.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from findajob import config_loader
from findajob.scorer_prefilter import _hard_reject_match


FIXTURE_PREFILTER_YAML = """
hard_rejects:
  seniority_below_floor:
    - '\\bjunior\\b'
    - '\\bintern\\b'
    - '\\bassociate\\s+(engineer|analyst|developer)\\b'
context_suppressors:
  - '\\bjunior\\s+achievement\\b'
"""


@pytest.fixture
def fixture_prefilter(tmp_path: Path, monkeypatch):
    """Point the loader at a fixture prefilter_rules.yaml under tmp_path."""
    rules_path = tmp_path / "prefilter_rules.yaml"
    rules_path.write_text(FIXTURE_PREFILTER_YAML)
    monkeypatch.setattr(config_loader, "_RULES_PATH", rules_path)
    config_loader._reset_cache()
    yield
    config_loader._reset_cache()


class TestLevelWordPatternsRejectJuniorTitles:
    """Level-word patterns reject titles that clearly indicate sub-target seniority."""

    def test_junior_engineer_rejected(self, fixture_prefilter):
        assert _hard_reject_match("Junior Backend Engineer") is not None

    def test_intern_rejected(self, fixture_prefilter):
        assert _hard_reject_match("Software Engineering Intern") is not None

    def test_associate_engineer_rejected(self, fixture_prefilter):
        assert _hard_reject_match("Associate Data Engineer") is not None

    def test_associate_analyst_rejected(self, fixture_prefilter):
        assert _hard_reject_match("Associate Analyst, Operations") is not None


class TestLevelWordPatternsPreserveSeniorTitles:
    """Same patterns must NOT reject titles using these words in non-junior senses."""

    def test_senior_director_preserved(self, fixture_prefilter):
        # "senior" is not in the reject list; this test guards against accidental over-match.
        assert _hard_reject_match("Senior Director, Engineering") is None

    def test_associate_vice_president_preserved(self, fixture_prefilter):
        # "associate" is in the reject list but only the (engineer|analyst|developer) variant.
        # "Associate Vice President" must NOT match.
        assert _hard_reject_match("Associate Vice President, Operations") is None

    def test_junior_achievement_director_preserved_via_suppressor(self, fixture_prefilter):
        # "Junior" appears, but "Junior Achievement" is a context_suppressor (it's a
        # nonprofit name, not a seniority signal). The reject is canceled.
        assert _hard_reject_match("Director, Junior Achievement Partnerships") is None
```

- [ ] **Step 3: Run the new tests and verify they fail**

Run:
```bash
uv run pytest tests/test_scorer_role_shape.py -v
```
Expected: all 7 tests run; `TestLevelWordPatternsRejectJuniorTitles` fails (no patterns yet) — actually wait. The fixture YAML *does* contain the patterns. So the tests should PASS on the first run. This is the verification that the fixture mechanics work.

If any test fails, debug:
- Fixture not being applied → check `monkeypatch.setattr` and `_reset_cache` calls
- Pattern not matching → eyeball the regex via `python -c "import re; print(re.search(r'\\bjunior\\b', 'Junior Backend Engineer'))"`

If all 7 tests pass, the test file is doing what we want: verifying the *shape* of the new patterns is sound. Move on.

- [ ] **Step 4: Commit the test file**

```bash
git add tests/test_scorer_role_shape.py
git commit -m "$(cat <<'EOF'
test(scorer): add role-shape prefilter pattern shape tests (#276)

Field-agnostic tests guarding the level-word + context-suppressor pattern
shapes operators are expected to use in their gitignored prefilter_rules.yaml.
No operator-specific titles in the corpus.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Phase 2 — Add abstract Role-Shape Calibration section to scorer prompt

**Files:**
- Modify: `config/roles/job_scorer.md` (insert new section between CANDIDATE-TOKEN CALIBRATION and CROSS-INDUSTRY RECOGNITION)

- [ ] **Step 1: Read the current scorer prompt to confirm insertion point**

Run:
```bash
grep -n "^## " config/roles/job_scorer.md
```
Expected: line numbers for each `## ` heading. Identify the line immediately before `## CROSS-INDUSTRY RECOGNITION`.

- [ ] **Step 2: Insert the Role-Shape Calibration section**

Use Edit tool. Insert this section *after* the closing `---` of `## CANDIDATE-TOKEN CALIBRATION` and *before* `## CROSS-INDUSTRY RECOGNITION`:

```markdown
## ROLE-SHAPE CALIBRATION

Beyond the title (which CANDIDATE-TOKEN CALIBRATION above handles), the JD content
describes the **shape** of the role — IC contribution work, management of others,
customer-facing technical advocacy, content-depth requirements. When the title alone
is ambiguous, the JD's description of contribution shape is the deciding signal.

Read the profile sections that name the candidate's role-shape preferences:
`## Title Calibration Notes`, `## Role-Shape Calibration` (if present), and the
seniority signal in `## Career Summary` and `## Employer History`. Profile content
is the source of truth — never infer shape preferences not stated in the profile.

Apply these rules:

1. If the profile names a leadership shape (years of management, span of leadership,
   founded-orgs language), and the JD describes pure-IC contribution work below the
   level the profile is targeting, score conservatively — a title token the candidate
   has held in the past is not enough.

2. If the profile names a contribution-depth signal (specific technical depth or
   practice area the candidate has or lacks), and the JD describes work at a different
   depth or adjacency, score conservatively.

3. If the profile is silent on shape, apply standard scoring without a shape-based
   adjustment.

This calibration applies *after* HARD REJECT RULES and TIER 1 EXCEPTION but *before*
the JD-absent rules.

---
```

- [ ] **Step 3: Verify the edit didn't break the file structure**

Run:
```bash
grep -c "^## " config/roles/job_scorer.md
```
Expected: section count is now 1 higher than before. Spot-check the new section appears at the right place:
```bash
grep -n "^## " config/roles/job_scorer.md
```

- [ ] **Step 4: Generalization gate — inspect for enumerated titles/categories**

Run:
```bash
git diff config/roles/job_scorer.md | grep -i -E '\b(tpm|director|manager|engineer|technician|npi|hardware|software|gpu)\b' | grep -v '^-'
```
Expected: ZERO matches. If any of those tokens appear in the diff (added lines), the section is leaking domain vocabulary — rewrite to abstract phrasing.

- [ ] **Step 5: Commit**

```bash
git add config/roles/job_scorer.md
git commit -m "$(cat <<'EOF'
feat(scorer): add Role-Shape Calibration section to job_scorer prompt (#276)

Field-agnostic section that directs the scorer to penalize JD-described
contribution shapes (IC work, content depth) that conflict with the
candidate's profile-stated leadership/depth signal, when the title token
alone is ambiguous. Profile is the source of truth; the prompt names no
specific titles, role-categories, or industries.

See docs/superpowers/specs/2026-04-25-scorer-role-shape-design.md for design
rationale; see profile.md (gitignored) for operator-specific calibration.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Phase 2 — Apply operator-side profile and prefilter edits on docker.lan

**Files:**
- Edit on docker.lan (operator's gitignored config; not committed):
  - `/opt/stacks/findajob-{operator-stack}/state/candidate_context/profile.md`
  - `/opt/stacks/findajob-{operator-stack}/state/config/prefilter_rules.yaml`

- [ ] **Step 1: Build the new profile content from Phase 1 observations**

Open `tmp/role_shape_observations.md` and read the "Patterns this analysis suggests for the operator's profile.md" section. This contains the concrete language to paste in.

- [ ] **Step 2: Apply profile edits via /config/ web UI OR direct ssh edit**

**Option A (preferred — uses the in-app editor):**
1. Open `http://docker.lan:8090/config/` in browser.
2. Click into `candidate_context/profile.md`.
3. Append/edit the `## Title Calibration Notes` section with the role-shape disambiguators from `tmp/role_shape_observations.md`.
4. Optionally add a new `## Role-Shape Calibration` section if Title Calibration becomes too long.
5. Save.

**Option B (direct ssh edit, if /config/ unavailable):**
```bash
ssh docker.lan
sudo -u lad nano /opt/stacks/findajob-{operator-stack}/state/candidate_context/profile.md
# paste edits, save
```

- [ ] **Step 3: Apply prefilter rule edits**

Same pattern. Add the new `seniority_below_floor` and `clear_career_mismatch` categories from `tmp/role_shape_observations.md`'s "Patterns this analysis suggests for prefilter_rules.yaml" section. Add any required `context_suppressors`.

Verify the YAML is valid:
```bash
ssh docker.lan "sudo -u lad python3 -c \"import yaml; print(yaml.safe_load(open('/opt/stacks/findajob-{operator-stack}/state/config/prefilter_rules.yaml')))\"" | head -20
```
Expected: parsed dict prints without error.

- [ ] **Step 4: Verify config loads cleanly inside the container**

Run:
```bash
ssh docker.lan 'sudo -u lad docker exec findajob-{operator-stack}-scheduler-1 python3 -c "from findajob.config_loader import load_hard_reject_rules; r, s = load_hard_reject_rules(); print(\"hard_rejects:\", r.pattern[:200]); print(\"suppressors:\", (s.pattern[:200] if s else None))"'
```
Expected: both patterns print without raising; new patterns appear in output.

- [ ] **Step 5: No commit (operator-side configs are gitignored)**

Verify nothing pending in the repo:
```bash
git status --short
```
Expected: empty output.

---

## Task 8: Phase 3 — Re-score the baseline with new configs

**Files:**
- Create: `tmp/role_shape_rescore.csv`

- [ ] **Step 1: Build the re-score script**

Use Write tool to create `tmp/rescore_role_shape.py` (gitignored, throwaway):

```python
"""Throwaway re-score script for #276 verification.

Reads tmp/role_shape_baseline.csv and tmp/role_shape_hand_grade_pool.csv,
calls findajob.scoring.score_job for each row, writes new scores + deltas.

Runs INSIDE the container (so it sees the new prompt + profile + prefilter):
    docker exec findajob-{operator-stack}-scheduler-1 python /app/tmp/rescore_role_shape.py
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

from findajob.scoring import score_job, _build_feedback_block
from findajob.paths import BASE


def main():
    profile = Path(BASE, "candidate_context", "profile.md").read_text()
    feedback = _build_feedback_block()

    inputs = [
        Path(BASE, "tmp", "role_shape_hand_grade_pool.csv"),
        Path(BASE, "tmp", "role_shape_baseline.csv"),
    ]
    out_path = Path(BASE, "tmp", "role_shape_rescore.csv")

    seen: set[str] = set()
    rows_out: list[dict] = []

    for in_path in inputs:
        if not in_path.exists():
            print(f"WARN: {in_path} not found, skipping", file=sys.stderr)
            continue
        with in_path.open() as f:
            reader = csv.DictReader(f, delimiter="\t")
            for row in reader:
                jid = row["job_id"]
                if jid in seen:
                    continue
                seen.add(jid)

                old_score = int(row["relevance_score"]) if row.get("relevance_score") else None
                result, latency_ms = score_job(
                    title=row["title"],
                    company=row["company"],
                    location=row.get("location") or "",
                    jd_text=row.get("jd_first_2000") or "",
                    candidate_profile=profile,
                    feedback_block=feedback,
                )
                new_score = result.get("relevance_score")
                rows_out.append({
                    "job_id": jid,
                    "source": row.get("source"),
                    "title": row["title"],
                    "company": row["company"],
                    "old_score": old_score,
                    "new_score": new_score,
                    "delta": (new_score - old_score) if (old_score is not None and new_score is not None) else None,
                    "in_applied": row.get("in_applied", "0"),
                    "in_hand_grade_pool": "1" if "hand_grade" in str(in_path) else "0",
                    "old_status": row.get("score_status"),
                    "new_status": result.get("score_status"),
                    "latency_ms": latency_ms,
                })
                print(f"{jid}\t{old_score}\t{new_score}", file=sys.stderr)

    with out_path.open("w") as f:
        writer = csv.DictWriter(
            f, fieldnames=list(rows_out[0].keys()), delimiter="\t"
        )
        writer.writeheader()
        writer.writerows(rows_out)

    print(f"Wrote {len(rows_out)} rows to {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Copy the script + input CSVs to a host scratch path on docker.lan**

`state/` bind mounts are: `data, config, aichat_ng, candidate_context, companies, .backups` (per `CLAUDE.md` §"Container Context"). There is no `state/tmp/` bind mount, so we use `/tmp/role_shape/` on the host and add it as a `-v` mount in the docker run in Step 3. Per memory `feedback_scp_quiet`, use `scp -q`:

```bash
ssh docker.lan 'sudo -u lad mkdir -p /tmp/role_shape && sudo -u lad chmod 777 /tmp/role_shape'
scp -q tmp/rescore_role_shape.py tmp/role_shape_baseline.csv tmp/role_shape_hand_grade_pool.csv docker.lan:/tmp/role_shape/
ssh docker.lan 'ls -la /tmp/role_shape/'
```
Expected: three files visible.

- [ ] **Step 3: Build the test image on the laptop and ship it to docker.lan**

The running scheduler container has the published `:latest` image, which does not yet contain this branch's `config/roles/job_scorer.md` edit. Build a throwaway image off the current branch and load it on docker.lan:

```bash
cd <repo-root>
docker build -t findajob:role-shape-test .
docker save findajob:role-shape-test | ssh docker.lan 'sudo -u lad docker load'
```
Expected: `Loaded image: findajob:role-shape-test`.

- [ ] **Step 4: Run the re-score in a one-shot container with operator state mounted**

```bash
ssh docker.lan 'sudo -u lad docker run --rm \
  -v /opt/stacks/findajob-{operator-stack}/state/data:/app/data \
  -v /opt/stacks/findajob-{operator-stack}/state/candidate_context:/app/candidate_context \
  -v /opt/stacks/findajob-{operator-stack}/state/config:/app/config \
  -v /opt/stacks/findajob-{operator-stack}/state/aichat_ng:/app/.config/aichat_ng \
  -v /tmp/role_shape:/app/tmp \
  -e JSP_BASE=/app \
  findajob:role-shape-test python /app/tmp/rescore_role_shape.py 2>&1 | tee /tmp/role_shape/rescore.log'
```
Expected: ~700–900 lines of `job_id\told\tnew` on stderr; final line `Wrote N rows to /app/tmp/role_shape_rescore.csv`. Total runtime ~10–20 minutes at deepseek-v3.2 throughput.

If the run fails because `aichat-ng` cannot reach OpenRouter: confirm `OPENROUTER_API_KEY` is in the operator's stack `data/.env` (mounted in via the data bind) and that the container's network can reach the API. Per the brainstorming session note, OpenRouter keys were rotated 2026-04-25 — verify the current key works with a quick `aichat-ng -m openrouter:google/gemini-3-flash-preview "ping"` from inside the container.

- [ ] **Step 5: Pull the rescore CSV back to the laptop**

```bash
scp -q docker.lan:/tmp/role_shape/role_shape_rescore.csv tmp/
wc -l tmp/role_shape_rescore.csv
```
Expected: ~700–900 rows (1 header + N data).

---

## Task 9: Phase 4 — Verify acceptance gates

**Files:**
- Create: `tmp/role_shape_gate_report.md` (summary of gate results)

- [ ] **Step 1: Compute gate [b] — Hard floor: every applied job stays ≥7**

Run:
```bash
awk -F'\t' 'NR==1 {for(i=1;i<=NF;i++) c[$i]=i; next}
            $c["in_applied"]=="1" && $c["new_score"]+0 < 7 {print $c["job_id"], $c["title"], $c["old_score"], $c["new_score"]}' \
  tmp/role_shape_rescore.csv
```
Expected: ZERO output rows. Any output row is a hard-floor failure — stop and iterate Phase 2.

- [ ] **Step 2: Compute gate [a] — Primary objective: ≥60% of hand-grade-pool mismatches drop to ≤4**

The hand-grade pool is in `tmp/role_shape_hand_grade_pool.csv` (all 132+64). The legit-shape ~12% subset will be identified by hand in Step 3. For now, treat the entire hand-grade pool as "candidate mismatches" and compute the drop rate:

```bash
awk -F'\t' 'NR==1 {for(i=1;i<=NF;i++) c[$i]=i; next}
            $c["in_hand_grade_pool"]=="1" {
              total++;
              if ($c["new_score"]+0 <= 4) dropped++;
            }
            END {printf "Total: %d, Dropped to ≤4: %d (%.1f%%)\n", total, dropped, 100*dropped/total}' \
  tmp/role_shape_rescore.csv
```
Expected output: `Total: 196, Dropped to ≤4: N (XX.X%)`. Target: XX.X >= the 88% mismatch portion × 60% = ~53% overall (since the 12% legit-shape jobs should NOT drop). Adjust expectation as Step 3 refines.

- [ ] **Step 3: Hand-spot-check the legit-shape subset (gate [c])**

Read `tmp/role_shape_rescore.csv` (the rows where `in_hand_grade_pool=1`) and sort by `new_score`. Find rows where `new_score >= 6` AND title pattern matches the legit-shape categories the issue body names: Director-NPI, Production Manager, Sr PDM, Infrastructure Lead, Ops/Program Manager. These should mostly stay ≥6.

For any row that previously was score-6 AND has a legit-shape title pattern AND now scores <6: this is a soft-floor failure. Investigate the JD content to decide if the new prompt is correctly identifying it as not-a-fit (genuine new info) or incorrectly downgrading (false-negative regression).

- [ ] **Step 4: Compute gate [d] — Per (source × score-band) drift**

```bash
awk -F'\t' 'NR==1 {for(i=1;i<=NF;i++) c[$i]=i; next}
            $c["delta"]!="" {
              key=$c["source"]"\t"$c["old_score"];
              total[key]++;
              if ($c["delta"]+0 <= -3) dropped3plus[key]++;
            }
            END {for(k in total) printf "%s\t%d\t%d\t%.1f%%\n", k, total[k], dropped3plus[k]+0, 100*(dropped3plus[k]+0)/total[k]}' \
  tmp/role_shape_rescore.csv | sort
```
Expected: each (source × old_score) cell prints with N, drop-≥3 count, percentage. Investigate any cell where percentage > 50% AND old_score >= 7 (those represent jobs the operator might want to apply to, dropping unexpectedly).

- [ ] **Step 5: Compute gate [e] — Generalization (zero enumerated terms in tracked diff)**

```bash
git diff origin/main...HEAD -- config/roles/job_scorer.md | \
  grep -E '^\+' | \
  grep -i -E '\b(tpm|director|manager|engineer|technician|npi|hardware|software|gpu|sales|nurse|teacher|case\s+manager)\b' | \
  grep -v '^+++ ' | head
```
Expected: zero matches. Any match means the prompt section leaks domain vocabulary — rewrite.

- [ ] **Step 6: Write tmp/role_shape_gate_report.md**

Use Write tool. Capture the results of all 5 gates with verdict (PASS / FAIL / NEEDS-INVESTIGATION) and counts. This is the durable record of the verification pass.

- [ ] **Step 7: Decision point**

If all 5 gates PASS: proceed to Task 11.

If any gate FAILS: proceed to Task 10 (iteration). Hard ceiling: 3 iterations of Task 10. After the 3rd failed iteration, stop and re-scope (the issue may not be reachable via prompt + profile alone).

---

## Task 10: Iteration loop (executed only on Task 9 gate failure; max 3 times)

**Files:**
- Modify: same surfaces as Tasks 6 + 7 (scorer prompt, profile, prefilter rules)

- [ ] **Step 1: Diagnose which gate failed and why**

From the Step 6 report in Task 9, identify the gate that failed. For each failure mode:

| Gate failed | Likely cause | Iteration target |
|---|---|---|
| [a] False-pos drop too low (<60%) | Prompt section too vague or profile content insufficient | Tighten profile `## Title Calibration Notes` content; tighten prompt's instruction strength |
| [b] Applied jobs dropping below 7 | Profile content too aggressive in penalizing IC work | Loosen profile's seniority floor language; check whether feedback_log clusters are over-firing |
| [c] Legit-shape jobs dropping below 6 | Prefilter pattern over-matching OR profile overcorrection | Add `context_suppressors` to prefilter; soften profile language |
| [d] Source-specific drift | Source-specific title format quirk hitting new pattern | Add source-specific `context_suppressor` |
| [e] Tracked diff leaks domain vocab | Prompt section drifted from abstract phrasing | Rewrite prompt section to reference profile sections only |

- [ ] **Step 2: Edit the relevant surface**

If profile or prefilter: re-run Task 7 steps with adjusted content.
If scorer prompt: re-run Task 6 steps with adjusted phrasing. Amend the Task 6 commit (this is local history before PR open — amending is appropriate).

- [ ] **Step 3: Re-run Task 8 (re-score) and Task 9 (verify)**

Note iteration count in `tmp/role_shape_gate_report.md`. After 3 failed iterations, stop and escalate.

---

## Task 11: Update CHANGELOG and prepare PR

**Files:**
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Read current CHANGELOG**

Run:
```bash
head -30 CHANGELOG.md
```
Expected: `## [Unreleased]` section near top with `### Added` / `### Changed` / `### Fixed` subsections.

- [ ] **Step 2: Add entry under [Unreleased] → Changed**

Use Edit tool. Add this line under `### Changed` in `[Unreleased]`:

```
- Scorer prompt: added "Role-Shape Calibration" section that directs the scorer to penalize JD-described contribution shapes (IC work, content depth) that conflict with the candidate's profile-stated leadership/depth signal, when the title token alone is ambiguous (#276)
```

If `### Changed` doesn't exist under `[Unreleased]`, create it.

- [ ] **Step 3: Commit CHANGELOG update**

```bash
git add CHANGELOG.md
git commit -m "$(cat <<'EOF'
chore(changelog): add #276 Role-Shape Calibration entry

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 4: Push branch and open PR**

```bash
git push -u origin feat/276-scorer-role-shape
```

Then open PR:
```bash
gh pr create --title "feat(scorer): add Role-Shape Calibration section to job_scorer prompt (#276)" --body "$(cat <<'EOF'
## Summary
- Adds a new field-agnostic "Role-Shape Calibration" section to `config/roles/job_scorer.md` that directs the scorer to penalize JD-described contribution shapes that conflict with the candidate's profile-stated leadership/depth signal, when the title token alone is ambiguous.
- Adds `tests/test_scorer_role_shape.py` covering the level-word + context-suppressor pattern shapes operators are expected to use in their gitignored `prefilter_rules.yaml`.
- Closes #276.

## Operator-side migration (one-time, per stack)

After pulling the new image, each operator must apply gitignored config edits before the change has effect:

1. **Profile** — `candidate_context/profile.md`: enrich `## Title Calibration Notes` with role-shape disambiguators specific to your field. Optionally add a `## Role-Shape Calibration` section. The new prompt section reads both.
2. **Prefilter** — `config/prefilter_rules.yaml`: add narrow level-word patterns (`\bjunior\b`, `\bintern\b`, `\bassociate\s+(engineer|analyst|developer)\b`, etc.) under a `seniority_below_floor` category. Add any field-specific `context_suppressors` that legitimately override these patterns.

Both edits can be made via the in-app `/config/` editor or directly on the bind-mounted state directory.

See `docs/superpowers/specs/2026-04-25-scorer-role-shape-design.md` for the design rationale and the locus-split rule (title-deterministic = prefilter; JD-content = profile + prompt).

## Verification

- All gates from §7 of the spec passed on the operator's stack:
  - ≥60% of hand-grade-pool mismatch jobs dropped to ≤4
  - Every previously-applied job re-scores ≥7 (hard floor)
  - Hand-graded legit-shape jobs stay ≥6 (soft floor)
  - No (source × score-band) cell shows >50% of jobs dropping ≥3 points unintentionally
  - Tracked diff contains zero enumerated titles, role-categories, or industry vocabulary

## Test plan
- [ ] CI green: ruff check, ruff format --check, mypy, pytest (per memory `feedback_ruff_format_check`)
- [ ] Operator-side migration applied to operator stack and Alice stack at deploy
- [ ] Post-deploy spot-check: next ingestion's score-5/6 distribution shows the expected shift

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 5: Wait for CI; address feedback**

Run:
```bash
gh pr checks
```
Expected: all checks green. If ruff or pytest fails, fix the underlying issue (do NOT skip hooks — per CLAUDE.md "no --no-verify").

---

## Task 12: Merge + close #276 + post-merge ops

**Files:**
- None (operations on board + deploy)

- [ ] **Step 1: Merge the PR**

When CI green and review passes:
```bash
gh pr merge --squash --delete-branch
```

- [ ] **Step 2: Verify board state**

Run:
```bash
gh issue view 276 --json state,projectItems
```
Expected: state=CLOSED, project Status=Done (auto-moved by GitHub).

- [ ] **Step 3: Append session notes to #276**

Use `gh issue comment 276` to add a `## Session 2026-04-25` block with:
- Progress: which gates passed, false-positive reduction percentage achieved
- Decisions: any iterations and what they taught
- Next action: nothing required — change is shipped, observe newly-ingested jobs over the next week to confirm in-the-wild behavior

- [ ] **Step 4: Plan the operator-side deploy** (per memory `feedback_deploy_both_stacks`)

The PR's tracked code change ships in the next image (e.g., when `:latest` is rebuilt and pulled to operator + Alice stacks). The operator-side gitignored config changes (profile.md, prefilter_rules.yaml) only need to be applied to the operator stack — Alice will add her own social-work-specific calibration to her own profile when she's ready.

Document the deploy step in the next release-process.md run when the next `:latest` rebuild happens.

- [ ] **Step 5: Append final session notes to tmp/role-shape-tuning-notes.md**

Use Edit/Write tool to append a `### 2026-04-25 (final) — gates passed, PR merged` section capturing the actual gate numbers achieved, anything surprising in the data, and any candidate refinements for future tuning iterations (which feed forward into #150 and #228).

---

## Out of scope (do not do during this plan)

- Building any part of #150 (guided tuning UI)
- Backfilling historical scores (the change applies to newly-ingested jobs only)
- Modifying `src/findajob/scorer_prefilter.py` Python (the existing two-stage mechanics already handle the new patterns)
- Updating Alice's stack with operator-specific role-shape language (she has her own profile)
- Modifying `CLAUDE.md` (the locus-split rule is captured in the spec; promote to CLAUDE.md only if multiple future tunes confirm it as load-bearing)
