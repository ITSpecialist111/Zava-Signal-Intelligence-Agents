"""Companies House API client for trust enrichment.

Uses the official Companies House REST API to pull financial data,
officer information, and filing history for academy trusts.

API docs: https://developer.company-information.service.gov.uk/
"""

from __future__ import annotations

import logging
import re
from typing import Any

import httpx

from src.config import CompaniesHouseConfig

logger = logging.getLogger(__name__)


class CompaniesHouseClient:
    """Client for the UK Companies House API.

    Gracefully degrades when no API key is configured —
    all methods return empty results instead of raising.
    """

    def __init__(self, config: CompaniesHouseConfig | None = None):
        self.config = config or CompaniesHouseConfig()
        self.base_url = self.config.base_url
        self._client: httpx.AsyncClient | None = None

    @property
    def is_available(self) -> bool:
        """True if an API key has been configured."""
        return self.config.is_available

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                auth=(self.config.api_key, ""),
                timeout=30.0,
                headers={"Accept": "application/json"},
            )
        return self._client

    async def search_company(self, query: str, items_per_page: int = 10) -> list[dict[str, Any]]:
        """Search for a company by name.

        Args:
            query: Company name or partial name (e.g., "Harris Federation").
            items_per_page: Max results to return.

        Returns:
            List of matching company records.
        """
        logger.info("Companies House: searching for '%s'", query)
        resp = await self.client.get(
            "/search/companies",
            params={"q": query, "items_per_page": items_per_page},
        )
        if resp.status_code == 401:
            logger.warning("Companies House: 401 Unauthorized — API key may be invalid or not yet active")
            return []
        resp.raise_for_status()
        data = resp.json()
        return data.get("items", [])

    async def get_company_profile(self, company_number: str) -> dict[str, Any]:
        """Get full company profile.

        Args:
            company_number: Companies House registration number.

        Returns:
            Company profile data including status, SIC codes, registered address.
        """
        logger.info("Companies House: fetching profile for %s", company_number)
        resp = await self.client.get(f"/company/{company_number}")
        if resp.status_code == 401:
            logger.warning("Companies House: 401 Unauthorized")
            return {}
        resp.raise_for_status()
        return resp.json()

    async def get_officers(self, company_number: str) -> list[dict[str, Any]]:
        """Get current officers (directors, secretaries) of a company.

        Useful for detecting leadership changes when compared over time.

        Args:
            company_number: Companies House registration number.

        Returns:
            List of officer records.
        """
        logger.info("Companies House: fetching officers for %s", company_number)
        resp = await self.client.get(f"/company/{company_number}/officers")
        if resp.status_code == 401:
            logger.warning("Companies House: 401 Unauthorized")
            return []
        resp.raise_for_status()
        data = resp.json()
        return data.get("items", [])

    async def get_filing_history(
        self, company_number: str, items_per_page: int = 25
    ) -> list[dict[str, Any]]:
        """Get recent filing history.

        Useful for detecting financial changes, auditor appointments,
        and structural reorganizations.

        Args:
            company_number: Companies House registration number.
            items_per_page: Number of filings to retrieve.

        Returns:
            List of filing records.
        """
        logger.info("Companies House: fetching filings for %s", company_number)
        resp = await self.client.get(
            f"/company/{company_number}/filing-history",
            params={"items_per_page": items_per_page},
        )
        if resp.status_code == 401:
            logger.warning("Companies House: 401 Unauthorized")
            return []
        resp.raise_for_status()
        data = resp.json()
        return data.get("items", [])

    async def get_accounts(self, company_number: str) -> dict[str, Any]:
        """Get latest accounts summary.

        Args:
            company_number: Companies House registration number.

        Returns:
            Accounts data including last accounts date, next due date.
        """
        profile = await self.get_company_profile(company_number)
        return profile.get("accounts", {})

    async def enrich_trust(self, trust_name: str) -> dict[str, Any]:
        """Full enrichment pipeline for a trust.

        Searches for the trust, retrieves profile, officers, and recent filings.
        Returns a consolidated enrichment record.

        Uses a multi-strategy search: tries the exact name first, then
        attempts to expand common abbreviations, and validates that the
        top result is actually relevant before using it.

        Args:
            trust_name: The name of the academy trust or MAT.

        Returns:
            Consolidated enrichment data.
        """
        if not self.is_available:
            logger.warning(
                "Companies House API key not configured — skipping enrichment for %s",
                trust_name,
            )
            return {"status": "skipped", "trust_name": trust_name, "reason": "no_api_key"}

        logger.info("Enriching trust: %s", trust_name)

        # Build a list of search queries to try (original + cleaned variants)
        queries = _build_search_queries(trust_name)

        best_match: dict[str, Any] | None = None
        for query in queries:
            results = await self.search_company(query)
            match = _pick_best_match(trust_name, query, results)
            if match is not None:
                best_match = match
                break

        if best_match is None:
            logger.warning(
                "Companies House: no relevant match for '%s' (tried %s)",
                trust_name,
                queries,
            )
            return {"status": "not_found", "trust_name": trust_name}

        company_number = best_match["company_number"]
        logger.info(
            "Companies House: matched '%s' → %s (#%s)",
            trust_name,
            best_match.get("title", "?"),
            company_number,
        )

        # Parallel enrichment
        profile = await self.get_company_profile(company_number)
        officers = await self.get_officers(company_number)
        filings = await self.get_filing_history(company_number)

        # Identify key decision makers
        active_officers = [
            o for o in officers if o.get("resigned_on") is None
        ]
        directors = [
            o for o in active_officers if "director" in o.get("officer_role", "").lower()
        ]

        return {
            "status": "enriched",
            "trust_name": trust_name,
            "company_number": company_number,
            "company_status": profile.get("company_status"),
            "sic_codes": profile.get("sic_codes", []),
            "registered_address": profile.get("registered_office_address", {}),
            "accounts": profile.get("accounts", {}),
            "active_officers_count": len(active_officers),
            "directors": [
                {
                    "name": d.get("name"),
                    "role": d.get("officer_role"),
                    "appointed_on": d.get("appointed_on"),
                }
                for d in directors[:5]
            ],
            "recent_filings": [
                {
                    "type": f.get("type"),
                    "description": f.get("description"),
                    "date": f.get("date"),
                }
                for f in filings[:10]
            ],
        }

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None


