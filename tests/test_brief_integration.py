import unittest
from datetime import datetime, timezone
from pathlib import Path

from src.shadow.capabilities.brief import get_brief_bullets_and_focus, render_brief
from src.shadow.models import (
    CapacityAllocation,
    Defect,
    MailMessage,
    Snapshot,
    StrategySignal,
    TeamMember,
    TestRun,
)


def _snapshot(**kwargs):
    defaults = {
        "as_of": datetime(2026, 5, 19, 10, 0, tzinfo=timezone.utc),
        "sources": ["unit-test"],
    }
    defaults.update(kwargs)
    return Snapshot(**defaults)


class BriefIntegrationTests(unittest.TestCase):
    def test_mail_consumes_bullet_budget_before_work_items(self):
        long_subject = "Important release coordination " + ("x" * 80)
        snapshot = _snapshot(
            mail_messages=[
                MailMessage("m1", long_subject, "a@example.com", "", is_unread=True),
                MailMessage("m2", "Second", "b@example.com", "", is_unread=False),
                MailMessage("m3", "Third", "c@example.com", "", is_unread=False),
            ],
            defects=[
                Defect("D-1", "Critical checkout bug", "Critical", "Open"),
            ],
        )

        bullets, focus = get_brief_bullets_and_focus(snapshot, {}, max_bullets=3)

        self.assertEqual(len(bullets), 3)
        self.assertEqual(bullets[0], "Gmail: 3 in view, 1 unread.")
        self.assertTrue(bullets[1].startswith("\u2014 Important release coordination "))
        self.assertTrue(bullets[1].endswith("\u2026"))
        self.assertEqual(bullets[2], "\u2014 Second")
        self.assertFalse(any("Defects:" in b for b in bullets))
        self.assertEqual(
            focus,
            "Blend inbox triage with defect and test-run priorities for today.",
        )

    def test_focus_line_distinguishes_mail_qe_and_work_only_inputs(self):
        mail_only = _snapshot(
            mail_messages=[MailMessage("m1", "Subject", "a@example.com", "")]
        )
        qe_only = _snapshot(team_members=[TeamMember(id="qe-1", name="Alex")])
        work_only = _snapshot(
            defects=[Defect("D-1", "Bug", "High", "Open")],
            test_runs=[TestRun("R-1", "Nightly", "Failed")],
        )

        self.assertEqual(
            get_brief_bullets_and_focus(mail_only, {}, max_bullets=3)[1],
            "Triage unread Gmail; reply, archive, or snooze so nothing important slips.",
        )
        self.assertEqual(
            get_brief_bullets_and_focus(qe_only, {}, max_bullets=3)[1],
            "Reconcile team capacity and sprint allocations with strategy signals; "
            "pick 1\u20132 leadership moves today.",
        )
        self.assertEqual(
            get_brief_bullets_and_focus(work_only, {}, max_bullets=3)[1],
            "Review open defects and latest test run; align with your QA team on priorities.",
        )

    def test_qe_context_bullets_are_capped_before_work_bullets(self):
        snapshot = _snapshot(
            team_members=[
                TeamMember(id="qe-1", name="Alex"),
                TeamMember(
                    id="qe-2",
                    name="Jordan",
                    last_one_on_one=datetime(2026, 4, 1),
                ),
            ],
            capacity_allocations=[
                CapacityAllocation(id="a1", person_id="qe-1", app_name="Billing")
            ],
            strategy_signals=[
                StrategySignal(id="s1", pillar="Automation", summary="Raise API coverage")
            ],
            defects=[Defect("D-1", "Critical checkout bug", "Critical", "Open")],
        )

        bullets, focus = get_brief_bullets_and_focus(
            snapshot,
            {"brief": {"include_qe_context": True, "max_qe_context_bullets": 2}},
            max_bullets=5,
        )

        self.assertEqual(bullets[0], "QE team (file): 2 people, 0 flagged on vacation.")
        self.assertEqual(
            bullets[1],
            "1:1 hygiene: 2 member(s) past 21d or missing last 1:1 date.",
        )
        self.assertTrue(any(b.startswith("Defects:") for b in bullets))
        self.assertFalse(any(b.startswith("Allocations:") for b in bullets))
        self.assertFalse(any(b.startswith("Strategy file:") for b in bullets))
        self.assertEqual(
            focus,
            "Balance people/capacity/strategy context with inbox and execution signals for today.",
        )

    def test_render_brief_appends_adapter_notes_after_provenance(self):
        snapshot = _snapshot(notes=["Gmail: token refresh failed (expired)."])

        md = render_brief(snapshot, Path.cwd(), {}, max_bullets=3)

        self.assertIn("*As of 2026-05-19T10:00:00Z (UTC) \u00b7 Sources: unit-test*", md)
        self.assertTrue(md.rstrip().endswith("*Gmail: token refresh failed (expired).*"))


if __name__ == "__main__":
    unittest.main()
