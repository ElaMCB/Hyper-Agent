import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.shadow.snapshot import build_snapshot


class SnapshotBuildTests(unittest.TestCase):
    def test_build_snapshot_loads_qe_files_and_keeps_gmail_failures_in_notes_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_dir = root / "data"
            data_dir.mkdir()
            (data_dir / "team.json").write_text(
                json.dumps({"team": [{"id": "qa-1", "name": "Asha"}]}),
                encoding="utf-8",
            )
            (data_dir / "allocations.json").write_text(
                json.dumps({"allocations": [{"id": "a-1", "person_id": "qa-1", "app_name": "Checkout"}]}),
                encoding="utf-8",
            )
            (data_dir / "strategy.json").write_text(
                json.dumps({"strategy": [{"id": "s-1", "pillar": "Release", "summary": "Ship safely"}]}),
                encoding="utf-8",
            )
            config = {
                "gmail": {"enabled": True},
                "data": {
                    "dir": "data",
                    "load_defects": False,
                    "load_test_runs": False,
                    "load_team": True,
                    "load_allocations": True,
                    "load_strategy": True,
                },
            }

            with patch(
                "src.shadow.snapshot.fetch_gmail_messages",
                return_value=([], ["Gmail: OAuth client JSON not found at /tmp/missing.json"]),
            ):
                snapshot = build_snapshot(root, config)

        self.assertEqual(len(snapshot.team_members), 1)
        self.assertEqual(len(snapshot.capacity_allocations), 1)
        self.assertEqual(len(snapshot.strategy_signals), 1)
        self.assertIn("File: team (team.json)", snapshot.sources)
        self.assertIn("File: allocations (allocations.json)", snapshot.sources)
        self.assertIn("File: strategy (strategy.json)", snapshot.sources)
        self.assertEqual(snapshot.notes, ["Gmail: OAuth client JSON not found at /tmp/missing.json"])
        self.assertNotIn("Gmail: connected (0 messages for this query)", snapshot.sources)

    def test_build_snapshot_records_connected_empty_gmail_only_when_no_adapter_notes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = {
                "gmail": {"enabled": True},
                "data": {
                    "dir": "data",
                    "load_defects": False,
                    "load_test_runs": False,
                    "load_team": False,
                    "load_allocations": False,
                    "load_strategy": False,
                },
            }

            with patch("src.shadow.snapshot.fetch_gmail_messages", return_value=([], [])):
                snapshot = build_snapshot(root, config)

        self.assertEqual(snapshot.sources, ["Gmail: connected (0 messages for this query)"])
        self.assertEqual(snapshot.notes, [])


if __name__ == "__main__":
    unittest.main()
