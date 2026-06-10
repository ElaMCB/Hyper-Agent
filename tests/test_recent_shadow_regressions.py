import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from src.shadow.adapters.file_export import load_allocations_from_json, load_team_from_json
from src.shadow.adapters.gmail import _header_map, _parse_internal_date
from src.shadow.capabilities.brief import get_brief_bullets_and_focus
from src.shadow.capabilities.headquarters import render_headquarters_html
from src.shadow.capabilities.resource_allocation import render_resource_allocation_md
from src.shadow.capabilities.strategy_lens import strategy_summary_bullets
from src.shadow.models import CapacityAllocation, MailMessage, Snapshot, StrategySignal, TeamMember
from src.shadow.snapshot import build_snapshot


def _snapshot(**overrides) -> Snapshot:
    defaults = {
        "as_of": datetime(2026, 6, 10, 10, 0, tzinfo=timezone.utc),
        "sources": ["test"],
        "defects": [],
        "test_runs": [],
        "mail_messages": [],
        "team_members": [],
        "capacity_allocations": [],
        "strategy_signals": [],
        "notes": [],
    }
    defaults.update(overrides)
    return Snapshot(**defaults)


def _write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


class FileExportParsingTests(unittest.TestCase):
    def test_team_loader_coerces_string_booleans_and_skills(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "team.json"
            _write_json(
                path,
                {
                    "members": [
                        {"id": "a", "name": "Alex", "skills": "API, UI", "on_vacation": "false"},
                        {"id": "b", "name": "Blair", "vacation": "yes"},
                    ]
                },
            )

            members = load_team_from_json(path)

        self.assertEqual(["API", "UI"], members[0].skills)
        self.assertFalse(members[0].on_vacation)
        self.assertTrue(members[1].on_vacation)

    def test_allocation_loader_preserves_zero_and_ignores_invalid_percentages(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "allocations.json"
            _write_json(
                path,
                {
                    "allocations": [
                        {"id": "zero", "person_id": "a", "focus_pct": 0},
                        {"id": "fallback", "person_id": "b", "focus_pct": "", "allocation_pct": "25"},
                        {"id": "bad", "person_id": "c", "pct": "not-a-number"},
                    ]
                },
            )

            rows = load_allocations_from_json(path)

        self.assertEqual(0, rows[0].focus_pct)
        self.assertEqual(25, rows[1].focus_pct)
        self.assertIsNone(rows[2].focus_pct)


class GmailAndSnapshotTests(unittest.TestCase):
    def test_gmail_helpers_normalize_headers_and_dates(self) -> None:
        headers = _header_map(
            {
                "headers": [
                    {"name": "Subject", "value": "Release review"},
                    {"name": "FROM", "value": "qe@example.com"},
                    {"name": "", "value": "ignored"},
                    {"value": "ignored"},
                ]
            }
        )

        self.assertEqual("Release review", headers["subject"])
        self.assertEqual("qe@example.com", headers["from"])
        self.assertNotIn("", headers)
        self.assertEqual(
            datetime(2023, 11, 14, 22, 13, 20, tzinfo=timezone.utc),
            _parse_internal_date("1700000000000"),
        )
        self.assertIsNone(_parse_internal_date("not-ms"))

    def test_snapshot_records_gmail_failure_as_note_not_false_zero_source(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            config = {
                "gmail": {"enabled": True},
                "data": {
                    "dir": "data",
                    "load_defects": False,
                    "load_test_runs": False,
                    "load_team": False,
                    "load_allocations": False,
                    "load_strategy": False,
                },
            }
            with patch(
                "src.shadow.snapshot.fetch_gmail_messages",
                return_value=([], ["Gmail: listing messages failed (boom)."]),
            ):
                snap = build_snapshot(root, config)

        self.assertIn("Gmail: listing messages failed (boom).", snap.notes)
        self.assertNotIn("Gmail: connected (0 messages for this query)", snap.sources)

    def test_snapshot_loads_qe_files_when_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            data = root / "exports"
            data.mkdir()
            _write_json(data / "team.json", [{"id": "qe-1", "name": "Alex", "on_vacation": "false"}])
            _write_json(
                data / "allocations.json",
                [{"id": "al-1", "person_id": "qe-1", "person_name": "Alex", "focus_pct": 0}],
            )
            _write_json(
                data / "strategy.json",
                [{"id": "st-1", "pillar": "Automation", "priority": "P0", "summary": "Cover APIs"}],
            )

            snap = build_snapshot(
                root,
                {
                    "data": {
                        "dir": "exports",
                        "load_defects": False,
                        "load_test_runs": False,
                        "load_team": True,
                        "load_allocations": True,
                        "load_strategy": True,
                    }
                },
            )

        self.assertFalse(snap.team_members[0].on_vacation)
        self.assertEqual(0, snap.capacity_allocations[0].focus_pct)
        self.assertEqual(
            ["File: team (team.json)", "File: allocations (allocations.json)", "File: strategy (strategy.json)"],
            snap.sources,
        )


class CapabilityRegressionTests(unittest.TestCase):
    def test_brief_caps_qe_context_and_uses_blended_focus(self) -> None:
        snap = _snapshot(
            mail_messages=[
                MailMessage(
                    id="m1",
                    subject="Unread stakeholder question",
                    from_addr="vp@example.com",
                    snippet="Can we ship?",
                    is_unread=True,
                )
            ],
            team_members=[
                TeamMember(
                    id="qe-1",
                    name="Alex",
                    on_vacation=False,
                    last_one_on_one=datetime(2026, 6, 10, tzinfo=timezone.utc),
                )
            ],
            capacity_allocations=[CapacityAllocation(id="al-1", person_id="qe-1", app_name="Billing")],
            strategy_signals=[
                StrategySignal(id="st-1", pillar="Automation", priority="P0", summary="Raise API coverage")
            ],
        )

        bullets, suggested = get_brief_bullets_and_focus(
            snap,
            {"brief": {"include_qe_context": True, "max_qe_context_bullets": 2, "max_bullets": 3}},
            max_bullets=3,
        )

        self.assertEqual(3, len(bullets))
        self.assertTrue(bullets[0].startswith("QE team (file): 1 people"))
        self.assertTrue(bullets[1].startswith("Allocations: 1 row"))
        self.assertEqual("Gmail: 1 in view, 1 unread.", bullets[2])
        self.assertEqual(
            "Balance people/capacity/strategy context with inbox and execution signals for today.",
            suggested,
        )

    def test_resource_allocation_warns_on_overcommit_and_renders_zero_percent(self) -> None:
        snap = _snapshot(
            capacity_allocations=[
                CapacityAllocation(id="a1", person_id="qe-1", person_name="Alex", app_name="Billing", sprint_label="S1", focus_pct=60),
                CapacityAllocation(id="a2", person_id="qe-1", person_name="Alex", app_name="Mobile", sprint_label="S1", focus_pct=50),
                CapacityAllocation(id="a3", person_id="qe-2", person_name="Blair", app_name="Admin", sprint_label="S1", focus_pct=0),
            ]
        )

        md = render_resource_allocation_md(snap, {})

        self.assertIn("**Warning:** focus % sums > 100 for:", md)
        self.assertIn("- qe-1 @ S1", md)
        self.assertIn("**Blair** — 0% · sprint `S1`", md)

    def test_strategy_summary_uses_p0_before_p1(self) -> None:
        snap = _snapshot(
            strategy_signals=[
                StrategySignal(id="st-1", pillar="Ownership", priority="P1", summary="Clarify RACI"),
                StrategySignal(id="st-2", pillar="Automation", priority="P0", summary="Stabilize critical suites"),
            ]
        )

        bullets = strategy_summary_bullets(snap, {})

        self.assertIn("**Automation** (P0): Stabilize critical suites", bullets[0])

    def test_headquarters_escapes_user_content_and_can_hide_qe_panels(self) -> None:
        snap = _snapshot(
            mail_messages=[
                MailMessage(
                    id="message-with-long-id",
                    subject="<script>alert(1)</script>",
                    from_addr="attacker@example.com",
                    snippet="<b>snippet</b>",
                )
            ],
            team_members=[TeamMember(id="qe-1", name="Alex")],
            capacity_allocations=[CapacityAllocation(id="al-1", person_id="qe-1", app_name="Billing")],
            strategy_signals=[StrategySignal(id="st-1", pillar="Automation", summary="Cover APIs")],
        )

        html = render_headquarters_html(
            snap,
            {"headquarters": {"show_qe_panels": False}},
            full_brief_markdown="# Brief\n\n<script>raw</script>",
        )

        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertNotIn("<script>raw</script>", html)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)
        self.assertIn("&lt;script&gt;raw&lt;/script&gt;", html)
        self.assertNotIn("<h2>QE team (file)</h2>", html)
        self.assertNotIn("<h2>QE allocations</h2>", html)
        self.assertNotIn("<h2>QE strategy signals</h2>", html)


if __name__ == "__main__":
    unittest.main()
