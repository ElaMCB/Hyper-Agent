import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from src.shadow.adapters.gmail import _header_map, _parse_internal_date
from src.shadow.capabilities.brief import get_brief_bullets_and_focus
from src.shadow.capabilities.headquarters import render_headquarters_html
from src.shadow.models import (
    CapacityAllocation,
    Defect,
    MailMessage,
    Snapshot,
    StrategySignal,
    TeamMember,
)
from src.shadow.snapshot import build_snapshot


class RecentRegressionCoverageTests(unittest.TestCase):
    def test_build_snapshot_loads_enabled_qe_files_with_sources(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_dir = root / "data"
            data_dir.mkdir()
            (data_dir / "team.json").write_text(
                json.dumps(
                    {
                        "members": [
                            {
                                "id": "qe-1",
                                "name": "Rae",
                                "role": "QE Lead",
                                "skills": "api, data, automation",
                                "morale": "amber",
                                "last_1_1": "2026-05-01",
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
                                "id": "alloc-1",
                                "person": "qe-1",
                                "app": "Payments",
                                "sprint": "S42",
                                "pct": "75",
                                "note": "critical path",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            (data_dir / "strategy.json").write_text(
                json.dumps(
                    {
                        "signals": [
                            {
                                "key": "strat-1",
                                "theme": "Release confidence",
                                "title": "Automate the checkout smoke path",
                                "priority": "P1",
                                "horizon": "Now",
                                "evidence": "QE-123",
                            }
                        ]
                    }
                ),
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

        self.assertEqual([], snapshot.defects)
        self.assertEqual([], snapshot.test_runs)
        self.assertEqual(1, len(snapshot.team_members))
        self.assertEqual(["api", "data", "automation"], snapshot.team_members[0].skills)
        self.assertEqual("amber", snapshot.team_members[0].morale_flag)
        self.assertEqual(datetime(2026, 5, 1), snapshot.team_members[0].last_one_on_one)
        self.assertEqual(75, snapshot.capacity_allocations[0].focus_pct)
        self.assertEqual("Release confidence", snapshot.strategy_signals[0].pillar)
        self.assertEqual(
            [
                "File: team (team.json)",
                "File: allocations (allocations.json)",
                "File: strategy (strategy.json)",
            ],
            snapshot.sources,
        )

    def test_qe_context_brief_prioritizes_leadership_signals_without_work_data(self):
        snapshot = Snapshot(
            as_of=datetime(2026, 5, 22, tzinfo=timezone.utc),
            sources=["unit"],
            team_members=[
                TeamMember(
                    id="qe-1",
                    name="Rae",
                    on_vacation=True,
                    last_one_on_one=datetime(2026, 4, 1, tzinfo=timezone.utc),
                ),
                TeamMember(id="qe-2", name="Morgan"),
            ],
            capacity_allocations=[
                CapacityAllocation(
                    id="a1",
                    person_id="qe-1",
                    person_name="Rae",
                    app_name="Payments",
                    sprint_label="S42",
                    focus_pct=50,
                )
            ],
            strategy_signals=[
                StrategySignal(
                    id="s1",
                    pillar="Release confidence",
                    priority="P0",
                    summary="Unblock go/no-go automation evidence",
                )
            ],
        )

        bullets, focus = get_brief_bullets_and_focus(
            snapshot,
            {
                "brief": {
                    "include_qe_context": True,
                    "max_bullets": 4,
                    "max_qe_context_bullets": 4,
                },
                "people": {"one_on_one_stale_days": 21},
            },
        )

        self.assertEqual(
            [
                "QE team (file): 2 people, 1 flagged on vacation.",
                "1:1 hygiene: 2 member(s) past 21d or missing last 1:1 date.",
                "Allocations: 1 row(s) across 1 app bucket(s).",
                "Strategy file: 1 signal(s); top priority line \u2014 **Release confidence** (P0): Unblock go/no-go automation evidence",
            ],
            bullets,
        )
        self.assertEqual(
            "Reconcile team capacity and sprint allocations with strategy signals; pick 1\u20132 leadership moves today.",
            focus,
        )

    def test_gmail_metadata_helpers_normalize_headers_and_internal_dates(self):
        headers = _header_map(
            {
                "headers": [
                    {"name": "Subject", "value": "Morning update"},
                    {"name": "FROM", "value": "lead@example.com"},
                    {"name": "", "value": "ignored"},
                    {"name": "Date", "value": "Fri, 22 May 2026 10:00:00 +0000"},
                ]
            }
        )

        self.assertEqual(
            {
                "subject": "Morning update",
                "from": "lead@example.com",
                "date": "Fri, 22 May 2026 10:00:00 +0000",
            },
            headers,
        )
        self.assertEqual(
            datetime(2023, 11, 14, 22, 13, 20, tzinfo=timezone.utc),
            _parse_internal_date("1700000000000"),
        )
        self.assertIsNone(_parse_internal_date(None))
        self.assertIsNone(_parse_internal_date("not-a-timestamp"))

    def test_headquarters_html_escapes_private_rows_and_respects_mail_cap(self):
        snapshot = Snapshot(
            as_of=datetime(2026, 5, 22, 10, 0, tzinfo=timezone.utc),
            sources=["File: <sensitive>"],
            notes=["Gmail: token <refresh> failed"],
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
                    id="message-1234567890",
                    subject="<img src=x onerror=alert(1)>",
                    from_addr="lead@example.com",
                    snippet="please review <b>today</b>",
                    internal_date=datetime(2026, 5, 22, 9, 30, tzinfo=timezone.utc),
                    is_unread=True,
                ),
                MailMessage(
                    id="message-2",
                    subject="Hidden by cap",
                    from_addr="other@example.com",
                    snippet="not rendered",
                ),
            ],
        )

        page = render_headquarters_html(
            snapshot,
            {
                "brief": {"max_bullets": 2},
                "headquarters": {
                    "title": "Shadow <HQ>",
                    "show_qe_panels": False,
                    "max_mail_rows": 1,
                    "links": [
                        {
                            "label": "Dashboard <prod>",
                            "url": 'https://example.test/dashboard?a="b"&c=<d>',
                        }
                    ],
                }
            },
            full_brief_markdown="# Brief\n<script>alert('brief')</script>",
        )

        self.assertNotIn("<script>", page)
        self.assertNotIn("<img src=x", page)
        self.assertNotIn("Hidden by cap", page)
        self.assertNotIn("QE team (file)", page)
        self.assertIn("Shadow &lt;HQ&gt;", page)
        self.assertIn("&lt;script&gt;alert(&#x27;defect&#x27;)&lt;/script&gt;", page)
        self.assertIn("&lt;img src=x onerror=alert(1)&gt;", page)
        self.assertIn("please review &lt;b&gt;today&lt;/b&gt;", page)
        self.assertIn("File: &lt;sensitive&gt;", page)
        self.assertIn("Gmail: token &lt;refresh&gt; failed", page)
        self.assertIn("Showing 1 of 2.", page)
        self.assertIn("Dashboard &lt;prod&gt;", page)
        self.assertIn(
            "https://example.test/dashboard?a=&quot;b&quot;&amp;c=&lt;d&gt;",
            page,
        )


if __name__ == "__main__":
    unittest.main()
