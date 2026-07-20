import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from src.shadow.snapshot import build_snapshot


class SnapshotBuildTests(unittest.TestCase):
    def test_build_snapshot_loads_enabled_qe_files_and_records_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_dir = root / "data"
            data_dir.mkdir()
            (data_dir / "defects.json").write_text(
                json.dumps([{"id": "DEF-1", "title": "Checkout fails", "severity": "High"}]),
                encoding="utf-8",
            )
            (data_dir / "test_runs.json").write_text(
                json.dumps([{"id": "RUN-1", "name": "Smoke", "status": "Passed", "total": 10}]),
                encoding="utf-8",
            )
            (data_dir / "team.json").write_text(
                json.dumps([{"id": "qe-1", "name": "Riley Chen"}]),
                encoding="utf-8",
            )
            (data_dir / "allocations.json").write_text(
                json.dumps([{"id": "al-1", "person_id": "qe-1", "app_name": "Checkout"}]),
                encoding="utf-8",
            )
            (data_dir / "strategy.json").write_text(
                json.dumps([{"id": "st-1", "pillar": "Reliability", "summary": "Stabilize release gates"}]),
                encoding="utf-8",
            )

            snapshot = build_snapshot(
                root,
                {
                    "data": {
                        "dir": "data",
                        "load_team": True,
                        "load_allocations": True,
                        "load_strategy": True,
                    }
                },
            )

        self.assertEqual(1, len(snapshot.defects))
        self.assertEqual(1, len(snapshot.test_runs))
        self.assertEqual(1, len(snapshot.team_members))
        self.assertEqual(1, len(snapshot.capacity_allocations))
        self.assertEqual(1, len(snapshot.strategy_signals))
        self.assertEqual(
            [
                "File: defects (defects.json)",
                "File: test runs (test_runs.json)",
                "File: team (team.json)",
                "File: allocations (allocations.json)",
                "File: strategy (strategy.json)",
            ],
            snapshot.sources,
        )
        self.assertIsNotNone(snapshot.as_of.tzinfo)

    def test_gmail_failure_note_does_not_claim_connected_empty_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            with mock.patch(
                "src.shadow.snapshot.fetch_gmail_messages",
                return_value=([], ["Gmail: listing messages failed (boom)."]),
            ):
                snapshot = build_snapshot(
                    root,
                    {
                        "gmail": {"enabled": True},
                        "data": {"load_defects": False, "load_test_runs": False},
                    },
                )

        self.assertEqual(["Gmail: listing messages failed (boom)."], snapshot.notes)
        self.assertFalse(any("Gmail: connected" in source for source in snapshot.sources))
        self.assertEqual(
            ["(No sources \u2014 enable Gmail/ADO, load team/allocations/strategy in config, or add data/ files.)"],
            snapshot.sources,
        )

    def test_gmail_empty_success_records_connected_zero_messages_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            with mock.patch("src.shadow.snapshot.fetch_gmail_messages", return_value=([], [])):
                snapshot = build_snapshot(
                    root,
                    {
                        "gmail": {"enabled": True},
                        "data": {"load_defects": False, "load_test_runs": False},
                    },
                )

        self.assertEqual([], snapshot.notes)
        self.assertEqual(["Gmail: connected (0 messages for this query)"], snapshot.sources)


if __name__ == "__main__":
    unittest.main()
