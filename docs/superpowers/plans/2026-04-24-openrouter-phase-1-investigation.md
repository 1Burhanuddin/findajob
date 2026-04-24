# OpenRouter Phase 1 Investigation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a written verdict + per-role routing recommendation on whether findajob should standardize all LLM calls on OpenRouter (fully / partially / stay-as-is), with empirical evidence for the three open technical questions (Perplexity citation passthrough, Claude extended thinking via OR, Gemini embeddings) plus a head-to-head comparison of Claude Opus 4.6 vs 4.7 in thinking mode for `resume_tailor` and `cover_letter_writer`.

**Architecture:** Pure investigation — no pipeline code changes. Each task produces a concrete finding captured in a scratch notebook file. The deliverable is a single structured comment appended to GitHub issue #22. Tests run on the laptop's `aichat-ng` (OpenRouter client already configured) against current production models; findings apply to the container because OR behavior is server-side.

**Tech Stack:** `aichat-ng` (laptop install, OpenRouter client already configured), OpenRouter API (REST), direct Anthropic / Perplexity / Gemini clients (already configured in `~/.config/aichat_ng/config.yaml`) for baseline comparison, `curl` + `jq` + `python3` for catalog parsing, `gh issue comment` for publishing the verdict.

---

## File Structure

- **Plan file:** `docs/superpowers/plans/2026-04-24-openrouter-phase-1-investigation.md` (this file — tracked, committed to `main`).
- **Scratch notebook:** `/tmp/openrouter-phase1-findings.md` — untracked, consolidated notes as each task runs. Used to compose the final issue comment.
- **Raw catalog snapshot:** `/tmp/openrouter_catalog.json` — already fetched 2026-04-24, re-fetch if stale (>24h).
- **Test-prompt artifacts:** `/tmp/openrouter-test-*.txt` — prompts + raw responses per empirical test, referenced by the notebook.
- **Deliverable:** new GitHub comment on issue #22 (`gh issue comment 22 -F /tmp/openrouter-phase1-verdict.md`).

No pipeline source code is modified in this phase. A separate Phase 2 plan will execute the cutover implied by this phase's recommendation.

---

## Bounding constraints (read before starting)

- **No cutover this session.** If findings suggest routing changes, record them in the verdict comment — do NOT touch `~/.config/aichat_ng/models-override.yaml`, any role `.md` file in `config/roles/`, or `CLAUDE.md`'s pipeline context table. Phase 2 will do that.
- **Never echo API keys** into the notebook, issue comment, or plan. If a test command's output surfaces a key, redact before saving.
- **Gemini embeddings are already locked** (OR has zero embedding models). Don't spend test cycles here; one sentence of confirmation is enough.
- **RAG policy unchanged.** Do NOT test any route that would imply passing RAG to `job_scorer`, `cover_letter_writer`, or `outreach_drafter` — profile injection stays string-interpolation per CLAUDE.md "RAG Policy" rule.
- **Ad-hoc aichat-ng syntax discovery is part of the work.** OpenRouter exposes `reasoning` / `include_reasoning` as parameters, but aichat-ng may surface them via a different mechanism (patch body, :suffix, per-model override). Verify the correct invocation as part of Task 4 — don't assume `:thinking` works identically through `openrouter:` clients.

---

## Task 0: Commit the plan file (durability first)

**Files:**
- Add: `docs/superpowers/plans/2026-04-24-openrouter-phase-1-investigation.md`

Rationale: if execution derails mid-investigation, a committed plan file is recoverable; an uncommitted one is not. Plans live on `main` per CLAUDE.md commit flow (docs-only, no migration-required).

- [ ] **Step 1: Stage + commit the plan.**

Run:

    git add docs/superpowers/plans/2026-04-24-openrouter-phase-1-investigation.md
    git commit -m "docs(plans): OpenRouter Phase 1 investigation plan (#22)"

- [ ] **Step 2: Push immediately (not at end-of-session).**

Run:

    git push origin main

- [ ] **Step 3: Verify on remote.**

Run:

    git log --oneline -1 origin/main

Expected: the commit you just pushed is at the tip.

---

## Task 1: Refresh catalog snapshot, extract a structured slice, and verify 4.7 is invokable

**Files:**
- Read/Create: `/tmp/openrouter_catalog.json` (already present from 2026-04-24 fetch)
- Create: `/tmp/openrouter-phase1-findings.md`

- [ ] **Step 1: Re-fetch the catalog if stale, then confirm size + model count.**

Run:

    curl -sS https://openrouter.ai/api/v1/models > /tmp/openrouter_catalog.json
    python3 -c "import json; d=json.load(open('/tmp/openrouter_catalog.json')); print('models:', len(d['data']))"

Expected: `models: 355` (±10 — count drifts as OR adds/removes models).

- [ ] **Step 2: Initialize the findings notebook with a header.**

