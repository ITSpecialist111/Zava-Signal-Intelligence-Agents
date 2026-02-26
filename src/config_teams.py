"""Stakeholder & Team Configuration for Proactive M365 Actions.

Defines who receives what, when, and via which channel. The agent
uses this configuration to autonomously distribute signal intelligence
across the organisation via MCP-governed M365 services.

Loaded from environment variable STAKEHOLDER_CONFIG_PATH or defaults
to ./config/stakeholders.json.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Stakeholder:
    """A person who receives signal intelligence."""

    name: str
    email: str
    role: str  # e.g. "AE Lead", "Sales Director", "VP Public Sector"
    teams_id: str = ""  # Teams user ID (optional, resolved from email)

    # What this person cares about — empty = everything
    categories: list[str] = field(default_factory=list)
    min_confidence: float = 0.0  # Only see signals above this threshold

    # Notification preferences
    receives_daily_digest: bool = True
    receives_instant_alerts: bool = False  # HIGH confidence only
    receives_weekly_brief: bool = True
    receives_monthly_report: bool = True


@dataclass(frozen=True)
class TeamConfig:
    """A team of stakeholders with shared context."""

    name: str  # e.g. "Public Sector Sales", "Strategy"
    teams_channel_id: str = ""  # Teams channel for group notifications
    planner_plan_id: str = ""  # Planner plan for action tracking
    sharepoint_site_url: str = ""  # SharePoint site for document storage
    members: list[Stakeholder] = field(default_factory=list)


@dataclass(frozen=True)
class ProactiveConfig:
    """Configuration for all proactive M365 actions."""

    # Teams
    teams: list[TeamConfig] = field(default_factory=list)

    # Meeting defaults
    review_meeting_duration_minutes: int = 30
    review_meeting_title_template: str = (
        "Signal Review: {category} — {entity_name}"
    )

    # Email templates
    digest_subject_template: str = (
        "Signal Intelligence Digest — {date} ({signal_count} signals)"
    )
    alert_subject_template: str = (
        "⚡ HIGH Signal: {entity_name} — {category}"
    )

    # Word report settings
    report_template_name: str = "Signal Intelligence Report"
    report_sharepoint_folder: str = "Shared Documents/Signal Reports"

    # Planner settings
    task_title_template: str = "{entity_name}: {recommended_action}"
    task_due_days: int = 7  # Days from detection to task due date

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "ProactiveConfig":
        """Load config from JSON file, or return sensible defaults."""
        if path is None:
            path = Path(
                os.environ.get(
                    "STAKEHOLDER_CONFIG_PATH",
                    "./config/stakeholders.json",
                )
            )

        if not path.exists():
            logger.info(
                "No stakeholder config at %s — using defaults with "
                "placeholder team. Create this file to customise.",
                path,
            )
            return cls._default()

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return cls._from_dict(data)
        except Exception as e:
            logger.warning("Failed to load stakeholder config: %s", e)
            return cls._default()

    @classmethod
    def _default(cls) -> "ProactiveConfig":
        """Sensible defaults for a single-team setup."""
        return cls(
            teams=[
                TeamConfig(
                    name="Public Sector Sales",
                    members=[
                        Stakeholder(
                            name="Sales Team",
                            email=os.environ.get(
                                "MANAGER_EMAIL",
                                "",
                            ),
                            role="Team Lead",
                            receives_daily_digest=True,
                            receives_instant_alerts=True,
                            receives_weekly_brief=True,
                            receives_monthly_report=True,
                        )
                    ],
                )
            ]
        )

    @classmethod
    def _from_dict(cls, data: dict) -> "ProactiveConfig":
        """Parse config from a dictionary."""
        teams = []
        for team_data in data.get("teams", []):
            members = [
                Stakeholder(**m) for m in team_data.get("members", [])
            ]
            teams.append(
                TeamConfig(
                    name=team_data["name"],
                    teams_channel_id=team_data.get("teams_channel_id", ""),
                    planner_plan_id=team_data.get("planner_plan_id", ""),
                    sharepoint_site_url=team_data.get(
                        "sharepoint_site_url", ""
                    ),
                    members=members,
                )
            )

        return cls(
            teams=teams,
            review_meeting_duration_minutes=data.get(
                "review_meeting_duration_minutes", 30
            ),
            review_meeting_title_template=data.get(
                "review_meeting_title_template",
                cls.review_meeting_title_template,
            ),
            digest_subject_template=data.get(
                "digest_subject_template", cls.digest_subject_template
            ),
            alert_subject_template=data.get(
                "alert_subject_template", cls.alert_subject_template
            ),
            report_template_name=data.get(
                "report_template_name", cls.report_template_name
            ),
            report_sharepoint_folder=data.get(
                "report_sharepoint_folder", cls.report_sharepoint_folder
            ),
            task_title_template=data.get(
                "task_title_template", cls.task_title_template
            ),
            task_due_days=data.get("task_due_days", 7),
        )

    @property
    def all_stakeholders(self) -> list[Stakeholder]:
        """Flat list of all stakeholders across all teams."""
        return [m for t in self.teams for m in t.members]

    def stakeholders_for_category(self, category: str) -> list[Stakeholder]:
        """Get stakeholders interested in a specific signal category."""
        result = []
        for s in self.all_stakeholders:
            if not s.categories or category in s.categories:
                result.append(s)
        return result

    def digest_recipients(self) -> list[Stakeholder]:
        """Stakeholders who receive the daily email digest."""
        return [s for s in self.all_stakeholders if s.receives_daily_digest]

    def alert_recipients(self) -> list[Stakeholder]:
        """Stakeholders who receive instant HIGH-confidence alerts."""
        return [s for s in self.all_stakeholders if s.receives_instant_alerts]

    def weekly_recipients(self) -> list[Stakeholder]:
        """Stakeholders who receive the weekly brief."""
        return [s for s in self.all_stakeholders if s.receives_weekly_brief]

    def monthly_recipients(self) -> list[Stakeholder]:
        """Stakeholders who receive the monthly report."""
        return [s for s in self.all_stakeholders if s.receives_monthly_report]
