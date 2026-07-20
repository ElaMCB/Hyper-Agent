import unittest
from datetime import datetime, timezone

from src.shadow.capabilities.brief import get_brief_bullets_and_focus
from src.shadow.capabilities.people_capacity import people_capacity_summary_bullets
from src.shadow.capabilities.resource_allocation import render_resource_allocation_md
from src.shadow.capabilities.strategy_lens import render_strategy_md, strategy_summary_bullets
from src.shadow.models import CapacityAllocation, MailMessage, Snapshot, StrategySignal, TeamMember


def _snapshot(**overrides):
    values = {
        "as_of": datetime(2026, 5, 8, 10, 0, tzinfo=timezone.utc),
        "sources": ["test"],
    }
    values.update(overrides)
    return Snapshot(**values)


class QeAndBriefTests(unittest.TestCase):
    def test_resource_allocation_warns_when_person_exceeds_sprint_capacity(self):
        snapshot = _snapshot(
            capacity_allocations=[
                CapacityAllocation(
                    id="a-1",
                    person_id="qa-1",
                    person_name="Asha",
                    app_name="Checkout",
                    sprint_label="Sprint 12",
                    focus_pct=70,
                ),
                CapacityAllocation(
                    id="a-2",
                    person_id="qa-1",
                    person_name="Asha",
                    app_name="Payments",
                    sprint_label="Sprint 12",
                    focus_pct=40,
                ),
            ]
        )

        markdown = render_resource_allocation_md(snapshot, {})

        self.assertIn("**Warning:** focus % sums > 100 for:", markdown)
        self.assertIn("- qa-1 @ Sprint 12", markdown)

    def test_strategy_rendering_and_summary_prioritize_p0_signals(self):
        snapshot = _snapshot(
            strategy_signals=[
                StrategySignal(
                    id="s-1",
                    pillar="Automation",
                    summary="Reduce flaky suites",
                    horizon="Now",
                    priority="P1",
                ),
                StrategySignal(
                    id="s-2",
                    pillar="Release confidence",
                    summary="Protect checkout release",
                    horizon="Next",
                    priority="P0",
                ),
            ]
        )

        markdown = render_strategy_md(snapshot, {})
        summary = strategy_summary_bullets(snapshot, {})

        self.assertLess(markdown.index("Release confidence"), markdown.index("Automation"))
        self.assertEqual(
            summary,
            [
                "Strategy file: 2 signal(s); top priority line — **Release confidence** (P0): "
                "Protect checkout release"
            ],
        )

    def test_people_summary_flags_missing_and_stale_one_on_ones(self):
        snapshot = _snapshot(
            team_members=[
                TeamMember(
                    id="qa-1",
                    name="Asha",
                    on_vacation=True,
                    last_one_on_one=datetime(2026, 4, 1, tzinfo=timezone.utc),
                ),
                TeamMember(id="qa-2", name="Ben", last_one_on_one=None),
            ]
        )

        bullets = people_capacity_summary_bullets(
            snapshot,
            {"people": {"one_on_one_stale_days": 21}},
        )

        self.assertEqual(
            bullets,
            [
                "QE team (file): 2 people, 1 flagged on vacation.",
                "1:1 hygiene: 2 member(s) past 21d or missing last 1:1 date.",
            ],
        )

    def test_brief_reserves_capped_space_for_qe_context_before_mail_bullets(self):
        snapshot = _snapshot(
            team_members=[
                TeamMember(id="qa-1", name="Asha", last_one_on_one=None),
            ],
            capacity_allocations=[
                CapacityAllocation(id="a-1", person_id="qa-1", app_name="Checkout"),
            ],
            strategy_signals=[
                StrategySignal(
                    id="s-1",
                    pillar="Release confidence",
                    summary="Protect checkout release",
                    priority="P0",
                ),
            ],
            mail_messages=[
                MailMessage(
                    id="m-1",
                    subject="Escalation: checkout release decision",
                    from_addr="lead@example.com",
                    snippet="Please review",
                    is_unread=True,
                )
            ],
        )

        bullets, suggested = get_brief_bullets_and_focus(
            snapshot,
            {"brief": {"include_qe_context": True, "max_qe_context_bullets": 2}},
            max_bullets=3,
        )

        self.assertEqual(len(bullets), 3)
        self.assertEqual(bullets[0], "QE team (file): 1 people, 0 flagged on vacation.")
        self.assertEqual(
            bullets[1],
            "1:1 hygiene: 1 member(s) past 21d or missing last 1:1 date.",
        )
        self.assertEqual(bullets[2], "Gmail: 1 in view, 1 unread.")
        self.assertEqual(
            suggested,
            "Balance people/capacity/strategy context with inbox and execution signals for today.",
        )


if __name__ == "__main__":
    unittest.main()