Create `/tmp/openrouter-phase1-findings.md`:

    # OpenRouter Phase 1 — Findings (findajob #22)

    **Investigation date:** 2026-04-24
    **Catalog snapshot:** /tmp/openrouter_catalog.json (N=<count> models)
    **Runner:** Claude Code session on laptop (Chromebook Linux env)

    ---

- [ ] **Step 3: Extract the role-relevant model slice into the notebook.**

Run:

    python3 <<'PY' >> /tmp/openrouter-phase1-findings.md
    import json
    d = json.load(open('/tmp/openrouter_catalog.json'))
    models = d['data']
    groups = {
      'Anthropic (resume_tailor, cover_letter_writer, briefing_writer, outreach_drafter)':
        lambda m: 'anthropic' in m['id'] and 'claude' in m['id'],
      'Perplexity (company_researcher, fit_analyst)':
        lambda m: m['id'].startswith('perplexity/'),
      'Google Gemini (default, resume_change_reviewer, network_analyst)':
        lambda m: m['id'].startswith('google/gemini'),
      'DeepSeek (job_scorer)':
        lambda m: m['id'].startswith('deepseek/'),
    }
    print('## Role-relevant model availability on OpenRouter\n')
    for label, pred in groups.items():
        print(f'### {label}\n')
        for m in sorted([x for x in models if pred(x)], key=lambda x: x['id']):
            p = m.get('pricing', {})
            prompt_cost = float(p.get('prompt', 0)) * 1_000_000
            compl_cost  = float(p.get('completion', 0)) * 1_000_000
            ctx = m.get('context_length', '?')
            params = m.get('supported_parameters', [])
            has_reasoning = 'reasoning' in params
            print(f'- `{m["id"]}` — ctx {ctx}, ${prompt_cost:.2f}/M in, ${compl_cost:.2f}/M out'
                  f'{", reasoning✓" if has_reasoning else ""}')
        print()
    PY

- [ ] **Step 4: Verify the notebook has the four role groups populated.**

Run:

    grep -c '^### ' /tmp/openrouter-phase1-findings.md

Expected: `4` (one `###` header per role group).

- [ ] **Step 5: Verify Opus 4.7 is invokable by name before any test composition.**

Two paths to test:

    # Path A — via OpenRouter (known-good, catalog confirms model exists)
    aichat-ng -m openrouter:anthropic/claude-opus-4.7 --no-stream "Say 'hello from opus 4.7'." 2>&1 | head -20

Expected: a short greeting response.

    # Path B — direct Anthropic: depends on whether models-override.yaml has 4.7 registered
    grep -E 'claude-opus-4-?7' ~/.config/aichat_ng/models-override.yaml 2>/dev/null || echo "NOT REGISTERED"

If `NOT REGISTERED`, decide before Task 5: either add a 4.7 entry to `models-override.yaml` (one-line config change, low blast radius) OR commit to "4.7 via OR only" for Task 5 and skip the "4.7 direct" variant. Record the decision in the findings notebook as a bullet under a new `## Preflight` section:

    ## Preflight

    - OR model `anthropic/claude-opus-4.7` invokable: <yes/no>
    - Direct `claude:claude-opus-4-7` in models-override.yaml: <yes/no>
    - Decision for Task 5: <test both variants | via-OR only>

- [ ] **Step 6: Commit nothing yet — scratch file is intentionally untracked.** Move on to Task 2.

---

## Task 2: Build the per-role routing table

**Files:**
- Modify: `/tmp/openrouter-phase1-findings.md` (append table)

- [ ] **Step 1: Pull current role → model mapping from CLAUDE.md.**

