import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.shadow.adapters.file_export import (  # noqa: E402
    FileExportAdapter,
    load_defects_from_json,
    load_test_runs_from_json,
)
from src.shadow.capabilities.headquarters import render_headquarters_html  # noqa: E402
from src.shadow.models import Defect, MailMessage, Snapshot  # noqa: E402
from src.shadow.output.writer import (  # noqa: E402
    prune_headquarters_archives,
    write_headquarters_artifacts,
    write_headquarters_latest_md,
)
from src.shadow.snapshot import build_snapshot  # noqa: E402


class FileExportRegressionTests(unittest.TestCase):
    def test_json_loaders_accept_export_aliases_and_dates(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            defects_path = tmp_path / "jira_issues.json"
            test_runs_path = tmp_path / "runs.json"
            defects_path.write_text(
                json.dumps(
                    {
                        "issues": [
                            {
                                "key": "BUG-123",
                                "summary": "Checkout fails",
                                "priority": "Critical",
                                "state": "Open",
                                "Created": "2026-05-14",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            test_runs_path.write_text(
                json.dumps(
                    {
                        "runs": [
                            {
                                "run_id": "TR-9",
                                "run_name": "Nightly regression",
                                "Status": "Failed",
                                "date": "16/05/2026",
                                "passed": 42,
                                "failed": 3,
                                "total": 45,
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            defects = load_defects_from_json(defects_path)
            runs = load_test_runs_from_json(test_runs_path)

        self.assertEqual(len(defects), 1)
        self.assertEqual(defects[0].id, "BUG-123")
        self.assertEqual(defects[0].severity, "Critical")
        self.assertEqual(defects[0].created, datetime(2026, 5, 14))
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0].id, "TR-9")
        self.assertEqual(runs[0].name, "Nightly regression")
        self.assertEqual(runs[0].executed_at, datetime(2026, 5, 16))
        self.assertEqual(runs[0].failed, 3)

    def test_qe_file_exports_handle_aliases_lists_and_invalid_percentages(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            (data_dir / "team.json").write_text(
                json.dumps(
                    {
                        "members": [
                            {
                                "employee_id": "e-1",
                                "name": "Sam Tester",
                                "role": "QE Lead",
                                "skills": "api, automation, release",
                                "vacation": True,
                                "last_1_1": "2026-05-01T09:30:00",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            (data_dir / "allocations.json").write_text(
                json.dumps(
                    {
                        "assignments": [
                            {
                                "key": "alloc-1",
                                "person": "e-1",
                                "name": "Sam Tester",
                                "app": "Payments",
                                "sprint": "Sprint 42",
                                "pct": "not-a-number",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            (data_dir / "strategy.json").write_text(
                json.dumps(
                    {
                        "pillars": [
                            {
                                "key": "strat-1",
                                "theme": "Reliability",
                                "title": "Stabilize checkout",
                                "evidence": "Q2 roadmap",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            adapter = FileExportAdapter(data_dir)
            team = adapter.get_team_members()
            allocations = adapter.get_allocations()
            strategy = adapter.get_strategy_signals()

        self.assertEqual(team[0].skills, ["api", "automation", "release"])
        self.assertTrue(team[0].on_vacation)
        self.assertEqual(team[0].last_one_on_one, datetime(2026, 5, 1, 9, 30))
        self.assertEqual(allocations[0].person_id, "e-1")
        self.assertIsNone(allocations[0].focus_pct)
        self.assertEqual(strategy[0].pillar, "Reliability")
        self.assertEqual(strategy[0].summary, "Stabilize checkout")


class SnapshotRegressionTests(unittest.TestCase):
    def test_build_snapshot_records_no_source_fallback_when_every_adapter_disabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            snapshot = build_snapshot(
                Path(tmp),
                {
                    "data": {
                        "dir": "data",
                        "load_defects": False,
                        "load_test_runs": False,
                        "load_team": False,
                        "load_allocations": False,
                        "load_strategy": False,
                    },
                    "azure_devops": {"enabled": False},
                    "gmail": {"enabled": False},
                },
            )

        self.assertEqual(len(snapshot.sources), 1)
        self.assertTrue(snapshot.sources[0].startswith("(No sources"))
        self.assertIn("enable Gmail/ADO", snapshot.sources[0])
        self.assertEqual(snapshot.defects, [])
        self.assertEqual(snapshot.test_runs, [])

    def test_build_snapshot_reports_gmail_messages_as_source(self):
        message = MailMessage(
            id="msg-1",
            subject="Release readiness",
            from_addr="lead@example.com",
            snippet="Please review",
            is_unread=True,
        )

        with tempfile.TemporaryDirectory() as tmp, patch(
            "src.shadow.snapshot.fetch_gmail_messages", return_value=([message], [])
        ):
            snapshot = build_snapshot(
                Path(tmp),
                {
                    "data": {"dir": "data", "load_defects": False, "load_test_runs": False},
                    "gmail": {"enabled": True},
                },
            )

        self.assertEqual(snapshot.mail_messages, [message])
        self.assertIn("Gmail: 1 message(s)", snapshot.sources)
        self.assertEqual(snapshot.notes, [])

    def test_build_snapshot_keeps_gmail_failures_in_notes_not_sources(self):
        with tempfile.TemporaryDirectory() as tmp, patch(
            "src.shadow.snapshot.fetch_gmail_messages",
            return_value=([], ["Gmail: listing messages failed (boom)."]),
        ):
            snapshot = build_snapshot(
                Path(tmp),
                {
                    "data": {"dir": "data", "load_defects": False, "load_test_runs": False},
                    "gmail": {"enabled": True},
                },
            )

        self.assertEqual(snapshot.mail_messages, [])
        self.assertEqual(snapshot.notes, ["Gmail: listing messages failed (boom)."])
        self.assertNotIn("Gmail: connected (0 messages for this query)", snapshot.sources)
        self.assertEqual(len(snapshot.sources), 1)
        self.assertTrue(snapshot.sources[0].startswith("(No sources"))
        self.assertIn("enable Gmail/ADO", snapshot.sources[0])


class HeadquartersArtifactRegressionTests(unittest.TestCase):
    def test_headquarters_artifact_writes_latest_markdown_and_prunes_archives_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            hq_dir = "output/headquarters"
            out_dir = root / hq_dir
            out_dir.mkdir(parents=True)
            (out_dir / "headquarters-2026-05-13T100000Z.html").write_text("old", encoding="utf-8")
            (out_dir / "headquarters-2026-05-14T100000Z.html").write_text("middle", encoding="utf-8")
            (out_dir / "latest.html").write_text("stable", encoding="utf-8")

            stamped, latest = write_headquarters_artifacts(
                root,
                "<html>new</html>",
                datetime(2026, 5, 15, 10, 0, 0, tzinfo=timezone.utc),
                hq_dir,
            )
            latest_md = write_headquarters_latest_md(root, "# Morning brief\n", hq_dir)
            removed = prune_headquarters_archives(root, hq_dir, max_keep=2)

            remaining_archives = sorted(p.name for p in out_dir.glob("headquarters-*.html"))
            stamped_name = stamped.name
            latest_text = latest.read_text(encoding="utf-8") if latest else None
            latest_md_text = latest_md.read_text(encoding="utf-8")

        self.assertEqual(removed, 1)
        self.assertTrue(stamped_name.endswith("2026-05-15T100000Z.html"))
        self.assertIsNotNone(latest_text)
        self.assertEqual(latest_text, "<html>new</html>")
        self.assertEqual(latest_md_text, "# Morning brief\n")
        self.assertEqual(
            remaining_archives,
            ["headquarters-2026-05-14T100000Z.html", "headquarters-2026-05-15T100000Z.html"],
        )

    def test_headquarters_artifact_can_skip_latest_html_and_prune_can_noop(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            stamped, latest = write_headquarters_artifacts(
                root,
                "<html>archive only</html>",
                datetime(2026, 5, 16, 10, 0, 0, tzinfo=timezone.utc),
                "hq",
                write_latest=False,
            )
            removed = prune_headquarters_archives(root, "hq", max_keep=0)

            self.assertTrue(stamped.exists())
            self.assertIsNone(latest)
            self.assertFalse((root / "hq" / "latest.html").exists())
            self.assertEqual(removed, 0)
            self.assertTrue(stamped.exists())


class HeadquartersHtmlRegressionTests(unittest.TestCase):
    def test_render_headquarters_html_escapes_snapshot_content_and_empty_qe_rows(self):
        snapshot = Snapshot(
            as_of=datetime(2026, 5, 16, 10, 0, 0, tzinfo=timezone.utc),
            sources=["File: defects (defects.json)"],
            defects=[
                Defect(
                    id="BUG-<1>",
                    title='<script>alert("x")</script>',
                    severity="Critical & High",
                    status="Open",
                )
            ],
            mail_messages=[
                MailMessage(
                    id="msg-<unsafe>",
                    subject='Release <cutover> & "ship"',
                    from_addr="Lead <lead@example.com>",
                    snippet="<b>review now</b>",
                    is_unread=True,
                )
            ],
        )

        page = render_headquarters_html(
            snapshot,
            {"headquarters": {"title": "Shadow <HQ>"}, "brief": {"max_bullets": 5}},
            full_brief_markdown="# Brief\nWatch <unsafe> content",
        )

        self.assertIn("Shadow &lt;HQ&gt;", page)
        self.assertIn("BUG-&lt;1&gt;", page)
        self.assertIn("&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;", page)
        self.assertNotIn('<script>alert("x")</script>', page)
        self.assertIn("Release &lt;cutover&gt; &amp; &quot;ship&quot;", page)
        self.assertIn("&lt;b&gt;review now&lt;/b&gt;", page)
        self.assertIn("No team rows (set data.load_team and data/team.json).", page)
        self.assertIn("No allocation rows (set data.load_allocations).", page)
        self.assertIn("No strategy rows (set data.load_strategy).", page)


if __name__ == "__main__":
    unittest.main()
