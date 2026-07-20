import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from src.shadow.adapters.file_export import load_allocations_from_json, load_team_from_json
from src.shadow.capabilities.brief import get_brief_bullets_and_focus
from src.shadow.capabilities.people_capacity import (
    people_capacity_summary_bullets,
    render_people_capacity_md,
)
from src.shadow.capabilities.resource_allocation import render_resource_allocation_md
from src.shadow.models import (
    CapacityAllocation,
    Defect,
    MailMessage,
    Snapshot,
    StrategySignal,
    TeamMember,
    TestRun,
)
from src.shadow.snapshot import build_snapshot


FIXED_AS_OF = datetime(2026, 5, 29, 10, 0, tzinfo=timezone.utc)


def make_snapshot(**overrides):
    values = {
        "as_of": FIXED_AS_OF,
        "sources": ["unit-test"],
        "defects": [],
        "test_runs": [],
        "mail_messages": [],
        "team_members": [],
        "capacity_allocations": [],
        "strategy_signals": [],
        "notes": [],
    }
    values.update(overrides)
    return Snapshot(**values)


class GmailSnapshotProvenanceTests(unittest.TestCase):
    def test_failed_gmail_collection_stays_in_notes_not_connected_sources(self):
        gmail_note = "Gmail: listing messages failed (quota exceeded)."
        config = {
            "data": {
                "load_defects": False,
                "load_test_runs": False,
                "load_team": False,
                "load_allocations": False,
                "load_strategy": False,
            },
            "gmail": {"enabled": True},
        }

        with tempfile.TemporaryDirectory() as tmp:
            with patch("src.shadow.snapshot.fetch_gmail_messages", return_value=([], [gmail_note])):
                snapshot = build_snapshot(Path(tmp), config)

        self.assertEqual([], snapshot.mail_messages)
        self.assertIn(gmail_note, snapshot.notes)
        self.assertFalse(any(source.startswith("Gmail: connected") for source in snapshot.sources))

    def test_empty_successful_gmail_collection_records_connected_source(self):
        config = {
            "data": {
                "load_defects": False,
                "load_test_runs": False,
                "load_team": False,
                "load_allocations": False,
                "load_strategy": False,
            },
            "gmail": {"enabled": True},
        }

        with tempfile.TemporaryDirectory() as tmp:
            with patch("src.shadow.snapshot.fetch_gmail_messages", return_value=([], [])):
                snapshot = build_snapshot(Path(tmp), config)

        self.assertEqual([], snapshot.notes)
        self.assertIn("Gmail: connected (0 messages for this query)", snapshot.sources)


