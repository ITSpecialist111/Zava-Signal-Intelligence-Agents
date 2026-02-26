"""Signal Collector Agent — Layer 1: Web Crawling.

The primary signal collection agent that orchestrates Browser Automation
to sweep public-sector education websites for proxy signals. Uses the
Azure AI Foundry Browser Automation tool for resilient, semantic web navigation.

Ref: https://learn.microsoft.com/agent-framework/agents/
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
    SignalBatch,
    SignalCategory,
    SignalSubcategory,
)
from src.tools.browser_automation import BrowserAutomationWrapper

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Target sources for the Daily Public Sector Sweep
# ---------------------------------------------------------------------------

SWEEP_TARGETS = [
    {
        "name": "TES Magazine",
        "url": "https://www.tes.com/magazine/news",
        "signal_types": [
            "leadership_change",
            "merger_announcement",
            "shared_services",
            "restructure",
        ],
        "description": "UK education news — leadership changes and restructures",
    },
    {
        "name": "Gov.uk Academy Trust Handbook",
        "url": "https://www.gov.uk/guidance/academy-trust-handbook",
        "signal_types": [
            "compliance_update",
            "executive_pay",
            "financial_reporting",
        ],
        "description": "Official handbook updates — compliance and governance changes",
    },
    {
        "name": "Schools Week",
        "url": "https://schoolsweek.co.uk/",
        "signal_types": [
            "leadership_change",
            "MAT_growth",
            "merger_announcement",
            "federation",
        ],
        "description": "Education sector news — MAT movements and mergers",
    },
    {
        "name": "BESA Forum",
        "url": "https://www.besa.org.uk/news/",
        "signal_types": [
            "reporting_gaps",
            "procurement_trends",
            "technology_adoption",
        ],
        "description": "British Educational Suppliers Association — market trends",
    },
]


# ---------------------------------------------------------------------------
# Signal Collector Agent
# ---------------------------------------------------------------------------

COLLECTOR_INSTRUCTIONS = """You are the Signal Collector for Zava Market Intelligence.

Your role is to sweep public-sector education websites and identify "Proxy Signals"
— events that happen BEFORE a trust realizes they need new HR/payroll software.

You are looking for these specific signal categories:

## Structural Stress Signals
- "Hub-and-Spoke" Consolidation: Trusts moving from decentralized to centralized models.
  Look for: Job ads for "Trust-wide HR Director" or "Head of Shared Services"
- "Shadow" Mergers: "Strategic Partnerships" or "Federation Agreements"
  Look for: Two trusts "sharing a CEO" or "aligning back-office functions"

## Compliance Trap Signals
- Executive Pay Scrutiny: Trusts flagged as outliers or under pay review pressure
- Cyber-Ransom Ban & Cloud Migration: Trusts mentioning "Cloud Migration" or "Disaster Recovery"

## Leadership Changes
- New CFO from corporate background (signals professionalization)
- New CEO or executive appointments
- Head of Shared Services appointments

## Competitor Movement
- Competitor job postings in education sector
- Contract win announcements

For each signal found, provide:
1. Entity name (trust/MAT name)
2. Signal category and subcategory
3. Verbatim evidence text
4. Your confidence (0.0-1.0)
5. Source URL

