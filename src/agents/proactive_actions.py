"""Proactive M365 Actions — autonomous signal distribution via MCP servers.

After each sweep (or on-demand), the agent uses Agent 365 governed MCP
servers to proactively distribute intelligence across M365:

  Mail     → Daily digests, instant HIGH alerts, weekly briefs
  Calendar → Review meetings for HITL signals, follow-up calls
  Teams    → Channel alerts, discussion threads
  Word     → Structured reports as Word documents
  Planner  → Action tasks from approved signals
  Excel    → Pipeline tracker updates
  SharePoint → Report storage and signal lists

Each function generates the *content* and returns it as structured data
that the interactive agent tools can pass to the MCP servers. The MCP
servers handle the actual M365 API calls under governed identity.

Ref: https://learn.microsoft.com/microsoft-365/agents/a365-governed-mcp-servers
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

from src.config_teams import ProactiveConfig
from src.models.signal import ConfidenceLevel, Signal

logger = logging.getLogger(__name__)


# ───────────────────────────────────────────────────────────────────
# EMAIL: Daily digest
# ───────────────────────────────────────────────────────────────────

def build_daily_digest_email(
    signals: list[Signal],
    sweep_summary: dict,
    config: ProactiveConfig,
) -> dict:
    """Build the daily digest email content.

    Returns a dict with subject, html_body, and recipients that the
    agent can pass to the Mail MCP server.
    """
    today = datetime.utcnow().strftime("%d %b %Y")
    recipients = config.digest_recipients()

    if not recipients:
        return {"skipped": True, "reason": "No digest recipients configured"}

    # Group signals by category
    by_category: dict[str, list[Signal]] = {}
    for s in signals:
        cat = s.category.value
        by_category.setdefault(cat, []).append(s)

    # Build HTML email
    html = _digest_html(signals, by_category, sweep_summary, today)

    subject = config.digest_subject_template.format(
        date=today, signal_count=len(signals)
    )

    return {
        "subject": subject,
        "html_body": html,
        "recipients": [r.email for r in recipients],
        "importance": "high" if any(
            s.confidence_level == ConfidenceLevel.HIGH for s in signals
        ) else "normal",
    }


def _digest_html(
    signals: list[Signal],
    by_category: dict[str, list[Signal]],
    sweep_summary: dict,
    date: str,
) -> str:
    """Generate the HTML body for the daily digest email."""
    high = sum(1 for s in signals if s.confidence_level == ConfidenceLevel.HIGH)
    medium = sum(1 for s in signals if s.confidence_level == ConfidenceLevel.MEDIUM)
    low = sum(1 for s in signals if s.confidence_level == ConfidenceLevel.LOW)

    # Category rows
    cat_rows = ""
    for cat, sigs in sorted(by_category.items(), key=lambda x: -len(x[1])):
        cat_rows += f"""
        <tr>
            <td style="padding:8px;border-bottom:1px solid #eee;font-weight:600">{cat}</td>
            <td style="padding:8px;border-bottom:1px solid #eee;text-align:center">{len(sigs)}</td>
            <td style="padding:8px;border-bottom:1px solid #eee">{', '.join(s.entity_name for s in sigs[:3])}{'…' if len(sigs) > 3 else ''}</td>
        </tr>"""

    # Top signals table
    top_signals = sorted(signals, key=lambda s: s.confidence, reverse=True)[:10]
    signal_rows = ""
    for s in top_signals:
        conf_color = "#28a745" if s.confidence >= 0.8 else "#ffc107" if s.confidence >= 0.5 else "#dc3545"
        signal_rows += f"""
        <tr>
            <td style="padding:6px 8px;border-bottom:1px solid #f0f0f0">{s.entity_name}</td>
            <td style="padding:6px 8px;border-bottom:1px solid #f0f0f0">{s.category.value}</td>
            <td style="padding:6px 8px;border-bottom:1px solid #f0f0f0;text-align:center">
                <span style="background:{conf_color};color:white;padding:2px 8px;border-radius:12px;font-size:12px">{s.confidence:.0%}</span>
            </td>
            <td style="padding:6px 8px;border-bottom:1px solid #f0f0f0">{s.status.value}</td>
            <td style="padding:6px 8px;border-bottom:1px solid #f0f0f0;font-size:12px">{s.recommended_action or '—'}</td>
        </tr>"""

    hitl_pending = [s for s in signals if s.status.value == "HITL_PENDING"]
    hitl_section = ""
    if hitl_pending:
        hitl_section = f"""
        <div style="background:#fff3cd;border:1px solid #ffc107;border-radius:8px;padding:16px;margin:16px 0">
            <strong>⚠️ {len(hitl_pending)} signal(s) awaiting HITL review</strong>
            <p style="margin:8px 0 0">Open the Zava Signal Intel agent in Teams to approve or reject these signals.</p>
        </div>"""

    return f"""
    <div style="font-family:'Segoe UI',Arial,sans-serif;max-width:700px;margin:0 auto">
        <div style="background:linear-gradient(135deg,#1a237e,#283593);color:white;padding:24px;border-radius:8px 8px 0 0">
            <h1 style="margin:0;font-size:22px">📊 Signal Intelligence Digest</h1>
            <p style="margin:8px 0 0;opacity:0.9">{date} — Zava Public Sector Intelligence</p>
        </div>

        <div style="padding:20px;background:#f8f9fa;border:1px solid #e0e0e0">
            <div style="display:flex;gap:16px;text-align:center">
                <div style="flex:1;background:white;padding:16px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.1)">
                    <div style="font-size:28px;font-weight:700;color:#1a237e">{len(signals)}</div>
                    <div style="font-size:12px;color:#666">Total Signals</div>
                </div>
                <div style="flex:1;background:white;padding:16px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.1)">
                    <div style="font-size:28px;font-weight:700;color:#28a745">{high}</div>
                    <div style="font-size:12px;color:#666">High Confidence</div>
                </div>
                <div style="flex:1;background:white;padding:16px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.1)">
                    <div style="font-size:28px;font-weight:700;color:#ffc107">{medium}</div>
                    <div style="font-size:12px;color:#666">Medium</div>
                </div>
                <div style="flex:1;background:white;padding:16px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.1)">
                    <div style="font-size:28px;font-weight:700;color:#dc3545">{low}</div>
                    <div style="font-size:12px;color:#666">Low</div>
                </div>
            </div>
        </div>

        <div style="padding:20px;background:white;border:1px solid #e0e0e0;border-top:none">
            <h2 style="margin:0 0 12px;font-size:16px;color:#333">Category Breakdown</h2>
            <table style="width:100%;border-collapse:collapse">
                <tr style="background:#f8f9fa">
                    <th style="padding:8px;text-align:left;font-size:13px">Category</th>
                    <th style="padding:8px;text-align:center;font-size:13px">Count</th>
                    <th style="padding:8px;text-align:left;font-size:13px">Key Trusts</th>
                </tr>
                {cat_rows}
            </table>
        </div>

        <div style="padding:20px;background:white;border:1px solid #e0e0e0;border-top:none">
            <h2 style="margin:0 0 12px;font-size:16px;color:#333">Top Signals</h2>
            <table style="width:100%;border-collapse:collapse;font-size:13px">
                <tr style="background:#f8f9fa">
                    <th style="padding:6px 8px;text-align:left">Trust</th>
                    <th style="padding:6px 8px;text-align:left">Category</th>
                    <th style="padding:6px 8px;text-align:center">Confidence</th>
                    <th style="padding:6px 8px;text-align:left">Status</th>
                    <th style="padding:6px 8px;text-align:left">Action</th>
                </tr>
                {signal_rows}
            </table>
        </div>

        {hitl_section}

        <div style="padding:16px;background:#f8f9fa;border:1px solid #e0e0e0;border-top:none;border-radius:0 0 8px 8px;text-align:center;font-size:12px;color:#999">
            <p>Generated by Zava Signal Intelligence Agent • {date}</p>
            <p>Open the agent in Teams for interactive analysis and signal management</p>
        </div>
    </div>"""


# ───────────────────────────────────────────────────────────────────
# EMAIL: Instant HIGH alert
# ───────────────────────────────────────────────────────────────────

def build_high_alert_email(
    signal: Signal,
    config: ProactiveConfig,
) -> dict:
    """Build an instant email alert for a HIGH-confidence signal.

    Sent immediately when a signal scores ≥80% confidence so the
    team can act before the next digest.
    """
    recipients = config.alert_recipients()
    # Also include category-specific stakeholders
    cat_recipients = config.stakeholders_for_category(signal.category.value)
    all_emails = list({r.email for r in recipients + cat_recipients})

    if not all_emails:
        return {"skipped": True, "reason": "No alert recipients configured"}

    subject = config.alert_subject_template.format(
        entity_name=signal.entity_name,
        category=signal.category.value,
    )

    html = f"""
    <div style="font-family:'Segoe UI',Arial,sans-serif;max-width:600px;margin:0 auto">
        <div style="background:#d32f2f;color:white;padding:20px;border-radius:8px 8px 0 0">
            <h1 style="margin:0;font-size:20px">⚡ HIGH Confidence Signal Detected</h1>
        </div>
        <div style="padding:20px;background:white;border:1px solid #e0e0e0">
            <h2 style="margin:0 0 16px;color:#1a237e">{signal.entity_name}</h2>
            <table style="width:100%;border-collapse:collapse;font-size:14px">
                <tr><td style="padding:8px 0;font-weight:600;width:140px">Category</td><td>{signal.category.value}</td></tr>
                <tr><td style="padding:8px 0;font-weight:600">Subcategory</td><td>{signal.subcategory.value}</td></tr>
                <tr><td style="padding:8px 0;font-weight:600">Confidence</td><td><span style="background:#28a745;color:white;padding:2px 10px;border-radius:12px">{signal.confidence:.0%}</span></td></tr>
                <tr><td style="padding:8px 0;font-weight:600">Source</td><td><a href="{signal.source_url}">{signal.source_name}</a></td></tr>
                <tr><td style="padding:8px 0;font-weight:600">Detected</td><td>{signal.detected_at.strftime('%d %b %Y %H:%M UTC')}</td></tr>
                {'<tr><td style="padding:8px 0;font-weight:600">Current Provider</td><td>' + signal.current_provider + '</td></tr>' if signal.current_provider else ''}
                {'<tr><td style="padding:8px 0;font-weight:600">Key Contact</td><td>' + signal.key_decision_maker + '</td></tr>' if signal.key_decision_maker else ''}
                {'<tr><td style="padding:8px 0;font-weight:600">Playbook</td><td>' + signal.playbook_match.value + '</td></tr>' if signal.playbook_match else ''}
            </table>

            {'<div style="background:#e8f5e9;border-left:4px solid #28a745;padding:12px;margin:16px 0"><strong>Recommended Action:</strong> ' + signal.recommended_action + '</div>' if signal.recommended_action else ''}
            {'<div style="background:#e3f2fd;border-left:4px solid #1976d2;padding:12px;margin:16px 0"><strong>Talk Track:</strong> ' + signal.talk_track + '</div>' if signal.talk_track else ''}

            <div style="background:#f5f5f5;padding:12px;border-radius:4px;margin:16px 0">
                <strong>Evidence:</strong>
                <p style="margin:8px 0 0;font-size:13px;color:#555">{signal.raw_evidence[:500]}</p>
            </div>
        </div>
        <div style="padding:12px;background:#f8f9fa;border:1px solid #e0e0e0;border-top:none;border-radius:0 0 8px 8px;text-align:center;font-size:12px;color:#999">
            Open the Zava Signal Intel agent in Teams to review and discuss this signal
        </div>
    </div>"""

    return {
        "subject": subject,
        "html_body": html,
        "recipients": all_emails,
        "importance": "high",
    }


# ───────────────────────────────────────────────────────────────────
# CALENDAR: Schedule review meeting
# ───────────────────────────────────────────────────────────────────

def build_review_meeting(
    signals_for_review: list[Signal],
    config: ProactiveConfig,
    meeting_time: Optional[datetime] = None,
) -> dict:
    """Build a calendar meeting invite for HITL signal review.

    Called when there are signals pending human review — schedules
    a 30-minute review session with the relevant stakeholders.
    """
    if not signals_for_review:
        return {"skipped": True, "reason": "No signals pending review"}

    # Default: schedule for next business day at 10:00
    if meeting_time is None:
        now = datetime.utcnow()
        # Next business day
        days_ahead = 1
        candidate = now + timedelta(days=days_ahead)
        while candidate.weekday() >= 5:  # Skip weekend
            days_ahead += 1
            candidate = now + timedelta(days=days_ahead)
        meeting_time = candidate.replace(hour=10, minute=0, second=0, microsecond=0)

    end_time = meeting_time + timedelta(
        minutes=config.review_meeting_duration_minutes
    )

    # Determine attendees — all stakeholders who receive alerts
    attendees = [s.email for s in config.alert_recipients()]
    if not attendees:
        attendees = [s.email for s in config.all_stakeholders[:5]]

    # Build agenda with signal details
    categories = set(s.category.value for s in signals_for_review)
    title = f"Signal Review: {len(signals_for_review)} signals across {', '.join(categories)}"

    agenda_lines = [
        f"# Signal Review — {meeting_time.strftime('%d %b %Y')}",
        "",
        f"**{len(signals_for_review)} signals require human review.**",
        "",
        "## Signals for Discussion",
        "",
    ]
    for i, s in enumerate(signals_for_review, 1):
        agenda_lines.append(
            f"{i}. **{s.entity_name}** — {s.category.value} "
            f"({s.confidence:.0%} confidence)"
        )
        if s.recommended_action:
            agenda_lines.append(f"   - Action: {s.recommended_action}")
        agenda_lines.append("")

    agenda_lines.extend([
        "## Meeting Objective",
        "- Review each signal and decide: **Approve** or **Reject**",
        "- Assign follow-up actions to team members",
        "- Update the Zava Signal Intel agent with decisions",
    ])

    return {
        "subject": title,
        "start_time": meeting_time.isoformat() + "Z",
        "end_time": end_time.isoformat() + "Z",
        "attendees": list(set(attendees)),
        "body": "\n".join(agenda_lines),
        "is_online_meeting": True,
        "importance": "high" if len(signals_for_review) > 3 else "normal",
    }


# ───────────────────────────────────────────────────────────────────
# WORD: Generate Word document report
# ───────────────────────────────────────────────────────────────────

def build_word_report_content(
    signals: list[Signal],
    sweep_summary: Optional[dict] = None,
) -> dict:
    """Build structured content for a colour-coded Word document report.

    Returns content sections that ``_render_docx`` converts into a
    professionally formatted .docx with category colour coding,
    confidence heat indicators, and KPI metric boxes.
    """
    today = datetime.utcnow()
    high_signals = [s for s in signals if s.confidence_level == ConfidenceLevel.HIGH]
    medium_signals = [s for s in signals if s.confidence_level == ConfidenceLevel.MEDIUM]
    low_signals = [s for s in signals if s.confidence_level == ConfidenceLevel.LOW]
    by_category: dict[str, list[Signal]] = {}
    for s in signals:
        by_category.setdefault(s.category.value, []).append(s)
    unique_trusts = len(set(s.entity_name for s in signals))

    # Category colour map (matches _CATEGORY_HEX in interactive_tools.py)
    _CAT_HEX = {
        "STRUCTURAL_STRESS":    "C0392B",
        "COMPLIANCE_TRAP":      "E67E22",
        "COMPETITOR_MOVEMENT":  "8E44AD",
        "PROCUREMENT_SHIFT":    "2980B9",
        "LEADERSHIP_CHANGE":    "27AE60",
    }

    sections: list[dict] = [
        # ── Cover page ─────────────────────────────────────────────
        {
            "type": "title",
            "text": "Zava Signal Intelligence Report",
        },
        {
            "type": "subtitle",
            "text": f"UK Education Trust Market Intelligence — {today.strftime('%B %Y')}",
        },
        {
            "type": "subtitle",
            "text": f"Generated {today.strftime('%d %B %Y %H:%M UTC')}  ·  CONFIDENTIAL",
        },
        {"type": "page_break"},
        # ── Executive summary ──────────────────────────────────────
        {
            "type": "heading1",
            "text": "Executive Summary",
        },
        {
            "type": "paragraph",
            "text": (
                f"This report presents {len(signals)} signals detected across "
                f"the UK education trust landscape covering {unique_trusts} "
                f"unique trusts. {len(high_signals)} signals are rated HIGH "
                f"confidence, indicating strong procurement indicators that "
                f"warrant immediate sales-team attention. {len(medium_signals)} "
                f"are rated MEDIUM and are recommended for HITL review."
            ),
        },
        # ── KPI metric boxes ──────────────────────────────────────
        {
            "type": "kpi_row",
            "items": [
                {"label": "Total Signals", "value": str(len(signals)),
                 "color": "2980B9", "bg": "D4E6F1"},
                {"label": "HIGH Confidence", "value": str(len(high_signals)),
                 "color": "E74C3C", "bg": "FADBD8"},
                {"label": "MEDIUM", "value": str(len(medium_signals)),
                 "color": "F39C12", "bg": "FDEBD0"},
                {"label": "Unique Trusts", "value": str(unique_trusts),
                 "color": "27AE60", "bg": "D5F5E3"},
            ],
        },
        # ── Signal heat\u2011map summary ──────────────────────────────
        {
            "type": "heading1",
            "text": "Signal Priority Matrix",
        },
        {
            "type": "table",
            "headers": ["Category", "Signals", "HIGH", "MEDIUM", "LOW", "Top Trust"],
            "rows": [
                [
                    cat.replace("_", " ").title(),
                    str(len(sigs)),
                    str(sum(1 for s in sigs if s.confidence >= 0.8)),
                    str(sum(1 for s in sigs if 0.5 <= s.confidence < 0.8)),
                    str(sum(1 for s in sigs if s.confidence < 0.5)),
                    max(sigs, key=lambda s: s.confidence).entity_name,
                ]
                for cat, sigs in sorted(by_category.items(), key=lambda x: -len(x[1]))
            ],
        },
    ]

    # ── Category deep-dive sections ───────────────────────────────
    for cat, sigs in sorted(by_category.items(), key=lambda x: -len(x[1])):
        sigs_sorted = sorted(sigs, key=lambda s: s.confidence, reverse=True)
        cat_color = _CAT_HEX.get(cat, "2980B9")

        sections.append({"type": "page_break"})
        sections.append({
            "type": "heading1",
            "text": cat.replace("_", " ").title(),
            "category": cat,
        })
        sections.append({
            "type": "paragraph",
            "text": (
                f"{len(sigs)} signal(s) detected. "
                f"{sum(1 for s in sigs if s.confidence >= 0.8)} rated HIGH, "
                f"{sum(1 for s in sigs if 0.5 <= s.confidence < 0.8)} MEDIUM, "
                f"{sum(1 for s in sigs if s.confidence < 0.5)} LOW."
            ),
            "category": cat,
        })
        sections.append({
            "type": "table",
            "category": cat,
            "headers": [
                "Trust", "Subcategory", "Confidence",
                "Status", "Source", "Recommended Action",
            ],
            "rows": [
                [
                    s.entity_name,
                    s.subcategory.value.replace("_", " ").title(),
                    f"{s.confidence:.0%} ({s.confidence_level.value})",
                    s.status.value,
                    s.source_name,
                    s.recommended_action or "\u2014",
                ]
                for s in sigs_sorted
            ],
        })

        # Detail boxes for HIGH signals
        for s in sigs_sorted:
            if s.confidence_level != ConfidenceLevel.HIGH:
                continue

            sections.append({
                "type": "heading2",
                "text": f"\u26a0 {s.entity_name}  \u2014  {s.confidence:.0%} Confidence",
                "category": cat,
            })
            detail_parts = [
                f"Signal ID: {s.signal_id}",
                f"Detected: {s.detected_at.strftime('%d %b %Y')}",
                f"Source: {s.source_name} ({s.source_url})",
            ]
            if s.current_provider:
                detail_parts.append(f"Current Provider: {s.current_provider}")
            if s.key_decision_maker:
                detail_parts.append(f"Key Contact: {s.key_decision_maker}")
            if s.financial_summary:
                detail_parts.append(f"Financials: {s.financial_summary}")
            if s.playbook_match:
                detail_parts.append(f"Playbook: {s.playbook_match.value}")
            if s.impact_statement:
                detail_parts.append(f"Impact: {s.impact_statement}")
            if s.talk_track:
                detail_parts.append(f"Talk Track: {s.talk_track}")

            sections.append({
                "type": "paragraph",
                "text": "\n".join(detail_parts),
                "category": cat,
            })

            if s.raw_evidence:
                sections.append({
                    "type": "quote",
                    "text": s.raw_evidence[:500],
                    "category": cat,
                })

    # ── Appendix ──────────────────────────────────────────────────
    sections.append({"type": "page_break"})
    sections.append({
        "type": "heading1",
        "text": "Appendix: Methodology",
    })
    sections.append({
        "type": "paragraph",
        "text": (
            "Signals are collected from Companies House filings, procurement "
            "portals (Contracts Finder, Find a Tender), industry press (TES, "
            "SchoolsWeek), and enriched using Azure AI Foundry (gpt-4o). "
            "Confidence scoring uses multi-factor assessment: source "
            "reliability, corroboration count, recency, and specificity."
        ),
    })
    sections.append({
        "type": "heading1",
        "text": "Appendix: Colour Key",
    })
    sections.append({
        "type": "table",
        "headers": ["Category", "Colour"],
        "rows": [
            [cat.replace("_", " ").title(), f"#{hex_val}"]
            for cat, hex_val in _CAT_HEX.items()
        ],
    })
    sections.append({
        "type": "table",
        "headers": ["Confidence", "Indicator"],
        "rows": [
            ["HIGH (\u226580%)", "Red background \u2014 immediate action"],
            ["MEDIUM (50\u201379%)", "Amber background \u2014 HITL review"],
            ["LOW (<50%)", "Green background \u2014 monitor"],
        ],
    })

    return {
        "filename": f"Signal_Intelligence_Report_{today.strftime('%Y%m%d')}.docx",
        "sections": sections,
    }


# ───────────────────────────────────────────────────────────────────
# PLANNER: Create action tasks
# ───────────────────────────────────────────────────────────────────

def build_planner_tasks(
    approved_signals: list[Signal],
    config: ProactiveConfig,
) -> list[dict]:
    """Build Planner tasks for approved signals.

    Each approved signal with a recommended action becomes a task
    assigned to the relevant team, with the signal detail as notes.
    """
    tasks = []
    now = datetime.utcnow()
    due = now + timedelta(days=config.task_due_days)

    for signal in approved_signals:
        if not signal.recommended_action:
            continue

        title = config.task_title_template.format(
            entity_name=signal.entity_name,
            recommended_action=signal.recommended_action[:80],
        )

        notes_lines = [
            f"Signal ID: {signal.signal_id}",
            f"Category: {signal.category.value} / {signal.subcategory.value}",
            f"Confidence: {signal.confidence:.0%}",
            f"Source: {signal.source_name}",
            f"Detected: {signal.detected_at.strftime('%d %b %Y')}",
        ]
        if signal.current_provider:
            notes_lines.append(f"Current Provider: {signal.current_provider}")
        if signal.key_decision_maker:
            notes_lines.append(f"Key Contact: {signal.key_decision_maker}")
        if signal.playbook_match:
            notes_lines.append(f"Playbook: {signal.playbook_match.value}")
        if signal.talk_track:
            notes_lines.append(f"\nTalk Track:\n{signal.talk_track}")
        if signal.impact_statement:
            notes_lines.append(f"\nImpact:\n{signal.impact_statement}")

        # Assign to stakeholders interested in this category
        cat_stakeholders = config.stakeholders_for_category(
            signal.category.value
        )
        assignees = [s.email for s in cat_stakeholders[:3]]

        tasks.append({
            "title": title,
            "due_date": due.strftime("%Y-%m-%d"),
            "notes": "\n".join(notes_lines),
            "priority": "urgent" if signal.confidence >= 0.9 else "important",
            "assignees": assignees,
            "labels": [signal.category.value, signal.subcategory.value],
            "signal_id": signal.signal_id,
        })

    return tasks


# ───────────────────────────────────────────────────────────────────
# EXCEL: Pipeline tracker data
# ───────────────────────────────────────────────────────────────────

def build_excel_pipeline_data(
    signals: list[Signal],
) -> dict:
    """Build data for an Excel pipeline tracker spreadsheet.

    Creates a table of all signals suitable for the Excel MCP server
    to write into a tracking workbook.
    """
    headers = [
        "Signal ID", "Trust Name", "Category", "Subcategory",
        "Confidence", "Confidence Level", "Status", "Source",
        "Source URL", "Detected", "Current Provider",
        "Key Contact", "Playbook", "Recommended Action",
        "Impact Statement",
    ]

    rows = []
    for s in sorted(signals, key=lambda x: x.confidence, reverse=True):
        rows.append([
            s.signal_id,
            s.entity_name,
            s.category.value,
            s.subcategory.value,
            f"{s.confidence:.2f}",
            s.confidence_level.value,
            s.status.value,
            s.source_name,
            s.source_url,
            s.detected_at.strftime("%Y-%m-%d %H:%M"),
            s.current_provider or "",
            s.key_decision_maker or "",
            s.playbook_match.value if s.playbook_match else "",
            s.recommended_action or "",
            s.impact_statement or "",
        ])

    return {
        "filename": f"Signal_Pipeline_{datetime.utcnow().strftime('%Y%m%d')}.xlsx",
        "sheet_name": "Signal Pipeline",
        "headers": headers,
        "rows": rows,
    }


# ───────────────────────────────────────────────────────────────────
# TEAMS: Channel notification
# ───────────────────────────────────────────────────────────────────

def build_teams_channel_message(
    signals: list[Signal],
    sweep_summary: dict,
) -> dict:
    """Build a Teams channel message summarising the sweep results.

    Uses Adaptive Card format for a rich, interactive notification
    in the team's signal intelligence channel.
    """
    today = datetime.utcnow().strftime("%d %b %Y %H:%M UTC")
    high_signals = [s for s in signals if s.confidence_level == ConfidenceLevel.HIGH]
    hitl_pending = [s for s in signals if s.status.value == "HITL_PENDING"]

    # Build Adaptive Card
    card = {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.5",
        "body": [
            {
                "type": "TextBlock",
                "text": "📊 Signal Intelligence Sweep Complete",
                "weight": "Bolder",
                "size": "Large",
            },
            {
                "type": "TextBlock",
                "text": today,
                "spacing": "None",
                "isSubtle": True,
            },
            {
                "type": "ColumnSet",
                "columns": [
                    {
                        "type": "Column",
                        "width": "stretch",
                        "items": [
                            {"type": "TextBlock", "text": "Total", "isSubtle": True},
                            {"type": "TextBlock", "text": str(len(signals)), "size": "ExtraLarge", "weight": "Bolder"},
                        ],
                    },
                    {
                        "type": "Column",
                        "width": "stretch",
                        "items": [
                            {"type": "TextBlock", "text": "High", "isSubtle": True},
                            {"type": "TextBlock", "text": str(len(high_signals)), "size": "ExtraLarge", "weight": "Bolder", "color": "Good"},
                        ],
                    },
                    {
                        "type": "Column",
                        "width": "stretch",
                        "items": [
                            {"type": "TextBlock", "text": "Review", "isSubtle": True},
                            {"type": "TextBlock", "text": str(len(hitl_pending)), "size": "ExtraLarge", "weight": "Bolder", "color": "Warning"},
                        ],
                    },
                ],
            },
        ],
    }

    # Add top HIGH signals
    if high_signals:
        card["body"].append({
            "type": "TextBlock",
            "text": "🎯 High-Confidence Signals",
            "weight": "Bolder",
            "spacing": "Large",
        })
        for s in high_signals[:5]:
            card["body"].append({
                "type": "ColumnSet",
                "columns": [
                    {
                        "type": "Column",
                        "width": "stretch",
                        "items": [{
                            "type": "TextBlock",
                            "text": f"**{s.entity_name}** — {s.category.value}",
                        }],
                    },
                    {
                        "type": "Column",
                        "width": "auto",
                        "items": [{
                            "type": "TextBlock",
                            "text": f"{s.confidence:.0%}",
                            "color": "Good",
                            "weight": "Bolder",
                        }],
                    },
                ],
            })

    # HITL reminder
    if hitl_pending:
        card["body"].append({
            "type": "TextBlock",
            "text": f"⚠️ {len(hitl_pending)} signal(s) awaiting review — ask the agent to show the HITL queue",
            "color": "Warning",
            "spacing": "Large",
            "wrap": True,
        })

    return {
        "adaptive_card": card,
        "summary": f"Signal sweep: {len(signals)} signals, {len(high_signals)} high confidence",
    }


# ───────────────────────────────────────────────────────────────────
# SHAREPOINT: Upload report
# ───────────────────────────────────────────────────────────────────

def build_sharepoint_upload(
    report_path: str,
    config: ProactiveConfig,
) -> dict:
    """Build metadata for uploading a report to SharePoint."""
    return {
        "file_path": report_path,
        "destination_folder": config.report_sharepoint_folder,
        "metadata": {
            "Title": f"Signal Report — {datetime.utcnow().strftime('%B %Y')}",
            "Category": "Signal Intelligence",
            "Generated": datetime.utcnow().isoformat(),
        },
    }
