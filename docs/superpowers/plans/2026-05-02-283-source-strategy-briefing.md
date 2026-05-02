# #283 source-strategy briefing + profile-grounded source-config emission — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a four-source strategy briefing to the onboarding interview (educational layer in Phase 1, decisional sub-phase 3g) and emit profile-grounded source-config files (`jsearch_queries.txt`, `feed-urls.txt`, `linkedin-alerts.md`) opt-in based on candidate selection. Bundle #215 injector hardening polish.

**Architecture:** Parser (`findajob.onboarding.parser`) gets `jsearch_queries.txt` moved `ALLOWED → OPTIONAL`; `feed-urls.txt` and `linkedin-alerts.md` added as OPTIONAL. Injector (`findajob.onboarding.injector`) gains a generalized optional-staging loop iterating `_OPTIONAL_DESTINATIONS` (voice-samples.md keeps its special-case processing). Prompt (`config/roles/onboarding_interviewer.md`) gains Phase 1 educational source-strategy briefing, sub-phase 3g letter-prefixed source selection, and Phase 5 conditional emission for the three OPTIONAL files. Conditional emission is enforced by the prompt; the parser/injector remain selection-agnostic.

**Tech Stack:** Python 3.13, FastAPI (web layer untouched here), pytest, ruff, mypy. Test pattern: `pytest tests/test_onboarding_*.py` for unit tests; walkthrough corpus replay for prompt verification (`pytest tests/test_walkthrough_harness.py`).

**Spec:** [`docs/superpowers/specs/2026-05-02-283-design.md`](../specs/2026-05-02-283-design.md)

