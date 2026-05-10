# findajob

**Self-hosted job search infrastructure: AI triages thousands of listings down to a handful, generates tailored materials for the ones worth applying to, and learns from every rejection.**

The modern job search grinds people down — hundreds of listings per day, most irrelevant; the same cover letter rewritten at midnight; black-hole rejections that tell you nothing about whether you targeted wrong, wrote wrong, or got unlucky. findajob absorbs the triage, the tailoring, and the tracking so your attention goes to the few applications actually worth sending.

A pre-1.0 personal project — used daily by the operator and a small wave of beta testers, not a polished product yet.

---

## What it does

The pipeline narrows the funnel at every step where a human would otherwise waste attention — LLM triage on the way in, human triage on the way to prep, prep only for jobs worth applying to. Thirty days on the operator's instance looks like this:

```
Listings ingested                12,824   ──────────────────────────────
LLM-scored ≥7 (worth a look)        393   ▓                              3.1%
Operator flagged for prep           160   ▓▓▓▓▓▓▓▓▓▓                    41% of scored
Applications submitted               60   ▓▓▓▓▓▓▓▓▓                     38% of prepped
Interviews (lifetime)                  6
```

12,824 listings narrowed to 60 applications. Every rejection along the way is recorded with a reason — *Skills Mismatch*, *Too Senior*, *Comp Too Low*, *Geography/Onsite* — and those reasons feed back into tomorrow's scorer as negative examples. The system gets better at *your* search every week.

---

## How it works

**1. Daily triage** (00:00, scheduler-driven) — pulls 100–500 listings from LinkedIn (via RapidAPI), Indeed, direct ATS feeds (Greenhouse, Ashby, Lever, Workday), and your Gmail job alerts; cleans, deduplicates, enriches with job-description text; scores each against your candidate profile using DeepSeek v3.2.

**2. Dashboard triage** — the web UI shows every scored job that cleared the threshold with relevance/fit/probability scores, known contacts from your LinkedIn export, and the LLM's notes on why it scored where it did. You flag the ones worth prepping.

![Dashboard](docs/screenshots/dashboard.png)

*Fictional demo data spanning data-center ops, social services, and K-12 education — the same pipeline works for every field, only `profile.md` changes.*

**3. Prep** (one click) — generates a per-job folder containing a tailored resume, cover letter, deep-research company briefing, recruiter-perspective critique, and outreach drafts for known contacts. Claude Opus does the writing; Perplexity does the company research. ~$1–2 of LLM spend per prep run, in 5-10 minutes.

**4. Apply and track** — submit the application, mark *Applied*. The Applied tab color-codes rows by days-since-submission so silent applications surface at a glance.

![Applied](docs/screenshots/applied.png)

**5. Reject with reason** — jobs that don't pan out get rejected with a tagged reason. Those reasons are training examples for the next day's scorer. Manual-review flags point at the parts of your profile the LLM found ambiguous, so you know exactly where to tune.

**6. See the system working** — funnel and rejection-mix dashboards make the pipeline legible. Scorer drifting? Rejection reason spiking? You see it instead of guessing.

![Funnel](docs/screenshots/funnel.png)

---

## Why use it

- **Triage cuts the noise so you can focus.** 12K → 60 isn't unusual once the scorer learns your profile. Most job tools track what you applied to; this one finds the few worth applying to.
- **Your rejections train tomorrow's scoring.** Every *Skills Mismatch* / *Too Senior* / *Comp Too Low* tag is a labeled example. No other AI job tool closes that loop.
- **Tailored materials, locally generated.** Per-job folder with resume + cover letter + briefing + outreach drafts, sitting on your Docker host as plain `.docx` and `.md`. SQLite for state. The only outbound calls are to the LLM providers you've configured. No SaaS lock-in for your most personal data.
- **Field-agnostic.** Built by a data-center-ops candidate; works just as well for a social worker, teacher, accountant, or trades professional. Same pipeline, same setup — only `profile.md` changes. See [`docs/maintainers/generalization.md`](docs/maintainers/generalization.md).

---

## Stack

