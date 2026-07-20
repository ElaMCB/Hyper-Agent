import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from src.shadow.snapshot import build_snapshot, find_repo_root


class SnapshotBuildTests(unittest.TestCase):
    def test_find_repo_root_accepts_repo_or_direct_child(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "config").mkdir()
            (root / "config" / "config.yaml").write_text("data: {}\n", encoding="utf-8")
            child = root / "src"
            child.mkdir()

            self.assertEqual(find_repo_root(root), root)
            self.assertEqual(find_repo_root(child), root)

    def test_build_snapshot_loads_enabled_file_sources_with_provenance(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_dir = root / "data"
            data_dir.mkdir()
            (data_dir / "defects.json").write_text(
                json.dumps([{"id": "D1", "title": "Login broken", "severity": "High"}]),
                encoding="utf-8",
            )
            (data_dir / "test_runs.json").write_text(
                json.dumps({"runs": [{"id": "R1", "name": "Nightly", "status": "Failed", "total": 10}]}),
                encoding="utf-8",
            )
            (data_dir / "team.json").write_text(
                json.dumps({"members": [{"id": "T1", "name": "Alex", "skills": "api, web"}]}),
                encoding="utf-8",
            )
            (data_dir / "allocations.json").write_text(
                json.dumps([{"id": "A1", "person_id": "T1", "app_name": "Portal", "focus_pct": 50}]),
                encoding="utf-8",
            )
            (data_dir / "strategy.json").write_text(
                json.dumps({"signals": [{"id": "S1", "pillar": "Reliability", "summary": "Reduce escapes"}]}),
                encoding="utf-8",
            )

            snapshot = build_snapshot(
                root,
                {
                    "data": {
                        "dir": "data",
                        "load_test_runs": True,
                        "load_team": True,
                        "load_allocations": True,
                        "load_strategy": True,
                    },
                    "azure_devops": {"enabled": False},
                    "gmail": {"enabled": False},
                },
            )

        self.assertEqual([d.id for d in snapshot.defects], ["D1"])
        self.assertEqual([r.id for r in snapshot.test_runs], ["R1"])
        self.assertEqual([m.id for m in snapshot.team_members], ["T1"])
        self.assertEqual([a.id for a in snapshot.capacity_allocations], ["A1"])
        self.assertEqual([s.id for s in snapshot.strategy_signals], ["S1"])
        self.assertEqual(
            snapshot.sources,
            [
                "File: defects (defects.json)",
                "File: test runs (test_runs.json)",
                "File: team (team.json)",
                "File: allocations (allocations.json)",
                "File: strategy (strategy.json)",
            ],
        )
        self.assertEqual(snapshot.notes, [])

    def test_build_snapshot_records_adapter_errors_without_claiming_sources(self):
        with TemporaryDirectory() as tmp, patch.dict(os.environ, {}, clear=True):
            snapshot = build_snapshot(
                Path(tmp),
                {
                    "data": {
                        "dir": "missing",
                        "load_defects": False,
                        "load_test_runs": False,
                        "load_team": False,
                        "load_allocations": False,
                        "load_strategy": False,
                    },
                    "azure_devops": {
                        "enabled": True,
                        "organization": "org",
                        "project": "project",
                        "pat_env": "AZDO_PAT",
                    },
                    "gmail": {"enabled": False},
                },
            )

        self.assertEqual(snapshot.defects, [])
        self.assertEqual(snapshot.test_runs, [])
        self.assertTrue(snapshot.sources[0].startswith("(No sources"))
        self.assertEqual(len(snapshot.notes), 1)
        self.assertIn("Azure DevOps PAT missing", snapshot.notes[0])


if __name__ == "__main__":
    unittest.main()
