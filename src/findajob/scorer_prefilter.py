#!/usr/bin/env python3
# ~/JobSearchPipeline/scripts/scorer_prefilter.py
"""
Deterministic pre-filter for job scoring.
Runs BEFORE any LLM call. Two stages:

  Stage 1 — Hard reject by title regex → score 1, scored, no LLM
  Stage 2 — In-domain title + no usable JD → score 5 (or 6 for Tier 1), no LLM

If neither stage fires, returns (None, None) and caller should invoke the LLM.

Usage:
    from scorer_prefilter import prefilter_score
    result, reason = prefilter_score(title, company, jd_is_usable)
    if result is not None:
        return result, 0   # latency=0, no subprocess
    # ... LLM path
"""

from __future__ import annotations

import re

# ── Tier 1 companies ──────────────────────────────────────────────────────────
TIER1: frozenset[str] = frozenset(
    [
        "meta",
        "google",
        "alphabet",
        "microsoft",
        "amazon",
        "aws",
        "openai",
        "anthropic",
        "xai",
        "etched",
        "nscale",
        "cerebras",
        "groq",
        "tenstorrent",
        "sambanova",
        "nebius",
        "coreweave",
        "crusoe",
        "astera",
    ]
)


def _is_tier1(company: str) -> bool:
    if not company:
        return False
    c = company.lower()
    return any(t in c for t in TIER1)


