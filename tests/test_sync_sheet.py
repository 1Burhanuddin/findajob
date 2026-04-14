"""Tests for sync_sheet.py row-building and formula-generation logic."""

import sys
from unittest.mock import MagicMock, patch

# Mock Google API modules before importing sync_sheet (module-level side effects)
sys.modules["google.oauth2"] = MagicMock()
sys.modules["google.oauth2.service_account"] = MagicMock()
sys.modules["googleapiclient"] = MagicMock()
sys.modules["googleapiclient.discovery"] = MagicMock()

# Mock the file read for sheet_id.txt at module level
_real_open = open


def _patched_open(path, *args, **kwargs):
    if "sheet_id.txt" in str(path):
        from io import StringIO
        return StringIO("fake-sheet-id\n")
    return _real_open(path, *args, **kwargs)


with patch("builtins.open", side_effect=_patched_open):
    from scripts.sync_sheet import (
        DASH_HEADERS,
        DASH_LOOKUP,
        S1_HEADERS,
        S1_LOOKUP,
        build_row,
        hyperlink,
        safe_str,
    )


# ---------------------------------------------------------------------------
# FakeRow — mimics sqlite3.Row for build_row tests
# ---------------------------------------------------------------------------

class FakeRow:
    """Dict-like object that supports .keys() like sqlite3.Row."""

    def __init__(self, data):
        self._data = data

    def __getitem__(self, key):
        return self._data[key]

    def keys(self):
        return self._data.keys()


# ---------------------------------------------------------------------------
# hyperlink()
# ---------------------------------------------------------------------------

class TestHyperlink:
    def test_normal_url_and_label(self):
        result = hyperlink("https://example.com", "Click here")
        assert result == '=HYPERLINK("https://example.com","Click here")'

    def test_url_with_double_quotes(self):
        result = hyperlink('https://example.com/q="test"', "Label")
        assert result == '=HYPERLINK("https://example.com/q=%22test%22","Label")'

    def test_label_with_double_quotes(self):
        result = hyperlink("https://example.com", 'Say "hello"')
        assert result == '=HYPERLINK("https://example.com","Say ""hello""")'

    def test_empty_url_returns_plain_label(self):
        result = hyperlink("", "Plain label")
        assert result == "Plain label"

    def test_none_url_returns_plain_label(self):
        result = hyperlink(None, "Plain label")
        assert result == "Plain label"

    def test_none_label_returns_empty_hyperlink(self):
        result = hyperlink("https://example.com", None)
        assert result == '=HYPERLINK("https://example.com","")'

    def test_both_url_and_label_with_quotes(self):
        result = hyperlink('https://x.com/"path"', '"Title"')
        assert result == '=HYPERLINK("https://x.com/%22path%22","""Title""")'


# ---------------------------------------------------------------------------
# safe_str()
# ---------------------------------------------------------------------------

class TestSafeStr:
    def test_normal_string_unchanged(self):
        assert safe_str("hello") == "hello"

    def test_none_returns_empty(self):
        assert safe_str(None) == ""

    def test_leading_equals_prefixed(self):
        assert safe_str("=SUM(A1)") == "'=SUM(A1)"

    def test_leading_plus_prefixed(self):
        assert safe_str("+1234") == "'+1234"

    def test_leading_minus_prefixed(self):
        assert safe_str("-negative") == "'-negative"

    def test_leading_at_prefixed(self):
        assert safe_str("@mention") == "'@mention"

    def test_empty_string_unchanged(self):
        assert safe_str("") == ""

    def test_number_converted_to_string(self):
        assert safe_str(42) == "42"


# ---------------------------------------------------------------------------
# build_row() — Dashboard mode (use_status=True)
# ---------------------------------------------------------------------------

def _make_row(**overrides):
    """Create a FakeRow with sensible defaults for all columns used by build_row."""
    defaults = {
        "fingerprint": "abc123",
        "apply_flag": 0,
        "reject_reason": "",
        "fit_score": 7,
        "probability_score": 80,
        "relevance_score": 8,
        "title": "Software Engineer",
        "company": "Acme Corp",
        "location": "Remote",
        "remote_status": "remote",
        "known_contacts": "",
        "comp_estimate": "$150k",
        "ai_notes": "Good fit",
        "created_at": "2026-04-10",
        "source": "linkedin",
        "url": "https://example.com/job",
        "stage": "scored",
        "gdrive_folder_url": "",
        "prep_folder_path": "",
    }
    defaults.update(overrides)
    return FakeRow(defaults)


