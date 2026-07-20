import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.shadow.adapters.file_export import load_allocations_from_json, load_team_from_json
from src.shadow.models import MailMessage
from src.shadow.snapshot import build_snapshot


class FileExportParsingTests(unittest.TestCase):
    def test_team_loader_coerces_string_booleans_and_skills(self) -> None:
        rows = {
            "members": [
                {
                    "id": "qe-1",
                    "name": "Alex",
                    "skills": "API, CI, Accessibility",
                    "on_vacation": "false",
                },
                {
                    "id": "qe-2",
                    "name": "Jordan",
                    "skills": ["UI", "Security"],
                    "vacation": "yes",
                },
            ]
        }

        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "team.json"
            path.write_text(json.dumps(rows), encoding="utf-8")

            team = load_team_from_json(path)

        self.assertEqual(["API", "CI", "Accessibility"], team[0].skills)
        self.assertFalse(team[0].on_vacation)
        self.assertEqual(["UI", "Security"], team[1].skills)
        self.assertTrue(team[1].on_vacation)

    def test_allocation_loader_preserves_zero_and_falls_back_to_aliases(self) -> None:
        rows = {
            "allocations": [
                {"id": "explicit-zero", "person_id": "qe-1", "focus_pct": 0, "pct": 80},
                {"id": "string-zero", "person_id": "qe-2", "focus_pct": "0"},
                {"id": "alias", "person_id": "qe-3", "focus_pct": "", "allocation_pct": "35"},
                {"id": "invalid", "person_id": "qe-4", "focus_pct": "tbd"},
            ]
        }

        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "allocations.json"
            path.write_text(json.dumps(rows), encoding="utf-8")

            allocations = load_allocations_from_json(path)

        self.assertEqual(0, allocations[0].focus_pct)
        self.assertEqual(0, allocations[1].focus_pct)
        self.assertEqual(35, allocations[2].focus_pct)
        self.assertIsNone(allocations[3].focus_pct)


class SnapshotGmailProvenanceTests(unittest.TestCase):
    def test_gmail_failure_records_note_without_success_source(self) -> None:
        config = {
            "data": {
                "load_defects": False,
                "load_test_runs": False,
                "load_team": False,
                "load_allocations": False,
                "load_strategy": False,
            },
            "gmail": {"enabled": True},
        }

        with patch(
            "src.shadow.snapshot.fetch_gmail_messages",
            return_value=([], ["Gmail: listing messages failed (boom)."]),
        ):
            snapshot = build_snapshot(Path("."), config)

        self.assertEqual(["Gmail: listing messages failed (boom)."], snapshot.notes)
        self.assertNotIn("Gmail: connected (0 messages for this query)", snapshot.sources)
        self.assertEqual(
            ["(No sources — enable Gmail/ADO, load team/allocations/strategy in config, or add data/ files.)"],
            snapshot.sources,
        )

    def test_gmail_success_source_reflects_message_count(self) -> None:
        config = {
            "data": {
                "load_defects": False,
                "load_test_runs": False,
                "load_team": False,
                "load_allocations": False,
                "load_strategy": False,
            },
            "gmail": {"enabled": True},
        }
        message = MailMessage(
            id="m-1",
            subject="Launch readiness",
            from_addr="lead@example.test",
            snippet="Please review",
            is_unread=True,
        )

        with patch("src.shadow.snapshot.fetch_gmail_messages", return_value=([message], [])):
            snapshot = build_snapshot(Path("."), config)

        self.assertEqual(["Gmail: 1 message(s)"], snapshot.sources)
        self.assertEqual([message], snapshot.mail_messages)
        self.assertEqual([], snapshot.notes)


if __name__ == "__main__":
    unittest.main()
