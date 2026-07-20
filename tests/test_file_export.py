import json
import tempfile
import unittest
from pathlib import Path

from src.shadow.adapters.file_export import FileExportAdapter


class FileExportAdapterTests(unittest.TestCase):
    def test_loads_wrapped_qe_and_work_export_shapes(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            (data_dir / "defects.json").write_text(
                json.dumps(
                    {
                        "issues": [
                            {
                                "key": "BUG-7",
                                "summary": "Checkout fails",
                                "priority": "High",
                                "state": "Active",
                                "created_at": "2026-05-20T09:15:00Z",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            (data_dir / "test_runs.json").write_text(
                json.dumps(
                    {
                        "runs": [
                            {
                                "run_id": 42,
                                "run_name": "Nightly smoke",
                                "Status": "Failed",
                                "date": "21/05/2026",
                                "passed": 17,
                                "failed": 2,
                                "total": 19,
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            (data_dir / "team.json").write_text(
                json.dumps(
                    {
                        "members": [
                            {
                                "employee_id": "qe-1",
                                "name": "Alex",
                                "skills": "API, UI, , CI",
                                "vacation": True,
                                "last_1_1": "2026-05-01",
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
                            {"key": "a1", "person": "qe-1", "app": "Billing", "pct": "75"},
                            {
                                "key": "a2",
                                "person": "qe-2",
                                "app": "Search",
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
                                "key": "s1",
                                "theme": "Automation",
                                "title": "Expand API coverage",
                                "priority": "P0",
                                "evidence": "OKR-1",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            adapter = FileExportAdapter(data_dir)

            defects = adapter.get_defects()
            self.assertEqual("BUG-7", defects[0].id)
            self.assertEqual("Checkout fails", defects[0].title)
            self.assertEqual("High", defects[0].severity)
            self.assertEqual("Active", defects[0].status)
            self.assertEqual(2026, defects[0].created.year)

            runs = adapter.get_test_runs()
            self.assertEqual("42", runs[0].id)
            self.assertEqual("Nightly smoke", runs[0].name)
            self.assertEqual("Failed", runs[0].status)
            self.assertEqual(19, runs[0].total)
            self.assertEqual(21, runs[0].executed_at.day)

            team = adapter.get_team_members()
            self.assertEqual(["API", "UI", "CI"], team[0].skills)
            self.assertTrue(team[0].on_vacation)
            self.assertEqual(1, team[0].last_one_on_one.day)

            allocations = adapter.get_allocations()
            self.assertEqual(75, allocations[0].focus_pct)
            self.assertIsNone(allocations[1].focus_pct)

            strategy = adapter.get_strategy_signals()
            self.assertEqual("Automation", strategy[0].pillar)
            self.assertEqual("Expand API coverage", strategy[0].summary)
            self.assertEqual("OKR-1", strategy[0].evidence_ref)

    def test_missing_files_return_empty_lists(self):
        with tempfile.TemporaryDirectory() as tmp:
            adapter = FileExportAdapter(Path(tmp))

            self.assertEqual([], adapter.get_defects())
            self.assertEqual([], adapter.get_test_runs())
            self.assertEqual([], adapter.get_team_members())
            self.assertEqual([], adapter.get_allocations())
            self.assertEqual([], adapter.get_strategy_signals())


if __name__ == "__main__":
    unittest.main()
