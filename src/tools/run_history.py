"""Run History — tracks sweep results across runs for comparison.

Persists per-run metrics to a JSON file so each sweep can display
a "this run vs previous runs" summary table.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Maximum number of runs to retain in history
_MAX_HISTORY = 50


class RunHistory:
    """Persistent store for sweep run summaries."""

    def __init__(self, path: str | Path = "./data/run_history.json"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._runs: list[dict[str, Any]] = []
        self._load()

    # ------------------------------------------------------------------ #
    # Persistence
    # ------------------------------------------------------------------ #

    def _load(self) -> None:
        if self.path.exists():
            try:
                with open(self.path) as f:
                    data = json.load(f)
                self._runs = data if isinstance(data, list) else []
                logger.debug("Loaded %d run records", len(self._runs))
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("Failed to load run history: %s", e)
                self._runs = []

    def _save(self) -> None:
        with open(self.path, "w") as f:
            json.dump(self._runs[-_MAX_HISTORY:], f, indent=2, default=str)

    # ------------------------------------------------------------------ #
    # Recording
    # ------------------------------------------------------------------ #

    def record(self, summary: dict[str, Any]) -> dict[str, Any]:
        """Record a sweep run and return the stored record.

        Args:
            summary: The dict returned by ``run_daily_sweep()``.

        Returns:
            The stored run record (with ``run_number`` added).
        """
        record: dict[str, Any] = {
            "run_number": len(self._runs) + 1,
            "sweep_id": summary.get("sweep_id", ""),
            "timestamp": summary.get(
                "timestamp",
                datetime.now(timezone.utc).isoformat(),
            ),
            "total_detected": summary.get("total_detected", 0),
            "after_dedup": summary.get("after_dedup", 0),
            "enriched": summary.get("enriched", 0),
            "auto_activated": summary.get("auto_activated", 0),
            "hitl_pending": summary.get("hitl_pending", 0),
            "errors": len(summary.get("errors", [])),
            "category_breakdown": summary.get("category_breakdown", {}),
        }
        self._runs.append(record)
        self._save()
        logger.info("Recorded run #%d", record["run_number"])
        return record

    # ------------------------------------------------------------------ #
    # Querying
    # ------------------------------------------------------------------ #

    @property
    def latest(self) -> dict[str, Any] | None:
        """Return the most recent run, or ``None``."""
        return self._runs[-1] if self._runs else None

    @property
    def previous(self) -> dict[str, Any] | None:
        """Return the second-most-recent run, or ``None``."""
        return self._runs[-2] if len(self._runs) >= 2 else None

    def last_n(self, n: int = 5) -> list[dict[str, Any]]:
        """Return the last *n* runs (newest last)."""
        return self._runs[-n:]

    @property
    def count(self) -> int:
        return len(self._runs)

    # ------------------------------------------------------------------ #
    # Comparison formatting
    # ------------------------------------------------------------------ #

    @staticmethod
    def _delta(current: int, previous: int) -> str:
        """Format a delta indicator like ↑3 or ↓2 or '—'."""
        diff = current - previous
        if diff > 0:
            return f"  (+{diff})"
        elif diff < 0:
            return f"  ({diff})"
        return ""

    def format_summary(self) -> str:
        """Build a human-readable run summary with comparison table.

        Shows key metrics for the current run plus a comparison row
        for the previous run (if one exists), followed by a sparkline
        history of the last 5 runs.
        """
        current = self.latest
        if current is None:
            return "No runs recorded yet."

        prev = self.previous
        lines: list[str] = []

        lines.append("")
        lines.append("=" * 68)
        lines.append("  SWEEP RUN SUMMARY")
        lines.append("=" * 68)
        lines.append(f"  Run #{current['run_number']}  |  {current['timestamp']}")
        lines.append("-" * 68)

        # Key metrics
        metrics = [
            ("Signals Detected", "total_detected"),
            ("After Dedup", "after_dedup"),
            ("Enriched", "enriched"),
            ("Auto-Activated", "auto_activated"),
            ("HITL Pending", "hitl_pending"),
            ("Errors", "errors"),
        ]

        lines.append(f"  {'Metric':<22} {'This Run':>10}", )
        if prev:
            lines[-1] += f"  {'Prev Run':>10}  {'Delta':>8}"
        lines.append("  " + "-" * (44 if not prev else 64))

        for label, key in metrics:
            cur_val = current.get(key, 0)
            line = f"  {label:<22} {cur_val:>10}"
            if prev:
                prev_val = prev.get(key, 0)
                delta = self._delta(cur_val, prev_val)
                line += f"  {prev_val:>10}  {delta:>8}"
            lines.append(line)

        # Category breakdown
        cats = current.get("category_breakdown", {})
        if cats:
            lines.append("")
            lines.append("  Category Breakdown:")
            for cat, count in sorted(cats.items(), key=lambda x: -x[1]):
                bar = "█" * min(count, 30)
                lines.append(f"    {cat:<25} {count:>4}  {bar}")

        # Run history sparkline (last 5)
        recent = self.last_n(5)
        if len(recent) > 1:
            lines.append("")
            lines.append("  Run History (last %d runs):" % len(recent))
            lines.append(
                f"  {'#':<5} {'Date':<22} {'Det':>5} {'Dedup':>5}"
                f" {'Auto':>5} {'HITL':>5} {'Err':>5}"
            )
            lines.append("  " + "-" * 58)
            for r in recent:
                ts = r["timestamp"][:19].replace("T", " ")
                lines.append(
                    f"  {r['run_number']:<5} {ts:<22}"
                    f" {r['total_detected']:>5} {r['after_dedup']:>5}"
                    f" {r['auto_activated']:>5} {r['hitl_pending']:>5}"
                    f" {r['errors']:>5}"
                )

        lines.append("=" * 68)
        lines.append("")
        return "\n".join(lines)
