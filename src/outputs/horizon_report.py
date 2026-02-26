"""Horizon Report — Monthly Strategic PDF.

Produces a board-ready PDF report with:
  - Signal heatmap by category and month
  - Win/Loss analysis trends
  - Competitor landscape shifts
  - Pipeline attribution from signals
  - Strategic recommendations

Uses reportlab for PDF generation.
"""

from __future__ import annotations

import io
import logging
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

from src.models.feedback import DealFeedback, DealOutcome
from src.models.signal import ConfidenceLevel, Signal, SignalCategory

logger = logging.getLogger(__name__)


def generate_horizon_report(
    signals: list[Signal],
    feedback_records: list[DealFeedback] | None = None,
    month_ending: datetime | None = None,
    output_path: str | Path | None = None,
) -> bytes:
    """Generate a monthly Horizon Report as PDF.

    Args:
        signals: All signals from the reporting period (ideally 3+ months).
        feedback_records: Win/Loss feedback for attribution analysis.
        month_ending: Last day of the reporting month (defaults to now).
        output_path: If provided, also save to this file path.

    Returns:
        PDF content as bytes.
    """
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import cm
        from reportlab.platypus import (
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )
    except ImportError:
        logger.error(
            "reportlab not installed. Install with: pip install reportlab"
        )
        raise

    if month_ending is None:
        month_ending = datetime.utcnow()
    month_starting = month_ending.replace(day=1)

    if feedback_records is None:
        feedback_records = []

    # Filter signals to reporting window (3-month lookback)
    lookback = month_ending - timedelta(days=90)
    period_signals = [s for s in signals if s.detected_at >= lookback]
    month_signals = [
        s for s in signals if month_starting <= s.detected_at <= month_ending
    ]

    # Build PDF
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        leftMargin=2.5 * cm,
        rightMargin=2.5 * cm,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ReportTitle",
        parent=styles["Title"],
        fontSize=22,
        spaceAfter=12,
        textColor=colors.HexColor("#1a1a2e"),
    )
    heading_style = ParagraphStyle(
        "ReportHeading",
        parent=styles["Heading1"],
        fontSize=16,
        spaceBefore=20,
        spaceAfter=8,
        textColor=colors.HexColor("#16213e"),
    )
    subheading_style = ParagraphStyle(
        "ReportSubheading",
        parent=styles["Heading2"],
        fontSize=13,
        spaceBefore=12,
        spaceAfter=6,
    )
    body_style = ParagraphStyle(
        "ReportBody",
        parent=styles["Normal"],
        fontSize=10,
        spaceAfter=6,
        leading=14,
    )

    elements: list = []

    # --- Colour palette for priority bands ---
    COLOR_HIGH = colors.HexColor("#c0392b")     # Red
    COLOR_MEDIUM = colors.HexColor("#e67e22")    # Amber
    COLOR_LOW = colors.HexColor("#7f8c8d")       # Grey
    COLOR_HIGH_BG = colors.HexColor("#fadbd8")
    COLOR_MEDIUM_BG = colors.HexColor("#fdebd0")
    COLOR_LOW_BG = colors.HexColor("#eaecee")

    PRIORITY_COLORS = {
        ConfidenceLevel.HIGH: (COLOR_HIGH, COLOR_HIGH_BG),
        ConfidenceLevel.MEDIUM: (COLOR_MEDIUM, COLOR_MEDIUM_BG),
        ConfidenceLevel.LOW: (COLOR_LOW, COLOR_LOW_BG),
    }

    PRIORITY_ICONS = {
        ConfidenceLevel.HIGH: "HIGH PRIORITY",
        ConfidenceLevel.MEDIUM: "MEDIUM PRIORITY",
        ConfidenceLevel.LOW: "LOW PRIORITY",
    }

    # Additional styles for signal cards
    card_title_style = ParagraphStyle(
        "CardTitle",
        parent=styles["Heading3"],
        fontSize=12,
        spaceBefore=4,
        spaceAfter=2,
        textColor=colors.HexColor("#1a1a2e"),
    )
    card_body_style = ParagraphStyle(
        "CardBody",
        parent=styles["Normal"],
        fontSize=9,
        spaceAfter=3,
        leading=12,
    )
    card_label_style = ParagraphStyle(
        "CardLabel",
        parent=styles["Normal"],
        fontSize=8,
        textColor=colors.HexColor("#555555"),
        spaceAfter=1,
    )
    badge_style_high = ParagraphStyle(
        "BadgeHigh", parent=styles["Normal"],
        fontSize=8, textColor=COLOR_HIGH,
    )
    badge_style_medium = ParagraphStyle(
        "BadgeMedium", parent=styles["Normal"],
        fontSize=8, textColor=COLOR_MEDIUM,
    )
    badge_style_low = ParagraphStyle(
        "BadgeLow", parent=styles["Normal"],
        fontSize=8, textColor=COLOR_LOW,
    )
    BADGE_STYLES = {
        ConfidenceLevel.HIGH: badge_style_high,
        ConfidenceLevel.MEDIUM: badge_style_medium,
        ConfidenceLevel.LOW: badge_style_low,
    }

    # Title page
    elements.append(Spacer(1, 3 * cm))
    elements.append(
        Paragraph("Zava Signal Intelligence", title_style)
    )
    elements.append(
        Paragraph(
            f"Horizon Report — {month_ending.strftime('%B %Y')}",
            heading_style,
        )
    )
    elements.append(Spacer(1, 1 * cm))
    elements.append(
        Paragraph(
            f"Reporting period: {lookback.strftime('%d %b %Y')} — "
            f"{month_ending.strftime('%d %b %Y')}",
            body_style,
        )
    )
    elements.append(
        Paragraph(
            f"Generated: {datetime.utcnow().strftime('%d %B %Y %H:%M UTC')}",
            body_style,
        )
    )
    elements.append(Spacer(1, 2 * cm))

    # Executive summary
    elements.append(Paragraph("Executive Summary", heading_style))

    high = len([s for s in month_signals if s.confidence_level == ConfidenceLevel.HIGH])
    medium = len([s for s in month_signals if s.confidence_level == ConfidenceLevel.MEDIUM])
    low = len([s for s in month_signals if s.confidence_level == ConfidenceLevel.LOW])
    wins = len([f for f in feedback_records if f.outcome == DealOutcome.WON])
    losses = len([f for f in feedback_records if f.outcome == DealOutcome.LOST])

    summary = (
        f"This month, the platform detected <b>{len(month_signals)}</b> signals "
        f"across UK education trusts. Of these, <b>{high}</b> were high confidence, "
        f"<b>{medium}</b> medium, and <b>{low}</b> low. "
        f"Win/Loss feedback: <b>{wins}</b> wins, <b>{losses}</b> losses."
    )
    elements.append(Paragraph(summary, body_style))
    elements.append(Spacer(1, 0.5 * cm))

    # Signal heatmap table
    elements.append(Paragraph("Signal Heatmap by Category", heading_style))

    heatmap_data = [["Category", "Total", "High", "Medium", "Low"]]
    for cat in SignalCategory:
        cat_signals = [s for s in month_signals if s.category == cat]
        h = len([s for s in cat_signals if s.confidence_level == ConfidenceLevel.HIGH])
        m = len([s for s in cat_signals if s.confidence_level == ConfidenceLevel.MEDIUM])
        lo = len([s for s in cat_signals if s.confidence_level == ConfidenceLevel.LOW])
        heatmap_data.append([cat.value, str(len(cat_signals)), str(h), str(m), str(lo)])

    heatmap_table = Table(heatmap_data, colWidths=[6 * cm, 2.5 * cm, 2 * cm, 2 * cm, 2 * cm])
    heatmap_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#16213e")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTSIZE", (0, 0), (-1, 0), 10),
                ("FONTSIZE", (0, 1), (-1, -1), 9),
                ("ALIGN", (1, 0), (-1, -1), "CENTER"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f0f0f0")]),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    elements.append(heatmap_table)
    elements.append(Spacer(1, 1 * cm))

    # Top trusts section
    elements.append(Paragraph("Top Trust Targets", heading_style))

    trust_counts: dict[str, int] = defaultdict(int)
    for s in month_signals:
        trust_counts[s.entity_name] += 1

    top_trusts = sorted(trust_counts.items(), key=lambda x: -x[1])[:10]

    if top_trusts:
        trust_data = [["Trust Name", "Signals", "Categories"]]
        for name, count in top_trusts:
            cats = set(
                s.category.value for s in month_signals if s.entity_name == name
            )
            trust_data.append([name, str(count), ", ".join(cats)])

        trust_table = Table(trust_data, colWidths=[6 * cm, 2 * cm, 7 * cm])
        trust_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#16213e")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f0f0f0")]),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        elements.append(trust_table)
    else:
        elements.append(Paragraph("No signals detected this month.", body_style))

    elements.append(Spacer(1, 1 * cm))

    # ================================================================== #
    # Signal Detail Cards — the "Know / Say / Show" layer
    # ================================================================== #
    elements.append(Paragraph("Signal Intelligence Cards", heading_style))
    elements.append(
        Paragraph(
            "Each signal below includes an impact assessment, recommended "
            "action, and talk track. Signals are ordered by priority "
            "(HIGH → MEDIUM → LOW).",
            body_style,
        )
    )
    elements.append(Spacer(1, 0.3 * cm))

    # Sort signals: HIGH first, then MEDIUM, then LOW
    priority_order = {ConfidenceLevel.HIGH: 0, ConfidenceLevel.MEDIUM: 1, ConfidenceLevel.LOW: 2}
    sorted_signals = sorted(
        month_signals,
        key=lambda s: (priority_order.get(s.confidence_level, 2), s.entity_name),
    )

    for sig in sorted_signals:
        fg_color, bg_color = PRIORITY_COLORS.get(
            sig.confidence_level, (COLOR_LOW, COLOR_LOW_BG)
        )
        badge_text = PRIORITY_ICONS.get(sig.confidence_level, "LOW PRIORITY")

        # ---- Card Header Row: badge + entity + category ----
        card_header_data = [[
            Paragraph(
                f"<b>{badge_text}</b>",
                BADGE_STYLES.get(sig.confidence_level, badge_style_low),
            ),
            Paragraph(
                f"<b>{sig.entity_name}</b>",
                card_title_style,
            ),
            Paragraph(
                f"{sig.category.value.replace('_', ' ').title()}",
                card_label_style,
            ),
        ]]
        card_header = Table(card_header_data, colWidths=[3.5 * cm, 7 * cm, 4.5 * cm])
        card_header.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), bg_color),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LINEBELOW", (0, 0), (-1, -1), 1.5, fg_color),
        ]))
        elements.append(card_header)

        # ---- Card Body: evidence, impact, action, talk track ----
        card_rows = []

        # Source + date
        source_text = (
            f"<b>Source:</b> {sig.source_name} · "
            f"{sig.detected_at.strftime('%d %b %Y')} · "
            f"Confidence: {sig.confidence:.0%}"
        )
        card_rows.append([Paragraph(source_text, card_label_style)])

        # Raw evidence / what was detected
        evidence = sig.raw_evidence[:300] if sig.raw_evidence else "No evidence captured"
        card_rows.append([Paragraph(
            f"<b>What was detected:</b> {evidence}",
            card_body_style,
        )])

        # Impact statement (the "So What")
        impact = getattr(sig, 'impact_statement', None) or (
            f"Signal indicates potential opportunity in {sig.category.value.replace('_', ' ').lower()} "
            f"for {sig.entity_name}."
        )
        card_rows.append([Paragraph(
            f"<b>Why this matters:</b> {impact}",
            card_body_style,
        )])

        # Playbook match
        if sig.playbook_match:
            card_rows.append([Paragraph(
                f"<b>Playbook:</b> {sig.playbook_match.value}",
                card_body_style,
            )])

        # Recommended action
        action = sig.recommended_action or "Review signal and determine approach"
        card_rows.append([Paragraph(
            f"<b>Recommended action:</b> {action}",
            card_body_style,
        )])

        # Talk track (the "Say")
        talk_track = getattr(sig, 'talk_track', None)
        if talk_track:
            card_rows.append([Paragraph(
                f"<b>Talk track:</b> <i>\"{talk_track}\"</i>",
                card_body_style,
            )])

        # Key decision maker
        if sig.key_decision_maker:
            card_rows.append([Paragraph(
                f"<b>Key contact:</b> {sig.key_decision_maker}",
                card_body_style,
            )])

        # Financial context
        if sig.financial_summary and len(sig.financial_summary) > 10:
            # Truncate to first 200 chars for the card
            fin_text = sig.financial_summary[:200]
            if len(sig.financial_summary) > 200:
                fin_text += "..."
            card_rows.append([Paragraph(
                f"<b>Financial context:</b> {fin_text}",
                card_body_style,
            )])

        # Handbook reference
        if sig.handbook_reference:
            card_rows.append([Paragraph(
                f"<b>Handbook ref:</b> {sig.handbook_reference}",
                card_label_style,
            )])

        card_body = Table(card_rows, colWidths=[15 * cm])
        card_body.setStyle(TableStyle([
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (0, 0), 4),
            ("BOTTOMPADDING", (0, -1), (0, -1), 6),
            ("TOPPADDING", (0, 1), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -2), 2),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#d5d8dc")),
        ]))
        elements.append(card_body)
        elements.append(Spacer(1, 0.4 * cm))

    elements.append(Spacer(1, 0.5 * cm))

    # Win/Loss analysis
    if feedback_records:
        elements.append(Paragraph("Win/Loss Analysis", heading_style))

        win_rate = wins / len(feedback_records) * 100 if feedback_records else 0
        elements.append(
            Paragraph(
                f"Overall win rate: <b>{win_rate:.1f}%</b> "
                f"({wins} won / {losses} lost out of {len(feedback_records)} total)",
                body_style,
            )
        )

        # Loss reasons breakdown

        loss_reasons: dict[str, int] = defaultdict(int)
        for f in feedback_records:
            if f.outcome == DealOutcome.LOST:
                for reason in f.loss_reasons:
                    loss_reasons[reason.value] += 1

        if loss_reasons:
            elements.append(Paragraph("Loss Reasons", subheading_style))
            loss_data = [["Reason", "Count"]]
            for reason, count in sorted(loss_reasons.items(), key=lambda x: -x[1]):
                loss_data.append([reason, str(count)])

            loss_table = Table(loss_data, colWidths=[10 * cm, 3 * cm])
            loss_table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#8b0000")),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                        ("FONTSIZE", (0, 0), (-1, -1), 9),
                        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                        ("TOPPADDING", (0, 0), (-1, -1), 3),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                    ]
                )
            )
            elements.append(loss_table)

    elements.append(Spacer(1, 1 * cm))

    # 3-month trend
    elements.append(Paragraph("3-Month Signal Trend", heading_style))

    month_buckets: dict[str, int] = defaultdict(int)
    for s in period_signals:
        bucket = s.detected_at.strftime("%Y-%m")
        month_buckets[bucket] += 1

    if month_buckets:
        trend_data = [["Month", "Signals"]]
        for month_key in sorted(month_buckets.keys()):
            trend_data.append([month_key, str(month_buckets[month_key])])

        trend_table = Table(trend_data, colWidths=[6 * cm, 4 * cm])
        trend_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#16213e")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("ALIGN", (1, 0), (-1, -1), "CENTER"),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        elements.append(trend_table)

    elements.append(Spacer(1, 1 * cm))

    # Strategic recommendations
    elements.append(Paragraph("Strategic Recommendations", heading_style))

    recommendations = _generate_recommendations(
        month_signals, period_signals, feedback_records
    )
    for i, rec in enumerate(recommendations, 1):
        elements.append(Paragraph(f"<b>{i}.</b> {rec}", body_style))

    elements.append(Spacer(1, 1 * cm))

    # Footer
    elements.append(
        Paragraph(
            "<i>Generated by Zava Signal Intelligence Platform · "
            "Microsoft Agent Framework · Confidential</i>",
            ParagraphStyle(
                "Footer",
                parent=body_style,
                fontSize=8,
                textColor=colors.grey,
            ),
        )
    )

    # Build PDF
    doc.build(elements)
    pdf_bytes = buffer.getvalue()
    buffer.close()

    # Optionally save to disk
    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(pdf_bytes)
        logger.info("Horizon report saved to %s", output_path)

    logger.info(
        "Horizon report generated: %d signals, %d pages, %d bytes",
        len(month_signals),
        doc.page,
        len(pdf_bytes),
    )

    return pdf_bytes


