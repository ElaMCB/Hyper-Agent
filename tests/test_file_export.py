import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from src.shadow.adapters.file_export import (
    FileExportAdapter,
    load_allocations_from_json,
    load_strategy_from_json,
    load_team_from_json,
)


class FileExportAdapterTests(unittest.TestCase):
    def test_load_team_supports_wrapped_members_aliases_and_skill_strings(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "team.json"
            path.write_text(
                json.dumps(
                    {
                        "members": [
                            {
                                "employee_id": "e-1",
                                "name": "Alex",
                                "role": "Lead QE",
                                "skills": "api, automation, payments",
                                "vacation": True,
                                "vacation_until": "2026-05-10",
                                "morale": "amber",
                                "last_1_1": "2026-04-01",
                                "performance_note": "Owns regression triage",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            members = load_team_from_json(path)

        self.assertEqual(len(members), 1)
        member = members[0]
        self.assertEqual(member.id, "e-1")
        self.assertEqual(member.skills, ["api", "automation", "payments"])
        self.assertTrue(member.on_vacation)
        self.assertEqual(member.morale_flag, "amber")
        self.assertEqual(member.last_one_on_one.year, 2026)

    def test_load_allocations_normalizes_focus_percent_and_keeps_bad_values_none(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "allocations.json"
            path.write_text(
                json.dumps(
                    {
                        "assignments": [
                            {
                                "key": "a-1",
                                "person": "e-1",
                                "name": "Alex",
                                "app": "Billing",
                                "sprint": "Sprint 7",
                                "allocation_pct": "75",
                                "note": "release support",
                            },
                            {
                                "id": "a-2",
                                "person_id": "e-2",
                                "app_name": "Claims",
                                "focus_pct": "not-a-number",
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )

            allocations = load_allocations_from_json(path)

        self.assertEqual([a.id for a in allocations], ["a-1", "a-2"])
        self.assertEqual(allocations[0].focus_pct, 75)
        self.assertEqual(allocations[0].commitment_note, "release support")
        self.assertIsNone(allocations[1].focus_pct)

    def test_load_strategy_supports_wrapped_pillars_and_title_alias(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "strategy.json"
            path.write_text(
                json.dumps(
                    {
                        "pillars": [
                            {
                                "key": "s-1",
                                "theme": "Payments resilience",
                                "title": "Cut rollback risk",
                                "priority": "P0",
                                "evidence": "release-plan.md",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            signals = load_strategy_from_json(path)

        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0].id, "s-1")
        self.assertEqual(signals[0].pillar, "Payments resilience")
        self.assertEqual(signals[0].summary, "Cut rollback risk")
        self.assertEqual(signals[0].evidence_ref, "release-plan.md")

    def test_adapter_returns_empty_lists_for_missing_optional_files(self):
        with TemporaryDirectory() as tmp:
            adapter = FileExportAdapter(Path(tmp))

            self.assertEqual(adapter.get_team_members(), [])
            self.assertEqual(adapter.get_allocations(), [])
            self.assertEqual(adapter.get_strategy_signals(), [])


if __name__ == "__main__":
    unittest.main()
