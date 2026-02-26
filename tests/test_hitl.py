"""Unit tests for HITL gates: FalsePositiveFilter, ContentApprovalGate, StrategyPivotGate."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.hitl.content_approval import (
    ApprovalDecision,
    ContentApprovalGate,
    ContentDraft,
    ContentType,
)
from src.hitl.false_positive_filter import FalsePositiveFilter
from src.hitl.strategy_pivot import (
    HeatmapCell,
    StrategyDirective,
    StrategyPivotGate,
)
from src.models.signal import (
    ConfidenceLevel,
    Signal,
    SignalCategory,
    SignalStatus,
    SignalSubcategory,
)
from src.tools.signal_store import SignalStore


# ======================================================================== #
# False Positive Filter (HITL Gate 1)
# ======================================================================== #


def _hitl_signal(
    signal_id: str,
    status: SignalStatus = SignalStatus.HITL_PENDING,
    category: SignalCategory = SignalCategory.LEADERSHIP_CHANGE,
) -> Signal:
    return Signal(
        signal_id=signal_id,
        category=category,
        subcategory=SignalSubcategory.NEW_CFO,
        entity_name="Test Trust",
        confidence=0.4,
        confidence_level=ConfidenceLevel.LOW,
        status=status,
        source_url="http://test",
        source_name="Test",
        raw_evidence="Test evidence.",
    )


@pytest.fixture
def fp_filter(tmp_path: Path) -> FalsePositiveFilter:
    store = SignalStore(store_path=tmp_path / "hitl_signals.json")
    return FalsePositiveFilter(signal_store=store)


class TestFalsePositiveFilter:

    def test_get_pending_reviews_empty(self, fp_filter: FalsePositiveFilter):
        assert fp_filter.get_pending_reviews() == []

    def test_get_pending_reviews(self, fp_filter: FalsePositiveFilter):
        fp_filter.store.add_signal(_hitl_signal("fp-1"))
        fp_filter.store.add_signal(_hitl_signal("fp-2"))
        fp_filter.store.add_signal(_hitl_signal("fp-3", status=SignalStatus.DETECTED))
        pending = fp_filter.get_pending_reviews()
        assert len(pending) == 2

    def test_approve_signal(self, fp_filter: FalsePositiveFilter):
        fp_filter.store.add_signal(_hitl_signal("approve-1"))
        result = fp_filter.approve_signal("approve-1", reviewer="mgr@zava.com", notes="Looks legit")
        assert result is not None
        assert result.status == SignalStatus.APPROVED

    def test_approve_missing_signal(self, fp_filter: FalsePositiveFilter):
        result = fp_filter.approve_signal("nonexistent", reviewer="mgr@zava.com")
        assert result is None

    def test_reject_signal(self, fp_filter: FalsePositiveFilter):
        fp_filter.store.add_signal(_hitl_signal("reject-1"))
        result = fp_filter.reject_signal(
            "reject-1",
            reviewer="mgr@zava.com",
            reason="Headteacher, not Executive Leader",
        )
        assert result is not None
        assert result.status == SignalStatus.REJECTED

    def test_reject_with_learn_flag(self, fp_filter: FalsePositiveFilter):
        fp_filter.store.add_signal(_hitl_signal("learn-1"))
        fp_filter.reject_signal(
            "learn-1",
            reviewer="mgr@zava.com",
            reason="Wrong role",
            learn_from_rejection=True,
        )
        sig = fp_filter.store.get_signal("learn-1")
        assert sig is not None
        # The raw data includes the [TRAIN:] tag
        raw = fp_filter.store._signals["learn-1"]
        assert "TRAIN" in raw.get("review_notes", "")

    def test_reject_missing_signal(self, fp_filter: FalsePositiveFilter):
        result = fp_filter.reject_signal("missing", reviewer="mgr@zava.com", reason="test")
        assert result is None

    def test_review_summary(self, fp_filter: FalsePositiveFilter):
        fp_filter.store.add_signal(_hitl_signal("sum-1", category=SignalCategory.LEADERSHIP_CHANGE))
        fp_filter.store.add_signal(_hitl_signal("sum-2", category=SignalCategory.COMPLIANCE_TRAP))
        summary = fp_filter.get_review_summary()
        assert summary["total_pending"] == 2
        assert "LEADERSHIP_CHANGE" in summary["by_category"]
        assert "COMPLIANCE_TRAP" in summary["by_category"]

    def test_review_summary_empty(self, fp_filter: FalsePositiveFilter):
        summary = fp_filter.get_review_summary()
        assert summary["total_pending"] == 0
        assert summary["oldest_signal"] is None


# ======================================================================== #
# Content Approval Gate (HITL Gate 2)
# ======================================================================== #


def _make_draft(
    draft_id: str = "draft-001",
    entity_name: str = "Harris Federation",
    content_type: ContentType = ContentType.EMAIL_INTRO,
) -> ContentDraft:
    return ContentDraft(
        draft_id=draft_id,
        signal_id="sig-001",
        entity_name=entity_name,
        target_contact="jane.smith@harris.org",
        content_type=content_type,
        subject="Zava — Supporting your merger integration",
        body="Dear Jane, We noticed your trust is undergoing a significant structural change...",
    )


class TestContentApprovalGate:

    def test_submit_and_pending_count(self):
        gate = ContentApprovalGate()
        assert gate.get_pending_count() == 0
        gate.submit_for_review(_make_draft("d1"))
        gate.submit_for_review(_make_draft("d2"))
        assert gate.get_pending_count() == 2

    def test_approve_without_edits(self):
        gate = ContentApprovalGate()
        gate.submit_for_review(_make_draft("d3"))
        result = gate.approve("d3", reviewer="sr@zava.com")
        assert result is not None
        assert result.decision == ApprovalDecision.APPROVED
        assert result.reviewed_by == "sr@zava.com"
        assert result.reviewed_at is not None
        assert gate.get_pending_count() == 0

    def test_approve_with_edits(self):
        gate = ContentApprovalGate()
        gate.submit_for_review(_make_draft("d4"))
        edited_body = "Updated body text with reviewer corrections."
        result = gate.approve("d4", reviewer="sr@zava.com", edits=edited_body)
        assert result is not None
        assert result.decision == ApprovalDecision.APPROVED_WITH_EDITS
        assert result.reviewer_edits == edited_body

    def test_approve_missing_draft(self):
        gate = ContentApprovalGate()
        assert gate.approve("nonexistent", reviewer="sr@zava.com") is None

    def test_reject(self):
        gate = ContentApprovalGate()
        gate.submit_for_review(_make_draft("d5"))
        result = gate.reject("d5", reviewer="sr@zava.com", reason="Tone too aggressive")
        assert result is not None
        assert result.decision == ApprovalDecision.REJECTED
        assert result.rejection_reason == "Tone too aggressive"
        assert gate.get_pending_count() == 0

    def test_reject_missing_draft(self):
        gate = ContentApprovalGate()
        assert gate.reject("missing", reviewer="sr@zava.com", reason="test") is None

    def test_request_rework(self):
        gate = ContentApprovalGate()
        gate.submit_for_review(_make_draft("d6"))
        result = gate.request_rework("d6", reviewer="sr@zava.com", instructions="Soften opening para")
        assert result is not None
        assert result.decision == ApprovalDecision.NEEDS_REWORK
        assert "Soften opening para" in result.rejection_reason

    def test_request_rework_missing(self):
        gate = ContentApprovalGate()
        assert gate.request_rework("missing", reviewer="sr@zava.com", instructions="fix") is None

    def test_approval_rate_empty(self):
        gate = ContentApprovalGate()
        assert gate.get_approval_rate() == 0.0

    def test_approval_rate_mixed(self):
        gate = ContentApprovalGate()
        gate.submit_for_review(_make_draft("rate-1"))
        gate.submit_for_review(_make_draft("rate-2"))
        gate.submit_for_review(_make_draft("rate-3"))
        gate.submit_for_review(_make_draft("rate-4"))

        gate.approve("rate-1", reviewer="r")
        gate.approve("rate-2", reviewer="r", edits="edit")
        gate.reject("rate-3", reviewer="r", reason="bad")
        gate.reject("rate-4", reviewer="r", reason="bad")

        rate = gate.get_approval_rate()
        assert rate == pytest.approx(0.5)

    def test_get_edit_patterns(self):
        gate = ContentApprovalGate()
        gate.submit_for_review(_make_draft("edit-1"))
        gate.submit_for_review(_make_draft("edit-2"))
        gate.approve("edit-1", reviewer="r", edits="Edited version 1")
        gate.approve("edit-2", reviewer="r")  # No edits

        patterns = gate.get_edit_patterns()
        assert len(patterns) == 1
        assert patterns[0] == "Edited version 1"


class TestContentDraft:

    def test_draft_defaults(self):
        draft = _make_draft()
        assert draft.decision is None
        assert draft.reviewed_by is None
        assert draft.companies_house_data_used is False
        assert draft.source_signals == []

    def test_content_types_exist(self):
        expected = {
            "email_intro", "email_followup", "teams_message",
            "linkedin_inmail", "briefing_note", "call_script",
        }
        assert {ct.value for ct in ContentType} == expected


# ======================================================================== #
# Strategy Pivot Gate (HITL Gate 3)
# ======================================================================== #


class TestStrategyPivotGate:

    def test_no_directive_by_default(self):
        gate = StrategyPivotGate()
        assert gate.get_latest_directive() is None
        assert gate.get_active_disabled_categories() == set()

    def test_submit_directive(self):
        gate = StrategyPivotGate()
        directive = StrategyDirective(
            directive_id="dir-001",
            issued_by="vp@zava.com",
            categories_disabled=[SignalCategory.PROCUREMENT_SHIFT],
            categories_boosted=[SignalCategory.STRUCTURAL_STRESS],
            confidence_threshold_override=0.7,
            notes="Focus on structural stress for Q3.",
        )
        gate.submit_directive(directive)
        latest = gate.get_latest_directive()
        assert latest is not None
        assert latest.directive_id == "dir-001"
        assert latest.confidence_threshold_override == 0.7

    def test_active_disabled_categories(self):
        gate = StrategyPivotGate()
        directive = StrategyDirective(
            directive_id="dir-002",
            issued_by="vp@zava.com",
            categories_disabled=[SignalCategory.PROCUREMENT_SHIFT, SignalCategory.COMPLIANCE_TRAP],
        )
        gate.submit_directive(directive)
        disabled = gate.get_active_disabled_categories()
        assert disabled == {SignalCategory.PROCUREMENT_SHIFT, SignalCategory.COMPLIANCE_TRAP}

    def test_directive_history(self):
        gate = StrategyPivotGate()
        gate.submit_directive(StrategyDirective(directive_id="h1", issued_by="vp@zava.com"))
        gate.submit_directive(StrategyDirective(directive_id="h2", issued_by="vp@zava.com"))
        history = gate.get_directive_history()
        assert len(history) == 2
        assert history[0].directive_id == "h1"
        assert history[1].directive_id == "h2"

    def test_latest_directive_is_last(self):
        gate = StrategyPivotGate()
        gate.submit_directive(StrategyDirective(directive_id="old", issued_by="vp@zava.com"))
        gate.submit_directive(StrategyDirective(directive_id="new", issued_by="vp@zava.com"))
        assert gate.get_latest_directive().directive_id == "new"

    def test_build_heatmap(self, tmp_path: Path):
        store = SignalStore(store_path=tmp_path / "heatmap_signals.json")
        store.add_signal(_hitl_signal("hm-1", category=SignalCategory.LEADERSHIP_CHANGE))
        store.add_signal(_hitl_signal("hm-2", category=SignalCategory.LEADERSHIP_CHANGE))
        store.add_signal(_hitl_signal("hm-3", category=SignalCategory.COMPLIANCE_TRAP))

        gate = StrategyPivotGate()
        heatmap = gate.build_heatmap(store)
        assert len(heatmap) == len(SignalCategory)
        # All cells should be HeatmapCell instances
        assert all(isinstance(cell, HeatmapCell) for cell in heatmap)


class TestHeatmapCell:

    def test_defaults(self):
        cell = HeatmapCell(category=SignalCategory.STRUCTURAL_STRESS)
        assert cell.total_signals == 0
        assert cell.roi_score == 0.0

    def test_roi_score(self):
        cell = HeatmapCell(
            category=SignalCategory.STRUCTURAL_STRESS,
            total_signals=10,
            approved_signals=7,
        )
        # ROI is set by the gate's build_heatmap, not the cell itself
        assert cell.approved_signals == 7


class TestStrategyDirective:

    def test_defaults(self):
        d = StrategyDirective(directive_id="sd-001", issued_by="test@zava.com")
        assert d.categories_disabled == []
        assert d.categories_boosted == []
        assert d.new_sweep_targets == []
        assert d.confidence_threshold_override is None
        assert d.notes == ""
