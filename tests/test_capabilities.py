import unittest
from datetime import datetime, timezone

from src.shadow.capabilities.brief import get_brief_bullets_and_focus
from src.shadow.capabilities.resource_allocation import render_resource_allocation_md
from src.shadow.capabilities.strategy_lens import render_strategy_md, strategy_summary_bullets
from src.shadow.models import (
    CapacityAllocation,
    Defect,
    Snapshot,
    StrategySignal,
    TeamMember,
)


def _snapshot(**kwargs):
    return Snapshot(as_of=datetime(2026, 5, 13, 10, 0, tzinfo=timezone.utc), **kwargs)


class BriefSummaryTests(unittest.TestCase):
    def test_brief_counts_high_severity_and_open_defects(self):
        snapshot = _snapshot(
            defects=[
                Defect(id="D1", title="Checkout outage", severity="2 - High", status="Active"),
                Defect(id="D2", title="Closed typo", severity="Low", status="Done"),
            ]
        )

        bullets, suggested = get_brief_bullets_and_focus(snapshot, {"brief": {"max_bullets": 3}})

        self.assertEqual(
            bullets,
            [
                "Defects: 2 total, 1 critical/high, 1 not closed.",
                "Top severity: D1 — Checkout outage",
            ],
        )
        self.assertEqual(
            suggested,
            "Review open defects and latest test run; align with your QA team on priorities.",
        )

    def test_qe_context_is_capped_before_work_bullets_are_added(self):
        as_of = datetime(2026, 5, 13, 10, 0, tzinfo=timezone.utc)
        snapshot = Snapshot(
            as_of=as_of,
            defects=[Defect(id="D1", title="Critical regression", severity="Critical", status="New")],
            team_members=[
                TeamMember(id="T1", name="Alex", on_vacation=True, last_one_on_one=as_of)
            ],
            capacity_allocations=[
                CapacityAllocation(id="A1", person_id="T1", app_name="Portal", focus_pct=80)
            ],
            strategy_signals=[
                StrategySignal(
                    id="S1",
                    pillar="Reliability",
                    summary="Reduce customer escape rate",
                    priority="P1",
                )
            ],
        )

        bullets, suggested = get_brief_bullets_and_focus(
            snapshot,
            {"brief": {"max_bullets": 3, "include_qe_context": True, "max_qe_context_bullets": 2}},
        )

        self.assertEqual(len(bullets), 3)
        self.assertEqual(bullets[0], "QE team (file): 1 people, 1 flagged on vacation.")
        self.assertEqual(bullets[1], "Allocations: 1 row(s) across 1 app bucket(s).")
        self.assertEqual(bullets[2], "Defects: 1 total, 1 critical/high, 1 not closed.")
        self.assertEqual(
            suggested,
            "Balance people/capacity/strategy context with inbox and execution signals for today.",
        )


class ResourceAllocationTests(unittest.TestCase):
    def test_render_resource_allocation_warns_when_focus_exceeds_capacity(self):
        snapshot = _snapshot(
            capacity_allocations=[
                CapacityAllocation(
                    id="A1",
                    person_id="U1",
                    person_name="Riley",
                    app_name="Payments",
                    sprint_label="S42",
                    focus_pct=60,
                ),
                CapacityAllocation(
                    id="A2",
                    person_id="U1",
                    person_name="Riley",
                    app_name="Search",
                    sprint_label="S42",
                    focus_pct=50,
                    commitment_note="Risk | needs split",
                ),
            ]
        )

        md = render_resource_allocation_md(snapshot, {})

        self.assertIn("**Warning:** focus % sums > 100 for:", md)
        self.assertIn("- U1 @ S42", md)
        self.assertIn("Risk \\| needs split", md)


class StrategyLensTests(unittest.TestCase):
    def test_strategy_markdown_and_summary_use_priority_order(self):
        snapshot = _snapshot(
            strategy_signals=[
                StrategySignal(
                    id="S2",
                    pillar="Cost",
                    summary="Trim redundant environments",
                    horizon="Q3",
                    priority="P2",
                ),
                StrategySignal(
                    id="S1",
                    pillar="Reliability",
                    summary="Reduce customer escape rate",
                    horizon="Q2",
                    priority="P1",
                ),
            ]
        )

        md = render_strategy_md(snapshot, {})
        bullets = strategy_summary_bullets(snapshot, {})

        self.assertLess(md.index("## Reliability"), md.index("## Cost"))
        self.assertEqual(
            bullets,
            [
                "Strategy file: 2 signal(s); top priority line — **Reliability** (P1): Reduce customer escape rate"
            ],
        )


if __name__ == "__main__":
    unittest.main()
