import json
import unittest
from tempfile import TemporaryDirectory
from pathlib import Path

from src.shadow.adapters.file_export import (
    FileExportAdapter,
    load_allocations_from_json,
    load_strategy_from_json,
    load_team_from_json,
)


class FileExportTests(unittest.TestCase):
    def test_team_loader_accepts_wrappers_aliases_and_skill_strings(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "team.json"
            path.write_text(
                json.dumps(
                    {
                        "team": [
                            {
                                "employee_id": "qe-1",
                                "name": "Alex",
                                "role": "QE",
                                "skills": "API, CI, accessibility",
                                "vacation": True,
                                "vacation_until": "2026-05-21",
                                "morale": "Amber",
                                "last_1_1": "10/04/2026",
                                "performance_note": "Owns checkout | mobile",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            members = load_team_from_json(path)

        self.assertEqual(len(members), 1)
        self.assertEqual(members[0].id, "qe-1")
        self.assertEqual(members[0].skills, ["API", "CI", "accessibility"])
        self.assertTrue(members[0].on_vacation)
        self.assertEqual(members[0].vacation_until.strftime("%Y-%m-%d"), "2026-05-21")
        self.assertEqual(members[0].morale_flag, "Amber")
        self.assertEqual(members[0].last_one_on_one.strftime("%Y-%m-%d"), "2026-04-10")

    def test_allocation_loader_coerces_numeric_percent_and_keeps_bad_values_empty(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "allocations.json"
            path.write_text(
                json.dumps(
                    {
                        "assignments": [
                            {
                                "key": "a1",
                                "person": "qe-1",
                                "name": "Alex",
                                "app": "Checkout",
                                "sprint": "2026-W20",
                                "pct": "50",
                                "note": "Regression",
                            },
                            {"id": "a2", "person_id": "qe-2", "pct": "n/a"},
                        ]
                    }
                ),
                encoding="utf-8",
            )

            allocations = load_allocations_from_json(path)

        self.assertEqual([a.focus_pct for a in allocations], [50, None])
        self.assertEqual(allocations[0].person_id, "qe-1")
        self.assertEqual(allocations[0].app_name, "Checkout")
        self.assertEqual(allocations[0].commitment_note, "Regression")

    def test_strategy_loader_accepts_signals_wrapper(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "strategy.json"
            path.write_text(
                json.dumps(
                    {
                        "signals": [
                            {
                                "key": "s1",
                                "theme": "Automation",
                                "title": "Raise API coverage",
                                "horizon": "FY26",
                                "priority": "P0",
                                "status": "Active",
                                "evidence": "OKR",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            signals = load_strategy_from_json(path)

        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0].id, "s1")
        self.assertEqual(signals[0].pillar, "Automation")
        self.assertEqual(signals[0].summary, "Raise API coverage")
        self.assertEqual(signals[0].evidence_ref, "OKR")

    def test_file_export_adapter_missing_optional_files_returns_empty_lists(self):
        with TemporaryDirectory() as tmp:
            adapter = FileExportAdapter(Path(tmp))

            self.assertEqual(adapter.get_team_members(), [])
            self.assertEqual(adapter.get_allocations(), [])
            self.assertEqual(adapter.get_strategy_signals(), [])


if __name__ == "__main__":
    unittest.main()
