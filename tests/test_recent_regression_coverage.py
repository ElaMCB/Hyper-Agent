import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from src.shadow.adapters.file_export import load_allocations_from_json, load_team_from_json
from src.shadow.capabilities.headquarters import render_headquarters_html
from src.shadow.capabilities.people_capacity import render_people_capacity_md
from src.shadow.capabilities.qe_pack import render_qe_subagent_pack
from src.shadow.capabilities.resource_allocation import render_resource_allocation_md
from src.shadow.capabilities.strategy_lens import render_strategy_md
from src.shadow.models import CapacityAllocation, MailMessage, Snapshot, StrategySignal, TeamMember
from src.shadow.snapshot import build_snapshot


def write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


class FileExportParsingTests(unittest.TestCase):
    def test_team_loader_coerces_string_booleans_and_skill_shapes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "team.json"
            write_json(
                path,
                {
                    "team": [
                        {
                            "id": "qe-1",
                            "name": "Pat",
                            "skills": "API, UI, , Security",
                            "on_vacation": "false",
                        },
                        {
                            "id": "qe-2",
                            "name": "Sam",
                            "skills": ["Performance", 5],
                            "vacation": "YES",
                        },
                        {
                            "id": "qe-3",
                            "name": "Riley",
                            "on_vacation": "0",
                        },
                    ]
                },
            )

            members = load_team_from_json(path)

        self.assertEqual(["API", "UI", "Security"], members[0].skills)
        self.assertFalse(members[0].on_vacation)
        self.assertEqual(["Performance", "5"], members[1].skills)
        self.assertTrue(members[1].on_vacation)
        self.assertFalse(members[2].on_vacation)

    def test_allocation_loader_preserves_zero_and_uses_next_nonblank_alias(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "allocations.json"
            write_json(
                path,
                {
                    "allocations": [
                        {
                            "id": "a0",
                            "person_id": "qe-1",
                            "focus_pct": 0,
                            "pct": 75,
                        },
                        {
                            "id": "a1",
                            "person_id": "qe-2",
                            "focus_pct": "",
                            "pct": "25",
                        },
                        {
                            "id": "a2",
                            "person_id": "qe-3",
                            "allocation_pct": "not-a-number",
                        },
                    ]
                },
            )

            allocations = load_allocations_from_json(path)

        self.assertEqual(0, allocations[0].focus_pct)
        self.assertEqual(25, allocations[1].focus_pct)
        self.assertIsNone(allocations[2].focus_pct)


class SnapshotProvenanceTests(unittest.TestCase):
    def test_build_snapshot_loads_enabled_qe_files_and_gmail_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_dir = root / "data"
            data_dir.mkdir()
            write_json(data_dir / "team.json", [{"id": "qe-1", "name": "Pat"}])
            write_json(
                data_dir / "allocations.json",
                [{"id": "a1", "person_id": "qe-1", "app_name": "Checkout"}],
            )
            write_json(
                data_dir / "strategy.json",
                [{"id": "s1", "pillar": "Automation", "summary": "Cover the critical path"}],
            )
            mail = MailMessage(
                id="m1",
                subject="Launch follow-up",
                from_addr="lead@example.com",
                snippet="Please review",
                is_unread=True,
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
                "gmail": {"enabled": True, "max_messages": 5},
            }

            with patch("src.shadow.snapshot.fetch_gmail_messages", return_value=([mail], [])) as fetch:
                snapshot = build_snapshot(root, config)

        fetch.assert_called_once()
        self.assertEqual([], snapshot.defects)
        self.assertEqual([], snapshot.test_runs)
        self.assertEqual(1, len(snapshot.mail_messages))
        self.assertEqual(1, len(snapshot.team_members))
        self.assertEqual(1, len(snapshot.capacity_allocations))
        self.assertEqual(1, len(snapshot.strategy_signals))
        self.assertIn("Gmail: 1 message(s)", snapshot.sources)
        self.assertIn("File: team (team.json)", snapshot.sources)
        self.assertIn("File: allocations (allocations.json)", snapshot.sources)
        self.assertIn("File: strategy (strategy.json)", snapshot.sources)

    def test_build_snapshot_keeps_gmail_errors_in_notes_without_false_zero_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "data").mkdir()
            config = {
                "data": {
                    "dir": "data",
                    "load_defects": False,
                    "load_test_runs": False,
                    "load_team": False,
                    "load_allocations": False,
                    "load_strategy": False,
                },
                "gmail": {"enabled": True},
            }

            with patch(
                "src.shadow.snapshot.fetch_gmail_messages",
                return_value=([], ["Gmail: listing messages failed (boom)."]),
            ):
                snapshot = build_snapshot(root, config)

        self.assertIn("Gmail: listing messages failed (boom).", snapshot.notes)
        self.assertFalse(any(source.startswith("Gmail: connected") for source in snapshot.sources))


