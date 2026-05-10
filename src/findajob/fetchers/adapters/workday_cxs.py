"""WorkdayCXSAdapter — direct Workday CXS API ingestion (#617; spec from #248 Phase 1)."""

from __future__ import annotations

import html
import re
import time
from typing import ClassVar

import requests

from findajob.audit import log_event
from findajob.cleaning import clean_company, clean_title

from .base import LiveTestResult, QueryResult


class WorkdayCXSAdapter:
    """Workday CXS ingestion via the public per-tenant JSON API.

    Workday is a board-feed source (one feed per tenant+site, not query-search),
    so the ``queries`` parameter on ``fetch()`` is ignored. Tenants are parsed
    from ``config/feed_urls.txt`` as ``https://{tenant}.{pod}.myworkdayjobs.com/{site}``
    URLs. Each tenant requires:

      * 1 list POST per page of 20 (paginated up to ``_PER_TENANT_CAP``)
      * 1 detail GET per posting (for the JD body)

    Both endpoints are public — no API key, no warm-up GET, no CSRF token,
    no cookies. Standard payload returns 200 (#248 Phase 1 finding 2026-05-10).
    """

    name: ClassVar[str] = "workday-cxs"
    display_name: ClassVar[str] = "Workday CXS"
    source_label: ClassVar[str] = "workday_cxs"
    required_env_vars: ClassVar[tuple[str, ...]] = ()  # public API, no key

    _SLUG_RE: ClassVar[re.Pattern] = re.compile(r"https?://([^./?#]+)\.(wd\d+)\.myworkdayjobs\.com/([^/?#]+)")
    _LIST_TEMPLATE: ClassVar[str] = "https://{tenant}.{pod}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs"
    _DETAIL_TEMPLATE: ClassVar[str] = "https://{tenant}.{pod}.myworkdayjobs.com/wday/cxs/{tenant}/{site}{ext_path}"
    _PAGE_SIZE: ClassVar[int] = 20
    _PER_TENANT_CAP: ClassVar[int] = 500
    """Hard cap on per-tenant postings fetched per cycle.

    Workday returns up to 2000 postings per tenant; real active counts are
    usually 100-500. The cap keeps the daily triage cron bounded — a runaway
    tenant can't blow up wall-clock time. Tweakable via class attr if a
    specific tenant needs deeper coverage.
    """
    _UA: ClassVar[str] = "findajob-pipeline/1.0 (personal job search tool)"

    def __init__(self, feed_urls_path: str | None = None) -> None:
        if feed_urls_path is None:
            from findajob.paths import BASE

            feed_urls_path = f"{BASE}/config/feed_urls.txt"
        self._feed_urls_path = feed_urls_path

    def _parse_tenants(self) -> list[tuple[str, str, str]]:
        """Extract (tenant, pod, site) triples from feed_urls.txt.

        First-occurrence-wins on (tenant, site) — same tenant on multiple
        pods is rare in practice but the dedup key omits pod intentionally
        (a tenant moving wd5 → wd12 would otherwise double-count during
        the migration window).
        """
        try:
            with open(self._feed_urls_path) as f:
                urls = [line.strip() for line in f if line.strip() and not line.startswith("#")]
        except FileNotFoundError:
            return []
        seen: set[tuple[str, str]] = set()
        tenants: list[tuple[str, str, str]] = []
        for url in urls:
            m = self._SLUG_RE.search(url)
            if m:
                tenant, pod, site = m.group(1), m.group(2), m.group(3)
                key = (tenant, site)
                if key not in seen:
                    seen.add(key)
                    tenants.append((tenant, pod, site))
        return tenants

    def is_configured(self) -> bool:
        return bool(self._parse_tenants())

    def fetch(self, queries: list[str]) -> list[dict]:
        del queries  # board-feed source — query strings don't apply
        jobs: list[dict] = []
        for tenant, pod, site in self._parse_tenants():
            jobs.extend(self._fetch_tenant(tenant, pod, site))
        return jobs

    def _fetch_tenant(self, tenant: str, pod: str, site: str) -> list[dict]:
        list_url = self._LIST_TEMPLATE.format(tenant=tenant, pod=pod, site=site)
        list_headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": self._UA,
        }
        detail_headers = {"Accept": "application/json", "User-Agent": self._UA}
        company = clean_company(tenant)
        rows: list[dict] = []
        offset = 0
        while offset < self._PER_TENANT_CAP:
            payload = {
                "appliedFacets": {},
                "limit": self._PAGE_SIZE,
                "offset": offset,
                "searchText": "",
            }
            try:
                resp = requests.post(list_url, json=payload, headers=list_headers, timeout=15)
            except Exception as e:  # noqa: BLE001 — broad except matches Greenhouse pattern
                log_event("workday_cxs_list_error", tenant=tenant, site=site, error=str(e))
                break
            if resp.status_code != 200:
                log_event(
                    "workday_cxs_list_skip",
                    tenant=tenant,
                    site=site,
                    status=resp.status_code,
                )
                break
            try:
                payload_resp = resp.json()
            except ValueError:
                log_event("workday_cxs_invalid_json", tenant=tenant, site=site)
                break
            postings = payload_resp.get("jobPostings", [])
            if not postings:
                break
            for posting in postings:
                ext_path = posting.get("externalPath", "")
                if not ext_path:
                    continue
                detail = self._fetch_detail(tenant, pod, site, ext_path, detail_headers)
                if detail is None:
                    continue
                info = detail.get("jobPostingInfo", {}) or {}
                rows.append(
                    {
                        "title": clean_title(info.get("title") or posting.get("title", "")),
                        "company": company,
                        "url": info.get("externalUrl", "") or list_url,
                        "location": info.get("location", "") or posting.get("locationsText", ""),
                        "source": self.source_label,
                        "description": html.unescape(info.get("jobDescription", "") or ""),
                    }
                )
                time.sleep(0.5)  # 2 req/sec budget; Phase 1 observed no 429 at 1 req/sec
            offset += self._PAGE_SIZE
            if len(postings) < self._PAGE_SIZE:
                break
            time.sleep(0.3)
        log_event("workday_cxs_fetch", tenant=tenant, site=site, count=len(rows))
        return rows

    def _fetch_detail(
        self,
        tenant: str,
        pod: str,
        site: str,
        ext_path: str,
        headers: dict,
    ) -> dict | None:
        detail_url = self._DETAIL_TEMPLATE.format(tenant=tenant, pod=pod, site=site, ext_path=ext_path)
        try:
            resp = requests.get(detail_url, headers=headers, timeout=15)
        except Exception as e:  # noqa: BLE001
            log_event("workday_cxs_detail_error", tenant=tenant, ext_path=ext_path, error=str(e))
            return None
        if resp.status_code != 200:
            log_event(
                "workday_cxs_detail_skip",
                tenant=tenant,
                ext_path=ext_path,
                status=resp.status_code,
            )
            return None
        try:
            return resp.json()
        except ValueError:
            return None

    def live_test(self, queries: list[str]) -> LiveTestResult:
        del queries
        tenants = self._parse_tenants()
        if not tenants:
            return LiveTestResult(
                ok=False,
                bucket="auth",
                per_query=[],
                auth_error="No Workday URLs configured in feed_urls.txt.",
            )
        tenant, pod, site = tenants[0]
        list_url = self._LIST_TEMPLATE.format(tenant=tenant, pod=pod, site=site)
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": self._UA,
        }
        payload = {"appliedFacets": {}, "limit": 5, "offset": 0, "searchText": ""}
        try:
            resp = requests.post(list_url, json=payload, headers=headers, timeout=15)
        except requests.RequestException as e:
            return LiveTestResult(ok=False, bucket="network", per_query=[], auth_error=str(e))
        if resp.status_code == 404:
            return LiveTestResult(
                ok=False,
                bucket="auth",
                per_query=[],
                auth_error=f"Tenant '{tenant}/{site}' returned 404 — not a valid Workday CXS tenant.",
            )
        if resp.status_code == 429:
            return LiveTestResult(
                ok=False,
                bucket="rate_limit",
                per_query=[],
                auth_error="Rate limited.",
            )
        if 500 <= resp.status_code < 600:
            return LiveTestResult(
                ok=False,
                bucket="server",
                per_query=[],
                auth_error=f"HTTP {resp.status_code}: server error.",
            )
        if resp.status_code != 200:
            return LiveTestResult(
                ok=False,
                bucket="auth",
                per_query=[],
                auth_error=f"HTTP {resp.status_code}: unexpected response.",
            )
        try:
            count = int(resp.json().get("total", 0))
        except (ValueError, TypeError):
            return LiveTestResult(
                ok=False,
                bucket="server",
                per_query=[],
                auth_error="Invalid JSON response.",
            )
        per_query = [QueryResult(query=f"{tenant}/{site}", count=count)]
        if count > 0:
            return LiveTestResult(ok=True, bucket="success", per_query=per_query, auth_error=None)
        return LiveTestResult(ok=True, bucket="zero_rows", per_query=per_query, auth_error=None)
