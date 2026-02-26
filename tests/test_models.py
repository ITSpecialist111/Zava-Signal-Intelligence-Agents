"""Unit tests for data models: Signal, SignalBattlecard, DealFeedback."""

from __future__ import annotations

from datetime import datetime

import pytest
from pydantic import ValidationError

from src.models.battlecard import (
    CompetitorIntel,
    RecommendedAction,
    SignalBattlecard,
    WinLossContext,
)
from src.models.feedback import (
    DealFeedback,
    DealOutcome,
    FeedbackAdjustment,
    LossReason,
    WinFactor,
)
from src.models.signal import (
    ConfidenceLevel,
    Signal,
    SignalBatch,
    SignalCategory,
    SignalStatus,
    SignalSubcategory,
    ZavaPlaybook,
)


# ======================================================================== #
# Signal model
# ======================================================================== #


class TestSignal:
    """Tests for the core Signal model."""

    def test_create_minimal_signal(self):
        s = Signal(
            signal_id="sig-001",
            category=SignalCategory.STRUCTURAL_STRESS,
            subcategory=SignalSubcategory.HUB_AND_SPOKE,
            entity_name="Harris Federation",
            confidence=0.85,
            confidence_level=ConfidenceLevel.HIGH,
            source_url="https://example.com",
            source_name="TES",
            raw_evidence="Merger announced.",
        )
        assert s.signal_id == "sig-001"
        assert s.entity_name == "Harris Federation"
        assert s.status == SignalStatus.DETECTED  # default

    def test_confidence_boundaries(self):
        # Valid: exactly 0.0 and 1.0
        s1 = Signal(
            signal_id="a", category=SignalCategory.COMPLIANCE_TRAP,
            subcategory=SignalSubcategory.EXECUTIVE_PAY_SCRUTINY,
            entity_name="X", confidence=0.0, confidence_level=ConfidenceLevel.LOW,
            source_url="http://x", source_name="x", raw_evidence="x",
        )
        assert s1.confidence == 0.0

        s2 = Signal(
            signal_id="b", category=SignalCategory.COMPLIANCE_TRAP,
            subcategory=SignalSubcategory.EXECUTIVE_PAY_SCRUTINY,
            entity_name="X", confidence=1.0, confidence_level=ConfidenceLevel.HIGH,
            source_url="http://x", source_name="x", raw_evidence="x",
        )
        assert s2.confidence == 1.0

    def test_confidence_out_of_range_rejected(self):
        with pytest.raises(ValidationError):
            Signal(
                signal_id="c", category=SignalCategory.COMPLIANCE_TRAP,
                subcategory=SignalSubcategory.EXECUTIVE_PAY_SCRUTINY,
                entity_name="X", confidence=1.5,
                confidence_level=ConfidenceLevel.HIGH,
                source_url="http://x", source_name="x", raw_evidence="x",
            )

        with pytest.raises(ValidationError):
            Signal(
                signal_id="d", category=SignalCategory.COMPLIANCE_TRAP,
                subcategory=SignalSubcategory.EXECUTIVE_PAY_SCRUTINY,
                entity_name="X", confidence=-0.1,
                confidence_level=ConfidenceLevel.LOW,
                source_url="http://x", source_name="x", raw_evidence="x",
            )

    def test_to_confidence_level(self, sample_signal):
        # 0.85 → HIGH
        assert sample_signal.to_confidence_level() == ConfidenceLevel.HIGH

    def test_to_confidence_level_medium(self, sample_signal_medium):
        assert sample_signal_medium.to_confidence_level() == ConfidenceLevel.MEDIUM

    def test_to_confidence_level_low(self, sample_signal_low):
        assert sample_signal_low.to_confidence_level() == ConfidenceLevel.LOW

    def test_optional_fields_default_none(self):
        s = Signal(
            signal_id="e", category=SignalCategory.LEADERSHIP_CHANGE,
            subcategory=SignalSubcategory.NEW_CFO,
            entity_name="Test Trust", confidence=0.5,
            confidence_level=ConfidenceLevel.MEDIUM,
            source_url="http://test", source_name="Test",
            raw_evidence="evidence",
        )
        assert s.entity_id is None
        assert s.current_provider is None
        assert s.financial_summary is None
        assert s.key_decision_maker is None
        assert s.playbook_match is None
        assert s.reviewed_by is None

    def test_all_signal_categories_exist(self):
        expected = {
            "STRUCTURAL_STRESS", "COMPLIANCE_TRAP", "COMPETITOR_MOVEMENT",
            "PROCUREMENT_SHIFT", "LEADERSHIP_CHANGE",
        }
        assert {c.value for c in SignalCategory} == expected

    def test_all_confidence_levels_exist(self):
        assert set(ConfidenceLevel) == {
            ConfidenceLevel.HIGH, ConfidenceLevel.MEDIUM, ConfidenceLevel.LOW,
        }

    def test_all_statuses_exist(self):
        expected = {
            "DETECTED", "ENRICHED", "HITL_PENDING", "APPROVED",
            "REJECTED", "ACTIVATED", "ARCHIVED",
        }
        assert {s.value for s in SignalStatus} == expected


