"""Scheduled Sweep — runs the daily sweep automatically on a cron schedule.

Parses the ``SIGNAL_SWEEP_SCHEDULE_CRON`` env var (default ``0 7 * * 1-5``,
i.e. weekdays at 07:00 UTC) and runs the sweep at the next matching time
using an asyncio background task.

No external scheduler or cron library required — pure stdlib.
"""

from __future__ import annotations

import asyncio
import calendar
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# ── Cron parser (5-field subset) ──────────────────────────────────────────


def _parse_field(field: str, lo: int, hi: int) -> set[int]:
    """Parse a single cron field into a set of valid integer values.

    Supports: ``*``, ``*/N``, ``N``, ``N-M``, ``N-M/S``, and
    comma-separated combinations thereof.
    """
    values: set[int] = set()
    for part in field.split(","):
        if "/" in part:
            range_part, step_s = part.split("/", 1)
            step = int(step_s)
            if range_part == "*":
                start, end = lo, hi
            elif "-" in range_part:
                start, end = (int(x) for x in range_part.split("-", 1))
            else:
                start, end = int(range_part), hi
            values.update(range(start, end + 1, step))
        elif part == "*":
            values.update(range(lo, hi + 1))
        elif "-" in part:
            a, b = (int(x) for x in part.split("-", 1))
            values.update(range(a, b + 1))
        else:
            values.add(int(part))
    return values


def _next_cron_time(cron: str, after: datetime) -> datetime:
    """Return the next datetime (UTC) matching *cron* strictly after *after*.

    Only the standard 5-field format is supported:
    ``minute hour day-of-month month day-of-week``
    """
    fields = cron.strip().split()
    if len(fields) != 5:
        raise ValueError(f"Expected 5-field cron expression, got: {cron!r}")

    minutes = _parse_field(fields[0], 0, 59)
    hours = _parse_field(fields[1], 0, 23)
    doms = _parse_field(fields[2], 1, 31)
    months = _parse_field(fields[3], 1, 12)
    dows = _parse_field(fields[4], 0, 6)  # 0=Mon … 6=Sun (crontab: 0=Sun)

    # Crontab convention: 0 and 7 both mean Sunday.  Python weekday():
    # 0=Monday … 6=Sunday.  Convert cron DOW → Python weekday.
    py_dows: set[int] = set()
    for d in dows:
        if d == 0 or d == 7:
            py_dows.add(6)  # Sunday
        else:
            py_dows.add(d - 1)  # shift: cron 1=Mon→py 0, cron 6=Sat→py 5

    # Brute-force search — start from the next minute after *after*.
    candidate = after.replace(second=0, microsecond=0) + _ONE_MINUTE
    # Safety: don't search more than ~2 years
    limit = 366 * 24 * 60
    for _ in range(limit):
        if (
            candidate.month in months
            and candidate.day in doms
            and candidate.weekday() in py_dows
            and candidate.hour in hours
            and candidate.minute in minutes
            # Ensure the day is valid for the month
            and candidate.day <= calendar.monthrange(candidate.year, candidate.month)[1]
        ):
            return candidate
        candidate += _ONE_MINUTE
    raise RuntimeError(f"No matching cron time found within {limit} minutes")


from datetime import timedelta

_ONE_MINUTE = timedelta(minutes=1)

# ── Background task ───────────────────────────────────────────────────────

_task: asyncio.Task | None = None


async def _sweep_loop(cron: str, confidence: float) -> None:
    """Infinite loop: sleep until next cron time, run sweep, repeat."""
    from src.tools.run_history import RunHistory

    history = RunHistory()

    while True:
        now = datetime.now(timezone.utc)
        next_run = _next_cron_time(cron, now)
        delay = (next_run - now).total_seconds()
        logger.info(
            "Scheduled sweep: next run at %s UTC (in %.0f min)",
            next_run.strftime("%Y-%m-%d %H:%M"),
            delay / 60,
        )
        await asyncio.sleep(delay)

        logger.info("=== SCHEDULED SWEEP TRIGGERED ===")
        try:
            # Lazy import — avoids pulling in agent_framework at startup
            from src.workflows.daily_sweep import run_daily_sweep

            summary = await run_daily_sweep(
                confidence_threshold=confidence,
            )
            history.record(summary)
            logger.info(
                "Scheduled sweep complete — detected=%d, dedup=%d, "
                "enriched=%d, auto=%d, hitl=%d",
                summary["total_detected"],
                summary["after_dedup"],
                summary["enriched"],
                summary["auto_activated"],
                summary["hitl_pending"],
            )
        except Exception:
            logger.exception("Scheduled sweep failed")


async def start_scheduled_sweep(app=None) -> None:  # noqa: ANN001
    """Start the background sweep task.

    Designed to be used as an aiohttp ``on_startup`` signal handler
    (accepts the *app* argument) or called directly.
    """
    global _task
    if _task is not None:
        return  # Already running

    from src.config import AppConfig

    config = AppConfig.from_env()
    cron = config.signal.sweep_cron
    confidence = config.signal.confidence_threshold

    logger.info("Starting scheduled sweep (cron=%s)", cron)
    _task = asyncio.create_task(
        _sweep_loop(cron, confidence),
        name="scheduled-sweep",
    )


async def stop_scheduled_sweep(app=None) -> None:  # noqa: ANN001
    """Cancel the background sweep task.

    Designed to be used as an aiohttp ``on_cleanup`` signal handler.
    """
    global _task
    if _task is not None:
        _task.cancel()
        try:
            await _task
        except (asyncio.CancelledError, Exception):
            pass
        _task = None
        logger.info("Scheduled sweep stopped")
