import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from src.shadow.adapters.file_export import load_allocations_from_json, load_team_from_json
from src.shadow.adapters.gmail import _parse_internal_date
from src.shadow.capabilities.resource_allocation import render_resource_allocation_md
from src.shadow.models import Snapshot
from src.shadow.snapshot import build_snapshot


class FileExportParsingTests(unittest.TestCase):
    def test_team_loader_coerces_string_booleans_and_skills(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "team.json"
            path.write_text(
                json.dumps(
                    {
                        "members": [
                            {
                                "id": "qa-1",
                                "name": "Rae",
                                "role": "SDET",
                                "skills": "api, mobile, accessibility",
                                "on_vacation": "false",
                                "last_1_1": "2026-06-01",
                            },
                            {
                                "id": "qa-2",
                                "name": "Mo",
                                "role": "Lead",
                                "skills": ["strategy", "coaching"],
                                "vacation": "YES",
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )

            members = load_team_from_json(path)

        self.assertEqual(["api", "mobile", "accessibility"], members[0].skills)
        self.assertFalse(members[0].on_vacation)
        self.assertEqual(datetime(2026, 6, 1), members[0].last_one_on_one)
        self.assertTrue(members[1].on_vacation)

    def test_allocation_loader_preserves_zero_and_uses_nonblank_aliases(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "allocations.json"
            path.write_text(
                json.dumps(
                    {
                        "assignments": [
                            {
                                "id": "a1",
                                "person_id": "qa-1",
                                "person_name": "Rae",
                                "app": "Checkout",
                                "sprint": "Sprint 12",
                                "focus_pct": 0,
                                "pct": 75,
                            },
                            {
                                "id": "a2",
                                "person_id": "qa-2",
                                "person_name": "Mo",
                                "app": "Search",
                                "sprint": "Sprint 12",
                                "focus_pct": " ",
                                "pct": "25",
                            },
                            {
                                "id": "a3",
                                "person_id": "qa-3",
                                "person_name": "Lin",
                                "app": "Billing",
                                "sprint": "Sprint 12",
                                "allocation_pct": "not-a-number",
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )

            allocations = load_allocations_from_json(path)

        self.assertEqual(0, allocations[0].focus_pct)
        self.assertEqual(25, allocations[1].focus_pct)
        self.assertIsNone(allocations[2].focus_pct)

        markdown = render_resource_allocation_md(
            Snapshot(
                as_of=datetime(2026, 7, 1, tzinfo=timezone.utc),
                capacity_allocations=allocations,
            ),
            {},
        )
        self.assertIn("- **Rae** — 0% · sprint `Sprint 12`", markdown)
        self.assertIn("| Rae | Checkout | Sprint 12 | 0 |", markdown)


class GmailParsingTests(unittest.TestCase):
    def test_parse_internal_date_rejects_invalid_and_overflow_values(self):
        self.assertEqual(
            datetime(1970, 1, 1, tzinfo=timezone.utc),
            _parse_internal_date("0"),
        )
        self.assertIsNone(_parse_internal_date("not-ms"))
        self.assertIsNone(_parse_internal_date("999999999999999999999999999999999999"))


class SnapshotProvenanceTests(unittest.TestCase):
    def test_gmail_zero_messages_records_successful_empty_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = {
                "data": {"load_defects": False, "load_test_runs": False},
                "gmail": {"enabled": True},
            }
            with patch("src.shadow.snapshot.fetch_gmail_messages", return_value=([], [])):
                snapshot = build_snapshot(root, config)

        self.assertIn("Gmail: connected (0 messages for this query)", snapshot.sources)
        self.assertEqual([], snapshot.notes)

    def test_gmail_failure_stays_in_notes_without_successful_empty_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = {
                "data": {"load_defects": False, "load_test_runs": False},
                "gmail": {"enabled": True},
            }
            with patch(
                "src.shadow.snapshot.fetch_gmail_messages",
                return_value=([], ["Gmail: listing messages failed (boom)."]),
            ):
                snapshot = build_snapshot(root, config)

        self.assertNotIn("Gmail: connected (0 messages for this query)", snapshot.sources)
        self.assertIn("Gmail: listing messages failed (boom).", snapshot.notes)


if __name__ == "__main__":
    unittest.main()
