"""Shared test fixtures for the Zava Signal Intelligence test suite."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest

from src.models.battlecard import (
    CompetitorIntel,
    RecommendedAction,
    SignalBattlecard,
    WinLossContext,
)
from src.models.feedback import (
    DealFeedback,
    DealOutcome,
    LossReason,
    WinFactor,
)
from src.models.signal import (
    ConfidenceLevel,
    Signal,
    SignalCategory,
    SignalStatus,
    SignalSubcategory,
    ZavaPlaybook,
)


# ---------------------------------------------------------------------------
# Signal fixtures
# ---------------------------------------------------------------------------


def _make_signal(
    *,
    signal_id: str | None = None,
    entity_name: str = "Harris Federation",
    category: SignalCategory = SignalCategory.STRUCTURAL_STRESS,
    subcategory: SignalSubcategory = SignalSubcategory.HUB_AND_SPOKE,
    confidence: float = 0.85,
    confidence_level: ConfidenceLevel = ConfidenceLevel.HIGH,
    status: SignalStatus = SignalStatus.DETECTED,
    playbook_match: ZavaPlaybook | None = ZavaPlaybook.CONSOLIDATION_VALUE_PROP,
    detected_at: datetime | None = None,
    source_url: str = "https://tes.com/article/1234",
    source_name: str = "TES Magazine",
    raw_evidence: str = "Harris Federation announces merger with two local trusts, creating a 45-school MAT",
) -> Signal:
    return Signal(
        signal_id=signal_id or str(uuid.uuid4()),
        entity_name=entity_name,
        category=category,
        subcategory=subcategory,
        confidence=confidence,
        confidence_level=confidence_level,
        status=status,
        playbook_match=playbook_match,
        detected_at=detected_at or datetime.utcnow(),
        source_url=source_url,
        source_name=source_name,
        raw_evidence=raw_evidence,
    )


@pytest.fixture
def sample_signal() -> Signal:
    """A high-confidence structural stress signal."""
    return _make_signal()


@pytest.fixture
def sample_signal_low() -> Signal:
    """A low-confidence leadership change signal."""
    return _make_signal(
        entity_name="Oasis Community Learning",
        category=SignalCategory.LEADERSHIP_CHANGE,
        subcategory=SignalSubcategory.NEW_CFO,
        confidence=0.35,
        confidence_level=ConfidenceLevel.LOW,
        status=SignalStatus.HITL_PENDING,
        playbook_match=None,
        raw_evidence="New CFO appointed at Oasis Community Learning.",
    )


@pytest.fixture
def sample_signal_medium() -> Signal:
    """A medium-confidence compliance trap signal."""
    return _make_signal(
        entity_name="Ark Schools",
        category=SignalCategory.COMPLIANCE_TRAP,
        subcategory=SignalSubcategory.EXECUTIVE_PAY_SCRUTINY,
        confidence=0.65,
        confidence_level=ConfidenceLevel.MEDIUM,
        status=SignalStatus.ENRICHED,
        playbook_match=ZavaPlaybook.COMPLIANCE_SHIELD,
        raw_evidence="Ark Schools CEO pay exceeds £200k threshold for ESFA scrutiny.",
    )


@pytest.fixture
def weekly_signals(
    sample_signal, sample_signal_low, sample_signal_medium,
) -> list[Signal]:
    """A mixed-confidence batch of 5 signals for weekly reports."""
    now = datetime.utcnow()
    extra_1 = _make_signal(
        entity_name="Delta Academies Trust",
        category=SignalCategory.PROCUREMENT_SHIFT,
        subcategory=SignalSubcategory.PIPELINE_NOTICE,
        confidence=0.9,
        confidence_level=ConfidenceLevel.HIGH,
        detected_at=now - timedelta(days=1),
        raw_evidence="Pipeline notice published for payroll services procurement.",
    )
    extra_2 = _make_signal(
        entity_name="Harris Federation",
        category=SignalCategory.COMPETITOR_MOVEMENT,
        subcategory=SignalSubcategory.COMPETITOR_HIRING,
        confidence=0.55,
        confidence_level=ConfidenceLevel.MEDIUM,
        detected_at=now - timedelta(days=2),
        raw_evidence="Competitor hiring detected in Harris Federation area.",
    )
    return [sample_signal, sample_signal_low, sample_signal_medium, extra_1, extra_2]


# ---------------------------------------------------------------------------
# Battlecard fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_battlecard() -> SignalBattlecard:
    return SignalBattlecard(
        battlecard_id="bc-001",
        entity_name="Harris Federation",
        entity_id="07827865",
        signal_category=SignalCategory.STRUCTURAL_STRESS,
        signal_summary="Merger with two local trusts creating a 45-school MAT.",
        confidence_level=ConfidenceLevel.HIGH,
        source_url="https://tes.com/article/1234",
        detected_at=datetime.utcnow(),
        playbook=ZavaPlaybook.CONSOLIDATION_VALUE_PROP,
        key_message="Position consolidation value prop for post-merger payroll integration.",
        current_provider="MHR",
        financial_health="Revenue: growing 8% YoY",
        key_decision_maker="Jane Smith, CFO",
        actions=[
            RecommendedAction(priority=1, action="Schedule intro call with CFO"),
            RecommendedAction(priority=2, action="Prepare consolidation case study"),
        ],
        competitor_intel=[
            CompetitorIntel(
                competitor_name="MHR",
                activity_summary="Incumbent, contract renewal due Q3",
                detected_at=datetime.utcnow(),
                source="Digital Marketplace",
            ),
        ],
        win_loss=WinLossContext(
            similar_wins=3,
            similar_losses=1,
            common_win_factors=["consolidation", "cost_saving"],
        ),
    )


# ---------------------------------------------------------------------------
# Feedback fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_feedback_won() -> DealFeedback:
    return DealFeedback(
        feedback_id="fb-001",
        deal_id="CRM-5678",
        entity_name="Harris Federation",
        entity_id="07827865",
        outcome=DealOutcome.WON,
        win_factors=[WinFactor.CONSOLIDATION, WinFactor.COST_SAVING],
        ae_notes="Strong consolidation pitch post-merger signal.",
        submitted_by="ae@zava.com",
    )


@pytest.fixture
def sample_feedback_lost() -> DealFeedback:
    return DealFeedback(
        feedback_id="fb-002",
        deal_id="CRM-9999",
        entity_name="Oasis Community Learning",
        outcome=DealOutcome.LOST,
        loss_reasons=[LossReason.PRICE, LossReason.COMPETITOR_INCUMBENT],
        competitor_name="Access Group",
        ae_notes="Access Group incumbent, price was non-competitive.",
        submitted_by="ae2@zava.com",
    )
