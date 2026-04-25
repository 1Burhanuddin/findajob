---
**Shipped in #250 on 2026-04-25. Final decisions captured in issue body.**
---

# OpenRouter Phase 2 — cutover 10 roles + Opus 4.7 upgrade — design

**Issue:** #250
**Parent:** #240 (OpenRouter centralization epic)
**Depends on:** #22 (Phase 1 investigation — closed with verdict)
**Out of scope (separate issues):** #48 cost instrumentation, #87 cost dashboard, #252 scorer model eval, #67 env-var migration, #225 virtual keys

## Goal

Cut over 10 of 11 pipeline roles to `openrouter:*` routes, upgrade `resume_tailor` and `cover_letter_writer` from Opus 4.6 → 4.7 (same per-token price, small-to-moderate quality edge on real-pipeline prompts per Phase 1). Embedding stays on the direct Google client — OpenRouter's catalog has zero embedding endpoints.

Pure config — no Python changes, no DB schema changes, no scheduler changes. `aichat-ng` does all the routing.

## Scope — model string flips

| Role | File | Current | New |
|---|---|---|---|
| resume_tailor | `config/roles/resume_tailor.md` | `claude:claude-opus-4-6:thinking` | `openrouter:anthropic/claude-opus-4.7` |
| cover_letter_writer | `config/roles/cover_letter_writer.md` | `claude:claude-opus-4-6:thinking` | `openrouter:anthropic/claude-opus-4.7` |
| briefing_writer | `config/roles/briefing_writer.md` | `claude:claude-sonnet-4-6:thinking` | `openrouter:anthropic/claude-sonnet-4.6` |
| outreach_drafter | `config/roles/outreach_drafter.md` | `claude:claude-sonnet-4-6` | `openrouter:anthropic/claude-sonnet-4.6` |
| company_researcher | `config/roles/company_researcher.md` | `perplexity:sonar-reasoning-pro` | `openrouter:perplexity/sonar-reasoning-pro` |
| fit_analyst | `config/roles/fit_analyst.md` | `perplexity:sonar-reasoning-pro` | `openrouter:perplexity/sonar-reasoning-pro` |
| resume_change_reviewer | `config/roles/resume_change_reviewer.md` | `gemini:gemini-3-flash-preview` | `openrouter:google/gemini-3-flash-preview` |
| network_analyst | `config/roles/network_analyst.md` | `gemini:gemini-3-flash-preview` | `openrouter:google/gemini-3-flash-preview` |
| default (REPL, onboarding_interviewer, any role without `model:` front-matter) | `ops/aichat-ng/config.yaml.example` top-level `model:` | `gemini:gemini-3-flash-preview` | `openrouter:google/gemini-3-flash-preview` |
| job_scorer | unchanged — already on `openrouter:deepseek/deepseek-v3.2` | — | — |
| embedding | unchanged — stays direct (`gemini-embed:gemini-embedding-001`) | — | — |

**Catalog edits in `ops/aichat-ng/models-override.yaml`:**
1. Add `anthropic/claude-opus-4.7` entry under the existing `openrouter` provider block. Pricing: $5/M input, $25/M output per OR catalog (same as 4.6). Context: 200k input / 32k output. Thinking-capable.
2. Verify these target strings are already in the openrouter provider block; append any missing:
   - `anthropic/claude-sonnet-4-6`
   - `perplexity/sonar-reasoning-pro`
   - `google/gemini-3-flash-preview`
   - `deepseek/deepseek-v3.2` (already shipped for scorer)

## Parallel eval gate — pre-merge

**Method:** shadow role files on the operator stack, no branch/image/deploy required.

1. On the operator stack on docker.lan, copy the 4 quality-critical role files to shadow variants inside the stack's mounted `/app/config/roles/` (or invoke `aichat-ng` with `--role <path>` pointing at a scratch location):
   - `resume_tailor_phase2.md`
   - `cover_letter_writer_phase2.md`
   - `briefing_writer_phase2.md`
   - `outreach_drafter_phase2.md`
   Each identical to the current role except the `model:` front-matter points to the Phase 2 target.