| Component | Choice |
|---|---|
| Triage scoring | DeepSeek v3.2 via OpenRouter |
| Materials writing | Claude Opus 4.7 + Sonnet 4.6 via OpenRouter (prompt caching enabled) |
| Company research | Perplexity Sonar Pro |
| Job sources | RapidAPI (LinkedIn, Indeed, Bing, JSearch), direct ATS feeds (Greenhouse, Ashby, Lever, Workday CXS), Gmail IMAP — opt-in per source at `/settings/active-sources/` |
| Storage | SQLite |
| Web UI | FastAPI + HTMX + Tailwind + Chart.js |
| Push notifications | [ntfy.sh](https://ntfy.sh) |
| Scheduler | supercronic (in-container) |

---

## Quick start

The pipeline ships as `ghcr.io/brockamer/findajob`, pulled via Docker Compose. Multi-arch image (`linux/amd64` + `linux/arm64`) — Apple Silicon and ARM Linux hosts get a native build automatically.

### What you'll need

One required API key:

- **OpenRouter** — funds every LLM call (triage scoring, materials writing, in-app onboarding interview). Pay-as-you-go from $0; expect ~$0.50/day when triaging only, ~$1–2 per fully-prepped job.

One optional API key:

- **RapidAPI (jobs-api14)** — LinkedIn/Indeed/Bing search ingestion. BASIC plan is 150 req/month free, no credit card. Skipping it means LinkedIn/Indeed search is inactive, but Greenhouse/Ashby/Lever feeds and Gmail alerts still work.

Sign-up walkthroughs + cost expectations: [`docs/getting-started/api-keys.md`](docs/getting-started/api-keys.md). You collect both keys on the onboarding page once your container is up.

### Deploy

Pick any directory for your stack:

- Linux server: `/opt/stacks/findajob-<you>/` is the conventional system-path layout
- macOS or anywhere under your home directory: works fine for personal use

```bash
# Replace <stack-dir> with your chosen path
mkdir -p <stack-dir>/state/{data,config,candidate_context,companies,logs,.backups}
cd <stack-dir>

# Two .env files exist:
#   ./.env             — top-level: image tag, port, timezone (read by Docker Compose)
#   ./state/data/.env  — runtime: API keys, ntfy topic, optional basic-auth credentials
# Both must exist before `docker compose up -d` or Compose will refuse to start.
curl -fsSL -o compose.yaml         https://raw.githubusercontent.com/brockamer/findajob/main/ops/compose.yaml.example
curl -fsSL -o .env                 https://raw.githubusercontent.com/brockamer/findajob/main/ops/stack.env.example
curl -fsSL -o state/data/.env      https://raw.githubusercontent.com/brockamer/findajob/main/data/.env.example
chmod 600 state/data/.env

# Edit ./.env: set FINDAJOB_TZ to your timezone and FINDAJOB_MATERIALS_PORT to a free host port.
# Leave ./state/data/.env at the placeholder values — first-run onboarding overwrites them.
# (For internet-exposed deployments: also set FINDAJOB_AUTH_USER + FINDAJOB_AUTH_PASS
# in ./state/data/.env to gate the UI behind HTTP Basic Auth.)
docker compose up -d
```

> If you placed the stack in `/opt/stacks/`, prefix `mkdir` with `sudo` and follow with `sudo chown -R $(id -u):$(id -g) <stack-dir>/`. Skip both for paths under your home directory.

### First-run onboarding

Open `http://<your-host>:<port>/`. A fresh stack redirects to `/onboarding/`:

1. **Paste your OpenRouter key** (plus optional RapidAPI). The OpenRouter key is smoke-checked against the live API before being saved.
2. **Click Start interview.** A chat surface opens inside findajob and walks you through a 60–90 minute conversation about your background, target role, exclusions, and writing voice. The session is server-side persistent — close the tab anytime and the page surfaces a Resume affordance. Cost: ~$3–6 per interview with prompt caching.
3. **Gmail config** (optional) — wire up IMAP + an app password for LinkedIn job-alert ingestion. Skippable; configure later at `/config/gmail/`.
4. **LinkedIn Connections.csv** (optional) — drop in your LinkedIn connections export so outreach drafts can name real contacts at target companies. Skippable; upload later at `/onboarding/connections/`.

After both gates you land on the dashboard. The next scheduled triage run (00:00 in your `TZ`) ingests its first batch of jobs.

Full walkthrough → [`docs/getting-started/install-docker.md`](docs/getting-started/install-docker.md)

---

## Documentation

- **[Getting started](docs/getting-started/README.md)** — sequenced setup guide
- **[Daily workflow](docs/usage.md)** — what to do each day, web-UI tab by tab
- **[Troubleshooting](docs/troubleshooting.md)** — symptom index + log reading
- **[Architecture](docs/architecture.md)** — system design + data flow (for operators reading the code)

Live status of every issue and milestone: **[project board](https://github.com/users/brockamer/projects/1)** (the single source of truth for active work).

---

## What it costs

Real-world per-day usage on the operator's instance, ~10k jobs/month scored:

| Item | Typical day |
|---|---|
| Scoring (DeepSeek) | $0.10–0.30 |
| Per prepped job (briefing + resume + cover + critique + outreach) | $1.00 avg, $2.15 max |

Total: ~$0.50/day triage-only; ~$5–15 on days you prep several applications.

---

## Privacy and contributing

The repo contains zero personal data. All candidate content (resume, profile, writing samples, search queries, API keys) lives in gitignored paths populated from `.example` templates. The pre-commit hook blocks PII you accidentally try to commit.

- **[Issues](https://github.com/brockamer/findajob/issues)** — file a bug, request a feature
- **[Discussions](https://github.com/brockamer/findajob/discussions)** — "how do I…" or "have you considered…"
- **In-app Feedback widget** — floating button on every page files a GitHub issue directly from the web UI
- **Security** — please don't file public issues for security-relevant bugs; see [`SECURITY.md`](SECURITY.md)

Contributions welcome. Start at [`CONTRIBUTING.md`](CONTRIBUTING.md) — dev setup, commit conventions, the `migration-required` label, and the architectural invariants the code enforces.

---

## License

MIT.
