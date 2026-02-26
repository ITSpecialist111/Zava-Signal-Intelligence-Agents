"""Enrichment Agent — Layer 2: Companies House enrichment and playbook mapping.

Once a signal is detected, this agent enriches it with financial data,
officer information, and maps it to the appropriate Zava sales playbook.

Ref: https://learn.microsoft.com/agent-framework/agents/tools/
"""

from __future__ import annotations

import logging

from agent_framework import Agent
from agent_framework.azure import AzureOpenAIResponsesClient
from azure.identity import DefaultAzureCredential

from src.config import AzureAIConfig
from src.models.signal import Signal, SignalStatus, ZavaPlaybook
from src.tools.companies_house import CompaniesHouseClient

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Playbook mapping rules
# ---------------------------------------------------------------------------

PLAYBOOK_RULES: dict[str, dict[str, ZavaPlaybook]] = {
    "STRUCTURAL_STRESS": {
        "HUB_AND_SPOKE": ZavaPlaybook.CONSOLIDATION_VALUE_PROP,
        "SHADOW_MERGER": ZavaPlaybook.CONSOLIDATION_VALUE_PROP,
        "FEDERATION_AGREEMENT": ZavaPlaybook.CONSOLIDATION_VALUE_PROP,
    },
    "COMPLIANCE_TRAP": {
        "EXECUTIVE_PAY_SCRUTINY": ZavaPlaybook.COMPLIANCE_SHIELD,
        "CYBER_RANSOM_BAN": ZavaPlaybook.RISK_MITIGATION,
        "FBIT_OUTLIER": ZavaPlaybook.COMPLIANCE_SHIELD,
    },
    "COMPETITOR_MOVEMENT": {
        "COMPETITOR_HIRING": ZavaPlaybook.DIGITAL_TRANSFORMATION,
        "COMPETITOR_CONTRACT_WIN": ZavaPlaybook.COST_OPTIMISATION,
        "COMPETITOR_GTM_PIVOT": ZavaPlaybook.DIGITAL_TRANSFORMATION,
    },
    "PROCUREMENT_SHIFT": {
        "PIPELINE_NOTICE": ZavaPlaybook.DIGITAL_TRANSFORMATION,
        "PRELIMINARY_MARKET_ENGAGEMENT": ZavaPlaybook.PROFESSIONALIZATION_PITCH,
        "SOFT_MARKET_TESTING": ZavaPlaybook.PROFESSIONALIZATION_PITCH,
    },
    "LEADERSHIP_CHANGE": {
        "NEW_CFO": ZavaPlaybook.PROFESSIONALIZATION_PITCH,
        "NEW_CEO": ZavaPlaybook.DIGITAL_TRANSFORMATION,
        "NEW_HR_DIRECTOR": ZavaPlaybook.CONSOLIDATION_VALUE_PROP,
        "HEAD_OF_SHARED_SERVICES": ZavaPlaybook.CONSOLIDATION_VALUE_PROP,
    },
}


ENRICHMENT_INSTRUCTIONS = """You are the Enrichment Analyst for Zava Market Intelligence.

Given a detected signal and Companies House data about a trust, your job is to:

1. Summarize the trust's financial health over the last 3 years.
2. Identify the key decision maker (CFO, CEO, or Head of HR/Shared Services).
3. Note any recent leadership changes from the officer records.
4. Determine the recommended Zava sales playbook based on the signal type.
5. Craft a specific, actionable recommendation for the Account Executive.
6. Note the relevant Academy Trust Handbook reference if applicable.
7. Write a concise IMPACT STATEMENT (2-3 sentences) explaining WHY this signal
   matters to Zava — how it creates a sales opportunity, a competitive threat,
   or a timing advantage. This is the "so what" narrative.
8. Write a brief TALK TRACK (2-3 sentences) — a ready-made opener the AE can
   use when reaching out to the trust. It should reference the signal without
   revealing intelligence sources.

Be concise and actionable. The AE needs to act on this within 24 hours.

Return your response in this exact format:
FINANCIAL_SUMMARY: <summary>
RECOMMENDED_ACTION: <action>
HANDBOOK_REF: <reference or "None">
IMPACT_STATEMENT: <why this matters to Zava>
TALK_TRACK: <what to say to the prospect>
"""


