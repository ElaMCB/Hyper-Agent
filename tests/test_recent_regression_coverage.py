import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from src.shadow.adapters.file_export import load_allocations_from_json, load_team_from_json
from src.shadow.capabilities.resource_allocation import render_resource_allocation_md
from src.shadow.models import Snapshot


class QeFileLoaderRegressionTests(unittest.TestCase):
    def _write_json(self, payload) -> Path:
        tmp = tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False)
        with tmp:
            json.dump(payload, tmp)
        self.addCleanup(lambda: Path(tmp.name).unlink(missing_ok=True))
        return Path(tmp.name)

    def test_allocation_loader_preserves_explicit_zero_focus(self):
        path = self._write_json(
            {
                "allocations": [
                    {
                        "id": "zero",
                        "person_id": "qa-1",
                        "person_name": "Ada",
                        "app_name": "Billing",
                        "sprint_label": "Sprint 42",
                        "focus_pct": 0,
                    },
                    {
                        "id": "fallback",
                        "person": "qa-2",
                        "name": "Grace",
                        "app": "Claims",
                        "sprint": "Sprint 42",
                        "allocation_pct": "25",
                    },
                ]
            }
        )

        rows = load_allocations_from_json(path)

        self.assertEqual(rows[0].focus_pct, 0)
        self.assertEqual(rows[1].focus_pct, 25)

    def test_zero_allocation_is_visible_in_markdown(self):
        path = self._write_json(
            [
                {
                    "id": "zero",
                    "person_id": "qa-1",
                    "person_name": "Ada",
                    "app_name": "Billing",
                    "sprint_label": "Sprint 42",
                    "focus_pct": 0,
                }
            ]
        )
        snapshot = Snapshot(
            as_of=datetime(2026, 5, 25, tzinfo=timezone.utc),
            capacity_allocations=load_allocations_from_json(path),
        )

        md = render_resource_allocation_md(snapshot, {})

        self.assertIn("- **Ada** — 0% · sprint `Sprint 42`", md)
        self.assertIn("| Ada | Billing | Sprint 42 | 0 |", md)

    def test_team_loader_parses_string_booleans_without_truthiness_traps(self):
        path = self._write_json(
            {
                "team": [
                    {
                        "id": "qa-1",
                        "name": "Ada",
                        "skills": "api, payments, automation",
                        "on_vacation": "false",
                    },
                    {
                        "id": "qa-2",
                        "name": "Grace",
                        "skills": ["risk", "exploratory"],
                        "vacation": "YES",
                    },
                    {
                        "id": "qa-3",
                        "name": "Lin",
                        "vacation": "0",
                    },
                ]
            }
        )

        team = load_team_from_json(path)

        self.assertFalse(team[0].on_vacation)
        self.assertEqual(team[0].skills, ["api", "payments", "automation"])
        self.assertTrue(team[1].on_vacation)
        self.assertFalse(team[2].on_vacation)


if __name__ == "__main__":
    unittest.main()
