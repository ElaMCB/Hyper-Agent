import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from src.shadow.adapters.file_export import (
    FileExportAdapter,
    load_allocations_from_json,
    load_strategy_from_json,
    load_team_from_json,
)
from src.shadow.adapters.gmail import _header_map, _parse_internal_date
from src.shadow.capabilities.brief import get_brief_bullets_and_focus, render_brief
from src.shadow.capabilities.people_capacity import render_people_capacity_md
from src.shadow.capabilities.resource_allocation import render_resource_allocation_md
from src.shadow.capabilities.strategy_lens import render_strategy_md, strategy_summary_bullets
from src.shadow.models import (
    CapacityAllocation,
    Defect,
    MailMessage,
    Snapshot,
    StrategySignal,
    TeamMember,
)
from src.shadow.snapshot import build_snapshot


def _snapshot(**overrides):
    values = {
        "as_of": datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc),
        "sources": ["unit-test"],
        "defects": [],
        "test_runs": [],
        "mail_messages": [],
        "team_members": [],
        "capacity_allocations": [],
        "strategy_signals": [],
        "notes": [],
    }
    values.update(overrides)
    return Snapshot(**values)


class GmailParsingTests(unittest.TestCase):
    def test_header_map_normalizes_names_and_preserves_latest_value(self):
        payload = {
            "headers": [
                {"name": "Subject", "value": " First "},
                {"name": "FROM", "value": "sender@example.com"},
                {"name": "subject", "value": "Second"},
                {"name": "", "value": "ignored"},
            ]
        }

        headers = _header_map(payload)

        self.assertEqual(headers["subject"], "Second")
        self.assertEqual(headers["from"], "sender@example.com")
        self.assertNotIn("", headers)

    def test_parse_internal_date_handles_valid_and_bad_values(self):
        self.assertEqual(
            _parse_internal_date("1609459200000"),
            datetime(2021, 1, 1, tzinfo=timezone.utc),
        )
        self.assertIsNone(_parse_internal_date(None))
        self.assertIsNone(_parse_internal_date("not-a-timestamp"))


