import json
import tempfile
import unittest
from pathlib import Path

from src.shadow.adapters.file_export import load_allocations_from_json, load_team_from_json


class FileExportLoaderTests(unittest.TestCase):
    def test_allocation_loader_preserves_zero_focus_percentage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "allocations.json"
            path.write_text(
                json.dumps(
                    {
                        "allocations": [
                            {
                                "id": "a-0",
                                "person_id": "qe-1",
                                "person_name": "Priya",
                                "app_name": "Payments",
                                "sprint_label": "Sprint 14",
                                "focus_pct": 0,
                                "commitment_note": "Observer only",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            allocations = load_allocations_from_json(path)

        self.assertEqual(1, len(allocations))
        self.assertEqual(0, allocations[0].focus_pct)
        self.assertEqual("Payments", allocations[0].app_name)

    def test_allocation_loader_uses_alias_when_primary_percentage_is_blank(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "allocations.json"
            path.write_text(
                json.dumps(
                    [
                        {
                            "id": "a-1",
                            "person": "qe-2",
                            "name": "Marco",
                            "app": "Checkout",
                            "sprint": "Sprint 15",
                            "focus_pct": "",
                            "allocation_pct": "35",
                        }
                    ]
                ),
                encoding="utf-8",
            )

            allocations = load_allocations_from_json(path)

        self.assertEqual(35, allocations[0].focus_pct)
        self.assertEqual("qe-2", allocations[0].person_id)
        self.assertEqual("Marco", allocations[0].person_name)

    def test_team_loader_parses_string_false_vacation_flags(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "team.json"
            path.write_text(
                json.dumps(
                    {
                        "members": [
                            {
                                "id": "qe-3",
                                "name": "Avery",
                                "role": "QE Lead",
                                "skills": "api, automation",
                                "on_vacation": "false",
                                "morale": "green",
                            },
                            {
                                "id": "qe-4",
                                "name": "Sam",
                                "vacation": "yes",
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )

            members = load_team_from_json(path)

        self.assertFalse(members[0].on_vacation)
        self.assertEqual(["api", "automation"], members[0].skills)
        self.assertTrue(members[1].on_vacation)


if __name__ == "__main__":
    unittest.main()
