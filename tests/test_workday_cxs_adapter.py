"""Unit tests for WorkdayCXSAdapter (#617)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from findajob.fetchers.adapters.workday_cxs import WorkdayCXSAdapter


@pytest.fixture
def feed_urls(tmp_path: Path):
    def _write(urls: list[str]) -> str:
        p = tmp_path / "feed_urls.txt"
        p.write_text("\n".join(urls) + "\n")
        return str(p)

    return _write


# ───────────────────── is_configured ─────────────────────


def test_is_configured_true_when_workday_url_present(feed_urls) -> None:
    adapter = WorkdayCXSAdapter(
        feed_urls_path=feed_urls(["https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite"])
    )
    assert adapter.is_configured() is True


def test_is_configured_false_when_no_workday_url(feed_urls) -> None:
    adapter = WorkdayCXSAdapter(feed_urls_path=feed_urls(["https://boards.greenhouse.io/anthropic"]))
    assert adapter.is_configured() is False


def test_is_configured_false_when_file_missing(tmp_path: Path) -> None:
    assert WorkdayCXSAdapter(feed_urls_path=str(tmp_path / "nope.txt")).is_configured() is False


# ───────────────────── tenant extraction ─────────────────────


class TestTenantExtraction:
    """Covers the per-tenant URL-shape variations observed across real Workday tenants
    in the #248 Phase 1 spike (NVIDIA / Salesforce / Citi)."""

    def test_canonical_url_shape(self, feed_urls) -> None:
        tenants = WorkdayCXSAdapter(
            feed_urls_path=feed_urls(["https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite"])
        )._parse_tenants()
        assert tenants == [("nvidia", "wd5", "NVIDIAExternalCareerSite")]

    def test_numeric_site_id(self, feed_urls) -> None:
        """Citi's site is literally '2' — not a vendor-named string."""
        tenants = WorkdayCXSAdapter(feed_urls_path=feed_urls(["https://citi.wd5.myworkdayjobs.com/2"]))._parse_tenants()
        assert tenants == [("citi", "wd5", "2")]

    def test_different_pods(self, feed_urls) -> None:
        """wd1, wd5, wd12 all observed in the wild — regex must accept any digits."""
        tenants = WorkdayCXSAdapter(
            feed_urls_path=feed_urls(
                [
                    "https://salesforce.wd12.myworkdayjobs.com/External_Career_Site",
                    "https://twilio.wd1.myworkdayjobs.com/twilio",
                ]
            )
        )._parse_tenants()
        assert tenants == [
            ("salesforce", "wd12", "External_Career_Site"),
            ("twilio", "wd1", "twilio"),
        ]

    def test_dedupes_same_tenant_site_pair(self, feed_urls) -> None:
        tenants = WorkdayCXSAdapter(
            feed_urls_path=feed_urls(
                [
                    "https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite",
                    "https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite",
                ]
            )
        )._parse_tenants()
        assert tenants == [("nvidia", "wd5", "NVIDIAExternalCareerSite")]

    def test_dedupes_when_pod_changes_but_tenant_site_same(self, feed_urls) -> None:
        """A tenant migrating wd5 → wd12 would otherwise double-count during the
        migration window; dedup key intentionally omits pod."""
        tenants = WorkdayCXSAdapter(
            feed_urls_path=feed_urls(
                [
                    "https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite",
                    "https://nvidia.wd12.myworkdayjobs.com/NVIDIAExternalCareerSite",
                ]
            )
        )._parse_tenants()
        assert tenants == [("nvidia", "wd5", "NVIDIAExternalCareerSite")]

    def test_ignores_non_workday_urls_and_comments(self, feed_urls) -> None:
        tenants = WorkdayCXSAdapter(
            feed_urls_path=feed_urls(
                [
                    "# Tier 1",
                    "https://boards.greenhouse.io/anthropic",
                    "https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite",
                    "https://jobs.lever.co/zoox",
                    "https://jobs.ashbyhq.com/openai",
                ]
            )
        )._parse_tenants()
        assert tenants == [("nvidia", "wd5", "NVIDIAExternalCareerSite")]


# ───────────────────── fetch() ─────────────────────


def _list_response(jobs: list[dict], total: int | None = None) -> MagicMock:
    resp = MagicMock(status_code=200)
    resp.json.return_value = {"jobPostings": jobs, "total": total if total is not None else len(jobs)}
    return resp


def _detail_response(info: dict) -> MagicMock:
    resp = MagicMock(status_code=200)
    resp.json.return_value = {"jobPostingInfo": info}
    return resp


