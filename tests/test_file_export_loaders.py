import json
import tempfile
import unittest
from pathlib import Path

from src.shadow.adapters.file_export import (
    FileExportAdapter,
    load_allocations_from_json,
    load_strategy_from_json,
    load_team_from_json,
)


class FileExportLoaderTests(unittest.TestCase):
    def test_team_loader_supports_member_wrapper_aliases_and_skill_strings(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "team.json"
            path.write_text(
                json.dumps(
                    {
                        "members": [
                            {
                                "employee_id": "qa-1",
                                "name": "Asha",
                                "role": "QE Lead",
                                "skills": "API, automation, release",
                                "vacation": True,
                                "vacation_until": "2026-05-15",
                                "morale": "amber",
                                "last_1_1": "2026-04-20T09:30:00",
                                "performance_note": "Owns checkout | payments",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            team = load_team_from_json(path)

        self.assertEqual(len(team), 1)
        member = team[0]
        self.assertEqual(member.id, "qa-1")
        self.assertEqual(member.skills, ["API", "automation", "release"])
        self.assertTrue(member.on_vacation)
        self.assertEqual(member.vacation_until.strftime("%Y-%m-%d"), "2026-05-15")
        self.assertEqual(member.morale_flag, "amber")
        self.assertEqual(member.last_one_on_one.strftime("%Y-%m-%d %H:%M"), "2026-04-20 09:30")

    def test_allocation_loader_coerces_percent_aliases_and_keeps_bad_values_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "allocations.json"
            path.write_text(
                json.dumps(
                    {
                        "assignments": [
                            {
                                "key": "a-1",
                                "person": "qa-1",
                                "name": "Asha",
                                "app": "Checkout",
                                "sprint": "Sprint 12",
                                "pct": "60",
                                "note": "Primary lane",
                            },
                            {
                                "id": "a-2",
                                "person_id": "qa-2",
                                "app_name": "Payments",
                                "sprint_label": "Sprint 12",
                                "allocation_pct": "not-a-number",
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )

            allocations = load_allocations_from_json(path)

        self.assertEqual([a.focus_pct for a in allocations], [60, None])
        self.assertEqual(allocations[0].person_id, "qa-1")
        self.assertEqual(allocations[0].app_name, "Checkout")
        self.assertEqual(allocations[0].commitment_note, "Primary lane")

    def test_strategy_loader_supports_signal_wrapper_and_field_aliases(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "strategy.json"
            path.write_text(
                json.dumps(
                    {
                        "signals": [
                            {
                                "key": "s-1",
                                "theme": "Release confidence",
                                "title": "Protect checkout smoke coverage",
                                "horizon": "Now",
                                "priority": "P0",
                                "status": "At risk",
                                "evidence": "QA-123",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            signals = load_strategy_from_json(path)

        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0].id, "s-1")
        self.assertEqual(signals[0].pillar, "Release confidence")
        self.assertEqual(signals[0].summary, "Protect checkout smoke coverage")
        self.assertEqual(signals[0].evidence_ref, "QA-123")

    def test_file_export_adapter_returns_empty_lists_for_missing_qe_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            adapter = FileExportAdapter(Path(tmp))

            self.assertEqual(adapter.get_team_members(), [])
            self.assertEqual(adapter.get_allocations(), [])
            self.assertEqual(adapter.get_strategy_signals(), [])


if __name__ == "__main__":
    unittest.main()
