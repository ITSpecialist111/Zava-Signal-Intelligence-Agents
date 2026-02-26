"""Segment Brief — Weekly Structured Summary.

Aggregates the week's signals into a concise markdown brief,
grouped by trust segment and ranked by confidence. Delivered
via email (Agent 365 Outlook MCP) or SharePoint upload.

Output: Markdown document with executive summary, signal table,
and recommended next steps.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timedelta

from src.models.signal import ConfidenceLevel, Signal, SignalCategory

logger = logging.getLogger(__name__)


def generate_segment_brief(
    signals: list[Signal],
    week_ending: datetime | None = None,
) -> str:
    """Generate a weekly segment brief in Markdown.

    Args:
        signals: All signals from the reporting period.
        week_ending: The end date of the reporting week (defaults to now).

    Returns:
        Markdown string ready for delivery.
    """
    if week_ending is None:
        week_ending = datetime.utcnow()
    week_starting = week_ending - timedelta(days=7)

    # Filter to this week's signals
    weekly = [
        s for s in signals if week_starting <= s.detected_at <= week_ending
    ]

    # Group by category
    by_category: dict[str, list[Signal]] = defaultdict(list)
    for s in weekly:
        by_category[s.category.value].append(s)

    # Confidence breakdown
    high = [s for s in weekly if s.confidence_level == ConfidenceLevel.HIGH]
    medium = [s for s in weekly if s.confidence_level == ConfidenceLevel.MEDIUM]
    low = [s for s in weekly if s.confidence_level == ConfidenceLevel.LOW]

    # Build the brief
    lines: list[str] = []

    lines.append("# Zava Signal Intelligence — Weekly Brief")
    lines.append(f"**Week ending:** {week_ending.strftime('%d %B %Y')}")
    lines.append(f"**Generated:** {datetime.utcnow().strftime('%d %B %Y %H:%M UTC')}")
    lines.append("")

    # Executive summary
    lines.append("## Executive Summary")
    lines.append("")
    lines.append(f"- **Total signals detected:** {len(weekly)}")
    lines.append(f"- **High confidence:** {len(high)}")
    lines.append(f"- **Medium confidence:** {len(medium)}")
    lines.append(f"- **Low confidence:** {len(low)}")
    lines.append(f"- **Categories active:** {len(by_category)}")
    lines.append("")

    # Top signals table
    top_signals = sorted(
        weekly,
        key=lambda s: (
            {"HIGH": 0, "MEDIUM": 1, "LOW": 2}.get(s.confidence_level.value, 3),
            s.detected_at,
        ),
    )[:15]

    if top_signals:
        lines.append("## Top Signals This Week")
        lines.append("")
        lines.append(
            "| Trust | Category | Confidence | Playbook | Source | Detected |"
        )
        lines.append(
            "|-------|----------|------------|----------|--------|----------|"
        )
        for s in top_signals:
            playbook = s.playbook_match.value if s.playbook_match else "—"
            lines.append(
                f"| {s.entity_name} "
                f"| {s.category.value} "
                f"| {s.confidence_level.value} "
                f"| {playbook} "
                f"| {s.source_name} "
                f"| {s.detected_at.strftime('%d %b')} |"
            )
        lines.append("")

    # Category breakdown
    lines.append("## Category Breakdown")
    lines.append("")

    category_order = [
        SignalCategory.STRUCTURAL_STRESS,
        SignalCategory.COMPLIANCE_TRAP,
        SignalCategory.COMPETITOR_MOVEMENT,
        SignalCategory.PROCUREMENT_SHIFT,
        SignalCategory.LEADERSHIP_CHANGE,
    ]

    for cat in category_order:
        cat_signals = by_category.get(cat.value, [])
        if not cat_signals:
            continue

        lines.append(f"### {cat.value}")
        lines.append(f"*{len(cat_signals)} signals detected*")
        lines.append("")

        for s in sorted(cat_signals, key=lambda x: x.detected_at, reverse=True)[:5]:
            conf_badge = {
                ConfidenceLevel.HIGH: "🔴",
                ConfidenceLevel.MEDIUM: "🟡",
                ConfidenceLevel.LOW: "⚪",
            }.get(s.confidence_level, "⚪")
            lines.append(f"- {conf_badge} **{s.entity_name}**: {s.raw_evidence[:100]}")

        lines.append("")

    # Trusts with multiple signals (buying cluster)
    trust_counts: dict[str, int] = defaultdict(int)
    for s in weekly:
        trust_counts[s.entity_name] += 1

    multi_signal_trusts = {
        name: count for name, count in trust_counts.items() if count >= 2
    }

    if multi_signal_trusts:
        lines.append("## 🎯 Hot Trusts (Multiple Signals)")
        lines.append("")
        lines.append(
            "These trusts have multiple signals converging — "
            "highest priority for outreach."
        )
        lines.append("")
        for name, count in sorted(
            multi_signal_trusts.items(), key=lambda x: -x[1]
        ):
            trust_signals = [s for s in weekly if s.entity_name == name]
            categories = set(s.category.value for s in trust_signals)
            lines.append(
                f"- **{name}** — {count} signals across {', '.join(categories)}"
            )
        lines.append("")

    # Recommended next steps
    lines.append("## Recommended Next Steps")
    lines.append("")
    if high:
        lines.append(
            f"1. **Immediate action:** {len(high)} high-confidence signals "
            f"require outreach within 48 hours"
        )
    if medium:
        lines.append(
            f"2. **Nurture queue:** {len(medium)} medium-confidence signals "
            f"for monitoring and gentle engagement"
        )
    if multi_signal_trusts:
        lines.append(
            f"3. **Cluster review:** {len(multi_signal_trusts)} trusts with "
            f"converging signals — schedule battlecard reviews"
        )
    lines.append(
        f"4. **HITL review:** {len(low)} low-confidence signals pending "
        f"bi-weekly false-positive screening"
    )
    lines.append("")

    lines.append("---")
    lines.append(
        "*Generated by Zava Signal Intelligence Platform • "
        "Microsoft Agent Framework*"
    )

    return "\n".join(lines)
