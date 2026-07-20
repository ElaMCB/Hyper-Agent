import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from src.shadow.adapters.file_export import load_allocations_from_json, load_team_from_json
from src.shadow.adapters.gmail import _header_map, _parse_internal_date
from src.shadow.snapshot import build_snapshot


class GmailParsingTests(unittest.TestCase):
    def test_header_map_lowercases_names_and_preserves_values(self):
        payload = {
            "headers": [
                {"name": "Subject", "value": "Release note"},
                {"name": "FROM", "value": "QA Lead <qa@example.com>"},
                {"name": "", "value": "ignored"},
                {"value": "also ignored"},
            ]
        }

        headers = _header_map(payload)

        self.assertEqual(headers["subject"], "Release note")
        self.assertEqual(headers["from"], "QA Lead <qa@example.com>")
        self.assertNotIn("", headers)

    def test_parse_internal_date_handles_valid_and_invalid_values(self):
        self.assertEqual(
            _parse_internal_date("1000"),
            datetime(1970, 1, 1, 0, 0, 1, tzinfo=timezone.utc),
        )

        for value in (None, "", "not-a-date", "999999999999999999999999999999"):
            with self.subTest(value=value):
                self.assertIsNone(_parse_internal_date(value))


class FileExportParsingTests(unittest.TestCase):
    def test_team_loader_coerces_string_booleans_and_skills(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "team.json"
            path.write_text(
                json.dumps(
                    {
                        "team": [
                            {
                                "id": "t1",
                                "name": "Alex",
                                "skills": "api, e2e, automation",
                                "on_vacation": "false",
                            },
                            {
                                "id": "t2",
                                "name": "Blair",
                                "skills": ["mobile", "accessibility"],
                                "vacation": "yes",
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )

            team = load_team_from_json(path)

        self.assertEqual(team[0].skills, ["api", "e2e", "automation"])
        self.assertFalse(team[0].on_vacation)
        self.assertEqual(team[1].skills, ["mobile", "accessibility"])
        self.assertTrue(team[1].on_vacation)

    def test_allocation_loader_preserves_zero_and_falls_back_for_blank_aliases(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "allocations.json"
            path.write_text(
                json.dumps(
                    {
                        "allocations": [
                            {"id": "zero", "person_id": "p1", "focus_pct": 0},
                            {"id": "string", "person_id": "p2", "pct": "75"},
                            {
                                "id": "fallback",
                                "person_id": "p3",
                                "focus_pct": "",
                                "allocation_pct": "25",
                            },
                            {"id": "invalid", "person_id": "p4", "focus_pct": "NaN"},
                        ]
                    }
                ),
                encoding="utf-8",
            )

            allocations = load_allocations_from_json(path)

        self.assertEqual(
            [a.focus_pct for a in allocations],
            [0, 75, 25, None],
        )


class SnapshotGmailProvenanceTests(unittest.TestCase):
    def _base_config(self):
        return {
            "data": {
                "load_defects": False,
                "load_test_runs": False,
                "load_team": False,
                "load_allocations": False,
                "load_strategy": False,
            },
            "gmail": {"enabled": True},
        }

    @patch("src.shadow.snapshot.fetch_gmail_messages")
    def test_gmail_errors_are_notes_not_empty_success_sources(self, fetch_gmail):
        fetch_gmail.return_value = ([], ["Gmail: listing messages failed (boom)."])
        with tempfile.TemporaryDirectory() as tmp:
            snapshot = build_snapshot(Path(tmp), self._base_config())

        self.assertIn("Gmail: listing messages failed (boom).", snapshot.notes)
        self.assertNotIn("Gmail: connected (0 messages for this query)", snapshot.sources)

    @patch("src.shadow.snapshot.fetch_gmail_messages")
    def test_empty_gmail_success_records_empty_query_source(self, fetch_gmail):
        fetch_gmail.return_value = ([], [])
        with tempfile.TemporaryDirectory() as tmp:
            snapshot = build_snapshot(Path(tmp), self._base_config())

        self.assertIn("Gmail: connected (0 messages for this query)", snapshot.sources)
        self.assertEqual(snapshot.notes, [])


if __name__ == "__main__":
    unittest.main()
