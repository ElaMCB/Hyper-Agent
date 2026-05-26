import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from src.shadow.adapters.file_export import load_allocations_from_json, load_team_from_json
from src.shadow.capabilities.resource_allocation import render_resource_allocation_md
from src.shadow.models import CapacityAllocation, Snapshot


class FileBackedQeRegressionTests(unittest.TestCase):
    def _write_json(self, payload) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "data.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_team_loader_coerces_string_booleans_and_csv_skills(self):
        path = self._write_json(
            {
                "members": [
                    {
                        "id": "qe-1",
                        "name": "Alex",
                        "skills": "API, CI, , Java",
                        "on_vacation": "false",
                    },
                    {
                        "id": "qe-2",
                        "name": "Jordan",
                        "skills": ["UI", "Accessibility"],
                        "vacation": "yes",
                    },
                ]
            }
        )

        team = load_team_from_json(path)

        self.assertEqual(["API", "CI", "Java"], team[0].skills)
        self.assertFalse(team[0].on_vacation)
        self.assertTrue(team[1].on_vacation)

    def test_allocation_loader_preserves_zero_and_uses_nonempty_fallbacks(self):
        path = self._write_json(
            {
                "allocations": [
                    {
                        "id": "zero",
                        "person_id": "qe-1",
                        "focus_pct": 0,
                        "allocation_pct": 80,
                    },
                    {
                        "id": "fallback",
                        "person_id": "qe-2",
                        "pct": "",
                        "allocation_pct": "45",
                    },
                ]
            }
        )

        allocations = load_allocations_from_json(path)

        self.assertEqual(0, allocations[0].focus_pct)
        self.assertEqual(45, allocations[1].focus_pct)

    def test_resource_allocation_markdown_renders_zero_percent(self):
        snapshot = Snapshot(
            as_of=datetime(2026, 5, 26, tzinfo=timezone.utc),
            capacity_allocations=[
                CapacityAllocation(
                    id="zero",
                    person_id="qe-1",
                    person_name="Alex",
                    app_name="Billing API",
                    sprint_label="2026-W22",
                    focus_pct=0,
                    commitment_note="Bench support",
                )
            ],
        )

        markdown = render_resource_allocation_md(snapshot, {})

        self.assertIn("- **Alex** — 0% · sprint `2026-W22`", markdown)
        self.assertIn("| Alex | Billing API | 2026-W22 | 0 | Bench support |", markdown)


if __name__ == "__main__":
    unittest.main()
