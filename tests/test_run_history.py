"""Tests for RunHistory — sweep run tracking and comparison."""

from __future__ import annotations

import json


from src.tools.run_history import RunHistory


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #

def _make_summary(
    *,
    total_detected: int = 20,
    after_dedup: int = 17,
    enriched: int = 17,
    auto_activated: int = 12,
    hitl_pending: int = 5,
    errors: list | None = None,
    sweep_id: str = "test-sweep-1",
) -> dict:
    return {
        "sweep_id": sweep_id,
        "timestamp": "2026-02-21T12:00:00",
        "total_detected": total_detected,
        "after_dedup": after_dedup,
        "enriched": enriched,
        "auto_activated": auto_activated,
        "hitl_pending": hitl_pending,
        "errors": errors or [],
        "category_breakdown": {
            "LEADERSHIP_CHANGE": 5,
            "COMPETITOR_MOVEMENT": 3,
        },
    }


# ------------------------------------------------------------------ #
# Tests
# ------------------------------------------------------------------ #

class TestRunHistory:
    def test_record_first_run(self, tmp_path):
        h = RunHistory(tmp_path / "history.json")
        assert h.count == 0

        record = h.record(_make_summary())
        assert record["run_number"] == 1
        assert h.count == 1
        assert h.latest is not None
        assert h.latest["run_number"] == 1

    def test_record_multiple_runs(self, tmp_path):
        h = RunHistory(tmp_path / "history.json")
        h.record(_make_summary(total_detected=10, sweep_id="s1"))
        h.record(_make_summary(total_detected=20, sweep_id="s2"))
        h.record(_make_summary(total_detected=30, sweep_id="s3"))

        assert h.count == 3
        assert h.latest["total_detected"] == 30
        assert h.previous["total_detected"] == 20

    def test_previous_is_none_for_first_run(self, tmp_path):
        h = RunHistory(tmp_path / "history.json")
        h.record(_make_summary())
        assert h.previous is None

    def test_last_n(self, tmp_path):
        h = RunHistory(tmp_path / "history.json")
        for i in range(7):
            h.record(_make_summary(sweep_id=f"s{i}"))
        last_3 = h.last_n(3)
        assert len(last_3) == 3
        assert last_3[0]["run_number"] == 5
        assert last_3[2]["run_number"] == 7

    def test_persistence(self, tmp_path):
        path = tmp_path / "history.json"
        h1 = RunHistory(path)
        h1.record(_make_summary(total_detected=15))

        # Reload from disk
        h2 = RunHistory(path)
        assert h2.count == 1
        assert h2.latest["total_detected"] == 15

    def test_format_summary_no_runs(self, tmp_path):
        h = RunHistory(tmp_path / "history.json")
        assert "No runs recorded" in h.format_summary()

    def test_format_summary_single_run(self, tmp_path):
        h = RunHistory(tmp_path / "history.json")
        h.record(_make_summary(total_detected=20, auto_activated=12))
        output = h.format_summary()
        assert "SWEEP RUN SUMMARY" in output
        assert "Run #1" in output
        assert "20" in output  # total_detected
        assert "12" in output  # auto_activated
        # Should NOT have Prev Run column
        assert "Prev Run" not in output

    def test_format_summary_with_comparison(self, tmp_path):
        h = RunHistory(tmp_path / "history.json")
        h.record(_make_summary(total_detected=15, auto_activated=10))
        h.record(_make_summary(total_detected=23, auto_activated=18))
        output = h.format_summary()
        assert "Run #2" in output
        assert "Prev Run" in output
        assert "(+8)" in output  # total_detected delta 23-15
        assert "(+8)" in output  # auto_activated delta 18-10

    def test_format_summary_with_history_table(self, tmp_path):
        h = RunHistory(tmp_path / "history.json")
        for i in range(3):
            h.record(_make_summary(sweep_id=f"s{i}"))
        output = h.format_summary()
        assert "Run History" in output
        assert "#" in output

    def test_delta_formatting(self, tmp_path):
        assert RunHistory._delta(20, 15) == "  (+5)"
        assert RunHistory._delta(10, 15) == "  (-5)"
        assert RunHistory._delta(10, 10) == ""

    def test_max_history_cap(self, tmp_path):
        path = tmp_path / "history.json"
        h = RunHistory(path)
        for i in range(60):
            h.record(_make_summary(sweep_id=f"s{i}"))
        # In-memory: all 60
        assert h.count == 60
        # On disk: capped at 50
        with open(path) as f:
            data = json.load(f)
        assert len(data) == 50

    def test_errors_counted(self, tmp_path):
        h = RunHistory(tmp_path / "history.json")
        h.record(_make_summary(errors=["err1", "err2"]))
        assert h.latest["errors"] == 2

    def test_category_breakdown_stored(self, tmp_path):
        h = RunHistory(tmp_path / "history.json")
        h.record(_make_summary())
        cats = h.latest["category_breakdown"]
        assert cats["LEADERSHIP_CHANGE"] == 5
        assert cats["COMPETITOR_MOVEMENT"] == 3
