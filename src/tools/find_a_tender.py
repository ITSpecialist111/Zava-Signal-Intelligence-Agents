"""Find a Tender API client for procurement signal detection.

Monitors the UK Find a Tender service for Pipeline Notices,
Preliminary Market Engagement, and contract opportunities related
to HR, payroll, and shared services in the education sector.

Service: https://find-tender.service.gov.uk/
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Find a Tender doesn't have an official public API, but OJEU/FTS notices
# are available via the Contracts Finder API and the FTS OCDS feed.
CONTRACTS_FINDER_BASE = "https://www.contractsfinder.service.gov.uk/Published/Notices/OCDS/Search"


class FindATenderClient:
    """Client for monitoring UK public procurement notices.

    Uses the Contracts Finder API (OCDS format) as the primary data source,
    with keyword filtering for education-sector payroll/HR opportunities.
    """

    EDUCATION_KEYWORDS = [
        "payroll",
        "human resources",
        "HR system",
        "shared services",
        "academy trust",
        "multi-academy trust",
        "MAT",
        "education payroll",
        "staff management",
        "people management",
        "workforce management",
    ]

    SIGNAL_KEYWORDS = [
        "preliminary market engagement",
        "soft market testing",
        "pipeline notice",
        "prior information notice",
        "market consultation",
        "early engagement",
    ]

    def __init__(self):
        self._client: httpx.AsyncClient | None = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=30.0,
                headers={"Accept": "application/json"},
            )
        return self._client

    async def search_notices(
        self,
        keywords: list[str] | None = None,
        published_from: datetime | None = None,
        published_to: datetime | None = None,
        page: int = 1,
        size: int = 50,
    ) -> dict[str, Any]:
        """Search for published contract notices.

        Args:
            keywords: Search keywords. Defaults to education-sector terms.
            published_from: Start date filter. Defaults to last 7 days.
            published_to: End date filter. Defaults to today.
            page: Page number for pagination.
            size: Results per page.

        Returns:
            Search results with notice details.
        """
        if keywords is None:
            keywords = self.EDUCATION_KEYWORDS

        if published_from is None:
            published_from = datetime.utcnow() - timedelta(days=7)
        if published_to is None:
            published_to = datetime.utcnow()

        search_query = " OR ".join(f'"{kw}"' for kw in keywords)

        params = {
            "searchCriteria.keyword": search_query,
            "searchCriteria.publishedFrom": published_from.strftime("%d/%m/%Y"),
            "searchCriteria.publishedTo": published_to.strftime("%d/%m/%Y"),
            "page": page,
            "size": size,
        }

        logger.info("Contracts Finder: searching for education procurement notices")

        try:
            resp = await self.client.get(CONTRACTS_FINDER_BASE, params=params)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            logger.error("Contracts Finder search failed: %s", e)
            return {"error": str(e), "results": []}

    async def scan_for_signals(
        self,
        lookback_days: int = 7,
    ) -> list[dict[str, Any]]:
        """Scan for procurement signals in recent notices.

        Looks specifically for Preliminary Market Engagement,
        Soft Market Testing, and Pipeline Notices.

        Args:
            lookback_days: Number of days to look back.

        Returns:
            List of detected procurement signals.
        """
        signals: list[dict[str, Any]] = []

        # Search with signal-specific keywords
        results = await self.search_notices(
            keywords=self.SIGNAL_KEYWORDS + self.EDUCATION_KEYWORDS,
            published_from=datetime.utcnow() - timedelta(days=lookback_days),
        )

        releases = results.get("releases", [])
        for release in releases:
            tender = release.get("tender", {})
            buyer = release.get("buyer", {})

            title = tender.get("title", "").lower()
            description = tender.get("description", "").lower()
            combined_text = f"{title} {description}"

            # Check for signal keywords
            matching_signals = [
                kw for kw in self.SIGNAL_KEYWORDS
                if kw in combined_text
            ]

            if matching_signals:
                signals.append({
                    "notice_id": release.get("id"),
                    "title": tender.get("title"),
                    "description": tender.get("description", "")[:500],
                    "buyer_name": buyer.get("name"),
                    "published_date": release.get("date"),
                    "signal_keywords": matching_signals,
                    "url": f"https://find-tender.service.gov.uk/Notice/{release.get('id', '')}",
                    "procurement_method": tender.get("procurementMethod"),
                    "value": tender.get("value", {}),
                })

        logger.info("Found %d procurement signals in last %d days", len(signals), lookback_days)
        return signals

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
