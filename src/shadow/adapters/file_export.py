"""Read defects and test runs from JSON/CSV files (e.g. exports from Jira, Excel)."""

import csv
import json
from pathlib import Path
from typing import Any

from ..models import Action, CapacityAllocation, Defect, StrategySignal, TeamMember, TestRun


def _parse_datetime(s: str | None) -> Any:
    if not s:
        return None
    from datetime import datetime
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(s.strip()[:19], fmt)
        except (ValueError, TypeError):
            continue
    return None


def load_defects_from_json(path: Path) -> list[Defect]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raw = raw.get("defects", raw.get("issues", [raw]))
    out = []
    for r in raw:
        if isinstance(r, dict):
            created = _parse_datetime(r.get("created") or r.get("Created") or r.get("created_at"))
            out.append(Defect(
                id=str(r.get("id", r.get("key", ""))),
                title=str(r.get("title", r.get("summary", ""))),
                severity=str(r.get("severity", r.get("priority", "Unknown"))),
                status=str(r.get("status", r.get("state", "Open"))),
                created=created,
            ))
    return out


def load_defects_from_csv(path: Path) -> list[Defect]:
    out = []
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            key = row.get("id") or row.get("key") or row.get("Key")
            title = row.get("title") or row.get("summary") or row.get("Summary")
            severity = row.get("severity") or row.get("priority") or "Unknown"
            status = row.get("status") or row.get("Status") or "Open"
            created = _parse_datetime(row.get("created") or row.get("Created"))
            out.append(Defect(id=str(key), title=title, severity=severity, status=status, created=created))
    return out


def load_test_runs_from_json(path: Path) -> list[TestRun]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raw = raw.get("test_runs", raw.get("runs", [raw]))
    out = []
    for r in raw:
        if isinstance(r, dict):
            executed = _parse_datetime(r.get("executed_at") or r.get("ExecutedAt") or r.get("date"))
            out.append(TestRun(
                id=str(r.get("id", r.get("run_id", ""))),
                name=str(r.get("name", r.get("run_name", ""))),
                status=str(r.get("status", r.get("Status", "Unknown"))),
                executed_at=executed,
                passed=r.get("passed"),
                failed=r.get("failed"),
                total=r.get("total"),
            ))
    return out


def _skills_from_row(r: dict) -> list[str]:
    s = r.get("skills")
    if isinstance(s, list):
        return [str(x) for x in s]
    if isinstance(s, str) and s.strip():
        return [x.strip() for x in s.split(",") if x.strip()]
    return []


def load_team_from_json(path: Path) -> list[TeamMember]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raw = raw.get("team", raw.get("members", []))
    out: list[TeamMember] = []
    for r in raw:
        if isinstance(r, dict):
            out.append(
                TeamMember(
                    id=str(r.get("id", r.get("employee_id", ""))),
                    name=str(r.get("name", "")),
                    role=str(r.get("role", "")),
                    skills=_skills_from_row(r),
                    on_vacation=bool(r.get("on_vacation", r.get("vacation", False))),
                    vacation_until=_parse_datetime(r.get("vacation_until")),
                    morale_flag=str(r.get("morale_flag", r.get("morale", ""))),
                    last_one_on_one=_parse_datetime(r.get("last_one_on_one") or r.get("last_1_1")),
                    performance_note=str(r.get("performance_note", "")),
                )
            )
    return out


def load_allocations_from_json(path: Path) -> list[CapacityAllocation]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raw = raw.get("allocations", raw.get("assignments", []))
    out: list[CapacityAllocation] = []
    for r in raw:
        if isinstance(r, dict):
            pct = r.get("focus_pct") or r.get("pct") or r.get("allocation_pct")
            try:
                focus = int(pct) if pct is not None and str(pct).strip() != "" else None
            except (TypeError, ValueError):
                focus = None
            out.append(
                CapacityAllocation(
                    id=str(r.get("id", r.get("key", ""))),
                    person_id=str(r.get("person_id", r.get("person", ""))),
                    person_name=str(r.get("person_name", r.get("name", ""))),
                    app_name=str(r.get("app_name", r.get("app", ""))),
                    sprint_label=str(r.get("sprint_label", r.get("sprint", ""))),
                    focus_pct=focus,
                    commitment_note=str(r.get("commitment_note", r.get("note", ""))),
                )
            )
    return out


def load_strategy_from_json(path: Path) -> list[StrategySignal]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raw = raw.get("strategy", raw.get("signals", raw.get("pillars", [])))
    out: list[StrategySignal] = []
    for r in raw:
        if isinstance(r, dict):
            out.append(
                StrategySignal(
                    id=str(r.get("id", r.get("key", ""))),
                    pillar=str(r.get("pillar", r.get("theme", ""))),
                    summary=str(r.get("summary", r.get("title", ""))),
                    horizon=str(r.get("horizon", "")),
                    priority=str(r.get("priority", "")),
                    status=str(r.get("status", "")),
                    evidence_ref=str(r.get("evidence_ref", r.get("evidence", ""))),
                )
            )
    return out


def load_actions_from_json(path: Path) -> list[Action]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raw = raw.get("actions", raw.get("items", [raw]))
    out = []
    for r in raw:
        if isinstance(r, dict):
            due = _parse_datetime(r.get("due") or r.get("due_date"))
            out.append(Action(
                id=str(r.get("id", r.get("key", ""))),
                title=str(r.get("title", r.get("summary", ""))),
                owner=r.get("owner"),
                due=due,
                status=str(r.get("status", "Open")),
                meeting=r.get("meeting"),
            ))
    return out


class FileExportAdapter:
    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)

    def get_defects(self, filename: str | None = None) -> list[Defect]:
        path = self.data_dir / (filename or "defects.json")
        if not path.exists():
            return []
        if path.suffix.lower() == ".csv":
            return load_defects_from_csv(path)
        return load_defects_from_json(path)

    def get_test_runs(self, filename: str | None = None) -> list[TestRun]:
        path = self.data_dir / (filename or "test_runs.json")
        if not path.exists():
            return []
        return load_test_runs_from_json(path)

    def get_actions(self, filename: str | None = None) -> list[Action]:
        path = self.data_dir / (filename or "actions.json")
        if not path.exists():
            return []
        return load_actions_from_json(path)

    def get_team_members(self, filename: str | None = None) -> list[TeamMember]:
        path = self.data_dir / (filename or "team.json")
        if not path.exists():
            return []
        return load_team_from_json(path)

    def get_allocations(self, filename: str | None = None) -> list[CapacityAllocation]:
        path = self.data_dir / (filename or "allocations.json")
        if not path.exists():
            return []
        return load_allocations_from_json(path)

    def get_strategy_signals(self, filename: str | None = None) -> list[StrategySignal]:
        path = self.data_dir / (filename or "strategy.json")
        if not path.exists():
            return []
        return load_strategy_from_json(path)