# ── Search helpers ────────────────────────────────────────────────────────

# Noise words stripped when comparing entity names to search results.
# Includes legal suffixes AND common sector descriptors that would
# otherwise create false Jaccard overlap (e.g. "think tank").
_NOISE = re.compile(
    r"\b(the|ltd|limited|plc|inc|incorporated|llp|cic|group|uk"
    r"|think|tank|academy|trust|mat|federation|multi)\b",
    re.IGNORECASE,
)
_WHITESPACE = re.compile(r"\s+")


def _normalise(name: str) -> str:
    """Lower-case, strip noise words and extra whitespace."""
    name = _NOISE.sub(" ", name.lower())
    return _WHITESPACE.sub(" ", name).strip()


def _tokens(name: str) -> set[str]:
    """Return significant word tokens from a normalised name."""
    return {w for w in _normalise(name).split() if len(w) > 1}


def _similarity(query_name: str, candidate_title: str) -> float:
    """Jaccard-like word overlap between the search name and a result title.

    Returns a score between 0.0 (no overlap) and 1.0 (identical tokens).
    """
    q = _tokens(query_name)
    c = _tokens(candidate_title)
    if not q or not c:
        return 0.0
    intersection = q & c
    union = q | c
    return len(intersection) / len(union)


# Minimum similarity score to accept a Companies House result
_MIN_SIMILARITY = 0.3


def _pick_best_match(
    original_name: str, query: str, results: list[dict[str, Any]]
) -> dict[str, Any] | None:
    """Return the best-matching result, or None if nothing relevant.

    Checks each result title against both the original entity name and
    the search query for word overlap.  Requires at least 30 % similarity.
    """
    if not results:
        return None

    best: dict[str, Any] | None = None
    best_score = 0.0

    for r in results[:5]:  # only check top 5 results
        title = r.get("title", "")
        score = max(
            _similarity(original_name, title),
            _similarity(query, title),
        )
        if score > best_score:
            best_score = score
            best = r

    if best_score < _MIN_SIMILARITY:
        logger.debug(
            "Companies House: best match '%s' scored %.2f (below threshold %.2f)",
            best.get("title", "?") if best else "?",
            best_score,
            _MIN_SIMILARITY,
        )
        return None

    logger.debug(
        "Companies House: picked '%s' (score=%.2f) for '%s'",
        best.get("title", "?") if best else "?",
        best_score,
        original_name,
    )
    return best


def _build_search_queries(trust_name: str) -> list[str]:
    """Build a list of search queries to try, in priority order.

    Strategy:
    1. Use the original name as-is.
    2. Strip common suffixes like 'think tank', 'academy trust', etc.
    3. If the name looks like an acronym (all-caps, ≤6 chars),
       skip it (acronyms rarely match in Companies House search).
    """
    queries: list[str] = [trust_name]
    cleaned = trust_name.strip()

    # Strip informal suffixes that won't be in the legal company name
    for suffix in [
        "think tank",
        "academy trust",
        "multi-academy trust",
        "multi academy trust",
        "trust",
        "MAT",
        "federation",
    ]:
        pattern = re.compile(re.escape(suffix), re.IGNORECASE)
        stripped = pattern.sub("", cleaned).strip()
        # Only add the stripped variant if it has enough substance to
        # produce a meaningful search.  Short / acronym-like remnants
        # (e.g. "EPI") match too many unrelated companies.
        if (
            stripped
            and stripped != cleaned
            and stripped not in queries
            and len(stripped) > 4
        ):
            queries.append(stripped)

    return queries