Return results as structured JSON.
"""


async def create_signal_collector(
    ai_config: AzureAIConfig | None = None,
) -> Agent:
    """Create the Signal Collector agent using Agent Framework.

    Uses AzureOpenAIResponsesClient for GPT-4o inference with
    the Browser Automation tool for web navigation.
    """
    cfg = ai_config or AzureAIConfig()
    credential = DefaultAzureCredential()
    client = AzureOpenAIResponsesClient(
        endpoint=cfg.project_endpoint,
        deployment_name=cfg.deployment_name,
        credential=credential,
    )

    agent = client.as_agent(
        name="SignalCollector",
        instructions=COLLECTOR_INSTRUCTIONS,
    )

    return agent


async def run_sweep(targets: list[dict] | None = None) -> SignalBatch:
    """Execute a signal collection sweep across all targets.

    This is the primary entry point for the Daily Public Sector Sweep.
    It uses the Browser Automation tool to navigate each target site
    and extract potential signals.

    Args:
        targets: Override default sweep targets. Uses SWEEP_TARGETS if None.

    Returns:
        SignalBatch containing all detected signals.
    """
    targets = targets or SWEEP_TARGETS
    batch_id = str(uuid.uuid4())
    batch = SignalBatch(
        batch_id=batch_id,
        source="daily_sweep",
    )

    browser = BrowserAutomationWrapper()

    for target in targets:
        logger.info("Sweeping: %s (%s)", target["name"], target["url"])

        try:
            result = await browser.scan_for_signals(
                url=target["url"],
                signal_types=target["signal_types"],
            )

            batch.total_pages_scanned += 1

            if result["status"] == "success" and result["content"]:
                # The content is returned as structured text from the model.
                # In production, parse this into Signal objects using a
                # dedicated parsing agent or structured output.
                raw_signals = await _parse_raw_signals(
                    result["content"],
                    source_name=target["name"],
                    source_url=target["url"],
                )
                batch.signals.extend(raw_signals)
            elif result["status"] == "error":
                batch.errors.append(f"{target['name']}: {result.get('error', 'unknown')}")

        except Exception as e:
            logger.error("Sweep failed for %s: %s", target["name"], e)
            batch.errors.append(f"{target['name']}: {str(e)}")

    logger.info(
        "Sweep complete: %d signals detected from %d pages (%d errors)",
        len(batch.signals),
        batch.total_pages_scanned,
        len(batch.errors),
    )

    return batch


async def _parse_raw_signals(
    raw_content: str,
    source_name: str,
    source_url: str,
    ai_config: AzureAIConfig | None = None,
) -> list[Signal]:
    """Parse raw LLM output into structured Signal objects.

    Uses a secondary Agent Framework agent with structured output
    to convert the free-text extraction into validated Signal models.
    """
    cfg = ai_config or AzureAIConfig()
    credential = DefaultAzureCredential()
    client = AzureOpenAIResponsesClient(
        endpoint=cfg.project_endpoint,
        deployment_name=cfg.deployment_name,
        credential=credential,
    )

    parser_agent = client.as_agent(
        name="SignalParser",
        instructions=(
            "You parse raw website content into structured JSON signals for Zava Market Intelligence. "
            "Look for proxy signals in the text: leadership changes, mergers, shared services, "
            "restructures, compliance issues, competitor activity, procurement notices. "
            "For each signal found, return a JSON object with: "
            "entity_name (the trust/MAT name), "
            "category (STRUCTURAL_STRESS|COMPLIANCE_TRAP|COMPETITOR_MOVEMENT|PROCUREMENT_SHIFT|LEADERSHIP_CHANGE), "
            "subcategory (HUB_AND_SPOKE|SHADOW_MERGER|FEDERATION_AGREEMENT|EXECUTIVE_PAY_SCRUTINY|"
            "CYBER_RANSOM_BAN|FBIT_OUTLIER|COMPETITOR_HIRING|COMPETITOR_CONTRACT_WIN|COMPETITOR_GTM_PIVOT|"
            "PIPELINE_NOTICE|PRELIMINARY_MARKET_ENGAGEMENT|SOFT_MARKET_TESTING|NEW_CFO|NEW_CEO|NEW_HR_DIRECTOR|"
            "HEAD_OF_SHARED_SERVICES), "
            "confidence (0.0-1.0), evidence_text (verbatim excerpt). "
            "If no signals are found, return an empty array: []\n"
            "IMPORTANT: Return ONLY the raw JSON array. No markdown fences, no explanation."
        ),
    )

    result = await parser_agent.run(
        f"Parse these signals from {source_name} ({source_url}):\n\n{raw_content}"
    )

    # In production, use structured output / JSON mode for reliable parsing.
    # For now, attempt to parse the response text.
    signals: list[Signal] = []
    try:
        import json
        import re

        # Strip markdown code fences if present
        response_text = str(result)
        fence_match = re.search(r"```(?:json)?\s*\n?(.*?)```", response_text, re.DOTALL)
        if fence_match:
            response_text = fence_match.group(1).strip()

        parsed = json.loads(response_text)
        if isinstance(parsed, list):
            for item in parsed:
                confidence = float(item.get("confidence", 0.5))
                signal = Signal(
                    signal_id=str(uuid.uuid4()),
                    category=SignalCategory(item.get("category", "LEADERSHIP_CHANGE")),
                    subcategory=SignalSubcategory(item.get("subcategory", "NEW_CEO")),
                    entity_name=item.get("entity_name", "Unknown"),
                    confidence=confidence,
                    confidence_level=(
                        ConfidenceLevel.HIGH if confidence >= 0.8
                        else ConfidenceLevel.MEDIUM if confidence >= 0.5
                        else ConfidenceLevel.LOW
                    ),
                    source_url=source_url,
                    source_name=source_name,
                    raw_evidence=item.get("evidence_text", ""),
                    detected_at=datetime.utcnow(),
                )
                signals.append(signal)
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        logger.warning("Failed to parse signals from %s: %s", source_name, e)
        # Fallback: create a single signal with the raw content
        signals.append(
            Signal(
                signal_id=str(uuid.uuid4()),
                category=SignalCategory.LEADERSHIP_CHANGE,
                subcategory=SignalSubcategory.NEW_CEO,
                entity_name="PARSE_ERROR — manual review needed",
                confidence=0.3,
                confidence_level=ConfidenceLevel.LOW,
                source_url=source_url,
                source_name=source_name,
                raw_evidence=raw_content[:1000],
                detected_at=datetime.utcnow(),
            )
        )

    return signals
