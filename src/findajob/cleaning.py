"""Job title/company cleaning, normalization, and fingerprinting."""

import hashlib
import re

# ── Normalization & Dedup ──
ABBREVIATIONS: dict[str, str] = {
    r"\bsr\.?\b": "senior",
    r"\bjr\.?\b": "junior",
    r"\bmgr\.?\b": "manager",
    r"\bdir\.?\b": "director",
    r"\beng\.?\b": "engineer",
    r"\bengr\.?\b": "engineer",
    r"\bops\.?\b": "operations",
    r"\binfra\.?\b": "infrastructure",
    r"\bvp\b": "vice president",
    r"\bsvp\b": "senior vice president",
    r"\bhw\b": "hardware",
    r"\bsw\b": "software",
    r"\bdc\b": "data center",
    r"\bmfg\b": "manufacturing",
    r"\bpgm\b": "program",
    r"\btpm\b": "technical program manager",
}


def normalize(text: str) -> str:
    text = text.lower().strip()
    for pattern, replacement in ABBREVIATIONS.items():
        text = re.sub(pattern, replacement, text)
    text = re.sub(r"[^a-z0-9 ]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def fingerprint(title: str, company: str, location: str = "") -> str:
    key = normalize(title) + "|" + normalize(company) + "|" + normalize(location)
    return hashlib.sha256(key.encode()).hexdigest()[:16]


# ── Title Cleaning ──
# Job boards (especially Indeed via Jobs API) append metadata directly to the title field:
# board name, location, salary, time-ago, badges. Strip everything after these markers.
_TITLE_SPLIT_PATTERNS: re.Pattern[str] = re.compile(
    r"(?:"
    r"Jobs via \w[\w ]*·"  # "Jobs via Dice ·"
    r"|\bvia \w[\w ]*·"  # "via LinkedIn ·"
    r"|\s·\s"  # generic " · " separator
    r"|\s[-–]\s(?:Remote|Hybrid|On-?site|Contract|Full.?time|Part.?time)"
    r"|\$[\d,]+[Kk]?\s*[-–]"  # salary range start "$140K -"
    r"|\d+\s*(?:hour|day|week|month)s?\s+ago"  # "2 days ago"
    r"|(?:Easy|Quick)\s+Apply"
    r"|Actively\s+recruiting"
    r"|Fast\s+growing"
    r")",
    re.IGNORECASE,
)


def clean_title(raw_title: str) -> str:
    """Strip job board metadata appended to title field by Indeed/Jobs API."""
    m = _TITLE_SPLIT_PATTERNS.search(raw_title)
    if m:
        raw_title = raw_title[: m.start()]
    return raw_title.strip(" ·-–")


# Company field from LinkedIn API often has location/metadata appended:
# "Google – Multiple Sites4 days ago", "Google · Sunnyvale, CA, US 12 connections"
_COMPANY_SPLIT_PATTERNS: re.Pattern[str] = re.compile(
    r"(?:"
    r"\s[·–—-]\s"  # " · " or " – " separator before location
    r"|\d+\s+connections?"  # "12 connections"
    r"|\d+\s*(?:hour|day|week|month)s?\s+ago"  # "3 days ago"
    r"|(?:Easy|Quick)\s+Apply"
    r"|Actively\s+recruiting"
    r"|,\s*[A-Z][a-z]+,\s*(?:United States|US|Canada|UK)"  # ", Sunnyvale, United States"
    r")",
    re.IGNORECASE,
)


def clean_company(raw_company: str) -> str:
    """Strip location/metadata appended to company field by LinkedIn/Indeed API."""
    if not raw_company:
        return ""
    m = _COMPANY_SPLIT_PATTERNS.search(raw_company)
    if m:
        raw_company = raw_company[: m.start()]
    return raw_company.strip(" ·-–,")


# Regex to extract numeric LinkedIn job ID from job URLs
# Matches: linkedin.com/jobs/view/1234567890 and linkedin.com/comm/jobs/view/1234567890
_LINKEDIN_JOB_ID_RE: re.Pattern[str] = re.compile(r"linkedin\.com/(?:comm/)?jobs/view/(\d+)", re.IGNORECASE)


def extract_linkedin_job_id(url: str | None) -> str | None:
    """Extract numeric job ID from a LinkedIn job URL. Returns str or None."""
    m = _LINKEDIN_JOB_ID_RE.search(url or "")
    return m.group(1) if m else None