2. Select 5–10 jobs from `/app/companies/` or `/app/companies/_applied/` that were **prepped within the last 3–4 days**. This cutoff is important — older materials reflect role prompts and format rules that have since evolved, which would confound the model-quality delta with role-drift delta.
3. For each job, re-invoke each shadow role against the same inputs (JD + profile + master_resume) used at original prep time. Capture output alongside the original.
4. Hand-diff: resume FORMAT LAW compliance, cover letter voice, briefing usefulness, outreach tone.
5. **Decision rule:** parity-or-better on at least 4 of every 5 jobs per role, no "obvious regression" flags on any job. If a single role regresses, back out just that role's front-matter flip from the PR before merge; append a "Regressions excluded from cutover" addendum at the bottom of this spec listing the role + observed regression, and note in the CHANGELOG entry.
6. The 5 background roles (`company_researcher`, `fit_analyst`, `resume_change_reviewer`, `network_analyst`, default) are **not** in the manual eval — Phase 1 verdict established route-only swaps (no model change) are functionally equivalent to direct-provider calls. They're covered by the post-deploy smoke check.

**Estimated cost:** ~$1–2 in API spend. **Estimated time:** ~45 min of human review.

## Files changed

Tracked:
- `config/roles/resume_tailor.md` — `model:` front-matter
- `config/roles/cover_letter_writer.md` — `model:` front-matter
- `config/roles/briefing_writer.md` — `model:` front-matter
- `config/roles/outreach_drafter.md` — `model:` front-matter
- `config/roles/company_researcher.md` — `model:` front-matter
- `config/roles/fit_analyst.md` — `model:` front-matter
- `config/roles/resume_change_reviewer.md` — `model:` front-matter
- `config/roles/network_analyst.md` — `model:` front-matter
- `ops/aichat-ng/config.yaml.example` — top-level `model:` default
- `ops/aichat-ng/models-override.yaml` — add `anthropic/claude-opus-4.7`; verify others present
- `CLAUDE.md` — Pipeline Context Table rows (9 updates)
- `CHANGELOG.md` — `[Unreleased]` entry with migration guidance
- `docs/superpowers/specs/2026-04-24-openrouter-phase-2-cutover-design.md` — this spec
- `docs/setup/` — short OR-key-rotation paragraph; exact file located at plan time

Not touched:
- Any file under `src/findajob/`, `scripts/`, `tests/` — no code changes.
- `data/pipeline.db` — no schema changes.
- `config/roles/job_scorer.md`, `config/roles/onboarding_interviewer.md` — scorer already on OR; onboarding has no model front-matter, inherits updated default.

## Deploy plan

Role files (`config/roles/*.md`) are baked into the image under `/app/config/roles/`. `config.yaml` and `models-override.yaml` live on each stack under bind-mounted `state/aichat_ng/`.

**Pre-deploy tag verification:** at the start of the deploy session, confirm current stack pins on every findajob stack on docker.lan:

```
ssh docker.lan 'grep FINDAJOB_IMAGE_TAG /opt/stacks/findajob-*/.env'
```

Do not assume pins from memory — pinned minor aliases roll between sessions. Spec was drafted with the beta-tester stack on `:v0.3` and the operator stack on `:latest` as of 2026-04-24; re-verify at deploy time.

**Step 1 — merge PR.** Release-notes workflow publishes the migration notice.

**Step 2 — operator stack (`:latest`).** Path: `/opt/stacks/findajob-<operator>/`.
1. `ssh docker.lan 'cd /opt/stacks/findajob-<operator> && docker compose pull && docker compose up -d'` — image pull gives the new role front-matters.
2. Edit bind-mounted `state/aichat_ng/config.yaml` top-level `model:` line to `openrouter:google/gemini-3-flash-preview`.
3. Diff `state/aichat_ng/models-override.yaml` against `ops/aichat-ng/models-override.yaml` in the repo; append the `anthropic/claude-opus-4.7` entry (and any other missing target strings).
4. Restart aichat-ng consumers if needed (triage runs on the next cron tick; manual prep is on-demand).

**Step 3 — observe.** One daily triage + one on-demand prep must complete cleanly on the operator stack. Watch `log_event` for new error classes over 24h.

**Step 4 — beta-tester stack(s)** (pinned to `:vMAJOR.MINOR`). Path: `/opt/stacks/findajob-<beta>/`. This is a minor-version advancement on the pinned alias. The cutover lands on `main` before any new tag cut, so the pinned minor will pick it up only after the next release tag is built. Two paths:

