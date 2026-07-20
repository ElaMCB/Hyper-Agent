import json
import tempfile
import unittest
from pathlib import Path

from src.shadow.adapters.file_export import (
    load_allocations_from_json,
    load_strategy_from_json,
    load_team_from_json,
)


class FileExportLoaderTests(unittest.TestCase):
    def test_team_loader_accepts_nested_members_aliases_and_csv_skills(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "team.json"
            path.write_text(
                json.dumps(
                    {
                        "members": [
                            {
                                "employee_id": 42,
                                "name": "Riley Chen",
                                "role": "QE Lead",
                                "skills": "API, CI, security",
                                "vacation": True,
                                "vacation_until": "10/05/2026",
                                "morale": "yellow",
                                "last_1_1": "2026-04-15",
                                "performance_note": "Owns release readiness",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            members = load_team_from_json(path)

        self.assertEqual(1, len(members))
        self.assertEqual("42", members[0].id)
        self.assertEqual(["API", "CI", "security"], members[0].skills)
        self.assertTrue(members[0].on_vacation)
        self.assertEqual("yellow", members[0].morale_flag)
        self.assertEqual("2026-05-10", members[0].vacation_until.strftime("%Y-%m-%d"))
        self.assertEqual("2026-04-15", members[0].last_one_on_one.strftime("%Y-%m-%d"))

    def test_allocation_loader_normalizes_pct_aliases_and_ignores_bad_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "allocations.json"
            path.write_text(
                json.dumps(
                    {
                        "assignments": [
                            {
                                "key": "a-1",
                                "person": "qe-1",
                                "name": "Riley Chen",
                                "app": "Payments",
                                "sprint": "2026-W19",
                                "pct": "75",
                                "note": "Critical path regression",
                            },
                            {
                                "id": "a-2",
                                "person_id": "qe-2",
                                "app_name": "Identity",
                                "allocation_pct": "not-a-number",
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )

            allocations = load_allocations_from_json(path)

        self.assertEqual(2, len(allocations))
        self.assertEqual("a-1", allocations[0].id)
        self.assertEqual("qe-1", allocations[0].person_id)
        self.assertEqual("Payments", allocations[0].app_name)
        self.assertEqual(75, allocations[0].focus_pct)
        self.assertEqual("Critical path regression", allocations[0].commitment_note)
        self.assertIsNone(allocations[1].focus_pct)

    def test_strategy_loader_accepts_signal_aliases(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "strategy.json"
            path.write_text(
                json.dumps(
                    {
                        "signals": [
                            {
                                "key": "st-1",
                                "theme": "Reliability",
                                "title": "Reduce flaky release gates",
                                "priority": "P0",
                                "evidence": "CI stability dashboard",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            signals = load_strategy_from_json(path)

        self.assertEqual(1, len(signals))
        self.assertEqual("st-1", signals[0].id)
        self.assertEqual("Reliability", signals[0].pillar)
        self.assertEqual("Reduce flaky release gates", signals[0].summary)
        self.assertEqual("CI stability dashboard", signals[0].evidence_ref)


if __name__ == "__main__":
    unittest.main()
