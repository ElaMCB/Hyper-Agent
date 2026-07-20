import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from src.shadow.snapshot import build_snapshot, find_repo_root


class SnapshotTests(unittest.TestCase):
    def test_find_repo_root_uses_config_marker_in_current_or_parent(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "config").mkdir()
            (root / "config" / "config.yaml").write_text("data: {}\n", encoding="utf-8")
            child = root / "nested"
            child.mkdir()

            self.assertEqual(find_repo_root(root), root)
            self.assertEqual(find_repo_root(child), root)

        with TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            self.assertEqual(find_repo_root(cwd), cwd)

    def test_build_snapshot_keeps_gmail_failures_in_notes_not_zero_message_source(self):
        with TemporaryDirectory() as tmp, patch(
            "src.shadow.snapshot.fetch_gmail_messages",
            return_value=([], ["Gmail: listing messages failed (boom)."]),
        ):
            snapshot = build_snapshot(
                Path(tmp),
                {
                    "data": {"load_defects": False, "load_test_runs": False},
                    "gmail": {"enabled": True},
                },
            )

        self.assertIn("Gmail: listing messages failed (boom).", snapshot.notes)
        self.assertFalse(any("Gmail: connected (0 messages" in s for s in snapshot.sources))
        self.assertIn("(No sources", snapshot.sources[0])

    def test_build_snapshot_records_empty_gmail_success_as_connected_source(self):
        with TemporaryDirectory() as tmp, patch(
            "src.shadow.snapshot.fetch_gmail_messages",
            return_value=([], []),
        ):
            snapshot = build_snapshot(
                Path(tmp),
                {
                    "data": {"load_defects": False, "load_test_runs": False},
                    "gmail": {"enabled": True},
                },
            )

        self.assertIn("Gmail: connected (0 messages for this query)", snapshot.sources)
        self.assertEqual(snapshot.notes, [])

    def test_build_snapshot_loads_qe_files_only_when_flags_are_enabled(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = root / "data"
            data.mkdir()
            (data / "team.json").write_text(
                json.dumps(
                    [
                        {
                            "id": "qe-1",
                            "name": "Alex",
                            "role": "QE",
                            "skills": ["API"],
                        }
                    ]
                ),
                encoding="utf-8",
            )
            (data / "allocations.json").write_text(
                json.dumps(
                    [
                        {
                            "id": "a1",
                            "person_id": "qe-1",
                            "person_name": "Alex",
                            "app_name": "Checkout",
                            "sprint_label": "2026-W20",
                            "focus_pct": 75,
                        }
                    ]
                ),
                encoding="utf-8",
            )
            (data / "strategy.json").write_text(
                json.dumps(
                    [
                        {
                            "id": "s1",
                            "pillar": "Automation",
                            "summary": "Raise API coverage",
                            "priority": "P0",
                        }
                    ]
                ),
                encoding="utf-8",
            )

            disabled = build_snapshot(
                root,
                {"data": {"load_defects": False, "load_test_runs": False}},
            )
            enabled = build_snapshot(
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

        self.assertEqual(disabled.team_members, [])
        self.assertEqual(disabled.capacity_allocations, [])
        self.assertEqual(disabled.strategy_signals, [])
        self.assertEqual(len(enabled.team_members), 1)
        self.assertEqual(len(enabled.capacity_allocations), 1)
        self.assertEqual(len(enabled.strategy_signals), 1)
        self.assertIn("File: team (team.json)", enabled.sources)
        self.assertIn("File: allocations (allocations.json)", enabled.sources)
        self.assertIn("File: strategy (strategy.json)", enabled.sources)


if __name__ == "__main__":
    unittest.main()
