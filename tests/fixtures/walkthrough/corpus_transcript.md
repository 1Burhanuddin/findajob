# Walkthrough Replay Corpus — Avery Chen (fictional persona)

Captured 2026-05-23 via `scripts/walkthrough_harness.py --interactive-recapture`
against a freshly-reset `findajob-clean`. Skip-and-patched 2026-05-24 for #833
(auto-emit Phase 5 groups — collapsed turns 42–45 into turn 42, removed `next` gates). The persona is fictional — no real
candidate ever submitted any of this content to the pipeline.

The persona is intentionally **non-tech** (a clinical pharmacist transitioning
to clinical informatics) so the corpus exercises the prompt's field-agnostic
claim under stress — if a prompt revision narrows the question shape toward
tech-only assumptions, replay against this corpus will surface mismatches
loudly.

## Re-baseline workflow

When the onboarding prompt revisions noticeably shift question shape, replay
against this corpus will produce `answer_match_turn_N` REVIEW findings on the
drifted turns. Two paths to rebaseline:

**Primary — fresh interactive recapture** (used 2026-05-23 for this corpus):

1. Reset `findajob-clean` per `docs/personal/findajob-clean-reset.md`.
2. `uv run python scripts/walkthrough_harness.py --base-url http://docker.lan:8096 \
   --output-dir /tmp/walkthrough-recapture-$(date +%Y-%m-%d) \
   --interactive-recapture --browser-channel chrome --max-turns 60 \
   --cost-ceiling-usd 6.0` — runs the harness in interactive mode where each
   assistant turn is written to `<output-dir>/interactive/assistant_NN.txt`
   and the harness blocks waiting for `<output-dir>/interactive/answer_NN.txt`.
3. Operator (or maintainer driving the rebaseline) composes Avery-voice
   answers turn-by-turn against the live prompt; writes each `answer_NN.txt`.
4. When the harness finalizes, reformat its output to corpus shape:
   - Strip the leading `ASSISTANT\n\n` label each chat bubble's `inner_text()`
     captures.
   - Convert sequential `## Turn N — ROLE` numbering into paired numbering
     (`## Turn 1 — ASSISTANT` then `## Turn 1 — USER`, etc.) — `load_corpus()`
     indexes by turn_num, so paired numbering is required for replay.
   - Append a synthetic `next` USER on the final paired turn for shape
     symmetry (the harness breaks on finalize-block-populated before getting
     the last user reply).
5. Prepend this header. Save back over `tests/fixtures/walkthrough/corpus_transcript.md`.
6. Verify: `uv run python scripts/walkthrough_replay_corpus.py <path> --print-summary`
   should report `Non-empty user turns: N/N` and at least one phase anchor.
   Then reset findajob-clean again and re-run the harness (without
   `--interactive-recapture`) to confirm zero `answer_match_turn_N` REVIEWs.

**Secondary — skip-and-patch** (cheaper for minor drift only):

1. Run the harness against the current corpus to produce `transcript.md`.
2. The drifted turns will have `Skip — using prior context` as the user
   reply.
3. Hand-edit those lines into substantive answers in Avery Chen's voice.
4. Save back over this file.

Do NOT promote a real operator's walkthrough transcript over this file —
those contain operator PII and should never enter the repo.

---

## Turn 1 — ASSISTANT


Hi — I'm glad you're here. I'm going to help you set up findajob, a tool that triages job postings for you every day so you only look at the ones worth looking at. To get there I need to learn who you are, what you're looking for, and how you talk about your own work. We'll go through five phases together. Plan for about 60–90 minutes end to end — some people finish faster, some take longer. You can close the tab and come back later — your progress is saved automatically.

A few ground rules before we start:

This is a conversation. Push back on any question you find confusing, tell me if I'm on the wrong track, or ask me to brainstorm with you on anything you're unsure about.
You can ask "why are you asking this?" at any time and I'll explain.
If you want to revisit an earlier answer later, just say so — I'll update it.
Toward the end I'll emit your config in four groups (identity, targeting, filters, writing voice), all in one go. If something in a group looks wrong, type redo {a|b|c|d} any time before you click Finalize.
If something I produce isn't right at any point, just say "redo" and tell me what to change.

Before we dive into your background, I want to walk you through how findajob finds jobs in the first place — there are four different sources, and we'll pick the right mix for you later in the interview.

Job-Source Strategy (read this carefully)

This pipeline can find jobs from up to four different places. Each has different costs, what kinds of jobs it tends to find, and how much setup it needs. We'll come back to this in Phase 3 to pick what fits you — for now, just learn what they are.

A paid job-search service The pipeline asks a service called RapidAPI to find jobs that match your search terms (it pulls listings from sites like LinkedIn and Indeed). RapidAPI has a free tier that usually covers ~150 searches per month; paid plans are typically $5–20/month for steady use. You sign up at rapidapi.com and paste a key into the pipeline. If you didn't enter one in Step 1, you can skip this source — the pipeline just won't use it.
Best for: jobs that get posted on LinkedIn — corporate, tech, white-collar, professional services.

Worst for: fields where most jobs aren't on LinkedIn — skilled trades, local or regional employers, social services, some healthcare niches.

Company career-page feeds (free) Many large companies publish their open jobs in a feed format the pipeline can read directly. You give it a list of companies you want to watch, and it checks them every day. No signup, no cost.

Best for: anyone with specific target employers in mind.

Worst for: discovering companies you don't already know — you only see jobs from companies you've named.

Gmail job alerts (free, 15–30 min setup) LinkedIn and Indeed both let you save a search and have them email you matches. The pipeline reads those alert emails from your Gmail inbox and pulls the jobs out. You turn on the alerts on LinkedIn or Indeed, then connect the pipeline to your Gmail.

Best for: people who already use saved searches and want a wider net than just named companies.

Worst for: anyone who'd rather not connect their Gmail.

Manual (free, you-driven) You see a job somewhere — LinkedIn, a company website, a friend forwards it — and paste the link into the pipeline yourself. There's also a "speculative" option for cold-outreaching companies that aren't posting a matching role but you want to approach anyway. No setup at all.

Best for: highly-targeted job seekers who'd rather have 5 hand-picked jobs than 200 to triage.
Worst for: anyone wanting volume without effort.

You can pick any combination. Common mixes: company feeds + Gmail alerts (both free, decent recall); paid service + manual (volume plus precision); manual only (zero setup). We'll discuss what makes sense for you once we know your target roles.

Any questions about how those sources work before we move on? If not, let's get started — I'll ask you to paste your resume next.

## Turn 1 — USER


No questions on the mechanics — that's a clear walkthrough. A quick read of what I think fits my search: Gmail alerts and company career-page feeds both sound like they'll do real work for me. I already use Indeed alerts for clinical pharmacy informatics roles, so Gmail is an easy add. And the company-feed option — I have a named list of academic medical centers and integrated systems I'm targeting, which sounds like exactly what that source is for. The paid service I'd lean away from. Healthcare informatics roles don't concentrate on LinkedIn the way corporate or tech roles do, and I suspect I'd pay for coverage I already get from the other two. Happy to confirm that once we get to the actual source-selection step. Ready to move on.

## Turn 2 — ASSISTANT


That's a useful preview — clinical pharmacy informatics, academic medical centers and integrated systems, already using Indeed alerts. That context will shape a lot of what we build. We'll confirm the source selection formally when we get to that step.

Let's move to Phase 2.

