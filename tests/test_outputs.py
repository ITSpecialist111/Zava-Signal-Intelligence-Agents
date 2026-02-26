"""Unit tests for output modules: teams_pulse, segment_brief, horizon_report."""

from __future__ import annotations

import json
from datetime import datetime


from src.models.signal import (
    ConfidenceLevel,
    Signal,
    SignalCategory,
    SignalSubcategory,
)
from src.outputs.teams_pulse import (
    build_battlecard_card,
    build_signal_card,
    render_card_json,
)
from src.outputs.segment_brief import generate_segment_brief


# ======================================================================== #
# Teams Pulse — Adaptive Cards
# ======================================================================== #


class TestBuildSignalCard:

    def test_card_structure(self, sample_signal):
        card = build_signal_card(sample_signal)
        assert card["type"] == "AdaptiveCard"
        assert card["version"] == "1.5"
        assert "$schema" in card

    def test_card_has_actions(self, sample_signal):
        card = build_signal_card(sample_signal)
        actions = card["actions"]
        assert len(actions) == 3  # Approve, Dismiss, Source link
        action_types = {a["title"] for a in actions}
        assert "✅ Approve" in action_types
        assert "❌ Dismiss" in action_types
        assert "🔗 Source" in action_types

    def test_card_entity_name(self, sample_signal):
        card = build_signal_card(sample_signal)
        body = card["body"]
        # Find the entity name text block
        column_set = body[0]
        entity_text = column_set["columns"][0]["items"][1]["text"]
        assert entity_text == "Harris Federation"

    def test_card_facts(self, sample_signal):
        card = build_signal_card(sample_signal)
        fact_set = card["body"][1]
        assert fact_set["type"] == "FactSet"
        fact_titles = {f["title"] for f in fact_set["facts"]}
        assert "Category" in fact_titles
        assert "Subcategory" in fact_titles
        assert "Source" in fact_titles
        assert "Playbook" in fact_titles

    def test_card_long_evidence_truncated(self):
        long_evidence = "A" * 500
        sig = Signal(
            signal_id="long",
            category=SignalCategory.STRUCTURAL_STRESS,
            subcategory=SignalSubcategory.HUB_AND_SPOKE,
            entity_name="Test",
            confidence=0.9,
            confidence_level=ConfidenceLevel.HIGH,
            source_url="http://test",
            source_name="Test",
            raw_evidence=long_evidence,
        )
        card = build_signal_card(sig)
        # Evidence preview should be truncated at 300 chars + "…"
        evidence_block = card["body"][3]
        assert evidence_block["text"].endswith("…")
        assert len(evidence_block["text"]) == 301  # 300 + "…"

    def test_card_submit_data(self, sample_signal):
        card = build_signal_card(sample_signal)
        approve_action = card["actions"][0]
        assert approve_action["data"]["action"] == "approve_signal"
        assert approve_action["data"]["signal_id"] == sample_signal.signal_id

    def test_card_confidence_colours(self, sample_signal, sample_signal_low, sample_signal_medium):
        # HIGH → "good"
        card_h = build_signal_card(sample_signal)
        conf_text = card_h["body"][0]["columns"][1]["items"][0]
        assert conf_text["color"] == "good"

        # LOW → "attention"
        card_l = build_signal_card(sample_signal_low)
        conf_text_l = card_l["body"][0]["columns"][1]["items"][0]
        assert conf_text_l["color"] == "attention"

        # MEDIUM → "warning"
        card_m = build_signal_card(sample_signal_medium)
        conf_text_m = card_m["body"][0]["columns"][1]["items"][0]
        assert conf_text_m["color"] == "warning"