# ── Stage 1: Hard reject patterns ─────────────────────────────────────────────
# Applied to title only. Any match → score 1 immediately, no JD needed.
# Order: specific before general to aid readability; all case-insensitive.
_HARD_REJECT_PATTERNS: list[str] = [
    # Software engineering
    r"\bsoftware\s+engineer(ing)?\b",
    r"\bsoftware\s+developer\b",
    r"\bsoftware\s+architect\b",
    r"\bsoftware\s+development\s+engineer\b",
    r"\b(swe|sde)\b",
    # Security (cyber / logical — not physical DC security which would be facilities)
    r"\bsecurity\s+analyst\b",
    r"\bsoc\s+analyst\b",
    r"\bthreat\s+(detection|intelligence|hunting)\b",
    r"\bcyber\s*security\b",
    r"\binformation\s+security\b",
    r"\bsecurity\s+sales\b",
    r"\bsecurity\s+site\s+(operations|manager)\b",
    r"\bsecurity\s+operations\s+center\b",
    # Sales / BD
    r"\baccount\s+executive\b",
    r"\bsales\s+specialist\b",
    r"\bsales\s+representative\b",
    r"\bsales\s+manager\b",
    r"\benterprise\s+sales\b",
    r"\bkey\s+account\b",
    r"\bfield\s+sales\b",
    r"\bbusiness\s+development\s+(manager|lead|director|representative)\b",
    # IT service management
    r"\bit\s+service\s+management\b",
    r"\bitsm\b",
    r"\bit\s+help\s*desk\b",
    r"\bservice\s+desk\s+manager\b",
    r"\bit\s+support\s+manager\b",
    # General IT management (no DC scope)
    r"\bregional\s+it\s+manager\b",
    r"\bworkplace\s+technology\s+manager\b",
    r"\bend.user\s+computing\b",
    # Supply chain
    r"\bsupply\s+chain\b",
    r"\bprocurement\s+(manager|lead|specialist|director)\b",
    r"\bsourcing\s+(manager|lead|specialist)\b",
    r"\blogistics\s+manager\b",
    r"\bfulfillment\s+manager\b",
    r"\binventory\s+(manager|analyst)\b",
    # Networking
    r"\bnetwork\s+engineer(ing)?\b",
    r"\bnetwork\s+architect\b",
    r"\bnoc\s+engineer\b",
    r"\bconnectivity\s+engineer\b",
    # Hardware design (NOT ops — Tier 1 does NOT override these)
    r"\bcontrols\s+engineer(ing)?\b",
    r"\belectrical\s+engineer(ing)?\b",
    r"\bmechanical\s+engineer(ing)?\b",
    r"\bfirmware\s+engineer(ing)?\b",
    r"\bfpga\b",
    r"\bboard\s+design\b",
    r"\bhardware\s+development\s+engineer\b",
    r"\bhardware\s+design\s+engineer\b",
    # Healthcare / life sciences
    r"\bnurs(e|ing)\b",
    r"\bclinical\s+(manager|director|lead|specialist|coordinator|trial|research|lab)\b",
    r"\bpatient\s+care\b",
    r"\bhealthcare\s+(manager|administrator|coordinator)\b",
    r"\bpharmaceut",
    r"\bbiotech\b",
    r"\blife\s+sciences\s+(manager|director|lead)\b",
    r"\bphlebotom",
    r"\bbiomedical?\s+(equip|tech)",
    r"\blab\s+scientist\b",
    r"\bcare\s+(coordinator|at\s+home)\b",
    r"\bnephrology\b",
    # Finance / legal / HR / admin
    r"\bfinancial\s+(analyst|advisor|planner|controller)\b",
    r"\baudit\s+(manager|director|analyst)\b",
    r"\bcompliance\s+(manager|officer|analyst)\b",
    r"\blegal\s+(counsel|manager|director)\b",
    r"\bhuman\s+resources\s+(manager|director|business\s+partner)\b",
    r"\btalent\s+acquisition\b",
    r"\brecruiter\b",
    r"\bmarketing\s+manager\b",
    r"\bfp&?a\s+(manager|analyst|director)\b",
    r"\b(senior\s+)?gl\s+accountant\b",
    r"\bpayroll\s+(manager|operations|specialist)\b",
    r"\breal\s+estate\s+operations\s+accountant\b",
    # Construction / trades
    r"\bconstruction\s+(manager|safety|specialist)\b",
    r"\bmep\s+superintendent\b",
    r"\bcrane\b.*\b(supt|superintendent)\b",
    r"\brigging\s+(supt|superintendent)\b",
    r"\bgeneral\s+superintendent\b",
    r"\bsite\s+superintendent\b",
    r"\bsurvey\s+technician\b",
    r"\bsignal\s+engineer\b",
    # Aviation / military hardware
    r"\baircraft\s+mechanic\b",
    r"\bf-\d+\b",
    # AV / events
    r"\bevent\s+techni(cian|cal)\b",
    r"\baudio\s+visual\b",
    r"\bevent\s+tech\s",
    r"\bdirector\s+event\s+tech\b",
    # Food service / culinary
    r"\bschool\s+nutrition\b",
    r"\bculinary\b",
    r"\b(lead\s+)?cook\b",
    r"\bfood\s+service\b",
    r"\bchef\b",
    # Landscaping / groundskeeping
    r"\blandscap(e|ing)\b",
    r"\blawn\b",
    # Property management
    r"\bproperty\s+manager\b",
    r"\bcommunity\s+association\b",
    # Chemical
    r"\bchemist\b",
    # Manufacturing / production / plant (non-DC)
    r"\bproduction\s+(buyer|planner|engineer)\b",
    r"\bplant\s+(manager|maintenance)\b",
    r"\bmanufacturing\s+(engineer|manager|operations|test)\b",
    r"\bmanufacturing\s+test\b",
    # Quality / process engineering (0% applied rate in feedback data)
    r"\bquality\s+(engineer|technician|assurance|control)\b",
    r"\bprocess\s+engineer\b",
    r"\bprocess\s+quality\s+engineer\b",
    # Systems development engineering (SDE-adjacent, not DC ops)
    r"\bsystems\s+development\s+engineer\b",
    # Transportation / warehouse / logistics expansions
    r"\btransportation\s+coordinator\b",
    r"\bhauling\b",
    r"\blogistics\s+(analyst|associate)\b",
    r"\bwarehouse\s+manager\b",
    r"\bfulfillment\s+operations\b",
    # Childcare / education
    r"\bchildcare\b",
    r"\bdaycare\b",
    r"\bstipend\b.*\bsite\s+supervisor\b",
    # Digital signage
    r"\bdigital\s+signage\b",
    # Salesperson / GTM
    r"\bsalesperson\b",
    r"\bsales\s+lead\b",
    # Systems admin (not DC ops)
    r"\bsystems\s+administrator\b",
    # Storage / SRE / DevOps (pure software roles)
    r"\bstorage\s+engineer\b",
    r"\bsite\s+reliability\s+engineer\b",
    r"\bdevops\s+engineer\b",
    r"\bkernel\s+engineer\b",
    # Data engineering / BI (not DC)
    r"\bdata\s+engineer\b",
    r"\bbusiness\s+intelligence\s+(developer|analyst)\b",
    r"\bdata\s+strategist\b",
    # General manager / maintenance tech (DC override prevents false positives)
    r"\bgeneral\s+manager\b",
    r"\bmaintenance\s+technician\b",
    # Generic junk / non-job entries
    r"^manage\s+job\s+alerts?\b",
    r"^your\s+job\s+alert\s+for\b",
    r"\bjoin\s+our\s+talent\s+network\b",
    # Facilities (no DC scope in title)
    r"\bcustodial\b",
    r"\bjanitorial\b",
    r"\bvenue\s+operations\b",
    r"\bfacilities\s+coordinator\b",
    r"\bbuilding\s+manager\b",
    r"\bworkplace\s+services\s+manager\b",
    r"\boffice\s+manager\b",
    r"\bworkplace\s+manager\b",
]

