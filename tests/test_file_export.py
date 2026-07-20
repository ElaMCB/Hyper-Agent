import json
import tempfile
import unittest
from pathlib import Path

from src.shadow.adapters.file_export import FileExportAdapter


class FileExportAdapterTests(unittest.TestCase):
    def test_loads_qe_json_shapes_and_normalizes_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            (data_dir / "team.json").write_text(
                json.dumps(
                    {
                        "members": [
                            {
                                "employee_id": "qa-1",
                                "name": "Alex",
                                "role": "QE Lead",
                                "skills": "api, mobile, automation",
                                "on_vacation": True,
                                "vacation_until": "2026-05-25",
                                "morale": "amber",
                                "last_1_1": "01/05/2026",
                                "performance_note": "Owns release readiness",
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
                                "person": "qa-1",
                                "name": "Alex",
                                "app": "Checkout",
                                "sprint": "S42",
                                "pct": "75",
                                "note": "Regression owner",
                            },
                            {
                                "key": "alloc-2",
                                "person": "qa-2",
                                "app": "Profile",
                                "sprint": "S42",
                                "allocation_pct": "not-a-number",
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
                                "key": "strat-1",
                                "theme": "Release confidence",
                                "title": "Lift automation signal before launch",
                                "horizon": "current",
                                "priority": "P1",
                                "status": "At risk",
                                "evidence": "ADO dashboard",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            adapter = FileExportAdapter(data_dir)

            team = adapter.get_team_members()
            self.assertEqual(len(team), 1)
            self.assertEqual(team[0].id, "qa-1")
            self.assertEqual(team[0].skills, ["api", "mobile", "automation"])
            self.assertTrue(team[0].on_vacation)
            self.assertEqual(team[0].vacation_until.strftime("%Y-%m-%d"), "2026-05-25")
            self.assertEqual(team[0].last_one_on_one.strftime("%Y-%m-%d"), "2026-05-01")

            allocations = adapter.get_allocations()
            self.assertEqual(len(allocations), 2)
            self.assertEqual(allocations[0].focus_pct, 75)
            self.assertIsNone(allocations[1].focus_pct)
            self.assertEqual(allocations[0].commitment_note, "Regression owner")

            strategy = adapter.get_strategy_signals()
            self.assertEqual(len(strategy), 1)
            self.assertEqual(strategy[0].id, "strat-1")
            self.assertEqual(strategy[0].pillar, "Release confidence")
            self.assertEqual(strategy[0].summary, "Lift automation signal before launch")
            self.assertEqual(strategy[0].evidence_ref, "ADO dashboard")

    def test_missing_optional_files_return_empty_lists(self):
        with tempfile.TemporaryDirectory() as tmp:
            adapter = FileExportAdapter(Path(tmp))

            self.assertEqual(adapter.get_team_members(), [])
            self.assertEqual(adapter.get_allocations(), [])
            self.assertEqual(adapter.get_strategy_signals(), [])


if __name__ == "__main__":
    unittest.main()
