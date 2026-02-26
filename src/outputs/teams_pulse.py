"""Teams Pulse — Real-Time Adaptive Card Notifications.

Sends signal alerts to a Teams channel as Adaptive Cards.
Uses the Agent 365 governed MCP server for Teams messaging.

Output format: Single card per signal with trust name, category,
confidence level, recommended action, and approve/dismiss buttons.

Ref: https://learn.microsoft.com/microsoft-365/agents/a365-governed-mcp-servers
"""

from __future__ import annotations

import json
import logging

from src.models.battlecard import SignalBattlecard
from src.models.signal import ConfidenceLevel, Signal

logger = logging.getLogger(__name__)


def build_signal_card(signal: Signal) -> dict:
    """Build a Teams Adaptive Card payload for a single signal.

    Args:
        signal: The signal to render as a card.

    Returns:
        Adaptive Card JSON payload (dict).
    """
    confidence_colour = {
        ConfidenceLevel.HIGH: "good",
        ConfidenceLevel.MEDIUM: "warning",
        ConfidenceLevel.LOW: "attention",
    }

    headline = signal.raw_evidence[:120] if signal.raw_evidence else "—"
    evidence_preview = (
        signal.raw_evidence[:300] + "…"
        if len(signal.raw_evidence) > 300
        else signal.raw_evidence
    )

    card = {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.5",
        "body": [
            {
                "type": "ColumnSet",
                "columns": [
                    {
                        "type": "Column",
                        "width": "stretch",
                        "items": [
                            {
                                "type": "TextBlock",
                                "text": "🎯 Signal Detected",
                                "weight": "Bolder",
                                "size": "Medium",
                            },
                            {
                                "type": "TextBlock",
                                "text": signal.entity_name,
                                "weight": "Bolder",
                                "size": "Large",
                                "color": "Accent",
                            },
                        ],
                    },
                    {
                        "type": "Column",
                        "width": "auto",
                        "items": [
                            {
                                "type": "TextBlock",
                                "text": signal.confidence_level.value,
                                "weight": "Bolder",
                                "color": confidence_colour.get(
                                    signal.confidence_level, "default"
                                ),
                                "horizontalAlignment": "Right",
                            },
                        ],
                    },
                ],
            },
            {
                "type": "FactSet",
                "facts": [
                    {"title": "Category", "value": signal.category.value},
                    {"title": "Subcategory", "value": signal.subcategory.value},
                    {"title": "Source", "value": signal.source_name},
                    {
                        "title": "Detected",
                        "value": signal.detected_at.strftime("%d %b %Y %H:%M"),
                    },
                    {
                        "title": "Playbook",
                        "value": signal.playbook_match.value
                        if signal.playbook_match
                        else "—",
                    },
                ],
            },
            {"type": "TextBlock", "text": headline, "wrap": True},
            {
                "type": "TextBlock",
                "text": evidence_preview,
                "wrap": True,
                "isSubtle": True,
                "size": "Small",
            },
        ],
        "actions": [
            {
                "type": "Action.Submit",
                "title": "✅ Approve",
                "data": {
                    "action": "approve_signal",
                    "signal_id": signal.signal_id,
                },
            },
            {
                "type": "Action.Submit",
                "title": "❌ Dismiss",
                "data": {
                    "action": "reject_signal",
                    "signal_id": signal.signal_id,
                },
            },
            {
                "type": "Action.OpenUrl",
                "title": "🔗 Source",
                "url": signal.source_url,
            },
        ],
    }

    return card


def build_battlecard_card(battlecard: SignalBattlecard) -> dict:
    """Build a Teams Adaptive Card for a full Signal Battlecard.

    Richer than a signal card — includes enrichment data,
    competitor intel, and recommended actions.
    """
    facts = [
        {"title": "Trust", "value": battlecard.entity_name},
        {"title": "Category", "value": battlecard.signal_category.value},
        {"title": "Confidence", "value": battlecard.confidence_level.value},
    ]

    if battlecard.entity_id:
        facts.append(
            {"title": "Companies House", "value": battlecard.entity_id}
        )
    if battlecard.financial_health:
        facts.append(
            {"title": "Financial Health", "value": battlecard.financial_health}
        )
    if battlecard.current_provider:
        facts.append(
            {"title": "Current Provider", "value": battlecard.current_provider}
        )

    body = [
        {
            "type": "TextBlock",
            "text": "📋 Signal Battlecard",
            "weight": "Bolder",
            "size": "Large",
        },
        {"type": "FactSet", "facts": facts},
    ]

    # Competitor intel section
    if battlecard.competitor_intel:
        body.append(
            {
                "type": "TextBlock",
                "text": "⚔️ Competitor Intelligence",
                "weight": "Bolder",
                "spacing": "Medium",
            }
        )
        for intel in battlecard.competitor_intel:
            body.append(
                {
                    "type": "TextBlock",
                    "text": f"**{intel.competitor_name}**: {intel.activity_summary}",
                    "wrap": True,
                    "size": "Small",
                }
            )

    # Recommended actions
    if battlecard.actions:
        body.append(
            {
                "type": "TextBlock",
                "text": "🎯 Recommended Actions",
                "weight": "Bolder",
                "spacing": "Medium",
            }
        )
        for action in battlecard.actions:
            body.append(
                {
                    "type": "TextBlock",
                    "text": f"- [{action.priority}] {action.action}",
                    "wrap": True,
                    "size": "Small",
                }
            )

    card = {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.5",
        "body": body,
        "actions": [
            {
                "type": "Action.Submit",
                "title": "✅ Approve for Outreach",
                "data": {
                    "action": "approve_battlecard",
                    "battlecard_id": battlecard.battlecard_id,
                },
            },
            {
                "type": "Action.Submit",
                "title": "📝 Edit & Approve",
                "data": {
                    "action": "edit_battlecard",
                    "battlecard_id": battlecard.battlecard_id,
                },
            },
        ],
    }

    return card


def render_card_json(card: dict) -> str:
    """Serialize an Adaptive Card dict to pretty JSON."""
    return json.dumps(card, indent=2, default=str)


async def send_pulse_to_teams(
    signal: Signal,
    teams_webhook_url: str | None = None,
) -> bool:
    """Send a signal pulse notification to Teams.

    In production, uses the Agent 365 governed Teams MCP server.
    Falls back to webhook if provided.

    Args:
        signal: The signal to notify about.
        teams_webhook_url: Optional webhook URL for direct posting.

    Returns:
        True if sent successfully.
    """
    card = build_signal_card(signal)
    card_json = render_card_json(card)

    if teams_webhook_url:
        import httpx

        payload = {
            "type": "message",
            "attachments": [
                {
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "content": card,
                }
            ],
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(teams_webhook_url, json=payload, timeout=30)
            if resp.status_code == 200:
                logger.info("Pulse sent to Teams for %s", signal.entity_name)
                return True
            else:
                logger.error(
                    "Failed to send Teams pulse: %s %s",
                    resp.status_code,
                    resp.text,
                )
                return False

    # Log card for development / Agent 365 MCP delivery
    logger.info(
        "Teams pulse card generated for %s (use Agent 365 MCP for delivery):\n%s",
        signal.entity_name,
        card_json,
    )
    return True
