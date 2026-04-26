# Dynamic Company Discoverer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Implementation-style tasks SHOULD be dispatched to a Sonnet subagent (per `feedback_subagent_model_defaults`); review-style work stays on Opus.

**Goal:** Implement #284 — a `company_discoverer` role + library + weekly cron + onboarding hook that produces a regenerable, field-agnostic, reasoned company-set in `candidate_context/discovered_companies.md` (+ JSON sidecar). Augments — does not replace — the static `## Target Companies / Organizations` profile section. Loadbearing prerequisite for #285 (scorer rewire) and unblock for #276.

**Architecture:** Library module `src/findajob/discoverer/` with separable units (`prompt.py`, `parser.py`, `runner.py`, `writer.py`). Two entry points share the library: a thin CLI script `scripts/discover_companies.py` (weekly cron) and a post-commit hook in `findajob.onboarding.injector.inject()` (synchronous, soft-fail). Output is markdown for humans + JSON sidecar for machines; both written by a single atomic temp+replace commit, parse-validated before any disk write.

**Tech Stack:** Python 3.11+, `aichat-ng` subprocess (model: `openrouter:perplexity/sonar-reasoning-pro`, ~$3-5/run), pytest + tmp_path fixtures, FastAPI (existing onboarding route), Jinja2 templates, supercronic (existing crontab).

**Spec:** [`docs/superpowers/specs/2026-04-26-company-discoverer-design.md`](../specs/2026-04-26-company-discoverer-design.md) (commit `82aa0a7` on `main`).

---

## 1. Goal + scope

### 1.1 Goal

