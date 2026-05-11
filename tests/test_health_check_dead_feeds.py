"""Tests for the silent-feed-failure detection in findajob.notifications.health_check (#637).

The jobs_fetched event shape migrated around 2026-05-09→05-10: per-source counts
moved from top-level keys into a nested ``adapters: {...}`` dict. The dead-feed
detector must read from both shapes (new events have only adapters; old events
in the 7-day baseline window may still have top-level keys; some hybrid events
have both).
"""

from __future__ import annotations

from findajob.notifications.health_check import _extract_source_counts


class TestExtractSourceCounts:
    def test_new_shape_reads_adapters_dict(self):
        """Post-2026-05-10 events keep all per-source counts inside adapters: {}."""
        event = {
            "event": "jobs_fetched",
            "count": 7345,
            "adapters": {
                "jobs-api14": 102,
                "jobs-api14-indeed": 340,
                "jsearch": 153,
                "greenhouse": 4872,
                "ashby": 1543,
                "lever": 304,
                "gmail": 31,
            },
            "attempt": 1,
        }
        counts = _extract_source_counts(event)
        assert counts["greenhouse"] == 4872
        assert counts["ashby"] == 1543
        assert counts["lever"] == 304
        assert counts["gmail"] == 31
        assert counts["jobs-api14"] == 102

    def test_legacy_shape_reads_top_level_keys(self):
        """Pre-2026-05-04 events had top-level greenhouse/ashby/lever/jobsapi/gmail."""
        event = {
            "event": "jobs_fetched",
            "count": 7443,
            "greenhouse": 4694,
            "ashby": 1511,
            "lever": 320,
            "jobsapi": 249,
            "gmail": 669,
            "attempt": 1,
        }
        counts = _extract_source_counts(event)
        assert counts["greenhouse"] == 4694
        assert counts["ashby"] == 1511
        assert counts["lever"] == 320
        assert counts["jobsapi"] == 249
        assert counts["gmail"] == 669

    def test_hybrid_shape_takes_max(self):
        """Brief transitional window (2026-05-04→2026-05-09) had BOTH top-level + adapters."""
        event = {
            "event": "jobs_fetched",
            "count": 7158,
            "greenhouse": 4872,
            "ashby": 1535,
            "lever": 304,
            "adapters": {"jobs-api14": 83, "jobs-api14-indeed": 220, "jsearch": 106},
            "gmail": 38,
            "attempt": 1,
        }
        counts = _extract_source_counts(event)
        # Top-level legacy keys
        assert counts["greenhouse"] == 4872
        assert counts["ashby"] == 1535
        assert counts["lever"] == 304
        assert counts["gmail"] == 38
        # Adapters-only sources
        assert counts["jobs-api14"] == 83
        assert counts["jobs-api14-indeed"] == 220
        assert counts["jsearch"] == 106

    def test_missing_adapters_dict(self):
        """No adapters dict, no legacy keys → empty dict."""
        event = {"event": "jobs_fetched", "count": 0, "attempt": 1}
        assert _extract_source_counts(event) == {}

    def test_non_int_values_ignored(self):
        """Defensive: a malformed event with a non-int count is skipped."""
        event = {
            "event": "jobs_fetched",
            "adapters": {"greenhouse": "many", "ashby": 1000},
        }
        counts = _extract_source_counts(event)
        assert "greenhouse" not in counts
        assert counts["ashby"] == 1000


class TestDeadFeedDetection:
    """Integration: feed synthetic event lists through the detection logic."""

    def test_gmail_oscillation_does_not_flag(self):
        """gmail returns 0 in some runs, 30 in others — max-across-window must see the 30."""
        from findajob.notifications.health_check import _detect_dead_feeds

        window_25h = [
            {"event": "jobs_fetched", "adapters": {"gmail": 0}},
            {"event": "jobs_fetched", "adapters": {"gmail": 31}},  # this run had new mail
            {"event": "jobs_fetched", "adapters": {"gmail": 0}},
        ]
        week_7d = window_25h + [
            {"event": "jobs_fetched", "adapters": {"gmail": 950}},  # past peak in baseline
        ]
        dead = _detect_dead_feeds(window_25h, week_7d)
        assert "gmail" not in dead

    def test_truly_dead_feed_is_flagged(self):
        """Feed produced 4000+ jobs in baseline but 0 every run in 25h window → flagged."""
        from findajob.notifications.health_check import _detect_dead_feeds

        window_25h = [
            {"event": "jobs_fetched", "adapters": {"greenhouse": 0, "ashby": 1000}},
            {"event": "jobs_fetched", "adapters": {"greenhouse": 0, "ashby": 1000}},
        ]
        week_7d = window_25h + [
            {"event": "jobs_fetched", "adapters": {"greenhouse": 4872, "ashby": 1500}},
        ]
        dead = _detect_dead_feeds(window_25h, week_7d)
        assert "greenhouse" in dead
        assert "ashby" not in dead

    def test_dynamic_source_enumeration_covers_new_adapters(self):
        """Adapter names come from events — a new adapter is auto-covered."""
        from findajob.notifications.health_check import _detect_dead_feeds

        # workday-cxs (#617) is registered but not in any hardcoded list
        window_25h = [{"event": "jobs_fetched", "adapters": {"workday-cxs": 0}}]
        week_7d = window_25h + [{"event": "jobs_fetched", "adapters": {"workday-cxs": 50}}]
        dead = _detect_dead_feeds(window_25h, week_7d)
        assert "workday-cxs" in dead

    def test_legacy_only_events_in_baseline_still_work(self):
        """7-day baseline may include events older than 2026-05-10 (top-level shape only)."""
        from findajob.notifications.health_check import _detect_dead_feeds

        window_25h = [
            {"event": "jobs_fetched", "adapters": {"greenhouse": 0}},
        ]
        # Baseline events are entirely legacy-shape
        week_7d = window_25h + [
            {"event": "jobs_fetched", "greenhouse": 4694, "ashby": 1511},
            {"event": "jobs_fetched", "greenhouse": 4700, "ashby": 1500},
        ]
        dead = _detect_dead_feeds(window_25h, week_7d)
        # greenhouse was 0 today, baseline had 4694/4700 → dead
        assert "greenhouse" in dead
        # ashby never appeared in 25h window at all → not flagged
        # (only flag sources that had >0 in baseline AND ==0 in 25h)
        assert "ashby" not in dead
