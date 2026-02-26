"""Content Approval — HITL Gate 2 (Ad-Hoc).

Before any AI-generated outreach content reaches a prospect, a Senior
Sales Rep must review and approve it. This gate catches:
  - Hallucinated data (e.g., wrong trust financials)
  - Tone mismatches (too aggressive, too generic)
  - Competitive intelligence leaks
  - GDPR-sensitive personal data

Ref: https://learn.microsoft.com/agent-framework/user-guide/workflows/orchestrations/human-in-the-loop
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class ContentType(str, Enum):
    """Types of outreach content requiring approval."""

    EMAIL_INTRO = "email_intro"
    EMAIL_FOLLOWUP = "email_followup"
    TEAMS_MESSAGE = "teams_message"
    LINKEDIN_INMAIL = "linkedin_inmail"
    BRIEFING_NOTE = "briefing_note"
    CALL_SCRIPT = "call_script"


class ApprovalDecision(str, Enum):
    """Content approval decisions."""

    APPROVED = "approved"
    APPROVED_WITH_EDITS = "approved_with_edits"
    REJECTED = "rejected"
    NEEDS_REWORK = "needs_rework"


@dataclass
class ContentDraft:
    """A piece of AI-generated outreach content awaiting approval."""

    draft_id: str
    signal_id: str
    entity_name: str
    target_contact: str
    content_type: ContentType
    subject: str
    body: str
    generated_at: datetime = field(default_factory=datetime.utcnow)
    # Provenance: what data sources influenced this content
    source_signals: list[str] = field(default_factory=list)
    companies_house_data_used: bool = False
    competitor_intel_used: bool = False
    # Approval state
    decision: Optional[ApprovalDecision] = None
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    reviewer_edits: Optional[str] = None
    rejection_reason: Optional[str] = None


class ContentApprovalGate:
    """HITL gate for reviewing outreach content before delivery.

    In production, this sends drafts to a Senior Sales Rep via
    Teams Adaptive Card with approve/edit/reject buttons. Edits
    are tracked for future prompt refinement.
    """

    def __init__(self):
        self._pending: dict[str, ContentDraft] = {}
        self._history: list[ContentDraft] = []

    def submit_for_review(self, draft: ContentDraft) -> str:
        """Submit a content draft for human review.

        Returns:
            The draft_id for tracking.
        """
        self._pending[draft.draft_id] = draft
        logger.info(
            "Content draft %s submitted for review — %s for %s",
            draft.draft_id,
            draft.content_type.value,
            draft.entity_name,
        )
        return draft.draft_id

    def approve(
        self,
        draft_id: str,
        reviewer: str,
        edits: str | None = None,
    ) -> ContentDraft | None:
        """Approve a content draft, optionally with edits.

        Args:
            draft_id: The draft to approve.
            reviewer: Name/email of the reviewing Senior Sales Rep.
            edits: If provided, the edited version of the body text.

        Returns:
            The approved draft, or None if not found.
        """
        draft = self._pending.pop(draft_id, None)
        if draft is None:
            logger.warning("Draft %s not found for approval", draft_id)
            return None

        if edits:
            draft.decision = ApprovalDecision.APPROVED_WITH_EDITS
            draft.reviewer_edits = edits
        else:
            draft.decision = ApprovalDecision.APPROVED

        draft.reviewed_by = reviewer
        draft.reviewed_at = datetime.utcnow()
        self._history.append(draft)

        logger.info("Draft %s approved by %s", draft_id, reviewer)
        return draft

    def reject(
        self,
        draft_id: str,
        reviewer: str,
        reason: str,
    ) -> ContentDraft | None:
        """Reject a content draft.

        Args:
            draft_id: The draft to reject.
            reviewer: Name/email of the reviewing Senior Sales Rep.
            reason: Why the content was rejected.

        Returns:
            The rejected draft, or None if not found.
        """
        draft = self._pending.pop(draft_id, None)
        if draft is None:
            logger.warning("Draft %s not found for rejection", draft_id)
            return None

        draft.decision = ApprovalDecision.REJECTED
        draft.reviewed_by = reviewer
        draft.reviewed_at = datetime.utcnow()
        draft.rejection_reason = reason
        self._history.append(draft)

        logger.info("Draft %s rejected by %s: %s", draft_id, reviewer, reason)
        return draft

    def request_rework(
        self,
        draft_id: str,
        reviewer: str,
        instructions: str,
    ) -> ContentDraft | None:
        """Send a draft back for AI rework with specific instructions.

        Args:
            draft_id: The draft to send back.
            reviewer: Name/email of the reviewer.
            instructions: What the AI should change.

        Returns:
            The draft with rework status, or None if not found.
        """
        draft = self._pending.pop(draft_id, None)
        if draft is None:
            logger.warning("Draft %s not found for rework", draft_id)
            return None

        draft.decision = ApprovalDecision.NEEDS_REWORK
        draft.reviewed_by = reviewer
        draft.reviewed_at = datetime.utcnow()
        draft.rejection_reason = f"REWORK: {instructions}"
        self._history.append(draft)

        logger.info("Draft %s sent for rework by %s", draft_id, reviewer)
        return draft

    def get_pending_count(self) -> int:
        """Number of drafts awaiting review."""
        return len(self._pending)

    def get_approval_rate(self) -> float:
        """Percentage of reviewed drafts that were approved."""
        if not self._history:
            return 0.0
        approved = sum(
            1
            for d in self._history
            if d.decision
            in (ApprovalDecision.APPROVED, ApprovalDecision.APPROVED_WITH_EDITS)
        )
        return approved / len(self._history)

    def get_edit_patterns(self) -> list[str]:
        """Get all reviewer edits for prompt refinement analysis."""
        return [
            d.reviewer_edits
            for d in self._history
            if d.decision == ApprovalDecision.APPROVED_WITH_EDITS
            and d.reviewer_edits
        ]
