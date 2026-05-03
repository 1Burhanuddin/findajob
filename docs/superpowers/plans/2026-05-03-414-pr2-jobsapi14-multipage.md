# #414 PR2 — `JobsApi14Adapter` multi-page LinkedIn fetch

## 1. Goal + scope

**Goal.** Loop `JobsApi14Adapter.fetch()` over `meta.nextToken` to bring back more
than the API's hard-fixed 10 jobs/page from the LinkedIn endpoint. Each query
keeps making `/v2/linkedin/search` calls — passing the prior response's
`nextToken` as the `token` query param — until either (a) `nextToken` is
absent, (b) a configurable per-stack `max_pages` ceiling is reached, or (c) a
non-retryable error breaks the loop. Default ceiling is `1` (current behavior),
making this PR an opt-in expansion. Operators on PRO tier raise the ceiling per
stack via env var.

The §C dupe-rate measurement on operator's stack (97-100% source-exclusivity,
9.2% within-source dedup) confirms additional pages on LinkedIn are near-additive
yield against current sources.

**Out of scope.**

- JSearch `num_pages` configurability (PR3 — pending empirical billing probe; tracked under #414).
- Bing endpoint as separate adapter (PR4 — deferred; tracked under #414).
- `JobsApi14IndeedAdapter` multi-page (separate scope; Indeed already returns 20/page so single-page yields more than LinkedIn's full multi-page; revisit if quota lets it).
- Source-aware query allocation (§C item 2 — separate brainstorm).

## 2. Tasks

### Task 1 — Empirical billing probe (manual, before implementation)

**Why first:** the handoff and #414 issue body both flag this as a precondition.
We assume each `nextToken` call is a separate billed RapidAPI request, but one
empirical confirmation costs 1 quota unit and avoids designing the env-var
ceiling around a wrong cost model.

**Steps:**

1. From operator's stack, capture `x-ratelimit-requests-remaining` BEFORE the probe:

   ```
   ssh docker.lan 'sudo -u lad docker exec -u 1000 findajob-<operator>-scheduler-1 \
     curl -sI -H "x-rapidapi-host: jobs-api14.p.rapidapi.com" \
              -H "x-rapidapi-key: $RAPIDAPI_KEY" \
              "https://jobs-api14.p.rapidapi.com/v2/linkedin/search?query=engineer&location=United%20States&datePosted=day" \
     | grep -i "x-ratelimit-requests-remaining"'
   ```

   Per `feedback_curl_redirect_url_leak`, never use `-w "%{redirect_url}"` here.
   Per `feedback_never_print_secrets`, the `$RAPIDAPI_KEY` interpolation happens
   inside `docker exec`'s shell — value never crosses ssh stdout.

2. Make a first call, capture `meta.nextToken` from JSON body:

   ```
   ssh docker.lan 'sudo -u lad docker exec -u 1000 findajob-<operator>-scheduler-1 \
     bash -c "curl -s -H \"x-rapidapi-host: jobs-api14.p.rapidapi.com\" \
                       -H \"x-rapidapi-key: \$RAPIDAPI_KEY\" \
                       \"https://jobs-api14.p.rapidapi.com/v2/linkedin/search?query=engineer&location=United%20States&datePosted=day\" \
              | python3 -c \"import json,sys; d=json.load(sys.stdin); print(d.get(\\\"meta\\\",{}).get(\\\"nextToken\\\",\\\"NONE\\\"))\""'
   ```

3. Make a second call passing `token=<that>` as the only material param.

4. Capture `x-ratelimit-requests-remaining` AFTER. Observation:
   - Drop of exactly **2** = each `nextToken` call is a separate billed unit (assumed).
   - Drop of exactly **1** = paginated calls are batched on the billing dimension (would change the cost model materially).

**Verification:** screenshot or text capture of before/after `x-ratelimit-requests-remaining` header values, posted as a comment on #414. Confirms the cost model the env-var ceiling design depends on.

**Commit message:** N/A — this task produces only an issue comment, no code.

---

### Task 2 — Add `JOBS_API14_MAX_PAGES` env var resolver

**Files:**
- `src/findajob/fetchers/adapters/jobs_api14.py` — add `_max_pages()` method
- `src/findajob/fetchers/adapters/jobs_api14.py` — add module constant `_DEFAULT_MAX_PAGES = 1`

**Steps:**

1. Add class method:

   ```python
   @classmethod
   def _max_pages(cls) -> int:
       """Per-stack pagination ceiling. Default 1 (current behavior).

       Set JOBS_API14_MAX_PAGES=N in data/.env to fetch up to N pages per
       query. Each page is one billed RapidAPI request (confirmed empirically
       in #414 PR2 task 1). Recommended for PRO-tier stacks; free-tier stacks
       should stay at 1.
       """
       raw = os.environ.get("JOBS_API14_MAX_PAGES", "").strip()
       if not raw:
           return cls._DEFAULT_MAX_PAGES
       try:
           value = int(raw)
       except ValueError:
           log_event("jobsapi_max_pages_invalid", value=raw)
           return cls._DEFAULT_MAX_PAGES
       return max(1, min(value, 20))  # clamp to [1, 20] as a sanity rail
   ```

2. The clamp at 20 is a defense-in-depth rail — even at PRO's 20k/mo quota,
   `5 queries × 20 pages × 30 days = 3,000 calls/month` (15% of quota), still
   safe.

**Verification:**

- `uv run pytest tests/test_jobs_api14_adapter.py -k max_pages -v` — new tests pass
- Read the change with `_max_pages()` invoked from `fetch()` (Task 3) — env-var changes resolve at fetch time, not import time

**Commit message:**

```
feat(adapters): #414 PR2 add JOBS_API14_MAX_PAGES env var resolver

Per-stack pagination ceiling for JobsApi14Adapter. Default 1
(unchanged behavior). Clamped to [1, 20]. Invalid values log
jobsapi_max_pages_invalid and fall back to default.
```

---

### Task 3 — Add nextToken loop in `fetch()`

**Files:**
- `src/findajob/fetchers/adapters/jobs_api14.py` — modify `fetch()` + new helper `_fetch_one_page()`

**Steps:**

1. Refactor the per-query body of `fetch()` so a single call site invokes
   either 1 or N pages. Sketch:

   ```python
   def fetch(self, queries: list[str]) -> list[dict]:
       api_key = self._api_key()
       if not api_key:
           log_event("jobsapi_error", error="No RAPIDAPI_KEY or JOBS_API14_KEY set in .env")
           return []

       date_posted = _date_posted_for_install()
       log_event("jobsapi_date_posted", value=date_posted)

       max_pages = self._max_pages()
       headers = self._headers(api_key)
       rows: list[dict] = []
       last_idx = len(queries) - 1
       for i, query in enumerate(queries):
           token: str | None = None
           pages_fetched = 0
           query_rows = 0
           for _page in range(max_pages):
               params = self._params(query, date_posted)
               if token is not None:
                   params = {"token": token}  # API accepts token-only; other params are no-ops with token set
               data = self._call_with_retry(headers, params, query)
               if data is None:
                   break
               new_rows = self._parse_rows(data, query)
               rows.extend(new_rows)
               query_rows += len(new_rows)
               pages_fetched += 1
               token = (data.get("meta") or {}).get("nextToken")
               if not token:
                   break
               time.sleep(0.6)  # intra-query pagination throttle (same as inter-query)
           log_event("jobsapi_fetched", source="linkedin", query=query, count=query_rows, pages=pages_fetched)
           if i < last_idx:
               time.sleep(0.6)
       return rows
   ```

2. Critical correctness points:
   - Per the §A doc-read finding ("The other URL-parameters can be left out if the token is set, but it will work even when the other parameters are present"), passing only `{"token": token}` is the documented pattern.
   - The intra-query `time.sleep(0.6)` throttle respects the 2 req/sec PRO ceiling. Inter-query sleep stays.
   - `log_event("jobsapi_fetched", ...)` now includes `pages` for observability — `pages=1` is the default-config baseline; `pages>1` confirms multi-page activated.
   - If `_call_with_retry` returns `None` (error / rate-limit-after-retry), the inner loop breaks; outer loop continues to next query. Same failure mode as current behavior.

**Verification:**

- `uv run pytest tests/test_jobs_api14_adapter.py -v` — all existing + new tests pass
- New tests:
  - `test_fetch_single_page_when_max_pages_default()` — fakes a 1-page response, asserts only 1 call made
  - `test_fetch_loops_to_max_pages()` — sets `JOBS_API14_MAX_PAGES=3` via monkeypatch, fakes responses with `nextToken` chained through 3 pages, asserts 3 calls + 30 rows
  - `test_fetch_stops_when_next_token_absent()` — fakes 2-page response where page 2 has no `nextToken`, sets `MAX_PAGES=5`, asserts loop breaks at 2
  - `test_fetch_uses_token_only_on_pagination_calls()` — asserts second call's params dict contains `token` and NOT the original query/location params (per documented behavior)
  - `test_fetch_logs_pages_counter()` — captures `log_event` calls, asserts `pages=N` is included in `jobsapi_fetched`

**Commit message:**

```
feat(adapters): #414 PR2 JobsApi14Adapter LinkedIn nextToken multi-page

Loop fetch() over meta.nextToken up to JOBS_API14_MAX_PAGES per query.
Default 1 = unchanged behavior. Pagination calls send {"token": <value>}
only per the documented API contract. 0.6s intra-query throttle preserves
the 2 req/sec PRO ceiling. log_event jobsapi_fetched now includes pages
counter for observability.
```

---

### Task 4 — `live_test()` honors `_max_pages` for the success bucket?

**Decision:** NO. `live_test()` stays single-page.

**Why:** `live_test()` runs at onboarding + key-rotation time, where the goal is
to verify connectivity + auth + per-query non-zero rows on a budget-conscious
spot check. Multi-page would multiply the live-test cost by the ceiling for no
behavioral signal — connectivity is binary; it's confirmed on page 1.

This task documents the decision in the adapter docstring and adds a unit test
that pins the behavior so a future refactor doesn't accidentally generalize the
multi-page loop into `live_test`.

**Files:**
- `src/findajob/fetchers/adapters/jobs_api14.py` — class docstring sentence

**Steps:**

1. Update class docstring:

   ```python
   class JobsApi14Adapter:
       """LinkedIn ingestion via jobs-api14 (RapidAPI).

       fetch() loops up to JOBS_API14_MAX_PAGES pages per query via the
       opaque nextToken pagination contract; live_test() stays single-page
       to keep onboarding-time spot checks budget-bounded.
       """
   ```

2. Add test `test_live_test_does_not_paginate()` — sets `JOBS_API14_MAX_PAGES=5`,
   provides a fake response with `nextToken` set, asserts exactly N calls (one
   per query, not N*5).

**Commit message:**

```
docs(adapters): #414 PR2 pin live_test single-page contract
```

(Combine with Task 3 if commit churn isn't worth it — they're related changes.
Decide at commit time.)

---

### Task 5 — Documentation surfaces

**Files (per Documentation Impact §3 below):**

- `data/.env.example` — add `JOBS_API14_MAX_PAGES=` (commented, default-1 explanation)
- `docs/setup/api-keys.md` — append section on per-stack pagination tuning
- `docs/setup/install-docker.md` — note in "Updating" section that PRO-tier operators can opt into multi-page
- `CHANGELOG.md` `[Unreleased]` — Added entry + migration note (no migration required, opt-in only)

**Steps:**

1. `data/.env.example`:

   ```
   # Optional: per-stack pagination ceiling for JobsApi14Adapter (LinkedIn endpoint).
   # Default 1 = single-page (10 jobs/query). Each additional page costs 1
   # RapidAPI request. PRO-tier (20,000/month) operators can safely raise to
   # 3-5; free-tier operators should leave at 1.
   # JOBS_API14_MAX_PAGES=1
   ```

2. `docs/setup/api-keys.md` — find the RapidAPI section, add a "Pagination
   tuning" subsection that links to PRO-tier quota math and the env var.

3. `docs/setup/install-docker.md` — under "Updating" or "Operating an existing
   stack", one-paragraph mention that this exists for operators on the
   v0.16-or-later image.

4. `CHANGELOG.md` `[Unreleased]`:

   ```markdown
   ### Added
   - `JOBS_API14_MAX_PAGES` env var — optional per-stack pagination ceiling for
     `JobsApi14Adapter`. Default 1 (unchanged behavior). Each additional page
     is one RapidAPI request; PRO-tier operators (jobs-api14 PRO = 20k/mo) can
     safely set 3-5 for additive yield. Clamped to [1, 20]. (#414)
   ```

   Add migration note:

   ```markdown
   ### Migration required
   - **No action required.** New env var is opt-in; default value matches v0.15
     behavior exactly.
   ```

**Verification:**

- `grep -r "JOBS_API14_MAX_PAGES" docs/ data/.env.example CHANGELOG.md` — all 4 surfaces named above contain the var
- Renders cleanly in `/docs/` viewer (visual check on dev VM)

**Commit message:**

```
docs: #414 PR2 document JOBS_API14_MAX_PAGES across 4 surfaces
```

---

### Task 6 — Whole-feature verification (post-task gate, see §4)

(See §4 below.)

---

## 3. Documentation Impact

| Surface | Change |
|---|---|
| `data/.env.example` | Add `JOBS_API14_MAX_PAGES` commented line + explanation block |
| `docs/setup/api-keys.md` | Add "Pagination tuning" subsection under jobs-api14 |
| `docs/setup/install-docker.md` | One-paragraph note in Updating / Operating section |
| `CHANGELOG.md` | `[Unreleased]` Added entry + Migration-required (no-op) note |
| `CLAUDE.md` | None — pipeline context table doesn't enumerate per-adapter env vars; the var is a tuning knob, not a structural fact |
| `CLAUDE.local.md` | None — no operator-specific configuration changes needed at PR-merge time. Operator may set `JOBS_API14_MAX_PAGES=3` on their own stack post-merge as a separate operational step |
| Spec doc (`docs/superpowers/specs/`) | None — #414 has no spec doc; the issue body + comments are the design record. The PR2 plan doc itself archives into `docs/superpowers/plans/archived/2026-05/` once #414 closes |
| In-code docstrings | `JobsApi14Adapter` class docstring updated (Task 4) |
| `docs/superpowers/plans/2026-05-03-414-shared-key-and-indeed-restore.md` (PR1's plan, archived) | None — PR1 plan stays as historical record; PR2 has its own plan doc |

## 4. Verification gate (whole-feature)

Run BEFORE opening the PR:

1. `uv run pytest -x -q` — full suite green, expected delta is +5 new tests, no regressions
2. `uv run ruff format --check .` — no diffs
3. `uv run ruff check .` — no issues
4. `uv run mypy src/` — no issues
5. Empirical billing probe (Task 1) result documented as comment on #414
6. Manual fetch dry-run with `JOBS_API14_MAX_PAGES=3`:

   - Run `JOBS_API14_MAX_PAGES=3 uv run python -c "from findajob.fetchers.adapters.jobs_api14 import JobsApi14Adapter; print(len(JobsApi14Adapter().fetch(['engineer'])))"` on dev VM
   - Expected: ~30 rows (3 pages × 10 jobs/page) vs ~10 with default
   - Confirms multi-page actually fires end-to-end against the real API
   - **Cost:** 3 RapidAPI requests (assuming probe-confirmed cost model) on dev VM's key
7. Diff review: confirm `live_test()` was not modified (Task 4 contract)

## 5. Self-review checklist

**Spec coverage map** (#414 §B "Multi-page fetch strategy"):

| Spec item | Plan task |
|---|---|
| §B "Stay within free-tier ceiling for the default install" | Task 2 — `_DEFAULT_MAX_PAGES = 1` |
| §B "Per-stack tunable" | Task 2 — `JOBS_API14_MAX_PAGES` env var |
| §B "Honor existing pacing — `time.sleep(0.6)` between queries stays" | Task 3 — inter-query sleep preserved + intra-query sleep added |
| §A "Multi-page billing — confirm empirically" | Task 1 — billing probe |
| §C "near-additive yield, not redundant" | Already empirically confirmed in 4365017323 (97-100% source-exclusivity) |

**Placeholder scan:** no `TBD` / `TODO` / `???` left in plan or in implementation tasks.

**Type/contract consistency:**

- `_max_pages()` returns `int` ≥ 1
- `fetch()` signature unchanged (`list[str]` → `list[dict]`)
- `live_test()` signature + behavior unchanged
- Pagination params dict shape `{"token": str}` matches API contract per §A doc-read
- All adapters call `resolve_rapidapi_key("RAPIDAPI_KEY", "<legacy>")` — JobsApi14 uses `("RAPIDAPI_KEY", "JOBS_API14_KEY")`; unchanged

**Anti-target check** (handoff prompt):

- ✅ Empirical billing probe before designing ceiling (Task 1)
- ✅ Default-off opt-in (Task 2 — `_DEFAULT_MAX_PAGES = 1`)
- ✅ PR1 deploy step is unrelated to PR2 (operator's `active_sources.txt` + `RAPIDAPI_KEY` mirror); PR2 lands on operator stack independently
- ✅ env_migrate.py concern (handoff anti-target #1) was addressed by #416 / PR #419 — pre-PR2 branch tip

**Open question for sign-off:**

- Does Task 1 (billing probe) need to run BEFORE the PR2 branch is cut, or can
  the probe run while Task 2 + 3 implementation is in flight (with the
  understanding that a probe surprise would force re-design)?
  - Recommendation: run the probe first. It's a 5-minute task; the surprise
    case (drop of 1, not 2) materially changes the cost model and the env-var
    framing in Task 5's docs.
