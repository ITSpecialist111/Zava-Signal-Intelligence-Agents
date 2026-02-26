"""Signal data model — the core entity of the intelligence system.

A Signal represents a detected "proxy event" that predicts a trust's future
need for Zava products, well before an official procurement appears.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Signal taxonomy
# ---------------------------------------------------------------------------

class SignalCategory(str, Enum):
    """Top-level signal categories aligned to Zava GTM strategy."""

    STRUCTURAL_STRESS = "STRUCTURAL_STRESS"
    COMPLIANCE_TRAP = "COMPLIANCE_TRAP"
    COMPETITOR_MOVEMENT = "COMPETITOR_MOVEMENT"
    PROCUREMENT_SHIFT = "PROCUREMENT_SHIFT"
    LEADERSHIP_CHANGE = "LEADERSHIP_CHANGE"


class SignalSubcategory(str, Enum):
    """Granular subcategories for signal classification."""

    # Structural Stress
    HUB_AND_SPOKE = "HUB_AND_SPOKE"
    SHADOW_MERGER = "SHADOW_MERGER"
    FEDERATION_AGREEMENT = "FEDERATION_AGREEMENT"

    # Compliance Trap
    EXECUTIVE_PAY_SCRUTINY = "EXECUTIVE_PAY_SCRUTINY"
    CYBER_RANSOM_BAN = "CYBER_RANSOM_BAN"
    FBIT_OUTLIER = "FBIT_OUTLIER"

    # Competitor Movement
    COMPETITOR_HIRING = "COMPETITOR_HIRING"
    COMPETITOR_CONTRACT_WIN = "COMPETITOR_CONTRACT_WIN"
    COMPETITOR_GTM_PIVOT = "COMPETITOR_GTM_PIVOT"

    # Procurement
    PIPELINE_NOTICE = "PIPELINE_NOTICE"
    PRELIMINARY_MARKET_ENGAGEMENT = "PRELIMINARY_MARKET_ENGAGEMENT"
    SOFT_MARKET_TESTING = "SOFT_MARKET_TESTING"

    # Leadership
    NEW_CFO = "NEW_CFO"
    NEW_CEO = "NEW_CEO"
    NEW_HR_DIRECTOR = "NEW_HR_DIRECTOR"
    HEAD_OF_SHARED_SERVICES = "HEAD_OF_SHARED_SERVICES"


class ConfidenceLevel(str, Enum):
    """Human-readable confidence bands."""

    HIGH = "HIGH"       # >0.8 — auto-route to activation
    MEDIUM = "MEDIUM"   # 0.5–0.8 — HITL review recommended
    LOW = "LOW"         # <0.5 — HITL review required


class SignalStatus(str, Enum):
    """Lifecycle status of a signal."""

    DETECTED = "DETECTED"
    ENRICHED = "ENRICHED"
    HITL_PENDING = "HITL_PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    ACTIVATED = "ACTIVATED"
    ARCHIVED = "ARCHIVED"


# ---------------------------------------------------------------------------
# Playbook mapping
# ---------------------------------------------------------------------------

class ZavaPlaybook(str, Enum):
    """Zava sales playbooks matched to signals."""

    PROFESSIONALIZATION_PITCH = "The Professionalization Pitch"
    CONSOLIDATION_VALUE_PROP = "The Consolidation Value Prop"
    RISK_MITIGATION = "The Risk Mitigation Pitch"
    COMPLIANCE_SHIELD = "The Compliance Shield"
    DIGITAL_TRANSFORMATION = "The Digital Transformation Play"
    COST_OPTIMISATION = "The Cost Optimisation Play"


# ---------------------------------------------------------------------------
# Core Signal model
# ---------------------------------------------------------------------------

class Signal(BaseModel):
    """A detected public-sector proxy signal.

    Represents a single piece of intelligence that indicates a trust
    may need new HR/payroll software within the next 3–12 months.
    """

    signal_id: str = Field(description="Unique identifier (UUID)")
    category: SignalCategory
    subcategory: SignalSubcategory
    entity_name: str = Field(description="Academy trust / MAT name")
    entity_id: Optional[str] = Field(default=None, description="Companies House number if known")
    confidence: float = Field(ge=0.0, le=1.0, description="Model-assigned confidence score")
    confidence_level: ConfidenceLevel = Field(description="Bucketed confidence band")
    status: SignalStatus = Field(default=SignalStatus.DETECTED)

    # Evidence
    source_url: str = Field(description="URL where the signal was found")
    source_name: str = Field(description="Human-readable source name, e.g. 'TES Magazine'")
    raw_evidence: str = Field(description="Verbatim text excerpt or summary from source")
    detected_at: datetime = Field(default_factory=datetime.utcnow)

    # Enrichment (populated in Phase 2)
    current_provider: Optional[str] = Field(default=None, description="Current payroll/HR provider if known")
    financial_summary: Optional[str] = Field(default=None, description="3-year financial trend summary")
    key_decision_maker: Optional[str] = Field(default=None, description="Name + role of key contact")
    recent_changes: Optional[str] = Field(default=None, description="Recent leadership or structural changes")

    # Playbook match
    playbook_match: Optional[ZavaPlaybook] = Field(default=None)
    recommended_action: Optional[str] = Field(default=None, description="Suggested next step for AE")
    impact_statement: Optional[str] = Field(default=None, description="Why this signal matters to Zava — the 'so what'")
    talk_track: Optional[str] = Field(default=None, description="What to say to the prospect (the 'Say' in Know/Say/Show)")
    handbook_reference: Optional[str] = Field(default=None, description="Relevant handbook section, e.g. '1.16'")

    # HITL tracking
    reviewed_by: Optional[str] = Field(default=None)
    review_notes: Optional[str] = Field(default=None)
    reviewed_at: Optional[datetime] = Field(default=None)

    def to_confidence_level(self) -> ConfidenceLevel:
        """Derive confidence level from numeric score."""
        if self.confidence >= 0.8:
            return ConfidenceLevel.HIGH
        elif self.confidence >= 0.5:
            return ConfidenceLevel.MEDIUM
        return ConfidenceLevel.LOW


class SignalBatch(BaseModel):
    """A collection of signals from a single sweep or analysis run."""

    batch_id: str
    sweep_timestamp: datetime = Field(default_factory=datetime.utcnow)
    source: str = Field(description="Which source was swept")
    signals: list[Signal] = Field(default_factory=list)
    total_pages_scanned: int = 0
    errors: list[str] = Field(default_factory=list)
