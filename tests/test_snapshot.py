import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.shadow.models import MailMessage
from src.shadow.snapshot import build_snapshot


class SnapshotBuildTests(unittest.TestCase):
    def test_build_snapshot_respects_file_load_flags_and_records_qe_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_dir = root / "data"
            data_dir.mkdir()
            (data_dir / "defects.json").write_text(
                json.dumps([{"id": "BUG-1", "title": "Should stay unloaded"}]),
                encoding="utf-8",
            )
            (data_dir / "test_runs.json").write_text(
                json.dumps([{"id": "run-1", "name": "Should stay unloaded"}]),
                encoding="utf-8",
            )
            (data_dir / "team.json").write_text(
                json.dumps([{"id": "qa-1", "name": "Alex"}]),
                encoding="utf-8",
            )
            (data_dir / "allocations.json").write_text(
                json.dumps([{"id": "alloc-1", "person_id": "qa-1", "app_name": "Checkout"}]),
                encoding="utf-8",
            )
            (data_dir / "strategy.json").write_text(
                json.dumps([{"id": "s-1", "pillar": "Automation", "summary": "Protect smoke suite"}]),
                encoding="utf-8",
            )

            snapshot = build_snapshot(
                root,
                {
                    "data": {
                        "dir": "data",
                        "load_defects": False,
                        "load_test_runs": False,
                        "load_team": True,
                        "load_allocations": True,
                        "load_strategy": True,
                    }
                },
            )

            self.assertEqual(snapshot.defects, [])
            self.assertEqual(snapshot.test_runs, [])
            self.assertEqual([m.name for m in snapshot.team_members], ["Alex"])
            self.assertEqual([a.app_name for a in snapshot.capacity_allocations], ["Checkout"])
            self.assertEqual([s.pillar for s in snapshot.strategy_signals], ["Automation"])
            self.assertEqual(
                snapshot.sources,
                [
                    "File: team (team.json)",
                    "File: allocations (allocations.json)",
                    "File: strategy (strategy.json)",
                ],
            )

    def test_gmail_success_adds_source_and_notes(self):
        with tempfile.TemporaryDirectory() as tmp:
            msg = MailMessage(
                id="gmail-1",
                subject="Launch review",
                from_addr="qa@example.com",
                snippet="Please review",
                is_unread=True,
            )

            with patch("src.shadow.snapshot.fetch_gmail_messages", return_value=([msg], ["Gmail: partial fetch"])):
                snapshot = build_snapshot(
                    Path(tmp),
                    {
                        "data": {"load_defects": False, "load_test_runs": False},
                        "gmail": {"enabled": True},
                    },
                )

            self.assertEqual(snapshot.mail_messages, [msg])
            self.assertIn("Gmail: 1 message(s)", snapshot.sources)
            self.assertEqual(snapshot.notes, ["Gmail: partial fetch"])

    def test_gmail_failure_notes_do_not_claim_zero_message_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("src.shadow.snapshot.fetch_gmail_messages", return_value=([], ["Gmail: token refresh failed"])):
                snapshot = build_snapshot(
                    Path(tmp),
                    {
                        "data": {"load_defects": False, "load_test_runs": False},
                        "gmail": {"enabled": True},
                    },
                )

            self.assertNotIn("Gmail: connected (0 messages for this query)", snapshot.sources)
            self.assertEqual(len(snapshot.sources), 1)
            self.assertTrue(snapshot.sources[0].startswith("(No sources"))
            self.assertIn("enable Gmail/ADO", snapshot.sources[0])
            self.assertEqual(snapshot.notes, ["Gmail: token refresh failed"])


if __name__ == "__main__":
    unittest.main()
