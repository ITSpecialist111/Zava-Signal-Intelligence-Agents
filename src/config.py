"""Zava Market Intelligence - Configuration Management.

Single-Tenant Architecture
--------------------------
All Azure resources (AI Foundry, Playwright) and the Agent 365 identity
live under the same Entra ID tenant.  Configure via environment variables.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


# ---------------------------------------------------------------------------
# Tenant identity
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TenantConfig:
    """Single-tenant config — M365/Agent 365 + Azure infrastructure."""

    tenant_id: str = field(
        default_factory=lambda: os.environ.get(
            "AZURE_TENANT_ID",
            os.environ.get("A365_TENANT_ID", ""),
        )
    )
    subscription_id: str = field(
        default_factory=lambda: os.environ.get(
            "AZURE_SUBSCRIPTION_ID", ""
        )
    )
    client_id: str = field(
        default_factory=lambda: os.environ.get("AZURE_CLIENT_ID", "")
    )
    client_secret: str = field(
        default_factory=lambda: os.environ.get("AZURE_CLIENT_SECRET", "")
    )
    a365_client_id: str = field(
        default_factory=lambda: os.environ.get("A365_CLIENT_ID", "")
    )
    a365_client_secret: str = field(
        default_factory=lambda: os.environ.get("A365_CLIENT_SECRET", "")
    )


# Backwards-compatible aliases
HoskingTenantConfig = TenantConfig
ContosoTenantConfig = TenantConfig


# ---------------------------------------------------------------------------
# Service configs
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AzureAIConfig:
    """Azure AI Foundry configuration."""

    project_endpoint: str = field(
        default_factory=lambda: os.environ.get("AZURE_AI_PROJECT_ENDPOINT", "")
    )
    deployment_name: str = field(
        default_factory=lambda: os.environ.get(
            "AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME", "gpt-4o"
        )
    )


@dataclass(frozen=True)
class PlaywrightConfig:
    """Playwright configuration.

    mode='local'  — use direct Playwright (POC, no Azure dependency)
    mode='azure'  — use Azure Playwright Testing workspace
    """

    mode: str = field(
        default_factory=lambda: os.environ.get("PLAYWRIGHT_MODE", "local")
    )
    azure_connection_name: str = field(
        default_factory=lambda: os.environ.get(
            "AZURE_PLAYWRIGHT_CONNECTION_NAME", ""
        )
    )

    @property
    def is_local(self) -> bool:
        return self.mode == "local"


@dataclass(frozen=True)
class CompaniesHouseConfig:
    """UK Companies House API configuration."""

    api_key: str = field(
        default_factory=lambda: os.environ.get("COMPANIES_HOUSE_API_KEY", "")
    )
    base_url: str = field(
        default_factory=lambda: os.environ.get(
            "COMPANIES_HOUSE_BASE_URL",
            "https://api-sandbox.company-information.service.gov.uk",
        )
    )

    @property
    def is_available(self) -> bool:
        """True if an API key has been configured."""
        return bool(self.api_key)


@dataclass(frozen=True)
class SignalConfig:
    """Signal detection and routing configuration."""

    confidence_threshold: float = field(
        default_factory=lambda: float(
            os.environ.get("SIGNAL_CONFIDENCE_THRESHOLD", "0.8")
        )
    )
    sweep_cron: str = field(
        default_factory=lambda: os.environ.get(
            "SIGNAL_SWEEP_SCHEDULE_CRON", "0 7 * * 1-5"
        )
    )
    store_path: Path = field(
        default_factory=lambda: Path(
            os.environ.get("SIGNAL_STORE_PATH", "./data/signals.json")
        )
    )


@dataclass(frozen=True)
class BlobStorageConfig:
    """Azure Blob Storage configuration for report persistence."""

    account_url: str = field(
        default_factory=lambda: os.environ.get(
            "BLOB_STORAGE_ACCOUNT_URL",
            "",
        )
    )
    container_name: str = field(
        default_factory=lambda: os.environ.get(
            "BLOB_STORAGE_CONTAINER", "reports"
        )
    )
    sas_expiry_hours: int = field(
        default_factory=lambda: int(
            os.environ.get("BLOB_SAS_EXPIRY_HOURS", "48")
        )
    )

    @property
    def is_available(self) -> bool:
        """True if a storage account URL has been configured."""
        return bool(self.account_url)


@dataclass(frozen=True)
class OutputConfig:
    """Output delivery configuration."""

    teams_webhook_url: str = field(
        default_factory=lambda: os.environ.get("TEAMS_WEBHOOK_URL", "")
    )
    output_dir: Path = field(
        default_factory=lambda: Path(
            os.environ.get("REPORT_OUTPUT_PATH", "./data/reports")
        )
    )


# ---------------------------------------------------------------------------
# Root config
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AppConfig:
    """Root application configuration (single-tenant)."""

    tenant: TenantConfig = field(default_factory=TenantConfig)
    azure_ai: AzureAIConfig = field(default_factory=AzureAIConfig)
    playwright: PlaywrightConfig = field(default_factory=PlaywrightConfig)
    companies_house: CompaniesHouseConfig = field(
        default_factory=CompaniesHouseConfig
    )
    signal: SignalConfig = field(default_factory=SignalConfig)
    blob: BlobStorageConfig = field(default_factory=BlobStorageConfig)
    output: OutputConfig = field(default_factory=OutputConfig)

    @classmethod
    def from_env(cls) -> "AppConfig":
        """Load configuration from environment variables."""
        return cls()


def load_config() -> AppConfig:
    """Load application configuration from environment."""
    return AppConfig.from_env()
