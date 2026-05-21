import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.shadow.models import MailMessage
from src.shadow.snapshot import build_snapshot


def _isolated_config(gmail_enabled: bool = True) -> dict:
    return {
        "data": {
            "dir": "data",
            "load_defects": False,
            "load_test_runs": False,
            "load_team": False,
            "load_allocations": False,
            "load_strategy": False,
        },
        "gmail": {"enabled": gmail_enabled},
    }


class SnapshotGmailProvenanceTests(unittest.TestCase):
    def test_gmail_failure_adds_note_without_success_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch(
                "src.shadow.snapshot.fetch_gmail_messages",
                return_value=([], ["Gmail: listing messages failed (boom)."]),
            ):
                snapshot = build_snapshot(root, _isolated_config())

        self.assertEqual(["Gmail: listing messages failed (boom)."], snapshot.notes)
        self.assertNotIn("Gmail: connected (0 messages for this query)", snapshot.sources)
        self.assertEqual(
            "(No sources — enable Gmail/ADO, load team/allocations/strategy in config, or add data/ files.)",
            snapshot.sources[0],
        )

    def test_gmail_zero_messages_without_errors_records_successful_connection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch("src.shadow.snapshot.fetch_gmail_messages", return_value=([], [])):
                snapshot = build_snapshot(root, _isolated_config())

        self.assertEqual([], snapshot.notes)
        self.assertIn("Gmail: connected (0 messages for this query)", snapshot.sources)

    def test_gmail_messages_are_added_to_snapshot_and_counted_as_source(self):
        message = MailMessage(
            id="m-1",
            subject="Production checkout alert",
            from_addr="alerts@example.com",
            snippet="Investigate before release.",
            is_unread=True,
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch("src.shadow.snapshot.fetch_gmail_messages", return_value=([message], [])):
                snapshot = build_snapshot(root, _isolated_config())

        self.assertEqual([message], snapshot.mail_messages)
        self.assertIn("Gmail: 1 message(s)", snapshot.sources)


if __name__ == "__main__":
    unittest.main()
