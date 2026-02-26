"""Tests for the scheduled sweep cron parser and background task."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from src.workflows.scheduled_sweep import (
    _next_cron_time,
    _parse_field,
    start_scheduled_sweep,
    stop_scheduled_sweep,
)


# ── _parse_field tests ─────────────────────────────────────────────────────


class TestParseField:
    def test_star(self):
        assert _parse_field("*", 0, 5) == {0, 1, 2, 3, 4, 5}

    def test_single_value(self):
        assert _parse_field("7", 0, 59) == {7}

    def test_range(self):
        assert _parse_field("1-5", 0, 6) == {1, 2, 3, 4, 5}

    def test_step(self):
        assert _parse_field("*/15", 0, 59) == {0, 15, 30, 45}

    def test_range_step(self):
        assert _parse_field("1-5/2", 0, 6) == {1, 3, 5}

    def test_comma_list(self):
        assert _parse_field("1,3,5", 0, 6) == {1, 3, 5}

    def test_mixed(self):
        # "0,30" → minutes 0 and 30
        assert _parse_field("0,30", 0, 59) == {0, 30}


# ── _next_cron_time tests ─────────────────────────────────────────────────


class TestNextCronTime:
    def test_weekday_morning(self):
        # "0 7 * * 1-5" = weekdays at 07:00
        # Start: Monday 2026-02-23 06:30 → next = Monday 07:00
        after = datetime(2026, 2, 23, 6, 30, tzinfo=timezone.utc)
        result = _next_cron_time("0 7 * * 1-5", after)
        assert result == datetime(2026, 2, 23, 7, 0, tzinfo=timezone.utc)

    def test_skip_weekend(self):
        # After Friday 07:00 → next = Monday 07:00
        after = datetime(2026, 2, 27, 7, 0, tzinfo=timezone.utc)  # Friday 07:00
        result = _next_cron_time("0 7 * * 1-5", after)
        assert result == datetime(2026, 3, 2, 7, 0, tzinfo=timezone.utc)  # Monday

    def test_same_day_past(self):
        # Monday 08:00 → next weekday 07:00 = Tuesday
        after = datetime(2026, 2, 23, 8, 0, tzinfo=timezone.utc)
        result = _next_cron_time("0 7 * * 1-5", after)
        assert result == datetime(2026, 2, 24, 7, 0, tzinfo=timezone.utc)

    def test_every_day_midnight(self):
        # "0 0 * * *" = every day at midnight
        after = datetime(2026, 2, 24, 23, 59, tzinfo=timezone.utc)
        result = _next_cron_time("0 0 * * *", after)
        assert result == datetime(2026, 2, 25, 0, 0, tzinfo=timezone.utc)

    def test_every_15_minutes(self):
        # "*/15 * * * *" = every 15 min
        after = datetime(2026, 2, 24, 10, 3, tzinfo=timezone.utc)
        result = _next_cron_time("*/15 * * * *", after)
        assert result == datetime(2026, 2, 24, 10, 15, tzinfo=timezone.utc)

    def test_invalid_field_count(self):
        with pytest.raises(ValueError, match="5-field"):
            _next_cron_time("0 7 *", datetime.now(timezone.utc))


# ── start / stop lifecycle tests ──────────────────────────────────────────


class TestScheduledSweepLifecycle:
    @pytest.fixture(autouse=True)
    def _reset_task(self):
        """Ensure no leftover task between tests."""
        import src.workflows.scheduled_sweep as mod

        mod._task = None
        yield
        if mod._task is not None:
            mod._task.cancel()
            mod._task = None

    @pytest.mark.asyncio
    async def test_start_creates_task(self):
        import src.workflows.scheduled_sweep as mod

        assert mod._task is None
        await start_scheduled_sweep()
        assert mod._task is not None
        assert mod._task.get_name() == "scheduled-sweep"
        # Clean up
        await stop_scheduled_sweep()
        assert mod._task is None

    @pytest.mark.asyncio
    async def test_start_is_idempotent(self):
        import src.workflows.scheduled_sweep as mod

        await start_scheduled_sweep()
        first = mod._task
        await start_scheduled_sweep()  # should not create a second task
        assert mod._task is first
        await stop_scheduled_sweep()

    @pytest.mark.asyncio
    async def test_stop_without_start(self):
        # Should be a no-op
        await stop_scheduled_sweep()