Reference (CLAUDE.md §Pipeline Context Table, don't re-derive):

| Role | Current | Provider via aichat-ng |
|---|---|---|
| job_scorer | `deepseek/deepseek-v3.2` | `openrouter:` (already on OR) |
| resume_tailor | `claude-opus-4-6:thinking` | `claude:` (direct) |
| cover_letter_writer | `claude-opus-4-6:thinking` | `claude:` (direct) |
| company_researcher | `sonar-reasoning-pro` | `perplexity:` (direct) |
| briefing_writer | `claude-sonnet-4-6:thinking` | `claude:` (direct) |
| outreach_drafter | `claude-sonnet-4-6` | `claude:` (direct) |
| fit_analyst | `sonar-reasoning-pro` | `perplexity:` (direct) |
| resume_change_reviewer | `gemini-3-flash-preview` | `gemini:` (direct) |
| network_analyst | `gemini-3-flash-preview` | `gemini:` (direct) |
| default (REPL / misc) | `gemini-3-flash-preview` | `gemini:` (direct) |
| **embedding** | `gemini-embedding-001` | `gemini-embed:` (direct — STAYS DIRECT) |

- [ ] **Step 2: Append routing table to the findings notebook.**

For each role, fill: `OR model ID` (from Task 1 extract), `Upgrade candidate` (stronger model in catalog), `Verdict` (`Route via OR`, `Stay direct`, or `Decide after empirical test`), `Rationale`.

Append this skeleton and fill it row-by-row:

    ## Per-role routing table (proposed, pending empirical validation)

    | Role | Current | OR model ID | Upgrade candidate | Verdict | Rationale |
    |---|---|---|---|---|---|
    | job_scorer | deepseek/deepseek-v3.2 | `deepseek/deepseek-v3.2` | `deepseek/deepseek-v4-pro`? | Route via OR (already is) | No change; re-evaluate v4 after benchmarking |
    | resume_tailor | claude-opus-4-6:thinking | `anthropic/claude-opus-4.7` | 4.7 direct vs via OR | Decide after Task 4 + 5 | Thinking mode through OR unverified; 4.7 quality unverified |
    | cover_letter_writer | claude-opus-4-6:thinking | `anthropic/claude-opus-4.7` | 4.7 direct vs via OR | Decide after Task 4 + 5 | Same as resume_tailor |
    | company_researcher | sonar-reasoning-pro | `perplexity/sonar-reasoning-pro` | none | Decide after Task 3 | Depends on citation passthrough |
    | briefing_writer | claude-sonnet-4-6:thinking | `anthropic/claude-sonnet-4.6` | none | Decide after Task 4 | Thinking via OR must work |
    | outreach_drafter | claude-sonnet-4-6 | `anthropic/claude-sonnet-4.6` | none | Route via OR (tentative) | No thinking required; low risk |
    | fit_analyst | sonar-reasoning-pro | `perplexity/sonar-reasoning-pro` | none | Decide after Task 3 | Same as company_researcher |
    | resume_change_reviewer | gemini-3-flash-preview | `google/gemini-3-flash-preview` | none | Route via OR (tentative) | Same model available |
    | network_analyst | gemini-3-flash-preview | `google/gemini-3-flash-preview` | none | Route via OR (tentative) | Same |
    | default | gemini-3-flash-preview | `google/gemini-3-flash-preview` | none | Route via OR (tentative) | Same |
    | embedding | gemini-embedding-001 | **not in OR catalog** | none | **Stay direct (locked)** | OR proxies no embedding endpoints |

- [ ] **Step 3: Verify the table has 11 rows** (10 generation roles + embedding).

Run:

    grep -cE '^\| [a-z_]+ \|' /tmp/openrouter-phase1-findings.md

Expected: `11`.

- [ ] **Step 4: Read the table back for sanity** — every "Decide after Task N" cell maps to a test we're about to run.

---

## Task 3: Empirical — Perplexity citation metadata passthrough

**Files:**
- Create: `/tmp/openrouter-test-pplx-direct.json`
- Create: `/tmp/openrouter-test-pplx-via-or.json`
- Modify: `/tmp/openrouter-phase1-findings.md` (append "Test 1" section)

**Hypothesis:** `perplexity/sonar-reasoning-pro` via OpenRouter returns citation metadata (source URLs, grounding chunks) in a field that aichat-ng can surface, the same way the direct Perplexity client does.

- [ ] **Step 1: Construct the test prompt.**

A question that *must* cite recent sources to be answered correctly. Pick a topic that (a) needs real-time web grounding, (b) has no stable/training-set answer, (c) is domain-neutral. Example:

    What is the publicly stated headcount of a well-known AI research lab (e.g., pick any one from 2026 news)
    and what source(s) support that number? Provide URLs.

Save the executor's chosen prompt as `/tmp/openrouter-test-pplx-prompt.txt`. Do not put the prompt in the plan — it is a scratch artifact.

- [ ] **Step 2: Call Perplexity direct via aichat-ng and save raw response.**

Run:

    aichat-ng -m perplexity:sonar-reasoning-pro --no-stream < /tmp/openrouter-test-pplx-prompt.txt > /tmp/openrouter-test-pplx-direct.txt 2>&1

Inspect `/tmp/openrouter-test-pplx-direct.txt`. Expected: response body contains numbered or bracketed citations with URLs (e.g., `[1] https://...`), or a `citations` section.

Note: if aichat-ng hides citation metadata even on the direct path, we have no baseline and the test is inconclusive — document that as a finding and move on.

- [ ] **Step 3: Call Perplexity via OpenRouter and save raw response.**

Run:

    aichat-ng -m openrouter:perplexity/sonar-reasoning-pro --no-stream < /tmp/openrouter-test-pplx-prompt.txt > /tmp/openrouter-test-pplx-via-or.txt 2>&1

- [ ] **Step 4: Diff and analyze.**

Run:

    diff /tmp/openrouter-test-pplx-direct.txt /tmp/openrouter-test-pplx-via-or.txt || true

Look for: (a) did the OR response contain any citations/URLs at all, (b) did it surface them in the same format, (c) was the factual claim supported.

- [ ] **Step 5: Optional — inspect raw API response for grounding field presence.**

If aichat-ng strips metadata client-side, call OR's HTTP endpoint directly to see what the server returned. OR API key is already in laptop config — read from there, do NOT paste here:

    API_KEY=$(python3 -c "import yaml; c=yaml.safe_load(open('$HOME/.config/aichat_ng/config.yaml')); print([x for x in c['clients'] if x.get('name')=='openrouter'][0]['api_key'])")
    curl -sS https://openrouter.ai/api/v1/chat/completions \
      -H "Authorization: Bearer $API_KEY" \
      -H "Content-Type: application/json" \
      -d @- <<'JSON' > /tmp/openrouter-test-pplx-raw.json
    {"model":"perplexity/sonar-reasoning-pro","messages":[{"role":"user","content":"What is Anthropic's publicly stated headcount as of early 2026, and what source(s) support that number? Provide URLs."}],"max_tokens":800}
    JSON
    python3 -c "import json; r=json.load(open('/tmp/openrouter-test-pplx-raw.json')); print(json.dumps(r, indent=2))" | head -80

Look for a top-level `citations`, `annotations`, or `sources` field in the response object.

- [ ] **Step 6: Record findings in notebook.**

Append to `/tmp/openrouter-phase1-findings.md`:

    ## Test 1 — Perplexity citation passthrough via OpenRouter

    **Prompt:** (see /tmp/openrouter-test-pplx-prompt.txt)

    **Direct (`perplexity:sonar-reasoning-pro`):** <verdict — citations present? format? accurate?>
    **Via OR (`openrouter:perplexity/sonar-reasoning-pro`):** <same questions>
    **Raw API grounding field:** <present / absent — and in what field?>

    **Verdict:** <Route via OR | Stay direct | Inconclusive — need <specific follow-up>>

- [ ] **Step 7: Update the Task 2 routing table** — fill the `company_researcher` and `fit_analyst` Verdict + Rationale cells based on the finding.

---

## Task 4: Empirical — Claude extended thinking via OpenRouter

**Files:**
- Create: `/tmp/openrouter-test-thinking-*.txt`
- Modify: `/tmp/openrouter-phase1-findings.md` (append "Test 2" section)

**Hypothesis:** aichat-ng can invoke Claude Opus 4.6 via `openrouter:anthropic/claude-opus-4.6` with extended thinking enabled, and the response is structurally usable by `resume_tailor` / `cover_letter_writer` / `briefing_writer` (same expected output format, thinking blocks either stripped client-side or exposed cleanly).

- [ ] **Step 1: Construct a prompt that benefits from thinking.**

A reasoning-heavy prompt — something like the kind of chain the `resume_tailor` runs, but with a domain-neutral placeholder bullet. Save as `/tmp/openrouter-test-thinking-prompt.txt`. Suggested pattern (executor chooses concrete content; keep it out of the plan):

    You are evaluating whether a resume bullet should be rewritten for a target job.

    Bullet: <pick a generic bullet — e.g., "Led a cross-functional team validating new hardware for production deployment.">
    Target job: <pick a generic target — e.g., "Senior TPM at a mid-stage infrastructure company.">

    Think step by step about what specific language, metrics, and domain-signals would strengthen this bullet for the target. Then output ONLY the rewritten bullet (no preamble), under 30 words.

- [ ] **Step 2: Call direct (`claude:claude-opus-4-6:thinking`) for baseline.**

Run:

    aichat-ng -m claude:claude-opus-4-6:thinking --no-stream < /tmp/openrouter-test-thinking-prompt.txt > /tmp/openrouter-test-thinking-direct-46.txt 2>&1

Verify: response contains a rewritten bullet under 30 words. Note how/whether thinking is surfaced in the output.

- [ ] **Step 3: Call via OR — first attempt, naïve syntax.**

Run:

    aichat-ng -m openrouter:anthropic/claude-opus-4.6 --no-stream < /tmp/openrouter-test-thinking-prompt.txt > /tmp/openrouter-test-thinking-or-46-naive.txt 2>&1

Verify: does this produce output at all? (Thinking may be off; compare quality to baseline.)

- [ ] **Step 4: Call via OR with `reasoning` parameter enabled.**

OR expects a `reasoning` parameter (see `supported_parameters` in the catalog record for `anthropic/claude-opus-4.6`). aichat-ng's mechanism for per-call parameter overrides is `--set` or a patch body in client config. First try CLI:

    aichat-ng -m openrouter:anthropic/claude-opus-4.6 --set reasoning=true --no-stream < /tmp/openrouter-test-thinking-prompt.txt > /tmp/openrouter-test-thinking-or-46-set.txt 2>&1 || true

If `--set` isn't supported for arbitrary parameters, fall back to a direct curl:

    API_KEY=$(python3 -c "import yaml; c=yaml.safe_load(open('$HOME/.config/aichat_ng/config.yaml')); print([x for x in c['clients'] if x.get('name')=='openrouter'][0]['api_key'])")
    # Build the JSON with jq so the prompt file is substituted in — avoids heredoc quoting issues
    jq -n --arg prompt "$(cat /tmp/openrouter-test-thinking-prompt.txt)" '{
      model: "anthropic/claude-opus-4.6",
      messages: [{role: "user", content: $prompt}],
      reasoning: {max_tokens: 4000},
      max_tokens: 1500
    }' > /tmp/openrouter-test-thinking-or-46-body.json
    curl -sS https://openrouter.ai/api/v1/chat/completions \
      -H "Authorization: Bearer $API_KEY" \
      -H "Content-Type: application/json" \
      -d @/tmp/openrouter-test-thinking-or-46-body.json \
      > /tmp/openrouter-test-thinking-or-46-curl.json
    python3 -c "import json; r=json.load(open('/tmp/openrouter-test-thinking-or-46-curl.json')); print(json.dumps(r, indent=2))" | head -60

