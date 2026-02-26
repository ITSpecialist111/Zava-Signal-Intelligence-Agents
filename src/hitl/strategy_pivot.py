"""Strategy Pivot — HITL Gate 3 (Quarterly).

VP of Sales reviews a signal heatmap that shows which signal
categories are producing actual pipeline vs noise.  The VP can:
  - Mark an entire SignalCategory as OFF (stop collecting)
  - Add new target sources to SWEEP_TARGETS
  - Adjust confidence thresholds
  - Update competitor watch list
  - Redirect focus to specific trust segments

Ref: https://learn.microsoft.com/agent-framework/user-guide/workflows/orchestrations/human-in-the-loop
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from src.models.signal import SignalCategory

logger = logging.getLogger(__name__)


@dataclass
class HeatmapCell:
    """One cell in the signal heatmap: category × metric."""

    category: SignalCategory
    total_signals: int = 0
    approved_signals: int = 0
    rejected_signals: int = 0
    pipeline_generated: float = 0.0  # £ pipeline attributed
    deals_won: int = 0
    deals_lost: int = 0
    avg_days_to_pipeline: float = 0.0
    roi_score: float = 0.0  # pipeline_generated / cost-of-collection


@dataclass
class StrategyDirective:
    """A strategic instruction from the VP to modify system behaviour."""

    directive_id: str
    issued_by: str
    issued_at: datetime = field(default_factory=datetime.utcnow)
    # Category toggles
    categories_disabled: list[SignalCategory] = field(default_factory=list)
    categories_boosted: list[SignalCategory] = field(default_factory=list)
    # Source adjustments
    new_sweep_targets: list[dict] = field(default_factory=list)
    removed_sweep_targets: list[str] = field(default_factory=list)
    # Threshold adjustments
    confidence_threshold_override: Optional[float] = None
    # Competitor adjustments
    new_competitors: list[str] = field(default_factory=list)
    removed_competitors: list[str] = field(default_factory=list)
    # Segment focus
    priority_segments: list[str] = field(default_factory=list)
    # Free-text strategic notes
    notes: str = ""


class StrategyPivotGate:
    """HITL gate for quarterly strategic review.

    Presents a heatmap of signal performance to the VP of Sales.
    Collects strategic directives that reshape system behaviour for
    the next quarter.
    """

    def __init__(self):
        self._directives: list[StrategyDirective] = []

    def build_heatmap(self, signal_store) -> list[HeatmapCell]:
        """Build performance heatmap from signal store data.

        Args:
            signal_store: The SignalStore instance to query.

        Returns:
            List of HeatmapCells, one per signal category.
        """
        counts = signal_store.get_signal_counts_by_category()
        cells: list[HeatmapCell] = []

        for category in SignalCategory:
            total = counts.get(category.value, 0)
            cell = HeatmapCell(
                category=category,
                total_signals=total,
            )
            # ROI score: approved / total (simple proxy until
            # CRM integration provides pipeline £ values)
            if cell.total_signals > 0:
                cell.roi_score = cell.approved_signals / cell.total_signals
            cells.append(cell)

        return cells

    def submit_directive(self, directive: StrategyDirective) -> None:
        """Record a strategic directive from the VP review.

        In production this triggers reconfiguration of:
        - signal_collector.SWEEP_TARGETS
        - competitor_ghost.COMPETITORS
        - daily_sweep confidence routing thresholds
        - signal_store category filters
        """
        self._directives.append(directive)
        logger.info(
            "Strategy directive %s issued by %s — "
            "disabled=%s, boosted=%s, new_targets=%d, threshold=%s",
            directive.directive_id,
            directive.issued_by,
            [c.value for c in directive.categories_disabled],
            [c.value for c in directive.categories_boosted],
            len(directive.new_sweep_targets),
            directive.confidence_threshold_override,
        )

    def get_latest_directive(self) -> StrategyDirective | None:
        """Get the most recent strategic directive."""
        return self._directives[-1] if self._directives else None

    def get_active_disabled_categories(self) -> set[SignalCategory]:
        """Get categories currently disabled by strategic directive."""
        latest = self.get_latest_directive()
        if latest is None:
            return set()
        return set(latest.categories_disabled)

    def get_directive_history(self) -> list[StrategyDirective]:
        """Return full history of strategic directives for audit."""
        return list(self._directives)