def test_fetch_returns_normalized_rows(feed_urls) -> None:
    list_resp = _list_response(
        [
            {
                "title": "Senior Data Center Performance Engineer",
                "externalPath": "/job/US-CA-Santa-Clara/Senior-DC-Perf_JR2008808",
                "locationsText": "2 Locations",
                "postedOn": "Posted Today",
                "bulletFields": ["JR2008808"],
            }
        ]
    )
    detail_resp = _detail_response(
        {
            "title": "Senior Data Center Performance Engineer",
            "jobDescription": "<p>Help us build the future of computing.</p>",
            "location": "US, CA, Santa Clara",
            "jobReqId": "JR2008808",
            "externalUrl": "https://nvidia.wd5.myworkdayjobs.com/.../JR2008808",
        }
    )
    # Second list call returns empty → loop ends.
    empty_list = _list_response([])

    with (
        patch(
            "findajob.fetchers.adapters.workday_cxs.requests.post",
            side_effect=[list_resp, empty_list],
        ),
        patch(
            "findajob.fetchers.adapters.workday_cxs.requests.get",
            return_value=detail_resp,
        ),
        patch("findajob.fetchers.adapters.workday_cxs.time.sleep"),
    ):
        rows = WorkdayCXSAdapter(
            feed_urls_path=feed_urls(["https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite"])
        ).fetch([])

    assert len(rows) == 1
    row = rows[0]
    assert row["source"] == "workday_cxs"
    assert row["title"] == "Senior Data Center Performance Engineer"
    assert row["company"] == "nvidia"  # tenant slug fallback (matches Greenhouse pattern)
    assert "Santa Clara" in row["location"]
    # Raw HTML preserved at fetch time; downstream pipeline strips tags.
    assert "<p>" in row["description"]
    assert "future of computing" in row["description"]
    assert row["url"] == "https://nvidia.wd5.myworkdayjobs.com/.../JR2008808"


def test_fetch_skips_postings_with_missing_external_path(feed_urls) -> None:
    list_resp = _list_response(
        [
            {"title": "Bad row, no externalPath"},
            {"title": "Good row", "externalPath": "/job/X/JR1"},
        ]
    )
    detail_resp = _detail_response(
        {
            "title": "Good row",
            "jobDescription": "ok",
            "externalUrl": "u",
            "location": "loc",
        }
    )
    empty_list = _list_response([])

    with (
        patch(
            "findajob.fetchers.adapters.workday_cxs.requests.post",
            side_effect=[list_resp, empty_list],
        ),
        patch(
            "findajob.fetchers.adapters.workday_cxs.requests.get",
            return_value=detail_resp,
        ),
        patch("findajob.fetchers.adapters.workday_cxs.time.sleep"),
    ):
        rows = WorkdayCXSAdapter(
            feed_urls_path=feed_urls(["https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite"])
        ).fetch([])

    assert len(rows) == 1
    assert rows[0]["title"] == "Good row"


def test_fetch_skips_when_detail_404s(feed_urls) -> None:
    """A failing detail call drops the row — must not poison the whole tenant."""
    list_resp = _list_response([{"title": "T", "externalPath": "/job/X/JR1"}])
    bad_detail = MagicMock(status_code=404)
    empty_list = _list_response([])

    with (
        patch(
            "findajob.fetchers.adapters.workday_cxs.requests.post",
            side_effect=[list_resp, empty_list],
        ),
        patch(
            "findajob.fetchers.adapters.workday_cxs.requests.get",
            return_value=bad_detail,
        ),
        patch("findajob.fetchers.adapters.workday_cxs.time.sleep"),
    ):
        rows = WorkdayCXSAdapter(
            feed_urls_path=feed_urls(["https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite"])
        ).fetch([])
    assert rows == []


def test_fetch_breaks_on_list_non_200(feed_urls) -> None:
    """A 500 on the list endpoint terminates the tenant loop without partial output."""
    bad_list = MagicMock(status_code=500)
    with (
        patch(
            "findajob.fetchers.adapters.workday_cxs.requests.post",
            return_value=bad_list,
        ),
        patch("findajob.fetchers.adapters.workday_cxs.time.sleep"),
    ):
        rows = WorkdayCXSAdapter(
            feed_urls_path=feed_urls(["https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite"])
        ).fetch([])
    assert rows == []


