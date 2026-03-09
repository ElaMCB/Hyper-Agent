"""Shared data shapes for all adapters."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class Defect:
    id: str
    title: str
    severity: str  # e.g. Critical, High, Medium, Low
    status: str
    created: Optional[datetime] = None
    age_days: Optional[float] = None


@dataclass
class TestRun:
    id: str
    name: str
    status: str  # e.g. Passed, Failed, In Progress
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
