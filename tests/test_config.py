"""Unit tests for configuration management."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from src.config import (
    AppConfig,
    AzureAIConfig,
    CompaniesHouseConfig,
    OutputConfig,
    PlaywrightConfig,
    SignalConfig,
    TenantConfig,
    load_config,
)


class TestTenantConfig:

    def test_defaults(self):
        with patch.dict(os.environ, {}, clear=True):
            cfg = TenantConfig()
        assert cfg.tenant_id == ""
        assert cfg.subscription_id == ""
        assert cfg.client_id == ""
        assert cfg.client_secret == ""
        assert cfg.a365_client_id == ""
        assert cfg.a365_client_secret == ""

    def test_from_env(self):
        env = {
            "AZURE_TENANT_ID": "test-tenant",
            "AZURE_SUBSCRIPTION_ID": "test-sub",
            "AZURE_CLIENT_ID": "test-client",
            "AZURE_CLIENT_SECRET": "test-secret",
            "A365_CLIENT_ID": "a365-cid",
            "A365_CLIENT_SECRET": "a365-csec",
        }
        with patch.dict(os.environ, env, clear=True):
            cfg = TenantConfig()
        assert cfg.tenant_id == "test-tenant"
        assert cfg.subscription_id == "test-sub"
        assert cfg.client_id == "test-client"
        assert cfg.client_secret == "test-secret"
        assert cfg.a365_client_id == "a365-cid"
        assert cfg.a365_client_secret == "a365-csec"

    def test_a365_tenant_fallback(self):
        """A365_TENANT_ID is used when AZURE_TENANT_ID is not set."""
        env = {"A365_TENANT_ID": "fallback-tenant"}
        with patch.dict(os.environ, env, clear=True):
            cfg = TenantConfig()
        assert cfg.tenant_id == "fallback-tenant"

    def test_frozen(self):
        cfg = TenantConfig()
        with pytest.raises(AttributeError):
            cfg.tenant_id = "new-value"  # type: ignore[misc]


class TestAzureAIConfig:

    def test_defaults(self):
        with patch.dict(os.environ, {}, clear=True):
            cfg = AzureAIConfig()
        assert cfg.project_endpoint == ""
        assert cfg.deployment_name == "gpt-4o"

    def test_from_env(self):
        env = {
            "AZURE_AI_PROJECT_ENDPOINT": "https://test.azure.com",
            "AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME": "gpt-4o-mini",
        }
        with patch.dict(os.environ, env, clear=True):
            cfg = AzureAIConfig()
        assert cfg.project_endpoint == "https://test.azure.com"
        assert cfg.deployment_name == "gpt-4o-mini"


class TestPlaywrightConfig:

    def test_default_is_local(self):
        with patch.dict(os.environ, {}, clear=True):
            cfg = PlaywrightConfig()
        assert cfg.mode == "local"
        assert cfg.is_local is True

    def test_azure_mode(self):
        env = {
            "PLAYWRIGHT_MODE": "azure",
            "AZURE_PLAYWRIGHT_CONNECTION_NAME": "pw-connection",
        }
        with patch.dict(os.environ, env, clear=True):
            cfg = PlaywrightConfig()
        assert cfg.mode == "azure"
        assert cfg.is_local is False
        assert cfg.azure_connection_name == "pw-connection"


class TestCompaniesHouseConfig:

    def test_not_available_without_key(self):
        with patch.dict(os.environ, {}, clear=True):
            cfg = CompaniesHouseConfig()
        assert cfg.is_available is False

    def test_available_with_key(self):
        env = {"COMPANIES_HOUSE_API_KEY": "test-api-key-123"}
        with patch.dict(os.environ, env, clear=True):
            cfg = CompaniesHouseConfig()
        assert cfg.is_available is True
        assert cfg.api_key == "test-api-key-123"

    def test_base_url_default(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("COMPANIES_HOUSE_BASE_URL", None)
            cfg = CompaniesHouseConfig()
            assert cfg.base_url == "https://api-sandbox.company-information.service.gov.uk"

    def test_base_url_override(self):
        with patch.dict(os.environ, {"COMPANIES_HOUSE_BASE_URL": "https://api.company-information.service.gov.uk"}):
            cfg = CompaniesHouseConfig()
            assert cfg.base_url == "https://api.company-information.service.gov.uk"


class TestSignalConfig:

    def test_defaults(self):
        with patch.dict(os.environ, {}, clear=True):
            cfg = SignalConfig()
        assert cfg.confidence_threshold == 0.8
        assert cfg.sweep_cron == "0 7 * * 1-5"

    def test_custom_threshold(self):
        env = {"SIGNAL_CONFIDENCE_THRESHOLD": "0.6"}
        with patch.dict(os.environ, env, clear=True):
            cfg = SignalConfig()
        assert cfg.confidence_threshold == 0.6


class TestOutputConfig:

    def test_defaults(self):
        with patch.dict(os.environ, {}, clear=True):
            cfg = OutputConfig()
        assert cfg.teams_webhook_url == ""

    def test_webhook_from_env(self):
        env = {"TEAMS_WEBHOOK_URL": "https://webhook.example.com"}
        with patch.dict(os.environ, env, clear=True):
            cfg = OutputConfig()
        assert cfg.teams_webhook_url == "https://webhook.example.com"


class TestAppConfig:

    def test_from_env(self):
        cfg = AppConfig.from_env()
        assert isinstance(cfg.tenant, TenantConfig)
        assert isinstance(cfg.azure_ai, AzureAIConfig)
        assert isinstance(cfg.playwright, PlaywrightConfig)
        assert isinstance(cfg.companies_house, CompaniesHouseConfig)
        assert isinstance(cfg.signal, SignalConfig)
        assert isinstance(cfg.output, OutputConfig)

    def test_load_config_helper(self):
        cfg = load_config()
        assert isinstance(cfg, AppConfig)

    def test_frozen(self):
        cfg = AppConfig.from_env()
        with pytest.raises(AttributeError):
            cfg.tenant = TenantConfig()  # type: ignore[misc]
