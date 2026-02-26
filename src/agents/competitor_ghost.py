"""Competitor Ghost Agent — monitors competitor activity.

Tracks competitor job boards, press releases, and contract wins
to detect GTM pivots, regional expansion, and market movements.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime

from agent_framework import Agent
from agent_framework.azure import AzureOpenAIResponsesClient
from azure.identity import DefaultAzureCredential

from src.config import AzureAIConfig
from src.models.signal import (
    ConfidenceLevel,
    Signal,
    SignalCategory,
    SignalSubcategory,
)
from src.tools.browser_automation import BrowserAutomationWrapper

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Competitor targets
# ---------------------------------------------------------------------------

COMPETITORS = [
    {
        "name": "Competitor A",
        "job_board_url": "https://www.digitalmarketplace.service.gov.uk/g-cloud/search?q=education+payroll&lot=cloud-software",
        "description": "Monitor GOV.UK Digital Marketplace for education payroll service listings",
    },
    {
        "name": "Competitor B",
        "job_board_url": "https://www.indeed.co.uk/jobs?q=education+implementation+consultant",
        "description": "Monitor for implementation consultant hiring (contract win indicator)",
    },
]

COMPETITOR_INSTRUCTIONS = """You are the Competitor Ghost Agent for Zava Market Intelligence.

Your job is to monitor competitor activity in the UK education payroll/HR market.
You look for these specific signals:

1. SERVICE LISTINGS: If a competitor has new or updated listings on the GOV.UK
   Digital Marketplace for education payroll/HR services, they may be targeting
   new academy trust contracts or expanding their public sector footprint.

2. CONTRACT WINS: Press releases or news about competitors winning contracts
   with academy trusts or MATs.

3. GTM PIVOTS: Changes in competitor messaging, new product announcements,
   or strategic pivots toward specific segments (e.g., cybersecurity, compliance).

4. HIRING PATTERNS: If a competitor is hiring multiple "Education Implementation
   Consultants" or "Public Sector Payroll Specialists" in a specific region,
   they've likely just won a contract or are pivoting their GTM.

For each finding, extract:
- Competitor name
- What they're doing (hiring/winning/pivoting)
- Region affected
- Estimated impact on Zava
- Confidence (0.0-1.0)

Return structured JSON.
"""


async def create_competitor_agent(
    ai_config: AzureAIConfig | None = None,
) -> Agent:
    """Create the Competitor Ghost agent."""
    cfg = ai_config or AzureAIConfig()
    credential = DefaultAzureCredential()
    client = AzureOpenAIResponsesClient(
        endpoint=cfg.project_endpoint,
        deployment_name=cfg.deployment_name,
        credential=credential,
    )

    return client.as_agent(
        name="CompetitorGhost",
        instructions=COMPETITOR_INSTRUCTIONS,
    )


async def scan_competitors() -> list[Signal]:
    """Scan competitor job boards and news for movement signals.

    Returns:
        List of competitor movement signals.
    """
    browser = BrowserAutomationWrapper()
    signals: list[Signal] = []

    for competitor in COMPETITORS:
        logger.info("Scanning competitor: %s", competitor["name"])

        try:
            result = await browser.scan_for_signals(
                url=competitor["job_board_url"],
                signal_types=["hiring_pattern", "contract_win", "gtm_pivot"],
            )

            if result["status"] == "success" and result["content"]:
                # Create signal for each detected competitor movement
                signal = Signal(
                    signal_id=str(uuid.uuid4()),
                    category=SignalCategory.COMPETITOR_MOVEMENT,
                    subcategory=SignalSubcategory.COMPETITOR_HIRING,
                    entity_name=competitor["name"],
                    confidence=0.6,
                    confidence_level=ConfidenceLevel.MEDIUM,
                    source_url=competitor["job_board_url"],
                    source_name=f"{competitor['name']} Job Board",
                    raw_evidence=result["content"][:1000],
                    detected_at=datetime.utcnow(),
                )
                signals.append(signal)

        except Exception as e:
            logger.error("Competitor scan failed for %s: %s", competitor["name"], e)

    logger.info("Competitor scan complete: %d signals detected", len(signals))
    return signals
