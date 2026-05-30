import html
import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


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
    TestRun,
)
from src.shadow.output.writer import prune_headquarters_archives
from src.shadow.snapshot import build_snapshot


class RecentRegressionCoverageTests(unittest.TestCase):
    def test_snapshot_loads_enabled_qe_files_with_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = root / "data"
            data.mkdir()
            (data / "defects.json").write_text(
                json.dumps({"defects": [{"key": "BUG-7", "summary": "Checkout failure"}]}),
                encoding="utf-8",
            )
            (data / "test_runs.json").write_text(
                json.dumps({"runs": [{"run_id": "RUN-1", "run_name": "Smoke", "Status": "Passed"}]}),
                encoding="utf-8",
            )
            (data / "team.json").write_text(
                json.dumps({"members": [{"employee_id": "qe-1", "name": "Avery", "skills": "api, mobile"}]}),
                encoding="utf-8",
            )
            (data / "allocations.json").write_text(
                json.dumps(
                    {
                        "assignments": [
                            {
                                "key": "alloc-1",
                                "person": "qe-1",
                                "name": "Avery",
                                "app": "Checkout",
                                "allocation_pct": "40",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            (data / "strategy.json").write_text(
                json.dumps({"signals": [{"key": "sig-1", "theme": "Reliability", "priority": "P0"}]}),
                encoding="utf-8",
            )

            snapshot = build_snapshot(
                root,
                {
                    "data": {
                        "dir": "data",
                        "load_team": True,
                        "load_allocations": True,
                        "load_strategy": True,
                    }
                },
            )

        self.assertEqual(["BUG-7"], [d.id for d in snapshot.defects])
        self.assertEqual(["RUN-1"], [r.id for r in snapshot.test_runs])
        self.assertEqual(["api", "mobile"], snapshot.team_members[0].skills)
        self.assertEqual(40, snapshot.capacity_allocations[0].focus_pct)
        self.assertEqual("Reliability", snapshot.strategy_signals[0].pillar)
        self.assertIn("File: team (team.json)", snapshot.sources)
        self.assertIn("File: allocations (allocations.json)", snapshot.sources)
        self.assertIn("File: strategy (strategy.json)", snapshot.sources)

    def test_brief_qe_context_uses_configured_budget_without_hiding_work_signals(self):
        snapshot = Snapshot(
            as_of=datetime(2026, 5, 30, tzinfo=timezone.utc),
            sources=["fixture"],
            defects=[Defect(id="BUG-1", title="Critical login breakage", severity="Critical", status="Open")],
            mail_messages=[
                MailMessage(
                    id="mail-1",
                    subject="Escalation from support",
                    from_addr="support@example.com",
                    snippet="",
                    is_unread=True,
                )
            ],
            team_members=[TeamMember(id="qe-1", name="Avery")],
            capacity_allocations=[
                CapacityAllocation(id="alloc-1", person_id="qe-1", person_name="Avery", app_name="Checkout")
            ],
            strategy_signals=[
                StrategySignal(id="sig-1", pillar="Reliability", summary="Protect checkout", priority="P0")
            ],
        )

        bullets, suggested = get_brief_bullets_and_focus(
            snapshot,
            {"brief": {"include_qe_context": True, "max_bullets": 3, "max_qe_context_bullets": 2}},
        )

        self.assertEqual(3, len(bullets))
        self.assertTrue(bullets[0].startswith("QE team (file):"))
        self.assertTrue(bullets[1].startswith("Allocations:"))
        self.assertTrue(bullets[2].startswith("Gmail:"))
        self.assertEqual(
            "Balance people/capacity/strategy context with inbox and execution signals for today.",
            suggested,
        )

    def test_headquarters_escapes_user_fields_and_enforces_row_caps(self):
        unsafe = '<img src=x onerror="alert(1)">'
        snapshot = Snapshot(
            as_of=datetime(2026, 5, 30, 10, 0, tzinfo=timezone.utc),
            sources=[f"source {unsafe}"],
            notes=[f"note {unsafe}"],
            defects=[
                Defect(id="BUG-1", title=f"first {unsafe}", severity="High", status="Open"),
                Defect(id="BUG-2", title="second should be capped", severity="Low", status="Open"),
            ],
            test_runs=[
                TestRun(id="RUN-1", name=f"run {unsafe}", status="Passed", total=1, passed=1, failed=0)
            ],
            mail_messages=[
                MailMessage(
                    id="mail-1",
                    subject=f"mail {unsafe}",
                    from_addr="qa@example.com",
                    snippet=f"snippet {unsafe}",
                    internal_date=datetime(2026, 5, 30, tzinfo=timezone.utc),
                ),
                MailMessage(id="mail-2", subject="second mail should be capped", from_addr="", snippet=""),
            ],
            team_members=[TeamMember(id="qe-1", name=f"Avery {unsafe}", role="Lead")],
            capacity_allocations=[
                CapacityAllocation(
                    id="alloc-1",
                    person_id="qe-1",
                    person_name=f"Avery {unsafe}",
                    app_name="Checkout",
                    commitment_note=f"note {unsafe}",
                )
            ],
            strategy_signals=[
                StrategySignal(id="sig-1", pillar=f"Reliability {unsafe}", summary=f"summary {unsafe}")
            ],
        )

        rendered = render_headquarters_html(
            snapshot,
            {
                "headquarters": {
                    "title": f"HQ {unsafe}",
                    "links": [{"label": f"Docs {unsafe}", "url": 'https://example.test/?q="bad"'}],
                    "max_mail_rows": 1,
                },
                "brief": {"max_bullets": 5},
            },
            full_brief_markdown=f"# Brief\n\n{unsafe}",
            max_defect_rows=1,
        )

        self.assertNotIn(unsafe, rendered)
        self.assertIn(html.escape(unsafe), rendered)
        self.assertIn("first", rendered)
        self.assertNotIn("second should be capped", rendered)
        self.assertIn("mail", rendered)
        self.assertNotIn("second mail should be capped", rendered)
        self.assertIn("Showing 1 of 2.", rendered)
        self.assertIn("https://example.test/?q=&quot;bad&quot;", rendered)

    def test_gmail_helpers_normalize_headers_and_reject_bad_internal_dates(self):
        headers = _header_map(
            {
                "headers": [
                    {"name": "Subject", "value": "Daily status"},
                    {"name": "FROM", "value": "lead@example.com"},
                    {"name": "", "value": "ignored"},
                ]
            }
        )

        self.assertEqual({"subject": "Daily status", "from": "lead@example.com"}, headers)
        self.assertEqual(
            datetime(2026, 5, 30, 10, 0, tzinfo=timezone.utc),
            _parse_internal_date("1780135200000"),
        )
        self.assertIsNone(_parse_internal_date("not-a-timestamp"))
        self.assertIsNone(_parse_internal_date(None))

    def test_prune_headquarters_archives_keeps_latest_by_stamp_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            hq = root / "output" / "headquarters"
            hq.mkdir(parents=True)
            for name in [
                "headquarters-2026-05-28T100000Z.html",
                "headquarters-2026-05-29T100000Z.html",
                "headquarters-2026-05-30T100000Z.html",
                "latest.html",
                "latest.md",
                "headquarters-notes.txt",
            ]:
                (hq / name).write_text(name, encoding="utf-8")

            removed = prune_headquarters_archives(root, "output/headquarters", max_keep=2)

            remaining = {p.name for p in hq.iterdir()}
        self.assertEqual(1, removed)
        self.assertNotIn("headquarters-2026-05-28T100000Z.html", remaining)
        self.assertIn("headquarters-2026-05-29T100000Z.html", remaining)
        self.assertIn("headquarters-2026-05-30T100000Z.html", remaining)
        self.assertIn("latest.html", remaining)
        self.assertIn("latest.md", remaining)
        self.assertIn("headquarters-notes.txt", remaining)


if __name__ == "__main__":
    unittest.main()
