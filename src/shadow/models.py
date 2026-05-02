"""Domain models and the timestamped Snapshot (single spine for all capabilities)."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Defect:
    id: str
    title: str
    severity: str
    status: str
    created: Optional[datetime] = None
    age_days: Optional[float] = None


@dataclass
class TestRun:
    id: str
    name: str
    status: str
    executed_at: Optional[datetime] = None
    passed: Optional[int] = None
    failed: Optional[int] = None
    total: Optional[int] = None


@dataclass
class Action:
    id: str
    title: str
    owner: Optional[str] = None
    due: Optional[datetime] = None
    status: str = "Open"
    meeting: Optional[str] = None


@dataclass
class MailMessage:
    """Gmail (or other mail) row for brief / HQ — keep fields minimal; full body not stored."""

    id: str
    subject: str
    from_addr: str
    snippet: str
    internal_date: Optional[datetime] = None
    is_unread: bool = False


@dataclass
class TeamMember:
    """QE people & capacity — fed from local JSON/CSV you control (see data/team.json sample)."""

    id: str
    name: str
    role: str = ""
    skills: list[str] = field(default_factory=list)
    on_vacation: bool = False
    vacation_until: Optional[datetime] = None
    morale_flag: str = ""
    last_one_on_one: Optional[datetime] = None
    performance_note: str = ""


@dataclass
class CapacityAllocation:
    """Who is on which app this sprint — from data/allocations.json or export."""

    id: str
    person_id: str
    person_name: str = ""
    app_name: str = ""
    sprint_label: str = ""
    focus_pct: Optional[int] = None
    commitment_note: str = ""


@dataclass
class StrategySignal:
    """Portfolio / quality strategy facts you supply — Shadow summarizes, does not invent."""

    id: str
    pillar: str
    summary: str
    horizon: str = ""
    priority: str = ""
    status: str = ""
    evidence_ref: str = ""


@dataclass
class Snapshot:
    """
    Point-in-time view Shadow used to render briefs (and later prep).
    Every run gets a fresh Snapshot with UTC as_of and explicit sources.
    """

    as_of: datetime
    sources: list[str] = field(default_factory=list)
    defects: list[Defect] = field(default_factory=list)
    test_runs: list[TestRun] = field(default_factory=list)
    mail_messages: list[MailMessage] = field(default_factory=list)
    team_members: list[TeamMember] = field(default_factory=list)
    capacity_allocations: list[CapacityAllocation] = field(default_factory=list)
    strategy_signals: list[StrategySignal] = field(default_factory=list)
    """Human-readable issues (e.g. adapter failures) — shown in brief footer."""
    notes: list[str] = field(default_factory=list)
