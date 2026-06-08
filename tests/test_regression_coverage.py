import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from src.shadow.adapters.file_export import FileExportAdapter
from src.shadow.capabilities.brief import get_brief_bullets_and_focus
from src.shadow.capabilities.resource_allocation import render_resource_allocation_md
from src.shadow.models import CapacityAllocation, Snapshot
from src.shadow.output.writer import prune_headquarters_archives
from src.shadow.snapshot import build_snapshot


class FileExportRegressionTests(unittest.TestCase):
    def test_qe_json_aliases_and_invalid_allocation_percent_are_parsed_safely(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            (data_dir / "team.json").write_text(
                json.dumps(
                    {
                        "members": [
                            {
                                "employee_id": 101,
                                "name": "Ava",
                                "role": "QA Lead",
                                "skills": "api, regression, payments",
                                "vacation": True,
                                "vacation_until": "2026-06-12",
                                "morale": "amber",
                                "last_1_1": "01/06/2026",
                                "performance_note": "Owns checkout risk",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            (data_dir / "allocations.json").write_text(
                json.dumps(
                    {
                        "assignments": [
                            {
                                "key": "alloc-1",
                                "person": 101,
                                "name": "Ava",
                                "app": "Checkout",
                                "sprint": "Sprint 42",
                                "pct": "60",
                                "note": "automation focus",
                            },
                            {
                                "key": "alloc-2",
                                "person": 101,
                                "name": "Ava",
                                "app": "Payments",
                                "sprint": "Sprint 42",
                                "pct": "not-a-number",
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )
            (data_dir / "strategy.json").write_text(
                json.dumps(
                    {
                        "pillars": [
                            {
                                "key": "s1",
                                "theme": "Release confidence",
                                "title": "Reduce escaped checkout defects",
                                "priority": "P0",
                                "horizon": "Now",
                                "status": "At risk",
                                "evidence": "ADO query",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            adapter = FileExportAdapter(data_dir)

            team = adapter.get_team_members()
            self.assertEqual(team[0].id, "101")
            self.assertEqual(team[0].skills, ["api", "regression", "payments"])
            self.assertTrue(team[0].on_vacation)
            self.assertEqual(team[0].vacation_until, datetime(2026, 6, 12))
            self.assertEqual(team[0].last_one_on_one, datetime(2026, 6, 1))
            self.assertEqual(team[0].morale_flag, "amber")

            allocations = adapter.get_allocations()
            self.assertEqual(allocations[0].focus_pct, 60)
            self.assertIsNone(allocations[1].focus_pct)
            self.assertEqual(allocations[1].app_name, "Payments")

            strategy = adapter.get_strategy_signals()
            self.assertEqual(strategy[0].id, "s1")
            self.assertEqual(strategy[0].pillar, "Release confidence")
            self.assertEqual(strategy[0].summary, "Reduce escaped checkout defects")
            self.assertEqual(strategy[0].evidence_ref, "ADO query")

    def test_snapshot_respects_disabled_work_data_while_loading_enabled_qe_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_dir = root / "data"
            data_dir.mkdir()
            (data_dir / "defects.json").write_text(
                json.dumps([{"id": "D1", "title": "Should stay disabled", "severity": "High"}]),
                encoding="utf-8",
            )
            (data_dir / "test_runs.json").write_text(
                json.dumps([{"id": "R1", "name": "Should stay disabled", "status": "Failed"}]),
                encoding="utf-8",
            )
            (data_dir / "team.json").write_text(
                json.dumps(
                    [
                        {
                            "id": "u1",
                            "name": "Ava",
                            "on_vacation": True,
                            "last_one_on_one": "2026-05-01",
                        }
                    ]
                ),
                encoding="utf-8",
            )
            (data_dir / "allocations.json").write_text(
                json.dumps([{"id": "a1", "person_id": "u1", "app_name": "Checkout", "focus_pct": 50}]),
                encoding="utf-8",
            )
            (data_dir / "strategy.json").write_text(
                json.dumps(
                    [
                        {
                            "id": "s1",
                            "pillar": "Release confidence",
                            "summary": "Focus checkout risk",
                            "priority": "P0",
                        }
                    ]
                ),
                encoding="utf-8",
            )

            config = {
                "data": {
                    "dir": "data",
                    "load_defects": False,
                    "load_test_runs": False,
                    "load_team": True,
                    "load_allocations": True,
                    "load_strategy": True,
                },
                "brief": {
                    "include_qe_context": True,
                    "max_qe_context_bullets": 3,
                    "max_bullets": 3,
                },
                "people": {"one_on_one_stale_days": 21},
            }

            snapshot = build_snapshot(root, config)

            self.assertEqual(snapshot.defects, [])
            self.assertEqual(snapshot.test_runs, [])
            self.assertEqual(len(snapshot.team_members), 1)
            self.assertEqual(len(snapshot.capacity_allocations), 1)
            self.assertEqual(len(snapshot.strategy_signals), 1)
            self.assertNotIn("defects", " ".join(snapshot.sources).lower())
            self.assertNotIn("test runs", " ".join(snapshot.sources).lower())

            bullets, suggested = get_brief_bullets_and_focus(snapshot, config)
            self.assertEqual(
                bullets,
                [
                    "QE team (file): 1 people, 1 flagged on vacation.",
                    "1:1 hygiene: 1 member(s) past 21d or missing last 1:1 date.",
                    "Allocations: 1 row(s) across 1 app bucket(s).",
                ],
            )
            self.assertEqual(
                suggested,
                "Reconcile team capacity and sprint allocations with strategy signals; pick 1\u20132 leadership moves today.",
            )


class CapabilityRenderingRegressionTests(unittest.TestCase):
    def test_allocation_renderer_warns_when_person_exceeds_full_focus_for_a_sprint(self):
        snapshot = Snapshot(
            as_of=datetime(2026, 6, 8, tzinfo=timezone.utc),
            capacity_allocations=[
                CapacityAllocation(
                    id="a1",
                    person_id="u1",
                    person_name="Ava",
                    app_name="Checkout",
                    sprint_label="Sprint 42",
                    focus_pct=70,
                    commitment_note="checkout | hardening",
                ),
                CapacityAllocation(
                    id="a2",
                    person_id="u1",
                    person_name="Ava",
                    app_name="Payments",
                    sprint_label="Sprint 42",
                    focus_pct=40,
                ),
            ],
        )

        rendered = render_resource_allocation_md(snapshot, {})

        self.assertIn("**Warning:** focus % sums > 100", rendered)
        self.assertIn("- u1 @ Sprint 42", rendered)
        self.assertIn("checkout \\| hardening", rendered)


class HeadquartersWriterRegressionTests(unittest.TestCase):
    def test_prune_headquarters_archives_keeps_newest_stamped_files_and_stable_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            hq = root / "output" / "headquarters"
            hq.mkdir(parents=True)
            for name in [
                "headquarters-2026-06-01T090000Z.html",
                "headquarters-2026-06-02T090000Z.html",
                "headquarters-2026-06-03T090000Z.html",
                "headquarters-2026-06-04T090000Z.html",
                "latest.html",
                "latest.md",
                "headquarters-notes.txt",
            ]:
                (hq / name).write_text(name, encoding="utf-8")

            removed = prune_headquarters_archives(root, "output/headquarters", max_keep=2)

            self.assertEqual(removed, 2)
            self.assertFalse((hq / "headquarters-2026-06-01T090000Z.html").exists())
            self.assertFalse((hq / "headquarters-2026-06-02T090000Z.html").exists())
            self.assertTrue((hq / "headquarters-2026-06-03T090000Z.html").exists())
            self.assertTrue((hq / "headquarters-2026-06-04T090000Z.html").exists())
            self.assertTrue((hq / "latest.html").exists())
            self.assertTrue((hq / "latest.md").exists())
            self.assertTrue((hq / "headquarters-notes.txt").exists())

    def test_prune_headquarters_archives_keeps_all_when_retention_is_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            hq = root / "output" / "headquarters"
            hq.mkdir(parents=True)
            archives = [
                "headquarters-2026-06-01T090000Z.html",
                "headquarters-2026-06-02T090000Z.html",
            ]
            for name in archives:
                (hq / name).write_text(name, encoding="utf-8")

            removed = prune_headquarters_archives(root, "output/headquarters", max_keep=0)

            self.assertEqual(removed, 0)
            for name in archives:
                self.assertTrue((hq / name).exists())


if __name__ == "__main__":
    unittest.main()
