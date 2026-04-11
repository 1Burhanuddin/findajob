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

- [ ] **Feedback loop — systematic learning from rejections**
  `feedback_log` captures every Dashboard/Review rejection with reason and JD excerpt, but
  this data doesn't feed back into scoring. Ideas: periodic `reject_reason` clustering to
  tune prefilter patterns; score calibration (if user consistently rejects score-7 jobs with
  certain title patterns, auto-demote); track accept/reject ratio by score bucket over time.

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