Paste your resume into the chat — copy it from the source document (Word, Google Docs, PDF, LinkedIn export, plain text — whatever you've got) and drop it in here. If you have performance reviews, 360s, or self-assessments where someone has described your work in their own words, paste those too in follow-up messages. More context here means fewer questions later.

If your resume is in a PDF and you can only get the text out as a messy block, paste what you can — I'll work with it. The shape doesn't have to be pretty. If you've got nothing in document form, type out your work history: employer, title, dates, and a few lines on what you did at each job.

## Turn 2 — USER


Avery Chen, Pharm.D., BCPS — Minneapolis, MN
avery.chen.pharmd@example.com  •  555-0142  •  linkedin.com/in/avery-chen-pharmd-example

Summary
Hospital clinical pharmacist with eight years of acute-care practice and a residency-trained background in medication safety. Recent focus on the seam between pharmacy practice and the EHR — built order-set governance and CPOE rule logic for a 600-bed academic medical center, partnered with informatics on alert-fatigue reduction projects. Looking to move full-time into clinical informatics where pharmacy expertise translates to system design rather than dispensing throughput.

Experience

Senior Clinical Pharmacist — Lakefront Medical Center, Minneapolis MN — 2022–present
- Lead pharmacist for the inpatient antimicrobial stewardship program; reduced broad-spectrum DOT (days of therapy) by 14% across two service lines through provider education and order-set redesign.
- Co-chair of the Pharmacy & Therapeutics order-set subcommittee; rewrote 40+ legacy order sets to incorporate weight-based dosing and renal-function logic in CPOE.
- Project lead on the 2024 alert-fatigue reduction initiative — partnered with informatics analysts to retire 1,200 low-yield interruptive alerts; clinician override rate fell from 91% to 67% on the remaining set.
- Precept PGY-1 residents on a clinical informatics elective rotation (2 residents/year).

Clinical Pharmacist — Lakefront Medical Center, Minneapolis MN — 2018–2022
- Front-line acute-care coverage across general medicine, ICU, and oncology service lines.
- Served on the medication-error review committee; co-authored a workflow change that eliminated a class of pediatric heparin dosing errors traced to a unit-conversion ambiguity.

PGY-1 Pharmacy Practice Resident — Saint Aldhelm Hospital, Madison WI — 2017–2018
- Standard ASHP-accredited residency with required and elective rotations across acute care, ambulatory care, and informatics.

Education
Doctor of Pharmacy (Pharm.D.) — University of Minnesota — 2017
B.S. Biochemistry — Carleton College — 2013

Credentials
Board Certified Pharmacotherapy Specialist (BCPS) — 2020
Active pharmacist license in Minnesota and Wisconsin
Epic Willow Inpatient — proficiency self-attested; no formal Epic certification yet

## Turn 3 — ASSISTANT


Here's what I see:

Avery is a hospital clinical pharmacist with eight years of acute-care practice at a single institution — Lakefront Medical Center in Minneapolis — following an ASHP-accredited residency at Saint Aldhelm in Madison. The arc of the work is clearly transitional: the early years were front-line clinical coverage across general medicine, ICU, and oncology, and the recent years have moved steadily toward the seam between pharmacy and the EHR — order-set governance, CPOE rule logic, and a meaningful alert-fatigue reduction project that retired 1,200 low-yield alerts and moved the clinician override rate from 91% to 67%. What stood out in the language: Avery doesn't describe this as "getting into informatics" but as work where pharmacy expertise "translates to system design rather than dispensing throughput" — that framing is precise and will be useful later.

Before I continue — does that summary feel accurate? Tell me what I got right, what I got wrong, and anything important I missed.

## Turn 3 — USER


That's accurate, with one addition I want to make sure carries through: please preserve the Epic Willow line on my resume — self-attested proficiency, no formal certification yet. The reason matters. I haven't done formal Epic certification because my employer wouldn't fund it without an informatics title, but I've been working in Epic for years and would take certification on day one of an informatics role. Most informatics jobs require Epic cert within 12 months anyway, and I want recruiters to read this as "certification-ready," not "Epic-naive." That distinction is load-bearing.

Two paste-backs from my 2024 annual review that might be useful before we move on, if you want them in the picture:

From my director: "Avery is the person other pharmacists go to when something is unclear in CPOE. She bridges the gap between what bedside clinicians need and what the EHR enforces, and she does it without making either side feel talked down to. Her work on the alert-fatigue project this year was the most important non-clinical contribution from the pharmacy department. She has earned the trust of informatics and physician colleagues to a degree that's unusual for a staff pharmacist."

From a peer (an informatics analyst on the EHR team): "Avery doesn't speak to me like I'm an outsider — she explains the clinical reasoning behind every change request, which makes my own work better. She's the rare clinician who actually wants to understand why the system behaves the way it does, and she's patient about it. I would hire her into my team if she had the title, no hesitation."

## Turn 4 — ASSISTANT


Both of those are noted and carry real signal — I'll make sure they inform how we write the "What Makes You Unusual" and "What to Emphasize" sections of your profile. The peer quote in particular ("I would hire her into my team if she had the title, no hesitation") is a strong framing device.

On the Epic Willow line: understood, and I'll preserve it exactly as you've described it — self-attested proficiency, no formal certification, with the context that certification-readiness is the intended read. That distinction will appear in the resume as written and in the "Employer Formatting Rules" section of your profile so the resume tailor doesn't accidentally soften or drop it.

Let's move to Phase 3.

In the next set of questions, frame what you do in terms of impact — outcomes, scale, numbers, people served, decisions influenced — rather than activities or responsibilities. "Managed a team" is an activity. "Grew a team from 5 to 20 while cutting time-to-hire in half" is impact. If you catch yourself listing duties, pause and re-frame. If you're unsure, tell me what you did and I'll help you translate it.

3a. Target role

In one sentence, what role are you targeting? Think specific title plus level plus any qualifier that matters to you.

## Turn 4 — USER


Primary target: Pharmacy Informaticist or Clinical Informatics Pharmacist at senior IC or first-line lead level — those titles vary by health system but the work is the same.

A few qualifiers I'd want carried through, since the one-sentence version flattens what I actually care about: I'm open to broader Clinical Informatics Specialist titles when the role is pharmacy-adjacent and the clinical license stays load-bearing. I'm not interested in pure application-analyst roles where the Pharm.D. is decorative. Not chasing director-level yet — I want to do the work, not manage people doing it.

## Turn 5 — ASSISTANT


That's specific enough to build a clean filter from. Let me mirror it back:

"Pharmacy Informaticist or Clinical Informatics Pharmacist at senior IC or first-line lead level at a health system; open to Clinical Informatics Specialist titles when the role is pharmacy-adjacent and the Pharm.D. is genuinely load-bearing; not interested in pure application-analyst roles or director-level people management."

Does that capture it accurately before we move on?

## Turn 5 — USER


Yes, that's exactly it. Move on.

## Turn 6 — ASSISTANT


3b. Geography and remote preference

Where do you live, and what are your location constraints? Are you open to remote, hybrid, on-site, or relocation?

## Turn 6 — USER


Based in Minneapolis, MN. Open to all three modes, with rank-ordered preferences: remote (US) first, hybrid in the Twin Cities second, and willing to relocate within the Upper Midwest for the right informatics role. By "right" I mean a clinical informatics role at one of the academic medical centers or large integrated systems on my target list — not just any informatics title that happens to be open in Iowa.

## Turn 7 — ASSISTANT


Got it. I'm capturing three location values from that:

Remote (US-wide, first preference)
Minneapolis, MN (hybrid, second preference)
United States (relocation within Upper Midwest for right-fit roles)

I'll use those when we build the location config later. Moving on.

3c. Target employers

List 5–15 employers you'd genuinely take a job at today. These can be health systems, academic medical centers, integrated systems — whatever kind of employer fits your field.

## Turn 7 — USER


Here's my target list, grouped because the rationale differs across them:

Academic medical centers in the Upper Midwest:
- Mayo Clinic
- M Health Fairview
- Allina Health
- Hennepin Healthcare
- Essentia Health
- Marshfield Clinic
- UW Health

Large regional integrated systems (also Upper Midwest, but more on the integrated-delivery side):
- Sanford Health
- Avera Health
- Children's Minnesota

Also genuinely open to:
- VA hospitals (federal — strong informatics shops at many sites)
- IHS facilities
- Health-system-owned ACOs

The common thread is Epic-shop systems with active clinical informatics programs where a Pharm.D. is doing real EHR work, not staff coverage. Happy to add more if you think the list needs to be broader; this is what I'd say yes to today without much arm-twisting.

## Turn 8 — ASSISTANT


Good list — 10 named employers plus two federal/ACO categories. Let me run the tier-split before we move on.

For each employer, tell me which tier fits:

Tier 1 — would take a role there today, near any role that matches your target.
Tier 2 — strong interest, but you'd be choosier about the specific role.
Tier 3 — opportunistic only — you'd consider it if the role were exceptional.

Want to walk through them one at a time, or call them out by name? You can also just say "Tier 1 is everything" or give me a split — whatever's fastest.

## Turn 8 — USER


Quick split, not one at a time:

Tier 1 (would take today for the right informatics role):
- Mayo Clinic
- M Health Fairview
- UW Health
- Allina Health
- Children's Minnesota

Tier 2 (strong interest, choosier on role specifics):
- Hennepin Healthcare
- Essentia Health
- Sanford Health
- Avera Health
- Marshfield Clinic

Tier 3 (opportunistic only — would need the role to be unusually well-fit):
- VA hospitals
- IHS facilities
- Health-system-owned ACOs

The Tier 1 / Tier 2 split is mostly about institutional informatics-program maturity and how visible their Epic/CPOE work is from the outside. Tier 3 is opportunistic because the federal and ACO worlds have different career arcs that I'd need to actively want, not just accept.

## Turn 9 — ASSISTANT


That's a clean split and the reasoning tracks. Let me confirm the tiered list before we move on:

Tier 1: Mayo Clinic, M Health Fairview, UW Health, Allina Health, Children's Minnesota

Tier 2: Hennepin Healthcare, Essentia Health, Sanford Health, Avera Health, Marshfield Clinic

Tier 3: VA hospitals, IHS facilities, Health-system-owned ACOs

Now, for the sector-reference file — looking at your Tier 1 list, I'd like you to group them into 2–4 categories by why the role's background should emphasize each kind of employer. One sentence per category explaining what makes that kind of employer distinctive. For example: what does Mayo Clinic call for that's different from Children's Minnesota? Or do they all call for the same framing?

You don't have to match my suggested groupings — use whatever categories feel right to you.

## Turn 9 — USER


Three categories work for the Tier 1 list:

1. Destination academic medical centers with strong research arms — Mayo Clinic, UW Health. The framing should lead with evidence-based-practice rigor, ASHP-accredited residency lineage, and the alert-fatigue work as a quantitative informatics contribution, since these systems hire toward research-informed clinical informatics roles.

2. University-affiliated integrated delivery networks — M Health Fairview. Framing should emphasize cross-site standardization, EHR governance at scale, and the P&T order-set subcommittee co-chair work, since these systems care about multi-hospital harmonization more than single-institution depth.

3. Large nonprofit integrated systems and specialty pediatric — Allina Health, Children's Minnesota. Framing should foreground operational pharmacy informatics, medication-safety committee experience, and the pediatric heparin-dosing workflow change, since these systems hire toward applied safety-and-throughput work rather than research framing. (Children's is the outlier — for them the pediatric-medication-safety story is the lead, not a side note.)