Build a competency-driven company discovery pipeline that pressure-tests transferable-competency fit against actual hiring activity (via `sonar-reasoning-pro`'s web search + reasoning), regenerates weekly, and exposes its output to two downstream consumers (#285 scorer rewire and #283 Greenhouse-slug derivation) via a stable JSON sidecar contract. The static `## Target Companies / Organizations` section stays as a strategic-preference seed; the discovered set carries the orthogonal competency-fit signal.

### 1.2 Out of scope (deferred to other issues)

- **Replacing the static `## Target Companies` section** (stays as strategic-preference signal; scorer rewire to drop `TIER 1 EXCEPTION` is #285).
- **Per-role discovery** (e.g., narrowing to specific job titles within a cluster) — cluster-by-competency-adjacency is the right altitude for v1.
- **Hiring-activity scraping beyond `sonar-reasoning-pro`'s web search** — no LinkedIn API, no proprietary data feeds.
- **Permanent CI gates for field-agnosticism** — no grep-lint, no committed Alice fixture, no snapshot-diff test (per Q4 brainstorm reflection: committed test fixtures for one-time gates are an antipattern).
- **A `/tools/` re-trigger button** — operators can run the script directly; UI button is #150-tuning territory.
- **Quarterly Deep Research mode** (`sonar-deep-research`) — opt-in extension, deferred.

---

## 2. Tasks

### Task 1: Create feature branch and update `.gitignore`

**Files:**
- Modify: `.gitignore`

**Steps:**

- [ ] **Step 1: Create + switch to feature branch off origin/main.**

```bash
git fetch origin
git checkout -b feat/284-company-discoverer origin/main
```

Expected: `Switched to a new branch 'feat/284-company-discoverer'`.

- [ ] **Step 2: Add discovered_companies.* to `.gitignore`.** Find the line `candidate_context/master_resume.md` and add the two new patterns immediately after.

```diff
 candidate_context/master_resume.md
+candidate_context/discovered_companies.md
+candidate_context/discovered_companies.json
 candidate_context/voice_samples/*
```

- [ ] **Step 3: Verify the patterns work locally.**

Run: `touch candidate_context/discovered_companies.md candidate_context/discovered_companies.json && git status --short`
Expected: those two paths do **not** appear in the output.
Cleanup: `rm candidate_context/discovered_companies.md candidate_context/discovered_companies.json`.

- [ ] **Step 4: Commit.**

```bash
git add .gitignore
git commit -m "chore(discoverer): gitignore discovered_companies.{md,json} (#284)"
```

---

### Task 2: Write the `company_discoverer` role file

**Files:**
- Create: `config/roles/company_discoverer.md`

The role file is read by `aichat-ng --role company_discoverer`. Its frontmatter sets the model + temperature; its body is the system prompt. It MUST contain no enumerated industries, no named companies, no role titles — see spec §10. The top-of-file comment is verbatim from spec §10.

**Steps:**

- [ ] **Step 1: Write the role file.**

```markdown
---
model: openrouter:perplexity/sonar-reasoning-pro
temperature: 0.2
---
<!--
This prompt is intentionally field-agnostic. It reads the candidate's profile and
reasons about competency-stack adjacencies in their field, whatever that field is.
If you fork this project to tune the discoverer for your own field, that is
expected; if you contribute back upstream, please preserve field-agnosticism so
other operators in unrelated fields continue to benefit from improvements.
-->

You are a company discovery analyst. Given a candidate profile, identify
companies and organizations whose hiring activity, scale, and role mix make
them a plausible fit for the candidate's competency stack. Use web search to
ground every recommendation in a current, citeable source.

Read the candidate profile carefully. Pay particular attention to:

- `## Core Competencies` — the load-bearing skills the candidate has named.
- `## Career Summary` — the kinds of problems the candidate has solved.
- `## Target Roles` (or `## Target Role`) — the role shapes the candidate is
  pursuing.
- `## Target Companies / Organizations` — a seed list, not the universe. Treat
  these as one signal among many; the candidate is willing to be surprised.

Produce three clusters of companies. For each company, provide one line of
reasoning that ties the company's hiring activity or work to a specific
competency or career signal in the candidate's profile. Cite at least one
verifiable source per company.

## Cluster 1: Direct domain match

Companies whose advertised roles most closely match the candidate's target
roles and core competencies. The candidate's competency stack is what the
company is hiring for.

## Cluster 2: Transferable-competency adjacency

Companies in adjacent industries or domains where the candidate's competency
stack would transfer well, even though the surface-level industry vocabulary
differs from the candidate's career history.

## Cluster 3: Cross-industry application

Companies in unrelated industries that nevertheless need the specific kind of
work the candidate has done. The connection should be defensible, not
speculative.

## Output format

Return markdown only. Use the following structure verbatim:

```
# Discovered Companies — generated YYYY-MM-DD

Generated by findajob `company_discoverer` (model: openrouter:perplexity/sonar-reasoning-pro).
This file augments — does not replace — the `## Target Companies / Organizations`
section in `profile.md`.

## Cluster: Direct domain match

- **Company Name** — channel=greenhouse. Reasoning: <one line tying the company to a specific profile signal>. Citations: [1], [2].
- ...

## Cluster: Transferable-competency adjacency

- ...

## Cluster: Cross-industry application

- ...

## References

[1] https://example.com/path
[2] https://example.com/other-path
```

Channel values: `greenhouse`, `ashby`, `lever`, `workday`, `in_house`,
`unknown`. Use `unknown` if you cannot determine the public hiring channel
from your sources.

Emit at least 3 companies total across at least 2 clusters. Aim for 5–10
companies per cluster when the signal supports it; never invent companies to
fill quotas.

Citation indices in row text MUST resolve to numbered URLs in the
`## References` footer. No placeholder citations, no `[citation needed]`.

If the candidate profile is empty, malformed, or lacks any of the named
sections, respond with the literal text `INSUFFICIENT_PROFILE` and nothing
else.

Be specific and factual. Length: 600–900 words excluding references.
```

- [ ] **Step 2: Verify the role file does not introduce any operator-specific or field-locked content.**

The pre-commit hook (installed locally per `docs/setup/configure.md`) is the authoritative gate for operator PII. As a separate field-locked-vocabulary check, scan for industry tokens that should not appear in a generic prompt:

Run: `grep -inE "GPU|data center|robotics|social work|nursing|teaching|software engineer|hardware engineer" config/roles/company_discoverer.md`
Expected: no matches (empty output, exit 1).

If the pre-commit hook flags any operator identifier when committing this file, the prompt body has accidentally referenced operator-specific content — redact and retry.

- [ ] **Step 3: Commit.**

```bash
git add config/roles/company_discoverer.md
git commit -m "feat(discoverer): add company_discoverer role file (#284)"
```

---

### Task 3: Implement `prompt.py` (TDD)

**Files:**
- Create: `src/findajob/discoverer/__init__.py`
- Create: `src/findajob/discoverer/prompt.py`
- Create: `tests/discoverer/__init__.py`
- Create: `tests/discoverer/test_prompt.py`

`prompt.build_prompt(profile_text: str) -> str` is a pure function. It returns the user-prompt string passed to `aichat-ng -S <prompt>` (the system prompt is the role file body). It MUST NOT paraphrase profile content into the prompt — only reference profile sections by name and pass the raw profile through verbatim.

**Steps:**

- [ ] **Step 1: Create empty package init.**

`src/findajob/discoverer/__init__.py`:
```python
"""findajob.discoverer — competency-driven company discovery (#284)."""
```

`tests/discoverer/__init__.py`:
```python
```

- [ ] **Step 2: Write the failing tests.**

`tests/discoverer/test_prompt.py`:
```python
from findajob.discoverer.prompt import build_prompt


def _profile_a() -> str:
    return """
## Identity
Name: Test One

## Core Competencies
- Skill A
- Skill B

## Career Summary
Built thing X.

## Target Roles
Senior Person at Place.

## Target Companies / Organizations
Acme, Beta Co, Gamma Inc.
"""


def _profile_b() -> str:
    return """
## Identity
Name: Test Two

## Core Competencies
- Different Skill C
- Different Skill D

## Career Summary
Solved problem Y.

## Target Roles
Lead Other at Other Place.

## Target Companies / Organizations
Delta, Epsilon Org, Zeta LLC.
"""


def test_build_prompt_includes_full_profile_verbatim() -> None:
    profile = _profile_a()
    prompt = build_prompt(profile)
    # The full profile passes through verbatim — the role file (system) does the reasoning.
    assert profile.strip() in prompt


def test_build_prompt_references_expected_sections_by_name() -> None:
    prompt = build_prompt(_profile_a())
    for marker in ("Core Competencies", "Career Summary", "Target Roles", "Target Companies"):
        assert marker in prompt


def test_build_prompt_is_field_agnostic() -> None:
    """The scaffolding (everything except the verbatim profile) must contain
    no enumerated industries, named companies, or role-title lists."""
    prompt = build_prompt(_profile_a())
    # Strip the verbatim profile block; what's left is the scaffolding.
    scaffolding = prompt.replace(_profile_a().strip(), "")
    forbidden = (
        "tech", "software", "engineer", "GPU", "NVIDIA", "Meta", "Google",
        "social work", "nursing", "teaching", "robotics", "data center",
    )
    for tok in forbidden:
        assert tok.lower() not in scaffolding.lower(), f"scaffolding contains field-locked token: {tok!r}"


def test_build_prompt_is_pure_and_deterministic() -> None:
    profile = _profile_a()
    assert build_prompt(profile) == build_prompt(profile)


def test_build_prompt_two_profiles_produce_different_outputs() -> None:
    a = build_prompt(_profile_a())
    b = build_prompt(_profile_b())
    assert a != b
    # Profile A markers
    assert "Skill A" in a and "Acme" in a
    # Profile B markers
    assert "Skill C" in b and "Delta" in b
```

- [ ] **Step 3: Run tests; expect ImportError / failure.**

Run: `uv run pytest tests/discoverer/test_prompt.py -v`
Expected: collection error or all tests fail (ImportError on `findajob.discoverer.prompt`).

- [ ] **Step 4: Implement `prompt.py`.**

`src/findajob/discoverer/prompt.py`:
```python
"""Pure prompt builder for the company_discoverer role.

The role file's system prompt does the reasoning; this module produces the
user-prompt string that wraps the candidate's profile. Field-agnostic: the
scaffolding contains no enumerated industries, named companies, or role
titles. Profile content passes through verbatim — the LLM is responsible
for reading and reasoning about it.
"""

from __future__ import annotations

_TEMPLATE = """\
The candidate profile is below, between the delimiters. Read it carefully.
Pay particular attention to the sections named: Core Competencies, Career
Summary, Target Roles (or Target Role), Target Companies / Organizations.

The Target Companies / Organizations section is a seed, not the universe.
Augment it with companies the candidate has not named, grouped into the
three clusters described in your role.

=== BEGIN CANDIDATE PROFILE ===
{profile}
=== END CANDIDATE PROFILE ===

Now produce the discovered-companies markdown per your role's output
format. Cite every company. If the profile lacks the required sections,
respond with the literal text INSUFFICIENT_PROFILE and nothing else.
"""


def build_prompt(profile_text: str) -> str:
    """Return the user-prompt string for the company_discoverer role.

    Pure function: same input, same output. The profile is embedded
    verbatim — no paraphrasing, no field-specific scaffolding.
    """
    return _TEMPLATE.format(profile=profile_text.strip())
```

- [ ] **Step 5: Run tests; expect all pass.**

Run: `uv run pytest tests/discoverer/test_prompt.py -v`
Expected: all 5 tests pass.

- [ ] **Step 6: Commit.**

```bash
git add src/findajob/discoverer/__init__.py src/findajob/discoverer/prompt.py tests/discoverer/__init__.py tests/discoverer/test_prompt.py
git commit -m "feat(discoverer): add prompt builder (#284)"
```

---

### Task 4: Implement `parser.py` with golden fixtures (TDD)

**Files:**
- Create: `src/findajob/discoverer/parser.py`
- Create: `tests/discoverer/test_parser.py`
- Create: `tests/fixtures/discoverer/valid_three_clusters.md`
- Create: `tests/fixtures/discoverer/valid_two_clusters.md`
- Create: `tests/fixtures/discoverer/invalid_one_cluster.md`
- Create: `tests/fixtures/discoverer/invalid_two_companies.md`
- Create: `tests/fixtures/discoverer/invalid_missing_channel.md`
- Create: `tests/fixtures/discoverer/valid_with_extra_whitespace.md`
- Create: `tests/fixtures/discoverer/valid_unknown_channel.md`

`parser.parse_markdown(md_text: str) -> ParseResult` validates and structures the LLM output. Validation gates: ≥3 companies total, ≥2 clusters present, every entry has non-empty `name`+`cluster`+`channel`+`reasoning`. Footer `[N]` indices resolve to URLs. Failure raises `DiscoveryParseError` naming the gate.

**Steps:**

- [ ] **Step 1: Write the seven fixtures.** Each fixture is the markdown output the LLM would produce. They drive the parser tests.

`tests/fixtures/discoverer/valid_three_clusters.md`:
```markdown
# Discovered Companies — generated 2026-04-26

Generated by findajob `company_discoverer` (model: openrouter:perplexity/sonar-reasoning-pro).
This file augments — does not replace — the `## Target Companies / Organizations`
section in `profile.md`.

## Cluster: Direct domain match

- **Alpha Co** — channel=greenhouse. Reasoning: Direct match on competency A. Citations: [1], [2].
- **Beta Inc** — channel=ashby. Reasoning: Hiring shape aligns with target roles. Citations: [3].

## Cluster: Transferable-competency adjacency

- **Gamma LLC** — channel=lever. Reasoning: Adjacent industry, same skill stack. Citations: [4].

## Cluster: Cross-industry application

- **Delta Org** — channel=in_house. Reasoning: Unrelated industry but needs the work pattern the candidate has done. Citations: [5], [6].

## References

[1] https://alpha.example.com/careers
[2] https://alpha.example.com/news
[3] https://beta.example.com/jobs
[4] https://gamma.example.com/about
[5] https://delta.example.org/work
[6] https://delta.example.org/team
```

`tests/fixtures/discoverer/valid_two_clusters.md`:
```markdown
# Discovered Companies — generated 2026-04-26

## Cluster: Direct domain match

- **Alpha Co** — channel=greenhouse. Reasoning: Direct match. Citations: [1].
- **Beta Inc** — channel=ashby. Reasoning: Hiring shape aligns. Citations: [2].

## Cluster: Transferable-competency adjacency

- **Gamma LLC** — channel=lever. Reasoning: Adjacent industry. Citations: [3].

## References

[1] https://alpha.example.com
[2] https://beta.example.com
[3] https://gamma.example.com
```

`tests/fixtures/discoverer/invalid_one_cluster.md`:
```markdown
# Discovered Companies — generated 2026-04-26

## Cluster: Direct domain match

- **Alpha Co** — channel=greenhouse. Reasoning: Direct match. Citations: [1].
- **Beta Inc** — channel=ashby. Reasoning: Hiring shape aligns. Citations: [2].
- **Gamma LLC** — channel=lever. Reasoning: Adjacent. Citations: [3].

## References

[1] https://alpha.example.com
[2] https://beta.example.com
[3] https://gamma.example.com
```

`tests/fixtures/discoverer/invalid_two_companies.md`:
```markdown
# Discovered Companies — generated 2026-04-26

## Cluster: Direct domain match

- **Alpha Co** — channel=greenhouse. Reasoning: Direct match. Citations: [1].

## Cluster: Transferable-competency adjacency

- **Beta Inc** — channel=ashby. Reasoning: Hiring shape aligns. Citations: [2].

## References

[1] https://alpha.example.com
[2] https://beta.example.com
```

`tests/fixtures/discoverer/invalid_missing_channel.md`:
```markdown
# Discovered Companies — generated 2026-04-26

## Cluster: Direct domain match

- **Alpha Co** — Reasoning: Missing channel field. Citations: [1].
- **Beta Inc** — channel=ashby. Reasoning: Hiring shape aligns. Citations: [2].

## Cluster: Transferable-competency adjacency

- **Gamma LLC** — channel=lever. Reasoning: Adjacent industry. Citations: [3].

## References

[1] https://alpha.example.com
[2] https://beta.example.com
[3] https://gamma.example.com
```

`tests/fixtures/discoverer/valid_with_extra_whitespace.md`:
```markdown
# Discovered Companies — generated 2026-04-26



## Cluster: Direct domain match

- **Alpha Co** — channel=greenhouse. Reasoning: Direct match. Citations: [1].

## Cluster: Transferable-competency adjacency

- **Beta Inc** — channel=ashby. Reasoning: Hiring shape aligns. Citations: [2].
- **Gamma LLC** — channel=lever. Reasoning: Adjacent industry. Citations: [3].


## References

   [1]   https://alpha.example.com
[2]https://beta.example.com
   [3] https://gamma.example.com

```

`tests/fixtures/discoverer/valid_unknown_channel.md`:
```markdown
# Discovered Companies — generated 2026-04-26

## Cluster: Direct domain match

- **Alpha Co** — channel=unknown. Reasoning: Public hiring channel not discoverable. Citations: [1].
- **Beta Inc** — channel=ashby. Reasoning: Hiring shape aligns. Citations: [2].

## Cluster: Cross-industry application

- **Gamma LLC** — channel=lever. Reasoning: Cross-industry fit. Citations: [3].

## References

[1] https://alpha.example.com
[2] https://beta.example.com
[3] https://gamma.example.com
```

- [ ] **Step 2: Write the failing tests.**

`tests/discoverer/test_parser.py`:
```python
from pathlib import Path

import pytest

from findajob.discoverer.parser import (
    CompanyEntry,
    DiscoveryParseError,
    parse_markdown,
)

FIXTURES = Path(__file__).parent.parent / "fixtures" / "discoverer"


def _read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_valid_three_clusters_parses_to_six_entries() -> None:
    result = parse_markdown(_read("valid_three_clusters.md"))
    assert len(result.companies) == 6
    by_cluster = {c.name: c.cluster for c in result.companies}
    assert by_cluster["Alpha Co"] == "direct"
    assert by_cluster["Beta Inc"] == "direct"
    assert by_cluster["Gamma LLC"] == "adjacency"
    assert by_cluster["Delta Org"] == "cross_industry"


def test_valid_three_clusters_resolves_per_row_citations() -> None:
    result = parse_markdown(_read("valid_three_clusters.md"))
    alpha = next(c for c in result.companies if c.name == "Alpha Co")
    assert alpha.citations == [
        "https://alpha.example.com/careers",
        "https://alpha.example.com/news",
    ]
    delta = next(c for c in result.companies if c.name == "Delta Org")
    assert delta.citations == [
        "https://delta.example.org/work",
        "https://delta.example.org/team",
    ]


def test_valid_three_clusters_extracts_channels() -> None:
    result = parse_markdown(_read("valid_three_clusters.md"))
    by_channel = {c.name: c.channel for c in result.companies}
    assert by_channel["Alpha Co"] == "greenhouse"
    assert by_channel["Beta Inc"] == "ashby"
    assert by_channel["Gamma LLC"] == "lever"
    assert by_channel["Delta Org"] == "in_house"


def test_valid_two_clusters_passes_minimum_gates() -> None:
    result = parse_markdown(_read("valid_two_clusters.md"))
    assert len(result.companies) == 3
    clusters = {c.cluster for c in result.companies}
    assert clusters == {"direct", "adjacency"}


def test_valid_unknown_channel_is_accepted() -> None:
    result = parse_markdown(_read("valid_unknown_channel.md"))
    alpha = next(c for c in result.companies if c.name == "Alpha Co")
    assert alpha.channel == "unknown"


def test_valid_with_extra_whitespace_in_references_resolves_correctly() -> None:
    result = parse_markdown(_read("valid_with_extra_whitespace.md"))
    by_name = {c.name: c.citations for c in result.companies}
    assert by_name["Alpha Co"] == ["https://alpha.example.com"]
    assert by_name["Beta Inc"] == ["https://beta.example.com"]
    assert by_name["Gamma LLC"] == ["https://gamma.example.com"]


def test_invalid_one_cluster_raises_with_clear_message() -> None:
    with pytest.raises(DiscoveryParseError) as excinfo:
        parse_markdown(_read("invalid_one_cluster.md"))
    assert "at least 2 clusters" in str(excinfo.value).lower()


def test_invalid_two_companies_raises_with_clear_message() -> None:
    with pytest.raises(DiscoveryParseError) as excinfo:
        parse_markdown(_read("invalid_two_companies.md"))
    assert "at least 3 companies" in str(excinfo.value).lower()


def test_invalid_missing_channel_raises_with_clear_message() -> None:
    with pytest.raises(DiscoveryParseError) as excinfo:
        parse_markdown(_read("invalid_missing_channel.md"))
    msg = str(excinfo.value).lower()
    assert "channel" in msg and "alpha co" in msg


def test_company_entry_is_frozen() -> None:
    entry = CompanyEntry(
        name="X", cluster="direct", channel="greenhouse",
        reasoning="r", citations=("u",),
    )
    with pytest.raises((AttributeError, Exception)):
        entry.name = "Y"  # type: ignore[misc]


def test_parse_markdown_returns_clean_markdown() -> None:
    md = _read("valid_three_clusters.md")
    result = parse_markdown(md)
    # Clean markdown is the input minus any think-block residue.
    # For valid input, it equals the input (modulo strip).
    assert result.markdown_clean.strip() == md.strip()
```

- [ ] **Step 3: Run tests; expect ImportError.**

Run: `uv run pytest tests/discoverer/test_parser.py -v`
Expected: collection error.

- [ ] **Step 4: Implement `parser.py`.**

`src/findajob/discoverer/parser.py`:
```python
"""Markdown -> structured parser for the company_discoverer output.

Validates the LLM's emitted markdown against the schema in
`docs/superpowers/specs/2026-04-26-company-discoverer-design.md` §5.1
and produces a list of :class:`CompanyEntry` records suitable for the
JSON sidecar (§5.2).

Pure module: re, dataclasses. No filesystem access.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

VALID_CLUSTERS: frozenset[str] = frozenset({"direct", "adjacency", "cross_industry"})
VALID_CHANNELS: frozenset[str] = frozenset(
    {"greenhouse", "ashby", "lever", "workday", "in_house", "unknown"}
)

_CLUSTER_HEADING_RE = re.compile(
    r"^##\s+Cluster:\s+(?P<label>.+?)\s*$",
    re.MULTILINE,
)
# Row format:
#   - **Name** — channel=foo. Reasoning: ... Citations: [1], [2].
_ROW_RE = re.compile(
    r"^\s*-\s+\*\*(?P<name>[^*]+?)\*\*\s*[—-]\s*"
    r"channel=(?P<channel>[a-z_]+)\.\s*"
    r"Reasoning:\s*(?P<reasoning>.+?)\s*"
    r"Citations:\s*(?P<cites>(?:\[\d+\],?\s*)+)\s*\.?\s*$",
    re.MULTILINE,
)
_CITE_INDEX_RE = re.compile(r"\[(\d+)\]")
_REFERENCES_HEADING_RE = re.compile(r"^##\s+References\s*$", re.MULTILINE)
_REF_LINE_RE = re.compile(r"^\s*\[(\d+)\]\s*(\S.*?)\s*$", re.MULTILINE)


_LABEL_TO_CLUSTER: dict[str, str] = {
    "direct domain match": "direct",
    "transferable-competency adjacency": "adjacency",
    "cross-industry application": "cross_industry",
}


@dataclass(frozen=True)
class CompanyEntry:
    name: str
    cluster: str
    channel: str
    reasoning: str
    citations: tuple[str, ...]


@dataclass(frozen=True)
class ParseResult:
    markdown_clean: str
    companies: list[CompanyEntry] = field(default_factory=list)


class DiscoveryParseError(ValueError):
    """Raised when the LLM output fails a validation gate."""


def _resolve_references(md: str) -> dict[int, str]:
    ref_match = _REFERENCES_HEADING_RE.search(md)
    if not ref_match:
        return {}
    tail = md[ref_match.end():]
    return {int(i): url.strip() for i, url in _REF_LINE_RE.findall(tail)}


def _label_to_cluster(label: str) -> str | None:
    return _LABEL_TO_CLUSTER.get(label.strip().lower())


def parse_markdown(md_text: str) -> ParseResult:
    """Parse ``md_text`` into a :class:`ParseResult`.

    Raises :class:`DiscoveryParseError` if any validation gate fails
    (≥3 companies, ≥2 clusters, well-formed rows, resolvable citations).
    """
    refs = _resolve_references(md_text)
    cluster_headings = list(_CLUSTER_HEADING_RE.finditer(md_text))
    companies: list[CompanyEntry] = []
    seen_clusters: set[str] = set()

    for i, h in enumerate(cluster_headings):
        cluster = _label_to_cluster(h.group("label"))
        if cluster is None:
            continue
        section_start = h.end()
        section_end = cluster_headings[i + 1].start() if i + 1 < len(cluster_headings) else len(md_text)
        ref_match = _REFERENCES_HEADING_RE.search(md_text, section_start, section_end)
        if ref_match:
            section_end = ref_match.start()
        section = md_text[section_start:section_end]
        for row in _ROW_RE.finditer(section):
            name = row.group("name").strip()
            channel = row.group("channel").strip()
            reasoning = row.group("reasoning").strip().rstrip(".").strip()
            cites_raw = row.group("cites")
            cite_indices = [int(m.group(1)) for m in _CITE_INDEX_RE.finditer(cites_raw)]
            citations = tuple(refs[i] for i in cite_indices if i in refs)
            if not name:
                raise DiscoveryParseError(f"company entry has empty name in cluster {cluster!r}")
            if channel not in VALID_CHANNELS:
                raise DiscoveryParseError(
                    f"company {name!r} has invalid channel {channel!r} (must be one of {sorted(VALID_CHANNELS)})"
                )
            if not reasoning:
                raise DiscoveryParseError(f"company {name!r} has empty reasoning")
            companies.append(
                CompanyEntry(
                    name=name,
                    cluster=cluster,
                    channel=channel,
                    reasoning=reasoning,
                    citations=citations,
                )
            )
            seen_clusters.add(cluster)

    # Detect malformed rows that didn't match the row regex but should have:
    # any cluster section that contains "channel=" but yielded no parsed rows.
    for i, h in enumerate(cluster_headings):
        cluster = _label_to_cluster(h.group("label"))
        if cluster is None:
            continue
        section_start = h.end()
        section_end = cluster_headings[i + 1].start() if i + 1 < len(cluster_headings) else len(md_text)
        ref_match = _REFERENCES_HEADING_RE.search(md_text, section_start, section_end)
        if ref_match:
            section_end = ref_match.start()
        section = md_text[section_start:section_end]
        # Find bullet rows the strict row regex missed (e.g., missing channel)
        bullet_lines = [ln for ln in section.splitlines() if ln.lstrip().startswith("- **")]
        for ln in bullet_lines:
            if not _ROW_RE.match(ln):
                # Try to extract a name for a useful error
                m = re.search(r"\*\*([^*]+)\*\*", ln)
                bad_name = m.group(1).strip() if m else "<unknown>"
                if "channel=" not in ln:
                    raise DiscoveryParseError(
                        f"company {bad_name!r} is missing channel field in cluster {cluster!r}"
                    )
                raise DiscoveryParseError(
                    f"company {bad_name!r} row is malformed in cluster {cluster!r}"
                )

    if len(companies) < 3:
        raise DiscoveryParseError(
            f"validation: at least 3 companies required, got {len(companies)}"
        )
    if len(seen_clusters) < 2:
        raise DiscoveryParseError(
            f"validation: at least 2 clusters required, got {sorted(seen_clusters)}"
        )

    return ParseResult(markdown_clean=md_text.strip(), companies=companies)
```

- [ ] **Step 5: Run tests; expect all pass.**

Run: `uv run pytest tests/discoverer/test_parser.py -v`
Expected: 11 tests pass.

- [ ] **Step 6: Commit.**

```bash
git add src/findajob/discoverer/parser.py tests/discoverer/test_parser.py tests/fixtures/discoverer/
git commit -m "feat(discoverer): add markdown parser with validation gates (#284)"
```

---

### Task 5: Implement `writer.py` (TDD)

**Files:**
- Create: `src/findajob/discoverer/writer.py`
- Create: `tests/discoverer/test_writer.py`

`writer.commit_atomically(base_root, markdown, json_payload) -> Path` writes both `discovered_companies.md` and `discovered_companies.json` to `base_root/candidate_context/` via temp+replace. Pre-existing good output is backed up to `base_root/.backups/{stamp}/` first. Mirrors `findajob.onboarding.injector.backup_existing()` and atomic temp+replace pattern (lines 80-95 + 158-201 of `injector.py`).

**Steps:**

- [ ] **Step 1: Write the failing tests.**

`tests/discoverer/test_writer.py`:
```python
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from findajob.discoverer.writer import commit_atomically


def _payload() -> dict:
    return {
        "generated_at": "2026-04-26",
        "model": "openrouter:perplexity/sonar-reasoning-pro",
        "companies": [
            {"name": "Alpha", "cluster": "direct", "channel": "greenhouse",
             "reasoning": "x", "citations": ["https://example.com"]},
        ],
    }


def test_commit_atomically_writes_both_files(tmp_path: Path) -> None:
    md_path = commit_atomically(tmp_path, "# md\n\nhello\n", _payload())
    assert md_path == tmp_path / "candidate_context" / "discovered_companies.md"
    assert md_path.read_text() == "# md\n\nhello\n"
    json_path = tmp_path / "candidate_context" / "discovered_companies.json"
    assert json.loads(json_path.read_text())["companies"][0]["name"] == "Alpha"


def test_commit_atomically_creates_parent_dir(tmp_path: Path) -> None:
    # candidate_context/ does not exist yet
    assert not (tmp_path / "candidate_context").exists()
    commit_atomically(tmp_path, "x", _payload())
    assert (tmp_path / "candidate_context").is_dir()


def test_commit_atomically_backs_up_pre_existing_files(tmp_path: Path) -> None:
    cc = tmp_path / "candidate_context"
    cc.mkdir()
    (cc / "discovered_companies.md").write_text("OLD MD\n")
    (cc / "discovered_companies.json").write_text('{"companies": []}\n')
    commit_atomically(tmp_path, "NEW MD\n", _payload())
    # New content in place
    assert (cc / "discovered_companies.md").read_text() == "NEW MD\n"
    # Backup directory contains the old content
    backups = sorted((tmp_path / ".backups").iterdir())
    assert len(backups) == 1
    bdir = backups[0]
    assert (bdir / "candidate_context" / "discovered_companies.md").read_text() == "OLD MD\n"
    assert (bdir / "candidate_context" / "discovered_companies.json").read_text() == '{"companies": []}\n'


def test_commit_atomically_rolls_back_on_replace_failure(tmp_path: Path) -> None:
    """If os.replace fails on the second file, the first file's prior state
    is preserved (last-good invariant).
    """
    cc = tmp_path / "candidate_context"
    cc.mkdir()
    (cc / "discovered_companies.md").write_text("OLD MD\n")
    (cc / "discovered_companies.json").write_text("OLD JSON\n")

    import findajob.discoverer.writer as wr
    real_replace = wr.os.replace
    calls = {"n": 0}

    def flaky(src, dst):
        calls["n"] += 1
        if calls["n"] == 2:
            raise OSError("simulated failure on second replace")
        return real_replace(src, dst)

    with patch.object(wr.os, "replace", side_effect=flaky):
        with pytest.raises(OSError):
            commit_atomically(tmp_path, "NEW MD\n", _payload())

    # First file may have been replaced (atomicity is per-file via os.replace);
    # second file MUST still be the old content.
    assert (cc / "discovered_companies.json").read_text() == "OLD JSON\n"
    # No tempfile residue
    leftovers = [p for p in cc.iterdir() if p.name.startswith("discovered_companies.") and ".tmp" in p.name]
    assert leftovers == []
```

- [ ] **Step 2: Run tests; expect ImportError.**

Run: `uv run pytest tests/discoverer/test_writer.py -v`
Expected: collection error.

- [ ] **Step 3: Implement `writer.py`.**

`src/findajob/discoverer/writer.py`:
```python
"""Atomic temp+replace writer for the discoverer output pair.

Mirrors the pattern in `findajob.onboarding.injector` (atomic staging,
rollback on failure, rolling backup of pre-existing destinations).

Pure-ish module: stdlib only (os, json, shutil, tempfile, datetime,
pathlib). No FastAPI, no findajob imports.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path

_MD_RELPATH = "candidate_context/discovered_companies.md"
_JSON_RELPATH = "candidate_context/discovered_companies.json"
_BACKUP_ROOT = ".backups"


def _utc_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _backup_existing(base_root: Path, stamp: str) -> Path | None:
    """Copy any pre-existing output pair to `.backups/{stamp}/`.

    Returns the backup directory path if a backup was made, else None.
    """
    paths = [base_root / _MD_RELPATH, base_root / _JSON_RELPATH]
    if not any(p.is_file() for p in paths):
        return None
    dest_root = base_root / _BACKUP_ROOT / stamp
    dest_root.mkdir(parents=True, exist_ok=True)
    for src in paths:
        if not src.is_file():
            continue
        target = dest_root / src.relative_to(base_root)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, target)
    return dest_root


def commit_atomically(
    base_root: Path,
    markdown: str,
    json_payload: dict,
) -> Path:
    """Write the markdown + JSON sidecar atomically.

    Pre-existing files at the destinations are backed up to
    ``base_root/.backups/{utc_stamp}/`` before any write. Each file is
    staged via :func:`tempfile.mkstemp` in the destination directory then
    committed via :func:`os.replace`.

    On any staging failure, all temp files created by this run are
    cleaned up and the exception propagates. Pre-existing destination
    files are not modified by a staging failure.

    Returns the absolute path of the markdown file on success.
    """
    md_dest = base_root / _MD_RELPATH
    json_dest = base_root / _JSON_RELPATH
    md_dest.parent.mkdir(parents=True, exist_ok=True)

    stamp = _utc_stamp()
    _backup_existing(base_root, stamp)

    tempfiles: list[tuple[str, Path]] = []
    try:
        # Stage markdown
        fd, tmp_md = tempfile.mkstemp(prefix=md_dest.name + ".", suffix=".tmp", dir=str(md_dest.parent))
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
            fh.write(markdown)
        tempfiles.append((tmp_md, md_dest))

        # Stage JSON
        fd, tmp_json = tempfile.mkstemp(prefix=json_dest.name + ".", suffix=".tmp", dir=str(json_dest.parent))
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
            json.dump(json_payload, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        tempfiles.append((tmp_json, json_dest))

        # Commit
        for tmp_name, dest in tempfiles:
            os.replace(tmp_name, dest)
        tempfiles = []
    except Exception:
        for tmp_name, _dest in tempfiles:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
        raise

    return md_dest
```

- [ ] **Step 4: Run tests; expect all pass.**

Run: `uv run pytest tests/discoverer/test_writer.py -v`
Expected: 4 tests pass.

- [ ] **Step 5: Commit.**

```bash
git add src/findajob/discoverer/writer.py tests/discoverer/test_writer.py
git commit -m "feat(discoverer): add atomic temp+replace writer (#284)"
```

---

### Task 6: Implement `runner.py` orchestration (TDD)

**Files:**
- Create: `src/findajob/discoverer/runner.py`
- Modify: `src/findajob/discoverer/__init__.py`
- Create: `tests/discoverer/test_runner.py`

`runner.run(base_root, profile_path=None, ntfy_enabled=True) -> RunResult` is the orchestration entry. Reads profile → builds prompt → subprocesses to `aichat-ng` → strips `<think>` → parses → calls writer → logs + ntfy. Returns `RunResult(success, count, error, cost_usd)`. Mirrors `aichat()` helper at `scripts/prep_application.py:40-52`.

**Steps:**

- [ ] **Step 1: Write the failing tests.**

`tests/discoverer/test_runner.py`:
```python
import json
import os
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from findajob.discoverer.runner import RunResult, run


VALID_LLM_OUTPUT = """\
# Discovered Companies — generated 2026-04-26

## Cluster: Direct domain match

- **Alpha Co** — channel=greenhouse. Reasoning: Direct match. Citations: [1].
- **Beta Inc** — channel=ashby. Reasoning: Hiring shape aligns. Citations: [2].

## Cluster: Transferable-competency adjacency

- **Gamma LLC** — channel=lever. Reasoning: Adjacent industry. Citations: [3].

## References

[1] https://alpha.example.com
[2] https://beta.example.com
[3] https://gamma.example.com
"""


def _setup_profile(base_root: Path) -> Path:
    cc = base_root / "candidate_context"
    cc.mkdir(parents=True, exist_ok=True)
    p = cc / "profile.md"
    p.write_text(
        "## Identity\nName: T\n\n## Core Competencies\n- A\n\n"
        "## Career Summary\nx\n\n## Target Roles\nr\n\n"
        "## Target Companies / Organizations\nAcme.\n",
        encoding="utf-8",
    )
    return p


def _stub_subprocess_run(stdout: str, returncode: int = 0):
    completed = MagicMock(spec=subprocess.CompletedProcess)
    completed.stdout = stdout
    completed.stderr = ""
    completed.returncode = returncode
    return MagicMock(return_value=completed)


def test_run_happy_path_writes_both_files_and_returns_success(tmp_path: Path) -> None:
    _setup_profile(tmp_path)
    with patch("findajob.discoverer.runner.subprocess.run", _stub_subprocess_run(VALID_LLM_OUTPUT)):
        result = run(tmp_path, ntfy_enabled=False)
    assert result.success is True
    assert result.count == 3
    assert result.error is None
    md = (tmp_path / "candidate_context" / "discovered_companies.md").read_text()
    assert "Alpha Co" in md
    payload = json.loads((tmp_path / "candidate_context" / "discovered_companies.json").read_text())
    assert len(payload["companies"]) == 3


def test_run_strips_think_blocks_before_parser(tmp_path: Path) -> None:
    _setup_profile(tmp_path)
    output = "<think>I'm reasoning.</think>\n" + VALID_LLM_OUTPUT
    with patch("findajob.discoverer.runner.subprocess.run", _stub_subprocess_run(output)):
        result = run(tmp_path, ntfy_enabled=False)
    assert result.success is True
    md = (tmp_path / "candidate_context" / "discovered_companies.md").read_text()
    assert "<think>" not in md


def test_run_parse_failure_returns_failure_and_leaves_disk_untouched(tmp_path: Path) -> None:
    _setup_profile(tmp_path)
    bad_output = "## Cluster: Direct domain match\n- **A** — channel=greenhouse. Reasoning: x. Citations: [1].\n## References\n[1] https://example.com"
    with patch("findajob.discoverer.runner.subprocess.run", _stub_subprocess_run(bad_output)):
        result = run(tmp_path, ntfy_enabled=False)
    assert result.success is False
    assert result.error and "at least 3 companies" in result.error.lower()
    assert not (tmp_path / "candidate_context" / "discovered_companies.md").exists()
    assert not (tmp_path / "candidate_context" / "discovered_companies.json").exists()


def test_run_subprocess_failure_returns_failure(tmp_path: Path) -> None:
    _setup_profile(tmp_path)
    with patch(
        "findajob.discoverer.runner.subprocess.run",
        _stub_subprocess_run("", returncode=1),
    ):
        result = run(tmp_path, ntfy_enabled=False)
    assert result.success is False
    assert result.error is not None


def test_run_missing_profile_returns_failure(tmp_path: Path) -> None:
    # No profile.md at all
    result = run(tmp_path, ntfy_enabled=False)
    assert result.success is False
    assert result.error is not None
    assert "profile" in result.error.lower()


def test_run_does_not_overwrite_last_good_on_failure(tmp_path: Path) -> None:
    _setup_profile(tmp_path)
    cc = tmp_path / "candidate_context"
    (cc / "discovered_companies.md").write_text("LAST GOOD\n")
    (cc / "discovered_companies.json").write_text('{"companies": []}\n')
    with patch(
        "findajob.discoverer.runner.subprocess.run",
        _stub_subprocess_run("INSUFFICIENT_PROFILE"),
    ):
        result = run(tmp_path, ntfy_enabled=False)
    assert result.success is False
    assert (cc / "discovered_companies.md").read_text() == "LAST GOOD\n"
    assert (cc / "discovered_companies.json").read_text() == '{"companies": []}\n'


def test_run_emits_ntfy_when_threshold_breached(tmp_path: Path, monkeypatch) -> None:
    _setup_profile(tmp_path)
    monkeypatch.setenv("DISCOVERY_COST_THRESHOLD_USD", "1.00")
    notify_mock = MagicMock()
    with (
        patch("findajob.discoverer.runner.subprocess.run", _stub_subprocess_run(VALID_LLM_OUTPUT)),
        patch("findajob.discoverer.runner._extract_cost_usd", return_value=5.50),
        patch("findajob.discoverer.runner._send_ntfy", notify_mock),
    ):
        result = run(tmp_path, ntfy_enabled=True)
    assert result.success is True
    assert notify_mock.called
    title, body = notify_mock.call_args.args[:2]
    assert "cost" in body.lower()


def test_run_does_not_emit_ntfy_when_disabled(tmp_path: Path) -> None:
    _setup_profile(tmp_path)
    notify_mock = MagicMock()
    with (
        patch("findajob.discoverer.runner.subprocess.run", _stub_subprocess_run("INSUFFICIENT_PROFILE")),
        patch("findajob.discoverer.runner._send_ntfy", notify_mock),
    ):
        run(tmp_path, ntfy_enabled=False)
    assert not notify_mock.called
```

- [ ] **Step 2: Run tests; expect ImportError.**

Run: `uv run pytest tests/discoverer/test_runner.py -v`
Expected: collection error.

- [ ] **Step 3: Implement `runner.py`.**

`src/findajob/discoverer/runner.py`:
```python
"""Orchestration for the company_discoverer pipeline (#284).

Reads the candidate profile, builds the prompt, calls aichat-ng,
strips think-block residue, parses, validates, and atomically writes
the output pair. On any failure: logs to pipeline.jsonl, optionally
ntfys, and returns a failure RunResult without raising.

Mirrors the `aichat()` helper pattern at scripts/prep_application.py:40-52.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import NamedTuple

from findajob.discoverer.parser import DiscoveryParseError, parse_markdown
from findajob.discoverer.prompt import build_prompt
from findajob.discoverer.writer import commit_atomically
from findajob.paths import AICHAT, BASE
from findajob.utils import log_event


_DEFAULT_TIMEOUT_S = 540  # under cron's 600s timeout, room for IO
_DEFAULT_COST_THRESHOLD_USD = 10.00
_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


class RunResult(NamedTuple):
    success: bool
    count: int
    error: str | None
    cost_usd: float | None


def _extract_cost_usd(stderr: str) -> float | None:
    """Parse aichat-ng stderr for the per-call cost line, if present.

    aichat-ng emits a `usage` line on stderr when verbose. The exact format
    depends on the OpenRouter provider's reporting; for sonar-reasoning-pro
    the line includes a `total_cost` field. Returns None if no line matches.
    """
    m = re.search(r"total_cost[^0-9]*([0-9]+\.[0-9]+)", stderr or "")
    if m:
        return float(m.group(1))
    return None


def _send_ntfy(title: str, body: str) -> None:
    """Best-effort ntfy via scripts/notify.py send-raw.

    Uses subprocess to call the existing notify.py CLI; suppresses any
    error so a notification failure cannot mask a successful run.
    """
    try:
        subprocess.run(
            [sys.executable, str(Path(BASE) / "scripts" / "notify.py"), "send-raw", title, body],
            check=False,
            capture_output=True,
            timeout=15,
        )
    except Exception:
        pass


def _cost_threshold() -> float:
    raw = os.environ.get("DISCOVERY_COST_THRESHOLD_USD", "")
    try:
        return float(raw) if raw else _DEFAULT_COST_THRESHOLD_USD
    except ValueError:
        return _DEFAULT_COST_THRESHOLD_USD


def run(
    base_root: Path,
    profile_path: Path | None = None,
    ntfy_enabled: bool = True,
) -> RunResult:
    """Run the full discovery pipeline. Never raises.

    Returns a :class:`RunResult` describing success/failure and metadata.
    """
    profile = profile_path or (base_root / "candidate_context" / "profile.md")
    if not profile.is_file():
        msg = f"profile not found at {profile}"
        log_event("discovery_failed", reason="profile_missing", path=str(profile))
        if ntfy_enabled:
            _send_ntfy("discovery: profile missing", msg)
        return RunResult(success=False, count=0, error=msg, cost_usd=None)

    try:
        profile_text = profile.read_text(encoding="utf-8")
        prompt = build_prompt(profile_text)
        completed = subprocess.run(
            [AICHAT, "--role", "company_discoverer", "-S", prompt],
            capture_output=True,
            text=True,
            timeout=_DEFAULT_TIMEOUT_S,
        )
        if completed.returncode != 0 or not completed.stdout.strip():
            stderr = (completed.stderr or "")[:500]
            log_event(
                "discovery_failed",
                reason="aichat_returncode",
                returncode=completed.returncode,
                stderr=stderr.strip(),
            )
            if ntfy_enabled:
                _send_ntfy("discovery: aichat failed", f"returncode={completed.returncode}\n{stderr[:200]}")
            return RunResult(success=False, count=0, error=f"aichat failed (rc={completed.returncode})", cost_usd=None)

        raw_md = _THINK_RE.sub("", completed.stdout).strip()
        if raw_md == "INSUFFICIENT_PROFILE":
            log_event("discovery_failed", reason="insufficient_profile")
            if ntfy_enabled:
                _send_ntfy("discovery: insufficient profile", "LLM returned INSUFFICIENT_PROFILE")
            return RunResult(success=False, count=0, error="LLM returned INSUFFICIENT_PROFILE", cost_usd=None)

        parsed = parse_markdown(raw_md)
        json_payload: dict = {
            "generated_at": datetime.now(UTC).strftime("%Y-%m-%d"),
            "model": "openrouter:perplexity/sonar-reasoning-pro",
            "companies": [
                {
                    "name": c.name,
                    "cluster": c.cluster,
                    "channel": c.channel,
                    "reasoning": c.reasoning,
                    "citations": list(c.citations),
                }
                for c in parsed.companies
            ],
        }
        commit_atomically(base_root, parsed.markdown_clean + "\n", json_payload)

        cost = _extract_cost_usd(completed.stderr)
        log_event(
            "discovery_complete",
            count=len(parsed.companies),
            cost_usd=cost,
        )
        threshold = _cost_threshold()
        if cost is not None and cost > threshold and ntfy_enabled:
            _send_ntfy(
                "discovery: cost exceeded threshold",
                f"run cost ${cost:.2f} > threshold ${threshold:.2f} (still wrote {len(parsed.companies)} companies)",
            )
        return RunResult(success=True, count=len(parsed.companies), error=None, cost_usd=cost)

    except subprocess.TimeoutExpired:
        msg = f"aichat timeout after {_DEFAULT_TIMEOUT_S}s"
        log_event("discovery_failed", reason="timeout", timeout_s=_DEFAULT_TIMEOUT_S)
        if ntfy_enabled:
            _send_ntfy("discovery: timeout", msg)
        return RunResult(success=False, count=0, error=msg, cost_usd=None)
    except DiscoveryParseError as e:
        msg = str(e)
        log_event("discovery_failed", reason="parse_error", message=msg)
        if ntfy_enabled:
            _send_ntfy("discovery: parse error", msg[:200])
        return RunResult(success=False, count=0, error=msg, cost_usd=None)
    except Exception as e:  # noqa: BLE001 — guarantee never-raise contract
        msg = f"{type(e).__name__}: {e}"
        log_event("discovery_failed", reason="unhandled", message=msg)
        if ntfy_enabled:
            _send_ntfy("discovery: unhandled error", msg[:200])
        return RunResult(success=False, count=0, error=msg, cost_usd=None)
```

- [ ] **Step 4: Re-export from package init.**

Replace `src/findajob/discoverer/__init__.py` with:
```python
"""findajob.discoverer — competency-driven company discovery (#284)."""

from findajob.discoverer.runner import RunResult, run

__all__ = ["RunResult", "run"]
```

- [ ] **Step 5: Run tests; expect all pass.**

Run: `uv run pytest tests/discoverer/test_runner.py -v`
Expected: 8 tests pass.

- [ ] **Step 6: Run the full discoverer suite.**

Run: `uv run pytest tests/discoverer/ -v`
Expected: 28 tests pass (5 prompt + 11 parser + 4 writer + 8 runner).

- [ ] **Step 7: Commit.**

```bash
git add src/findajob/discoverer/runner.py src/findajob/discoverer/__init__.py tests/discoverer/test_runner.py
git commit -m "feat(discoverer): add runner orchestration with cost guardrail (#284)"
```

---

### Task 7: Add `scripts/discover_companies.py` CLI entry point

**Files:**
- Create: `scripts/discover_companies.py`

Thin CLI wrapper around `findajob.discoverer.run()`. Exits 0 on success, 1 on failure (cron picks up).

**Steps:**

- [ ] **Step 1: Write the script.**

`scripts/discover_companies.py`:
```python
#!/usr/bin/env python3
"""scripts/discover_companies.py — entry point for the weekly discovery cron.

Calls findajob.discoverer.run(base_root) and exits 0/1 by RunResult.success.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from findajob.discoverer import run as run_discovery
from findajob.paths import BASE


def main() -> int:
    parser = argparse.ArgumentParser(description="Discover companies for the candidate profile.")
    parser.add_argument(
        "--profile",
        type=Path,
        default=None,
        help="Path to profile.md (default: BASE/candidate_context/profile.md)",
    )
    parser.add_argument(
        "--ntfy/--no-ntfy",
        dest="ntfy",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Enable ntfy alerts on failure / cost-threshold breach (default: enabled).",
    )
    args = parser.parse_args()
    base_root = Path(BASE)
    result = run_discovery(base_root, profile_path=args.profile, ntfy_enabled=args.ntfy)
    if result.success:
        print(f"discovery: wrote {result.count} companies (cost={result.cost_usd or 'unknown'})")
        return 0
    print(f"discovery: FAILED — {result.error}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Make executable.**

Run: `chmod +x scripts/discover_companies.py`

- [ ] **Step 3: Smoke-test the `--help` interface.**

Run: `uv run python3 scripts/discover_companies.py --help`
Expected: argparse help text printed; exit 0.

- [ ] **Step 4: Commit.**

```bash
git add scripts/discover_companies.py
git commit -m "feat(discoverer): add scripts/discover_companies.py CLI (#284)"
```

---

### Task 8: Add weekly cron line to `ops/crontab`

**Files:**
- Modify: `ops/crontab`

**Steps:**

- [ ] **Step 1: Append the cron line under "Notifications" or before the RAG block.** Place it logically near other weekly jobs:

```diff
 0    8   *  *  0        python3 /app/scripts/notify.py feedback-review

+# ── Discovery (Sunday 02:00 — competency-driven company discovery, #284) ─────
+0    2   *  *  0   timeout 600 python3 /app/scripts/discover_companies.py
+
 # ── RAG rebuild (Sunday 03:00) ───────────────────────────────────────────────
 0    3   *  *  0   /usr/local/bin/aichat-ng --rag job_search_rag --rebuild-rag
```

- [ ] **Step 2: Verify the entry parses as cron syntax.**

Run: `awk '!/^#/ && NF{print}' ops/crontab | grep "discover_companies.py"`
Expected: one line printed showing `0 2 * * 0 timeout 600 python3 /app/scripts/discover_companies.py`.

- [ ] **Step 3: Commit.**

```bash
git add ops/crontab
git commit -m "feat(discoverer): add weekly cron entry — Sun 02:00 (#284)"
```

---

### Task 9: Widen `inject()` return type to `InjectResult` and add post-commit discovery hook

**Files:**
- Modify: `src/findajob/onboarding/__init__.py` (re-export)
- Modify: `src/findajob/onboarding/injector.py`
- Modify: `tests/test_onboarding_injector.py`

The injector's existing return type is `Path` (the backup directory). We widen it to a `NamedTuple` `InjectResult(backup_dir, discovery)` so the route handler can render the discovery status. Two existing inject tests call `inject(...)` and expect a Path-like return — they need to be updated to use `result.backup_dir`.

**Steps:**

- [ ] **Step 1: Read the existing `inject()` implementation and tests.**

Run: `head -30 src/findajob/onboarding/injector.py && echo --- && grep -n 'def test_inject\|inject(' tests/test_onboarding_injector.py`
Expected: see `def inject(...) -> Path:` and the two test functions that capture the return value.

- [ ] **Step 2: Modify `injector.py` to define `InjectResult` and call the discoverer post-commit.**

Edit `src/findajob/onboarding/injector.py`:

(a) After the imports block (around line 23), add:

```python
from typing import NamedTuple

# Imported lazily inside inject() to avoid a circular import on the
# discoverer side, and to keep this module importable even when the
# discoverer package isn't yet on the path during unit tests of unrelated
# subsystems.
```

(b) Below the existing top-level constants (after `_BUNDLE_DIR_RELPATH`-style declarations, around line 47), add:

```python
class DiscoveryStatus(NamedTuple):
    """Lightweight mirror of findajob.discoverer.RunResult for return.

    Kept module-local so callers don't have to import the discoverer
    package to inspect onboarding results.
    """
    success: bool
    count: int
    error: str | None


class InjectResult(NamedTuple):
    backup_dir: Path
    discovery: DiscoveryStatus
```

(c) Modify the `inject()` signature (line 127) from `-> Path` to `-> InjectResult` and modify the final `return backup_dir` (line 203) to:

```python
    # Post-commit discovery hook. Soft-fail: any failure here does NOT
    # roll back the seven-file commit (sentinel is already written).
    try:
        from findajob.discoverer import run as run_discovery
        discovery_result = run_discovery(base_root, ntfy_enabled=False)
        discovery = DiscoveryStatus(
            success=discovery_result.success,
            count=discovery_result.count,
            error=discovery_result.error,
        )
    except Exception as e:  # noqa: BLE001 — discovery must never crash onboarding
        discovery = DiscoveryStatus(success=False, count=0, error=str(e))
    return InjectResult(backup_dir=backup_dir, discovery=discovery)
```

(d) Re-export `InjectResult` and `DiscoveryStatus` from `src/findajob/onboarding/__init__.py`. The existing file imports `inject, is_complete, mark_complete` from injector and `ALLOWED_FILENAMES, ParsedEmission, parse_emission` from parser. Edit the file in place to add the two new names — minimal diff:

```diff
-from findajob.onboarding.injector import inject, is_complete, mark_complete
+from findajob.onboarding.injector import (
+    DiscoveryStatus,
+    InjectResult,
+    inject,
+    is_complete,
+    mark_complete,
+)
 from findajob.onboarding.parser import ALLOWED_FILENAMES, ParsedEmission, parse_emission

 __all__ = [
     "ALLOWED_FILENAMES",
+    "DiscoveryStatus",
+    "InjectResult",
     "ParsedEmission",
     "inject",
     "is_complete",
     "mark_complete",
     "parse_emission",
 ]
```

Also add the two names to the public-surface docstring at the top of the file:

```diff
 - :func:`parse_emission` — parse an interview emission into files to inject.
-- :func:`inject` — write parsed files atomically; return the backup dir.
+- :func:`inject` — write parsed files atomically + run discovery; return :class:`InjectResult`.
+- :class:`InjectResult` — backup_dir + DiscoveryStatus from a successful inject.
+- :class:`DiscoveryStatus` — success/count/error from the post-commit discovery hook.
 - :func:`is_complete` — True iff the sentinel file exists under ``base_root``.
 - :func:`mark_complete` — write the sentinel file with the current UTC timestamp.
```

- [ ] **Step 3: Update `tests/test_onboarding_injector.py` to match the new return type.**

Replace the body of `test_inject_writes_seven_files_and_sentinel_and_derivation`:

```python
def test_inject_writes_seven_files_and_sentinel_and_derivation(tmp_path: Path) -> None:
    result = inject(tmp_path, _MIN_FILES)
    assert result.backup_dir is not None
    # Discovery is exercised in the discoverer's own tests; here we only
    # confirm the result is shaped correctly. Discovery will fail in this
    # test environment because aichat-ng isn't on PATH, which is expected.
    assert result.discovery.success in (True, False)
    # Seven canonical files
    assert (tmp_path / "candidate_context" / "profile.md").read_text() == _MIN_FILES["profile.md"]
    # ... rest of existing assertions unchanged
```

(Apply the same `result.backup_dir` shape change to any other test that captures inject's return — search for `inject(tmp_path, _MIN_FILES)`.)

- [ ] **Step 4: Add a new test verifying the discovery hook is called and soft-fails.**

Append to `tests/test_onboarding_injector.py`:

```python
def test_inject_discovery_hook_soft_fails_when_aichat_missing(tmp_path: Path, monkeypatch) -> None:
    """When aichat-ng isn't available, inject() returns success=True for the
    seven-file commit but discovery.success=False. Sentinel is still written.
    """
    # Force the discoverer's subprocess call to fail
    import findajob.discoverer.runner as run_mod

    def boom(*a, **kw):
        raise FileNotFoundError("simulated: aichat-ng not on PATH")

    monkeypatch.setattr(run_mod.subprocess, "run", boom)

    result = inject(tmp_path, _MIN_FILES)
    # Sentinel was written (onboarding succeeded)
    assert (tmp_path / "data" / ".onboarding-complete").is_file()
    # Discovery soft-failed
    assert result.discovery.success is False
    assert result.discovery.error is not None
```

- [ ] **Step 5: Run the full onboarding test file + discoverer suite.**

Run: `uv run pytest tests/test_onboarding_injector.py tests/discoverer/ -v`
Expected: all tests pass (existing onboarding tests pass with widened return; new discovery soft-fail test passes; discoverer tests still pass).

- [ ] **Step 6: Commit.**

```bash
git add src/findajob/onboarding/injector.py src/findajob/onboarding/__init__.py tests/test_onboarding_injector.py
git commit -m "feat(onboarding): widen inject() return + add discovery post-commit hook (#284)"
```

---

### Task 10: Render onboarding completion page with discovery status

**Files:**
- Modify: `src/findajob/web/routes/onboarding.py`
- Create: `src/findajob/web/templates/onboarding/complete.html`

The current handler at `routes/onboarding.py:71` calls `inject()` (return value discarded) and then redirects to `/board/dashboard`. We replace the redirect with a render of a new completion template that shows the discovery status and a "Continue to Dashboard" button.

**Steps:**

- [ ] **Step 1: Modify `routes/onboarding.py:onboarding_inject()`** — capture the inject result and render the completion template instead of redirecting:

Replace lines 47–74 (the `onboarding_inject` function) with:

```python
@router.post("/onboarding/inject", response_model=None)
def onboarding_inject(
    request: Request,
    emission: str = Form(default=""),
) -> HTMLResponse | RedirectResponse:
    """Parse and inject an interview emission; render completion page on success."""
    result = parse_emission(emission)
    templates = request.app.state.templates
    if result.missing:
        return templates.TemplateResponse(
            request=request,
            name="onboarding/index.html",
            context={
                "is_rerun": False,
                "paste_content": emission,
                "paste_error": (
                    f"Your paste is missing: {', '.join(result.missing)}. "
                    "Scroll through your chat for any <<<FILE: name>>> block "
                    "that's not in your paste and include it."
                ),
            },
            status_code=400,
        )
    base_root: Path = request.app.state.base_root
    inject_result = inject(base_root, result.found)
    # Clear cached guard state so the next /board/ request passes through
    request.app.state.onboarding_complete = True
    return templates.TemplateResponse(
        request=request,
        name="onboarding/complete.html",
        context={
            "discovery_success": inject_result.discovery.success,
            "discovery_count": inject_result.discovery.count,
            "discovery_error": inject_result.discovery.error,
        },
    )
```

- [ ] **Step 2: Create the completion template.**

`src/findajob/web/templates/onboarding/complete.html`:
```html
{% extends "base.html" %}

{% block title %}Onboarding complete — findajob{% endblock %}

{% block main %}
<section class="max-w-2xl mx-auto py-10 px-6 space-y-6">
  <h1 class="text-2xl font-semibold">Onboarding complete</h1>

  <p class="text-slate-700">
    Your seven config files are installed. The pipeline is ready to run on
    its next scheduled tick.
  </p>

  <div class="rounded-lg border border-slate-200 bg-white p-4 space-y-2">
    <h2 class="font-medium">Initial company discovery</h2>
    {% if discovery_success %}
      <p class="text-emerald-700">
        Generated <strong>{{ discovery_count }}</strong> companies in
        <code>candidate_context/discovered_companies.md</code>.
      </p>
    {% else %}
      <p class="text-amber-700">
        Discovery deferred to the weekly cron. Reason:
        <code class="text-xs">{{ discovery_error or "unknown" }}</code>
      </p>
      <p class="text-slate-600 text-sm">
        Your pipeline will work without the discovered set; the next Sunday
        02:00 cron run will produce one. You can also run
        <code>python3 scripts/discover_companies.py</code> manually if your
        environment supports it.
      </p>
    {% endif %}
  </div>

  <div>
    <a
      href="/board/dashboard"
      class="inline-flex items-center px-4 py-2 rounded-md bg-slate-900 text-white hover:bg-slate-700"
    >
      Continue to Dashboard →
    </a>
  </div>
</section>
{% endblock %}
```

- [ ] **Step 3: Verify the template loads (smoke test).**

There may be no end-to-end test for this page; verify by import:

Run: `uv run python3 -c "from findajob.web.routes.onboarding import onboarding_inject; print('ok')"`
Expected: `ok`.

- [ ] **Step 4: Run the full web test suite.**

Run: `uv run pytest tests/web/ tests/test_onboarding_injector.py -v`
Expected: all pass (onboarding routes untouched in test logic; new template path is referenced only on success; existing tests should not exercise the new template).

If any web test asserts a 303 redirect from `/onboarding/inject`, update it to assert a 200 + the new template's distinguishing string ("Onboarding complete").

- [ ] **Step 5: Commit.**

```bash
git add src/findajob/web/routes/onboarding.py src/findajob/web/templates/onboarding/complete.html
git commit -m "feat(onboarding): render completion page with discovery status (#284)"
```

---

### Task 11: Allowlist `discovered_companies.md` for the `/config/` editor

**Files:**
- Modify: `src/findajob/web/config_files.py`
- Modify: `tests/test_web_config_files.py` (if it exists; otherwise add coverage to existing tests)

Add `candidate_context/discovered_companies.md` to `EDITABLE_CATEGORIES` so operators can hand-edit if discovery surfaces noise.

**Steps:**

- [ ] **Step 1: Modify `config_files.py:EDITABLE_CATEGORIES`** at line 17:

```diff
 EDITABLE_CATEGORIES: dict[str, list[str] | str] = {
     "Candidate context": [
         "candidate_context/profile.md",
         "candidate_context/master_resume.md",
+        "candidate_context/discovered_companies.md",
     ],
```

- [ ] **Step 2: Find the existing tests for the allowlist.**

Run: `grep -ln "EDITABLE_CATEGORIES\|is_editable\|resolve_editable" tests/`
Expected: one or more test files. Read them.

- [ ] **Step 3: Add a test asserting the new path is editable.**

Append (or insert near similar tests in the existing file):

```python
def test_discovered_companies_md_is_editable() -> None:
    from findajob.web.config_files import is_editable
    assert is_editable("candidate_context/discovered_companies.md") is True


def test_discovered_companies_json_is_NOT_editable() -> None:
    """JSON sidecar is machine-managed; only the markdown is operator-editable."""
    from findajob.web.config_files import is_editable
    assert is_editable("candidate_context/discovered_companies.json") is False
```

- [ ] **Step 4: Run tests.**

Run: `uv run pytest tests/ -k config_files -v`
Expected: all pass, including the two new tests.

- [ ] **Step 5: Commit.**

```bash
git add src/findajob/web/config_files.py tests/
git commit -m "feat(config-editor): allowlist discovered_companies.md (#284)"
```

---

### Task 12: Documentation updates

**Files:**
- Modify: `CLAUDE.md`
- Modify: `docs/GENERALIZATION.md`
- Modify: `candidate_context/profile.md.example`
- Modify: `CHANGELOG.md`

**Steps:**

- [ ] **Step 1: Update `CLAUDE.md` Pipeline Context Table.** Add a row near the other roles:

In the "Pipeline Context Table" section, add:

```markdown
| `company_discoverer` | `openrouter:perplexity/sonar-reasoning-pro` — runs weekly Sun 02:00; emits `candidate_context/discovered_companies.md` + `.json`; field-agnostic, augments static `## Target Companies` |
```

- [ ] **Step 2: Update `CLAUDE.md` Container Context table.** Add rows under the bind-mount section:

```markdown
| `discovered_companies.md/.json` | `<repo>/candidate_context/discovered_companies.{md,json}` (gitignored, generated) | `/app/candidate_context/discovered_companies.{md,json}` (generated into bind-mount) |
```

- [ ] **Step 3: Update `CLAUDE.md` Critical Architecture Rules.** Add a new bullet:

```markdown
### Company Discovery is a Parallel Signal
`config/roles/company_discoverer.md` runs weekly via supercronic and after
onboarding completion. It emits `candidate_context/discovered_companies.md`
+ `.json` (gitignored). Both are read by #285's scorer rewire and #283's
Greenhouse-slug derivation as INPUTS, not floors. The static
`## Target Companies / Organizations` section in profile.md remains as a
strategic-preference signal — orthogonal to the competency-fit signal the
discoverer produces. Do not delete the static list to "consolidate" — they
serve different purposes.
```

- [ ] **Step 4: Update `CLAUDE.md` Key File Locations** to reference the new module:

In the `# ── Package (pip install -e .) ──` block, add:
```
<repo>/src/findajob/discoverer/                # company discovery library — prompt, parser, runner, writer
```

In the `# ── Entry point scripts ──` block, add:
```
<repo>/scripts/discover_companies.py            # weekly company discovery cron entry
```

- [ ] **Step 5: Append to `docs/GENERALIZATION.md`.** Add a new section before the file's tail:

```markdown
## Company discovery — replaces hand-curated Tier 1 expansion (#284)

The `## Target Companies / Organizations` section in `profile.md` was
previously the only mechanism for naming companies the candidate would
take a job at. It conflated two signals: strategic preference (would-take
even if not a perfect fit) and competency-domain fit (skill-stack
matches). Hand-expanding the list to cover competency-fit was a known
dead end — hand-written lists don't track hiring activity and don't scale
across operator fields.

The `company_discoverer` role (#284) handles competency-fit discovery as
a parallel, regenerable, field-agnostic signal. The static list stays as
the strategic-preference signal. The two are read separately by
downstream consumers (#285's scorer rewire, #283's Greenhouse-slug
derivation) without either acting as a hard floor.

The discoverer's role file (`config/roles/company_discoverer.md`) is
intentionally field-agnostic. It enumerates no industries, no companies,
no role titles. If you fork to tune the prompt for your own field, that
is expected; if you contribute back upstream, please preserve
field-agnosticism so other operators in unrelated fields continue to
benefit.
```

- [ ] **Step 6: Annotate `candidate_context/profile.md.example`.**

Find the `## Target Companies / Organizations` block (around line 50) and replace its description with:

```diff
 ## Target Companies / Organizations
-[List primary targets. Could be companies, nonprofits, school districts, hospital systems,
-government agencies — whatever fits your field. The job_scorer reads this to apply the
-"Tier 1 floor" — in-domain titles at these orgs get a minimum score of 6 even at junior
-levels.]
+[List primary targets you'd take a job at even if the role isn't a perfect fit. This is
+a SEED — not the universe. The findajob `company_discoverer` role (#284) augments this
+with a regenerable, reasoned set in `candidate_context/discovered_companies.md`. The
+job_scorer reads BOTH lists as inputs to scoring; this section carries strategic
+preference, the discovered list carries competency-fit (orthogonal signals).]
```

- [ ] **Step 7: Add CHANGELOG entry.**

In `CHANGELOG.md` under `## [Unreleased]` → `### Added`, append:

```markdown
- **Dynamic company discovery (#284).** New `company_discoverer` role
  (`openrouter:perplexity/sonar-reasoning-pro`, ~$3-5/run) runs weekly on
  Sunday 02:00 and after onboarding completion. Emits
  `candidate_context/discovered_companies.md` (human-readable, gitignored)
  + `.json` sidecar (machine-readable consumer contract for #285 scorer
  rewire and #283 Greenhouse-slug derivation). Augments — does not
  replace — the static `## Target Companies / Organizations` profile
  section: the static list now carries strategic preference, the
  discovered set carries competency-fit (orthogonal signals). Field-
  agnostic by design; same prompt produces sensibly different outputs for
  operators in different fields. Cost soft-guardrail: ntfy warning when
  any single run reports >$10 (configurable via
  `DISCOVERY_COST_THRESHOLD_USD`).
```

- [ ] **Step 8: Verify pre-commit hook passes (no PII leaks).**

Run: `git add CLAUDE.md docs/GENERALIZATION.md candidate_context/profile.md.example CHANGELOG.md && git status --short`
Expected: only the four files staged.

- [ ] **Step 9: Commit.**

```bash
git commit -m "docs(discoverer): CLAUDE.md, GENERALIZATION.md, CHANGELOG, profile.md.example (#284)"
```

If the pre-commit hook flags PII in any file, abort the commit and fix the offending content before re-running.

---

### Task 13: Whole-feature lint, typecheck, format gate

**Files:** none (verification only)

**Steps:**

- [ ] **Step 1: Run ruff check.**

Run: `uv run ruff check src/findajob/discoverer/ scripts/discover_companies.py tests/discoverer/`
Expected: no issues.

- [ ] **Step 2: Run ruff format check.**

Run: `uv run ruff format --check src/findajob/discoverer/ scripts/discover_companies.py tests/discoverer/`
Expected: "would be reformatted: 0 file(s)" or equivalent clean output.

If formatting differs: `uv run ruff format src/findajob/discoverer/ scripts/discover_companies.py tests/discoverer/`, then re-run --check, then `git add -u && git commit -m "style(discoverer): ruff format (#284)"`.

- [ ] **Step 3: Run mypy.**

Run: `uv run mypy src/findajob/discoverer/ scripts/discover_companies.py`
Expected: no issues.

- [ ] **Step 4: Run the full test suite (catches collateral breakage).**

Run: `uv run pytest -q`
Expected: all tests pass; ~900+ existing tests + ~30 new = ~930 passing.

If anything fails: investigate root cause (per `feedback_anti_drift` discipline — don't paper over).

- [ ] **Step 5: No commit if all checks pass; otherwise commit fixes from steps 2 / 4.**

---

### Task 14: PR-time manual smoke + open PR

**Files:** none for the smoke; PR description on GitHub.

The manual smoke is the one-time real-API verification specified in spec §9.3 — runs the discoverer against the operator's real `candidate_context/profile.md` once, eyeballs the output, documents the result in the PR description. No permanent fixture or CI gate (per Q4 brainstorm reflection).

**Steps:**

- [ ] **Step 1: Push the feature branch.**

```bash
git push -u origin feat/284-company-discoverer
```

- [ ] **Step 2: Run the discoverer locally against the operator's real profile.** This consumes ~$3-5 of OpenRouter credit on `sonar-reasoning-pro`.

Note: this requires a working local aichat-ng + OpenRouter credentials. If the laptop doesn't have aichat-ng configured (per `feedback_laptop_aichat_config` — the laptop config is off-limits), run on docker.lan instead via:

```bash
ssh docker.lan 'sudo -u lad docker compose -f /opt/stacks/findajob-{operator-stack}/compose.yaml exec scheduler python3 /app/scripts/discover_companies.py --no-ntfy'
```

- [ ] **Step 3: Capture the result.** Read the generated markdown:

```bash
ssh docker.lan 'sudo -u lad cat /opt/stacks/findajob-{operator-stack}/state/candidate_context/discovered_companies.md' | head -60
```

- [ ] **Step 4: Eyeball check.** Confirm:
- The three cluster headings are present (Direct / Adjacency / Cross-industry)
- ≥3 companies total, ≥2 clusters populated (the parser would have rejected otherwise — but eyeball anyway)
- Reasoning lines reference the operator's actual competencies (not generic boilerplate)
- Citations are real, resolvable URLs
- No operator-specific identifiers leaked into the prompt scaffolding (all field-specific content lives in the verbatim profile section)

- [ ] **Step 5: Open the PR with the manual-smoke result documented in the body.**

```bash
gh pr create --title "feat(scorer): dynamic company discoverer (#284)" --body "$(cat <<'EOF'
## Summary

Implements #284 — competency-driven company discovery as a parallel signal that augments (does not replace) the static `## Target Companies / Organizations` profile section. Loadbearing prerequisite for #285 (scorer rewire) and unblock for #276.

- New role `config/roles/company_discoverer.md` (model: openrouter:perplexity/sonar-reasoning-pro)
- New library `src/findajob/discoverer/{prompt,parser,runner,writer}.py` with full unit/integration tests
- New CLI `scripts/discover_companies.py` + weekly cron entry (Sun 02:00)
- Onboarding post-commit hook in `findajob.onboarding.injector.inject()` — soft-fails to "weekly cron will produce one" if discovery fails (sentinel still written)
- Output pair `candidate_context/discovered_companies.md` + `.json` (gitignored, atomic temp+replace, last-good preserved on failure)
- Cost soft-guardrail: ntfy warning when any single run reports >$10

Spec: `docs/superpowers/specs/2026-04-26-company-discoverer-design.md` (12 sections + decisions log).
Plan: `docs/superpowers/plans/2026-04-26-company-discoverer.md`.

## Test plan

- [x] Unit tests pass: prompt (5), parser (11), writer (4), runner (8) — all in `tests/discoverer/`
- [x] Integration: existing onboarding tests still pass (the inject() hook is non-breaking)
- [x] ruff check + ruff format --check + mypy clean
- [x] Full pytest suite green
- [x] Manual real-API smoke on operator profile (see "Manual smoke result" below)

## Manual smoke result

Ran the discoverer against the operator's real `candidate_context/profile.md` on docker.lan via `docker compose exec scheduler python3 /app/scripts/discover_companies.py --no-ntfy`. Result:

- Cluster: Direct domain match — N companies
- Cluster: Transferable-competency adjacency — N companies
- Cluster: Cross-industry application — N companies
- Total: N companies across 3 clusters
- Cost reported: $X.XX

Representative reasoning line (anonymized): _<one line, profile-grounded, no operator PII>_

Eyeball verdict: clusters read as field-appropriate; citations resolve to real careers/news pages; reasoning references the operator's competencies plausibly. Field-agnostic — the prompt scaffolding contains no operator-specific or field-locked vocabulary; profile content is the only field-specific input.

No permanent CI gate for field-agnosticism per spec §9.3 / Q4 brainstorm reflection — committed Alice fixture would be an antipattern.

## Migration / docs

- No `migration-required` label — output files are gitignored, no schema or breaking config changes.
- Documentation updates: CLAUDE.md (Pipeline Context Table, Container Context, Architecture Rules, Key File Locations), docs/GENERALIZATION.md, candidate_context/profile.md.example, CHANGELOG.md (Unreleased / Added).

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 6: Replace the placeholders** in the PR body:
  - `N` — actual cluster counts
  - `$X.XX` — actual reported cost
  - `_<one line, profile-grounded, no operator PII>_` — paraphrased reasoning line that demonstrates groundedness without leaking operator name / employer / cert names (per CLAUDE.md PII rules — this is a public PR description on a public repo)

- [ ] **Step 7: Verify the PR opens cleanly.**

Run: `gh pr view --web` to spot-check the rendered description.

---

## 3. Documentation Impact

| Surface | Change | Task |
|---|---|---|
| `CLAUDE.md` Pipeline Context Table | Add row for `company_discoverer` | Task 12 §1 |
| `CLAUDE.md` Container Context | Add rows for `discovered_companies.md/.json` | Task 12 §2 |
| `CLAUDE.md` Critical Architecture Rules | Add "Company Discovery is a Parallel Signal" rule | Task 12 §3 |
| `CLAUDE.md` Key File Locations | Add `src/findajob/discoverer/` and `scripts/discover_companies.py` | Task 12 §4 |
| `docs/GENERALIZATION.md` | Add "Company discovery" section | Task 12 §5 |
| `candidate_context/profile.md.example` | Annotate `## Target Companies / Organizations` as a seed | Task 12 §6 |
| `CHANGELOG.md` `[Unreleased] / Added` | Discoverer entry | Task 12 §7 |
| `config/roles/company_discoverer.md` (top-of-file comment) | Field-agnostic intent — verbatim from spec §10 | Task 2 §1 |
| Spec doc | None — spec is the source of truth and was committed in 82aa0a7 | — |

No `migration-required` label is needed: output files are gitignored, no schema changes, no breaking changes to existing config files.

---

## 4. Verification gate (whole-feature)

The PR cannot merge until all of the below are true:

1. **All unit tests pass.** `uv run pytest tests/discoverer/ tests/test_onboarding_injector.py -v` — ~30 new + existing onboarding tests.
2. **Full test suite green.** `uv run pytest -q` — ~930 tests.
3. **ruff check + ruff format --check clean.**
4. **mypy clean** for the new module + script.
5. **Manual real-API smoke completed and documented in the PR body.** Per spec §9.3 — eyeball verdict that the output reads as field-appropriate and citations resolve to real URLs.
6. **Pre-commit PII hook passes** on every commit in the branch.
7. **CI green** on the PR.
8. **Cost guardrail wired and exercised in unit tests.** Test `test_run_emits_ntfy_when_threshold_breached` proves the path.
9. **Last-good invariant exercised in unit tests.** Tests `test_commit_atomically_rolls_back_on_replace_failure` and `test_run_does_not_overwrite_last_good_on_failure` prove the invariant.
10. **Documentation diff present in the PR.** Reviewer can see CLAUDE.md / GENERALIZATION.md / profile.md.example / CHANGELOG entries.

---

## 5. Self-review checklist

### 5.1 Spec coverage map (every spec section → implementing tasks)

| Spec section | Implementing task(s) |
|---|---|
| §3.1 In scope: role file | Task 2 |
| §3.1 In scope: library module (prompt/parser/runner/writer) | Tasks 3, 4, 5, 6 |
| §3.1 In scope: CLI | Task 7 |
| §3.1 In scope: cron | Task 8 |
| §3.1 In scope: onboarding hook | Task 9 |
| §3.1 In scope: output files (gitignore + writer) | Tasks 1, 5 |
| §3.1 In scope: editable allowlist | Task 11 |
| §3.1 In scope: progress UI | Task 10 |
| §3.1 In scope: cost guardrail | Task 6 (runner._cost_threshold + threshold-breach test) |
| §3.1 In scope: docs | Task 12 |
| §4.1 prompt.py contract | Task 3 (TDD: 5 tests) |
| §4.1 parser.py contract | Task 4 (TDD: 11 tests + 7 fixtures) |
| §4.1 runner.py contract | Task 6 (TDD: 8 tests) |
| §4.1 writer.py contract | Task 5 (TDD: 4 tests) |
| §4.2 cron entry | Task 8 |
| §4.2 onboarding hook (InjectResult widening) | Task 9 |
| §5.1 markdown schema | Task 2 (role-file output format), Task 4 (parser validates) |
| §5.2 JSON sidecar schema | Task 6 (runner builds payload), Task 5 (writer commits) |
| §6.1 cron data flow | Tasks 7, 8 |
| §6.2 onboarding data flow | Tasks 9, 10 |
| §7 error handling matrix | Tasks 5 (writer rollback), 6 (runner never raises), 9 (injector soft-fail) |
| §8 cost guardrail | Task 6 |
| §9.1 unit tests | Tasks 3, 4, 5, 6 |
| §9.2 integration tests | Task 6 |
| §9.3 manual smoke | Task 14 (PR-time, documented in PR body) |
| §10 generalization safety | Task 2 (top-of-file comment + field-agnostic prompt body), Task 12 (GENERALIZATION.md) |
| §11 documentation impact | Task 12 (every row) |

Every spec section maps to at least one task. No section is unimplemented.

### 5.2 Placeholder scan

This plan contains no `TBD`, `TODO`, `FIXME`, `<placeholder>`, "implement later", or "similar to Task N" stubs. Every code block shows the actual code; every command shows actual arguments; every commit message is the literal message. Red-flag scan:

- "Add appropriate error handling" — not used
- "Write tests for the above" — not used; every test is shown
- "Similar to Task N" — not used; code is repeated when needed

The PR-body manual-smoke result (Task 14) deliberately uses placeholders (`N`, `$X.XX`, `_<one line>_`) because they cannot be known until the smoke runs at PR time. Task 14 §6 calls out replacing them explicitly.

### 5.3 Type / contract consistency

- `RunResult(success, count, error, cost_usd)` — defined in Task 6, used in Tasks 7, 9.
- `CompanyEntry(name, cluster, channel, reasoning, citations)` — defined in Task 4, consumed in Task 6 runner JSON-payload construction.
- `ParseResult(markdown_clean, companies)` — defined in Task 4, consumed in Task 6.
- `InjectResult(backup_dir, discovery)` + `DiscoveryStatus(success, count, error)` — defined in Task 9, consumed in Task 10.
- `commit_atomically(base_root, markdown, json_payload) -> Path` — defined in Task 5, called in Task 6.
- `build_prompt(profile_text) -> str` — defined in Task 3, called in Task 6.
- `parse_markdown(md_text) -> ParseResult` — defined in Task 4, called in Task 6.
- `run(base_root, profile_path=None, ntfy_enabled=True) -> RunResult` — defined in Task 6, called in Tasks 7 (CLI), 9 (onboarding hook).
- `DiscoveryParseError` — defined in Task 4 (subclass of `ValueError`), caught in Task 6.

All names match across tasks. `cluster` values are the literal strings `"direct"`, `"adjacency"`, `"cross_industry"` everywhere. `channel` values are the literal strings in `VALID_CHANNELS` everywhere.

---

## Notes for the executing implementer / subagent

- **Branch is already created** as `feat/284-company-discoverer` off `origin/main` in Task 1; do not switch branches mid-implementation.
- **Per `feedback_subagent_model_defaults`:** dispatch implementation tasks (Tasks 1–13) to a Sonnet subagent. Task 14 (PR-time smoke + writeup) stays with the orchestrator (Opus).
- **Per `feedback_anti_drift`:** if a test fails, find the root cause; do not paper over with `pytest.skip` or `xfail`.
- **Per `feedback_announce_long_operations`:** the real-API smoke in Task 14 takes ~30-60s; announce before running.
- **Per `feedback_apply_gate_check`:** this work is sourcing-side and exempt from the apply gate.
- **Per CLAUDE.md PII rules:** when filling in the PR body's manual-smoke section (Task 14 §6), paraphrase any reasoning lines that reference operator's name, employer history, or cert names. The PR is on a public repo.
- **Per `feedback_docker_lan_db_query`:** docker.lan operations in Task 14 use `sudo -u lad`; do not run bare `ssh docker.lan 'sqlite3 ...'`.
