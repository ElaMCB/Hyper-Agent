import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.shadow.adapters.file_export import load_allocations_from_json, load_team_from_json
from src.shadow.capabilities.brief import get_brief_bullets_and_focus
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
from src.shadow.snapshot import build_snapshot


class RecentShadowRegressionTests(unittest.TestCase):
    def test_qe_file_exports_preserve_false_booleans_and_zero_percentages(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            team_path = root / "team.json"
            team_path.write_text(
                json.dumps(
                    {
                        "members": [
                            {
                                "id": "u1",
                                "name": "No Leave",
                                "skills": "automation, api, ",
                                "on_vacation": "false",
                            },
                            {
                                "employee_id": "u2",
                                "name": "Also Here",
                                "vacation": "0",
                            },
                            {
                                "id": "u3",
                                "name": "Away",
                                "skills": ["perf", 7],
                                "on_vacation": "yes",
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )
            allocations_path = root / "allocations.json"
            allocations_path.write_text(
                json.dumps(
                    {
                        "assignments": [
                            {"id": "a1", "person": "u1", "focus_pct": 0},
                            {"id": "a2", "person": "u2", "pct": "0"},
                            {"id": "a3", "person": "u3", "allocation_pct": "n/a"},
                            {"id": "a4", "person": "u4", "focus_pct": ""},
                        ]
                    }
                ),
                encoding="utf-8",
            )

            team = load_team_from_json(team_path)
            allocations = load_allocations_from_json(allocations_path)

        self.assertEqual([False, False, True], [m.on_vacation for m in team])
        self.assertEqual(["automation", "api"], team[0].skills)
        self.assertEqual(["perf", "7"], team[2].skills)
        self.assertEqual([0, 0, None, None], [a.focus_pct for a in allocations])

    def test_build_snapshot_loads_qe_files_and_keeps_gmail_failures_in_notes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_dir = root / "data"
            data_dir.mkdir()
            (data_dir / "team.json").write_text(
                json.dumps({"team": [{"id": "u1", "name": "QE Lead", "on_vacation": "false"}]}),
                encoding="utf-8",
            )
            (data_dir / "allocations.json").write_text(
                json.dumps({"allocations": [{"id": "a1", "person_id": "u1", "app_name": "Portal", "focus_pct": 0}]}),
                encoding="utf-8",
            )
            (data_dir / "strategy.json").write_text(
                json.dumps({"signals": [{"id": "s1", "pillar": "Release", "priority": "P0", "summary": "Gate risk"}]}),
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
                "gmail": {
                    "enabled": True,
                    "credentials_file": "secrets/missing_client.json",
                    "max_messages": 5,
                },
            }

            snapshot = build_snapshot(root, config)

        self.assertEqual(["QE Lead"], [m.name for m in snapshot.team_members])
        self.assertEqual([0], [a.focus_pct for a in snapshot.capacity_allocations])
        self.assertEqual(["Release"], [s.pillar for s in snapshot.strategy_signals])
        self.assertIn("File: team (team.json)", snapshot.sources)
        self.assertIn("File: allocations (allocations.json)", snapshot.sources)
        self.assertIn("File: strategy (strategy.json)", snapshot.sources)
        self.assertFalse(any(source.startswith("Gmail: connected") for source in snapshot.sources))
        self.assertTrue(any("OAuth client JSON not found" in note for note in snapshot.notes))

    def test_brief_keeps_qe_context_and_focus_when_mail_work_and_qe_are_present(self):
        as_of = datetime(2026, 6, 7, tzinfo=timezone.utc)
        snapshot = Snapshot(
            as_of=as_of,
            sources=["test"],
            defects=[Defect(id="D1", title="Checkout blocks release", severity="High", status="Open")],
            mail_messages=[
                MailMessage(
                    id="m1",
                    subject="Steering asks for status",
                    from_addr="lead@example.com",
                    snippet="Need the quality position",
                    is_unread=True,
                )
            ],
            team_members=[
                TeamMember(id="u1", name="Alex", on_vacation=False, last_one_on_one=as_of - timedelta(days=1))
            ],
            capacity_allocations=[
                CapacityAllocation(id="a1", person_id="u1", person_name="Alex", app_name="Portal", focus_pct=60)
            ],
            strategy_signals=[
                StrategySignal(id="s1", pillar="Release readiness", priority="P0", summary="Stabilize critical path")
            ],
        )
        config = {"brief": {"include_qe_context": True, "max_qe_context_bullets": 2}}

        bullets, focus = get_brief_bullets_and_focus(snapshot, config, max_bullets=3)

        self.assertEqual(3, len(bullets))
        self.assertTrue(bullets[0].startswith("QE team (file): 1 people"))
        self.assertTrue(bullets[1].startswith("Allocations: 1 row(s)"))
        self.assertEqual("Gmail: 1 in view, 1 unread.", bullets[2])
        self.assertEqual(
            "Balance people/capacity/strategy context with inbox and execution signals for today.",
            focus,
        )

    def test_qe_pack_renders_stale_capacity_overallocation_zero_pct_and_strategy_order(self):
        as_of = datetime(2026, 6, 7, tzinfo=timezone.utc)
        snapshot = Snapshot(
            as_of=as_of,
            sources=["test"],
            team_members=[
                TeamMember(
                    id="u1",
                    name="Alice",
                    role="SDET",
                    morale_flag="red",
                    last_one_on_one=as_of - timedelta(days=45),
                ),
                TeamMember(id="u2", name="Bob", role="QA", on_vacation=True),
            ],
            capacity_allocations=[
                CapacityAllocation(id="a1", person_id="u1", person_name="Alice", app_name="Portal", sprint_label="S6", focus_pct=70),
                CapacityAllocation(id="a2", person_id="u1", person_name="Alice", app_name="API", sprint_label="S6", focus_pct=40),
                CapacityAllocation(id="a3", person_id="u3", person_name="Zero Tester", app_name="Mobile", sprint_label="S6", focus_pct=0),
            ],
            strategy_signals=[
                StrategySignal(id="s2", pillar="Automation debt", priority="P2", horizon="Q3", summary="Reduce flaky tests"),
                StrategySignal(id="s1", pillar="Release readiness", priority="P0", horizon="Now", summary="Guard go-live"),
            ],
        )

        markdown = render_qe_subagent_pack(snapshot, {"people": {"one_on_one_stale_days": 21}})

        self.assertIn("**Morale watch (amber/red):** Alice", markdown)
        self.assertIn("**1:1 stale (>21d or missing):** Alice, Bob", markdown)
        self.assertIn("**Warning:** focus % sums > 100 for:", markdown)
        self.assertIn("- u1 @ S6", markdown)
        self.assertIn("- **Zero Tester** — 0% · sprint `S6`", markdown)
        self.assertLess(
            markdown.index("## Release readiness — `P0`"),
            markdown.index("## Automation debt — `P2`"),
        )

    def test_headquarters_html_escapes_free_text_from_gmail_qe_and_full_brief(self):
        snapshot = Snapshot(
            as_of=datetime(2026, 6, 7, tzinfo=timezone.utc),
            sources=["File: <data>"],
            mail_messages=[
                MailMessage(
                    id="message-with-long-id",
                    subject="<script>alert('mail')</script>",
                    from_addr="Bad <sender>",
                    snippet="snippet <img src=x onerror=alert(1)>",
                    is_unread=True,
                )
            ],
            team_members=[TeamMember(id="u1", name="<b>Alice</b>", role="QA <Lead>")],
            capacity_allocations=[
                CapacityAllocation(
                    id="a1",
                    person_id="u1",
                    person_name="<Alice>",
                    app_name="Portal <core>",
                    sprint_label="S6",
                    focus_pct=25,
                    commitment_note="keep | markdown safe <now>",
                )
            ],
            strategy_signals=[
                StrategySignal(
                    id="s1",
                    pillar="<Release>",
                    priority="P0",
                    horizon="Now",
                    status="Watch",
                    summary="<ship> only when ready",
                    evidence_ref="https://example.invalid/?x=<y>",
                )
            ],
        )

        html = render_headquarters_html(
            snapshot,
            {"brief": {"max_bullets": 3}, "headquarters": {"title": "<HQ>"}},
            full_brief_markdown="Full brief says <do not render>",
        )

        self.assertNotIn("<script>alert('mail')</script>", html)
        self.assertNotIn("<b>Alice</b>", html)
        self.assertNotIn("Full brief says <do not render>", html)
        self.assertIn("&lt;script&gt;alert(&#x27;mail&#x27;)&lt;/script&gt;", html)
        self.assertIn("&lt;b&gt;Alice&lt;/b&gt;", html)
        self.assertIn("Full brief says &lt;do not render&gt;", html)


if __name__ == "__main__":
    unittest.main()
