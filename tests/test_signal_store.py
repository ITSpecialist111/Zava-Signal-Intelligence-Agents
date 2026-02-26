"""Unit tests for SignalStore — JSON-backed persistence."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from src.models.signal import (
    ConfidenceLevel,
    Signal,
    SignalBatch,
    SignalCategory,
    SignalStatus,
    SignalSubcategory,
)
from src.tools.signal_store import SignalStore


@pytest.fixture
def tmp_store(tmp_path: Path) -> SignalStore:
    """Create a SignalStore backed by a temp file."""
    return SignalStore(store_path=tmp_path / "signals.json")


def _quick_signal(
    signal_id: str | None = None,
    entity_name: str = "Harris Federation",
    status: SignalStatus = SignalStatus.DETECTED,
    confidence: float = 0.85,
    detected_offset_days: int = 0,
) -> Signal:
    return Signal(
        signal_id=signal_id or str(uuid.uuid4()),
        category=SignalCategory.STRUCTURAL_STRESS,
        subcategory=SignalSubcategory.HUB_AND_SPOKE,
        entity_name=entity_name,
        confidence=confidence,
        confidence_level=ConfidenceLevel.HIGH if confidence >= 0.8 else ConfidenceLevel.MEDIUM,
        status=status,
        source_url="https://test.com",
        source_name="Test",
        raw_evidence="Test evidence.",
        detected_at=datetime.utcnow() - timedelta(days=detected_offset_days),
    )


class TestSignalStore:

    def test_add_and_get_signal(self, tmp_store: SignalStore):
        sig = _quick_signal(signal_id="sig-001")
        tmp_store.add_signal(sig)
        retrieved = tmp_store.get_signal("sig-001")
        assert retrieved is not None
        assert retrieved.signal_id == "sig-001"
        assert retrieved.entity_name == "Harris Federation"

    def test_get_missing_signal_returns_none(self, tmp_store: SignalStore):
        assert tmp_store.get_signal("nonexistent") is None

    def test_get_all_signals(self, tmp_store: SignalStore):
        for i in range(3):
            tmp_store.add_signal(_quick_signal(signal_id=f"sig-{i}"))
        all_signals = tmp_store.get_all_signals()
        assert len(all_signals) == 3

    def test_count(self, tmp_store: SignalStore):
        assert tmp_store.count() == 0
        tmp_store.add_signal(_quick_signal())
        assert tmp_store.count() == 1

    def test_update_status(self, tmp_store: SignalStore):
        tmp_store.add_signal(_quick_signal(signal_id="sig-u1"))
        tmp_store.update_status("sig-u1", SignalStatus.APPROVED, reviewed_by="reviewer@test.com")
        sig = tmp_store.get_signal("sig-u1")
        assert sig is not None
        assert sig.status == SignalStatus.APPROVED

    def test_get_signals_by_status(self, tmp_store: SignalStore):
        tmp_store.add_signal(_quick_signal(signal_id="s1", status=SignalStatus.DETECTED))
        tmp_store.add_signal(_quick_signal(signal_id="s2", status=SignalStatus.HITL_PENDING))
        tmp_store.add_signal(_quick_signal(signal_id="s3", status=SignalStatus.HITL_PENDING))

        pending = tmp_store.get_signals_by_status(SignalStatus.HITL_PENDING)
        assert len(pending) == 2

        detected = tmp_store.get_signals_by_status(SignalStatus.DETECTED)
        assert len(detected) == 1

    def test_get_signals_pending_review(self, tmp_store: SignalStore):
        tmp_store.add_signal(_quick_signal(signal_id="p1", status=SignalStatus.HITL_PENDING))
        tmp_store.add_signal(_quick_signal(signal_id="p2", status=SignalStatus.DETECTED))
        pending = tmp_store.get_signals_pending_review()
        assert len(pending) == 1
        assert pending[0].signal_id == "p1"

    def test_get_signals_for_activation(self, tmp_store: SignalStore):
        tmp_store.add_signal(_quick_signal(signal_id="a1", status=SignalStatus.APPROVED))
        tmp_store.add_signal(_quick_signal(signal_id="a2", status=SignalStatus.DETECTED))
        approved = tmp_store.get_signals_for_activation()
        assert len(approved) == 1
        assert approved[0].signal_id == "a1"

    def test_add_batch(self, tmp_store: SignalStore):
        s1 = _quick_signal(signal_id="b1")
        s2 = _quick_signal(signal_id="b2")
        batch = SignalBatch(batch_id="batch-001", source="TES", signals=[s1, s2])
        tmp_store.add_batch(batch)
        assert tmp_store.count() == 2

    def test_get_recent_signals(self, tmp_store: SignalStore):
        # One recent, one old
        tmp_store.add_signal(_quick_signal(signal_id="recent", detected_offset_days=1))
        tmp_store.add_signal(_quick_signal(signal_id="old", detected_offset_days=30))

        recent = tmp_store.get_recent_signals(days=7)
        assert len(recent) == 1
        assert recent[0].signal_id == "recent"

    def test_get_signal_counts_by_category(self, tmp_store: SignalStore):
        tmp_store.add_signal(_quick_signal(signal_id="c1"))
        tmp_store.add_signal(_quick_signal(signal_id="c2"))
        counts = tmp_store.get_signal_counts_by_category()
        assert counts.get("STRUCTURAL_STRESS") == 2

    def test_persists_to_disk(self, tmp_path: Path):
        store_file = tmp_path / "persist_test.json"
        store1 = SignalStore(store_path=store_file)
        store1.add_signal(_quick_signal(signal_id="disk-sig"))

        # Create a new store instance from the same file
        store2 = SignalStore(store_path=store_file)
        assert store2.count() == 1
        retrieved = store2.get_signal("disk-sig")
        assert retrieved is not None
        assert retrieved.entity_name == "Harris Federation"

    def test_handles_corrupted_file(self, tmp_path: Path):
        store_file = tmp_path / "corrupt.json"
        store_file.write_text("not json!")
        store = SignalStore(store_path=store_file)
        assert store.count() == 0  # should gracefully reset

    def test_upsert_existing_signal(self, tmp_store: SignalStore):
        sig = _quick_signal(signal_id="upsert-1")
        tmp_store.add_signal(sig)
        assert tmp_store.count() == 1

        # Update the same signal
        updated = _quick_signal(signal_id="upsert-1", entity_name="Updated Trust")
        tmp_store.add_signal(updated)
        assert tmp_store.count() == 1
        retrieved = tmp_store.get_signal("upsert-1")
        assert retrieved is not None
        assert retrieved.entity_name == "Updated Trust"