class TestSignalBatch:
    """Tests for the SignalBatch container."""

    def test_empty_batch(self):
        batch = SignalBatch(batch_id="batch-001", source="TES")
        assert len(batch.signals) == 0
        assert batch.total_pages_scanned == 0
        assert batch.errors == []

    def test_batch_with_signals(self, sample_signal, sample_signal_low):
        batch = SignalBatch(
            batch_id="batch-002",
            source="Gov.UK",
            signals=[sample_signal, sample_signal_low],
            total_pages_scanned=5,
        )
        assert len(batch.signals) == 2
        assert batch.total_pages_scanned == 5


class TestZavaPlaybook:
    def test_playbook_values(self):
        assert len(ZavaPlaybook) == 6
        assert ZavaPlaybook.PROFESSIONALIZATION_PITCH.value == "The Professionalization Pitch"


# ======================================================================== #
# Battlecard model
# ======================================================================== #


class TestSignalBattlecard:

    def test_from_signal(self, sample_signal):
        bc = SignalBattlecard.from_signal(sample_signal, battlecard_id="bc-test-001")
        assert bc.entity_name == sample_signal.entity_name
        assert bc.signal_category == sample_signal.category
        assert bc.confidence_level == sample_signal.confidence_level
        assert bc.playbook == sample_signal.playbook_match
        assert bc.source_url == sample_signal.source_url

    def test_from_signal_no_playbook(self, sample_signal_low):
        bc = SignalBattlecard.from_signal(sample_signal_low, battlecard_id="bc-test-002")
        assert bc.playbook is None
        assert bc.key_message == "Review signal and determine approach"

    def test_battlecard_fields(self, sample_battlecard):
        assert sample_battlecard.entity_id == "07827865"
        assert len(sample_battlecard.actions) == 2
        assert sample_battlecard.actions[0].priority == 1
        assert len(sample_battlecard.competitor_intel) == 1
        assert sample_battlecard.win_loss.similar_wins == 3

    def test_recommended_action_priority_constraint(self):
        with pytest.raises(ValidationError):
            RecommendedAction(priority=0, action="invalid")

        with pytest.raises(ValidationError):
            RecommendedAction(priority=4, action="invalid")

    def test_win_loss_context_defaults(self):
        wl = WinLossContext()
        assert wl.similar_wins == 0
        assert wl.similar_losses == 0
        assert wl.common_win_factors == []

    def test_competitor_intel_serialisation(self):
        ci = CompetitorIntel(
            competitor_name="Access Group",
            activity_summary="New contract win",
            detected_at=datetime(2025, 1, 15),
            source="Digital Marketplace",
        )
        d = ci.model_dump()
        assert d["competitor_name"] == "Access Group"
        assert "detected_at" in d


# ======================================================================== #
# Feedback model
# ======================================================================== #


class TestDealFeedback:

    def test_won_deal(self, sample_feedback_won):
        assert sample_feedback_won.outcome == DealOutcome.WON
        assert WinFactor.CONSOLIDATION in sample_feedback_won.win_factors
        assert sample_feedback_won.loss_reasons == []

    def test_lost_deal(self, sample_feedback_lost):
        assert sample_feedback_lost.outcome == DealOutcome.LOST
        assert LossReason.PRICE in sample_feedback_lost.loss_reasons
        assert sample_feedback_lost.competitor_name == "Access Group"

    def test_all_deal_outcomes(self):
        expected = {"WON", "LOST", "NO_DECISION", "DEFERRED"}
        assert {o.value for o in DealOutcome} == expected

    def test_all_loss_reasons(self):
        assert len(LossReason) == 12

    def test_all_win_factors(self):
        assert len(WinFactor) == 9

    def test_feedback_related_signal_ids(self):
        fb = DealFeedback(
            feedback_id="fb-100",
            deal_id="CRM-100",
            entity_name="Test Trust",
            outcome=DealOutcome.WON,
            related_signal_ids=["sig-001", "sig-002"],
            submitted_by="user@test.com",
        )
        assert len(fb.related_signal_ids) == 2


class TestFeedbackAdjustment:

    def test_adjustment_creation(self):
        adj = FeedbackAdjustment(
            adjustment_id="adj-001",
            derived_from_feedback_ids=["fb-001", "fb-002"],
            adjustment_type="BOOST_SEARCH_WEIGHT",
            parameter_name="structural_stress_weight",
            old_value="1.0",
            new_value="1.5",
            rationale="Strong correlation between structural stress and wins.",
        )
        assert adj.approved is False
        assert adj.approved_by is None
        assert adj.adjustment_type == "BOOST_SEARCH_WEIGHT"