Goal: confirm OR returns reasoning content, identify what aichat-ng would need to expose it.

- [ ] **Step 5: Record findings.**

Append to `/tmp/openrouter-phase1-findings.md`:

    ## Test 2 — Claude extended thinking via OpenRouter

    **Prompt:** (see /tmp/openrouter-test-thinking-prompt.txt)

    **Direct (`claude:claude-opus-4-6:thinking`):** <output? quality? thinking visibility?>
    **Via OR naïve (`openrouter:anthropic/claude-opus-4.6`, no reasoning param):** <output? quality?>
    **Via OR with reasoning enabled:** <works? how invoked — CLI flag / patch / curl? response shape?>

    **aichat-ng integration requirement:** <e.g., client-level `patch.chat_completions` body with `reasoning`, or a per-model override, or not doable — then we'd either keep thinking roles on direct Anthropic OR accept non-thinking via OR>

    **Verdict for thinking roles (resume_tailor, cover_letter_writer, briefing_writer):**
    - If OR-with-reasoning works via aichat-ng: route via OR
    - If only curl works: stay direct for these 3 roles (accept partial consolidation)
    - If even curl doesn't produce usable thinking output: stay direct

- [ ] **Step 6: Update the Task 2 routing table** — fill `resume_tailor`, `cover_letter_writer`, `briefing_writer` Verdict + Rationale cells.

