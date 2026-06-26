import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from src.shadow.adapters.file_export import load_allocations_from_json, load_team_from_json
from src.shadow.capabilities.resource_allocation import render_resource_allocation_md
from src.shadow.models import Snapshot


class FileExportParsingTests(unittest.TestCase):
    def test_team_export_coerces_string_vacation_flags(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "team.json"
            path.write_text(
                json.dumps(
                    {
                        "members": [
                            {
                                "id": "qe-1",
                                "name": "Avery",
                                "skills": "api, regression",
                                "on_vacation": "false",
                            },
                            {
                                "id": "qe-2",
                                "name": "Blake",
                                "vacation": "yes",
                            },
                            {
                                "id": "qe-3",
                                "name": "Casey",
                                "on_vacation": "0",
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )

            team = load_team_from_json(path)

        self.assertEqual(["api", "regression"], team[0].skills)
        self.assertFalse(team[0].on_vacation)
        self.assertTrue(team[1].on_vacation)
        self.assertFalse(team[2].on_vacation)

    def test_allocation_export_preserves_zero_and_alias_fallbacks(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "allocations.json"
            path.write_text(
                json.dumps(
                    {
                        "assignments": [
                            {
                                "id": "alloc-1",
                                "person_id": "qe-1",
                                "person_name": "Avery",
                                "app": "Payments",
                                "sprint": "Sprint 42",
                                "focus_pct": 0,
                            },
                            {
                                "id": "alloc-2",
                                "person_id": "qe-2",
                                "person_name": "Blake",
                                "app": "Search",
                                "pct": "0",
                            },
                            {
                                "id": "alloc-3",
                                "person_id": "qe-3",
                                "person_name": "Casey",
                                "app": "Mobile",
                                "focus_pct": "",
                                "allocation_pct": "25",
                            },
                            {
                                "id": "alloc-4",
                                "person_id": "qe-4",
                                "person_name": "Drew",
                                "app": "Portal",
                                "allocation_pct": "not-a-number",
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )

            allocations = load_allocations_from_json(path)

        self.assertEqual([0, 0, 25, None], [a.focus_pct for a in allocations])

        snapshot = Snapshot(
            as_of=datetime(2026, 6, 26, tzinfo=timezone.utc),
            capacity_allocations=allocations,
        )
        rendered = render_resource_allocation_md(snapshot, {})

        self.assertIn("- **Avery** — 0% · sprint `Sprint 42`", rendered)
        self.assertIn("- **Blake** — 0% · sprint `—`", rendered)
        self.assertIn("| Avery | Payments | Sprint 42 | 0 |", rendered)
        self.assertIn("| Drew | Portal |  | — |", rendered)


if __name__ == "__main__":
    unittest.main()
