"""Tests for scoring.py normalization and helpers."""

import json

import pytest

from findajob.scoring import _normalize_llm_output


class TestNormalizeLlmOutput:
    """Test _normalize_llm_output fixes common LLM output issues."""

    def _make_raw(self, **overrides):
        base = {
            "score_status": "scored",
            "relevance_score": 7,
            "interview_likelihood": 6,
            "strengths_alignment": "Good fit.",
            "industry_sector": "Technology",
            "comp_estimate": "$150k-200k",
            "ai_notes": "Solid match.",
            "score_flag_reason": None,
            "remote_status": "Remote",
        }
        base.update(overrides)
        return json.dumps(base)

    def test_passthrough_valid(self):
        raw = self._make_raw(remote_status="Remote")
        result = json.loads(_normalize_llm_output(raw))
        assert result["remote_status"] == "Remote"

    def test_remote_friendly_maps_to_remote(self):
        raw = self._make_raw(remote_status="Remote-Friendly")
        result = json.loads(_normalize_llm_output(raw))
        assert result["remote_status"] == "Remote"

    def test_remote_friendly_travel_maps_to_remote(self):
        raw = self._make_raw(remote_status="Remote-Friendly (Travel-Required)")
        result = json.loads(_normalize_llm_output(raw))
        assert result["remote_status"] == "Remote"

    def test_remote_friendly_travel_v2(self):
        raw = self._make_raw(remote_status="Remote-Friendly (Travel Required)")
        result = json.loads(_normalize_llm_output(raw))
        assert result["remote_status"] == "Remote"

    def test_hybrid_passthrough(self):
        raw = self._make_raw(remote_status="Hybrid")
        result = json.loads(_normalize_llm_output(raw))
        assert result["remote_status"] == "Hybrid"

    def test_hybrid_flexible(self):
        raw = self._make_raw(remote_status="Hybrid/Flexible")
        result = json.loads(_normalize_llm_output(raw))
        assert result["remote_status"] == "Hybrid"

    def test_onsite_passthrough(self):
        raw = self._make_raw(remote_status="Onsite")
        result = json.loads(_normalize_llm_output(raw))
        assert result["remote_status"] == "Onsite"

    def test_on_site_variant(self):
        raw = self._make_raw(remote_status="On-Site")
        result = json.loads(_normalize_llm_output(raw))
        assert result["remote_status"] == "Onsite"

    def test_in_office(self):
        raw = self._make_raw(remote_status="In-Office")
        result = json.loads(_normalize_llm_output(raw))
        assert result["remote_status"] == "Onsite"

    def test_unknown_passthrough(self):
        raw = self._make_raw(remote_status="Unknown")
        result = json.loads(_normalize_llm_output(raw))
        assert result["remote_status"] == "Unknown"

    def test_unrecognized_maps_to_unknown(self):
        raw = self._make_raw(remote_status="Flexible with Travel")
        result = json.loads(_normalize_llm_output(raw))
        assert result["remote_status"] == "Unknown"

    def test_clamp_negative_score(self):
        raw = self._make_raw(relevance_score=-1)
        result = json.loads(_normalize_llm_output(raw))
        assert result["relevance_score"] == 1

    def test_clamp_zero_score(self):
        raw = self._make_raw(relevance_score=0)
        result = json.loads(_normalize_llm_output(raw))
        assert result["relevance_score"] == 1

    def test_clamp_high_score(self):
        raw = self._make_raw(relevance_score=15)
        result = json.loads(_normalize_llm_output(raw))
        assert result["relevance_score"] == 10

    def test_clamp_interview_likelihood(self):
        raw = self._make_raw(interview_likelihood=-1)
        result = json.loads(_normalize_llm_output(raw))
        assert result["interview_likelihood"] == 1

    def test_invalid_json_passthrough(self):
        raw = "not valid json at all"
        assert _normalize_llm_output(raw) == raw

    def test_markdown_fenced(self):
        inner = self._make_raw(remote_status="Remote-Friendly")
        raw = f"```json\n{inner}\n```"
        result = json.loads(_normalize_llm_output(raw))
        assert result["remote_status"] == "Remote"

    def test_null_scores_untouched(self):
        raw = self._make_raw(relevance_score=None, interview_likelihood=None)
        result = json.loads(_normalize_llm_output(raw))
        assert result["relevance_score"] is None
        assert result["interview_likelihood"] is None