---

## Task 5: Empirical — Opus 4.7 vs 4.6 thinking for resume_tailor and cover_letter_writer

**Files:**
- Create: `/tmp/openrouter-test-47-*.txt`
- Modify: `/tmp/openrouter-phase1-findings.md` (append "Test 3" section)

**Hypothesis:** Claude Opus 4.7 in thinking mode produces materially better `resume_tailor` / `cover_letter_writer` output than 4.6 for the same prompt. If so, upgrade is a slam-dunk (same $/token per catalog).

- [ ] **Step 1: Construct representative prompts using the real candidate profile (gitignored).**

The test is most informative when run against the actual `resume_tailor` / `cover_letter_writer` inputs, because model quality differences on generic prompts won't predict quality differences on the real pipeline's prompts. Build the test prompts by combining:

1. A real target-job record from the pipeline DB (pick any open role in `data/pipeline.db` with a populated JD — e.g., `sqlite3 data/pipeline.db "SELECT title, company, url FROM jobs WHERE stage='scored' AND jd IS NOT NULL ORDER BY relevance_score DESC LIMIT 3"` on docker.lan via `sudo -u lad sqlite3 ...`).
2. A real bullet from `candidate_context/master_resume.md` (gitignored — read on laptop).
3. The role prompt template from `config/roles/resume_tailor.md` and `config/roles/cover_letter_writer.md`.

**Save the combined prompts in `/tmp/openrouter-test-47-resume-prompt.txt` and `/tmp/openrouter-test-47-cover-prompt.txt`. Do not inline the content into this plan file — all candidate-specific content stays in gitignored or scratch files per CLAUDE.md PII rules.**

Sanity bound: each prompt should be structured like `<role template> + <master resume excerpt> + <target JD>`. Keep the JD excerpt under ~400 words so each call stays fast.

- [ ] **Step 2a: Run Prompt A (resume bullet) through the variants.**

