"""Signal persistence layer.

Stores and retrieves signals using a simple JSON file store for
development. In production, replace with Azure Cosmos DB or similar.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from src.models.signal import Signal, SignalBatch, SignalStatus

logger = logging.getLogger(__name__)


class SignalStore:
    """Persistent store for detected signals."""

    def __init__(self, store_path: str | Path = "./data/signals.json"):
        self.store_path = Path(store_path)
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        self._signals: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        """Load signals from disk."""
        if self.store_path.exists():
            try:
                with open(self.store_path) as f:
                    self._signals = json.load(f)
                logger.info("Loaded %d signals from store", len(self._signals))
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("Failed to load signal store: %s", e)
                self._signals = {}

    def reload(self) -> None:
        """Re-read signals from disk (useful when another instance has written)."""
        self._load()

    def _save(self) -> None:
        """Persist signals to disk."""
        with open(self.store_path, "w") as f:
            json.dump(self._signals, f, indent=2, default=str)

    def add_signal(self, signal: Signal) -> None:
        """Add or update a signal."""
        self._signals[signal.signal_id] = signal.model_dump(mode="json")
        self._save()
        logger.info("Stored signal %s (%s)", signal.signal_id, signal.entity_name)

    def add_batch(self, batch: SignalBatch) -> None:
        """Add all signals from a batch."""
        for signal in batch.signals:
            self.add_signal(signal)

    def get_signal(self, signal_id: str) -> Signal | None:
        """Retrieve a signal by ID."""
        data = self._signals.get(signal_id)
        if data:
            return Signal(**data)
        return None

    def get_all_signals(self) -> list[Signal]:
        """Return every signal in the store."""
        return [Signal(**data) for data in self._signals.values()]

    def get_signals_by_status(self, status: SignalStatus) -> list[Signal]:
        """Get all signals with a given status."""
        return [
            Signal(**data)
            for data in self._signals.values()
            if data.get("status") == status.value
        ]

    def get_signals_pending_review(self) -> list[Signal]:
        """Get signals awaiting HITL review."""
        return self.get_signals_by_status(SignalStatus.HITL_PENDING)

    def get_signals_for_activation(self) -> list[Signal]:
        """Get approved signals ready for activation."""
        return self.get_signals_by_status(SignalStatus.APPROVED)

    def update_status(self, signal_id: str, status: SignalStatus, **kwargs: Any) -> None:
        """Update the status of a signal, optionally adding review metadata."""
        if signal_id in self._signals:
            self._signals[signal_id]["status"] = status.value
            for key, value in kwargs.items():
                self._signals[signal_id][key] = value if not isinstance(value, datetime) else value.isoformat()
            self._save()

    def get_recent_signals(self, days: int = 7) -> list[Signal]:
        """Get signals detected within the last N days."""
        cutoff = datetime.utcnow().timestamp() - (days * 86400)
        results = []
        for data in self._signals.values():
            detected = data.get("detected_at", "")
            try:
                dt = datetime.fromisoformat(detected)
                if dt.timestamp() >= cutoff:
                    results.append(Signal(**data))
            except (ValueError, TypeError):
                continue
        return results

    def get_signal_counts_by_category(self) -> dict[str, int]:
        """Get signal counts grouped by category (for heatmap)."""
        counts: dict[str, int] = {}
        for data in self._signals.values():
            cat = data.get("category", "UNKNOWN")
            counts[cat] = counts.get(cat, 0) + 1
        return counts

    def count(self) -> int:
        """Total number of signals in the store."""
        return len(self._signals)
