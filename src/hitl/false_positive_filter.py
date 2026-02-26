"""False Positive Filter — HITL Gate 1 (Bi-Weekly).

A Marketing Manager reviews "Low Confidence" signals. The human teaches
the AI by marking signals as true positives or false positives, with
optional notes (e.g., "This person was a Headteacher, not an Executive
Leader — ignore these in the future").

Ref: https://learn.microsoft.com/agent-framework/user-guide/workflows/orchestrations/human-in-the-loop
"""

from __future__ import annotations

import logging
from datetime import datetime

from src.models.signal import Signal, SignalStatus
from src.tools.signal_store import SignalStore

logger = logging.getLogger(__name__)


class FalsePositiveFilter:
    """HITL gate for reviewing low-confidence signals.

    In production, this integrates with Agent 365 SDK to:
    1. Send Teams Adaptive Cards to the Marketing Manager
    2. Receive approval/rejection via Teams interaction
    3. Update the signal store and train the model

    During development, provides a programmatic interface for testing.
    """

    def __init__(self, signal_store: SignalStore | None = None):
        self.store = signal_store or SignalStore()

    def get_pending_reviews(self) -> list[Signal]:
        """Get all signals awaiting HITL review."""
        return self.store.get_signals_pending_review()

    def approve_signal(
        self,
        signal_id: str,
        reviewer: str,
        notes: str = "",
    ) -> Signal | None:
        """Mark a signal as a true positive (approved).

        Args:
            signal_id: The signal to approve.
            reviewer: Name/email of the reviewing Marketing Manager.
            notes: Optional reviewer notes for context.

        Returns:
            The updated signal, or None if not found.
        """
        signal = self.store.get_signal(signal_id)
        if signal is None:
            logger.warning("Signal %s not found for approval", signal_id)
            return None

        self.store.update_status(
            signal_id=signal_id,
            status=SignalStatus.APPROVED,
            reviewed_by=reviewer,
            review_notes=notes,
            reviewed_at=datetime.utcnow(),
        )

        logger.info("Signal %s approved by %s", signal_id, reviewer)
        return self.store.get_signal(signal_id)

    def reject_signal(
        self,
        signal_id: str,
        reviewer: str,
        reason: str,
        learn_from_rejection: bool = True,
    ) -> Signal | None:
        """Mark a signal as a false positive (rejected).

        If learn_from_rejection is True, the rejection reason is stored
        for future model training to reduce similar false positives.

        Args:
            signal_id: The signal to reject.
            reviewer: Name/email of the reviewing Marketing Manager.
            reason: Why this is a false positive (e.g., "Headteacher, not Executive").
            learn_from_rejection: Whether to flag for model retraining.

        Returns:
            The updated signal, or None if not found.
        """
        signal = self.store.get_signal(signal_id)
        if signal is None:
            logger.warning("Signal %s not found for rejection", signal_id)
            return None

        notes = f"REJECTED: {reason}"
        if learn_from_rejection:
            notes += " [TRAIN: suppress similar signals]"

        self.store.update_status(
            signal_id=signal_id,
            status=SignalStatus.REJECTED,
            reviewed_by=reviewer,
            review_notes=notes,
            reviewed_at=datetime.utcnow(),
        )

        logger.info("Signal %s rejected by %s: %s", signal_id, reviewer, reason)
        return self.store.get_signal(signal_id)

    def get_review_summary(self) -> dict:
        """Get summary statistics for the bi-weekly review session."""
        pending = self.get_pending_reviews()

        # Group by category for the reviewer
        by_category: dict[str, int] = {}
        by_source: dict[str, int] = {}
        for signal in pending:
            cat = signal.category.value
            by_category[cat] = by_category.get(cat, 0) + 1
            src = signal.source_name
            by_source[src] = by_source.get(src, 0) + 1

        return {
            "total_pending": len(pending),
            "by_category": by_category,
            "by_source": by_source,
            "oldest_signal": (
                min(s.detected_at for s in pending).isoformat() if pending else None
            ),
        }
