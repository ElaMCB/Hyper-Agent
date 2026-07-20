import json
import tempfile
import unittest
from pathlib import Path

from src.shadow.adapters.file_export import (
    load_allocations_from_json,
    load_team_from_json,
)


class QEFileExportTests(unittest.TestCase):
    def test_team_loader_coerces_boolean_strings_and_skills(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "team.json"
            path.write_text(
                json.dumps(
                    {
                        "team": [
                            {
                                "id": "qa-1",
                                "name": "Dana",
                                "role": "SDET",
                                "skills": "api, ui, regression",
                                "on_vacation": "false",
                            },
                            {
                                "id": "qa-2",
                                "name": "Lee",
                                "vacation": "yes",
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )

            team = load_team_from_json(path)

        self.assertEqual(["api", "ui", "regression"], team[0].skills)
        self.assertFalse(team[0].on_vacation)
        self.assertTrue(team[1].on_vacation)

    def test_allocation_loader_preserves_zero_focus_and_falls_back(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "allocations.json"
            path.write_text(
                json.dumps(
                    {
                        "allocations": [
                            {
                                "id": "alloc-0",
                                "person_id": "qa-1",
                                "app_name": "Checkout",
                                "focus_pct": 0,
                            },
                            {
                                "id": "alloc-1",
                                "person_id": "qa-2",
                                "app_name": "Payments",
                                "focus_pct": "",
                                "pct": "25",
                            },
                            {
                                "id": "alloc-2",
                                "person_id": "qa-3",
                                "app_name": "Search",
                                "allocation_pct": "not-a-number",
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )

            allocations = load_allocations_from_json(path)

        self.assertEqual(0, allocations[0].focus_pct)
        self.assertEqual(25, allocations[1].focus_pct)
        self.assertIsNone(allocations[2].focus_pct)


if __name__ == "__main__":
    unittest.main()
