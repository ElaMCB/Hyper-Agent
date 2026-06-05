import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from src.shadow.adapters.file_export import load_allocations_from_json, load_team_from_json
from src.shadow.capabilities.people_capacity import render_people_capacity_md
from src.shadow.capabilities.resource_allocation import render_resource_allocation_md
from src.shadow.models import Snapshot


class QeFileExportParsingTests(unittest.TestCase):
    def test_team_loader_parses_string_vacation_flags_before_rendering(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "team.json"
            path.write_text(
                json.dumps(
                    {
                        "team": [
                            {
                                "id": "qe-1",
                                "name": "Maya",
                                "role": "QE Lead",
                                "skills": "API, Payments",
                                "on_vacation": "false",
                                "last_one_on_one": "2026-05-30",
                            },
                            {
                                "id": "qe-2",
                                "name": "Ravi",
                                "role": "Automation",
                                "skills": ["UI"],
                                "vacation": "yes",
                                "vacation_until": "2026-06-10",
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )

            team = load_team_from_json(path)

        self.assertFalse(team[0].on_vacation)
        self.assertTrue(team[1].on_vacation)
        self.assertEqual(team[0].skills, ["API", "Payments"])

        snapshot = Snapshot(
            as_of=datetime(2026, 6, 5, tzinfo=timezone.utc),
            team_members=team,
        )
        rendered = render_people_capacity_md(snapshot, {"people": {"one_on_one_stale_days": 21}})

        self.assertIn("- **On vacation (flag):** 1", rendered)
        self.assertIn("| Maya | QE Lead | API, Payments | No  |", rendered)
        self.assertIn("| Ravi | Automation | UI | Yes 2026-06-10 |", rendered)

    def test_allocation_loader_preserves_zero_and_ignores_invalid_percentages(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "allocations.json"
            path.write_text(
                json.dumps(
                    {
                        "allocations": [
                            {
                                "id": "a-1",
                                "person_id": "qe-1",
                                "person_name": "Maya",
                                "app_name": "Checkout",
                                "sprint_label": "Sprint 12",
                                "focus_pct": 0,
                            },
                            {
                                "id": "a-2",
                                "person_id": "qe-2",
                                "person_name": "Ravi",
                                "app_name": "Checkout",
                                "sprint_label": "Sprint 12",
                                "pct": "0",
                            },
                            {
                                "id": "a-3",
                                "person_id": "qe-3",
                                "person_name": "Noor",
                                "app_name": "Billing",
                                "sprint_label": "Sprint 12",
                                "allocation_pct": "",
                            },
                            {
                                "id": "a-4",
                                "person_id": "qe-4",
                                "person_name": "Iris",
                                "app_name": "Billing",
                                "sprint_label": "Sprint 12",
                                "focus_pct": "not available",
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )

            allocations = load_allocations_from_json(path)

        self.assertEqual([a.focus_pct for a in allocations], [0, 0, None, None])

        snapshot = Snapshot(
            as_of=datetime(2026, 6, 5, tzinfo=timezone.utc),
            capacity_allocations=allocations,
        )
        rendered = render_resource_allocation_md(snapshot, {})

        self.assertIn("- **Maya** \u2014 0% \u00b7 sprint `Sprint 12`", rendered)
        self.assertIn("- **Ravi** \u2014 0% \u00b7 sprint `Sprint 12`", rendered)
        self.assertIn("| Maya | Checkout | Sprint 12 | 0 |", rendered)
        self.assertIn("| Noor | Billing | Sprint 12 | \u2014 |", rendered)
        self.assertIn("| Iris | Billing | Sprint 12 | \u2014 |", rendered)


if __name__ == "__main__":
    unittest.main()