The Task 1 Step 5 preflight already decided whether "4.7 direct" is possible. If that decision was "via-OR only," skip the `claude:claude-opus-4-7` line; otherwise run all four.

    # 4.6 direct (current production)
    aichat-ng -m claude:claude-opus-4-6:thinking --no-stream < /tmp/openrouter-test-47-resume-prompt.txt > /tmp/openrouter-test-47-resume-46-direct.txt

    # 4.7 direct — only if preflight confirmed models-override.yaml has it
    aichat-ng -m claude:claude-opus-4-7:thinking --no-stream < /tmp/openrouter-test-47-resume-prompt.txt > /tmp/openrouter-test-47-resume-47-direct.txt

    # 4.6 via OR — skip if Task 4 verdict was "stay direct for thinking roles"
    aichat-ng -m openrouter:anthropic/claude-opus-4.6 --no-stream < /tmp/openrouter-test-47-resume-prompt.txt > /tmp/openrouter-test-47-resume-46-or.txt

    # 4.7 via OR
    aichat-ng -m openrouter:anthropic/claude-opus-4.7 --no-stream < /tmp/openrouter-test-47-resume-prompt.txt > /tmp/openrouter-test-47-resume-47-or.txt

- [ ] **Step 2b: Run Prompt B (cover letter opener) through the same variants.**

    # 4.6 direct
    aichat-ng -m claude:claude-opus-4-6:thinking --no-stream < /tmp/openrouter-test-47-cover-prompt.txt > /tmp/openrouter-test-47-cover-46-direct.txt

    # 4.7 direct — skip if preflight said no
    aichat-ng -m claude:claude-opus-4-7:thinking --no-stream < /tmp/openrouter-test-47-cover-prompt.txt > /tmp/openrouter-test-47-cover-47-direct.txt

    # 4.6 via OR — skip if Task 4 verdict was "stay direct"
    aichat-ng -m openrouter:anthropic/claude-opus-4.6 --no-stream < /tmp/openrouter-test-47-cover-prompt.txt > /tmp/openrouter-test-47-cover-46-or.txt

    # 4.7 via OR
    aichat-ng -m openrouter:anthropic/claude-opus-4.7 --no-stream < /tmp/openrouter-test-47-cover-prompt.txt > /tmp/openrouter-test-47-cover-47-or.txt

- [ ] **Step 3: Side-by-side qualitative review.**

Read each output carefully. For each of the two prompts, rank 4.6 vs 4.7 on:
- **Specificity** — does it reference concrete target-company signals?
- **Concision** — word budget respected?
- **Voice** — does it sound like the candidate (whose profile is in `candidate_context/master_resume.md`), or generic?
- **Risk** — any hallucinated claims?

This is judgment, not metric. Write a short comparative paragraph per prompt.

- [ ] **Step 4: Record findings.**

Append to `/tmp/openrouter-phase1-findings.md`:

    ## Test 3 — Opus 4.7 vs 4.6 thinking (resume_tailor + cover_letter_writer)

    ### Prompt A — Resume bullet tailor
    - 4.6 direct: <paste output verbatim>
    - 4.7 direct: <paste output verbatim, or "not available at laptop — see 4.7 via OR">
    - 4.7 via OR: <paste output verbatim>
    - **Comparative:** <2-4 sentences: is 4.7 materially better, same, or worse?>

    ### Prompt B — Cover letter opener
    - (same four-way)

    **Verdict — should resume_tailor + cover_letter_writer upgrade to 4.7?**
    - <Yes / No / More testing needed>
    - Cost delta: same per-token pricing (catalog confirms)
    - Latency delta: <note rough subjective feel, precise numbers defer to Task 7>

- [ ] **Step 5: Update the Task 2 routing table** if the verdict is "upgrade to 4.7" — note that resume_tailor and cover_letter_writer rows should record both the model change AND the OR-vs-direct route choice inherited from Task 4.

---

## Task 6: Confirm Gemini embeddings stay direct

**Files:**
- Modify: `/tmp/openrouter-phase1-findings.md` (append "Test 4" section — short)

- [ ] **Step 1: Re-verify OR catalog has no embedding endpoints.**

Run:

    python3 -c "
    import json
    d = json.load(open('/tmp/openrouter_catalog.json'))
    emb = [m for m in d['data'] if 'embed' in m['id'].lower()]
    print('embedding-named models:', len(emb))
    for m in emb: print(' ', m['id'])
    # Also check input_modalities for any embedding-ish signal
    emb_arch = [m['id'] for m in d['data'] if 'embed' in (m.get('description') or '').lower()]
    print('description mentions embedding:', len(emb_arch))
    for m in emb_arch[:5]: print(' ', m)
    "

Expected: `embedding-named models: 0`.

- [ ] **Step 2: Record verdict in notebook.**

Append:

    ## Test 4 — Gemini embeddings

    OpenRouter catalog contains zero embedding endpoints (verified 2026-04-24 against snapshot).
    **Verdict — locked:** `gemini-embed:gemini-embedding-001` stays direct. RAG rebuild weekly cron
    continues to hit Google AI directly. This is the only role explicitly excluded from consolidation.

- [ ] **Step 3: No table update needed** — `embedding` row is already locked in Task 2.

