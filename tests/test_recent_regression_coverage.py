import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from src.shadow.adapters.file_export import (
    FileExportAdapter,
    load_allocations_from_json,
    load_team_from_json,
)
from src.shadow.adapters.gmail import _header_map, _parse_internal_date
from src.shadow.capabilities.headquarters import render_headquarters_html
from src.shadow.capabilities.resource_allocation import render_resource_allocation_md
from src.shadow.capabilities.strategy_lens import _priority_rank, render_strategy_md
from src.shadow.models import (
    CapacityAllocation,
    MailMessage,
    Snapshot,
    StrategySignal,
)
from src.shadow.snapshot import build_snapshot


class FileExportParsingTests(unittest.TestCase):
    def test_team_loader_coerces_string_booleans_and_skills(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "team.json"
            path.write_text(
                json.dumps(
                    {
                        "members": [
                            {
                                "id": "qe-1",
                                "name": "Alex",
                                "skills": "API, CI, accessibility",
                                "on_vacation": "false",
                                "last_1_1": "2026-04-10",
                            },
                            {
                                "id": "qe-2",
                                "name": "Jordan",
                                "vacation": "yes",
                                "skills": ["UI"],
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )

            members = load_team_from_json(path)

        self.assertFalse(members[0].on_vacation)
        self.assertEqual(members[0].skills, ["API", "CI", "accessibility"])
        self.assertEqual(members[0].last_one_on_one, datetime(2026, 4, 10))
        self.assertTrue(members[1].on_vacation)

    def test_allocation_loader_preserves_zero_and_uses_nonblank_aliases(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "allocations.json"
            path.write_text(
                json.dumps(
                    {
                        "assignments": [
                            {"id": "zero", "person_id": "qe-1", "focus_pct": 0},
                            {"id": "alias", "person_id": "qe-2", "focus_pct": "", "pct": "35"},
                            {"id": "bad", "person_id": "qe-3", "allocation_pct": "not-a-number"},
                        ]
                    }
                ),
                encoding="utf-8",
            )

            allocations = load_allocations_from_json(path)

        self.assertEqual([a.focus_pct for a in allocations], [0, 35, None])

    def test_file_adapter_missing_qe_files_returns_empty_lists(self):
        adapter = FileExportAdapter(Path("/definitely/not/a/real/data-dir"))

        self.assertEqual(adapter.get_team_members(), [])
        self.assertEqual(adapter.get_allocations(), [])
        self.assertEqual(adapter.get_strategy_signals(), [])


class SnapshotProvenanceTests(unittest.TestCase):
    def test_build_snapshot_records_qe_files_and_gmail_message_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_dir = root / "data"
            data_dir.mkdir()
            (data_dir / "team.json").write_text(
                json.dumps([{"id": "qe-1", "name": "Alex"}]),
                encoding="utf-8",
            )
            (data_dir / "allocations.json").write_text(
                json.dumps([{"id": "a-1", "person_id": "qe-1", "focus_pct": 50}]),
                encoding="utf-8",
            )
            (data_dir / "strategy.json").write_text(
                json.dumps([{"id": "s-1", "pillar": "Automation", "priority": "P0"}]),
                encoding="utf-8",
            )
            config = {
                "data": {
                    "dir": "data",
                    "load_defects": False,
                    "load_test_runs": False,
                    "load_team": True,
                    "load_allocations": True,
                    "load_strategy": True,
                },
                "gmail": {"enabled": True},
            }
            mail = MailMessage(
                id="m-1",
                subject="Important launch note",
                from_addr="lead@example.com",
                snippet="Read before release",
                is_unread=True,
            )

            with patch("src.shadow.snapshot.fetch_gmail_messages", return_value=([mail], ["Gmail: note"])):
                snapshot = build_snapshot(root, config)

        self.assertEqual(len(snapshot.team_members), 1)
        self.assertEqual(len(snapshot.capacity_allocations), 1)
        self.assertEqual(len(snapshot.strategy_signals), 1)
        self.assertIn("File: team (team.json)", snapshot.sources)
        self.assertIn("File: allocations (allocations.json)", snapshot.sources)
        self.assertIn("File: strategy (strategy.json)", snapshot.sources)
        self.assertIn("Gmail: 1 message(s)", snapshot.sources)
        self.assertEqual(snapshot.notes, ["Gmail: note"])

    def test_build_snapshot_keeps_failed_gmail_in_notes_not_zero_message_source(self):
        config = {
            "data": {"load_defects": False, "load_test_runs": False, "load_team": False},
            "gmail": {"enabled": True},
        }

        with patch(
            "src.shadow.snapshot.fetch_gmail_messages",
            return_value=([], ["Gmail: listing messages failed (boom)."]),
        ):
            snapshot = build_snapshot(Path("/tmp"), config)

        self.assertIn("Gmail: listing messages failed (boom).", snapshot.notes)
        self.assertNotIn("Gmail: connected (0 messages for this query)", snapshot.sources)


class GmailHelperTests(unittest.TestCase):
    def test_header_map_is_case_insensitive_and_internal_date_is_safe(self):
        headers = _header_map(
            {
                "headers": [
                    {"name": "Subject", "value": "Ship readiness"},
                    {"name": "FROM", "value": "leader@example.com"},
                    {"name": "", "value": "ignored"},
                ]
            }
        )

        self.assertEqual(headers["subject"], "Ship readiness")
        self.assertEqual(headers["from"], "leader@example.com")
        self.assertEqual(_parse_internal_date("0"), datetime(1970, 1, 1, tzinfo=timezone.utc))
        self.assertIsNone(_parse_internal_date("not-a-date"))
        self.assertIsNone(_parse_internal_date("999999999999999999999999999"))


class QERendererRegressionTests(unittest.TestCase):
    def test_allocation_markdown_warns_on_overcommit_and_renders_zero_percent(self):
        snapshot = Snapshot(
            as_of=datetime(2026, 5, 2, tzinfo=timezone.utc),
            capacity_allocations=[
                CapacityAllocation(
                    id="a-1",
                    person_id="qe-1",
                    person_name="Alex Kim",
                    app_name="Billing",
                    sprint_label="2026-W18",
                    focus_pct=60,
                ),
                CapacityAllocation(
                    id="a-2",
                    person_id="qe-1",
                    person_name="Alex Kim",
                    app_name="Checkout",
                    sprint_label="2026-W18",
                    focus_pct=50,
                ),
                CapacityAllocation(
                    id="a-3",
                    person_id="qe-2",
                    person_name="Jordan Lee",
                    app_name="Admin",
                    sprint_label="2026-W18",
                    focus_pct=0,
                ),
            ],
        )

        md = render_resource_allocation_md(snapshot, {})

        self.assertIn("**Warning:** focus % sums > 100", md)
        self.assertIn("- qe-1 @ 2026-W18", md)
        self.assertIn("**Jordan Lee** — 0%", md)

    def test_strategy_renderer_orders_true_p1_ahead_of_p10(self):
        snapshot = Snapshot(
            as_of=datetime(2026, 5, 2, tzinfo=timezone.utc),
            strategy_signals=[
                StrategySignal(
                    id="s-p10",
                    pillar="Later",
                    summary="Should not sort as P1",
                    horizon="FY26",
                    priority="P10",
                ),
                StrategySignal(
                    id="s-p1",
                    pillar="Sooner",
                    summary="True P1 work",
                    horizon="FY26",
                    priority="P1",
                ),
            ],
        )

        md = render_strategy_md(snapshot, {})

        self.assertLess(md.index("## Sooner"), md.index("## Later"))
        self.assertEqual(_priority_rank("P10")[0], 9)
        self.assertEqual(_priority_rank("P1 - urgent")[0], 1)


class HeadquartersRegressionTests(unittest.TestCase):
    def test_headquarters_escapes_mail_content_and_can_hide_qe_panels(self):
        snapshot = Snapshot(
            as_of=datetime(2026, 5, 2, tzinfo=timezone.utc),
            sources=["unit-test"],
            mail_messages=[
                MailMessage(
                    id="message-with-long-id",
                    subject="<script>alert('x')</script>",
                    from_addr="attacker@example.com",
                    snippet="<b>do not render html</b>",
                    is_unread=True,
                )
            ],
            strategy_signals=[
                StrategySignal(id="s-1", pillar="Secret", summary="Hidden if QE off", priority="P0")
            ],
        )

        html = render_headquarters_html(
            snapshot,
            {"headquarters": {"show_qe_panels": False}, "brief": {"max_bullets": 3}},
            full_brief_markdown="# Brief\n\n<script>bad()</script>",
        )

        self.assertIn("&lt;script&gt;alert", html)
        self.assertIn("&lt;b&gt;do not render html&lt;/b&gt;", html)
        self.assertIn("&lt;script&gt;bad()&lt;/script&gt;", html)
        self.assertNotIn("<script>alert", html)
        self.assertNotIn("<h2>QE strategy signals</h2>", html)
        self.assertNotIn("Hidden if QE off", html)


if __name__ == "__main__":
    unittest.main()
