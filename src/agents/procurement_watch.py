"""Procurement Watch Agent — monitors Find a Tender for procurement signals.

Specifically watches for Procurement Act 2023 changes including
Soft Market Testing and Preliminary Market Engagement notices.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime

from src.models.signal import (
    ConfidenceLevel,
    Signal,
    SignalCategory,
    SignalSubcategory,
)
from src.tools.find_a_tender import FindATenderClient

logger = logging.getLogger(__name__)


async def scan_procurement(lookback_days: int = 7) -> list[Signal]:
    """Scan Find a Tender / Contracts Finder for procurement signals.

    Focuses on:
    - Pipeline Notices (new under Procurement Act 2023)
    - Preliminary Market Engagement (soft market testing)
    - Education-sector HR/payroll tenders

    Args:
        lookback_days: Number of days to look back.

    Returns:
        List of procurement signals.
    """
    client = FindATenderClient()
    signals: list[Signal] = []

    try:
        raw_signals = await client.scan_for_signals(lookback_days=lookback_days)

        for raw in raw_signals:
            # Map signal keywords to subcategories
            keywords = raw.get("signal_keywords", [])
            if any("pipeline" in kw for kw in keywords):
                subcategory = SignalSubcategory.PIPELINE_NOTICE
            elif any("preliminary" in kw or "early engagement" in kw for kw in keywords):
                subcategory = SignalSubcategory.PRELIMINARY_MARKET_ENGAGEMENT
            elif any("soft market" in kw for kw in keywords):
                subcategory = SignalSubcategory.SOFT_MARKET_TESTING
            else:
                subcategory = SignalSubcategory.PIPELINE_NOTICE

            signal = Signal(
                signal_id=str(uuid.uuid4()),
                category=SignalCategory.PROCUREMENT_SHIFT,
                subcategory=subcategory,
                entity_name=raw.get("buyer_name", "Unknown Buyer"),
                confidence=0.85,  # High confidence — these are official procurement signals
                confidence_level=ConfidenceLevel.HIGH,
                source_url=raw.get("url", ""),
                source_name="Find a Tender / Contracts Finder",
                raw_evidence=(
                    f"Title: {raw.get('title', 'N/A')}\n"
                    f"Description: {raw.get('description', 'N/A')}\n"
                    f"Published: {raw.get('published_date', 'N/A')}\n"
                    f"Procurement Method: {raw.get('procurement_method', 'N/A')}"
                ),
                detected_at=datetime.utcnow(),
            )
            signals.append(signal)

    except Exception as e:
        logger.error("Procurement scan failed: %s", e)
    finally:
        await client.close()

    logger.info("Procurement scan complete: %d signals detected", len(signals))
    return signals
