"""Unit tests for CompaniesHouseClient — graceful degradation & API calls."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.config import CompaniesHouseConfig
from src.tools.companies_house import CompaniesHouseClient


class TestCompaniesHouseAvailability:

    def test_not_available_without_key(self):
        config = CompaniesHouseConfig(api_key="")
        client = CompaniesHouseClient(config=config)
        assert client.is_available is False

    def test_available_with_key(self):
        config = CompaniesHouseConfig(api_key="test-key-123")
        client = CompaniesHouseClient(config=config)
        assert client.is_available is True


class TestCompaniesHouseEnrichTrust:

    @pytest.mark.asyncio
    async def test_enrich_skips_when_no_api_key(self):
        config = CompaniesHouseConfig(api_key="")
        client = CompaniesHouseClient(config=config)
        result = await client.enrich_trust("Harris Federation")
        assert result["status"] == "skipped"
        assert result["reason"] == "no_api_key"
        assert result["trust_name"] == "Harris Federation"

    @pytest.mark.asyncio
    async def test_enrich_not_found(self):
        config = CompaniesHouseConfig(api_key="test-key")
        client = CompaniesHouseClient(config=config)
        # Mock the search to return empty
        client.search_company = AsyncMock(return_value=[])
        result = await client.enrich_trust("Nonexistent Trust")
        assert result["status"] == "not_found"

    @pytest.mark.asyncio
    async def test_enrich_success(self):
        config = CompaniesHouseConfig(api_key="test-key")
        client = CompaniesHouseClient(config=config)

        # Mock all sub-calls
        client.search_company = AsyncMock(return_value=[
            {"company_number": "07827865", "title": "Harris Federation"}
        ])
        client.get_company_profile = AsyncMock(return_value={
            "company_status": "active",
            "sic_codes": ["85310"],
            "registered_office_address": {"locality": "London"},
            "accounts": {"last_accounts": {"period_end_on": "2024-03-31"}},
        })
        client.get_officers = AsyncMock(return_value=[
            {"name": "Jane Smith", "officer_role": "director", "appointed_on": "2020-01-01", "resigned_on": None},
            {"name": "Bob Former", "officer_role": "director", "appointed_on": "2018-01-01", "resigned_on": "2023-06-01"},
        ])
        client.get_filing_history = AsyncMock(return_value=[
            {"type": "AA", "description": "Annual accounts", "date": "2024-03-31"},
        ])

        result = await client.enrich_trust("Harris Federation")
        assert result["status"] == "enriched"
        assert result["company_number"] == "07827865"
        assert result["company_status"] == "active"
        assert result["active_officers_count"] == 1  # Only Jane is still active
        assert len(result["directors"]) == 1
        assert result["directors"][0]["name"] == "Jane Smith"


class TestCompaniesHouseClient:

    def test_client_property_creates_httpx_client(self):
        config = CompaniesHouseConfig(api_key="test-key")
        ch_client = CompaniesHouseClient(config=config)
        assert ch_client._client is None
        http_client = ch_client.client
        assert http_client is not None
        # Second access returns same instance
        assert ch_client.client is http_client

    def test_default_config(self):
        config = CompaniesHouseConfig(api_key="test-key")
        client = CompaniesHouseClient(config=config)
        assert "company-information.service.gov.uk" in client.base_url
