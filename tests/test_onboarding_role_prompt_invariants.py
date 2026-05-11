"""Static invariants for `config/roles/onboarding_interviewer.md` (#621).

The onboarding interviewer's role prompt is purely instructions to an LLM —
no Python parser to test against. The failure mode #621 documents (LLM
mixes letters / digits / bullets across questions in the same session) is
behavioral and only verifiable empirically via a full interview run.

These tests guard against the **structural cause** the bug originated from:
optional "letter OR digit" phrasing in the meta-rule, which gave the LLM
freedom to drift. Once locked to a single style with explicit prohibition
on the others, mid-session drift becomes the LLM's mistake to fix, not
the prompt's licence to grant.

Tests are static-only (regex grep over the file). They're cheap, run
without network, and fire if a future edit reintroduces the optionality
that caused #621.
"""

from __future__ import annotations

import re
from pathlib import Path

_ROLE_PATH = Path(__file__).parent.parent / "config" / "roles" / "onboarding_interviewer.md"


def _read_role() -> str:
    return _ROLE_PATH.read_text(encoding="utf-8")


# ── #621: option-prefix style is locked, not optional ────────────────────


def test_meta_rule_does_not_offer_letter_or_digit_choice() -> None:
    """The original bug source — "letter (a, b, c, …) or digit (1, 2, 3, …)"
    in the meta-rule — must not return. The LLM treated this as licence to
    pick a style per question, producing the mid-session drift testers saw."""
    text = _read_role()
    # The exact phrasing pre-#621 was "Number or letter every list of options"
    # plus "prefix each with a letter (a, b, c, …) or digit (1, 2, 3, …)".
    # Guard both forms.
    assert "Number or letter every list" not in text, (
        "The meta-rule must commit to one option-prefix style, not offer the LLM a choice. See #621."
    )
    # Detect "letter ... or digit" / "digit ... or letter" patterns within ~80
    # chars of each other in the meta-rule paragraph. False-positive-safe
    # because legitimate Phase-5 emit rules use long-form constructs like
    # "3g selection includes `a` (paid service) OR `c` (Gmail alerts)" — the
    # tokens "letter" and "digit" don't co-occur there.
    assert not re.search(
        r"\bletter\b[^.]{0,80}\bor\b[^.]{0,80}\bdigit\b",
        text,
        re.IGNORECASE,
    ), "meta-rule still offers letter-OR-digit style choice; see #621"
    assert not re.search(
        r"\bdigit\b[^.]{0,80}\bor\b[^.]{0,80}\bletter\b",
        text,
        re.IGNORECASE,
    ), "meta-rule still offers digit-OR-letter style choice; see #621"


def test_meta_rule_commits_to_letter_style() -> None:
    """The replacement instruction picks letters (a, b, c, …) — the style
    every actual question in the prompt already uses (sub-phase 3g source
    selection, Pass A/B category lists). The bullet "Letter every list of
    options" anchors the rule; absence means the meta-rule was dropped
    or weakened."""
    text = _read_role()
    assert "Letter every list of options" in text, (
        "meta-rule heading 'Letter every list of options' is missing; see #621"
    )


def test_meta_rule_forbids_bullets() -> None:
    """Bullets ("- foo", "* foo") were the third drift mode the tester
    observed. The meta-rule must explicitly forbid them — without that,
    the LLM falls back to its training-default list style on long lists."""
    text = _read_role()
    # Match the explicit prohibition phrase in the rewritten rule.
    assert re.search(
        r"Do NOT use\s+(digits|bullets)|never use\s+(digits|bullets)",
        text,
        re.IGNORECASE,
    ), "meta-rule must explicitly forbid digits and bullets to prevent drift; see #621"
