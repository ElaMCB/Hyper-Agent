import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from src.shadow.adapters.file_export import FileExportAdapter
from src.shadow.adapters.gmail import _header_map, _parse_internal_date
from src.shadow.capabilities.headquarters import render_headquarters_html
from src.shadow.capabilities.qe_pack import render_qe_subagent_pack
from src.shadow.models import (
    CapacityAllocation,
    Defect,
    MailMessage,
    Snapshot,
    StrategySignal,
    TeamMember,
)
from src.shadow.output.writer import prune_headquarters_archives
from src.shadow.snapshot import build_snapshot


class FileExportAdapterRegressionTests(unittest.TestCase):
    def test_loads_qe_leadership_files_from_supported_wrappers(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            (data_dir / "team.json").write_text(
                json.dumps(
                    {
                        "members": [
                            {
                                "employee_id": "qa-1",
                                "name": "Priya",
                                "role": "QE Lead",
                                "skills": "api, payments, automation",
                                "vacation": True,
                                "vacation_until": "2026-05-20",
                                "morale": "amber",
                                "last_1_1": "2026-04-01",
                                "performance_note": "Owns release risk",
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
                                "person": "qa-1",
                                "name": "Priya",
                                "app": "Checkout",
                                "sprint": "S-42",
                                "pct": "60",
                                "note": "Regression lead",
                            },
                            {
                                "key": "alloc-2",
                                "person": "qa-2",
                                "app": "Search",
                                "allocation_pct": "not-a-number",
                            },
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
                                "theme": "Release confidence",
                                "title": "Stabilize payment smoke coverage",
                                "horizon": "Q2",
                                "priority": "P0",
                                "status": "active",
                                "evidence": "board/CHECKOUT-7",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            adapter = FileExportAdapter(data_dir)

            team = adapter.get_team_members()
            self.assertEqual(len(team), 1)
            self.assertEqual(team[0].id, "qa-1")
            self.assertEqual(team[0].skills, ["api", "payments", "automation"])
            self.assertTrue(team[0].on_vacation)
            self.assertEqual(team[0].vacation_until, datetime(2026, 5, 20))
            self.assertEqual(team[0].last_one_on_one, datetime(2026, 4, 1))

            allocations = adapter.get_allocations()
            self.assertEqual([a.focus_pct for a in allocations], [60, None])
            self.assertEqual(allocations[0].commitment_note, "Regression lead")

            strategy = adapter.get_strategy_signals()
            self.assertEqual(strategy[0].id, "strat-1")
            self.assertEqual(strategy[0].pillar, "Release confidence")
            self.assertEqual(strategy[0].summary, "Stabilize payment smoke coverage")
            self.assertEqual(strategy[0].evidence_ref, "board/CHECKOUT-7")


class GmailMetadataRegressionTests(unittest.TestCase):
    def test_header_map_normalizes_names_and_parse_internal_date_is_safe(self):
        headers = _header_map(
            {
                "headers": [
                    {"name": "Subject", "value": "Release readiness"},
                    {"name": "FROM", "value": "lead@example.test"},
                    {"name": "", "value": "ignored"},
                    {"name": "Date"},
                ]
            }
        )

        self.assertEqual(headers["subject"], "Release readiness")
        self.assertEqual(headers["from"], "lead@example.test")
        self.assertEqual(headers["date"], "")
        self.assertNotIn("", headers)
        self.assertEqual(
            _parse_internal_date("1716033600000"),
            datetime(2024, 5, 18, 12, 0, tzinfo=timezone.utc),
        )
        self.assertIsNone(_parse_internal_date("bad timestamp"))
        self.assertIsNone(_parse_internal_date(None))


class SnapshotRegressionTests(unittest.TestCase):
    def test_build_snapshot_loads_qe_sources_and_keeps_gmail_failures_in_notes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_dir = root / "data"
            data_dir.mkdir()
            (data_dir / "team.json").write_text(
                json.dumps([{"id": "qa-1", "name": "Priya"}]),
                encoding="utf-8",
            )
            (data_dir / "allocations.json").write_text(
                json.dumps([{"id": "a1", "person_id": "qa-1", "app_name": "Checkout"}]),
                encoding="utf-8",
            )
            (data_dir / "strategy.json").write_text(
                json.dumps([{"id": "s1", "pillar": "Quality", "summary": "Raise release bar"}]),
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

            with patch(
                "src.shadow.snapshot.fetch_gmail_messages",
                return_value=([], ["Gmail: token refresh failed"]),
            ):
                snapshot = build_snapshot(root, config)

            self.assertEqual(len(snapshot.team_members), 1)
            self.assertEqual(len(snapshot.capacity_allocations), 1)
            self.assertEqual(len(snapshot.strategy_signals), 1)
            self.assertIn("File: team (team.json)", snapshot.sources)
            self.assertIn("File: allocations (allocations.json)", snapshot.sources)
            self.assertIn("File: strategy (strategy.json)", snapshot.sources)
            self.assertEqual(snapshot.notes, ["Gmail: token refresh failed"])
            self.assertFalse(any(source.startswith("Gmail:") for source in snapshot.sources))

    def test_build_snapshot_records_empty_gmail_success_as_connected_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = {
                "data": {"dir": "data", "load_defects": False, "load_test_runs": False},
                "gmail": {"enabled": True},
            }

            with patch("src.shadow.snapshot.fetch_gmail_messages", return_value=([], [])):
                snapshot = build_snapshot(root, config)

            self.assertEqual(snapshot.sources, ["Gmail: connected (0 messages for this query)"])
            self.assertEqual(snapshot.notes, [])


class QeRenderingRegressionTests(unittest.TestCase):
    def test_qe_pack_flags_stale_one_on_ones_overallocations_and_sorts_strategy(self):
        snapshot = Snapshot(
            as_of=datetime(2026, 5, 18, tzinfo=timezone.utc),
            team_members=[
                TeamMember(
                    id="qa-1",
                    name="Priya",
                    role="QE Lead",
                    skills=["api", "payments"],
                    morale_flag="amber",
                    last_one_on_one=datetime(2026, 4, 1),
                    performance_note="Can explain release risk | needs backup",
                )
            ],
            capacity_allocations=[
                CapacityAllocation(
                    id="a1",
                    person_id="qa-1",
                    person_name="Priya",
                    app_name="Checkout",
                    sprint_label="S-42",
                    focus_pct=70,
                ),
                CapacityAllocation(
                    id="a2",
                    person_id="qa-1",
                    person_name="Priya",
                    app_name="Search",
                    sprint_label="S-42",
                    focus_pct=50,
                ),
            ],
            strategy_signals=[
                StrategySignal(
                    id="s2",
                    pillar="Later",
                    summary="P2 item",
                    horizon="Q3",
                    priority="P2",
                ),
                StrategySignal(
                    id="s1",
                    pillar="Now",
                    summary="P0 item",
                    horizon="Q2",
                    priority="P0",
                ),
            ],
        )

        md = render_qe_subagent_pack(snapshot, {"people": {"one_on_one_stale_days": 21}})

        self.assertIn("Morale watch (amber/red):** Priya", md)
        self.assertIn("1:1 stale (>21d or missing):** Priya", md)
        self.assertIn("**Warning:** focus % sums > 100", md)
        self.assertIn("- qa-1 @ S-42", md)
        self.assertLess(md.index("## Now"), md.index("## Later"))
        self.assertIn("Can explain release risk \\| needs backup", md)


class HeadquartersRegressionTests(unittest.TestCase):
    def test_headquarters_escapes_snapshot_and_configured_content(self):
        snapshot = Snapshot(
            as_of=datetime(2026, 5, 18, 10, 0, tzinfo=timezone.utc),
            sources=["File: defects (<unsafe>)"],
            defects=[
                Defect(
                    id="BUG-1",
                    title="<script>alert('defect')</script>",
                    severity="High",
                    status="Open",
                )
            ],
            mail_messages=[
                MailMessage(
                    id="mail-123456789012345",
                    subject="<script>alert('mail')</script>",
                    from_addr="attacker@example.test",
                    snippet="x < y & z",
                    internal_date=datetime(2026, 5, 18, 9, 0, tzinfo=timezone.utc),
                    is_unread=True,
                )
            ],
            team_members=[
                TeamMember(id="qa-1", name="<img src=x onerror=alert(1)>", role="Lead")
            ],
            capacity_allocations=[
                CapacityAllocation(
                    id="a1",
                    person_id="qa-1",
                    person_name="Priya",
                    app_name="Checkout <prod>",
                    sprint_label="S-42",
                    focus_pct=80,
                    commitment_note="keep <smoke> green",
                )
            ],
            strategy_signals=[
                StrategySignal(
                    id="s1",
                    pillar="Quality <north>",
                    summary="Avoid <b>invented</b> confidence",
                    priority="P0",
                )
            ],
        )
        config = {
            "headquarters": {
                "title": "Shadow <HQ>",
                "links": [{"label": "Risk <board>", "url": "https://example.test/?q=<risk>"}],
                "show_qe_panels": True,
            }
        }

        html = render_headquarters_html(
            snapshot,
            config,
            full_brief_markdown="# Brief\n\n<script>alert('brief')</script>",
        )

        self.assertIn("Shadow &lt;HQ&gt;", html)
        self.assertIn("Risk &lt;board&gt;", html)
        self.assertIn("https://example.test/?q=&lt;risk&gt;", html)
        self.assertIn("&lt;script&gt;alert(&#x27;mail&#x27;)&lt;/script&gt;", html)
        self.assertIn("&lt;img src=x onerror=alert(1)&gt;", html)
        self.assertIn("Checkout &lt;prod&gt;", html)
        self.assertIn("Avoid &lt;b&gt;invented&lt;/b&gt; confidence", html)
        self.assertIn("&lt;script&gt;alert(&#x27;brief&#x27;)&lt;/script&gt;", html)
        self.assertNotIn("<script>alert", html)
        self.assertNotIn("<img src=x", html)
        self.assertNotIn("<b>invented</b>", html)


class OutputWriterRegressionTests(unittest.TestCase):
    def test_prune_headquarters_archives_keeps_latest_files_and_newest_archives(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            hq_dir = root / "output" / "headquarters"
            hq_dir.mkdir(parents=True)
            for name in [
                "headquarters-2026-05-15T100000Z.html",
                "headquarters-2026-05-16T100000Z.html",
                "headquarters-2026-05-17T100000Z.html",
                "headquarters-2026-05-18T100000Z.html",
                "latest.html",
                "latest.md",
            ]:
                (hq_dir / name).write_text(name, encoding="utf-8")

            removed = prune_headquarters_archives(root, "output/headquarters", 2)

            self.assertEqual(removed, 2)
            self.assertFalse((hq_dir / "headquarters-2026-05-15T100000Z.html").exists())
            self.assertFalse((hq_dir / "headquarters-2026-05-16T100000Z.html").exists())
            self.assertTrue((hq_dir / "headquarters-2026-05-17T100000Z.html").exists())
            self.assertTrue((hq_dir / "headquarters-2026-05-18T100000Z.html").exists())
            self.assertTrue((hq_dir / "latest.html").exists())
            self.assertTrue((hq_dir / "latest.md").exists())


if __name__ == "__main__":
    unittest.main()