## Turn 10 — ASSISTANT


That's a well-reasoned split and the per-category framing is exactly what the sector-reference file needs. I'll carry those three categories through with the reasoning you gave, including the Children's Minnesota callout.

Let me confirm the groupings before we move on:

Category 1 — Destination academic medical centers with research arms: Mayo Clinic, UW Health. Lead with evidence-based-practice rigor, ASHP residency lineage, alert-fatigue work as quantitative informatics contribution.

Category 2 — University-affiliated integrated delivery networks: M Health Fairview. Lead with cross-site standardization, EHR governance at scale, P&T order-set subcommittee co-chair work.

Category 3 — Large nonprofit integrated systems and specialty pediatric: Allina Health, Children's Minnesota. Lead with operational pharmacy informatics, medication-safety committee experience, pediatric heparin-dosing workflow change. For Children's specifically, the pediatric medication-safety story leads.

Does that look right?

## Turn 10 — USER


Yes, exactly. Move on.

## Turn 11 — ASSISTANT


3d. Career-history gaps

Are there any gaps in your resume I should know about — a break, a sabbatical, something ongoing that isn't on the document?

## Turn 11 — USER


No employment gaps — straight through since residency. The one thing recruiters sometimes pattern-match on with a pharmacy-to-informatics pivot is "are you really sure you don't want to stay clinical?" — and I am sure. I've been doing the informatics-adjacent work without the title for two years; this isn't a pivot I'm trying on, it's a pivot I've already half-completed and need to formalize. If you can frame that proactively in the materials, recruiters won't have to dig for it.

## Turn 12 — ASSISTANT


Noted — and that's a strong framing. The story isn't "pharmacist wants to change careers," it's "pharmacist who has been doing informatics work without the title for two years and is formalizing what's already true." I'll make sure that reads clearly in the profile's career summary and "What to Emphasize" sections so recruiters don't have to reconstruct it themselves.

3e. Résumé formatting rules per employer

Do any of your past employers have formatting quirks on your resume? For example: a role that was a contract and you want it marked that way, a company that was acquired and you want both names shown, or a program you founded and want called out.

## Turn 12 — USER


No formatting quirks. Single employer for the eight working years (Lakefront Medical Center) plus the residency at Saint Aldhelm — both kept their names, no acquisitions, no contract roles, no founded programs to call out. The only thing I'd flag — already covered — is the Epic Willow self-attested-proficiency framing, which is content not formatting.

## Turn 13 — ASSISTANT


Clean — no formatting rules needed, and the Epic Willow framing is already captured. Moving on.

3f. Voice samples (optional — but strongly recommended)

The pipeline writes cover letters and recruiter outreach drafts in your voice. To do that well, it needs a sample of how you actually write — not your resume bullets, which are compressed business prose, but real long-form first-person writing where your natural voice comes through.

Paste 3,000–8,000 words of your own long-form prose. Good sources:

A blog post export, Substack archive, or personal essays
Long emails to a colleague where you explained something you cared about
Application essays you're proud of
A long-form Medium / LinkedIn / Reddit post you wrote (your unaided writing, not LLM-edited)

Avoid: resume bullets, code, lists, tweets, text messages, anything an LLM helped you write. Voice signal lives in the flow between sentences, so prose-form is what matters.

Don't worry about cleaning up the formatting — I'll handle that. Don't worry about scrubbing personal details — the pipeline auto-generalizes those before writing the file. Just paste what you have.

If you don't have anything that fits, say "skip" and we'll move on. The pipeline falls back to using your resume bullets for voice calibration; the cover letters will be fine but a touch more generic.

If you're not sure whether something counts, paste it and I'll tell you whether it'll work.

## Turn 13 — USER


Skip. I'd rather have cover letters drafted from the resume and the framing notes than risk over-fitting to a small writing sample — I don't have a blog or Substack, and the personal essays I do have are old enough that the voice has moved on. If the cover-letter drafts don't sound right once I see a few, we can revisit and I'll dig something up. For now, the resume bullets plus the "thoughtful clinician, not MBA" voice direction should give the pipeline enough to work with.

## Turn 14 — ASSISTANT


Understood — skipping voice samples, falling back to resume-based calibration. I'll carry the "thoughtful clinician, not MBA" voice direction into the profile's "What to Emphasize" section so the cover-letter writer has that framing explicitly, not just implicitly.