class FileExportLoaderTests(unittest.TestCase):
    def test_team_loader_coerces_skills_and_string_booleans(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "team.json"
            path.write_text(
                json.dumps(
                    {
                        "team": [
                            {
                                "id": "qe-1",
                                "name": "Alex",
                                "skills": "API, CI, ",
                                "on_vacation": "false",
                            },
                            {
                                "id": "qe-2",
                                "name": "Jordan",
                                "skills": ["UI"],
                                "vacation": "yes",
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )

            team = load_team_from_json(path)

        self.assertEqual(team[0].skills, ["API", "CI"])
        self.assertFalse(team[0].on_vacation)
        self.assertTrue(team[1].on_vacation)

    def test_allocation_loader_preserves_zero_and_rejects_invalid_pct(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "allocations.json"
            path.write_text(
                json.dumps(
                    {
                        "allocations": [
                            {"id": "zero", "person_id": "qe-1", "focus_pct": 0},
                            {"id": "alias", "person_id": "qe-2", "allocation_pct": "25"},
                            {"id": "bad", "person_id": "qe-3", "pct": "many"},
                        ]
                    }
                ),
                encoding="utf-8",
            )

            allocations = load_allocations_from_json(path)

        self.assertEqual([a.focus_pct for a in allocations], [0, 25, None])

    def test_strategy_loader_accepts_wrapped_strategy_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "strategy.json"
            path.write_text(
                json.dumps(
                    {
                        "strategy": [
                            {
                                "key": "st-1",
                                "theme": "Automation",
                                "title": "Stabilize CI",
                                "priority": "P0",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            strategy = load_strategy_from_json(path)

        self.assertEqual(strategy[0].id, "st-1")
        self.assertEqual(strategy[0].pillar, "Automation")
        self.assertEqual(strategy[0].summary, "Stabilize CI")

    def test_missing_optional_files_return_empty_lists(self):
        with tempfile.TemporaryDirectory() as tmp:
            adapter = FileExportAdapter(Path(tmp))

            self.assertEqual(adapter.get_team_members(), [])
            self.assertEqual(adapter.get_allocations(), [])
            self.assertEqual(adapter.get_strategy_signals(), [])


class SnapshotBuildTests(unittest.TestCase):
    def test_qe_file_flags_load_sources_without_work_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = root / "data"
            data.mkdir()
            (data / "team.json").write_text(
                json.dumps([{"id": "qe-1", "name": "Alex"}]),
                encoding="utf-8",
            )
            (data / "allocations.json").write_text(
                json.dumps([{"id": "al-1", "person_id": "qe-1", "focus_pct": 50}]),
                encoding="utf-8",
            )
            (data / "strategy.json").write_text(
                json.dumps([{"id": "st-1", "pillar": "Automation", "priority": "P0"}]),
                encoding="utf-8",
            )

            snapshot = build_snapshot(
                root,
                {
                    "data": {
                        "dir": "data",
                        "load_defects": False,
                        "load_test_runs": False,
                        "load_team": True,
                        "load_allocations": True,
                        "load_strategy": True,
                    }
                },
            )

        self.assertEqual(len(snapshot.team_members), 1)
        self.assertEqual(len(snapshot.capacity_allocations), 1)
        self.assertEqual(len(snapshot.strategy_signals), 1)
        self.assertEqual(snapshot.defects, [])
        self.assertEqual(snapshot.test_runs, [])
        self.assertIn("File: team (team.json)", snapshot.sources)
        self.assertIn("File: allocations (allocations.json)", snapshot.sources)
        self.assertIn("File: strategy (strategy.json)", snapshot.sources)

    def test_gmail_errors_are_notes_not_successful_empty_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "data").mkdir()

            with patch(
                "src.shadow.snapshot.fetch_gmail_messages",
                return_value=([], ["Gmail: OAuth client JSON not found at missing.json"]),
            ):
                snapshot = build_snapshot(
                    root,
                    {
                        "gmail": {"enabled": True},
                        "data": {
                            "dir": "data",
                            "load_defects": False,
                            "load_test_runs": False,
                            "load_team": False,
                            "load_allocations": False,
                            "load_strategy": False,
                        },
                    },
                )

        self.assertEqual(snapshot.notes, ["Gmail: OAuth client JSON not found at missing.json"])
        self.assertNotIn("Gmail: connected (0 messages for this query)", snapshot.sources)
        self.assertIn("(No sources", snapshot.sources[0])


class BriefAndQeRenderingTests(unittest.TestCase):
    def test_mail_only_brief_prioritizes_inbox_triage_focus(self):
        snapshot = _snapshot(
            mail_messages=[
                MailMessage(
                    id="m1",
                    subject="Release question",
                    from_addr="lead@example.com",
                    snippet="Can we ship?",
                    is_unread=True,
                )
            ]
        )

        bullets, focus = get_brief_bullets_and_focus(snapshot, {"brief": {"max_bullets": 5}})

        self.assertEqual(bullets[0], "Gmail: 1 in view, 1 unread.")
        self.assertIn("Triage unread Gmail", focus)

    def test_qe_context_budget_precedes_work_bullets(self):
        snapshot = _snapshot(
            defects=[Defect(id="DEF-1", title="Token expiry", severity="Critical", status="Open")],
            team_members=[TeamMember(id="qe-1", name="Alex", on_vacation=False)],
            capacity_allocations=[
                CapacityAllocation(
                    id="al-1",
                    person_id="qe-1",
                    person_name="Alex",
                    app_name="Billing",
                    focus_pct=60,
                )
            ],
            strategy_signals=[
                StrategySignal(
                    id="st-1",
                    pillar="Automation",
                    summary="Stabilize releases",
                    priority="P0",
                )
            ],
        )

        bullets, focus = get_brief_bullets_and_focus(
            snapshot,
            {"brief": {"include_qe_context": True, "max_qe_context_bullets": 2}},
            max_bullets=3,
        )

        self.assertEqual(len(bullets), 3)
        self.assertTrue(bullets[0].startswith("QE team (file):"))
        self.assertTrue(bullets[1].startswith("1:1 hygiene:"))
        self.assertTrue(bullets[2].startswith("Defects:"))
        self.assertIn("people/capacity/strategy", focus)

    def test_render_brief_includes_provenance_and_adapter_notes(self):
        snapshot = _snapshot(
            sources=["File: defects (defects.json)"],
            notes=["Gmail: OAuth client JSON not found at missing.json"],
            defects=[Defect(id="DEF-1", title="Token expiry", severity="Critical", status="Open")],
        )

        markdown = render_brief(snapshot, Path("/workspace"), {"brief": {"title": "# Morning brief"}})

        self.assertIn("# Morning brief", markdown)
        self.assertIn("Defects: 1 total, 1 critical/high, 1 not closed.", markdown)
        self.assertIn("*As of 2026-05-01T12:00:00Z (UTC) · Sources: File: defects (defects.json)*", markdown)
        self.assertIn("*Gmail: OAuth client JSON not found at missing.json*", markdown)

    def test_resource_allocation_warns_on_overallocation_and_keeps_zero_pct(self):
        snapshot = _snapshot(
            capacity_allocations=[
                CapacityAllocation("al-1", "qe-1", "Alex", "Billing", "2026-W18", 60),
                CapacityAllocation("al-2", "qe-1", "Alex", "Mobile", "2026-W18", 50),
                CapacityAllocation("al-3", "qe-2", "Jordan", "Admin", "2026-W18", 0),
            ]
        )

        markdown = render_resource_allocation_md(snapshot, {})

        self.assertIn("**Warning:** focus % sums > 100", markdown)
        self.assertIn("- qe-1 @ 2026-W18", markdown)
        self.assertIn("**Jordan** — 0% · sprint `2026-W18`", markdown)
        self.assertIn("| Jordan | Admin | 2026-W18 | 0 |", markdown)

    def test_people_capacity_marks_stale_one_on_ones(self):
        snapshot = _snapshot(
            team_members=[
                TeamMember(
                    id="qe-1",
                    name="Jordan Lee",
                    morale_flag="amber",
                    last_one_on_one=datetime(2026, 3, 1),
                )
            ]
        )

        markdown = render_people_capacity_md(snapshot, {"people": {"one_on_one_stale_days": 21}})

        self.assertIn("Morale watch (amber/red):** Jordan Lee", markdown)
        self.assertIn("1:1 stale (>21d or missing):** Jordan Lee", markdown)

    def test_strategy_rendering_and_summary_order_p0_before_p1(self):
        snapshot = _snapshot(
            strategy_signals=[
                StrategySignal("st-2", "Ownership", "Clarify RACI", "2026-H2", "P1", "Draft"),
                StrategySignal("st-1", "Automation", "Stabilize CI", "FY26", "P0", "Active"),
            ]
        )

        markdown = render_strategy_md(snapshot, {})
        summary = strategy_summary_bullets(snapshot, {})[0]

        self.assertLess(markdown.index("## Automation"), markdown.index("## Ownership"))
        self.assertIn("**Automation** (P0): Stabilize CI", summary)


if __name__ == "__main__":
    unittest.main()
