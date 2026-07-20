import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.shadow.capabilities.brief import render_brief
from src.shadow.snapshot import build_snapshot


class SnapshotRegressionTests(unittest.TestCase):
    def test_snapshot_loads_enabled_qe_files_and_brief_includes_provenance(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            data_dir = root / "data"
            data_dir.mkdir()
            (data_dir / "defects.json").write_text(
                json.dumps([{"id": "DEF-1", "title": "Payment failure", "severity": "Critical", "status": "Open"}]),
                encoding="utf-8",
            )
            (data_dir / "test_runs.json").write_text(
                json.dumps([{"id": "RUN-1", "name": "Smoke", "status": "Passed", "total": 10, "passed": 10, "failed": 0}]),
                encoding="utf-8",
            )
            (data_dir / "team.json").write_text(
                json.dumps([{"id": "qe-1", "name": "Alex", "on_vacation": False, "last_one_on_one": "2026-05-01"}]),
                encoding="utf-8",
            )
            (data_dir / "allocations.json").write_text(
                json.dumps([{"id": "a-1", "person_id": "qe-1", "person_name": "Alex", "app_name": "Billing", "focus_pct": 50}]),
                encoding="utf-8",
            )
            (data_dir / "strategy.json").write_text(
                json.dumps([{"id": "s-1", "pillar": "Automation", "priority": "P0", "summary": "Protect checkout"}]),
                encoding="utf-8",
            )
            config = {
                "data": {
                    "dir": "data",
                    "load_team": True,
                    "load_allocations": True,
                    "load_strategy": True,
                },
                "brief": {
                    "include_qe_context": True,
                    "max_bullets": 5,
                    "max_qe_context_bullets": 3,
                },
                "people": {"one_on_one_stale_days": 45},
            }

            snapshot = build_snapshot(root, config)
            markdown = render_brief(snapshot, root, config)

        self.assertEqual(len(snapshot.defects), 1)
        self.assertEqual(len(snapshot.test_runs), 1)
        self.assertEqual(len(snapshot.team_members), 1)
        self.assertEqual(len(snapshot.capacity_allocations), 1)
        self.assertEqual(len(snapshot.strategy_signals), 1)
        self.assertIn("File: defects (defects.json)", snapshot.sources)
        self.assertIn("File: team (team.json)", snapshot.sources)
        self.assertIn("QE team (file): 1 people, 0 flagged on vacation.", markdown)
        self.assertIn("Allocations: 1 row(s) across 1 app bucket(s).", markdown)
        self.assertIn("Strategy file: 1 signal(s); top priority line", markdown)
        self.assertIn("Sources: File: defects (defects.json)", markdown)

    def test_gmail_adapter_notes_do_not_create_successful_source_claim(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "data").mkdir()
            config = {
                "data": {
                    "dir": "data",
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
                return_value=([], ["Gmail: token refresh failed"]),
            ):
                snapshot = build_snapshot(root, config)

        self.assertEqual(snapshot.mail_messages, [])
        self.assertEqual(snapshot.notes, ["Gmail: token refresh failed"])
        self.assertNotIn("Gmail: connected (0 messages for this query)", snapshot.sources)
        self.assertEqual(
            snapshot.sources,
            ["(No sources — enable Gmail/ADO, load team/allocations/strategy in config, or add data/ files.)"],
        )


if __name__ == "__main__":
    unittest.main()
