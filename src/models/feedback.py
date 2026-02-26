"""Win/Loss Feedback model — the learning loop.

When a deal is won or lost, the AE enters structured feedback that the
system ingests to adjust signal search parameters and improve future
detection accuracy.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class DealOutcome(str, Enum):
    """Outcome of a sales deal."""

    WON = "WON"
    LOST = "LOST"
    NO_DECISION = "NO_DECISION"
    DEFERRED = "DEFERRED"


class LossReason(str, Enum):
    """Structured loss reasons for pattern analysis."""

    PRICE = "PRICE"
    FEATURES_REPORTING = "LACK_OF_REPORTING"
    FEATURES_MAT_SPECIFIC = "LACK_OF_MAT_REPORTING"
    FEATURES_INTEGRATION = "INTEGRATION_GAPS"
    COMPETITOR_INCUMBENT = "COMPETITOR_INCUMBENT"
    COMPETITOR_BETTER_FIT = "COMPETITOR_BETTER_FIT"
    TIMING_TOO_EARLY = "TIMING_TOO_EARLY"
    TIMING_TOO_LATE = "TIMING_TOO_LATE"
    PROCUREMENT_PROCESS = "PROCUREMENT_PROCESS"
    BUDGET = "BUDGET_CONSTRAINTS"
    RELATIONSHIP = "RELATIONSHIP_NOT_ESTABLISHED"
    OTHER = "OTHER"


class WinFactor(str, Enum):
    """Structured win factors for pattern reinforcement."""

    RISK_MITIGATION = "RISK_MITIGATION"
    COMPLIANCE_READY = "COMPLIANCE_READY"
    COST_SAVING = "COST_SAVING"
    CONSOLIDATION = "CONSOLIDATION"
    MODERN_PLATFORM = "MODERN_PLATFORM"
    RELATIONSHIP = "EXISTING_RELATIONSHIP"
    TIMING = "RIGHT_TIMING"
    REFERRAL = "REFERRAL"
    OTHER = "OTHER"


class DealFeedback(BaseModel):
    """Structured feedback from an Account Executive after a deal concludes.

    This drives the Win/Loss Feedback Loop: the system ingests this data
    and adjusts signal search weights and detection parameters accordingly.
    """

    feedback_id: str
    deal_id: str = Field(description="CRM deal/opportunity ID")
    entity_name: str = Field(description="Trust name")
    entity_id: Optional[str] = Field(default=None, description="Companies House number")

    outcome: DealOutcome
    loss_reasons: list[LossReason] = Field(default_factory=list)
    win_factors: list[WinFactor] = Field(default_factory=list)
    competitor_name: Optional[str] = Field(default=None, description="Competitor if lost to a specific vendor")

    # Free-text context
    ae_notes: str = Field(default="", description="AE's narrative about the deal outcome")
    key_learning: Optional[str] = Field(default=None, description="What should we do differently?")

    # Linkage to signals
    related_signal_ids: list[str] = Field(
        default_factory=list,
        description="Signal IDs that contributed to identifying this opportunity",
    )

    submitted_by: str = Field(description="AE name or email")
    submitted_at: datetime = Field(default_factory=datetime.utcnow)


class FeedbackAdjustment(BaseModel):
    """A parameter adjustment derived from feedback analysis.

    The feedback loop agent generates these adjustments to tune the
    signal detection system.
    """

    adjustment_id: str
    derived_from_feedback_ids: list[str]
    adjustment_type: str = Field(description="E.g., 'BOOST_SEARCH_WEIGHT', 'ADD_KEYWORD', 'SUPPRESS_SIGNAL_TYPE'")
    parameter_name: str = Field(description="Which parameter to adjust")
    old_value: Optional[str] = None
    new_value: str
    rationale: str = Field(description="Why this adjustment is being made")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    approved: bool = False
    approved_by: Optional[str] = None
