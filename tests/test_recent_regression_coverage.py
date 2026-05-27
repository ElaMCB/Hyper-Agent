import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.shadow.adapters.file_export import load_allocations_from_json, load_team_from_json
from src.shadow.snapshot import build_snapshot


class QeFileExportParsingTests(unittest.TestCase):
    def test_team_loader_coerces_human_json_export_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "team.json"
            path.write_text(
                json.dumps(
                    {
                        "members": [
                            {
                                "employee_id": "qe-1",
                                "name": "Asha",
                                "role": "Lead",
                                "skills": "api, regression, automation",
                                "on_vacation": "false",
                                "last_1_1": "2026-05-01",
                            },
                            {
                                "id": "qe-2",
                                "name": "Ben",
                                "skills": ["mobile", "accessibility"],
                                "vacation": "yes",
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )

            team = load_team_from_json(path)

        self.assertEqual(["api", "regression", "automation"], team[0].skills)
        self.assertFalse(team[0].on_vacation)
        self.assertEqual("2026-05-01", team[0].last_one_on_one.strftime("%Y-%m-%d"))
        self.assertEqual(["mobile", "accessibility"], team[1].skills)
        self.assertTrue(team[1].on_vacation)

    def test_allocation_loader_preserves_zero_percent_and_rejects_bad_percentages(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "allocations.json"
            path.write_text(
                json.dumps(
                    {
                        "assignments": [
                            {"id": "a-1", "person": "qe-1", "app": "Core", "focus_pct": 0},
                            {"id": "a-2", "person": "qe-2", "app": "Mobile", "allocation_pct": "35"},
                            {"id": "a-3", "person": "qe-3", "app": "Risk", "pct": ""},
                            {"id": "a-4", "person": "qe-4", "app": "Data", "pct": "unknown"},
                        ]
                    }
                ),
                encoding="utf-8",
            )

            allocations = load_allocations_from_json(path)

        self.assertEqual(0, allocations[0].focus_pct)
        self.assertEqual(35, allocations[1].focus_pct)
        self.assertIsNone(allocations[2].focus_pct)
        self.assertIsNone(allocations[3].focus_pct)


class SnapshotQeWiringTests(unittest.TestCase):
    def test_build_snapshot_loads_qe_files_and_keeps_gmail_failures_in_notes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_dir = root / "data"
            data_dir.mkdir()
            (data_dir / "team.json").write_text(
                json.dumps({"team": [{"id": "qe-1", "name": "Asha", "on_vacation": False}]}),
                encoding="utf-8",
            )
            (data_dir / "allocations.json").write_text(
                json.dumps({"allocations": [{"id": "alloc-1", "person_id": "qe-1", "focus_pct": 0}]}),
                encoding="utf-8",
            )
            (data_dir / "strategy.json").write_text(
                json.dumps(
                    {
                        "signals": [
                            {
                                "id": "s-1",
                                "pillar": "Release readiness",
                                "summary": "Protect payment regression scope",
                                "priority": "P1",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            config = {
                "data": {
                    "dir": "data",
                    "load_team": True,
                    "load_allocations": True,
                    "load_strategy": True,
                },
                "gmail": {"enabled": True},
            }

            with patch(
                "src.shadow.snapshot.fetch_gmail_messages",
                return_value=([], ["Gmail: listing messages failed (boom)."]),
            ):
                snapshot = build_snapshot(root, config)

        self.assertEqual(1, len(snapshot.team_members))
        self.assertEqual(1, len(snapshot.capacity_allocations))
        self.assertEqual(0, snapshot.capacity_allocations[0].focus_pct)
        self.assertEqual(1, len(snapshot.strategy_signals))
        self.assertIn("File: team (team.json)", snapshot.sources)
        self.assertIn("File: allocations (allocations.json)", snapshot.sources)
        self.assertIn("File: strategy (strategy.json)", snapshot.sources)
        self.assertNotIn("Gmail: connected (0 messages for this query)", snapshot.sources)
        self.assertEqual(["Gmail: listing messages failed (boom)."], snapshot.notes)


if __name__ == "__main__":
    unittest.main()
