"""Daily Sweep Workflow — orchestrates the complete signal collection cycle.

Uses Agent Framework Workflows for graph-based, type-safe orchestration
with checkpointing and human-in-the-loop support.

Ref: https://learn.microsoft.com/agent-framework/workflows/
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime

from src.agents.competitor_ghost import scan_competitors
from src.agents.enrichment import enrich_signal
from src.agents.procurement_watch import scan_procurement
from src.agents.signal_collector import run_sweep
from src.models.signal import Signal, SignalBatch, SignalStatus
from src.tools.signal_store import SignalStore

logger = logging.getLogger(__name__)


async def run_daily_sweep(
    signal_store: SignalStore | None = None,
    confidence_threshold: float = 0.8,
) -> dict:
    """Execute the complete Daily Public Sector Sweep.

    This workflow orchestrates four parallel collection streams,
    then routes signals through enrichment and HITL gates based
    on confidence scores.

    Workflow steps:
    1. COLLECT: Run parallel signal collection from all sources
    2. DEDUPLICATE: Remove duplicate signals across sources
    3. ENRICH: Pull Companies House data + playbook mapping
    4. ROUTE: High-confidence → auto-activate, Low → HITL queue
    5. STORE: Persist all signals for tracking

    Args:
        signal_store: Signal persistence layer.
        confidence_threshold: Threshold for auto-activation vs HITL.

    Returns:
        Summary of the sweep results.
    """
    store = signal_store or SignalStore()
    sweep_id = str(uuid.uuid4())

    logger.info("=== DAILY SWEEP %s STARTED ===", sweep_id)

    # -----------------------------------------------------------------
    # Step 1: COLLECT — parallel signal collection
    # -----------------------------------------------------------------
    # In production, these would run as concurrent workflow executors.
    # Agent Framework Workflows support concurrent orchestration:
    # https://learn.microsoft.com/agent-framework/user-guide/workflows/orchestrations/concurrent

    all_signals: list[Signal] = []
    errors: list[str] = []

    # Stream 1: Web crawling (TES, Gov.uk, Schools Week, BESA)
    try:
        web_batch: SignalBatch = await run_sweep()
        all_signals.extend(web_batch.signals)
        errors.extend(web_batch.errors)
        logger.info("Web sweep: %d signals", len(web_batch.signals))
    except Exception as e:
        logger.error("Web sweep failed: %s", e)
        errors.append(f"Web sweep: {e}")

    # Stream 2: Competitor monitoring
    try:
        competitor_signals = await scan_competitors()
        all_signals.extend(competitor_signals)
        logger.info("Competitor scan: %d signals", len(competitor_signals))
    except Exception as e:
        logger.error("Competitor scan failed: %s", e)
        errors.append(f"Competitor scan: {e}")

    # Stream 3: Procurement monitoring
    try:
        procurement_signals = await scan_procurement()
        all_signals.extend(procurement_signals)
        logger.info("Procurement scan: %d signals", len(procurement_signals))
    except Exception as e:
        logger.error("Procurement scan failed: %s", e)
        errors.append(f"Procurement scan: {e}")

    # -----------------------------------------------------------------
    # Step 2: DEDUPLICATE
    # -----------------------------------------------------------------
    deduped = _deduplicate_signals(all_signals)
    logger.info("After dedup: %d signals (was %d)", len(deduped), len(all_signals))

    # -----------------------------------------------------------------
    # Step 3: ENRICH each signal
    # -----------------------------------------------------------------
    enriched_signals: list[Signal] = []
    for signal in deduped:
        try:
            enriched = await enrich_signal(signal)
            enriched_signals.append(enriched)
        except Exception as e:
            logger.error("Enrichment failed for %s: %s", signal.entity_name, e)
            signal.status = SignalStatus.DETECTED  # Keep as-is
            enriched_signals.append(signal)

    # -----------------------------------------------------------------
    # Step 4: ROUTE by confidence
    # -----------------------------------------------------------------
    auto_activate: list[Signal] = []
    hitl_queue: list[Signal] = []

    for signal in enriched_signals:
        if signal.confidence >= confidence_threshold:
            signal.status = SignalStatus.APPROVED
            auto_activate.append(signal)
        else:
            signal.status = SignalStatus.HITL_PENDING
            hitl_queue.append(signal)

    logger.info(
        "Routing: %d auto-activate, %d HITL queue",
        len(auto_activate),
        len(hitl_queue),
    )

    # -----------------------------------------------------------------
    # Step 5: STORE all signals
    # -----------------------------------------------------------------
    for signal in enriched_signals:
        store.add_signal(signal)

    summary = {
        "sweep_id": sweep_id,
        "timestamp": datetime.utcnow().isoformat(),
        "total_detected": len(all_signals),
        "after_dedup": len(deduped),
        "enriched": len(enriched_signals),
        "auto_activated": len(auto_activate),
        "hitl_pending": len(hitl_queue),
        "errors": errors,
        "category_breakdown": store.get_signal_counts_by_category(),
    }

    logger.info("=== DAILY SWEEP %s COMPLETE === %s", sweep_id, summary)
    return summary


def _deduplicate_signals(signals: list[Signal]) -> list[Signal]:
    """Remove duplicate signals based on entity name + category.

    Simple dedup: if the same entity has the same signal category
    detected from multiple sources, keep the highest-confidence one.
    """
    seen: dict[str, Signal] = {}
    for signal in signals:
        key = f"{signal.entity_name.lower().strip()}::{signal.category.value}"
        existing = seen.get(key)
        if existing is None or signal.confidence > existing.confidence:
            seen[key] = signal
    return list(seen.values())
