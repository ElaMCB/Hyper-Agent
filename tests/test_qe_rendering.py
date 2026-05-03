import unittest
from datetime import datetime, timezone

from src.shadow.capabilities.brief import get_brief_bullets_and_focus
from src.shadow.capabilities.resource_allocation import render_resource_allocation_md
from src.shadow.capabilities.strategy_lens import render_strategy_md, strategy_summary_bullets
from src.shadow.models import CapacityAllocation, Snapshot, StrategySignal, TeamMember


class QeRenderingTests(unittest.TestCase):
    def test_brief_includes_capped_qe_context_and_qe_only_focus(self):
        snapshot = Snapshot(
            as_of=datetime(2026, 5, 3, tzinfo=timezone.utc),
            team_members=[
                TeamMember(
                    id="e-1",
                    name="Alex",
                    on_vacation=True,
                    last_one_on_one=datetime(2026, 3, 1),
                )
            ],
            capacity_allocations=[
                CapacityAllocation(id="a-1", person_id="e-1", app_name="Billing", focus_pct=50)
            ],
            strategy_signals=[
                StrategySignal(
                    id="s-1",
                    pillar="Payments",
                    priority="P1",
                    summary="Stabilize checkout",
                )
            ],
        )

        bullets, focus = get_brief_bullets_and_focus(
            snapshot,
            {
                "brief": {
                    "include_qe_context": True,
                    "max_qe_context_bullets": 2,
                    "max_bullets": 2,
                }
            },
        )

        self.assertEqual(len(bullets), 2)
        self.assertEqual(bullets[0], "QE team (file): 1 people, 1 flagged on vacation.")
        self.assertEqual(bullets[1], "1:1 hygiene: 1 member(s) past 21d or missing last 1:1 date.")
        self.assertIn("Reconcile team capacity and sprint allocations", focus)
        self.assertIn("leadership moves today", focus)

    def test_resource_allocation_warns_when_person_exceeds_sprint_capacity(self):
        snapshot = Snapshot(
            as_of=datetime(2026, 5, 3, tzinfo=timezone.utc),
            capacity_allocations=[
                CapacityAllocation(
                    id="a-1",
                    person_id="e-1",
                    person_name="Alex",
                    app_name="Billing",
                    sprint_label="Sprint 7",
                    focus_pct=70,
                    commitment_note="checkout | payments",
                ),
                CapacityAllocation(
                    id="a-2",
                    person_id="e-1",
                    person_name="Alex",
                    app_name="Claims",
                    sprint_label="Sprint 7",
                    focus_pct=40,
                ),
            ],
        )

        markdown = render_resource_allocation_md(snapshot, {})

        self.assertIn("**Warning:** focus % sums > 100 for:", markdown)
        self.assertIn("- e-1 @ Sprint 7", markdown)
        self.assertIn("| Alex | Billing | Sprint 7 | 70 | checkout \\| payments |", markdown)

    def test_strategy_orders_p0_before_p1_and_escapes_table_pipes(self):
        snapshot = Snapshot(
            as_of=datetime(2026, 5, 3, tzinfo=timezone.utc),
            strategy_signals=[
                StrategySignal(
                    id="s-1",
                    pillar="Later",
                    priority="P1",
                    horizon="Now",
                    summary="Secondary",
                ),
                StrategySignal(
                    id="s-2",
                    pillar="Payments",
                    priority="P0",
                    horizon="Next",
                    status="At risk",
                    summary="Cut release | rollback risk",
                    evidence_ref="plan | risks",
                ),
            ],
        )

        markdown = render_strategy_md(snapshot, {})
        bullets = strategy_summary_bullets(snapshot, {})

        self.assertLess(markdown.index("## Payments"), markdown.index("## Later"))
        self.assertIn("| Payments | P0 | Next | At risk | Cut release \\| rollback risk | plan \\| risks |", markdown)
        self.assertEqual(len(bullets), 1)
        self.assertIn("top priority line", bullets[0])
        self.assertIn("**Payments** (P0): Cut release | rollback risk", bullets[0])


if __name__ == "__main__":
    unittest.main()
