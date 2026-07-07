import unittest
from datetime import datetime, timezone

from src.shadow.capabilities.brief import get_brief_bullets_and_focus
from src.shadow.capabilities.resource_allocation import render_resource_allocation_md
from src.shadow.capabilities.strategy_lens import (
    _priority_rank,
    render_strategy_md,
    strategy_summary_bullets,
)
from src.shadow.models import CapacityAllocation, MailMessage, Snapshot, StrategySignal, TeamMember


def _snapshot(**overrides):
    data = {"as_of": datetime(2026, 7, 2, 10, 0, tzinfo=timezone.utc)}
    data.update(overrides)
    return Snapshot(**data)


class StrategyPriorityTests(unittest.TestCase):
    def test_priority_rank_treats_p10_as_unknown_not_p1(self):
        self.assertEqual(_priority_rank(" p1 ")[0], 1)
        self.assertEqual(_priority_rank("P1 - launch readiness")[0], 1)
        self.assertEqual(_priority_rank("P10")[0], 9)

    def test_strategy_summary_uses_sorted_priority_not_file_order(self):
        snapshot = _snapshot(
            strategy_signals=[
                StrategySignal(
                    id="long-tail",
                    pillar="Lower risk",
                    priority="P10",
                    horizon="Now",
                    summary="Should not outrank actual P2 work.",
                ),
                StrategySignal(
                    id="release",
                    pillar="Release confidence",
                    priority="P2",
                    horizon="Later",
                    summary="Real priority line for the brief.",
                ),
            ]
        )

        bullets = strategy_summary_bullets(snapshot, {})

        self.assertEqual(len(bullets), 1)
        self.assertIn("**Release confidence** (P2)", bullets[0])
        self.assertNotIn("Lower risk", bullets[0])

    def test_strategy_markdown_orders_p0_p1_p2_before_unknown_priorities(self):
        snapshot = _snapshot(
            strategy_signals=[
                StrategySignal(id="unknown", pillar="Unknown", priority="P10", horizon="Now", summary="later"),
                StrategySignal(id="p2", pillar="P2 pillar", priority="P2", horizon="Now", summary="third"),
                StrategySignal(id="p1", pillar="P1 pillar", priority="p1", horizon="Now", summary="second"),
                StrategySignal(id="p0", pillar="P0 pillar", priority="P0-critical", horizon="Now", summary="first"),
            ]
        )

        markdown = render_strategy_md(snapshot, {})

        self.assertLess(markdown.index("## P0 pillar"), markdown.index("## P1 pillar"))
        self.assertLess(markdown.index("## P1 pillar"), markdown.index("## P2 pillar"))
        self.assertLess(markdown.index("## P2 pillar"), markdown.index("## Unknown"))


class ResourceAllocationTests(unittest.TestCase):
    def test_allocation_warning_sums_by_person_and_sprint_and_ignores_missing_percent(self):
        snapshot = _snapshot(
            capacity_allocations=[
                CapacityAllocation(
                    id="a1",
                    person_id="qe-1",
                    person_name="Ari",
                    app_name="Checkout",
                    sprint_label="2026-W27",
                    focus_pct=60,
                ),
                CapacityAllocation(
                    id="a2",
                    person_id="qe-1",
                    person_name="Ari",
                    app_name="Search",
                    sprint_label="2026-W27",
                    focus_pct=50,
                ),
                CapacityAllocation(
                    id="a3",
                    person_id="qe-1",
                    person_name="Ari",
                    sprint_label="2026-W28",
                    focus_pct=40,
                ),
                CapacityAllocation(
                    id="a4",
                    person_id="qe-2",
                    person_name="Blake",
                    app_name="",
                    sprint_label="2026-W27",
                    focus_pct=None,
                ),
            ]
        )

        markdown = render_resource_allocation_md(snapshot, {})

        self.assertIn("**Warning:** focus % sums > 100 for:", markdown)
        self.assertIn("- qe-1 @ 2026-W27", markdown)
        self.assertNotIn("- qe-1 @ 2026-W28", markdown)
        self.assertIn("### (no app)", markdown)
        self.assertIn("- **Blake** — — · sprint `2026-W27`", markdown)


class BriefQeContextTests(unittest.TestCase):
    def test_qe_context_respects_budget_and_blends_with_mail_focus(self):
        snapshot = _snapshot(
            mail_messages=[
                MailMessage(
                    id="m1",
                    subject="Release readiness follow-up",
                    from_addr="lead@example.com",
                    snippet="Please confirm coverage.",
                    is_unread=True,
                )
            ],
            team_members=[
                TeamMember(id="qe-1", name="Ari", on_vacation=True),
                TeamMember(id="qe-2", name="Blake"),
            ],
            capacity_allocations=[
                CapacityAllocation(
                    id="a1",
                    person_id="qe-1",
                    app_name="Checkout",
                    sprint_label="2026-W27",
                    focus_pct=80,
                )
            ],
            strategy_signals=[
                StrategySignal(
                    id="s1",
                    pillar="Release confidence",
                    summary="Tighten exploratory charter around payments.",
                    priority="P0",
                )
            ],
        )
        config = {"brief": {"include_qe_context": True, "max_qe_context_bullets": 2}}

        bullets, focus = get_brief_bullets_and_focus(snapshot, config, max_bullets=3)

        self.assertEqual(
            bullets,
            [
                "QE team (file): 2 people, 1 flagged on vacation.",
                "1:1 hygiene: 2 member(s) past 21d or missing last 1:1 date.",
                "Gmail: 1 in view, 1 unread.",
            ],
        )
        self.assertEqual(
            focus,
            "Balance people/capacity/strategy context with inbox and execution signals for today.",
        )


if __name__ == "__main__":
    unittest.main()
