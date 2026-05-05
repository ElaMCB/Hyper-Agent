import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from src.shadow.adapters.gmail import _header_map, _parse_internal_date
from src.shadow.capabilities.brief import get_brief_bullets_and_focus
from src.shadow.capabilities.headquarters import render_headquarters_html
from src.shadow.models import CapacityAllocation, MailMessage, Snapshot, StrategySignal, TeamMember
from src.shadow.snapshot import build_snapshot


class SnapshotRegressionTests(unittest.TestCase):
    def test_build_snapshot_loads_qe_files_and_records_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_dir = root / "exports"
            data_dir.mkdir()
            (data_dir / "team.json").write_text(
                json.dumps(
                    {
                        "members": [
                            {
                                "employee_id": "qa-1",
                                "name": "Avery",
                                "role": "Lead QE",
                                "skills": "api, automation, payments",
                                "vacation": True,
                                "vacation_until": "2026-05-10",
                                "morale": "amber",
                                "last_1_1": "2026-04-01",
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
                                "name": "Avery",
                                "app": "Checkout",
                                "sprint": "Sprint 42",
                                "allocation_pct": "75",
                                "note": "Release hardening",
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
                                "theme": "Release confidence",
                                "title": "Cut escaped defects",
                                "horizon": "Q2",
                                "priority": "P1",
                                "status": "On track",
                                "evidence": "quality-review",
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
                        "dir": "exports",
                        "load_defects": False,
                        "load_test_runs": False,
                        "load_team": True,
                        "load_allocations": True,
                        "load_strategy": True,
                    },
                    "gmail": {"enabled": False},
                },
            )

        self.assertEqual(["File: team (team.json)", "File: allocations (allocations.json)", "File: strategy (strategy.json)"], snapshot.sources)
        self.assertEqual("Avery", snapshot.team_members[0].name)
        self.assertEqual(["api", "automation", "payments"], snapshot.team_members[0].skills)
        self.assertTrue(snapshot.team_members[0].on_vacation)
        self.assertEqual(75, snapshot.capacity_allocations[0].focus_pct)
        self.assertEqual("Release confidence", snapshot.strategy_signals[0].pillar)

    def test_gmail_failures_are_notes_not_successful_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "secrets").mkdir()
            (root / "secrets" / "gmail_oauth_client.json").write_text("{}", encoding="utf-8")

            with patch(
                "src.shadow.snapshot.fetch_gmail_messages",
                return_value=([], ["Gmail: listing messages failed (quota exceeded)."]),
            ):
                snapshot = build_snapshot(
                    root,
                    {
                        "data": {"load_defects": False, "load_test_runs": False},
                        "gmail": {
                            "enabled": True,
                            "credentials_file": "secrets/gmail_oauth_client.json",
                        },
                    },
                )

        self.assertIn("Gmail: listing messages failed (quota exceeded).", snapshot.notes)
        self.assertNotIn("Gmail: connected (0 messages for this query)", snapshot.sources)
        self.assertEqual(
            ["(No sources — enable Gmail/ADO, load team/allocations/strategy in config, or add data/ files.)"],
            snapshot.sources,
        )


class GmailParsingRegressionTests(unittest.TestCase):
    def test_header_map_normalizes_names_and_internal_date_is_utc(self):
        headers = _header_map(
            {
                "headers": [
                    {"name": "Subject", "value": "Daily Risk"},
                    {"name": "FROM", "value": "qa@example.com"},
                    {"name": "", "value": "ignored"},
                ]
            }
        )

        self.assertEqual({"subject": "Daily Risk", "from": "qa@example.com"}, headers)
        self.assertEqual(
            datetime(2023, 11, 14, 22, 13, 20, tzinfo=timezone.utc),
            _parse_internal_date("1700000000000"),
        )
        self.assertIsNone(_parse_internal_date("not-a-timestamp"))


class BriefRegressionTests(unittest.TestCase):
    def test_qe_context_counts_toward_bullet_limit_and_sets_leadership_focus(self):
        snapshot = Snapshot(
            as_of=datetime(2026, 5, 5, 10, 0, tzinfo=timezone.utc),
            sources=["unit-test"],
            team_members=[
                TeamMember(
                    id="qa-1",
                    name="Avery",
                    on_vacation=True,
                    last_one_on_one=datetime(2026, 4, 1, tzinfo=timezone.utc),
                )
            ],
            capacity_allocations=[
                CapacityAllocation(
                    id="alloc-1",
                    person_id="qa-1",
                    app_name="Checkout",
                    sprint_label="Sprint 42",
                    focus_pct=75,
                )
            ],
            strategy_signals=[
                StrategySignal(
                    id="strategy-1",
                    pillar="Release confidence",
                    summary="Reduce escaped defects before launch",
                    priority="P0",
                )
            ],
        )

        bullets, suggested = get_brief_bullets_and_focus(
            snapshot,
            {"brief": {"include_qe_context": True, "max_qe_context_bullets": 3}},
            max_bullets=2,
        )

        self.assertEqual(2, len(bullets))
        self.assertEqual("QE team (file): 1 people, 1 flagged on vacation.", bullets[0])
        self.assertEqual(
            "1:1 hygiene: 1 member(s) past 21d or missing last 1:1 date.",
            bullets[1],
        )
        self.assertEqual(
            "Reconcile team capacity and sprint allocations with strategy signals; pick 1–2 leadership moves today.",
            suggested,
        )


class HeadquartersRegressionTests(unittest.TestCase):
    def test_headquarters_escapes_untrusted_mail_links_and_brief_content(self):
        snapshot = Snapshot(
            as_of=datetime(2026, 5, 5, 10, 0, tzinfo=timezone.utc),
            sources=["Gmail: 1 message(s)"],
            mail_messages=[
                MailMessage(
                    id="message-1234567890",
                    subject="<script>alert('subject')</script>",
                    from_addr='"QA" <qa@example.com>',
                    snippet="<img src=x onerror=alert(1)>",
                    internal_date=datetime(2026, 5, 5, 9, 0, tzinfo=timezone.utc),
                    is_unread=True,
                )
            ],
        )

        html = render_headquarters_html(
            snapshot,
            {
                "headquarters": {
                    "title": "HQ <Unsafe>",
                    "links": [{"label": "Risk <Board>", "url": "https://example.test/?q=<risk>&x=\"1\""}],
                    "show_qe_panels": False,
                }
            },
            full_brief_markdown="# Brief\n\n<script>alert('brief')</script>",
        )

        self.assertIn("HQ &lt;Unsafe&gt;", html)
        self.assertIn("Risk &lt;Board&gt;", html)
        self.assertIn("https://example.test/?q=&lt;risk&gt;&amp;x=&quot;1&quot;", html)
        self.assertIn("&lt;script&gt;alert(&#x27;subject&#x27;)&lt;/script&gt;", html)
        self.assertIn("&lt;img src=x onerror=alert(1)&gt;", html)
        self.assertIn("&lt;script&gt;alert(&#x27;brief&#x27;)&lt;/script&gt;", html)
        self.assertNotIn("<script>alert", html)
        self.assertNotIn("<img src=x", html)
        self.assertNotIn("QE team (file)</h2>", html)


if __name__ == "__main__":
    unittest.main()
