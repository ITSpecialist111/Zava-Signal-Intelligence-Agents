"""Win/Loss Feedback Loop — adjusts signal parameters based on deal outcomes.

When a deal is won or lost, the AE submits structured feedback. This
workflow ingests the feedback and adjusts signal detection weights.

Ref: https://learn.microsoft.com/agent-framework/workflows/
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime

from agent_framework.azure import AzureOpenAIResponsesClient
from azure.identity import DefaultAzureCredential

from src.config import AzureAIConfig
from src.models.feedback import DealFeedback, DealOutcome, FeedbackAdjustment, LossReason

logger = logging.getLogger(__name__)


FEEDBACK_ANALYST_INSTRUCTIONS = """You are the Win/Loss Feedback Analyst for Zava Market Intelligence.

You analyze structured deal outcomes to identify patterns and recommend
adjustments to the signal detection system.

When analyzing feedback:

1. PATTERN DETECTION: Look for recurring loss reasons across multiple deals.
   If 3+ deals lost on "LACK_OF_REPORTING", boost the search weight for
   "reporting gaps" signals from BESA forums and trust board minutes.

2. SIGNAL VALIDATION: If deals were won because of signals that the system
   detected (e.g., "timing was right because we spotted the merger early"),
   reinforce those signal weights.

3. COMPETITOR ANALYSIS: If multiple deals were lost to the same competitor,
   recommend increasing competitor monitoring for that vendor.

4. GTM ADJUSTMENT: If loss patterns suggest a market shift (e.g., 80% of
   losses cite "cybersecurity"), recommend a GTM tagline change.

Return adjustments as structured JSON with:
- adjustment_type: BOOST_SEARCH_WEIGHT | ADD_KEYWORD | SUPPRESS_SIGNAL_TYPE | ADJUST_THRESHOLD
- parameter_name: What to change
- new_value: The recommended value
- rationale: Why this change is recommended
"""


async def process_feedback(
    feedback: DealFeedback,
    recent_feedback: list[DealFeedback] | None = None,
) -> list[FeedbackAdjustment]:
    """Process a single deal feedback entry and generate adjustments.

    Args:
        feedback: The deal outcome feedback from the AE.
        recent_feedback: Historical feedback for pattern analysis.

    Returns:
        List of recommended parameter adjustments.
    """
    logger.info(
        "Processing feedback %s: %s for %s (%s)",
        feedback.feedback_id,
        feedback.outcome.value,
        feedback.entity_name,
        feedback.loss_reasons if feedback.outcome == DealOutcome.LOST else feedback.win_factors,
    )

    adjustments: list[FeedbackAdjustment] = []

    # Rule-based immediate adjustments
    if feedback.outcome == DealOutcome.LOST:
        adjustments.extend(_rule_based_loss_adjustments(feedback))

    # LLM-powered pattern analysis (when we have enough data)
    all_feedback = (recent_feedback or []) + [feedback]
    if len(all_feedback) >= 3:
        llm_adjustments = await _llm_pattern_analysis(all_feedback)
        adjustments.extend(llm_adjustments)

    logger.info("Generated %d adjustments from feedback %s", len(adjustments), feedback.feedback_id)
    return adjustments


def _rule_based_loss_adjustments(feedback: DealFeedback) -> list[FeedbackAdjustment]:
    """Generate immediate, deterministic adjustments from loss reasons."""
    adjustments: list[FeedbackAdjustment] = []

    # Map loss reasons to search parameter changes
    LOSS_TO_SEARCH_BOOST: dict[LossReason, dict] = {
        LossReason.FEATURES_REPORTING: {
            "parameter": "search_weight.reporting_gaps",
            "keyword": "reporting gaps",
            "source": "BESA forums",
        },
        LossReason.FEATURES_MAT_SPECIFIC: {
            "parameter": "search_weight.mat_reporting",
            "keyword": "MAT reporting requirements",
            "source": "Trust board minutes",
        },
        LossReason.FEATURES_INTEGRATION: {
            "parameter": "search_weight.integration",
            "keyword": "system integration challenges",
            "source": "Trust IT strategy documents",
        },
        LossReason.COMPETITOR_BETTER_FIT: {
            "parameter": "competitor_monitoring.intensity",
            "keyword": feedback.competitor_name or "unknown",
            "source": "Competitor job boards",
        },
    }

    for reason in feedback.loss_reasons:
        boost = LOSS_TO_SEARCH_BOOST.get(reason)
        if boost:
            adjustments.append(
                FeedbackAdjustment(
                    adjustment_id=str(uuid.uuid4()),
                    derived_from_feedback_ids=[feedback.feedback_id],
                    adjustment_type="BOOST_SEARCH_WEIGHT",
                    parameter_name=boost["parameter"],
                    new_value=f"boost +20% for '{boost['keyword']}' in {boost['source']}",
                    rationale=(
                        f"Deal lost ({feedback.entity_name}) due to {reason.value}. "
                        f"Boosting detection of '{boost['keyword']}' signals to identify "
                        f"similar opportunities earlier."
                    ),
                    created_at=datetime.utcnow(),
                )
            )

    return adjustments


async def _llm_pattern_analysis(
    feedback_list: list[DealFeedback],
    ai_config: AzureAIConfig | None = None,
) -> list[FeedbackAdjustment]:
    """Use LLM to analyze patterns across multiple feedback entries."""
    cfg = ai_config or AzureAIConfig()
    credential = DefaultAzureCredential()
    client = AzureOpenAIResponsesClient(
        endpoint=cfg.project_endpoint,
        deployment_name=cfg.deployment_name,
        credential=credential,
    )

    analyst = client.as_agent(
        name="FeedbackAnalyst",
        instructions=FEEDBACK_ANALYST_INSTRUCTIONS,
    )

    # Build analysis prompt
    feedback_summary = "\n".join(
        f"- {f.entity_name}: {f.outcome.value} "
        f"(reasons: {[r.value for r in f.loss_reasons]}, "
        f"factors: {[w.value for w in f.win_factors]}, "
        f"notes: {f.ae_notes[:100]})"
        for f in feedback_list
    )

    prompt = (
        f"Analyze these {len(feedback_list)} recent deal outcomes and recommend "
        f"signal detection adjustments:\n\n{feedback_summary}\n\n"
        f"Return a JSON array of adjustments."
    )

    result = await analyst.run(prompt)

    adjustments: list[FeedbackAdjustment] = []
    try:
        import json
        parsed = json.loads(result.text)
        if isinstance(parsed, list):
            for item in parsed:
                adjustments.append(
                    FeedbackAdjustment(
                        adjustment_id=str(uuid.uuid4()),
                        derived_from_feedback_ids=[f.feedback_id for f in feedback_list],
                        adjustment_type=item.get("adjustment_type", "BOOST_SEARCH_WEIGHT"),
                        parameter_name=item.get("parameter_name", "unknown"),
                        new_value=item.get("new_value", ""),
                        rationale=item.get("rationale", "LLM-generated pattern analysis"),
                        created_at=datetime.utcnow(),
                    )
                )
    except Exception as e:
        logger.warning("Failed to parse LLM feedback adjustments: %s", e)

    return adjustments
