import json
import tempfile
import unittest
from pathlib import Path

from src.shadow.adapters.file_export import load_allocations_from_json, load_team_from_json


class FileExportParsingTests(unittest.TestCase):
    def write_json(self, payload: object) -> Path:
        tmp = tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False)
        with tmp:
            json.dump(payload, tmp)
        self.addCleanup(lambda: Path(tmp.name).unlink(missing_ok=True))
        return Path(tmp.name)

    def test_team_loader_coerces_string_vacation_flags(self) -> None:
        path = self.write_json(
            {
                "team": [
                    {
                        "id": "qe-001",
                        "name": "Alex",
                        "skills": "API, CI",
                        "on_vacation": "false",
                    },
                    {
                        "id": "qe-002",
                        "name": "Jordan",
                        "skills": ["UI"],
                        "vacation": "YES",
                    },
                ]
            }
        )

        team = load_team_from_json(path)

        self.assertEqual(["API", "CI"], team[0].skills)
        self.assertFalse(team[0].on_vacation)
        self.assertTrue(team[1].on_vacation)

    def test_allocation_loader_preserves_zero_percentages_and_fallbacks(self) -> None:
        path = self.write_json(
            {
                "allocations": [
                    {
                        "id": "al-1",
                        "person_id": "qe-001",
                        "person_name": "Alex",
                        "focus_pct": 0,
                    },
                    {
                        "id": "al-2",
                        "person_id": "qe-002",
                        "person_name": "Jordan",
                        "focus_pct": "",
                        "pct": "0",
                    },
                    {
                        "id": "al-3",
                        "person_id": "qe-003",
                        "person_name": "Sam",
                        "focus_pct": "not exported",
                        "allocation_pct": 40,
                    },
                ]
            }
        )

        allocations = load_allocations_from_json(path)

        self.assertEqual(0, allocations[0].focus_pct)
        self.assertEqual(0, allocations[1].focus_pct)
        self.assertIsNone(allocations[2].focus_pct)


if __name__ == "__main__":
    unittest.main()