class QeCapabilityRenderingTests(unittest.TestCase):
    def test_qe_renderers_flag_stale_people_overallocations_and_priority_order(self):
        snapshot = Snapshot(
            as_of=datetime(2026, 5, 2, tzinfo=timezone.utc),
            team_members=[
                TeamMember(
                    id="qe-1",
                    name="Jordan Lee",
                    role="QE II",
                    morale_flag="amber",
                    last_one_on_one=datetime(2026, 3, 1),
                )
            ],
            capacity_allocations=[
                CapacityAllocation(
                    id="a1",
                    person_id="qe-1",
                    person_name="Jordan Lee",
                    app_name="Checkout",
                    sprint_label="2026-W18",
                    focus_pct=60,
                    commitment_note="Regression | contract tests",
                ),
                CapacityAllocation(
                    id="a2",
                    person_id="qe-1",
                    person_name="Jordan Lee",
                    app_name="Billing",
                    sprint_label="2026-W18",
                    focus_pct=50,
                ),
            ],
            strategy_signals=[
                StrategySignal(
                    id="s1",
                    pillar="Quality ownership",
                    summary="Clarify RACI",
                    priority="P1",
                    horizon="2026-H2",
                ),
                StrategySignal(
                    id="s2",
                    pillar="Test automation",
                    summary="Raise API coverage",
                    priority="P0",
                    horizon="FY26",
                ),
            ],
        )
        config = {"people": {"one_on_one_stale_days": 21}}

        people_md = render_people_capacity_md(snapshot, config)
        allocation_md = render_resource_allocation_md(snapshot, config)
        strategy_md = render_strategy_md(snapshot, config)
        qe_pack = render_qe_subagent_pack(snapshot, config)

        self.assertIn("Morale watch (amber/red): Jordan Lee", people_md)
        self.assertIn("1:1 stale (>21d or missing): Jordan Lee", people_md)
        self.assertIn("Warning:", allocation_md)
        self.assertIn("qe-1 @ 2026-W18", allocation_md)
        self.assertIn("Regression \\| contract tests", allocation_md)
        self.assertLess(strategy_md.index("## Test automation"), strategy_md.index("## Quality ownership"))
        self.assertIn("# People & capacity (QE)", qe_pack)
        self.assertIn("# Resource allocation (QE)", qe_pack)
        self.assertIn("# Strategy lens (QE)", qe_pack)

    def test_headquarters_escapes_mail_content_and_can_hide_qe_panels(self):
        snapshot = Snapshot(
            as_of=datetime(2026, 5, 2, tzinfo=timezone.utc),
            sources=["unit-test"],
            mail_messages=[
                MailMessage(
                    id="message-one-with-long-id",
                    subject='<P0> & "urgent"',
                    from_addr="Boss <boss@example.com>",
                    snippet="Use <script>alert(1)</script> & confirm",
                    is_unread=True,
                ),
                MailMessage(
                    id="message-two",
                    subject="Overflow",
                    from_addr="peer@example.com",
                    snippet="Hidden by cap",
                ),
            ],
            team_members=[TeamMember(id="qe-1", name="Pat")],
        )
        html = render_headquarters_html(
            snapshot,
            {"headquarters": {"show_qe_panels": False, "max_mail_rows": 1}, "brief": {}},
            full_brief_markdown='Brief with <unsafe> & "quotes"',
        )

        self.assertIn("&lt;P0&gt; &amp; &quot;urgent&quot;", html)
        self.assertIn("Boss &lt;boss@example.com&gt;", html)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt; &amp; confirm", html)
        self.assertIn("Showing 1 of 2.", html)
        self.assertNotIn("QE team (file)", html)
        self.assertNotIn('Brief with <unsafe> & "quotes"', html)


if __name__ == "__main__":
    unittest.main()