class TestBuildRowDashboard:
    """build_row with use_status=True (Dashboard mode)."""

    def test_materials_drafted_no_override_ready_to_apply(self):
        row = _make_row(stage="materials_drafted")
        result = build_row(row, DASH_HEADERS, DASH_LOOKUP, use_status=True)
        assert result[0] == "Ready to Apply"

    def test_scored_apply_flag_1_flag_for_prep(self):
        row = _make_row(stage="scored", apply_flag=1)
        result = build_row(row, DASH_HEADERS, DASH_LOOKUP, use_status=True)
        assert result[0] == "Flag for Prep"

    def test_scored_apply_flag_0_empty(self):
        row = _make_row(stage="scored", apply_flag=0)
        result = build_row(row, DASH_HEADERS, DASH_LOOKUP, use_status=True)
        assert result[0] == ""

    def test_status_override_used(self):
        row = _make_row(stage="scored", apply_flag=0)
        result = build_row(
            row, DASH_HEADERS, DASH_LOOKUP,
            status_override="Applied", use_status=True,
        )
        assert result[0] == "Applied"

    def test_reject_override_used(self):
        row = _make_row(reject_reason="")
        result = build_row(
            row, DASH_HEADERS, DASH_LOOKUP,
            reject_override="Low Fit Score", use_status=True,
        )
        # REJECT_REASON is at index 1 in DASH_HEADERS
        assert result[1] == "Low Fit Score"

    def test_reject_override_none_falls_back_to_db(self):
        row = _make_row(reject_reason="Wrong Level")
        result = build_row(row, DASH_HEADERS, DASH_LOOKUP, use_status=True)
        assert result[1] == "Wrong Level"

    def test_prep_in_progress_shows_prep_in_progress(self):
        row = _make_row(stage="prep_in_progress")
        result = build_row(row, DASH_HEADERS, DASH_LOOKUP, use_status=True)
        assert result[0] == "Prep in Progress"

    def test_prep_in_progress_apply_flag_1_still_shows_prep_in_progress(self):
        """apply_flag=1 should NOT override stage-derived status."""
        row = _make_row(stage="prep_in_progress", apply_flag=1)
        result = build_row(row, DASH_HEADERS, DASH_LOOKUP, use_status=True)
        assert result[0] == "Prep in Progress"


# ---------------------------------------------------------------------------
# build_row() — Sheet1 mode (use_status=False)
# ---------------------------------------------------------------------------

class TestBuildRowSheet1:
    """build_row with use_status=False (Sheet1 mode)."""

    def test_apply_flag_1_true(self):
        row = _make_row(apply_flag=1)
        result = build_row(row, S1_HEADERS, S1_LOOKUP, use_status=False)
        # APPLY_FLAG is at index 1 in S1_HEADERS
        assert result[1] == "TRUE"

    def test_apply_flag_0_false(self):
        row = _make_row(apply_flag=0)
        result = build_row(row, S1_HEADERS, S1_LOOKUP, use_status=False)
        assert result[1] == "FALSE"


# ---------------------------------------------------------------------------
# Dashboard company hyperlink logic (replicating sync_dashboard conditional)
# ---------------------------------------------------------------------------

def _company_cell(row):
    """Replicate the sync_dashboard conditional for company hyperlink."""
    gdrive_url = row["gdrive_folder_url"] if "gdrive_folder_url" in row.keys() else None
    if row["stage"] == "materials_drafted" and gdrive_url and str(gdrive_url).startswith("http"):
        return hyperlink(gdrive_url, row["company"])
    return safe_str(row["company"])


class TestDashboardCompanyHyperlink:
    def test_materials_drafted_with_gdrive_url(self):
        row = _make_row(
            stage="materials_drafted",
            gdrive_folder_url="https://drive.google.com/folder/xyz",
            company="Acme Corp",
        )
        result = _company_cell(row)
        assert result == '=HYPERLINK("https://drive.google.com/folder/xyz","Acme Corp")'

    def test_materials_drafted_no_gdrive_url(self):
        row = _make_row(
            stage="materials_drafted",
            gdrive_folder_url="",
            company="Acme Corp",
        )
        result = _company_cell(row)
        assert result == "Acme Corp"

    def test_scored_with_gdrive_url_no_hyperlink(self):
        row = _make_row(
            stage="scored",
            gdrive_folder_url="https://drive.google.com/folder/xyz",
            company="Acme Corp",
        )
        result = _company_cell(row)
        assert result == "Acme Corp"


# ---------------------------------------------------------------------------
# Pending status preservation logic (replicating sync_dashboard)
# ---------------------------------------------------------------------------

def _resolve_pending(pending_status, stage):
    """Replicate the sync_dashboard pending-status override logic.

    Returns the status_override to pass to build_row (None means let build_row derive).
    """
    if pending_status and not (pending_status == "Flag for Prep" and stage == "materials_drafted"):
        return pending_status
    return None


class TestPendingStatusPreservation:
    def test_flag_for_prep_scored_preserved(self):
        override = _resolve_pending("Flag for Prep", "scored")
        assert override == "Flag for Prep"

    def test_flag_for_prep_materials_drafted_not_preserved(self):
        override = _resolve_pending("Flag for Prep", "materials_drafted")
        assert override is None

    def test_applied_preserved_regardless_of_stage(self):
        assert _resolve_pending("Applied", "scored") == "Applied"
        assert _resolve_pending("Applied", "materials_drafted") == "Applied"

    def test_empty_status_returns_none(self):
        # Empty string is falsy, so returns None
        assert _resolve_pending("", "scored") is None

    def test_waitlist_status_preserved(self):
        assert _resolve_pending("Waitlist", "scored") == "Waitlist"
