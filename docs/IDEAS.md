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

*(nothing yet)*

---

## Prep / Output

*(nothing yet)*

---

## Observability

*(nothing yet)*

---

## Shipped

*(move items here with ship date)*