---

## Task 7: Spot-check latency + cost delta

**Files:**
- Modify: `/tmp/openrouter-phase1-findings.md` (append "Test 5" section)

**Goal:** Rough numbers, not a benchmark. Precise instrumentation belongs to #48.

- [ ] **Step 1: Time a typical scorer call direct (already on OR — baseline).**

Run, three trials, take the median:

    for i in 1 2 3; do
      time aichat-ng -m openrouter:deepseek/deepseek-v3.2 --no-stream "Score this job title-only for fit with a data center infrastructure / NPI candidate: 'Senior TPM, AI Infrastructure'. One sentence verdict + 1-10 score." >/dev/null
    done

Record median wall-clock.

- [ ] **Step 2: Time the same prompt via `perplexity:` direct to establish non-OR baseline.**

Run:

    for i in 1 2 3; do
      time aichat-ng -m perplexity:sonar-reasoning-pro --no-stream "Summarize what Anthropic does in one sentence." >/dev/null
    done
    for i in 1 2 3; do
      time aichat-ng -m openrouter:perplexity/sonar-reasoning-pro --no-stream "Summarize what Anthropic does in one sentence." >/dev/null
    done

Record both medians. OR-proxy overhead is the delta.

- [ ] **Step 3: Compute cost delta at current volume.**

Reference volume (from Session 2026-04-24 scoping): ~200 scorer calls/day, ~2-3 prep runs/day (each prep = 3-4 LLM calls including thinking). Estimate monthly LLM spend order-of-magnitude; apply OR's ~5.5% markup. User has already accepted this markup, so this is an informational line in the verdict, not a decision point.

- [ ] **Step 4: Record findings.**

Append:

    ## Test 5 — Latency + cost

    - Direct scorer (already OR): median <X>s for title-only score
    - Direct Perplexity: median <X>s — via OR: median <X>s — overhead: <X>s (<Y>%)
    - Estimated monthly spend at current volume: ~$<X>/month; OR markup ≈ $<X>
    - **Verdict:** acceptable (markup already accepted; latency overhead tolerable for batch).

---

## Task 8: Compile and post verdict comment on issue #22

**Files:**
- Create: `/tmp/openrouter-phase1-verdict.md` (comment body for GitHub)
- Read: `/tmp/openrouter-phase1-findings.md`

- [ ] **Step 1: Draft the verdict comment.**

Open `/tmp/openrouter-phase1-findings.md` and extract the essentials into a tighter GitHub comment at `/tmp/openrouter-phase1-verdict.md`. Structure:

    ## Session 2026-04-24 — Phase 1 investigation complete

    **Bottom line:** <Full consolidation | Partial: keep <N> roles direct | Stay as-is>

    ### Per-role routing recommendation

    (final version of the Task 2 table with all "Decide after" cells filled)

    ### Open questions — answers

    1. **Perplexity citation passthrough:** <verdict + one-sentence evidence>
    2. **Claude extended thinking via OR:** <verdict + aichat-ng integration requirement>
    3. **Gemini embeddings:** stay direct (confirmed — zero embedding endpoints in OR catalog)

    ### Opus 4.7 upgrade (resume_tailor, cover_letter_writer)

    - <Upgrade / Defer / Mixed>
    - <2-3 sentence rationale from Task 5 comparative>

    ### Latency + cost

    - OR proxy overhead: ~<X>% (acceptable for batch workload)
    - Monthly cost delta: ~$<X> markup at current volume

    ### Phase 2 scope (separate issue)

    Roles to cut over via OR: <list>
    Roles staying direct: <list + reason>
    Config files that will need edits in Phase 2: `~/.config/aichat_ng/models-override.yaml`, `config/roles/*.md` (model headers), `CLAUDE.md` §Pipeline Context Table.

    ### Artifacts

    Raw findings notebook: `/tmp/openrouter-phase1-findings.md` (laptop, volatile).
    Test outputs: `/tmp/openrouter-test-*.txt` (laptop, volatile).

- [ ] **Step 2: Self-review the comment** — every table cell filled, every open question answered, no "TBD" strings.

Run:

    grep -n -iE 'tbd|todo|<.+>' /tmp/openrouter-phase1-verdict.md || echo "clean"

Expected: `clean` (or only matches inside intentional `< >` labels — review each).

- [ ] **Step 3: Post the comment.**

Run:

    gh issue comment 22 -F /tmp/openrouter-phase1-verdict.md

Expected: GitHub returns a comment URL. Capture it.

