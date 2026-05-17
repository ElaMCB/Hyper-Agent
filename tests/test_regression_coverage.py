import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from src.shadow.adapters.file_export import (
    FileExportAdapter,
    load_defects_from_json,
    load_test_runs_from_json,
)
from src.shadow.adapters.gmail import _header_map, _parse_internal_date
from src.shadow.capabilities.brief import get_brief_bullets_and_focus
from src.shadow.capabilities.headquarters import render_headquarters_html
from src.shadow.capabilities.resource_allocation import render_resource_allocation_md
from src.shadow.capabilities.strategy_lens import render_strategy_md, strategy_summary_bullets
from src.shadow.models import (
    CapacityAllocation,
    Defect,
    MailMessage,
    Snapshot,
    StrategySignal,
    TeamMember,
    TestRun,
)
from src.shadow.output.writer import (
    prune_headquarters_archives,
    write_headquarters_artifacts,
    write_headquarters_latest_md,
)
from src.shadow.snapshot import build_snapshot


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
            (data_dir / "team-export.json").write_text(
                json.dumps(
                    {
                        "members": [
                            {
                                "employee_id": "qe-7",
                                "name": "Priya Shah",
                                "role": "QE Lead",
                                "skills": "API, CI, , Security",
                                "vacation": True,
                                "vacation_until": "14/05/2026",
                                "morale": "yellow",
                                "last_1_1": "2026-05-01",
                                "performance_note": "Owns checkout risk",
                            },
                            "ignore malformed export row",
                        ]
                    }
                ),
                encoding="utf-8",
            )
            (data_dir / "alloc-export.json").write_text(
                json.dumps(
                    {
                        "assignments": [
                            {
                                "key": "alloc-1",
                                "person": "qe-7",
                                "name": "Priya Shah",
                                "app": "Checkout",
                                "sprint": "2026-W20",
                                "pct": "60",
                                "note": "Regression owner",
                            },
                            {
                                "key": "alloc-2",
                                "person": "qe-8",
                                "name": "Marco Lee",
                                "app": "Billing",
                                "sprint": "2026-W20",
                                "allocation_pct": "not a number",
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )
            (data_dir / "strategy-export.json").write_text(
                json.dumps(
                    {
                        "pillars": [
                            {
                                "key": "strat-1",
                                "theme": "Release readiness",
                                "title": "Protect checkout conversion before launch",
                                "priority": "P1",
                                "evidence": "Launch readiness review",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            adapter = FileExportAdapter(data_dir)
            team = adapter.get_team_members("team-export.json")
            allocations = adapter.get_allocations("alloc-export.json")
            strategy = adapter.get_strategy_signals("strategy-export.json")

        self.assertEqual(len(team), 1)
        self.assertEqual(team[0].id, "qe-7")
        self.assertEqual(team[0].skills, ["API", "CI", "Security"])
        self.assertTrue(team[0].on_vacation)
        self.assertEqual(team[0].vacation_until, datetime(2026, 5, 14))
        self.assertEqual(team[0].morale_flag, "yellow")
        self.assertEqual(team[0].last_one_on_one, datetime(2026, 5, 1))
        self.assertEqual([a.focus_pct for a in allocations], [60, None])
        self.assertEqual(allocations[0].person_id, "qe-7")
        self.assertEqual(allocations[1].app_name, "Billing")
        self.assertEqual(len(strategy), 1)
        self.assertEqual(strategy[0].id, "strat-1")
        self.assertEqual(strategy[0].pillar, "Release readiness")
        self.assertEqual(strategy[0].summary, "Protect checkout conversion before launch")
        self.assertEqual(strategy[0].evidence_ref, "Launch readiness review")

    def test_file_adapter_returns_empty_for_missing_files_and_loads_csv_defects(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            (data_dir / "defects.csv").write_text(
                "Key,Summary,priority,Status,Created\n"
                "BUG-7,Pipe export regression,High,Investigating,2026-05-15 11:30:00\n",
                encoding="utf-8",
            )

            adapter = FileExportAdapter(data_dir)
            missing_runs = adapter.get_test_runs()
            defects = adapter.get_defects("defects.csv")

        self.assertEqual(missing_runs, [])
        self.assertEqual(len(defects), 1)
        self.assertEqual(defects[0].id, "BUG-7")
        self.assertEqual(defects[0].title, "Pipe export regression")
        self.assertEqual(defects[0].created, datetime(2026, 5, 15, 11, 30))


class GmailAdapterRegressionTests(unittest.TestCase):
    def test_header_map_normalizes_names_and_uses_last_duplicate(self):
        headers = _header_map(
            {
                "headers": [
                    {"name": "Subject", "value": "Older subject"},
                    {"name": "FROM", "value": "lead@example.com"},
                    {"name": "", "value": "ignored"},
                    {"value": "missing name"},
                    {"name": "subject", "value": "Release approval"},
                ]
            }
        )

        self.assertEqual(
            headers,
            {
                "subject": "Release approval",
                "from": "lead@example.com",
            },
        )

    def test_parse_internal_date_returns_utc_datetime_or_none(self):
        parsed = _parse_internal_date("1714608000000")

        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.tzinfo, timezone.utc)
        self.assertEqual(parsed.isoformat(), "2024-05-02T00:00:00+00:00")
        self.assertIsNone(_parse_internal_date(None))
        self.assertIsNone(_parse_internal_date("not-a-timestamp"))


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

    def test_build_snapshot_loads_enabled_qe_files_and_records_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_dir = root / "data"
            data_dir.mkdir()
            (data_dir / "team.json").write_text(
                json.dumps([{"id": "qe-1", "name": "Alex Kim"}]),
                encoding="utf-8",
            )
            (data_dir / "allocations.json").write_text(
                json.dumps([{"id": "a1", "person_id": "qe-1", "app_name": "Checkout"}]),
                encoding="utf-8",
            )
            (data_dir / "strategy.json").write_text(
                json.dumps([{"id": "s1", "pillar": "Automation", "summary": "Raise coverage"}]),
                encoding="utf-8",
            )
            (data_dir / "defects.json").write_text(
                json.dumps([{"id": "bug-1", "title": "Disabled sample defect"}]),
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
        self.assertEqual(len(snapshot.team_members), 1)
        self.assertEqual(len(snapshot.capacity_allocations), 1)
        self.assertEqual(len(snapshot.strategy_signals), 1)
        self.assertEqual(
            snapshot.sources,
            [
                "File: team (team.json)",
                "File: allocations (allocations.json)",
                "File: strategy (strategy.json)",
            ],
        )

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


class QeRenderingRegressionTests(unittest.TestCase):
    def test_brief_qe_context_is_capped_before_work_bullets(self):
        snapshot = Snapshot(
            as_of=datetime(2026, 5, 14, tzinfo=timezone.utc),
            sources=["test"],
            defects=[
                Defect(
                    id="BUG-1",
                    title="Checkout payment callback intermittently drops high value orders",
                    severity="Critical",
                    status="Open",
                )
            ],
            test_runs=[
                TestRun(
                    id="run-1",
                    name="Nightly regression",
                    status="Failed",
                    total=10,
                    passed=8,
                    failed=2,
                )
            ],
            team_members=[
                TeamMember(
                    id="qe-1",
                    name="Alex Kim",
                    on_vacation=True,
                    last_one_on_one=datetime(2026, 4, 1),
                )
            ],
            capacity_allocations=[
                CapacityAllocation(id="a1", person_id="qe-1", app_name="Checkout", focus_pct=100)
            ],
            strategy_signals=[
                StrategySignal(id="s1", pillar="Automation", summary="Cover checkout API", priority="P0")
            ],
        )

        bullets, suggested = get_brief_bullets_and_focus(
            snapshot,
            {
                "brief": {"include_qe_context": True, "max_qe_context_bullets": 2},
                "people": {"one_on_one_stale_days": 21},
            },
            max_bullets=4,
        )

        self.assertEqual(len(bullets), 4)
        self.assertEqual(bullets[0], "QE team (file): 1 people, 1 flagged on vacation.")
        self.assertEqual(bullets[1], "1:1 hygiene: 1 member(s) past 21d or missing last 1:1 date.")
        self.assertEqual(bullets[2], "Defects: 1 total, 1 critical/high, 1 not closed.")
        self.assertTrue(bullets[3].startswith("Top severity: BUG-1"))
        self.assertEqual(
            suggested,
            "Balance people/capacity/strategy context with inbox and execution signals for today.",
        )

    def test_resource_allocation_flags_overcommit_per_person_and_sprint(self):
        snapshot = Snapshot(
            as_of=datetime(2026, 5, 14, tzinfo=timezone.utc),
            capacity_allocations=[
                CapacityAllocation(
                    id="a1",
                    person_id="qe-1",
                    person_name="Alex Kim",
                    app_name="Checkout",
                    sprint_label="2026-W20",
                    focus_pct=70,
                    commitment_note="release | regression",
                ),
                CapacityAllocation(
                    id="a2",
                    person_id="qe-1",
                    person_name="Alex Kim",
                    app_name="Billing",
                    sprint_label="2026-W20",
                    focus_pct=40,
                ),
                CapacityAllocation(
                    id="a3",
                    person_id="qe-1",
                    person_name="Alex Kim",
                    sprint_label="2026-W21",
                    focus_pct=80,
                ),
            ],
        )

        markdown = render_resource_allocation_md(snapshot, {})

        self.assertIn("**Warning:** focus % sums > 100 for:", markdown)
        self.assertIn("- qe-1 @ 2026-W20", markdown)
        self.assertNotIn("- qe-1 @ 2026-W21", markdown)
        self.assertIn("### (no app)", markdown)
        self.assertIn("release \\| regression", markdown)

    def test_strategy_renderer_orders_priority_and_escapes_table_pipes(self):
        snapshot = Snapshot(
            as_of=datetime(2026, 5, 14, tzinfo=timezone.utc),
            strategy_signals=[
                StrategySignal(
                    id="p2",
                    pillar="Mobile",
                    summary="Later",
                    horizon="FY26",
                    priority="P2",
                ),
                StrategySignal(
                    id="p0",
                    pillar="API",
                    summary="Cut release | rollback risk",
                    horizon="FY26",
                    priority="P0",
                    evidence_ref="plan | risks",
                ),
                StrategySignal(id="p1", pillar="Web", summary="Next", horizon="FY25", priority="P1"),
            ],
        )

        markdown = render_strategy_md(snapshot, {})
        bullets = strategy_summary_bullets(snapshot, {})

        self.assertLess(markdown.index("## API"), markdown.index("## Web"))
        self.assertLess(markdown.index("## Web"), markdown.index("## Mobile"))
        self.assertIn("Cut release \\| rollback risk", markdown)
        self.assertIn("plan \\| risks", markdown)
        self.assertEqual(len(bullets), 1)
        self.assertIn("top priority line", bullets[0])
        self.assertIn("**API** (P0): Cut release | rollback risk", bullets[0])


class HeadquartersRegressionTests(unittest.TestCase):
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
            latest_text = latest.read_text(encoding="utf-8") if latest else None
            latest_md_text = latest_md.read_text(encoding="utf-8")

        self.assertEqual(removed, 1)
        self.assertTrue(stamped.name.endswith("2026-05-15T100000Z.html"))
        self.assertEqual(latest_text, "<html>new</html>")
        self.assertEqual(latest_md_text, "# Morning brief\n")
        self.assertEqual(
            remaining_archives,
            ["headquarters-2026-05-14T100000Z.html", "headquarters-2026-05-15T100000Z.html"],
        )

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
        self.assertIn("Watch &lt;unsafe&gt; content", page)
        self.assertIn("No team rows (set data.load_team and data/team.json).", page)
        self.assertIn("No allocation rows (set data.load_allocations).", page)
        self.assertIn("No strategy rows (set data.load_strategy).", page)


if __name__ == "__main__":
    unittest.main()
