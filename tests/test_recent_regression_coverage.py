import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.shadow.adapters.file_export import load_allocations_from_json, load_team_from_json
from src.shadow.capabilities.resource_allocation import render_resource_allocation_md
from src.shadow.models import Snapshot
from src.shadow.snapshot import build_snapshot


class FileExportQeParsingTests(unittest.TestCase):
    def test_allocation_loader_preserves_zero_focus_percent(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "allocations.json"
            path.write_text(
                json.dumps(
                    {
                        "allocations": [
                            {
                                "id": "zero",
                                "person_id": "qe-0",
                                "person_name": "Noah",
                                "app_name": "Billing",
                                "sprint_label": "2026-W22",
                                "focus_pct": 0,
                                "commitment_note": "Watching only",
                            },
                            {
                                "id": "fallback",
                                "person_id": "qe-1",
                                "app_name": "Mobile",
                                "sprint_label": "2026-W22",
                                "pct": "25",
                            },
                            {
                                "id": "blank",
                                "person_id": "qe-2",
                                "app_name": "Portal",
                                "sprint_label": "2026-W22",
                                "allocation_pct": "",
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )

            rows = load_allocations_from_json(path)

        self.assertEqual(0, rows[0].focus_pct)
        self.assertEqual(25, rows[1].focus_pct)
        self.assertIsNone(rows[2].focus_pct)

        md = render_resource_allocation_md(
            Snapshot(
                as_of=datetime(2026, 5, 24, tzinfo=timezone.utc),
                capacity_allocations=rows,
            ),
            {},
        )
        self.assertIn("- **Noah** — 0% · sprint `2026-W22`", md)

    def test_team_loader_parses_boolean_strings_and_skill_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "team.json"
            path.write_text(
                json.dumps(
                    {
                        "members": [
                            {
                                "id": "qe-1",
                                "name": "Rae",
                                "skills": "API, UI, , Accessibility",
                                "on_vacation": "false",
                            },
                            {
                                "id": "qe-2",
                                "name": "Dee",
                                "vacation": "yes",
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )

            rows = load_team_from_json(path)

        self.assertEqual(["API", "UI", "Accessibility"], rows[0].skills)
        self.assertFalse(rows[0].on_vacation)
        self.assertTrue(rows[1].on_vacation)


class SnapshotProvenanceTests(unittest.TestCase):
    def test_snapshot_records_gmail_failures_as_notes_without_success_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = root / "data"
            data.mkdir()
            (data / "team.json").write_text(
                json.dumps([{"id": "qe-1", "name": "Rae"}]),
                encoding="utf-8",
            )
            (data / "allocations.json").write_text(
                json.dumps([{"id": "a-1", "person_id": "qe-1", "focus_pct": 50}]),
                encoding="utf-8",
            )
            config = {
                "data": {
                    "dir": "data",
                    "load_defects": False,
                    "load_test_runs": False,
                    "load_team": True,
                    "load_allocations": True,
                    "load_strategy": False,
                },
                "gmail": {"enabled": True},
            }

            with patch(
                "src.shadow.snapshot.fetch_gmail_messages",
                return_value=([], ["Gmail: listing messages failed (boom)."]),
            ):
                snapshot = build_snapshot(root, config)

        self.assertIn("Gmail: listing messages failed (boom).", snapshot.notes)
        self.assertIn("File: team (team.json)", snapshot.sources)
        self.assertIn("File: allocations (allocations.json)", snapshot.sources)
        self.assertNotIn("Gmail: connected (0 messages for this query)", snapshot.sources)


if __name__ == "__main__":
    unittest.main()