_HARD_REJECT_RE: re.Pattern[str] = re.compile(
    "|".join(f"(?:{p})" for p in _HARD_REJECT_PATTERNS),
    re.IGNORECASE,
)

# If title contains DC context, suppress the hard reject — the job may be in-domain
_DC_CONTEXT_RE: re.Pattern[str] = re.compile(
    r"\bdata\s*center\b|\bdatacenter\b|\bdc\s+(ops|operations|site)\b",
    re.IGNORECASE,
)


def _hard_reject_match(title: str) -> str | None:
    """Return the matched pattern string, or None."""
    m = _HARD_REJECT_RE.search(title)
    if not m:
        return None
    # Don't reject if the title also contains data center context
    if _DC_CONTEXT_RE.search(title):
        return None
    return m.group(0).strip()


# ── Stage 2: In-domain title patterns ─────────────────────────────────────────
# If title matches and JD is unusable → score 5 (or 6 for Tier 1), no LLM.
_IN_DOMAIN_PATTERNS: list[str] = [
    r"\bdata\s*center\s+(operations|site|manager|lead|technician|engineer)\b",
    r"\bdatacenter\s+(operations|site|manager|lead)\b",
    r"\bdc\s+(ops|operations|site\s+manager)\b",
    r"\bnpi\s+(manager|lead|engineer|program\s+manager)\b",
    r"\bhardware\s+(ops|operations|bring.up|npi|program\s+manager)\b",
    r"\binfrastructure\s+operations\s+(manager|lead|director)\b",
    r"\boperational\s+readiness\b",
    r"\blab\s+operations\s+(manager|lead)\b",
    r"\bsite\s+manager,?\s+datacenter\b",
    r"\bdatacenter.*\boperations\s+manager\b",
    r"\bdata\s+center.*\boperations\s+(area\s+)?manager\b",
    r"\bsite\s+operations\s+manager\b",  # without "workplace services"
    r"\bengineering\s+operations\s+manager\b",
    r"\bfield\s+operations\s+(manager|lead)\b",
]

_IN_DOMAIN_RE: re.Pattern[str] = re.compile(
    "|".join(f"(?:{p})" for p in _IN_DOMAIN_PATTERNS),
    re.IGNORECASE,
)

# These terms in the same title poison an otherwise in-domain match
_IN_DOMAIN_POISON: re.Pattern[str] = re.compile(
    r"\b(workplace\s+services|custodial|janitorial|facilities\s+only|office\s+services)\b",
    re.IGNORECASE,
)


def _in_domain_match(title: str) -> bool:
    if _IN_DOMAIN_POISON.search(title):
        return False
    return bool(_IN_DOMAIN_RE.search(title))


# ── Public API ─────────────────────────────────────────────────────────────────


def prefilter_score(title: str, company: str, jd_usable: bool) -> tuple[dict[str, object] | None, str | None]:
    """
    Returns (result_dict, reason_str) if a deterministic decision can be made,
    or (None, None) if the LLM should be invoked.

    result_dict matches the scoring_schema.json shape.
    latency_ms should be logged as 0 by the caller.
    """
    t = (title or "").strip()

    # ── Stage 1: Hard reject ──────────────────────────────────────────────────
    match = _hard_reject_match(t)
    if match:
        reason = f'Pre-filter hard reject: title matched "{match}"'
        return {
            "score_status": "scored",
            "relevance_score": 1,
            "interview_likelihood": 1,
            "strengths_alignment": "Hard reject — title is outside candidate domain.",
            "industry_sector": None,
            "comp_estimate": None,
            "ai_notes": reason,
            "score_flag_reason": reason,
            "remote_status": "Unknown",
        }, reason

    # ── Stage 2: In-domain title, JD absent ──────────────────────────────────
    if not jd_usable and _in_domain_match(t):
        tier1 = _is_tier1(company)
        score = 6 if tier1 else 5
        tier_note = " (Tier 1 company bonus)" if tier1 else ""
        reason = f"Pre-filter in-domain/no-JD: scored {score}{tier_note}"
        return {
            "score_status": "scored",
            "relevance_score": score,
            "interview_likelihood": score - 1,
            "strengths_alignment": f"Title is directionally in-domain. JD unavailable — scored {score} per policy{tier_note}.",
            "industry_sector": None,
            "comp_estimate": None,
            "ai_notes": reason,
            "score_flag_reason": None,
            "remote_status": "Unknown",
        }, reason

    return None, None