3g. Source selection

Based on what you've told me — senior pharmacy informaticist or clinical informatics pharmacist roles at academic medical centers and large integrated health systems in the Upper Midwest — here's my read on sources:

Your preview at the start was well-reasoned and I agree with it. Clinical pharmacy informatics roles don't concentrate on LinkedIn the way corporate and tech roles do; your Indeed alerts are already doing real work; and you have a named list of target employers that maps well to the company-feeds source. The paid RapidAPI service would likely give you thin coverage and cost you free-tier calls you could spend elsewhere.

So I'd recommend b and c — company career-page feeds and Gmail alerts:

b. Company career-page feeds — your Tier 1 and Tier 2 named systems (Mayo, M Health Fairview, UW Health, Allina, Children's Minnesota, Hennepin, Essentia, Sanford, Avera, Marshfield) are large enough that most run Greenhouse, Lever, or Ashby career pages the pipeline can read directly. Daily checking at no cost.
c. Gmail alerts — your existing Indeed alerts for clinical pharmacy informatics are exactly the right seed. Connecting Gmail gives the pipeline a wider net beyond just named employers.

Pick which sources you want active (Manual is always available — no selection needed for that one):

a. Paid job-search service (RapidAPI) b. Company career-page feeds c. Gmail job alerts

Reply with the letters you want, or "none" for Manual only.

## Turn 14 — USER


b, c

## Turn 15 — ASSISTANT


Confirmed — company career-page feeds and Gmail alerts, plus Manual always available. No RapidAPI, so no paid-service config needed.

Since you picked c (Gmail alerts), I'll build a set of search queries that you'll use to set up your LinkedIn and Indeed saved searches. Since you picked b (company career-page feeds), I'll build feed URLs for your named target employers. Both of those come out in Phase 5.

3i. Reject reasons

Quick framing before I ask: the labels you pick here become the dropdown options on your rejection cell — every time you pass on a posting, you pick one. But they also feed back into the system: when you keep rejecting postings for the same reason, the pipeline mines those rejections for title patterns and starts filtering that flavor of posting before it ever reaches your dashboard.

That feedback loop is why the labels need to fit your actual mental model. If you keep seeing application-analyst roles and reject them as "Skills Mismatch" because nothing better fits, the prefilter learns nothing. But if your dropdown had "Pure App Analyst — Pharm.D. Decorative," the prefilter would start recognizing those titles and filtering them out automatically.

When you scan a posting and decide "no, this isn't for me," what phrases come to mind? Think about the last 5–10 postings you've passed on — what made each one wrong?

Here are some prompts from the healthcare/clinical informatics bucket to get you started if you stall:

a. Caseload Too High b. Population Mismatch c. Credential Gap d. Pay Band Wrong e. Wrong Setting (e.g. inpatient vs. outpatient) f. Admin Track (vs. clinical / direct service) g. Wrong Niche

Don't feel limited to these — your own language is better than mine here.

## Turn 15 — USER


Thinking about the last several postings I've scanned and passed on, here's the language that actually goes through my head:

- Staff Pharmacist — No Informatics Scope (bedside clinical only, even when titled "Senior")
- Pure App Analyst — Pharm.D. Decorative (Epic/IT title where the clinical license is window dressing)
- PBM — Wrong Career (UnitedHealthcare / CVS / Caremark / Express Scripts / Optum)
- Pharma Industry — Wrong Direction (MSL, Medical Affairs, Pharmacovigilance)
- Retail Pharmacy — Wrong Setting (CVS, Walgreens, Rite Aid)
- Director Track — Wrong Level (people-management, not the work I want to do yet)
- Outpatient/Ambulatory Only (my experience is acute-inpatient; ambulatory shop work is a different skill set)
- Geographic Mismatch (outside Upper Midwest, non-remote, no relocation fit)
- Informatics-on-the-Side Reframing ("clinical pharmacist who also does informatics" — that's my current job, not the pivot)

The "Informatics-on-the-Side Reframing" one is the most important to capture even though it'll show up rarely — it's the trap I'm explicitly trying to escape, and if I don't have a label for it I'll waste cycles re-evaluating the same posting shape every time it appears.

Skip the generic ones from your starter list (Caseload Too High, Population Mismatch, etc.) — those don't fit my decision-making. Mine is mostly about title-shape and employer-type rather than role-internal mechanics.

## Turn 16 — ASSISTANT


That's a sharp list and the reasoning is clear. Now the second question:

Of those nine labels, which ones would mean the system should have caught it before showing it to you — i.e. the title alone is the giveaway? For example, "Staff Pharmacist — No Informatics Scope" might be catchable from the title alone ("Staff Pharmacist," "Senior Clinical Pharmacist" with no informatics qualifier), whereas "Informatics-on-the-Side Reframing" might require reading the job description to spot.

Go through the nine and tell me which ones are title signals versus JD-read signals.

## Turn 16 — USER


Title-signal (catchable from title alone — prefilter these out):

- Staff Pharmacist — No Informatics Scope ("Staff Pharmacist," "Senior Staff Pharmacist," "Pharmacy Manager (Retail)" — any pharmacist title without an informatics qualifier)
- PBM — Wrong Career (employer name alone is the tell: UnitedHealthcare, CVS Health, Caremark, Express Scripts, Optum, Optum Rx)
- Pharma Industry — Wrong Direction (titles: Medical Science Liaison, Medical Affairs, Pharmacovigilance, Drug Safety Specialist — all tell you it's pharma)
- Retail Pharmacy — Wrong Setting (employer alone: CVS, Walgreens, Rite Aid; also titles like "Community Pharmacist," "Retail Pharmacist")
- Director Track — Wrong Level ("Director of Pharmacy," "VP," "Chief Pharmacy Officer" — title alone tells you)

JD-read signals (need to read the description):

- Pure App Analyst — Pharm.D. Decorative (title says "Application Analyst" or "Epic Willow Analyst," but you have to read whether the clinical license is required vs preferred vs irrelevant)
- Outpatient/Ambulatory Only (titles are usually generic — "Clinical Pharmacist Specialist" — and you only know from the setting line)
- Informatics-on-the-Side Reframing (title looks like a legit informatics role; only the JD reveals that the day-to-day is 80% staff coverage)
- Geographic Mismatch (some postings hide the location until you click in; harder to title-filter for)

Practically speaking the title-signal set is where the prefilter does its best work — and the five I called out cover most of the noise I'd see in a daily triage. The JD-read ones are slower-loop signals where I'd still need to make the call myself.

## Turn 17 — ASSISTANT


That's a clean split and exactly the level of precision the feedback loop needs. Let me confirm the full reject-reasons list before we move on:

All labels (dropdown order — most common first): 1. Staff Pharmacist — No Informatics Scope 2. Pure App Analyst — Pharm.D. Decorative 3. PBM — Wrong Career 4. Pharma Industry — Wrong Direction 5. Retail Pharmacy — Wrong Setting 6. Director Track — Wrong Level 7. Outpatient/Ambulatory Only 8. Geographic Mismatch 9. Informatics-on-the-Side Reframing 10. Already Applied 11. Stale/Closed 12. Company passed 13. Other

Title-signal subset (prefilter mines these): - Staff Pharmacist — No Informatics Scope - PBM — Wrong Career - Pharma Industry — Wrong Direction - Retail Pharmacy — Wrong Setting - Director Track — Wrong Level

Does that look right? If so, we move to Phase 4.

## Turn 17 — USER


Looks right. Move on.

## Turn 18 — ASSISTANT


Phase 4 — Translation and review

Quick framing for this phase. We'll work through your exclusions one category at a time. For each, I'll show you a short list of example job titles I'd filter out, and you'll tell me one of three things:

Yes — filter all of those titles, that category is right.
Some are OK — and you'll point at which titles should slip through; I'll narrow the rule until only the right ones get filtered.
Skip — drop this category entirely; don't filter any of those titles.

I'm doing the pattern-matching work behind the scenes; your job is just to react to example titles in plain English.

Pass A — Exclusions

Based on your background and reject reasons, here are the categories I'd suggest filtering out. Pick the ones that apply, drop any that don't, and add anything I missed:

a. Staff pharmacist titles without an informatics qualifier b. PBM employer titles (UnitedHealthcare, CVS Health, Optum, Express Scripts, Caremark) c. Pharma industry titles (MSL, Medical Affairs, Pharmacovigilance, Drug Safety) d. Retail pharmacy titles and employers (CVS, Walgreens, Rite Aid, community pharmacist) e. Director-and-above pharmacy titles (Director, VP, Chief Pharmacy Officer) f. Pure application analyst titles where the clinical license appears irrelevant g. Informatics-adjacent but primarily staff-coverage roles h. Ambulatory/outpatient-only clinical pharmacist roles i. Spam and alert-management noise (job alert emails, talent network invites)

Reply with the letters you want to keep, drop any that don't apply, and name any categories I missed.

## Turn 18 — USER


Keep all nine — a through i — they all map to my decision-making.

One I'd add as a tenth: locum tenens / per-diem / contract pharmacist roles. They surface on Indeed alerts because they keyword-match "pharmacist" + "remote-capable," but the contract structure isn't what I'm looking for. Call it (j) — "Locum/Per-Diem/Contract Pharmacist."

And a sub-note on (g) — "informatics-adjacent but primarily staff-coverage" is essentially the "Informatics-on-the-Side Reframing" reject reason I called out earlier. Same thing under a different name, both fine.

## Turn 19 — ASSISTANT


Good — all nine plus locum/per-diem/contract as (j). And noted on (g) — the prefilter and the reject-reason label are two faces of the same pattern; I'll make sure they're consistent.

Let's work through them one at a time.

Category a — Staff pharmacist titles without an informatics qualifier

I'd filter out titles like:

Staff Pharmacist
Senior Staff Pharmacist
Clinical Pharmacist
Senior Clinical Pharmacist
Pharmacy Manager
Inpatient Pharmacist

Borderline ones I'm currently catching too — tell me if these should slip through:

Clinical Pharmacy Specialist
Pharmacist Clinician

Yes (filter all of these) / Some are OK (tell me which to let through) / Skip (drop this category)?

## Turn 19 — USER


Some are OK — let the borderlines split:

Filter all six in the main list — Staff Pharmacist, Senior Staff Pharmacist, Clinical Pharmacist, Senior Clinical Pharmacist, Pharmacy Manager, Inpatient Pharmacist — those are all my current-job shape without the informatics qualifier.

On the borderlines:

- "Clinical Pharmacy Specialist" — let it through. At academic medical centers this title often carries an informatics or specialty-track scope; I'd rather scan the JD than miss the ones that fit.
- "Pharmacist Clinician" — filter. This is usually an advanced-practice direct-patient-care title; rarely informatics-flavored.

The rule that captures the whole category: filter any "Pharmacist," "Clinical Pharmacist," "Staff Pharmacist," or "Pharmacy Manager" title that doesn't have one of these qualifiers in it — Informatics, Clinical Informatics, CMIO, Order Set, CPOE, EHR, or Decision Support. That phrasing catches what I'd want and lets the right edges through.

## Turn 20 — ASSISTANT


Got it — filtering the six main titles plus "Pharmacist Clinician," letting "Clinical Pharmacy Specialist" slip through. The rule shape is: pharmacist/clinical pharmacist/staff pharmacist/pharmacy manager/inpatient pharmacist titles that lack an informatics qualifier. I'll build that internally.

Category a is locked in. Moving on.

Category b — PBM employer titles

I'd filter out titles like:

Clinical Pharmacist — UnitedHealthcare
Pharmacy Care Advocate — Optum Rx
Clinical Account Manager — Express Scripts
Prior Authorization Pharmacist — Caremark
Pharmacy Benefit Specialist — CVS Health

Borderline ones I'm currently catching too — tell me if these should slip through:

Clinical Informatics Pharmacist — Optum
Pharmacy Quality Analyst — UnitedHealthcare

Yes / Some are OK / Skip?

## Turn 20 — USER


Yes — filter all five plus both borderlines. PBM is a different career, full stop. Even "Clinical Informatics Pharmacist — Optum" is benefit/utilization-management informatics, not clinical-care informatics — different work, different exit paths, not what I'm trying to pivot into. The employer signal is the rule here, not the title.

## Turn 21 — ASSISTANT


Understood — PBM employer is the signal, title doesn't override it. Category b locked in.

Category c — Pharma industry titles

I'd filter out titles like:

Medical Science Liaison
Medical Affairs Manager
Pharmacovigilance Specialist
Drug Safety Associate
Clinical Research Pharmacist

Borderline ones I'm currently catching too — tell me if these should slip through:

Pharmacist — Medical Information
Clinical Safety Scientist

Yes / Some are OK / Skip?

## Turn 21 — USER


Yes — filter all seven. Pharma industry is wrong direction across the board, including the borderlines. "Clinical Research Pharmacist" is the one that gives me the most pause — there are bona fide hospital-based research-pharmacy roles I'd consider, but those are titled "Investigational Drug Service" or "Research Pharmacist" at the academic medical center, not "Clinical Research Pharmacist" which is usually pharma-industry. If a hospital-based one slips through under that title, the JD will make it obvious and I'll catch it manually.

## Turn 22 — ASSISTANT


Good call — the IDS/research-pharmacy distinction is a JD-read situation, not a title-filter situation. All seven filtered. Category c locked in.

Category d — Retail pharmacy titles and employers

I'd filter out titles like:

Retail Pharmacist
Community Pharmacist
Staff Pharmacist — Walgreens
Pharmacy Manager — CVS
Floating Pharmacist

Borderline ones I'm currently catching too — tell me if these should slip through:

Pharmacist in Charge — Rite Aid
Clinical Pharmacist — CVS Health (not CVS Pharmacy)

Yes / Some are OK / Skip?

## Turn 22 — USER


Yes — filter all seven. CVS Health is the PBM/insurance side; CVS Pharmacy is retail; both are out for me. "Pharmacist in Charge — Rite Aid" is a retail management title, definitely out. No exceptions to walk through.

## Turn 23 — ASSISTANT


Clean — all seven filtered, no exceptions. Category d locked in.

Category e — Director-and-above pharmacy titles

I'd filter out titles like:

Director of Pharmacy
Director of Clinical Informatics
Vice President of Pharmacy
Chief Pharmacy Officer
Associate Chief Pharmacy Officer

Borderline ones I'm currently catching too — tell me if these should slip through:

Associate Director of Pharmacy Informatics
Assistant Director — Clinical Informatics

Yes / Some are OK / Skip?

## Turn 23 — USER


Some are OK — let the borderlines through:

Filter the five main titles — those are real director-and-above roles where the work is people-management and budget, not informatics practice.

Let through:

- "Associate Director of Pharmacy Informatics" — at academic medical centers this often means first-line lead of a small informatics team, with the "Associate Director" title being institutional inflation. I'd want to scan the JD to see if the day-to-day is the work I want.
- "Assistant Director — Clinical Informatics" — same shape, same logic.

The rule I'd use: filter pure pharmacy-administration director/VP/chief titles, but let "Associate" or "Assistant Director" through when paired with Informatics or Clinical Informatics in the title — those are often IC-lead roles with promotional titling.

## Turn 24 — ASSISTANT


Got it — filtering pure Director/VP/Chief pharmacy-administration titles, letting Associate Director and Assistant Director slip through when paired with Informatics or Clinical Informatics. Category e locked in.

Category f — Pure application analyst titles

I'd filter out titles like:

Epic Willow Application Analyst
Pharmacy Application Analyst
EHR Application Analyst — Pharmacy
Systems Analyst — Pharmacy IT
Pharmacy Systems Specialist

Borderline ones I'm currently catching too — tell me if these should slip through:

Clinical Informatics Analyst — Pharmacy
Pharmacy Informatics Analyst

Yes / Some are OK / Skip?

## Turn 24 — USER


Push back on this whole category — most of these aren't title-signal, they're JD-read. Skip the title-filter approach for category f and let me explain:

"Epic Willow Application Analyst" is actually a positive in-domain pattern for me when the JD requires or prefers a clinical license. The same title at a non-clinical-license shop is a hard no. The title alone doesn't distinguish — only the JD does. Same logic for "Pharmacy Application Analyst" and "EHR Application Analyst — Pharmacy."

What you can title-filter is the IT-only flavor:

- "Systems Analyst — Pharmacy IT" — filter, that's pure infrastructure
- "Pharmacy Systems Specialist" — filter, same
- Anything titled "IT Analyst" or "Systems Engineer" with "Pharmacy" as the scope qualifier — filter, that's a different job family

What you should let through:

- Epic Willow Application Analyst
- Pharmacy Application Analyst
- EHR Application Analyst — Pharmacy
- Clinical Informatics Analyst — Pharmacy (both borderlines)
- Pharmacy Informatics Analyst

For those I want to read the JD. The reject-reason "Pure App Analyst — Pharm.D. Decorative" gets applied after I've read enough to confirm; the prefilter shouldn't try to predict it from the title.

## Turn 25 — ASSISTANT


That's exactly the right call and a useful correction — I was over-reaching with the title filter here. The distinction is clean: IT-infrastructure titles get filtered, analyst titles with clinical scope get through for JD review.

Filtering only: - Systems Analyst — Pharmacy IT - Pharmacy Systems Specialist - IT Analyst with Pharmacy as scope qualifier - Systems Engineer with Pharmacy as scope qualifier

Letting through: Epic Willow Application Analyst, Pharmacy Application Analyst, EHR Application Analyst — Pharmacy, Clinical Informatics Analyst — Pharmacy, Pharmacy Informatics Analyst.

Category f locked in (narrowed to IT-infrastructure-only filtering). Moving on.

Category g — Informatics-adjacent but primarily staff-coverage roles

I'd filter out titles like:

Clinical Pharmacist — Informatics Support
Pharmacist — EHR Champion
Staff Pharmacist with Informatics Duties
Clinical Pharmacist — Order Set Maintenance

Borderline ones I'm currently catching too — tell me if these should slip through:

Pharmacy Informatics Coordinator
Clinical Pharmacist — Informatics Lead

Yes / Some are OK / Skip?

## Turn 25 — USER


Same issue as category f — this is mostly JD-read, not title-signal. Let me split:

Filter (title is unambiguous side-duty):

- Staff Pharmacist with Informatics Duties — the "with X duties" formulation always means "primary role is X" where X is the leading title
- Clinical Pharmacist — Order Set Maintenance — "maintenance" is the tell; it's compliance work tacked onto staff coverage

Let through (title is ambiguous, JD needed):

- Clinical Pharmacist — Informatics Support — could be real informatics with reporting-line phrasing
- Pharmacist — EHR Champion — at academic medical centers "Champion" is often a real first-line informatics role
- Pharmacy Informatics Coordinator — could be real informatics, especially at smaller institutions
- Clinical Pharmacist — Informatics Lead — that "Lead" qualifier is exactly the IC-lead level I'm targeting

I'd rather scan a JD and reject manually under the "Informatics-on-the-Side Reframing" reject reason than miss the half of these that ARE real informatics roles with imperfect titling. The whole reason that reject reason exists is to catch this category at JD-read time — the prefilter shouldn't try to do that work.

## Turn 26 — ASSISTANT


Correct again — you're right to push back. The "with X duties" and "maintenance" formulations are the only unambiguous title signals here. Everything else needs JD-read.

Filtering only: - Any title with "with Informatics Duties" or "with [X] Duties" formulation - Clinical Pharmacist — Order Set Maintenance (and close variants with "Maintenance" as the trailing qualifier)

Letting through: Clinical Pharmacist — Informatics Support, Pharmacist — EHR Champion, Pharmacy Informatics Coordinator, Clinical Pharmacist — Informatics Lead, and similar ambiguous-but-possibly-real titles.

Category g locked in (narrowed to formulation-based filtering). Moving on.

Category h — Ambulatory/outpatient-only clinical pharmacist roles

I'd filter out titles like:

Ambulatory Care Pharmacist
Outpatient Clinical Pharmacist
Retail Ambulatory Pharmacist
Primary Care Pharmacy Specialist

Borderline ones I'm currently catching too — tell me if these should slip through:

Ambulatory Pharmacy Informatics Specialist
Clinical Pharmacist — Outpatient Informatics

Yes / Some are OK / Skip?

## Turn 26 — USER


Some are OK — let the informatics-flavored borderlines through:

Filter the four main titles — Ambulatory Care Pharmacist, Outpatient Clinical Pharmacist, Retail Ambulatory Pharmacist, Primary Care Pharmacy Specialist — those are direct-patient-care roles in a setting I don't have experience in and don't want to pivot toward.

Let through:

- Ambulatory Pharmacy Informatics Specialist — the "Informatics" qualifier makes this a real consideration even though the setting is ambulatory
- Clinical Pharmacist — Outpatient Informatics — same logic

The general rule: filter ambulatory/outpatient titles when they describe direct-patient-care work, but let anything with "Informatics" or "Decision Support" in the title slip through regardless of setting — those are the same skill set as inpatient informatics, just applied to a different care venue.

## Turn 27 — ASSISTANT


Clean rule — ambulatory/outpatient direct-care titles filtered, informatics qualifier overrides the setting filter. Category h locked in.

Category i — Spam and alert-management noise

I'd filter out titles like:

Manage Your Job Alerts
Your Job Alert for Pharmacist
Join Our Talent Network
New Jobs Matching Your Search
Recommended Jobs for You

No real borderlines here — this is all noise. Yes / Skip?

## Turn 27 — USER


Yes — filter all five. Noise.

## Turn 28 — ASSISTANT


Category i locked in.

Category j — Locum/per-diem/contract pharmacist roles

I'd filter out titles like:

Locum Tenens Pharmacist
Per Diem Clinical Pharmacist
Contract Pharmacist — Remote
Travel Pharmacist
Temporary Staff Pharmacist

Borderline ones I'm currently catching too — tell me if these should slip through:

Contract Pharmacy Informaticist
Per Diem Informatics Pharmacist

Yes / Some are OK / Skip?

## Turn 28 — USER


Yes — filter all seven, borderlines included. Contract and per-diem informatics roles aren't what I want either. Informatics work is iterative and trust-based; a six-month contract doesn't let you build the institutional knowledge or relationships that the role depends on. If I'm pivoting, I'm pivoting into a real seat.

## Turn 29 — ASSISTANT


Understood — contract structure is the signal regardless of title. Category j locked in.

That's all ten exclusion categories done. Let's move to Pass B.

Pass B — Positive patterns

Here are roles the pipeline should mark as "yes, this is me." Pick the ones that fit, drop any that don't, and add anything I missed:

a. Pharmacy Informaticist / Pharmacy Informatics Pharmacist b. Clinical Informatics Pharmacist c. Clinical Informatics Specialist (pharmacy-adjacent, clinical license load-bearing) d. Epic Willow / CPOE specialist titles (clinical, not pure IT) e. Medication safety informatics roles f. Order set / clinical decision support roles g. EHR governance / P&T informatics roles h. Antimicrobial stewardship informatics roles i. Patient safety pharmacist roles with informatics scope

Reply with the letters you want to keep, plus any I missed.

## Turn 29 — USER


Keep all nine — a through i — every one of them is a "yes, this is me" pattern that maps to work I've done or want to be doing.

Two I'd add:

j. CMIO support / Physician Informatics roles where pharmacy is in scope — these surface at academic medical centers and they fit when the org structure puts pharmacy informatics under the CMIO rather than under pharmacy administration.

k. Pharmacy Quality Improvement / Pharmacy Outcomes roles when they have an EHR/data-pipeline component — the alert-fatigue work I did sits at this intersection, and titles with "Quality" or "Outcomes" plus an EHR or data qualifier are legitimately my space.

One sub-note on (h) Antimicrobial stewardship informatics: even without "informatics" explicitly in the title, ASP coordinator roles with an EHR/decision-support scope qualify — that's literally what I do day-to-day now.

## Turn 30 — ASSISTANT


Good — all nine plus j and k, eleven total. And the ASP note is captured: antimicrobial stewardship coordinator titles qualify when paired with EHR or decision-support scope, even without "informatics" in the title.

Let's work through them one at a time.

Pattern a — Pharmacy Informaticist / Pharmacy Informatics Pharmacist

I'd mark as positive matches:

Pharmacy Informaticist
Pharmacy Informatics Pharmacist
Pharmacist Informaticist
Informatics Pharmacist
Pharmacy Informatics Specialist

Borderline ones I'm currently catching too — tell me if any of these should be excluded:

Pharmacy Informatics Coordinator
Pharmacy Informatics Technician

Yes (match all of these) / Some are OK (tell me which to exclude) / Skip?

## Turn 30 — USER


Some are OK — exclude one:

Match all five main titles. Match "Pharmacy Informatics Coordinator" — that one is fine, common at smaller systems.

Exclude "Pharmacy Informatics Technician" — that's the pharmacy-technician (not pharmacist) role, different credentialing entirely. A Pharm.D. wouldn't be hired into a tech-level title.

## Turn 31 — ASSISTANT


Clean — matching all six including Coordinator, excluding Technician. Pattern a locked in.

Pattern b — Clinical Informatics Pharmacist

I'd mark as positive matches:

Clinical Informatics Pharmacist
Pharmacist — Clinical Informatics
Clinical Pharmacy Informaticist
Pharmacist, Clinical Informatics
Clinical Informatics Specialist — Pharmacy

Borderline ones I'm currently catching too:

Clinical Informatics Pharmacist — Applications
Clinical Informatics Pharmacist — Decision Support

Yes / Some are OK / Skip?

## Turn 31 — USER


Yes — match all seven, borderlines included. The "— Applications" and "— Decision Support" qualifiers are just the institutional placement of the same role, not a meaningful narrowing of the work.

## Turn 32 — ASSISTANT


Pattern b locked in.

Pattern c — Clinical Informatics Specialist (pharmacy-adjacent, clinical license load-bearing)

I'd mark as positive matches:

Clinical Informatics Specialist
Clinical Informatics Analyst
Clinical Systems Specialist — Pharmacy
Informatics Specialist — Clinical Pharmacy
Clinical Informatics Consultant

Borderline ones I'm currently catching too:

Clinical Informatics Specialist — Nursing
Clinical Informatics Specialist — General

Yes / Some are OK / Skip?

## Turn 32 — USER


Some are OK — exclude one, narrow the other:

Match the five main titles when they appear at health systems and the JD indicates clinical-license preference. "Clinical Informatics Consultant" specifically — match only when at a health system or AMC; exclude when the employer is a consulting firm (Deloitte, Accenture Health, etc.) because that's a different career arc I'm not pursuing.

Exclude "Clinical Informatics Specialist — Nursing" — that's a nursing-informatics role, different licensure and scope. Not my space, even though the title rhymes.

Match "Clinical Informatics Specialist — General" — that's catch-all language and the JD will tell me whether pharmacy is in scope.

## Turn 33 — ASSISTANT


Got it — matching Clinical Informatics Specialist/Analyst/Consultant titles at health systems and AMCs, excluding nursing-specific variants, letting general variants through for JD review. The consulting-firm exclusion is a JD-read call rather than a title filter since employer type isn't always in the title itself — I'll note it in your profile's "Things to Avoid" section so the scorer has context.

Pattern c locked in.

Pattern d — Epic Willow / CPOE specialist titles (clinical, not pure IT)

I'd mark as positive matches:

Epic Willow Analyst — Clinical
CPOE Pharmacist
Epic Willow Clinical Informaticist
Clinical CPOE Specialist
Pharmacy CPOE Analyst

Borderline ones I'm currently catching too:

Epic Willow Application Analyst
Epic Willow Build Analyst

Yes / Some are OK / Skip?

## Turn 33 — USER


Some are OK — match the borderlines conditionally:

Match the five main titles unconditionally.

Match "Epic Willow Application Analyst" and "Epic Willow Build Analyst" when JD mentions clinical license requirement or preference; otherwise the Pharm.D. is decorative and that's a reject. Title alone isn't enough to distinguish, so include them in the positive set and let the scorer read the JD for the license-required signal.

## Turn 34 — ASSISTANT


Understood — both borderlines go in the positive set with the expectation that the JD-read catches the license-decorative cases. The scorer handles the distinction; the title filter just gets them into the queue. Pattern d locked in.

Pattern e — Medication safety informatics roles

I'd mark as positive matches:

Medication Safety Pharmacist — Informatics
Pharmacy Medication Safety Specialist
Medication Safety Informaticist
Clinical Pharmacist — Medication Safety Systems
Medication Safety Analyst — Pharmacy

Borderline ones I'm currently catching too:

Medication Safety Officer
Medication Safety Coordinator

Yes / Some are OK / Skip?

## Turn 34 — USER


Yes — match all seven, borderlines included. Medication Safety Officer is exactly the kind of role I'd take; at academic medical centers that title often carries informatics scope even when "informatics" isn't in the title. Coordinator is similar at smaller systems. Let both through and let the JD confirm scope.

## Turn 35 — ASSISTANT


Pattern e locked in.

Pattern f — Order set / clinical decision support roles

I'd mark as positive matches:

Clinical Decision Support Pharmacist
Order Set Analyst — Pharmacy
Clinical Decision Support Specialist
Order Set Coordinator — Clinical
Decision Support Pharmacist

Borderline ones I'm currently catching too:

Clinical Decision Support Analyst
Order Set Developer

Yes / Some are OK / Skip?

## Turn 35 — USER


Yes — match all seven. CDS Analyst and Order Set Developer can be either clinical or pure-IT depending on the shop, but I'd rather scan the JD on those than miss the real ones.

## Turn 36 — ASSISTANT


Pattern f locked in.

Pattern g — EHR governance / P&T informatics roles

I'd mark as positive matches:

EHR Governance Pharmacist
Pharmacy and Therapeutics Informatics Specialist
P&T Committee Informatics Lead
Clinical Governance Pharmacist — EHR
Formulary Informatics Pharmacist

Borderline ones I'm currently catching too:

Formulary Manager
P&T Coordinator

Yes / Some are OK / Skip?

## Turn 36 — USER


Some are OK — let me split:

Match all five main titles.

Match "P&T Coordinator" — at academic medical centers this is often an informatics-flavored role (managing the EHR-side formulary configuration, not just the meeting minutes). Worth scanning the JD.

Exclude "Formulary Manager" — this is a pharmacy administration title focused on contract negotiation and budget, not informatics work. Different role family even though the word "formulary" is shared.

## Turn 37 — ASSISTANT


Clean split — P&T Coordinator in, Formulary Manager out. The shared vocabulary is exactly the kind of false-positive the positive-pattern set needs to handle carefully. Pattern g locked in.

Pattern h — Antimicrobial stewardship informatics roles

I'd mark as positive matches:

Antimicrobial Stewardship Pharmacist — Informatics
ASP Informatics Pharmacist
Antimicrobial Stewardship Coordinator — EHR
Stewardship Pharmacist — Decision Support
Clinical Pharmacist — Antimicrobial Stewardship and Informatics

Borderline ones I'm currently catching too — per your earlier note, ASP coordinator titles with EHR/decision-support scope qualify even without "informatics" in the title:

Antimicrobial Stewardship Coordinator
Antimicrobial Stewardship Pharmacist

Yes / Some are OK / Skip?

## Turn 37 — USER


Yes — match all seven. Both borderlines stay in the positive set per the earlier note; the JD will reveal whether the EHR/decision-support scope is there. ASP coordinator without an informatics scope is still close enough to my current work that I'd rather see it and decide than have it filtered.

## Turn 38 — ASSISTANT


Pattern h locked in.

Pattern i — Patient safety pharmacist roles with informatics scope

I'd mark as positive matches:

Patient Safety Pharmacist — Informatics
Clinical Pharmacist — Patient Safety Systems
Pharmacy Patient Safety Specialist
Patient Safety Informaticist — Pharmacy
Clinical Safety Pharmacist — EHR

Borderline ones I'm currently catching too:

Patient Safety Pharmacist
Patient Safety Coordinator — Pharmacy

Yes / Some are OK / Skip?

## Turn 38 — USER


Yes — match all seven. Patient Safety Pharmacist and Patient Safety Coordinator — Pharmacy both fit even without an explicit informatics qualifier; the pediatric heparin-dosing workflow change on my resume is exactly the patient-safety-meets-CPOE work these roles usually cover.

## Turn 39 — ASSISTANT


Pattern i locked in.

Pattern j — CMIO support / Physician Informatics roles where pharmacy is in scope

I'd mark as positive matches:

Pharmacy Informatics Liaison — CMIO Office
Clinical Informatics Pharmacist — Physician Support
CMIO Support Pharmacist
Pharmacy Liaison — Clinical Informatics
Pharmacist — Physician Informatics Team

Borderline ones I'm currently catching too:

Clinical Informatics Analyst — CMIO Support
Physician Informatics Specialist

Yes / Some are OK / Skip?

## Turn 39 — USER


Some are OK — split the borderlines:

Match all five main titles.

Match "Clinical Informatics Analyst — CMIO Support" — the CMIO-support context tells me pharmacy is likely in scope; JD will confirm.

Exclude "Physician Informatics Specialist" — that's explicitly a physician-track role; pharmacy isn't in scope unless the title makes it explicit. Different credentialing path, different audience.

## Turn 40 — ASSISTANT


Clean — CMIO-support context is enough to queue for JD review, physician-track title without pharmacy qualifier is out. Pattern j locked in.

Pattern k — Pharmacy Quality Improvement / Pharmacy Outcomes roles with EHR/data-pipeline component

I'd mark as positive matches:

Pharmacy Quality Improvement Specialist — EHR
Pharmacy Outcomes Analyst — Informatics
Clinical Pharmacist — Quality and Informatics
Pharmacy Quality Informaticist
Medication Outcomes Specialist — Data Systems

Borderline ones I'm currently catching too:

Pharmacy Quality Improvement Specialist
Pharmacy Outcomes Analyst

Yes / Some are OK / Skip?

## Turn 40 — USER


Yes — match all seven. The borderlines without "EHR" or "Informatics" qualifiers can still be a fit when the JD describes data-pipeline work; the alert-fatigue project I led was technically a quality-improvement project with an EHR component, and roles in that shape often title themselves "Quality Improvement Specialist" without the data qualifier in the title. Let them through for JD review.

## Turn 41 — ASSISTANT


Pattern k locked in.

That's all eleven positive patterns done. Pass B complete.

Before we move to Phase 5, let me do a quick internal consistency check — I'll verify that everything I've captured across the phases lines up before I start emitting files. One moment.

Everything checks out:

All five Tier 1 employers (Mayo Clinic, M Health Fairview, UW Health, Allina Health, Children's Minnesota) are present in both the target-companies list and the sector-reference categories.
All ten exclusion categories from Phase 4 Pass A have corresponding prefilter rules.
All eleven positive patterns from Phase 4 Pass B are represented in the in-domain patterns.
All Tier 1 employers appear under exactly one sector-reference category.

Ready to emit. Here's what's coming and how we'll move through it:

I've captured your responses. I'm going to emit your config in four groups:

a. Identity — your name, timezone, and how to push you notifications b. Targeting — your target role and the companies you'd take a job at c. Filters — what to exclude and what to prioritize d. Writing voice — skipped (no voice samples provided)

I'll emit all four groups back-to-back. After the last group, a green Finalize button appears — click it and findajob writes your config. If anything in a group looks wrong, type redo {a|b|c|d} any time before Finalize.

Before I emit Group a, I need three quick values:

1. Display name — What name do you want on your resume and cover letter filenames? (Exactly as you want it to appear — e.g., "Avery Chen" or "Avery Chen PharmD" or however you prefer.)

2. Timezone — You're in Minneapolis — I'll use America/Chicago for you. Just confirm that's right.

3. Notification topic — The pipeline pushes your daily scoreboard and alerts via a free app called ntfy (install on your phone or use the web UI at ntfy.sh — no signup needed, just subscribe to your topic). Your suggested default topic is findajob-avery-202605. Reply "use default" or give me a different string — something nobody would guess works best. I'll confirm the full value back to you before writing it.

## Turn 41 — USER


1. Display name: Avery Chen, Pharm.D., BCPS

2. Timezone: confirmed, America/Chicago.

3. Notification topic: avery-pharmd-informatics-2026 — that's unique enough that nobody would guess it.

## Turn 42 — ASSISTANT


Got it. Let me confirm the three values before I emit:

Display name: `Avery Chen, Pharm.D., BCPS`
Timezone: `America/Chicago`
Notification topic: `avery-pharmd-informatics-2026`

All confirmed — emitting all groups now.

📄 Captured: profile.md

📄 Captured: master_resume.md

📄 Captured: display_name.txt

📄 Captured: timezone.txt

📄 Captured: ntfy_topic.txt

**Group a — Identity** done — 5 files captured: profile.md, master_resume.md, display_name.txt, timezone.txt, ntfy_topic.txt.

📄 Captured: target_companies.md

📄 Captured: business_sector_employers_reference.md

📄 Captured: jsearch_queries.txt

📄 Captured: linkedin-alerts.md

📄 Captured: feed-urls.txt

**Group b — Targeting** done — 5 files captured: target_companies.md, business_sector_employers_reference.md, jsearch_queries.txt, linkedin-alerts.md, feed-urls.txt.

One note on the feed URLs: most Upper Midwest health systems run Workday, which the pipeline's fetcher doesn't currently support. I've emitted the three I can confirm on supported ATSes (Mayo Clinic on Greenhouse, Allina Health on Greenhouse, Children's Minnesota on Lever) and commented out the rest. When Workday support lands, those commented lines are ready to activate. You may want to verify the three active slugs against the actual career pages — ATS slugs occasionally change after system migrations.

📄 Captured: prefilter_rules.yaml

📄 Captured: in_domain_patterns.yaml

📄 Captured: reject_reasons.yaml

**Group c — Filters** done — 3 files captured: prefilter_rules.yaml, in_domain_patterns.yaml, reject_reasons.yaml.

All groups captured. Click **Finalize** when ready, or type **redo {a|b|c|d}** if anything looks wrong.

## Turn 42 — USER


next
