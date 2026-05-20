import unittest
from datetime import datetime, timezone

from src.shadow.capabilities.people_capacity import (
    people_capacity_summary_bullets,
    render_people_capacity_md,
)
from src.shadow.capabilities.resource_allocation import render_resource_allocation_md
from src.shadow.capabilities.strategy_lens import render_strategy_md, strategy_summary_bullets
from src.shadow.models import CapacityAllocation, Snapshot, StrategySignal, TeamMember


class QECapabilityTests(unittest.TestCase):
    def test_people_capacity_flags_vacation_morale_and_stale_one_on_ones(self):
        snapshot = Snapshot(
            as_of=datetime(2026, 5, 20, tzinfo=timezone.utc),
            team_members=[
                TeamMember(
                    id="qa-1",
                    name="Alex",
                    role="Lead",
                    skills=["api"],
                    on_vacation=True,
                    morale_flag="amber",
                    last_one_on_one=datetime(2026, 4, 1),
                ),
                TeamMember(id="qa-2", name="Blair", role="SDET"),
            ],
        )
        config = {"people": {"one_on_one_stale_days": 21}}

        rendered = render_people_capacity_md(snapshot, config)
        bullets = people_capacity_summary_bullets(snapshot, config)

        self.assertIn("**On vacation (flag):** 1", rendered)
        self.assertIn("**Morale watch (amber/red):** Alex", rendered)
        self.assertIn("**1:1 stale (>21d or missing):** Alex, Blair", rendered)
        self.assertEqual(
            bullets,
            [
                "QE team (file): 2 people, 1 flagged on vacation.",
                "1:1 hygiene: 2 member(s) past 21d or missing last 1:1 date.",
            ],
        )

    def test_resource_allocation_warns_when_person_is_overcommitted_in_sprint(self):
        snapshot = Snapshot(
            as_of=datetime(2026, 5, 20, tzinfo=timezone.utc),
            capacity_allocations=[
                CapacityAllocation(
                    id="alloc-1",
                    person_id="qa-1",
                    person_name="Alex",
                    app_name="Checkout",
                    sprint_label="S42",
                    focus_pct=75,
                ),
                CapacityAllocation(
                    id="alloc-2",
                    person_id="qa-1",
                    person_name="Alex",
                    app_name="Profile",
                    sprint_label="S42",
                    focus_pct=50,
                ),
            ],
        )

        rendered = render_resource_allocation_md(snapshot, {})

        self.assertIn("**Warning:** focus % sums > 100 for:", rendered)
        self.assertIn("- qa-1 @ S42", rendered)

    def test_strategy_lens_orders_p0_before_lower_priority_signals(self):
        snapshot = Snapshot(
            as_of=datetime(2026, 5, 20, tzinfo=timezone.utc),
            strategy_signals=[
                StrategySignal(
                    id="s2",
                    pillar="Coverage",
                    summary="Expand API regression",
                    horizon="next",
                    priority="P2",
                ),
                StrategySignal(
                    id="s0",
                    pillar="Release",
                    summary="Stabilize checkout smoke",
                    horizon="current",
                    priority="P0",
                ),
                StrategySignal(
                    id="s1",
                    pillar="Observability",
                    summary="Add failure triage dashboard",
                    horizon="current",
                    priority="P1",
                ),
            ],
        )

        rendered = render_strategy_md(snapshot, {})
        p0_pos = rendered.index("## Release")
        p1_pos = rendered.index("## Observability")
        p2_pos = rendered.index("## Coverage")

        self.assertLess(p0_pos, p1_pos)
        self.assertLess(p1_pos, p2_pos)
        summary = strategy_summary_bullets(snapshot, {})
        self.assertEqual(len(summary), 1)
        self.assertTrue(summary[0].startswith("Strategy file: 3 signal(s); top priority line"))
        self.assertIn("**Release** (P0): Stabilize checkout smoke", summary[0])


if __name__ == "__main__":
    unittest.main()
