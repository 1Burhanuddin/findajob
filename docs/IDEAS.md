# Feature Ideas / Improvement Backlog

Speculative improvements, new capabilities, and enhancements to consider.
Not bugs — nothing here is broken. Prioritize after open issues are resolved.
Format: `- [ ]` not started, `- [~]` in progress, `- [x]` shipped.

---

## Ingestion

- [x] **Google Form → manual job ingestion pipeline** *(shipped 2026-04-08)*
  Form: [see CLAUDE.local.md]
  Responses sheet ID stored in `config/form_responses_sheet_id.txt`.
  `scripts/ingest_form.py` polls every 30 min via `com.OWNER.jobpipeline.form-ingest` launchd agent.
  New jobs injected as `source=manual_form`, `stage=scored`, `relevance_score=8`.
  Optional "Generate company folder immediately" checkbox triggers `prep_application.py`.
  Fields: Job URL, Company, Title, Location, Remote Status, Notes, Known Contacts, Generate Folder.

---

## Scoring / Triage

- [ ] **Scoring accuracy analysis — false negative audit**
  ~2,400 scored jobs are sitting unreviewed below the Dashboard threshold. Unknown how many
  are false negatives (good jobs scored too low). Analyze: score distribution by source,
  target-company jobs scored 1-6, title-keyword hits in low-score buckets. Requires JD quality
  fix first (spec: `docs/superpowers/specs/2026-04-10-jd-quality-design.md`).

- [x] **Feedback loop — systematic learning from rejections** *(shipped 2026-04-11)*
  `scripts/analyze_feedback.py` reads feedback_log + jobs to produce: rejection breakdown,
  false positive analysis (score 8+ rejected), title keyword signals (applied vs rejected),
  company repeat patterns, source FP rates, and actionable prefilter/search suggestions.
  `notify.py feedback-review` updated to surface key stats from the analysis.
  First run findings: 80.6% of rejections are score 8+ (false positives); Greenhouse has 73%
  FP rate on score-7+ jobs; "engineer" title without "operations/data center" context is the
  dominant FP signal. Prefilter updated with quality/process/systems-dev engineer patterns.
  Search queries updated: removed "forward deployed engineer", "data center engineer"; added
  "data center technician manager", "datacenter site manager", "AI infrastructure operations".

## Data Sources

- [ ] **Evaluate alternative job APIs**
  Currently using jobs-api14 (RapidAPI) for LinkedIn + Indeed. First API found, not necessarily
  best. Evaluate: coverage (are we missing jobs that appear on other boards?), JD completeness
  (do other APIs return full JDs without truncation?), cost, rate limits. Candidates: LinkedIn
  official API (requires partnership), Adzuna, The Muse, Remotive, company career pages direct.

---

## Prep / Output

---

## Observability

*(nothing yet)*

---

## Shipped

*(move items here with ship date)*
