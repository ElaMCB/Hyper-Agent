import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from src.shadow.adapters.file_export import FileExportAdapter
from src.shadow.capabilities.brief import get_brief_bullets_and_focus
from src.shadow.capabilities.resource_allocation import render_resource_allocation_md
from src.shadow.capabilities.strategy_lens import render_strategy_md
from src.shadow.models import CapacityAllocation, Defect, Snapshot, StrategySignal, TeamMember, TestRun
from src.shadow.snapshot import build_snapshot


class FileExportQeDataTests(unittest.TestCase):
    def test_qe_json_loaders_accept_export_aliases_and_invalid_allocation_pct(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            (data_dir / "team-export.json").write_text(
                json.dumps(
                    {
                        "members": [
                            {
                                "employee_id": "qe-7",
                                "name": "Priya Shah",
                                "role": "QE Lead",
                                "skills": "API, CI, , Security",
                                "vacation": True,
                                "vacation_until": "14/05/2026",
                                "morale": "yellow",
                                "last_1_1": "2026-05-01",
                                "performance_note": "Owns checkout risk",
                            },
                            "ignore malformed export row",
                        ]
                    }
                ),
                encoding="utf-8",
            )
            (data_dir / "alloc-export.json").write_text(
                json.dumps(
                    {
                        "assignments": [
                            {
                                "key": "alloc-1",
                                "person": "qe-7",
                                "name": "Priya Shah",
                                "app": "Checkout",
                                "sprint": "2026-W20",
                                "pct": "60",
                                "note": "Regression owner",
                            },
                            {
                                "key": "alloc-2",
                                "person": "qe-8",
                                "name": "Marco Lee",
                                "app": "Billing",
                                "sprint": "2026-W20",
                                "allocation_pct": "not a number",
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )
            (data_dir / "strategy-export.json").write_text(
                json.dumps(
                    {
                        "pillars": [
                            {
                                "key": "strat-1",
                                "theme": "Release readiness",
                                "title": "Protect checkout conversion before launch",
                                "priority": "P1",
                                "evidence": "Launch readiness review",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            adapter = FileExportAdapter(data_dir)

            team = adapter.get_team_members("team-export.json")
            self.assertEqual(len(team), 1)
            self.assertEqual(team[0].id, "qe-7")
            self.assertEqual(team[0].skills, ["API", "CI", "Security"])
            self.assertTrue(team[0].on_vacation)
            self.assertEqual(team[0].vacation_until, datetime(2026, 5, 14))
            self.assertEqual(team[0].morale_flag, "yellow")
            self.assertEqual(team[0].last_one_on_one, datetime(2026, 5, 1))

            allocations = adapter.get_allocations("alloc-export.json")
            self.assertEqual([a.focus_pct for a in allocations], [60, None])
            self.assertEqual(allocations[0].person_id, "qe-7")
            self.assertEqual(allocations[1].app_name, "Billing")

            strategy = adapter.get_strategy_signals("strategy-export.json")
            self.assertEqual(len(strategy), 1)
            self.assertEqual(strategy[0].id, "strat-1")
            self.assertEqual(strategy[0].pillar, "Release readiness")
            self.assertEqual(strategy[0].summary, "Protect checkout conversion before launch")
            self.assertEqual(strategy[0].evidence_ref, "Launch readiness review")


class QeCapabilityRenderingTests(unittest.TestCase):
    def test_resource_allocation_flags_overcommit_per_person_and_sprint(self):
        snapshot = Snapshot(
            as_of=datetime(2026, 5, 14, tzinfo=timezone.utc),
            capacity_allocations=[
                CapacityAllocation(
                    id="a1",
                    person_id="qe-1",
                    person_name="Alex Kim",
                    app_name="Checkout",
                    sprint_label="2026-W20",
                    focus_pct=70,
                    commitment_note="release | regression",
                ),
                CapacityAllocation(
                    id="a2",
                    person_id="qe-1",
                    person_name="Alex Kim",
                    app_name="Billing",
                    sprint_label="2026-W20",
                    focus_pct=40,
                ),
                CapacityAllocation(
                    id="a3",
                    person_id="qe-1",
                    person_name="Alex Kim",
                    sprint_label="2026-W21",
                    focus_pct=80,
                ),
            ],
        )

        markdown = render_resource_allocation_md(snapshot, {})

        self.assertIn("**Warning:** focus % sums > 100 for:", markdown)
        self.assertIn("- qe-1 @ 2026-W20", markdown)
        self.assertNotIn("- qe-1 @ 2026-W21", markdown)
        self.assertIn("### (no app)", markdown)
        self.assertIn("release \\| regression", markdown)

    def test_strategy_renderer_orders_priority_before_horizon_and_pillar(self):
        snapshot = Snapshot(
            as_of=datetime(2026, 5, 14, tzinfo=timezone.utc),
            strategy_signals=[
                StrategySignal(id="p2", pillar="Mobile", summary="Later", horizon="FY26", priority="P2"),
                StrategySignal(id="p0", pillar="API", summary="Now", horizon="FY26", priority="P0"),
                StrategySignal(id="p1", pillar="Web", summary="Next", horizon="FY25", priority="P1"),
            ],
        )

        markdown = render_strategy_md(snapshot, {})

        self.assertLess(markdown.index("## API"), markdown.index("## Web"))
        self.assertLess(markdown.index("## Web"), markdown.index("## Mobile"))


class SnapshotAndBriefQeIntegrationTests(unittest.TestCase):
    def test_build_snapshot_loads_enabled_qe_files_and_records_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_dir = root / "data"
            data_dir.mkdir()
            (data_dir / "team.json").write_text(
                json.dumps([{"id": "qe-1", "name": "Alex Kim"}]),
                encoding="utf-8",
            )
            (data_dir / "allocations.json").write_text(
                json.dumps([{"id": "a1", "person_id": "qe-1", "app_name": "Checkout"}]),
                encoding="utf-8",
            )
            (data_dir / "strategy.json").write_text(
                json.dumps([{"id": "s1", "pillar": "Automation", "summary": "Raise coverage"}]),
                encoding="utf-8",
            )
            (data_dir / "defects.json").write_text(
                json.dumps([{"id": "bug-1", "title": "Disabled sample defect"}]),
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

            self.assertEqual(snapshot.defects, [])
            self.assertEqual(len(snapshot.team_members), 1)
            self.assertEqual(len(snapshot.capacity_allocations), 1)
            self.assertEqual(len(snapshot.strategy_signals), 1)
            self.assertEqual(
                snapshot.sources,
                [
                    "File: team (team.json)",
                    "File: allocations (allocations.json)",
                    "File: strategy (strategy.json)",
                ],
            )

    def test_brief_qe_context_is_capped_before_work_bullets(self):
        snapshot = Snapshot(
            as_of=datetime(2026, 5, 14, tzinfo=timezone.utc),
            sources=["test"],
            defects=[
                Defect(
                    id="BUG-1",
                    title="Checkout payment callback intermittently drops high value orders",
                    severity="Critical",
                    status="Open",
                )
            ],
            test_runs=[TestRun(id="run-1", name="Nightly regression", status="Failed", total=10, passed=8, failed=2)],
            team_members=[
                TeamMember(
                    id="qe-1",
                    name="Alex Kim",
                    on_vacation=True,
                    last_one_on_one=datetime(2026, 4, 1),
                )
            ],
            capacity_allocations=[
                CapacityAllocation(id="a1", person_id="qe-1", app_name="Checkout", focus_pct=100)
            ],
            strategy_signals=[
                StrategySignal(id="s1", pillar="Automation", summary="Cover checkout API", priority="P0")
            ],
        )

        bullets, suggested = get_brief_bullets_and_focus(
            snapshot,
            {"brief": {"include_qe_context": True, "max_qe_context_bullets": 2}, "people": {"one_on_one_stale_days": 21}},
            max_bullets=4,
        )

        self.assertEqual(len(bullets), 4)
        self.assertEqual(bullets[0], "QE team (file): 1 people, 1 flagged on vacation.")
        self.assertEqual(bullets[1], "1:1 hygiene: 1 member(s) past 21d or missing last 1:1 date.")
        self.assertEqual(bullets[2], "Defects: 1 total, 1 critical/high, 1 not closed.")
        self.assertTrue(bullets[3].startswith("Top severity: BUG-1"))
        self.assertEqual(
            suggested,
            "Balance people/capacity/strategy context with inbox and execution signals for today.",
        )


if __name__ == "__main__":
    unittest.main()
