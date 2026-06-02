import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.shadow.adapters.file_export import load_allocations_from_json, load_team_from_json
from src.shadow.capabilities.people_capacity import (
    people_capacity_summary_bullets,
    render_people_capacity_md,
)
from src.shadow.models import Snapshot, TeamMember


class RecentRegressionCoverageTests(unittest.TestCase):
    def test_team_loader_coerces_string_booleans_and_skill_exports(self):
        with tempfile.TemporaryDirectory() as tmp:
            team_path = Path(tmp) / "team.json"
            team_path.write_text(
                """
                {
                  "members": [
                    {
                      "id": "qe-1",
                      "name": "Asha",
                      "role": "QE Lead",
                      "skills": "payments, risk, automation",
                      "on_vacation": "false"
                    },
                    {
                      "employee_id": "qe-2",
                      "name": "Ben",
                      "skills": ["mobile", "accessibility"],
                      "vacation": "yes"
                    }
                  ]
                }
                """,
                encoding="utf-8",
            )

            team = load_team_from_json(team_path)

        self.assertEqual(["payments", "risk", "automation"], team[0].skills)
        self.assertFalse(team[0].on_vacation)
        self.assertEqual(["mobile", "accessibility"], team[1].skills)
        self.assertTrue(team[1].on_vacation)

    def test_allocation_loader_preserves_explicit_zero_focus_percentage(self):
        with tempfile.TemporaryDirectory() as tmp:
            allocations_path = Path(tmp) / "allocations.json"
            allocations_path.write_text(
                """
                {
                  "allocations": [
                    {
                      "id": "alloc-1",
                      "person_id": "qe-1",
                      "app_name": "Ledger",
                      "sprint_label": "2026.06",
                      "focus_pct": 0
                    },
                    {
                      "id": "alloc-2",
                      "person_id": "qe-2",
                      "allocation_pct": "35"
                    }
                  ]
                }
                """,
                encoding="utf-8",
            )

            allocations = load_allocations_from_json(allocations_path)

        self.assertEqual(0, allocations[0].focus_pct)
        self.assertEqual(35, allocations[1].focus_pct)

    def test_people_capacity_reports_morale_watch_and_stale_one_on_ones(self):
        snapshot = Snapshot(
            as_of=datetime(2026, 6, 2, tzinfo=timezone.utc),
            team_members=[
                TeamMember(
                    id="qe-1",
                    name="Asha",
                    role="QE Lead",
                    skills=["payments", "risk", "automation", "api", "mobile", "perf", "security"],
                    morale_flag="green",
                    last_one_on_one=datetime(2026, 5, 30),
                    performance_note="On track | mentoring new lead",
                ),
                TeamMember(
                    id="qe-2",
                    name="Ben",
                    role="SDET",
                    skills=["accessibility"],
                    morale_flag="Amber",
                    last_one_on_one=datetime(2026, 5, 1, tzinfo=timezone.utc),
                ),
                TeamMember(
                    id="qe-3",
                    name="Chen",
                    role="QE",
                    on_vacation=True,
                    morale_flag="red",
                    last_one_on_one=None,
                ),
            ],
        )
        config = {"people": {"one_on_one_stale_days": 21}}

        md = render_people_capacity_md(snapshot, config)
        bullets = people_capacity_summary_bullets(snapshot, config)

        self.assertIn("- **Headcount in file:** 3", md)
        self.assertIn("- **On vacation (flag):** 1", md)
        self.assertIn("- **Morale watch (amber/red):** Ben, Chen", md)
        self.assertIn("- **1:1 stale (>21d or missing):** Ben, Chen", md)
        self.assertIn("payments, risk, automation, api, mobile, perf", md)
        self.assertIn("On track \\| mentoring new lead", md)
        self.assertEqual(
            [
                "QE team (file): 3 people, 1 flagged on vacation.",
                "1:1 hygiene: 2 member(s) past 21d or missing last 1:1 date.",
            ],
            bullets,
        )


if __name__ == "__main__":
    unittest.main()