def _generate_recommendations(
    month_signals: list[Signal],
    period_signals: list[Signal],
    feedback_records: list[DealFeedback],
) -> list[str]:
    """Generate strategic recommendations based on data patterns."""
    recs: list[str] = []

    # Recommendation: hot categories
    cat_counts: dict[str, int] = defaultdict(int)
    for s in month_signals:
        cat_counts[s.category.value] += 1

    if cat_counts:
        hottest = max(cat_counts, key=cat_counts.get)  # type: ignore
        recs.append(
            f"<b>{hottest}</b> is the most active signal category this month "
            f"with {cat_counts[hottest]} signals — consider increasing "
            f"collection frequency for related sources."
        )

    # Recommendation: multi-signal trusts
    trust_counts: dict[str, int] = defaultdict(int)
    for s in month_signals:
        trust_counts[s.entity_name] += 1

    hot_trusts = [n for n, c in trust_counts.items() if c >= 3]
    if hot_trusts:
        recs.append(
            f"{len(hot_trusts)} trusts have 3+ converging signals — "
            f"prioritise these for immediate outreach: {', '.join(hot_trusts[:5])}."
        )

    # Recommendation: win rate trend
    if len(feedback_records) >= 5:
        wins = sum(1 for f in feedback_records if f.outcome == DealOutcome.WON)
        win_rate = wins / len(feedback_records)
        if win_rate >= 0.5:
            recs.append(
                f"Signal-to-win conversion rate is strong at {win_rate:.0%}. "
                f"Consider expanding to additional trust segments."
            )
        else:
            recs.append(
                f"Signal-to-win conversion rate is {win_rate:.0%}. "
                f"Review loss reasons and adjust confidence thresholds."
            )

    # Recommendation: volume trend
    if len(period_signals) > len(month_signals) * 3:
        recs.append(
            "Signal volume is declining month-over-month. "
            "Consider adding new sweep targets or broadening search keywords."
        )
    elif len(month_signals) > len(period_signals) / 2:
        recs.append(
            "Signal volume is accelerating. "
            "Consider increasing HITL review frequency to maintain quality."
        )

    if not recs:
        recs.append(
            "Insufficient data for actionable recommendations. "
            "Continue collecting signals and feedback for at least 3 months."
        )

    return recs
