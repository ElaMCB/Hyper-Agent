import unittest
from datetime import datetime, timedelta, timezone

from src.shadow.capabilities.brief import get_brief_bullets_and_focus
from src.shadow.models import (
    CapacityAllocation,
    Defect,
    MailMessage,
    Snapshot,
    StrategySignal,
    TeamMember,
    TestRun,
)


AS_OF = datetime(2026, 7, 5, 10, 0, tzinfo=timezone.utc)


def _snapshot(**kwargs) -> Snapshot:
    return Snapshot(as_of=AS_OF, sources=["test"], **kwargs)


class BriefRegressionTests(unittest.TestCase):
    def test_gmail_only_suppresses_missing_work_placeholders(self) -> None:
        snapshot = _snapshot(
            mail_messages=[
                MailMessage(
                    id="mail-1",
                    subject="Executive inbox follow-up",
                    from_addr="lead@example.com",
                    snippet="Can you review this?",
                    is_unread=True,
                )
            ]
        )

        bullets, focus = get_brief_bullets_and_focus(snapshot, {"brief": {"max_bullets": 5}})

        self.assertEqual(bullets[0], "Gmail: 1 in view, 1 unread.")
        self.assertIn("Executive inbox follow-up", bullets[1])
        self.assertNotIn("No defect data", "\n".join(bullets))
        self.assertNotIn("No test run data", "\n".join(bullets))
        self.assertEqual(
            focus,
            "Triage unread Gmail; reply, archive, or snooze so nothing important slips.",
        )

    def test_empty_snapshot_guides_user_to_enable_sources(self) -> None:
        bullets, focus = get_brief_bullets_and_focus(_snapshot(), {"brief": {"max_bullets": 5}})

        self.assertEqual(
            bullets,
            [
                "No defect data in this snapshot. Add data/ exports or enable Azure DevOps.",
                "No test run data in snapshot. Add test_runs.json under data/.",
            ],
        )
        self.assertEqual(
            focus,
            "Enable Gmail, work data, and/or QE files (team, allocations, strategy), then run again.",
        )

    def test_work_summary_counts_open_high_severity_and_truncates_top_defect(self) -> None:
        long_title = "A" * 65
        snapshot = _snapshot(
            defects=[
                Defect(id="BUG-1", title=long_title, severity="1 - Blocker", status="Active"),
                Defect(id="BUG-2", title="Medium closed", severity="3 - Medium", status="Closed"),
                Defect(id="BUG-3", title="Done low", severity="Low", status="Done"),
            ],
            test_runs=[
                TestRun(
                    id="run-1",
                    name="Regression",
                    status="Failed",
                    passed=92,
                    failed=8,
                    total=100,
                )
            ],
        )

        bullets, focus = get_brief_bullets_and_focus(snapshot, {"brief": {"max_bullets": 5}})

        self.assertIn("Defects: 3 total, 1 critical/high, 1 not closed.", bullets)
        self.assertIn(f"Top severity: BUG-1 \u2014 {'A' * 60}\u2026", bullets)
        self.assertIn("Latest test run: Regression \u2014 Failed. Passed: 92, Failed: 8", bullets)
        self.assertEqual(
            focus,
            "Review open defects and latest test run; align with your QA team on priorities.",
        )

    def test_qe_context_consumes_configured_bullet_budget_before_work_and_mail(self) -> None:
        snapshot = _snapshot(
            team_members=[
                TeamMember(
                    id="tm-1",
                    name="Riley",
                    on_vacation=True,
                    last_one_on_one=AS_OF - timedelta(days=45),
                )
            ],
            capacity_allocations=[
                CapacityAllocation(
                    id="alloc-1",
                    person_id="tm-1",
                    person_name="Riley",
                    app_name="Checkout",
                    sprint_label="S42",
                    focus_pct=75,
                )
            ],
            strategy_signals=[
                StrategySignal(
                    id="strat-1",
                    pillar="Release readiness",
                    summary="Cutover rehearsal coverage",
                    priority="P0",
                )
            ],
            mail_messages=[
                MailMessage(
                    id="mail-1",
                    subject="S" * 73,
                    from_addr="pm@example.com",
                    snippet="Need the latest plan",
                    is_unread=False,
                )
            ],
            defects=[Defect(id="BUG-9", title="Checkout blocker", severity="High", status="Active")],
        )
        config = {
            "brief": {
                "include_qe_context": True,
                "max_bullets": 5,
                "max_qe_context_bullets": 3,
            },
            "people": {"one_on_one_stale_days": 21},
        }

        bullets, focus = get_brief_bullets_and_focus(snapshot, config)

        self.assertEqual(len(bullets), 5)
        self.assertEqual(bullets[0], "QE team (file): 1 people, 1 flagged on vacation.")
        self.assertEqual(bullets[1], "1:1 hygiene: 1 member(s) past 21d or missing last 1:1 date.")
        self.assertEqual(bullets[2], "Allocations: 1 row(s) across 1 app bucket(s).")
        self.assertEqual(bullets[3], "Gmail: 1 in view, 0 unread.")
        self.assertEqual(bullets[4], f"\u2014 {'S' * 72}\u2026")
        self.assertNotIn("Checkout blocker", "\n".join(bullets))
        self.assertEqual(
            focus,
            "Balance people/capacity/strategy context with inbox and execution signals for today.",
        )

    def test_focus_matrix_distinguishes_work_mail_qe_combinations(self) -> None:
        mail_and_work = _snapshot(
            mail_messages=[
                MailMessage(
                    id="mail-1",
                    subject="Partner escalation",
                    from_addr="partner@example.com",
                    snippet="Please advise",
                )
            ],
            defects=[Defect(id="BUG-4", title="Payment outage", severity="Critical", status="New")],
        )
        qe_only = _snapshot(team_members=[TeamMember(id="tm-2", name="Morgan")])

        _, mail_work_focus = get_brief_bullets_and_focus(mail_and_work, {"brief": {"max_bullets": 5}})
        _, qe_focus = get_brief_bullets_and_focus(qe_only, {"brief": {"max_bullets": 5}})

        self.assertEqual(
            mail_work_focus,
            "Blend inbox triage with defect and test-run priorities for today.",
        )
        self.assertEqual(
            qe_focus,
            "Reconcile team capacity and sprint allocations with strategy signals; pick 1\u20132 leadership moves today.",
        )


if __name__ == "__main__":
    unittest.main()