**Issue:** [#283](https://github.com/brockamer/findajob/issues/283) (in progress); bundles [#215](https://github.com/brockamer/findajob/issues/215) hardening polish.

---

## Pre-flight: branch setup

Before Task 1, create a feature branch off `origin/main` (per memory rule "Git — branch off origin/main" — local main drifts from origin/main via squash-merge).

```bash
cd /home/brockamer/Code/findajob
git fetch origin main
git checkout -b feat/283-source-strategy-briefing origin/main
git status
```

Expected: clean working tree on `feat/283-source-strategy-briefing`.

---

## Task 1: Parser changes — move `jsearch_queries.txt` to OPTIONAL; add `feed-urls.txt` + `linkedin-alerts.md`

**Files:**
- Modify: `src/findajob/onboarding/parser.py:17-32`
- Modify: `tests/test_onboarding_parser.py` (the `_CLEAN_BLOCKS` fixture and the `test_allowed_filenames_are_exactly_ten` assertion)

### Steps

- [ ] **Step 1: Read current parser to confirm pre-edit state**

```bash
sed -n '17,35p' src/findajob/onboarding/parser.py
```

Expected: `ALLOWED_FILENAMES` has 10 entries including `jsearch_queries.txt`; `OPTIONAL_FILENAMES` has 1 entry (`voice-samples.md`).

- [ ] **Step 2: Write failing tests for new parser behavior**

Append to `tests/test_onboarding_parser.py`:

```python
def test_jsearch_queries_now_optional_not_in_missing_when_absent() -> None:
    """#283: jsearch_queries.txt moved ALLOWED → OPTIONAL; absence is no longer a 'missing'."""
    partial_blocks = {k: v for k, v in _CLEAN_BLOCKS.items() if k != "jsearch_queries.txt"}
    blob = "\n\n".join(_wrap(n, b) for n, b in partial_blocks.items())
    result = parse_emission(blob)
    assert "jsearch_queries.txt" not in result.missing
    assert result.missing == []  # all 9 remaining ALLOWED present


def test_feed_urls_txt_recognized_as_optional() -> None:
    """#283: feed-urls.txt is a new OPTIONAL filename."""
    blocks = dict(_CLEAN_BLOCKS)
    blocks["feed-urls.txt"] = "https://boards.greenhouse.io/acme\nhttps://jobs.lever.co/example\n"
    blob = "\n\n".join(_wrap(n, b) for n, b in blocks.items())
    result = parse_emission(blob)
    assert "feed-urls.txt" in result.found
    assert result.found["feed-urls.txt"] == "https://boards.greenhouse.io/acme\nhttps://jobs.lever.co/example\n"
    assert result.unknown == []


def test_linkedin_alerts_md_recognized_as_optional() -> None:
    """#283: linkedin-alerts.md is a new OPTIONAL filename."""
    blocks = dict(_CLEAN_BLOCKS)
    blocks["linkedin-alerts.md"] = "# LinkedIn alerts\n- [ ] Step 1\n"
    blob = "\n\n".join(_wrap(n, b) for n, b in blocks.items())
    result = parse_emission(blob)
    assert "linkedin-alerts.md" in result.found
    assert "linkedin-alerts.md" not in result.unknown


def test_all_three_new_optionals_together() -> None:
    """#283: jsearch_queries.txt + feed-urls.txt + linkedin-alerts.md present together — none flagged unknown."""
    blocks = dict(_CLEAN_BLOCKS)
    blocks["feed-urls.txt"] = "https://boards.greenhouse.io/acme\n"
    blocks["linkedin-alerts.md"] = "# LinkedIn alerts\n"
    blob = "\n\n".join(_wrap(n, b) for n, b in blocks.items())
    result = parse_emission(blob)
    assert {"jsearch_queries.txt", "feed-urls.txt", "linkedin-alerts.md"} <= set(result.found.keys())
    assert result.unknown == []
```

Also update the `_CLEAN_BLOCKS` definition at the top of the test file to no longer require `jsearch_queries.txt` for `test_clean_emission_all_required_found`. Keep `jsearch_queries.txt` in `_CLEAN_BLOCKS` for now (the test logic doesn't require it to be in ALLOWED), but update the existing assertion `test_allowed_filenames_are_exactly_ten`:

```python
def test_allowed_filenames_are_exactly_nine() -> None:
    """#283: jsearch_queries.txt moved to OPTIONAL (was 10, now 9 ALLOWED).

    Pre-#283: profile.md, master_resume.md, target_companies.md,
    business_sector_employers_reference.md, jsearch_queries.txt,
    prefilter_rules.yaml, in_domain_patterns.yaml, display_name.txt,
    timezone.txt, ntfy_topic.txt.
    """
    assert len(ALLOWED_FILENAMES) == 9
    assert "jsearch_queries.txt" not in ALLOWED_FILENAMES
    assert "jsearch_queries.txt" in OPTIONAL_FILENAMES
```

Delete the old `test_allowed_filenames_are_exactly_ten` function.

- [ ] **Step 3: Run tests to verify they fail**

```bash
uv run pytest tests/test_onboarding_parser.py -v
```

Expected: 4 new tests fail (the parser hasn't been updated yet); `test_allowed_filenames_are_exactly_nine` fails (still 10 entries).

- [ ] **Step 4: Update `src/findajob/onboarding/parser.py:17-34` with the new tuples**

Replace lines 17-34 with:

```python
ALLOWED_FILENAMES: tuple[str, ...] = (
    "profile.md",
    "master_resume.md",
    "target_companies.md",
    "business_sector_employers_reference.md",
    "prefilter_rules.yaml",
    "in_domain_patterns.yaml",
    "display_name.txt",
    "timezone.txt",
    "ntfy_topic.txt",
)

# Recognized but not required. If present in an emission, the injector
# processes them; if absent, no error and no entry in ParsedEmission.missing.
OPTIONAL_FILENAMES: tuple[str, ...] = (
    "voice-samples.md",
    "jsearch_queries.txt",
    "feed-urls.txt",
    "linkedin-alerts.md",
)

_KNOWN_FILENAMES: frozenset[str] = frozenset(ALLOWED_FILENAMES) | frozenset(OPTIONAL_FILENAMES)
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
uv run pytest tests/test_onboarding_parser.py -v
```

Expected: all parser tests PASS (existing + 4 new + the renamed `test_allowed_filenames_are_exactly_nine`).

- [ ] **Step 6: Commit**

```bash
git add src/findajob/onboarding/parser.py tests/test_onboarding_parser.py
git commit -m "$(cat <<'EOF'
feat(onboarding/parser): #283 — jsearch_queries.txt → OPTIONAL; add feed-urls.txt + linkedin-alerts.md

Conditional emission for source-config files lands in #283 (sections
A/B/C — search queries, ATS feed URLs, LinkedIn-alerts checklist). The
parser becomes selection-agnostic: it parses any of the four OPTIONAL
files when present, no longer flags jsearch_queries.txt as missing
when the candidate's 3g selection skips it.

ALLOWED_FILENAMES drops from 10 to 9 entries. The candidate-facing
discipline (which files to emit per 3g answer) lives in the prompt.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Injector — new OPTIONAL filename mappings + generalized optional-staging loop

**Files:**
- Modify: `src/findajob/onboarding/injector.py:41-64` (the destination tables)
- Modify: `src/findajob/onboarding/injector.py:336-344` (replace hardcoded voice-samples.md branch with a generalized loop over `_OPTIONAL_DESTINATIONS`)
- Modify: `tests/test_onboarding_injector.py` (add tests for new OPTIONAL files + manual-only path)

### Steps

- [ ] **Step 1: Read current injector destination tables and optional-staging loop**

```bash
sed -n '41,64p' src/findajob/onboarding/injector.py
sed -n '336,344p' src/findajob/onboarding/injector.py
```

Expected: `_ALL_DESTINATIONS` lists 9 entries (10 ALLOWED minus ntfy_topic.txt env-merge); `_OPTIONAL_DESTINATIONS` lists `voice-samples.md`. Optional-staging loop hardcodes the voice-samples branch.

- [ ] **Step 2: Write failing tests for new injector behavior**

Append to `tests/test_onboarding_injector.py`:

```python
def test_inject_writes_feed_urls_when_present(tmp_path: Path) -> None:
    """#283 Section B: feed-urls.txt → config/feed_urls.txt (hyphen→underscore)."""
    found = _minimal_found_dict()
    found["feed-urls.txt"] = (
        "https://boards.greenhouse.io/acme\n"
        "https://jobs.lever.co/example\n"
        "https://jobs.ashbyhq.com/zoox\n"
    )
    inject(tmp_path, found, openrouter_api_key="sk-test", skip_smoke_check=True)
    feed_path = tmp_path / "config" / "feed_urls.txt"
    assert feed_path.is_file()
    assert "boards.greenhouse.io/acme" in feed_path.read_text()
    assert "jobs.lever.co/example" in feed_path.read_text()
    assert "jobs.ashbyhq.com/zoox" in feed_path.read_text()


def test_inject_writes_linkedin_alerts_when_present(tmp_path: Path) -> None:
    """#283 Section C: linkedin-alerts.md → candidate_context/linkedin-alerts.md."""
    found = _minimal_found_dict()
    found["linkedin-alerts.md"] = "# LinkedIn alerts\n- [ ] Step 1\n"
    inject(tmp_path, found, openrouter_api_key="sk-test", skip_smoke_check=True)
    alerts_path = tmp_path / "candidate_context" / "linkedin-alerts.md"
    assert alerts_path.is_file()
    assert "LinkedIn alerts" in alerts_path.read_text()


def test_inject_manual_only_path_emits_no_optional_source_config(tmp_path: Path) -> None:
    """#283: candidate picks 'none' (manual only) → no jsearch/feed-urls/linkedin-alerts emitted."""
    found = _minimal_found_dict()
    # No jsearch_queries.txt, no feed-urls.txt, no linkedin-alerts.md
    inject(tmp_path, found, openrouter_api_key="sk-test", skip_smoke_check=True)
    # Sentinel set, ALLOWED files committed, no optional source-config files written
    assert (tmp_path / "data" / ".onboarding-complete").is_file()
    assert not (tmp_path / "config" / "jsearch_queries.txt").is_file()
    assert not (tmp_path / "config" / "feed_urls.txt").is_file()
    assert not (tmp_path / "candidate_context" / "linkedin-alerts.md").is_file()


def test_inject_backs_up_existing_feed_urls_before_overwrite(tmp_path: Path) -> None:
    """#283: re-onboarding via ?mode=rerun backs up existing config/feed_urls.txt."""
    feed_path = tmp_path / "config" / "feed_urls.txt"
    feed_path.parent.mkdir(parents=True, exist_ok=True)
    feed_path.write_text("https://boards.greenhouse.io/oldcompany\n")
    found = _minimal_found_dict()
    found["feed-urls.txt"] = "https://boards.greenhouse.io/newcompany\n"
    result = inject(tmp_path, found, openrouter_api_key="sk-test", skip_smoke_check=True)
    # New content committed
    assert "newcompany" in feed_path.read_text()
    # Old content backed up
    backup_files = list(result.backup_dir.rglob("feed_urls.txt"))
    assert len(backup_files) == 1
    assert "oldcompany" in backup_files[0].read_text()
```

If `_minimal_found_dict()` doesn't already exist in the test file, add this helper near the top of the file (after the imports):

```python
def _minimal_found_dict() -> dict[str, str]:
    """Build the minimum 'found' dict that injector.inject() requires (all 9 ALLOWED present)."""
    return {
        "profile.md": "# Profile\n## Identity\nTest User\n",
        "master_resume.md": "# Resume\n## Contact\nTest User\n",
        "target_companies.md": "## Tier 1 — Active Focus\n- Acme\n",
        "business_sector_employers_reference.md": "## Categories\n### Foo\n- Acme\n",
        "prefilter_rules.yaml": "hard_rejects:\n  spam:\n    - '\\bspam\\b'\n",
        "in_domain_patterns.yaml": "positive:\n  - '\\bbackend\\s+engineer\\b'\n",
        "display_name.txt": "Test User",
        "timezone.txt": "America/Los_Angeles",
        "ntfy_topic.txt": "test-topic-2026",
    }
```

(Inspect the existing test file first — there may already be a similar helper. If so, reuse it.)

- [ ] **Step 3: Run tests to verify they fail**

```bash
uv run pytest tests/test_onboarding_injector.py -v -k "feed_urls or linkedin_alerts or manual_only"
```

Expected: 4 new tests fail (injector hasn't been updated yet — feed-urls.txt and linkedin-alerts.md are in `found` but not staged).

- [ ] **Step 4: Update `_ALL_DESTINATIONS` to remove `jsearch_queries.txt`**

In `src/findajob/onboarding/injector.py`, edit the `_ALL_DESTINATIONS` dict (lines 41-51) by removing the `"jsearch_queries.txt"` entry:

```python
_ALL_DESTINATIONS: dict[str, str] = {
    "profile.md": "candidate_context/profile.md",
    "master_resume.md": "candidate_context/master_resume.md",
    "target_companies.md": "config/target_companies.md",
    "business_sector_employers_reference.md": "config/business_sector_employers_reference.md",
    "prefilter_rules.yaml": "config/prefilter_rules.yaml",
    "in_domain_patterns.yaml": "config/in_domain_patterns.yaml",
    "display_name.txt": "candidate_context/display_name.txt",
    "timezone.txt": "data/timezone",
}
```

- [ ] **Step 5: Update `_OPTIONAL_DESTINATIONS` to add the three new entries**

Replace lines 62-64 with:

```python
# Optional emission filenames -> destination relative path. Processed if
# present in the emission, silently skipped if absent. Backed up the same as
# required destinations.
_OPTIONAL_DESTINATIONS: dict[str, str] = {
    "voice-samples.md": "candidate_context/voice_samples/voice-samples.md",
    "jsearch_queries.txt": "config/jsearch_queries.txt",
    "feed-urls.txt": "config/feed_urls.txt",
    "linkedin-alerts.md": "candidate_context/linkedin-alerts.md",
}
```

- [ ] **Step 6: Replace the hardcoded voice-samples staging branch with a generalized loop**

Find the existing block at lines 336-344 (verify line numbers; they may shift after Step 4's edit):

```python
        # Stage optional files (voice-samples.md, etc.) — clean + redact first
        if "voice-samples.md" in found:
            processed, _redaction_ok = process_voice_samples(found["voice-samples.md"], redact=redact_voice_samples)
            if processed:
                dest = base_root / _OPTIONAL_DESTINATIONS["voice-samples.md"]
                fd, tmp_name = tempfile.mkstemp(prefix=dest.name + ".", suffix=".tmp", dir=str(dest.parent))
                with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
                    fh.write(processed)
                tempfiles.append((tmp_name, dest))
```

Replace with:

```python
        # Stage optional files. voice-samples.md goes through process_voice_samples
        # (clean + LLM-redact); the others (jsearch_queries.txt, feed-urls.txt,
        # linkedin-alerts.md) are plain-write.
        for opt_name, opt_relpath in _OPTIONAL_DESTINATIONS.items():
            if opt_name not in found:
                continue
            body = found[opt_name]
            if opt_name == "voice-samples.md":
                processed, _redaction_ok = process_voice_samples(body, redact=redact_voice_samples)
                if not processed:
                    continue  # voice-samples processing returned empty → skip write
                body = processed
            dest = base_root / opt_relpath
            fd, tmp_name = tempfile.mkstemp(prefix=dest.name + ".", suffix=".tmp", dir=str(dest.parent))
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
                fh.write(body)
            tempfiles.append((tmp_name, dest))
```

- [ ] **Step 7: Update parent-dir-creation block**

The block at line 309-314 ensures parent directories exist for the destinations. It already iterates `_OPTIONAL_DESTINATIONS.items()` checking `if opt_name in found`, so it picks up the new entries automatically. Verify by re-reading:

```bash
sed -n '309,317p' src/findajob/onboarding/injector.py
```

Expected: the loop is generic over `_OPTIONAL_DESTINATIONS` — no edit needed.

- [ ] **Step 8: Run injector tests to verify they pass**

```bash
uv run pytest tests/test_onboarding_injector.py -v
```

Expected: all injector tests PASS, including the 4 new ones. The existing voice-samples tests should still pass because the generalized loop preserves the special-case processing.

- [ ] **Step 9: Run the full onboarding test suite to catch any cross-module regressions**

```bash
uv run pytest tests/test_onboarding_*.py -v
```

Expected: all pass.

- [ ] **Step 10: Commit**

```bash
git add src/findajob/onboarding/injector.py tests/test_onboarding_injector.py
git commit -m "$(cat <<'EOF'
feat(onboarding/injector): #283 — generalize optional-staging loop; add feed-urls.txt + linkedin-alerts.md

Move jsearch_queries.txt from _ALL_DESTINATIONS to _OPTIONAL_DESTINATIONS
(parser change in previous commit moved it ALLOWED → OPTIONAL). Add new
OPTIONAL files: feed-urls.txt → config/feed_urls.txt (Section B),
linkedin-alerts.md → candidate_context/linkedin-alerts.md (Section C).

Replace the hardcoded voice-samples.md staging branch with a single loop
over _OPTIONAL_DESTINATIONS. voice-samples.md keeps its process_voice_samples
special case (clean + LLM-redact); plain-write semantics apply to the
other three. Atomic write + .backups/{UTC-stamp}/ flow unchanged for all
of them.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Injector — emission-consistency warnings

**Files:**
- Modify: `src/findajob/onboarding/injector.py` (add post-commit consistency-check pass)
- Create: `tests/test_onboarding_emission_anomaly.py`

### Steps

- [ ] **Step 1: Write failing test file**

Create `tests/test_onboarding_emission_anomaly.py`:

```python
"""Unit tests for #283 emission-consistency warnings.

These warnings are non-blocking — they log to logs/pipeline.jsonl as
event=onboarding_emission_anomaly so prompt-revision regressions can
be spotted in pipeline logs without failing onboarding.
"""

from __future__ import annotations

import json
from pathlib import Path

from findajob.onboarding.injector import inject

from tests.test_onboarding_injector import _minimal_found_dict  # reuse helper


def _read_pipeline_events(base: Path) -> list[dict]:
    log = base / "logs" / "pipeline.jsonl"
    if not log.is_file():
        return []
    return [json.loads(line) for line in log.read_text().splitlines() if line.strip()]


def test_warning_when_linkedin_alerts_present_without_jsearch_queries(tmp_path: Path) -> None:
    """linkedin-alerts.md cross-references config/jsearch_queries.txt by path —
    if alerts are emitted but queries are not, the cross-reference is broken."""
    found = _minimal_found_dict()
    found["linkedin-alerts.md"] = "# Alerts\nSee config/jsearch_queries.txt\n"
    # Deliberately omit jsearch_queries.txt
    inject(tmp_path, found, openrouter_api_key="sk-test", skip_smoke_check=True)
    events = _read_pipeline_events(tmp_path)
    anomaly = [e for e in events if e.get("event") == "onboarding_emission_anomaly"]
    assert len(anomaly) >= 1
    assert any("linkedin_alerts_without_jsearch_queries" in e.get("kind", "") for e in anomaly)


def test_warning_when_jsearch_queries_emitted_empty(tmp_path: Path) -> None:
    """An empty jsearch_queries.txt (zero query lines after comment-stripping)
    signals prompt-LLM drift — emit warning."""
    found = _minimal_found_dict()
    found["jsearch_queries.txt"] = "# Generated by findajob\n# 3-4 word queries\n"
    inject(tmp_path, found, openrouter_api_key="sk-test", skip_smoke_check=True)
    events = _read_pipeline_events(tmp_path)
    anomaly = [e for e in events if e.get("event") == "onboarding_emission_anomaly"]
    assert any("jsearch_queries_empty" in e.get("kind", "") for e in anomaly)


def test_no_warning_when_both_present_and_nonempty(tmp_path: Path) -> None:
    """Healthy emission: linkedin-alerts.md + jsearch_queries.txt both present, queries non-empty."""
    found = _minimal_found_dict()
    found["jsearch_queries.txt"] = "# Generated\nsenior backend engineer\nplatform engineer\n"
    found["linkedin-alerts.md"] = "# Alerts\nSee queries above\n"
    inject(tmp_path, found, openrouter_api_key="sk-test", skip_smoke_check=True)
    events = _read_pipeline_events(tmp_path)
    anomaly = [e for e in events if e.get("event") == "onboarding_emission_anomaly"]
    assert anomaly == []
```

- [ ] **Step 2: Run test file to verify all three tests fail**

```bash
uv run pytest tests/test_onboarding_emission_anomaly.py -v
```

Expected: 3 tests fail (consistency-check pass not yet implemented).

- [ ] **Step 3: Implement the consistency-check pass in `inject()`**

In `src/findajob/onboarding/injector.py`, add a helper function above `inject()`:

```python
def _emission_consistency_warnings(base_root: Path, found: dict[str, str]) -> None:
    """Log non-blocking warnings to pipeline.jsonl for emission inconsistencies.

    Triggers:
      - linkedin-alerts.md emitted but jsearch_queries.txt absent → broken
        cross-reference in the alerts checklist.
      - jsearch_queries.txt emitted but contains zero non-comment, non-blank
        lines → signals prompt-LLM drift.
    """
    from findajob.utils import log_event  # noqa: PLC0415 — match lazy-import idiom in this file

    if "linkedin-alerts.md" in found and "jsearch_queries.txt" not in found:
        log_event(
            "onboarding_emission_anomaly",
            kind="linkedin_alerts_without_jsearch_queries",
            base_root=str(base_root),
        )

    if "jsearch_queries.txt" in found:
        body = found["jsearch_queries.txt"]
        non_comment_lines = [
            line for line in body.splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        if not non_comment_lines:
            log_event(
                "onboarding_emission_anomaly",
                kind="jsearch_queries_empty",
                base_root=str(base_root),
            )
```

In `inject()`, call the helper after the sentinel write (line 377 — `mark_complete(base_root)`). The block becomes:

```python
        # Finally, the sentinel
        mark_complete(base_root)

        # Non-blocking emission-consistency warnings (#283)
        _emission_consistency_warnings(base_root, found)
```

Make sure the call is INSIDE the `try:` block (so a logging failure rolls back like any other staging failure — though `log_event` is pure file-append and shouldn't raise in practice).

- [ ] **Step 4: Verify `findajob.utils.log_event` writes to `logs/pipeline.jsonl` relative to BASE**

```bash
grep -nE "def log_event" src/findajob/utils.py
```

If `log_event` resolves the log path from `findajob.paths.BASE` (not from `base_root`), the test fixture's `tmp_path` may not match where the log actually goes. Check:

```bash
sed -n "$(grep -nE 'def log_event' src/findajob/utils.py | head -1 | cut -d: -f1),+15p" src/findajob/utils.py
```

If `log_event` uses `BASE` (module-level import), the tests need to monkeypatch `findajob.paths.BASE` or `findajob.utils.BASE`. If it accepts a base path, prefer threading `base_root` through. **Adjust the test fixtures to monkeypatch BASE if needed before Step 5.**

If `log_event` is BASE-relative and not configurable, update the test file's helper:

```python
@pytest.fixture(autouse=True)
def _patch_base(tmp_path: Path, monkeypatch):
    """Force findajob.utils.log_event to write to tmp_path/logs/pipeline.jsonl."""
    monkeypatch.setattr("findajob.utils.BASE", str(tmp_path))
    monkeypatch.setattr("findajob.paths.BASE", str(tmp_path))
    yield
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
uv run pytest tests/test_onboarding_emission_anomaly.py -v
```

Expected: all 3 PASS.

- [ ] **Step 6: Run full onboarding test suite to catch regressions**

```bash
uv run pytest tests/test_onboarding_*.py -v
```

Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add src/findajob/onboarding/injector.py tests/test_onboarding_emission_anomaly.py
git commit -m "$(cat <<'EOF'
feat(onboarding/injector): #283 — non-blocking emission-consistency warnings

Adds post-sentinel sanity checks logged as event=onboarding_emission_anomaly
in pipeline.jsonl. Triggers:

- linkedin-alerts.md present but jsearch_queries.txt absent → the
  alerts checklist's cross-reference to config/jsearch_queries.txt is
  broken.
- jsearch_queries.txt present but contains zero non-comment, non-blank
  lines → signals prompt-LLM drift (the prompt should not have emitted
  an empty queries file).

Non-blocking — onboarding completes regardless. Gives prompt-revision
regressions a tripwire that surfaces in operator-visible logs.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Injector — #215 hardening polish (Fix 1: rollback hole; Fix 2: widen rollback test glob)

**Files:**
- Modify: `src/findajob/onboarding/injector.py` (the staging loop tempfile registration)
- Modify: `tests/test_onboarding_injector.py::test_inject_staging_failure_rolls_back` (widen residue glob)

#215's three fixes per the issue body:
1. Rollback hole between `mkstemp` and `tempfiles.append` — register the tempfile immediately so it's tracked even if the `with os.fdopen` block raises.
2. Rollback test glob is too narrow — widen to catch any `*.tmp` residue across all destination dirs.
3. Multi-word hyphen-joined company names in Tier 1 derivation — handled in Task 11 (prompt-doc caveat, not code).

### Steps

- [ ] **Step 1: Read current staging loop to see the rollback hole**

```bash
sed -n '322,365p' src/findajob/onboarding/injector.py
```

Expected: each `mkstemp + os.fdopen + write` block calls `tempfiles.append((tmp_name, dest))` AFTER the `with` block exits. If `os.fdopen` or `fh.write` raises, the tempfile is created on disk but not in `tempfiles` — the `except` rollback never sees it.

- [ ] **Step 2: Write a failing test that exercises the hole**

Append to `tests/test_onboarding_injector.py`:

```python
def test_inject_rollback_includes_tempfile_when_write_fails_mid_staging(tmp_path: Path, monkeypatch) -> None:
    """#215 Fix 1: rollback must clean up tempfiles even if os.fdopen/write
    raises after mkstemp succeeded but before tempfiles.append."""
    import os
    from unittest.mock import MagicMock

    found = _minimal_found_dict()

    # Patch os.fdopen to raise on the THIRD call (after first 2 staging writes succeed).
    real_fdopen = os.fdopen
    call_count = {"n": 0}

    def fail_third(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 3:
            raise OSError("simulated mid-staging write failure")
        return real_fdopen(*args, **kwargs)

    monkeypatch.setattr(os, "fdopen", fail_third)

    with pytest.raises(OSError):
        inject(tmp_path, found, openrouter_api_key="sk-test", skip_smoke_check=True)

    # The third tempfile was created on disk by mkstemp before fdopen failed.
    # Rollback must have cleaned it up regardless.
    leftover = list(tmp_path.rglob("*.tmp"))
    assert leftover == [], f"rollback left tempfile residue: {leftover}"
```

Also update the existing `test_inject_staging_failure_rolls_back` to widen the residue glob:

```python
def test_inject_staging_failure_rolls_back(tmp_path: Path, monkeypatch) -> None:
    # ... existing setup that triggers a staging failure ...
    # ... existing assertions ...
    # WIDEN: assert no *.tmp residue anywhere in the tree, not just for profile.md
    leftover_anywhere = list(tmp_path.rglob("*.tmp"))
    assert leftover_anywhere == [], f"rollback left tempfile residue: {leftover_anywhere}"
```

(Read the existing test body first to see exactly where to insert the widened assertion.)

- [ ] **Step 3: Run tests to verify the new one fails (and the widened one may also fail)**

```bash
uv run pytest tests/test_onboarding_injector.py::test_inject_rollback_includes_tempfile_when_write_fails_mid_staging -v
uv run pytest tests/test_onboarding_injector.py::test_inject_staging_failure_rolls_back -v
```

Expected: the new test FAILS (rollback hole leaves a tempfile); the widened existing test may PASS or FAIL depending on what residue is around.

- [ ] **Step 4: Fix the rollback hole**

In `src/findajob/onboarding/injector.py`, restructure each `mkstemp + write + append` block so the tempfile is registered immediately after `mkstemp` returns. The required-files staging loop (lines 327-334 pre-edit) becomes:

```python
        for name in ALLOWED_FILENAMES:
            if name in _ENV_MERGE_FILENAMES:
                continue
            dest = base_root / _ALL_DESTINATIONS[name]
            fd, tmp_name = tempfile.mkstemp(prefix=dest.name + ".", suffix=".tmp", dir=str(dest.parent))
            tempfiles.append((tmp_name, dest))  # register immediately so rollback sees it
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
                fh.write(found[name])
```

Apply the same pattern to:
- The optional-staging loop in Task 2 (each iteration)
- The companies_of_interest staging block (around line 346-352 pre-edit)
- The env-merge staging block (around line 354-360 pre-edit)

In every case: `tempfiles.append((tmp_name, dest))` moves to the line immediately after `mkstemp` returns, before the `with os.fdopen` block.

- [ ] **Step 5: Run tests to verify they pass**

```bash
uv run pytest tests/test_onboarding_injector.py -v
```

Expected: all pass, including the new mid-staging-failure test and the widened residue assertion.

- [ ] **Step 6: Commit**

```bash
git add src/findajob/onboarding/injector.py tests/test_onboarding_injector.py
git commit -m "$(cat <<'EOF'
fix(onboarding/injector): #215 fixes 1+2 — narrow rollback hole + widen residue assertion

Fix 1: register tempfile in `tempfiles` list immediately after mkstemp
returns, before entering the `with os.fdopen` block. Mid-staging
failures (disk-full mid-write, OSError from fdopen) now leave no
untracked tempfile residue.

Fix 2: widen test_inject_staging_failure_rolls_back's residue assertion
from a per-filename glob to a tree-wide *.tmp glob — catches regressions
across all destination dirs, not just config/profile.md's.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Prompt — Phase 1 educational layer (source-strategy briefing)

**Files:**
- Modify: `config/roles/onboarding_interviewer.md` (insert new section near the end of Phase 1)

### Steps

- [ ] **Step 1: Locate Phase 1 in the prompt**

```bash
grep -n "^## Phase 1" config/roles/onboarding_interviewer.md
grep -n "^## Phase 2" config/roles/onboarding_interviewer.md
```

Expected: Phase 1 spans roughly lines 70-103 (per the line-number scan in the spec); Phase 2 starts around line 104.

- [ ] **Step 2: Insert the source-strategy briefing block immediately before `## Phase 2`**

The new section is the literal block from the spec §6. Add it as the last subsection of Phase 1, right before the `## Phase 2 — Document ingestion` heading:

```markdown
## Job-Source Strategy (read this carefully)

This pipeline can find jobs from up to four different places. Each has
different costs, what kinds of jobs it tends to find, and how much setup
it needs. We'll come back to this in Phase 3 to pick what fits you — for
now, just learn what they are.

1. **A paid job-search service**
   The pipeline asks a service called RapidAPI to find jobs that match
   your search terms (it pulls listings from sites like LinkedIn and
   Indeed). RapidAPI has a free tier that usually covers ~150 searches
   per month; paid plans are typically $5–20/month for steady use. You
   sign up at rapidapi.com and paste a key into the pipeline. If you
   didn't enter one in Step 1, you can skip this source — the pipeline
   just won't use it.
   - Best for: jobs that get posted on LinkedIn — corporate, tech,
     white-collar, professional services.
   - Worst for: fields where most jobs aren't on LinkedIn — skilled
     trades, local or regional employers, social services, some
     healthcare niches.
   - Note: today the pipeline uses one specific RapidAPI service. A
     future version will help you pick the one that best fits your field
     and walk you through the signup.

2. **Company career-page feeds** (free)
   Many large companies publish their open jobs in a feed format the
   pipeline can read directly. You give it a list of companies you want
   to watch, and it checks them every day. No signup, no cost.
   - Best for: anyone with specific target employers in mind.
   - Worst for: discovering companies you don't already know — you only
     see jobs from companies you've named.

3. **Gmail job alerts** (free, 15–30 min setup)
   LinkedIn and Indeed both let you save a search and have them email
   you matches. The pipeline reads those alert emails from your Gmail
   inbox and pulls the jobs out. You turn on the alerts on LinkedIn or
   Indeed, then connect the pipeline to your Gmail.
   - Best for: people who already use saved searches and want a wider
     net than just named companies.
   - Worst for: anyone who'd rather not connect their Gmail.

4. **Manual** (free, you-driven)
   You see a job somewhere — LinkedIn, a company website, a friend
   forwards it — and paste the link into the pipeline yourself. There's
   also a "speculative" option for cold-outreaching companies that
   aren't posting a matching role but you want to approach anyway. No
   setup at all.
   - Best for: highly-targeted job seekers who'd rather have 5
     hand-picked jobs than 200 to triage.
   - Worst for: anyone wanting volume without effort.

You can pick any combination. Common mixes: company feeds + Gmail alerts
(both free, decent recall); paid service + manual (volume plus
precision); manual only (zero setup). We'll discuss what makes sense
for *you* in Phase 3 once we know your target roles.
```

Insert as a subsection under the existing Phase 1 — use `## Job-Source Strategy` (H2 to match Phase 1's heading level for Phase-1-internal subsections; if the prompt uses H3 for sub-sections within phases, use H3 instead — match what's already there).

Verify the heading level matches the existing prompt convention by reading 5 lines on either side of `## Phase 1` and checking how its subsections are levelled.

- [ ] **Step 3: Verify the prompt still parses cleanly (syntax check)**

```bash
grep -cE "^## Phase " config/roles/onboarding_interviewer.md
```

Expected: 5 (Phase 1 through Phase 5 — same as before; the new section uses a non-`Phase` heading so the count is unchanged).

- [ ] **Step 4: Walkthrough harness sanity check (will likely fail until Task 10 corpus update lands; that's expected)**

```bash
uv run pytest tests/test_walkthrough_harness.py::TestRealCorpusReplay -v
```

Expected: phase-anchor tests still PASS (the new section doesn't change phase boundaries); self-replay test may fail or warn because the corpus doesn't yet have a turn for Phase 1's new section. This is expected; corpus update lands in Task 10.

- [ ] **Step 5: Commit**

```bash
git add config/roles/onboarding_interviewer.md
git commit -m "$(cat <<'EOF'
feat(onboarding/prompt): #283 — Phase 1 source-strategy educational layer

Adds the four-source taxonomy (paid service / company career-page feeds
/ Gmail alerts / manual) to Phase 1 in plain language. Cost, coverage,
and setup tradeoffs spelled out without API/IMAP/RSS jargon. Forward-
references "Phase 3 to pick what fits you" — sub-phase 3g lands in the
next commit.

Closing note on item 1 ("today the pipeline uses one specific RapidAPI
service; a future version will help you pick…") is the only forward-
reference to the curated-feed-picker follow-on (#408).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Prompt — Sub-phase 3g decisional layer

**Files:**
- Modify: `config/roles/onboarding_interviewer.md` (insert sub-phase 3g between current 3f and Phase 4)

### Steps

- [ ] **Step 1: Locate the boundary between sub-phase 3f and Phase 4**

```bash
grep -n "^### 3f\." config/roles/onboarding_interviewer.md
grep -n "^## Phase 4" config/roles/onboarding_interviewer.md
```

Expected: 3f starts around line 239, Phase 4 starts around line 285.

- [ ] **Step 2: Insert sub-phase 3g immediately before `## Phase 4`**

```markdown
### 3g. Source selection

Now that we know your target roles, let me suggest a source mix.

Based on what you've told me — {one-line recap of the user's target roles
from earlier in Phase 3} — here's what I'd recommend: {one or two of the
four sources, each with a short plain-language reason}.

When recommending, draw on the user's `## Target Roles` and `## Core
Competencies` (already established in Phase 3a / 3c). Some examples of
the recommendation shape:

- For a corporate / tech / professional services candidate
  (heavy LinkedIn presence): "I'd lean toward **a, b** — the paid
  service catches LinkedIn-heavy postings, and your named target
  companies (which use ATSes the pipeline can read) are great for
  company feeds."
- For a social-services or non-profit candidate (lighter LinkedIn
  presence): "I'd lean toward **b, c** — the paid service is weak in
  social services, but Gmail alerts on Indeed and saved searches at
  named non-profits gives you broad coverage."
- For a skilled-trades or regional-employer candidate (very light
  LinkedIn presence): "I'd lean toward **c** — the paid service is
  near-useless here; Indeed alerts via Gmail is the highest-recall path,
  and very few trades employers run a Greenhouse / Lever / Ashby career
  page."

These are illustrative *shapes*, not a closed taxonomy. Use the user's
specific role and competency signals to make the recommendation.

Then ask the user to pick:

> Pick which sources you want active (Manual is always available — no
> selection needed for that one):
>
>   a. Paid job-search service (RapidAPI)
>   b. Company career-page feeds
>   c. Gmail job alerts
>
> Reply with the letters you want (e.g. "b" or "a, b, c"). Reply "none"
> if you'd rather start with Manual only.
>
> If you skip RapidAPI (no 'a'), any key you entered in Step 1 just sits
> dormant — no cost, no problem. You can always come back and add a
> source later by re-running onboarding.

Capture the user's selection. The selection determines which file blocks
you emit in Phase 5:

- `a` (RapidAPI) selected → emit `<<<FILE: jsearch_queries.txt>>>`
- `b` (company feeds) selected → emit `<<<FILE: feed-urls.txt>>>`
- `c` (Gmail alerts) selected → emit `<<<FILE: jsearch_queries.txt>>>`
  (used as saved-search seed text on LinkedIn/Indeed) AND `<<<FILE:
  linkedin-alerts.md>>>` (the setup checklist)
- "none" → emit none of the three; Phase 5 emits only the standard 9
  required files

Note that if both `a` and `c` are selected, `jsearch_queries.txt` is
emitted once — the queries serve both the RapidAPI calls and the
LinkedIn/Indeed saved-search seed text (single source of truth).
```

Verify heading level (`### 3g.`) matches existing 3a-3f.

- [ ] **Step 3: Verify the prompt's sub-phase heading count**

```bash
grep -cE "^### 3[a-g]\." config/roles/onboarding_interviewer.md
```

Expected: 7 (3a through 3g).

- [ ] **Step 4: Commit**

```bash
git add config/roles/onboarding_interviewer.md
git commit -m "$(cat <<'EOF'
feat(onboarding/prompt): #283 — sub-phase 3g source selection (decisional)

Adds the decisional layer of #283's source-strategy briefing. After 3f
(voice samples) and before Phase 4, the LLM uses target roles + core
competencies to recommend a source mix and asks the user to pick using
letter-prefixed options (per prompt convention at lines 26–29).

Three field-diverse one-shot recommendations illustrate shape without
encoding a closed field taxonomy. Selection drives Phase 5 emission per
the matrix in the spec (§4.2):

  a → jsearch_queries.txt
  b → feed-urls.txt
  c → jsearch_queries.txt + linkedin-alerts.md
  none → emit none of the three

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Prompt — Section A: revise `jsearch_queries.txt` exemplar

**Files:**
- Modify: `config/roles/onboarding_interviewer.md:692-711` (the existing exemplar)

### Steps

- [ ] **Step 1: Read the current exemplar**

```bash
sed -n '692,711p' config/roles/onboarding_interviewer.md
```

Expected: matches the snippet from the spec — 6-10 query target, 3-4 word constraint, 4 example queries across fields.

- [ ] **Step 2: Replace the exemplar with the revised version**

Replace lines 692-711 with:

```markdown
### `jsearch_queries.txt`

**Conditional emission.** Emit this block only if the user picked `a`
(paid service) or `c` (Gmail alerts) in sub-phase 3g. Skip if they
picked only `b` (company feeds) or "none" (manual only).

```
# Generated by findajob onboarding interviewer v3 — 2026-05-02
# 3-4 word natural phrases. One per line. Used by both the paid
# job-search service (RapidAPI) and as seed text for LinkedIn/Indeed
# saved-search alerts.

[query 1 — 3 to 4 words]
[query 2]
[query 3]
# Examples across fields (do not copy — replace with user's own):
#   senior backend engineer
#   clinical social worker
#   middle school math teacher
#   nonprofit development director
#   commercial electrician master
#   labor delivery nurse
```

**Volume:** Aim for 8–12 queries. Below 8, recall suffers; above 12,
hits the 150-call/month free RapidAPI tier in <2 weeks of polling.

**Derivation:** queries are profile-grounded. Read `## Target Role`,
`## Core Competencies`, and `## Career Summary` from the user's profile
and produce queries covering the role-shape × industry combinations
the user cares about. Specifically do NOT consult `## Excluded
Categories` — those drive the prefilter, not the queries.

**Constraint:** each query must be 3–4 words. Reject anything longer
before emitting; LinkedIn returns zero results for keyword-heavy 5+
word strings (per `CLAUDE.md` constraint). No Boolean operators, no
quoted strings, no location qualifiers, no seniority modifiers —
LinkedIn handles those separately.
```

- [ ] **Step 3: Sanity-check that the exemplar is syntactically intact**

```bash
grep -n "^### \`jsearch_queries.txt\`" config/roles/onboarding_interviewer.md
```

Expected: one match.

- [ ] **Step 4: Commit**

```bash
git add config/roles/onboarding_interviewer.md
git commit -m "$(cat <<'EOF'
feat(onboarding/prompt): #283 Section A — profile-grounded jsearch_queries.txt exemplar

Revises the existing exemplar (lines 692-711) for #283:

- Conditional emission gate (only when 3g selection includes `a` or `c`).
- Volume target raised from 6-10 to 8-12 (matches free RapidAPI tier
  capacity).
- Profile-grounding made explicit: read ## Target Role, ## Core
  Competencies, ## Career Summary; do NOT use ## Excluded Categories.
- Examples expanded to 6 fields (was 4) including blue-collar trades
  and healthcare niches — illustrates shape without encoding a closed
  taxonomy.
- Constraint reasoning made explicit (5+ word strings → zero LinkedIn
  results, per CLAUDE.md).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Prompt — Section B: `feed-urls.txt` emission instructions

**Files:**
- Modify: `config/roles/onboarding_interviewer.md` (add new exemplar in Phase 5's "Schema exemplars" section)

### Steps

- [ ] **Step 1: Locate where to insert the new exemplar**

The existing `### \`jsearch_queries.txt\`` exemplar (after Task 7's revision) is followed by `### \`prefilter_rules.yaml\``. Insert `### \`feed-urls.txt\`` right after `### \`jsearch_queries.txt\`` and before `### \`prefilter_rules.yaml\``.

```bash
grep -n "^### \`jsearch_queries.txt\`" config/roles/onboarding_interviewer.md
grep -n "^### \`prefilter_rules.yaml\`" config/roles/onboarding_interviewer.md
```

- [ ] **Step 2: Insert the new exemplar**

```markdown
### `feed-urls.txt`

**Conditional emission.** Emit this block only if the user picked `b`
(company career-page feeds) in sub-phase 3g.

```
# Generated by findajob onboarding interviewer v3 — 2026-05-02
# One URL per line. Optional inline comment after the URL.
# Three supported ATS shapes:
#   https://boards.greenhouse.io/{slug}        # Greenhouse (older)
#   https://job-boards.greenhouse.io/{slug}    # Greenhouse (newer)
#   https://jobs.lever.co/{slug}               # Lever
#   https://jobs.ashbyhq.com/{slug}            # Ashby

https://boards.greenhouse.io/example  # Example Corp (Greenhouse)
https://jobs.lever.co/zoox  # Zoox (Lever)
https://jobs.ashbyhq.com/coreweave  # CoreWeave (Ashby)

# Companies on unsupported ATSes — comment-out, don't fabricate slugs:
# Acme Corp — uses Workday; not currently supported
# Beta Industries — uses in-house ATS; not currently supported
```

**Derivation:** for each company in the user's `## Target Companies /
Organizations` list (sub-phase 3c), determine which ATS the company uses
and emit the right URL shape. Use your knowledge of the major ATS
deployments — most large tech and corporate companies use one of
Greenhouse / Lever / Ashby. Many use Workday or in-house ATSes; those
are not currently supported and must be commented out, not fabricated.

**Don't fabricate slugs.** If you don't know the ATS or the slug for a
company, comment it out with the form `# {Company name} — uses {ATS} or
unknown; not currently supported`. Inventing a slug that returns 404 at
fetch time pollutes the pipeline logs.

**Volume:** typically 5–15 working URLs per candidate, plus a handful of
commented-out non-supported companies — reflects reality, since most
candidates' target lists are a mix of Greenhouse-hosted and
Workday/in-house companies.

**Note on Workday:** Workday is a common ATS but the pipeline's fetcher
does not currently consume Workday job feeds. When Workday support
lands, this exemplar will be updated to emit Workday URLs too. For now,
all Workday-using companies go in the comment-out section.
```

- [ ] **Step 3: Verify the new exemplar is syntactically intact**

```bash
grep -n "^### \`feed-urls.txt\`" config/roles/onboarding_interviewer.md
```

Expected: one match.

- [ ] **Step 4: Commit**

```bash
git add config/roles/onboarding_interviewer.md
git commit -m "$(cat <<'EOF'
feat(onboarding/prompt): #283 Section B — feed-urls.txt emission for Greenhouse + Lever + Ashby

New exemplar in Phase 5's schema exemplars section. Derives ATS feed
URLs from the user's ## Target Companies block. Three URL shapes (all
three are supported by findajob.fetchers today):

  https://boards.greenhouse.io/{slug}     (Greenhouse, older subdomain)
  https://job-boards.greenhouse.io/{slug} (Greenhouse, newer subdomain)
  https://jobs.lever.co/{slug}            (Lever)
  https://jobs.ashbyhq.com/{slug}         (Ashby)

Don't-fabricate-slugs guidance is explicit — the same hallucination
failure mode #345 just fixed for the discoverer. Workday-using
companies go in the comment-out section since the fetcher doesn't
support Workday yet.

Conditional emission: only when 3g selection includes `b`.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: Prompt — Section C: `linkedin-alerts.md` emission instructions

**Files:**
- Modify: `config/roles/onboarding_interviewer.md` (add new exemplar in Phase 5's "Schema exemplars" section)

### Steps

- [ ] **Step 1: Locate where to insert the new exemplar**

Insert `### \`linkedin-alerts.md\`` after the new `### \`feed-urls.txt\`` exemplar (created in Task 8) and before whatever currently follows. The `voice-samples.md` exemplar is at line 811 (per the line-number scan in the spec); the new exemplar should sit before that.

- [ ] **Step 2: Insert the new exemplar**

```markdown
### `linkedin-alerts.md` (optional, conditional)

**Conditional emission.** Emit this block only if the user picked `c`
(Gmail alerts) in sub-phase 3g. Skip if they picked only `a`/`b`/"none".

```
# LinkedIn job alerts setup

The pipeline reads job-alert emails from your Gmail inbox. To fill that
inbox with useful alerts, set up saved searches on LinkedIn that email
you matches.

## Steps

- [ ] On LinkedIn, go to the Jobs tab and search for one of your target
      roles (e.g., "{first query from search-queries.txt}"). Use the
      "Job alerts" toggle on the search results page to enable email
      alerts for this search.
- [ ] Repeat for each query in `config/jsearch_queries.txt`. LinkedIn
      caps you at ~20 active alerts; pick the highest-recall ones if
      you have more queries than that.
- [ ] Set the alert frequency to "Daily" (more granular than "Weekly",
      less noisy than "Real-time").
- [ ] Confirm the alerts are landing in the Gmail inbox you'll connect
      to the pipeline. Check the spam folder once — LinkedIn job alerts
      occasionally land there on the first delivery.

## Wire up the pipeline's Gmail reader

Once those alerts are firing in your inbox, configure the pipeline's
IMAP reader at `/config/gmail/` so it can ingest them automatically.
That page walks you through generating a Gmail app password and
testing the connection.
```

**Derivation:** the body is mostly static markdown — the only dynamic
substitution is `{first query from search-queries.txt}`, which should
be the first 3-4 word query you emit in `jsearch_queries.txt` for this
candidate. This grounds the example in the candidate's actual target
roles instead of a generic placeholder.

**Closing step is required.** The final section, "Wire up the
pipeline's Gmail reader," must be present and must point at
`/config/gmail/` (the IMAP integration UI shipped in #330). Without
this step, the LinkedIn-alerts → Gmail → IMAP → pipeline path is
incomplete — alerts land in the inbox but never reach the pipeline.

**Doc-only.** This file is a manual-action checklist for the user to
work through in their LinkedIn account. The interview does not call
out to LinkedIn or modify the user's LinkedIn settings programmatically
— Gmail OAuth doesn't reach the LinkedIn UI.
```

- [ ] **Step 3: Verify the new exemplar is syntactically intact**

```bash
grep -n "^### \`linkedin-alerts.md\`" config/roles/onboarding_interviewer.md
```

Expected: one match.

- [ ] **Step 4: Commit**

```bash
git add config/roles/onboarding_interviewer.md
git commit -m "$(cat <<'EOF'
feat(onboarding/prompt): #283 Section C — linkedin-alerts.md doc-only emission

New exemplar in Phase 5. A 5-step LinkedIn-alerts setup checklist plus
a closing "Wire up the pipeline's Gmail reader" section pointing the
user at /config/gmail/ (the IMAP UI shipped in #330). Closes the
LinkedIn-alerts → Gmail → IMAP → pipeline path even though interactive
credential capture is out of scope (filed as #407 follow-on).

Doc-only — Gmail OAuth doesn't reach the LinkedIn UI, so alert creation
stays a manual user action.

Conditional emission: only when 3g selection includes `c`.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: Prompt — #215 Fix 3 (Tier 1 hyphen-joined company name caveat)

**Files:**
- Modify: `config/roles/onboarding_interviewer.md` (the `target_companies.md` exemplar around line 637-660)

#215 Fix 3: per the issue body, the cleanest fix is "document as known caveat in role prompt (so the LLM avoids the form in Tier 1 output)" rather than changing the regex. The injector's `_SPLIT_COMMENTARY_RE` correctly splits `- SAP - Systems Analysis Programming` into `SAP` (intentional behavior — surrounding spaces distinguish commentary from compound names like `Coca-Cola`). But it's a footgun for any Tier 1 company whose legal name contains ` - ` with surrounding spaces.

### Steps

- [ ] **Step 1: Locate the `target_companies.md` exemplar**

```bash
grep -n "^### \`target_companies.md\`" config/roles/onboarding_interviewer.md
```

Expected: one match around line 637.

- [ ] **Step 2: Add a caveat note to the exemplar**

After the existing `target_companies.md` exemplar body (just before the next `### ` heading), append:

```markdown
**Caveat for Tier 1 names with ` - ` (space-hyphen-space):** the
injector's Tier 1 derivation splits each bullet on the first ` - ` (or
` — ` or ` (`) to strip trailing commentary. So `- SAP - Systems
Analysis Programming` derives to `SAP`. This is intentional — it
distinguishes "Coca-Cola" (no surrounding spaces, survives intact) from
trailing commentary. But if a Tier 1 company's legal name actually
contains ` - ` (space-hyphen-space) — e.g., `Procter - Gamble` — the
injector will truncate it.

**Avoid the form in Tier 1 output.** If a real company's name contains
a ` - `, normalize it to either an em-dash (`Procter — Gamble`) or no
surrounding spaces (`Procter-Gamble`) before emitting in the Tier 1
list. Document the canonical form once at the top of the user's
`## Notes` if it might confuse them later.
```

- [ ] **Step 3: Commit**

```bash
git add config/roles/onboarding_interviewer.md
git commit -m "$(cat <<'EOF'
fix(onboarding/prompt): #215 fix 3 — Tier 1 hyphen-joined name caveat

The injector's _SPLIT_COMMENTARY_RE splits Tier 1 bullets on ` - ` to
strip trailing commentary; this is intentional for the common case
(- SAP - Systems Analysis Programming → SAP) but truncates real company
names containing ` - ` with surrounding spaces.

Documents the form to avoid in target_companies.md emission rather than
loosening the regex (changing the regex would break the commentary-
stripping for the much-more-common ` - description` pattern).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 11: Walkthrough corpus update — Avery Chen turns for Phase 1 briefing + 3g + new emissions

**Files:**
- Modify: `tests/fixtures/walkthrough/corpus_transcript.md`

### Steps

- [ ] **Step 1: Read the current corpus to understand its end-state**

```bash
wc -l tests/fixtures/walkthrough/corpus_transcript.md
grep -nE "^## Turn [0-9]+ — (ASSISTANT|USER)" tests/fixtures/walkthrough/corpus_transcript.md | tail -10
grep -n "^### 3f\." tests/fixtures/walkthrough/corpus_transcript.md
grep -n "Phase 4" tests/fixtures/walkthrough/corpus_transcript.md
grep -n "<<<FILE:" tests/fixtures/walkthrough/corpus_transcript.md | head -20
```

Expected: 24 turn-pairs (last is Turn 24); the corpus walks Avery Chen through Phase 1 → Phase 5 emission. Note where 3f ends and Phase 4 begins (this is where 3g turns will be inserted) and where the Phase 5 emission turns begin (this is where the new `feed-urls.txt` and `linkedin-alerts.md` blocks need to be added).

- [ ] **Step 2: Insert 2 new turns near Phase 1 end for Avery acknowledging the source-strategy briefing**

Find the turn where the assistant ends Phase 1 (matches the prompt's Phase 1 → Phase 2 boundary in the corpus). Insert new turns immediately before the Phase 2 transition:

```markdown
## Turn N — ASSISTANT
[brief Phase 1 wrap-up paragraph followed by the new source-strategy
briefing block. Use the same wording as the prompt's new section, just
in the assistant's voice. End with: "Anything click for you in particular,
or any questions before we move on to ingesting your résumé?"]

## Turn N — USER
The Gmail alerts approach is interesting — I already use Indeed alerts
for clinical pharmacy informatics roles. And company career-page feeds
makes sense for the named hospital systems on my list. The paid service
sounds like it might be weak for healthcare informatics, so I'd lean
away from that. But let me confirm in Phase 3.
```

(Renumber subsequent turns accordingly. The turn numbers must remain monotonic and dense — no gaps.)

- [ ] **Step 3: Insert 3g turns between the existing 3f wrap-up and Phase 4 transition**

```markdown
## Turn M — ASSISTANT
### 3g. Source selection

Now that we know your target roles, let me suggest a source mix.

Based on what you've told me — clinical pharmacist transitioning into
clinical informatics, with a focus on EHR / order-set / decision-support
work at academic medical centers — here's what I'd recommend:

- **b (company career-page feeds)** — your named hospital systems
  (Stanford Health Care, Cedars-Sinai, UCLA Health, MGH, Cleveland
  Clinic) all have career pages we can poll directly.
- **c (Gmail alerts)** — clinical informatics is Indeed-skewed and
  LinkedIn-light; saved-search alerts will catch postings the paid
  service misses.

Pick which sources you want active (Manual is always available — no
selection needed for that one):

  a. Paid job-search service (RapidAPI)
  b. Company career-page feeds
  c. Gmail job alerts

Reply with the letters you want (e.g. "b" or "a, b, c"). Reply "none"
if you'd rather start with Manual only.

## Turn M — USER
b, c
```

- [ ] **Step 4: Update the existing `<<<FILE: jsearch_queries.txt>>>` emission**

The current corpus's Avery emission for `jsearch_queries.txt` may exist (it was previously required); confirm it exists and update its content if needed to match the revised 8-12 query target with profile-grounded healthcare-informatics queries. Example queries:

```
clinical informatics pharmacist
clinical pharmacist informatics
EHR pharmacist informatics
pharmacy informatics specialist
medication safety pharmacist
order set pharmacist
clinical decision support pharmacist
pharmacy clinical analyst
informatics pharmacist hospital
pharmacy IT specialist
```

(Keep ≤10 queries to match real-world rerunnability.)

- [ ] **Step 5: Add new `<<<FILE: feed-urls.txt>>>` emission turn**

Find the Phase 5 emission section in the corpus. After the existing emissions but before the final wrap-up turn, add:

```markdown
## Turn P — ASSISTANT
<<<FILE: feed-urls.txt>>>
# Generated by findajob onboarding interviewer v3 — 2026-05-02
# One URL per line. Optional inline comment after the URL.

https://boards.greenhouse.io/cedarssinai  # Cedars-Sinai (Greenhouse — verify slug)

# Companies on unsupported ATSes — comment-out:
# Stanford Health Care — uses Workday; not currently supported
# UCLA Health — uses in-house / PeopleSoft; not currently supported
# MGH (Mass General Brigham) — uses Workday; not currently supported
# Cleveland Clinic — uses Taleo; not currently supported
<<<END FILE: feed-urls.txt>>>

[Reply **next** to continue.]
```

(Hospital systems are realistically Workday-heavy; this corpus exercises
the comment-out path, which is more representative for the field-agnostic
stress test than picking a tech-flavored corpus that happens to be
Greenhouse-saturated.)

- [ ] **Step 6: Add new `<<<FILE: linkedin-alerts.md>>>` emission turn**

After the `feed-urls.txt` emission turn, add:

```markdown
## Turn Q — ASSISTANT
<<<FILE: linkedin-alerts.md>>>
# LinkedIn job alerts setup

The pipeline reads job-alert emails from your Gmail inbox. To fill that
inbox with useful alerts, set up saved searches on LinkedIn that email
you matches.

## Steps

- [ ] On LinkedIn, go to the Jobs tab and search for one of your target
      roles (e.g., "clinical informatics pharmacist"). Use the "Job
      alerts" toggle on the search results page to enable email alerts
      for this search.
- [ ] Repeat for each query in `config/jsearch_queries.txt`. LinkedIn
      caps you at ~20 active alerts; pick the highest-recall ones if
      you have more queries than that.
- [ ] Set the alert frequency to "Daily" (more granular than "Weekly",
      less noisy than "Real-time").
- [ ] Confirm the alerts are landing in the Gmail inbox you'll connect
      to the pipeline. Check the spam folder once — LinkedIn job alerts
      occasionally land there on the first delivery.

## Wire up the pipeline's Gmail reader

Once those alerts are firing in your inbox, configure the pipeline's
IMAP reader at `/config/gmail/` so it can ingest them automatically.
That page walks you through generating a Gmail app password and
testing the connection.
<<<END FILE: linkedin-alerts.md>>>

[Reply **next** to continue.]
```

- [ ] **Step 7: Run the walkthrough harness against the updated corpus**

```bash
uv run pytest tests/test_walkthrough_harness.py -v
```

Expected: all PASS, including:
- `test_corpus_parses_with_all_five_phase_anchors` (still 5 phases)
- `test_corpus_self_replay_has_no_review_turns` (every turn matches positionally within phase)

If any fail, the most likely cause is mismatched phase anchors (the new section uses `## Job-Source Strategy` which isn't a `## Phase X` heading; the harness anchor regex may need to skip it). Check the harness's phase-anchor detection:

```bash
grep -nE "phase_anchors|advance_phase_idx" tests/test_walkthrough_harness.py | head -10
```

If the harness uses regex `^## Phase \d+` to detect anchors, the new section is invisible to it (good — no anchor confusion). If it uses a broader regex, may need adjustment.

- [ ] **Step 8: Commit**

```bash
git add tests/fixtures/walkthrough/corpus_transcript.md
git commit -m "$(cat <<'EOF'
test(walkthrough): #283 — Avery Chen corpus turns for Phase 1 briefing + 3g + new emissions

Updates the in-repo replay corpus (Avery Chen, clinical pharmacist →
informatics) to exercise the #283 prompt revisions:

- Phase 1 source-strategy briefing read-through (one assistant turn,
  one user acknowledgement).
- Sub-phase 3g recommendation + selection (Avery picks `b, c` —
  realistic for healthcare informatics with Indeed-skewed alerts and
  named hospital-system targets).
- Phase 5 emissions for feed-urls.txt (mostly Workday comment-outs —
  representative for the field) and linkedin-alerts.md (with the
  /config/gmail/ closing step).

The Avery persona is the field-agnostic stress test — non-tech, light
LinkedIn presence, Workday-heavy target list. Replay-passes verify that
the prompt revisions don't regress phase-anchor detection or positional
matching.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 12: Doc updates — CLAUDE.md, api-keys.md, usage.md, configure.md, CHANGELOG.md

**Files:**
- Modify: `CLAUDE.md`
- Modify: `docs/setup/api-keys.md`
- Modify: `docs/usage.md`
- Modify: `docs/setup/configure.md`
- Modify: `CHANGELOG.md`

### Steps

- [ ] **Step 1: Update `CLAUDE.md` — add new file paths, note conditional emission**

Find the `Key File Locations` section. Under `# ── Candidate content` or `# ── Config`, add lines for the new files (use the same path-comment format as the existing entries):

```
<repo>/config/feed_urls.txt                 # Greenhouse / Lever / Ashby career-page feed URLs (interview-emitted, conditional on 3g 'b' selection)
<repo>/candidate_context/linkedin-alerts.md # LinkedIn-alerts setup checklist (interview-emitted, conditional on 3g 'c' selection)
```

Also update the `### Web Frontend Architecture` and `### Synthetic Jobs Convention` sections if they reference onboarding-emitted files; not expected to touch them but verify with:

```bash
grep -nE "(jsearch_queries|feed_urls|linkedin-alerts)" CLAUDE.md | head -10
```

Decide based on the matches whether any callouts need updating.

- [ ] **Step 2: Update `docs/setup/api-keys.md` — RapidAPI section cross-reference**

Find the `## RapidAPI (jobs-api14) — optional` section (line 75 per the spec's earlier scan). Add a paragraph at the top of that section:

```markdown
> **Already onboarded?** The onboarding interview's source-strategy
> briefing (#283) walks through what the paid service is good for and
> when to skip it. If the briefing led you to opt out of RapidAPI
> (sub-phase 3g, no `a` selection), you can leave the key field blank
> here — the pipeline will use your other sources only. Re-run
> onboarding via `/onboarding/?mode=rerun` if you want to revisit the
> source-strategy decision.
```

- [ ] **Step 3: Update `docs/usage.md` — add Source-strategy section**

Find a sensible insertion point (likely after an "Overview" or "Getting started" section). Add:

```markdown
## Job sources

The pipeline can ingest jobs from up to four sources. The onboarding
interview helps you pick which ones make sense for your field; this
section is a post-onboarding reference for what each source does and
how to tune it.

### Paid job-search service (RapidAPI)
The pipeline calls a third-party job-search API (today: jobs-api14 on
RapidAPI) with the queries in `config/jsearch_queries.txt`. Cost is
metered against the RapidAPI key you provided in onboarding (Step 1).
Free tier covers ~150 calls/month.

To tune: edit `config/jsearch_queries.txt` (one 3-4 word query per
line; LinkedIn returns zero results for 5+ word strings).

### Company career-page feeds
The pipeline polls Greenhouse / Lever / Ashby career-page endpoints
listed in `config/feed_urls.txt`. Free; no API key.

To tune: edit `config/feed_urls.txt` (one URL per line; supported
shapes are `boards.greenhouse.io/{slug}`, `job-boards.greenhouse.io/{slug}`,
`jobs.lever.co/{slug}`, `jobs.ashbyhq.com/{slug}`).

### Gmail-ingest alerts
The pipeline reads job-alert emails from your Gmail inbox via IMAP and
parses the embedded job listings. You set up saved-search alerts on
LinkedIn / Indeed, point them at your Gmail, and configure the
pipeline's IMAP reader at `/config/gmail/`.

The interview's `linkedin-alerts.md` checklist (in
`candidate_context/`) is a one-time setup walkthrough.

### Manual ingest
Paste a job URL into the in-app `/ingest/` form. Best for highly-
targeted candidates who'd rather hand-curate than triage volume. A
"speculative" variant lets you cold-outreach companies that aren't
posting a matching role.

### Re-running source-strategy onboarding
Visit `/onboarding/?mode=rerun` to walk through the source-strategy
briefing again. Existing source-config files (`jsearch_queries.txt`,
`feed_urls.txt`, `linkedin-alerts.md`) are backed up under
`.backups/{UTC-stamp}/` before being overwritten.
```

- [ ] **Step 4: Update `docs/setup/configure.md` — note interview-emitted defaults**

Find any section that references `feed_urls.txt` or `jsearch_queries.txt`. Add a note (or update existing) that these are now interview-emitted by default:

```markdown
> **Note:** `config/jsearch_queries.txt`, `config/feed_urls.txt`, and
> `candidate_context/linkedin-alerts.md` are now emitted by the
> onboarding interview (#283) based on your sub-phase 3g selection.
> Manual editing of these files remains supported — re-running
> onboarding overwrites them, but backs up the prior content under
> `.backups/{UTC-stamp}/`.
```

- [ ] **Step 5: Update `CHANGELOG.md` — `[Unreleased]` entry**

Read the current `[Unreleased]` section:

```bash
sed -n "/^## \[Unreleased\]/,/^## \[/p" CHANGELOG.md | head -30
```

Add the following entry under `### Added` (creating the heading if necessary):

```markdown
### Added
- **Onboarding source-strategy briefing (#283).** The onboarding interview now opens with a four-source taxonomy (paid service, company career-page feeds, Gmail alerts, manual) in plain language and asks the candidate to pick which sources to activate using letter-prefixed selection. Source-config files (`config/jsearch_queries.txt`, `config/feed_urls.txt`, `candidate_context/linkedin-alerts.md`) are emitted opt-in based on selection. Existing operators can re-run via `/onboarding/?mode=rerun` to upgrade. Includes #215 injector hardening polish.

### Changed
- `findajob.onboarding.parser.ALLOWED_FILENAMES` drops from 10 entries to 9 (`jsearch_queries.txt` moves to `OPTIONAL_FILENAMES`). New OPTIONAL files: `feed-urls.txt`, `linkedin-alerts.md`. Conditional emission is enforced by the prompt; the parser is selection-agnostic.
```

Decide whether to add a `migration-required` label note: re-onboarding is **optional** for existing operators (their existing `jsearch_queries.txt` / `feed_urls.txt` keep working unchanged), so this is **not** `migration-required`. Document accordingly.

- [ ] **Step 6: Run docs-only smoke checks**

```bash
# Markdown lint via ruff (some projects do this; verify findajob's setup)
uv run pytest tests/ -v -x  # whole suite to catch any test that asserts on doc content
```

Expected: no test failures from doc edits.

- [ ] **Step 7: Commit**

```bash
git add CLAUDE.md docs/setup/api-keys.md docs/usage.md docs/setup/configure.md CHANGELOG.md
git commit -m "$(cat <<'EOF'
docs: #283 — source-strategy briefing across CLAUDE.md, api-keys, usage, configure, CHANGELOG

CLAUDE.md: feed_urls.txt + linkedin-alerts.md added to file-paths
section.

docs/setup/api-keys.md: RapidAPI section cross-references the source-
strategy briefing — opt-out is now first-class.

docs/usage.md: new Job-sources section as a post-onboarding reference
for what each source does and how to tune it.

docs/setup/configure.md: notes that source-config files are interview-
emitted by default, with backup-then-overwrite on re-run.

CHANGELOG.md: [Unreleased] entry under Added/Changed. Not
migration-required (existing operators keep their files as-is unless
they re-run onboarding).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 13: Whole-feature verification gate (manual)

This is an operator-driven verification step. The plan documents what to do; an autonomous worker should NOT run the paid walkthrough without explicit operator authorization.

### Steps

- [ ] **Step 1: Run the full unit test suite**

```bash
uv run pytest tests/ -v
```

Expected: all pass. Particularly verify:
- `tests/test_onboarding_parser.py` — 4 new tests + renamed-existing
- `tests/test_onboarding_injector.py` — 4 new tests + #215 fix tests
- `tests/test_onboarding_emission_anomaly.py` — 3 tests
- `tests/test_walkthrough_harness.py` — `test_corpus_parses_with_all_five_phase_anchors` and `test_corpus_self_replay_has_no_review_turns` both green

- [ ] **Step 2: Run ruff + mypy**

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy src/
```

Expected: all clean.

- [ ] **Step 3: Walkthrough harness corpus replay (free, no API call)**

```bash
uv run pytest tests/test_walkthrough_harness.py -v
```

Expected: all pass. This verifies the prompt revisions don't break phase-anchor detection or positional matching against the updated Avery Chen corpus.

- [ ] **Step 4: Re-onboarding (`?mode=rerun`) on the operator's primary stack**

This is operator-driven and requires the operator to navigate `/onboarding/?mode=rerun` on their stack. Document the expected outcome:

- Pre-existing `config/jsearch_queries.txt`, `config/feed_urls.txt`, `candidate_context/linkedin-alerts.md` (if any) are backed up under `.backups/{UTC-stamp}/`.
- The interview re-runs Phase 1 briefing, sub-phase 3g, and Phase 5 emission per the operator's new selection.
- Sentinel `data/.onboarding-complete` is rewritten with a fresh timestamp.

Operator confirms via:

```bash
ssh docker.lan -- 'sudo -u lad ls -la /opt/stacks/findajob-{handle}/state/.backups/'
ssh docker.lan -- 'sudo -u lad ls -la /opt/stacks/findajob-{handle}/state/config/feed_urls.txt /opt/stacks/findajob-{handle}/state/candidate_context/linkedin-alerts.md'
```

- [ ] **Step 5: Paid `findajob-test` walkthrough (~$5; operator-authorized)**

This step costs ~$5 in OpenRouter / Sonnet 4.6 tokens. Do NOT run without operator authorization.

When authorized:
1. Operator navigates to `findajob-test` stack on `:latest` (already running, per CLAUDE.local.md).
2. Hits `/onboarding/?mode=rerun` on a fresh state directory.
3. Plays an Avery-shape persona end-to-end.
4. Verifies, after completion:
   - All 9 ALLOWED files are written.
   - The 3 OPTIONAL files emitted match the persona's 3g selection (e.g., `b, c` → `feed-urls.txt` + `jsearch_queries.txt` + `linkedin-alerts.md` written; no jsearch-only path).
   - Consistency-check warnings fire when expected (force a manual-only path, force a Gmail-without-queries path).
   - Sentinel set only after all writes succeed.
5. Operator runs additional persona variants if desired (manual-only path, RapidAPI-only path).

This step's operator-driven nature means an autonomous worker SHOULD NOT execute it. Document the expected outcomes and let the operator drive.

- [ ] **Step 6: PR self-review checklist mapping (run before opening PR)**

Verify every spec acceptance criterion has a corresponding task or change in this plan:

- "explicit Phase steps reading `## Target Roles` etc." → Task 6 (3g) + Task 7 (Section A profile-grounding)
- "emits 2–3 new file blocks" → Task 8 + Task 9 (and Section A revision in Task 7)
- "parser + injector handle them" → Task 1 + Task 2
- "3-4 word natural phrases" → Task 7
- "linkedin-alerts.md closing step points at `/config/gmail/`" → Task 9
- "backwards-compat via `?mode=rerun`" → Task 2 (`.backups` flow already works) + Task 13 step 4 verification
- "field-agnostic" → Task 5 (Phase 1) + Task 6 (3g one-shots) + Task 7 (Section A examples) + Task 11 (Avery non-tech corpus)
- "Section 0 plain-language educational layer" → Task 5
- "Conditional emission based on 3g selection" → Tasks 5+6+7+8+9 (prompt-side); Task 1+2 (parser/injector tolerate)

Every acceptance criterion has at least one task; every task has a clear deliverable.

---

## Task 14: Open PR

**Files:** none (git operation only)

### Steps

- [ ] **Step 1: Push the feature branch**

```bash
git push -u origin feat/283-source-strategy-briefing
```

- [ ] **Step 2: Open the PR**

```bash
gh pr create --title "feat(onboarding): #283 source-strategy briefing + profile-grounded source-config emission" --body "$(cat <<'EOF'
## Summary

Adds a four-source strategy briefing to the onboarding interview (educational layer in Phase 1, decisional sub-phase 3g) and emits profile-grounded source-config files (`jsearch_queries.txt`, `feed-urls.txt`, `linkedin-alerts.md`) opt-in based on candidate selection. Bundles #215 injector hardening polish.

Closes #283. Bundles #215.

Spec: `docs/superpowers/specs/2026-05-02-283-design.md`

## What changed

- **Parser** (`findajob.onboarding.parser`): `jsearch_queries.txt` moves `ALLOWED → OPTIONAL`; new OPTIONAL files `feed-urls.txt` and `linkedin-alerts.md`.
- **Injector** (`findajob.onboarding.injector`): generalized optional-staging loop over `_OPTIONAL_DESTINATIONS`; #215 Fix 1 (rollback hole between mkstemp and tempfiles.append); #215 Fix 2 (widened residue assertion); non-blocking emission-consistency warnings logged to `pipeline.jsonl`.
- **Prompt** (`config/roles/onboarding_interviewer.md`): Phase 1 source-strategy briefing (4-source taxonomy, plain language); sub-phase 3g letter-prefixed source selection; Section A `jsearch_queries.txt` exemplar revised for profile-grounding; Section B `feed-urls.txt` exemplar covering Greenhouse + Lever + Ashby; Section C `linkedin-alerts.md` exemplar with closing `/config/gmail/` reference; #215 Fix 3 (Tier 1 hyphen-joined name caveat).
- **Walkthrough corpus**: Avery Chen turns for Phase 1 briefing + 3g + new emissions.
- **Docs**: CLAUDE.md, docs/setup/api-keys.md, docs/usage.md, docs/setup/configure.md, CHANGELOG.md.

## Test plan

- [ ] All unit tests pass (`uv run pytest tests/`)
- [ ] Ruff + mypy clean (`uv run ruff check . && uv run ruff format --check . && uv run mypy src/`)
- [ ] Walkthrough harness replay against updated Avery Chen corpus passes
- [ ] Operator runs `/onboarding/?mode=rerun` on their primary stack and confirms `.backups/{UTC-stamp}/` captures pre-existing files cleanly
- [ ] (Optional, ~$5) Operator runs paid walkthrough on `findajob-test` end-to-end against the revised prompt; verifies emitted file set matches selection across at least two persona variants

## Migration

**Not migration-required.** Existing operators keep their pre-existing `jsearch_queries.txt` / `feed_urls.txt` unchanged. Re-running onboarding (`/onboarding/?mode=rerun`) is opt-in and backs up existing content under `.backups/{UTC-stamp}/` before overwrite.

## Follow-ons

- **#408** — curated RapidAPI feed picker + per-class recommendations + interactive signup walkthrough (depends on this PR)
- **#372** — `target_locations.txt` derivation (fast-follow; reuses this PR's source-config-derivation infrastructure)
- **#407** — interactive Gmail IMAP credential capture during interview (depends on this PR + #330)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Expected: PR URL printed.

- [ ] **Step 3: Verify CI starts**

```bash
gh pr checks
```

Expected: ruff + mypy + pytest checks running.

---

## Self-review checklist (run before declaring plan done)

- [x] Spec coverage: every acceptance criterion in spec §10 has a corresponding task above (verified in Task 13 Step 6 mapping).
- [x] No placeholders: every step has actual code/commands/expected output, no "TBD" or "TODO".
- [x] Type consistency: `_OPTIONAL_DESTINATIONS` keyed by emission filename → destination relpath in Tasks 2, 3 (consistent); `ALLOWED_FILENAMES`/`OPTIONAL_FILENAMES` are tuples in Task 1 (consistent with existing parser shape).
- [x] File paths and line numbers: where line numbers are given, they're sourced from explicit `grep -n` calls earlier in this plan-writing session and reflect pre-edit state.
- [x] Dependencies: Task 2 depends on Task 1 (parser change must precede injector change); Tasks 5-10 (prompt) all depend on Tasks 1-4 having landed (parser/injector accept the new files); Task 11 (corpus) depends on Tasks 5-10; Task 12 (docs) can land last; Task 13 (verification) is the gate before Task 14 (PR).

Plan is complete and ready for execution.
