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
class Snapshot:
    """
    Point-in-time view Shadow used to render briefs (and later prep).
    Every run gets a fresh Snapshot with UTC as_of and explicit sources.
    """

    as_of: datetime
    sources: list[str] = field(default_factory=list)
    defects: list[Defect] = field(default_factory=list)
    test_runs: list[TestRun] = field(default_factory=list)
    """Human-readable issues (e.g. adapter failures) — shown in brief footer."""
    notes: list[str] = field(default_factory=list)