class FileExportCoercionTests(unittest.TestCase):
    def test_team_loader_parses_string_booleans_and_skill_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "team.json"
            path.write_text(
                json.dumps(
                    {
                        "team": [
                            {
                                "id": "qe-1",
                                "name": "Avery",
                                "skills": "api, automation, accessibility",
                                "on_vacation": "false",
                            },
                            {
                                "id": "qe-2",
                                "name": "Blair",
                                "skills": ["mobile", "payments"],
                                "vacation": "yes",
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )

            team = load_team_from_json(path)

        self.assertFalse(team[0].on_vacation)
        self.assertEqual(["api", "automation", "accessibility"], team[0].skills)
        self.assertTrue(team[1].on_vacation)
        self.assertEqual(["mobile", "payments"], team[1].skills)

    def test_allocation_loader_preserves_explicit_zero_percentage(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "allocations.json"
            path.write_text(
                json.dumps(
                    {
                        "allocations": [
                            {
                                "id": "alloc-1",
                                "person_id": "qe-1",
                                "focus_pct": 0,
                                "allocation_pct": 75,
                            },
                            {
                                "id": "alloc-2",
                                "person_id": "qe-2",
                                "pct": "25",
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )

            allocations = load_allocations_from_json(path)

        self.assertEqual(0, allocations[0].focus_pct)
        self.assertEqual(25, allocations[1].focus_pct)


class BriefSummaryTests(unittest.TestCase):
    def test_brief_respects_qe_context_budget_and_focus(self):
        snapshot = make_snapshot(
            mail_messages=[
                MailMessage(
                    id="m1",
                    subject="Escalation from product",
                    from_addr="pm@example.com",
                    snippet="Need a call",
                    is_unread=True,
                )
            ],
            defects=[
                Defect(
                    id="BUG-1",
                    title="Checkout failure blocks release",
                    severity="High",
                    status="Open",
                )
            ],
            test_runs=[TestRun(id="run-1", name="Nightly smoke", status="Failed", total=10, passed=9, failed=1)],
            team_members=[
                TeamMember(
                    id="qe-1",
                    name="Avery",
                    on_vacation=True,
                    last_one_on_one=FIXED_AS_OF - timedelta(days=30),
                )
            ],
            capacity_allocations=[
                CapacityAllocation(
                    id="alloc-1",
                    person_id="qe-1",
                    person_name="Avery",
                    app_name="Checkout",
                    sprint_label="Sprint 12",
                    focus_pct=80,
                )
            ],
            strategy_signals=[
                StrategySignal(
                    id="strat-1",
                    pillar="Release confidence",
                    summary="Reduce escaped defects",
                    priority="P0",
                )
            ],
        )
        config = {"brief": {"include_qe_context": True, "max_qe_context_bullets": 2}}

        bullets, focus = get_brief_bullets_and_focus(snapshot, config, max_bullets=5)

        self.assertLessEqual(len(bullets), 5)
        self.assertEqual("QE team (file): 1 people, 1 flagged on vacation.", bullets[0])
        self.assertEqual(
            "1:1 hygiene: 1 member(s) past 21d or missing last 1:1 date.",
            bullets[1],
        )
        self.assertIn("Gmail: 1 in view, 1 unread.", bullets)
        self.assertEqual(
            "Balance people/capacity/strategy context with inbox and execution signals for today.",
            focus,
        )

    def test_mail_only_brief_points_focus_to_inbox_triage(self):
        snapshot = make_snapshot(
            mail_messages=[
                MailMessage(
                    id="m1",
                    subject="Please review today's launch checklist",
                    from_addr="lead@example.com",
                    snippet="Checklist attached",
                    is_unread=True,
                ),
                MailMessage(
                    id="m2",
                    subject="FYI",
                    from_addr="ops@example.com",
                    snippet="No action",
                    is_unread=False,
                ),
            ],
        )

        bullets, focus = get_brief_bullets_and_focus(snapshot, {}, max_bullets=3)

        self.assertEqual("Gmail: 2 in view, 1 unread.", bullets[0])
        self.assertEqual(
            "Triage unread Gmail; reply, archive, or snooze so nothing important slips.",
            focus,
        )


class QESignalTests(unittest.TestCase):
    def test_resource_allocation_warns_only_when_person_sprint_exceeds_capacity(self):
        over_snapshot = make_snapshot(
            capacity_allocations=[
                CapacityAllocation(
                    id="a1",
                    person_id="qe-1",
                    person_name="Avery",
                    app_name="Checkout",
                    sprint_label="Sprint 12",
                    focus_pct=70,
                ),
                CapacityAllocation(
                    id="a2",
                    person_id="qe-1",
                    person_name="Avery",
                    app_name="Payments",
                    sprint_label="Sprint 12",
                    focus_pct=40,
                ),
            ]
        )
        exact_snapshot = make_snapshot(
            capacity_allocations=[
                CapacityAllocation(
                    id="a1",
                    person_id="qe-1",
                    person_name="Avery",
                    app_name="Checkout",
                    sprint_label="Sprint 12",
                    focus_pct=60,
                ),
                CapacityAllocation(
                    id="a2",
                    person_id="qe-1",
                    person_name="Avery",
                    app_name="Payments",
                    sprint_label="Sprint 12",
                    focus_pct=40,
                ),
            ]
        )

        over_md = render_resource_allocation_md(over_snapshot, {})
        exact_md = render_resource_allocation_md(exact_snapshot, {})

        self.assertIn("**Warning:** focus % sums > 100 for:", over_md)
        self.assertIn("qe-1 @ Sprint 12", over_md)
        self.assertNotIn("**Warning:** focus % sums > 100 for:", exact_md)

    def test_people_capacity_flags_stale_and_missing_one_on_ones(self):
        snapshot = make_snapshot(
            team_members=[
                TeamMember(
                    id="qe-1",
                    name="Avery",
                    morale_flag="red",
                    last_one_on_one=FIXED_AS_OF - timedelta(days=30),
                ),
                TeamMember(id="qe-2", name="Blair", last_one_on_one=None),
                TeamMember(
                    id="qe-3",
                    name="Casey",
                    last_one_on_one=FIXED_AS_OF - timedelta(days=7),
                ),
            ]
        )
        config = {"people": {"one_on_one_stale_days": 21}}

        md = render_people_capacity_md(snapshot, config)
        bullets = people_capacity_summary_bullets(snapshot, config)

        self.assertIn("**Morale watch (amber/red):** Avery", md)
        self.assertIn("**1:1 stale (>21d or missing):** Avery, Blair", md)
        self.assertIn(
            "1:1 hygiene: 2 member(s) past 21d or missing last 1:1 date.",
            bullets,
        )


if __name__ == "__main__":
    unittest.main()
