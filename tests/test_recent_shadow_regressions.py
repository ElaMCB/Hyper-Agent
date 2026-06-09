import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from src.shadow.adapters.file_export import load_allocations_from_json, load_team_from_json
from src.shadow.capabilities.headquarters import render_headquarters_html
from src.shadow.models import CapacityAllocation, MailMessage, Snapshot, StrategySignal, TeamMember
from src.shadow.snapshot import build_snapshot


class FileExportParsingTests(unittest.TestCase):
    def test_team_loader_coerces_string_booleans_and_skills(self):
        with TemporaryDirectory() as tmp:
            team_path = Path(tmp) / "team.json"
            team_path.write_text(
                json.dumps(
                    {
                        "members": [
                            {
                                "id": "e1",
                                "name": "Ava",
                                "skills": "automation, api, release",
                                "on_vacation": "false",
                                "last_1_1": "2026-06-01",
                            },
                            {
                                "employee_id": "e2",
                                "name": "Bo",
                                "skills": ["mobile", "perf"],
                                "vacation": "yes",
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )

            members = load_team_from_json(team_path)

        self.assertEqual(["automation", "api", "release"], members[0].skills)
        self.assertFalse(members[0].on_vacation)
        self.assertEqual(datetime(2026, 6, 1), members[0].last_one_on_one)
        self.assertEqual(["mobile", "perf"], members[1].skills)
        self.assertTrue(members[1].on_vacation)

    def test_allocation_loader_preserves_zero_and_falls_back_for_invalid_percentages(self):
        with TemporaryDirectory() as tmp:
            allocation_path = Path(tmp) / "allocations.json"
            allocation_path.write_text(
                json.dumps(
                    {
                        "assignments": [
                            {"id": "a1", "person": "e1", "focus_pct": 0},
                            {"id": "a2", "person": "e1", "pct": "0"},
                            {"id": "a3", "person": "e2", "allocation_pct": " "},
                            {"id": "a4", "person": "e2", "pct": "not-a-number"},
                        ]
                    }
                ),
                encoding="utf-8",
            )

            allocations = load_allocations_from_json(allocation_path)

        self.assertEqual([0, 0, None, None], [a.focus_pct for a in allocations])


class SnapshotProvenanceTests(unittest.TestCase):
    def test_build_snapshot_loads_qe_files_and_records_sources(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = root / "data"
            data.mkdir()
            (data / "team.json").write_text(
                json.dumps({"team": [{"id": "e1", "name": "Ava", "on_vacation": "false"}]}),
                encoding="utf-8",
            )
            (data / "allocations.json").write_text(
                json.dumps({"allocations": [{"id": "a1", "person_id": "e1", "focus_pct": 0}]}),
                encoding="utf-8",
            )
            (data / "strategy.json").write_text(
                json.dumps({"signals": [{"id": "s1", "pillar": "Reliability", "priority": "P0"}]}),
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

        self.assertEqual(1, len(snapshot.team_members))
        self.assertFalse(snapshot.team_members[0].on_vacation)
        self.assertEqual(0, snapshot.capacity_allocations[0].focus_pct)
        self.assertEqual(1, len(snapshot.strategy_signals))
        self.assertIn("File: team (team.json)", snapshot.sources)
        self.assertIn("File: allocations (allocations.json)", snapshot.sources)
        self.assertIn("File: strategy (strategy.json)", snapshot.sources)

    def test_gmail_failure_stays_in_notes_without_success_provenance(self):
        with TemporaryDirectory() as tmp, patch(
            "src.shadow.snapshot.fetch_gmail_messages",
            return_value=([], ["Gmail: listing messages failed (boom)."]),
        ):
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
                    "gmail": {"enabled": True},
                },
            )

        self.assertEqual(["Gmail: listing messages failed (boom)."], snapshot.notes)
        self.assertTrue(snapshot.sources[0].startswith("(No sources"))
        self.assertNotIn("Gmail: connected", " ".join(snapshot.sources))


class HeadquartersRenderingTests(unittest.TestCase):
    def test_headquarters_escapes_sensitive_content_caps_mail_and_hides_qe_panels(self):
        snapshot = Snapshot(
            as_of=datetime(2026, 6, 9, 10, 0, tzinfo=timezone.utc),
            sources=["Source <b>"],
            notes=["Gmail note <script>alert(3)</script>"],
            mail_messages=[
                MailMessage(
                    id="mail-1",
                    subject="<script>alert(1)</script>",
                    from_addr='"ops@example.com"',
                    snippet="hello <b>world</b>",
                    is_unread=True,
                ),
                MailMessage(id="mail-2", subject="Second subject", from_addr="two@example.com", snippet=""),
            ],
            team_members=[
                TeamMember(
                    id="e1",
                    name="Eve <script>",
                    on_vacation=True,
                    performance_note="hidden <script>",
                )
            ],
            capacity_allocations=[
                CapacityAllocation(id="a1", person_id="e1", app_name="Payments", focus_pct=50)
            ],
            strategy_signals=[
                StrategySignal(id="s1", pillar="Trust", summary="hidden <script>", priority="P0")
            ],
        )

        html = render_headquarters_html(
            snapshot,
            {
                "brief": {"max_bullets": 4, "include_qe_context": False},
                "headquarters": {
                    "title": "HQ <unsafe>",
                    "max_mail_rows": 1,
                    "show_qe_panels": False,
                    "links": [{"label": "Docs <unsafe>", "url": "https://example.com/?q=<script>"}],
                },
            },
            full_brief_markdown="Brief <script>alert(2)</script>",
        )

        self.assertIn("HQ &lt;unsafe&gt;", html)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)
        self.assertIn("hello &lt;b&gt;world&lt;/b&gt;", html)
        self.assertIn("Gmail note &lt;script&gt;alert(3)&lt;/script&gt;", html)
        self.assertIn("Brief &lt;script&gt;alert(2)&lt;/script&gt;", html)
        self.assertIn("Showing 1 of 2.", html)
        self.assertNotIn("mail-2", html)
        self.assertNotIn("<script>", html)
        self.assertNotIn("QE team (file)", html)
        self.assertNotIn("hidden <script>", html)


if __name__ == "__main__":
    unittest.main()