class TestBuildBattlecardCard:

    def test_battlecard_card_structure(self, sample_battlecard):
        card = build_battlecard_card(sample_battlecard)
        assert card["type"] == "AdaptiveCard"
        assert card["version"] == "1.5"

    def test_battlecard_has_actions(self, sample_battlecard):
        card = build_battlecard_card(sample_battlecard)
        assert len(card["actions"]) == 2
        titles = {a["title"] for a in card["actions"]}
        assert "✅ Approve for Outreach" in titles
        assert "📝 Edit & Approve" in titles

    def test_battlecard_facts_include_entity(self, sample_battlecard):
        card = build_battlecard_card(sample_battlecard)
        fact_set = next(b for b in card["body"] if b.get("type") == "FactSet")
        fact_values = {f["title"]: f["value"] for f in fact_set["facts"]}
        assert fact_values["Trust"] == "Harris Federation"
        assert fact_values["Companies House"] == "07827865"

    def test_battlecard_competitor_section(self, sample_battlecard):
        card = build_battlecard_card(sample_battlecard)
        texts = [b.get("text", "") for b in card["body"]]
        assert "⚔️ Competitor Intelligence" in texts

    def test_battlecard_actions_section(self, sample_battlecard):
        card = build_battlecard_card(sample_battlecard)
        texts = [b.get("text", "") for b in card["body"]]
        assert "🎯 Recommended Actions" in texts


class TestRenderCardJson:

    def test_produces_valid_json(self, sample_signal):
        card = build_signal_card(sample_signal)
        json_str = render_card_json(card)
        parsed = json.loads(json_str)
        assert parsed["type"] == "AdaptiveCard"


# ======================================================================== #
# Segment Brief — Weekly Markdown
# ======================================================================== #


class TestSegmentBrief:

    def test_generates_markdown(self, weekly_signals):
        md = generate_segment_brief(weekly_signals)
        assert md.startswith("# Zava Signal Intelligence")
        assert "Weekly Brief" in md

    def test_executive_summary_counts(self, weekly_signals):
        md = generate_segment_brief(weekly_signals)
        assert "Total signals detected" in md

    def test_top_signals_table(self, weekly_signals):
        md = generate_segment_brief(weekly_signals)
        assert "| Trust | Category" in md

    def test_category_breakdown(self, weekly_signals):
        md = generate_segment_brief(weekly_signals)
        # At least one category should appear
        assert "###" in md

    def test_hot_trusts_section(self, weekly_signals):
        """Harris Federation has 2 signals so should appear as hot trust."""
        md = generate_segment_brief(weekly_signals)
        assert "Hot Trusts" in md
        assert "Harris Federation" in md

    def test_recommended_next_steps(self, weekly_signals):
        md = generate_segment_brief(weekly_signals)
        assert "Recommended Next Steps" in md

    def test_empty_signals_list(self):
        md = generate_segment_brief([])
        assert "Total signals detected:** 0" in md

    def test_custom_week_ending(self, weekly_signals):
        custom_date = datetime(2025, 6, 15)
        md = generate_segment_brief(weekly_signals, week_ending=custom_date)
        assert "15 June 2025" in md

    def test_footer_present(self, weekly_signals):
        md = generate_segment_brief(weekly_signals)
        assert "Microsoft Agent Framework" in md


# ======================================================================== #
# Horizon Report — Monthly PDF
# ======================================================================== #


class TestHorizonReport:

    def test_generates_pdf_bytes(self, weekly_signals):
        from src.outputs.horizon_report import generate_horizon_report

        pdf = generate_horizon_report(weekly_signals)
        assert isinstance(pdf, bytes)
        assert len(pdf) > 0
        # PDF magic bytes
        assert pdf[:5] == b"%PDF-"

    def test_pdf_with_feedback(self, weekly_signals, sample_feedback_won, sample_feedback_lost):
        from src.outputs.horizon_report import generate_horizon_report

        pdf = generate_horizon_report(
            weekly_signals,
            feedback_records=[sample_feedback_won, sample_feedback_lost],
        )
        assert pdf[:5] == b"%PDF-"

    def test_pdf_saves_to_file(self, weekly_signals, tmp_path):
        from src.outputs.horizon_report import generate_horizon_report

        output_file = tmp_path / "report.pdf"
        pdf = generate_horizon_report(weekly_signals, output_path=output_file)
        assert output_file.exists()
        assert output_file.read_bytes() == pdf

    def test_empty_signals_produces_pdf(self):
        from src.outputs.horizon_report import generate_horizon_report

        pdf = generate_horizon_report([])
        assert isinstance(pdf, bytes)
        assert pdf[:5] == b"%PDF-"
