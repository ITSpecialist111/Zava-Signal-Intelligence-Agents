"""Signal Battlecard model — the actionable output for Sales.

When a signal is detected, enriched, and approved, it is rendered as a
Battlecard that gives the Account Executive everything they need to act
within 24 hours.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from src.models.signal import ConfidenceLevel, Signal, SignalCategory, ZavaPlaybook


class CompetitorIntel(BaseModel):
    """Competitor intelligence related to a specific entity."""

    competitor_name: str
    activity_summary: str = Field(description="What the competitor is doing")
    detected_at: datetime
    source: str


class WinLossContext(BaseModel):
    """Historical win/loss context for similar deals."""

    similar_wins: int = 0
    similar_losses: int = 0
    common_win_factors: list[str] = Field(default_factory=list)
    common_loss_reasons: list[str] = Field(default_factory=list)


class RecommendedAction(BaseModel):
    """A specific action for the Account Executive."""

    priority: int = Field(ge=1, le=3, description="1=Primary, 2=Secondary, 3=Nurture")
    action: str
    detail: Optional[str] = None


class SignalBattlecard(BaseModel):
    """The complete Signal Battlecard delivered to Sales.

    This is the primary output artifact that gives AEs a 3-month head start
    over competitors by combining signal detection, enrichment, playbook
    mapping, and competitive intelligence into a single actionable brief.
    """

    # Header
    battlecard_id: str
    generated_at: datetime = Field(default_factory=datetime.utcnow)

    # Signal summary
    entity_name: str
    entity_id: Optional[str] = None
    signal_category: SignalCategory
    signal_summary: str = Field(description="2–3 sentence summary of what was detected")
    confidence_level: ConfidenceLevel
    source_url: str
    detected_at: datetime

    # The "So What"
    playbook: Optional[ZavaPlaybook] = None
    key_message: str = Field(description="One-liner for the AE to use")
    handbook_reference: Optional[str] = Field(default=None, description="E.g., 'Section 1.16 - Risk'")

    # Enrichment data
    current_provider: Optional[str] = None
    financial_health: Optional[str] = Field(default=None, description="Last 3-year trend summary")
    key_decision_maker: Optional[str] = None
    recent_changes: Optional[str] = None

    # Recommended actions
    actions: list[RecommendedAction] = Field(default_factory=list)

    # Competitor intel
    competitor_intel: list[CompetitorIntel] = Field(default_factory=list)

    # Win/Loss context
    win_loss: WinLossContext = Field(default_factory=WinLossContext)

    @classmethod
    def from_signal(cls, signal: Signal, battlecard_id: str) -> "SignalBattlecard":
        """Create a Battlecard from an enriched, approved Signal."""
        return cls(
            battlecard_id=battlecard_id,
            entity_name=signal.entity_name,
            entity_id=signal.entity_id,
            signal_category=signal.category,
            signal_summary=signal.raw_evidence[:500],
            confidence_level=signal.confidence_level,
            source_url=signal.source_url,
            detected_at=signal.detected_at,
            playbook=signal.playbook_match,
            key_message=signal.recommended_action or "Review signal and determine approach",
            handbook_reference=signal.handbook_reference,
            current_provider=signal.current_provider,
            financial_health=signal.financial_summary,
            key_decision_maker=signal.key_decision_maker,
            recent_changes=signal.recent_changes,
        )