- **Preferred — cut the next release before advancing the beta pin.** Follow `docs/release-process.md`: dogfood gate on the operator stack (the 24h observation above satisfies it), tag the next minor (verify current released minor at deploy time — spec drafted with `v0.3` as the latest minor), let `build-image.yml` push the new `:vMAJOR.MINOR` and `:latest`, then edit the beta stack's `.env` to advance the pin, `docker compose pull && up -d`, and do the same bind-mount edits as on the operator stack.
- **Acceptable — if the release is not ready, defer the beta-stack cutover.** No urgency; the beta stack continues on its pinned minor without the new roles until a tag is cut.

**Step 5 — post-deploy verification per stack.** One triage + one prep complete cleanly; no new `log_event` error classes in 24h.

## Rollback

- **Pre-merge, per-role:** remove the offending role's front-matter flip from the PR. Document in CHANGELOG as "cutover excluded <role> pending investigation."
- **Post-merge, pre-deploy:** `git revert <PR-merge-commit>`, re-release.
- **Post-deploy, per-stack:** edit the bind-mounted `config.yaml` and role files on docker.lan back to old model strings. No image revert required. File a follow-up issue documenting the regression.
- **Total rollback blast radius:** zero DB state, zero filesystem artifacts under `companies/`, zero schema changes. Only YAML + Markdown front-matter on two stacks.

## Success criteria

1. Parallel eval passes: parity-or-better on 4/5 jobs per role across the 4 quality-critical roles.
2. PR merges with all tracked files listed above and the `migration-required` label.
3. Operator stack: one full triage + one prep complete cleanly post-deploy; no new `log_event` error classes in 24h.
4. Beta-tester stack(s): same verification post-deploy (after next release tag is cut and the pin is advanced).
5. `CLAUDE.md` Pipeline Context Table, `CHANGELOG.md`, `ops/aichat-ng/config.yaml.example`, and `ops/aichat-ng/models-override.yaml` all updated in the same PR.
6. Post-deploy, audit a random prep run's materials — they should be indistinguishable from (or better than) current-baseline outputs in style, format, and accuracy.

## Deferred — reasoning body patch (optional follow-up)

Phase 1 verdict proposed adding a `patch.chat_completions` body patch on the `openrouter` client in `config.yaml` to inject `reasoning: {max_tokens: 4000}` for Claude model patterns. Empirical finding: Claude models reason implicitly on OR even without this patch, and naive-OR output is already production-quality.

This patch would add **transparency** (visible chain-of-thought traces in aichat-ng output) but does not materially change output quality. Deferred from this cutover because:
1. Phase 1 never empirically tested whether aichat-ng 0.31.0's `patch.chat_completions` mechanism applies correctly to an `openai-compatible` client (the `openrouter` client). If the patch doesn't take effect, bundling it would gate the cutover on debugging aichat-ng internals not on the critical path.
2. Output quality is the Phase 2 goal; reasoning-trace visibility is a separate observability/debugging concern.

Proposed body patch (for the future issue):

```yaml
clients:
  - type: openai-compatible
    name: openrouter
    api_base: https://openrouter.ai/api/v1
    api_key: ${OPENROUTER_API_KEY}
    patch:
      chat_completions:
        '.*/claude.*':
          body:
            reasoning:
              max_tokens: 4000
```

File a follow-up issue after cutover ships if reasoning-trace visibility becomes desirable.

## Documentation impact

- **`CLAUDE.md` Pipeline Context Table** — 9 row updates reflecting the new routes and the 4.7 versions for resume/CL.
- **`CHANGELOG.md`** — new `[Unreleased]` entry describing the cutover + migration steps; PR carries `migration-required` label so `release-notes-release-automation.yml` surfaces it to external operators.
- **`ops/aichat-ng/config.yaml.example`** — updated default `model:` line; existing users upgrading in place must manually edit their bind-mounted `config.yaml` (template is only seeded on fresh install).
- **`docs/setup/`** — short paragraph on rotating the single `OPENROUTER_API_KEY`. Exact destination file located at plan time (likely `docs/setup/configure.md` or a new short `docs/setup/rotating-keys.md`).
- **Spec doc** — this file, at `docs/superpowers/specs/2026-04-24-openrouter-phase-2-cutover-design.md`.
- **No changes** to `docs/usage.md`, `docs/troubleshooting.md`, `docs/release-process.md`, `README.md`, `docs/project-board.md`.
