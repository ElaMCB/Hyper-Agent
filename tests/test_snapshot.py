import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from src.shadow.models import MailMessage
from src.shadow.snapshot import build_snapshot


class SnapshotBuildTests(unittest.TestCase):
    def test_loads_qe_files_when_enabled_and_records_each_source(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_dir = root / "data"
            data_dir.mkdir()
            (data_dir / "team.json").write_text(
                json.dumps([{"id": "e-1", "name": "Alex"}]),
                encoding="utf-8",
            )
            (data_dir / "allocations.json").write_text(
                json.dumps([{"id": "a-1", "person_id": "e-1", "app_name": "Billing"}]),
                encoding="utf-8",
            )
            (data_dir / "strategy.json").write_text(
                json.dumps([{"id": "s-1", "pillar": "Quality", "summary": "Reduce escapes"}]),
                encoding="utf-8",
            )

            snapshot = build_snapshot(
                root,
                {
                    "data": {
                        "load_defects": False,
                        "load_test_runs": False,
                        "load_team": True,
                        "load_allocations": True,
                        "load_strategy": True,
                    }
                },
            )

        self.assertEqual([m.name for m in snapshot.team_members], ["Alex"])
        self.assertEqual([a.app_name for a in snapshot.capacity_allocations], ["Billing"])
        self.assertEqual([s.pillar for s in snapshot.strategy_signals], ["Quality"])
        self.assertIn("File: team (team.json)", snapshot.sources)
        self.assertIn("File: allocations (allocations.json)", snapshot.sources)
        self.assertIn("File: strategy (strategy.json)", snapshot.sources)

    def test_disabled_qe_files_are_not_loaded_or_listed_as_sources(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_dir = root / "data"
            data_dir.mkdir()
            (data_dir / "team.json").write_text(
                json.dumps([{"id": "e-1", "name": "Alex"}]),
                encoding="utf-8",
            )

            snapshot = build_snapshot(
                root,
                {
                    "data": {
                        "load_defects": False,
                        "load_test_runs": False,
                        "load_team": False,
                        "load_allocations": False,
                        "load_strategy": False,
                    }
                },
            )

        self.assertEqual(snapshot.team_members, [])
        self.assertEqual(snapshot.capacity_allocations, [])
        self.assertEqual(snapshot.strategy_signals, [])
        self.assertEqual(
            snapshot.sources,
            [
                "(No sources — enable Gmail/ADO, load team/allocations/strategy in config, or add data/ files.)"
            ],
        )

    def test_gmail_failures_are_notes_not_successful_zero_message_sources(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch("src.shadow.snapshot.fetch_gmail_messages", return_value=([], ["Gmail: bad token"])):
                snapshot = build_snapshot(
                    root,
                    {
                        "data": {"load_defects": False, "load_test_runs": False},
                        "gmail": {"enabled": True},
                    },
                )

        self.assertEqual(snapshot.mail_messages, [])
        self.assertEqual(snapshot.notes, ["Gmail: bad token"])
        self.assertNotIn("Gmail: connected (0 messages for this query)", snapshot.sources)

    def test_empty_successful_gmail_query_records_zero_message_source(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch("src.shadow.snapshot.fetch_gmail_messages", return_value=([], [])):
                snapshot = build_snapshot(
                    root,
                    {
                        "data": {"load_defects": False, "load_test_runs": False},
                        "gmail": {"enabled": True},
                    },
                )

        self.assertIn("Gmail: connected (0 messages for this query)", snapshot.sources)
        self.assertEqual(snapshot.notes, [])

    def test_successful_gmail_query_records_message_count_source(self):
        message = MailMessage(
            id="m-1",
            subject="Deploy approval",
            from_addr="lead@example.com",
            snippet="Please confirm",
        )
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch("src.shadow.snapshot.fetch_gmail_messages", return_value=([message], [])):
                snapshot = build_snapshot(
                    root,
                    {
                        "data": {"load_defects": False, "load_test_runs": False},
                        "gmail": {"enabled": True},
                    },
                )

        self.assertEqual(snapshot.mail_messages, [message])
        self.assertIn("Gmail: 1 message(s)", snapshot.sources)


if __name__ == "__main__":
    unittest.main()
