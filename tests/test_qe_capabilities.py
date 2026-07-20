import unittest
from datetime import datetime, timezone

from src.shadow.capabilities.people_capacity import (
    people_capacity_summary_bullets,
    render_people_capacity_md,
)
from src.shadow.capabilities.resource_allocation import render_resource_allocation_md
from src.shadow.capabilities.strategy_lens import render_strategy_md, strategy_summary_bullets
from src.shadow.models import CapacityAllocation, Snapshot, StrategySignal, TeamMember


class QeCapabilityRenderingTests(unittest.TestCase):
    def test_people_capacity_flags_morale_stale_one_on_ones_and_escapes_tables(self):
        snapshot = Snapshot(
            as_of=datetime(2026, 5, 21, tzinfo=timezone.utc),
            team_members=[
                TeamMember(
                    id="qe-1",
                    name="Alex",
                    role="QE",
                    skills=["API", "CI"],
                    morale_flag="amber",
                    last_one_on_one=datetime(2026, 4, 1),
                    performance_note="Owns billing | checkout",
                ),
                TeamMember(id="qe-2", name="Jordan", role="QE II", on_vacation=True),
            ],
        )
        config = {"people": {"one_on_one_stale_days": 21}}

        markdown = render_people_capacity_md(snapshot, config)
        bullets = people_capacity_summary_bullets(snapshot, config)

        self.assertIn("**Morale watch (amber/red):** Alex", markdown)
        self.assertIn("**1:1 stale (>21d or missing):** Alex, Jordan", markdown)
        self.assertIn("Owns billing \\| checkout", markdown)
        self.assertIn("QE team (file): 2 people, 1 flagged on vacation.", bullets)
        self.assertIn(
            "1:1 hygiene: 2 member(s) past 21d or missing last 1:1 date.",
            bullets,
        )

    def test_resource_allocation_warns_when_person_exceeds_sprint_capacity(self):
        snapshot = Snapshot(
            as_of=datetime(2026, 5, 21, tzinfo=timezone.utc),
            capacity_allocations=[
                CapacityAllocation(
                    id="a1",
                    person_id="qe-1",
                    person_name="Alex",
                    app_name="Billing",
                    sprint_label="2026-W21",
                    focus_pct=60,
                ),
                CapacityAllocation(
                    id="a2",
                    person_id="qe-1",
                    person_name="Alex",
                    app_name="Checkout",
                    sprint_label="2026-W21",
                    focus_pct=50,
                    commitment_note="release | support",
                ),
            ],
        )

        markdown = render_resource_allocation_md(snapshot, {})

        self.assertIn("**Warning:** focus % sums > 100 for:", markdown)
        self.assertIn("- qe-1 @ 2026-W21", markdown)
        self.assertIn("release \\| support", markdown)

    def test_strategy_orders_p0_before_lower_priorities_in_detail_and_summary(self):
        snapshot = Snapshot(
            as_of=datetime(2026, 5, 21, tzinfo=timezone.utc),
            strategy_signals=[
                StrategySignal(
                    id="s2",
                    pillar="Later work",
                    summary="Important but lower priority",
                    horizon="FY26",
                    priority="P2",
                ),
                StrategySignal(
                    id="s1",
                    pillar="Release readiness",
                    summary="Protect launch-critical coverage",
                    horizon="2026-H1",
                    priority="P0",
                ),
            ],
        )

        markdown = render_strategy_md(snapshot, {})
        summary = strategy_summary_bullets(snapshot, {})

        self.assertLess(markdown.index("Release readiness"), markdown.index("Later work"))
        self.assertIn("**Release readiness** (P0): Protect launch-critical coverage", summary[0])


if __name__ == "__main__":
    unittest.main()
