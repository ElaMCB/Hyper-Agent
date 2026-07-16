import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from src import main
from src.shadow.models import Snapshot, TeamMember


class QeCliArtifactTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = Snapshot(
            as_of=datetime(2026, 5, 2, 12, 0, tzinfo=timezone.utc),
            sources=["File: team (team.json)"],
            team_members=[
                TeamMember(
                    id="qe-1",
                    name="Jordan Lee",
                    role="QE lead",
                    performance_note="Sensitive leadership context",
                )
            ],
        )

    def test_qe_command_saves_complete_pack_to_configured_directory(self):
        config = {
            "qe_subagents": {
                "output_dir": "private/qe-artifacts",
                "save_on_cli": True,
            }
        }

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            stdout = io.StringIO()
            stderr = io.StringIO()
            with (
                patch.object(main, "_ROOT", root),
                patch.object(main, "build_snapshot", return_value=self.snapshot),
                redirect_stdout(stdout),
                redirect_stderr(stderr),
            ):
                main.cmd_qe(config)

            artifact = (
                root
                / "private/qe-artifacts"
                / "qe-pack-2026-05-02T120000Z.md"
            )
            self.assertTrue(artifact.is_file())
            markdown = artifact.read_text(encoding="utf-8")
            self.assertEqual(stdout.getvalue(), f"{markdown}\n")
            self.assertIn("# People & capacity (QE)", markdown)
            self.assertIn("# Resource allocation (QE)", markdown)
            self.assertIn("# Strategy lens (QE)", markdown)
            self.assertIn(str(artifact), stderr.getvalue())

    def test_qe_command_does_not_persist_sensitive_output_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with (
                patch.object(main, "_ROOT", root),
                patch.object(main, "build_snapshot", return_value=self.snapshot),
                redirect_stdout(io.StringIO()),
                redirect_stderr(io.StringIO()),
            ):
                main.cmd_qe({})

            self.assertFalse((root / "output").exists())


if __name__ == "__main__":
    unittest.main()