- [ ] **Step 4: Update Jared session note** — the Session note on #22 was the pre-session plan; now add a new Session comment recording the actual outcome, next action, and state. Use:

    /home/brockamer/Code/jared/skills/jared/scripts/jared comment 22 "$(cat <<'NOTE'
    ## Session 2026-04-24 (evening)

    **Progress:** Phase 1 investigation complete. Verdict posted above — see "Session 2026-04-24 — Phase 1 investigation complete."

    **Decisions:** <summary of the cutover scope decision>

    **Next action:** File Phase 2 cutover issue with scoped role list + the three config surfaces (models-override.yaml, role .md headers, CLAUDE.md table). Sequence Phase 2 against #48 (cost instrumentation) — decide whether to cut over first or instrument first.

    **Gotchas:** <anything surprising from empirical tests>

    **State:** #22 stays In Progress through the verdict-post, then closes this session only if Phase 2 issue is filed and #22's acceptance criteria (written verdict) is met. Otherwise move #22 back to Up Next with In Progress reserved for the Phase 2 issue.
    NOTE
    )"

- [ ] **Step 5: Decide issue state.**

Acceptance criteria for #22 (per issue body): "Written verdict on each open question + recommendation on whether to consolidate fully, partially, or stay-as-is." That is now satisfied. Close #22 and file the Phase 2 cutover issue as the natural follow-up — OR keep #22 open as the tracking issue for the whole 3-phase rollout. Choose one; both are defensible. Recommended: close #22 (acceptance criteria met), file Phase 2.

---

## Task 9: Wrap the session

Plan was already committed + pushed in Task 0. This task just verifies the worktree is clean and the session's state on the board + remote is coherent.

- [ ] **Step 1: Verify no stray tracked changes.**

Run:

    git status

Expected: no modified or staged files in `docs/`, `src/`, `config/`, or `tests/`. The 13 untracked PNGs predate this session and are unrelated to this work.

- [ ] **Step 2: Verify remote is caught up.**

Run:

    git log --oneline origin/main..main

Expected: empty output (local and remote `main` are at the same commit).

- [ ] **Step 3: Confirm issue #22 final state.**

Run:

    /home/brockamer/Code/jared/skills/jared/scripts/jared summary | grep -A1 "#22\|In Progress"

Expected: #22 is either closed (acceptance criteria met, per Task 8 Step 5 decision) or back in Up Next with a Phase 2 follow-up issue now showing in the list.

---

## Documentation Impact

- **CLAUDE.md** §Pipeline Context Table: not yet — Phase 2 updates this when roles actually cut over. In this phase, we only *recommend* changes.
- **`docs/project-board.md`**: no update — board conventions unchanged by this investigation.
- **CHANGELOG.md**: no entry — investigation produces no user-visible change. Phase 2 gets a CHANGELOG entry if it alters provider routing for operators.
- **Spec doc**: none. This plan is the investigation spec; the GitHub comment on #22 is the specification input for Phase 2.
- **`docs/superpowers/plans/2026-04-24-openrouter-phase-1-investigation.md`**: this file (new, committed in Task 9).
- **README / setup docs**: no change — API-key setup is unchanged in Phase 1.

---

## Whole-feature verification gate

Before declaring the investigation complete, verify all of:

- [ ] Task 2 routing table has **zero** "Decide after Task N" cells remaining — every role has a final verdict.
- [ ] All three open questions from issue #22 (Perplexity citations, Claude thinking, Gemini embeddings) have written answers grounded in empirical test output, not inference.
- [ ] Opus 4.7 comparative test was run for **both** `resume_tailor` and `cover_letter_writer` prompts (not just one).
- [ ] Verdict comment posted on issue #22 and the URL recorded.
- [ ] A Phase 2 follow-up path exists — either a new issue filed, or #22 itself moves to Phase 2 scope with an explicit updated body.
- [ ] Scratch notebook `/tmp/openrouter-phase1-findings.md` contains enough detail to reconstruct the verdict if the GitHub comment were lost (defense in depth for volatile laptop state).
- [ ] No API keys appear in the plan file, the findings notebook, the verdict comment, or any committed artifact.

---

## Self-review — spec-to-task mapping

Checking each spec requirement (from issue #22 body + Session 2026-04-24 scoping comment + today's user direction) against the tasks above:

| Spec requirement | Implemented by |
|---|---|
| Full OpenRouter model catalog review | Task 1 |
| Per-role routing table (9 roles + embedding) | Task 2 (skeleton), Tasks 3/4/5 (fill verdicts) |
| Perplexity web-search grounding metadata passthrough | Task 3 |
| Claude extended thinking via OR (shape + aichat-ng integration) | Task 4 |
| Gemini embeddings availability on OR | Task 6 |
| Opus 4.7 thinking quality test (user-added today) | Task 5 |
| Latency delta | Task 7 |
| Cost delta at current volume | Task 7 |
| Written verdict on each open question | Task 8 comment |
| Overall recommendation (full / partial / stay-as-is) | Task 8 comment "Bottom line" |
| Cutover scope for Phase 2 | Task 8 comment "Phase 2 scope" |
| Plan committed durably | Task 9 |

No spec requirement left unmapped.