def test_fetch_caps_at_per_tenant_cap(feed_urls, monkeypatch) -> None:
    """_PER_TENANT_CAP is the hard ceiling on per-tenant pagination.

    Override to a small value for fast test; verify the loop stops at the cap
    even when the list endpoint keeps returning full pages.
    """
    monkeypatch.setattr(WorkdayCXSAdapter, "_PER_TENANT_CAP", 40)
    monkeypatch.setattr(WorkdayCXSAdapter, "_PAGE_SIZE", 20)

    def _make_list_resp() -> MagicMock:
        return _list_response([{"title": f"T{i}", "externalPath": f"/job/X/JR{i}"} for i in range(20)])

    detail_resp = _detail_response({"title": "T", "jobDescription": "ok", "externalUrl": "u", "location": "loc"})

    # Pre-construct enough list responses; loop should consume exactly 2 (cap=40, page=20).
    list_responses = [_make_list_resp() for _ in range(10)]

    with (
        patch(
            "findajob.fetchers.adapters.workday_cxs.requests.post",
            side_effect=list_responses,
        ),
        patch(
            "findajob.fetchers.adapters.workday_cxs.requests.get",
            return_value=detail_resp,
        ),
        patch("findajob.fetchers.adapters.workday_cxs.time.sleep"),
    ):
        rows = WorkdayCXSAdapter(
            feed_urls_path=feed_urls(["https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite"])
        ).fetch([])

    # Cap=40, page=20 → 2 list iterations × 20 detail rows = 40 rows.
    assert len(rows) == 40


# ───────────────────── live_test() ─────────────────────


def test_live_test_success_bucket(feed_urls) -> None:
    fake = MagicMock(status_code=200)
    fake.json.return_value = {"total": 42, "jobPostings": [{"externalPath": "/job/X"}]}
    with patch("findajob.fetchers.adapters.workday_cxs.requests.post", return_value=fake):
        result = WorkdayCXSAdapter(
            feed_urls_path=feed_urls(["https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite"])
        ).live_test([])
    assert result.ok is True
    assert result.bucket == "success"
    assert result.per_query[0].count == 42


def test_live_test_zero_rows_bucket(feed_urls) -> None:
    fake = MagicMock(status_code=200)
    fake.json.return_value = {"total": 0, "jobPostings": []}
    with patch("findajob.fetchers.adapters.workday_cxs.requests.post", return_value=fake):
        result = WorkdayCXSAdapter(
            feed_urls_path=feed_urls(["https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite"])
        ).live_test([])
    assert result.ok is True
    assert result.bucket == "zero_rows"


def test_live_test_auth_bucket_on_404(feed_urls) -> None:
    """Workday is public — surface invalid (tenant, site) pairs as 'auth' so the
    onboarding form renders the same error card it does for RapidAPI 401/403."""
    fake = MagicMock(status_code=404)
    with patch("findajob.fetchers.adapters.workday_cxs.requests.post", return_value=fake):
        result = WorkdayCXSAdapter(feed_urls_path=feed_urls(["https://typo.wd5.myworkdayjobs.com/SomeSite"])).live_test(
            []
        )
    assert result.ok is False
    assert result.bucket == "auth"


def test_live_test_network_bucket(feed_urls) -> None:
    import requests as req

    with patch(
        "findajob.fetchers.adapters.workday_cxs.requests.post",
        side_effect=req.RequestException("dns fail"),
    ):
        result = WorkdayCXSAdapter(
            feed_urls_path=feed_urls(["https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite"])
        ).live_test([])
    assert result.ok is False
    assert result.bucket == "network"


def test_live_test_rate_limit_bucket(feed_urls) -> None:
    fake = MagicMock(status_code=429)
    with patch("findajob.fetchers.adapters.workday_cxs.requests.post", return_value=fake):
        result = WorkdayCXSAdapter(
            feed_urls_path=feed_urls(["https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite"])
        ).live_test([])
    assert result.ok is False
    assert result.bucket == "rate_limit"


def test_live_test_server_bucket_on_5xx(feed_urls) -> None:
    fake = MagicMock(status_code=502)
    with patch("findajob.fetchers.adapters.workday_cxs.requests.post", return_value=fake):
        result = WorkdayCXSAdapter(
            feed_urls_path=feed_urls(["https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite"])
        ).live_test([])
    assert result.ok is False
    assert result.bucket == "server"


def test_live_test_auth_bucket_when_no_tenants_configured(tmp_path: Path) -> None:
    result = WorkdayCXSAdapter(feed_urls_path=str(tmp_path / "nope.txt")).live_test([])
    assert result.ok is False
    assert result.bucket == "auth"
    assert "No Workday URLs" in (result.auth_error or "")