async def create_enrichment_agent(
    ai_config: AzureAIConfig | None = None,
) -> Agent:
    """Create the Enrichment agent using Agent Framework."""
    cfg = ai_config or AzureAIConfig()
    credential = DefaultAzureCredential()
    client = AzureOpenAIResponsesClient(
        endpoint=cfg.project_endpoint,
        deployment_name=cfg.deployment_name,
        credential=credential,
    )

    return client.as_agent(
        name="EnrichmentAnalyst",
        instructions=ENRICHMENT_INSTRUCTIONS,
    )


async def enrich_signal(signal: Signal) -> Signal:
    """Enrich a signal with Companies House data and playbook mapping.

    Phase 1 (Automated): Pull financial and officer data.
    Phase 2 (Contextualization): Map to Zava playbook + "So What" message.

    Args:
        signal: The detected signal to enrich.

    Returns:
        The enriched signal with updated fields.
    """
    logger.info("Enriching signal %s for %s", signal.signal_id, signal.entity_name)

    # Phase 1: Companies House enrichment (skipped if no API key)
    ch_client = CompaniesHouseClient()
    try:
        enrichment_data = await ch_client.enrich_trust(signal.entity_name)
    finally:
        await ch_client.close()

    if enrichment_data.get("status") == "skipped":
        logger.info(
            "Companies House enrichment skipped for %s (no API key)",
            signal.entity_name,
        )
        enrichment_data = {}  # proceed without CH data

    if enrichment_data.get("status") == "enriched":
        signal.entity_id = enrichment_data.get("company_number")

        # Key decision maker
        directors = enrichment_data.get("directors", [])
        if directors:
            top_director = directors[0]
            signal.key_decision_maker = (
                f"{top_director.get('name', 'Unknown')} "
                f"({top_director.get('role', 'Director')})"
            )

        # Recent filing summary
        filings = enrichment_data.get("recent_filings", [])
        if filings:
            filing_summary = "; ".join(
                f"{f.get('description', 'Filing')} ({f.get('date', 'unknown date')})"
                for f in filings[:3]
            )
            signal.recent_changes = filing_summary

    # Phase 2: Playbook mapping (rule-based for determinism)
    category_rules = PLAYBOOK_RULES.get(signal.category.value, {})
    playbook = category_rules.get(signal.subcategory.value)
    if playbook:
        signal.playbook_match = playbook

    # Phase 2b: Use LLM for contextual recommendation
    agent = await create_enrichment_agent()
    enrichment_prompt = (
        f"Signal detected for {signal.entity_name}:\n"
        f"Category: {signal.category.value}\n"
        f"Subcategory: {signal.subcategory.value}\n"
        f"Evidence: {signal.raw_evidence}\n"
        f"Playbook: {playbook.value if playbook else 'TBD'}\n"
        f"Companies House data: {enrichment_data}\n\n"
        f"Provide: 1) Financial health summary, 2) Recommended action for AE, "
        f"3) Relevant handbook reference. Be concise."
    )

    result = await agent.run(enrichment_prompt)
    if result and result.text:
        text = result.text

        # Parse structured fields from LLM response
        def _extract_field(label: str, fallback: str = "") -> str:
            """Extract a labelled field from the LLM response text."""
            import re
            pattern = rf"{label}:\s*(.+?)(?:\n[A-Z_]+:|$)"
            match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
            return match.group(1).strip() if match else fallback

        signal.financial_summary = _extract_field("FINANCIAL_SUMMARY", text[:500])
        signal.recommended_action = _extract_field("RECOMMENDED_ACTION", "Review enrichment data")
        signal.impact_statement = _extract_field("IMPACT_STATEMENT")
        signal.talk_track = _extract_field("TALK_TRACK")

        handbook_ref = _extract_field("HANDBOOK_REF")
        if handbook_ref and handbook_ref.lower() != "none":
            signal.handbook_reference = handbook_ref

        # Fallbacks if structured parsing missed
        if not signal.recommended_action or signal.recommended_action == "Review enrichment data":
            lines = text.split("\n")
            for line in lines:
                if "recommend" in line.lower() or "action" in line.lower():
                    signal.recommended_action = line.strip()[:200]
                    break

        if not signal.impact_statement:
            signal.impact_statement = (
                f"Signal detected for {signal.entity_name} in category "
                f"{signal.category.value} — review for potential opportunity."
            )

    signal.status = SignalStatus.ENRICHED
    logger.info("Enrichment complete for %s (playbook: %s)", signal.entity_name, playbook)

    return signal
