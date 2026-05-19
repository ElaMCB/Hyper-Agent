import unittest
from datetime import datetime, timezone

from src.shadow.capabilities.people_capacity import (
    people_capacity_summary_bullets,
    render_people_capacity_md,
)
from src.shadow.capabilities.qe_pack import render_qe_subagent_pack
from src.shadow.capabilities.resource_allocation import (
    render_resource_allocation_md,
    resource_allocation_summary_bullets,
)
from src.shadow.capabilities.strategy_lens import (
    render_strategy_md,
    strategy_summary_bullets,
)
from src.shadow.models import CapacityAllocation, Snapshot, StrategySignal, TeamMember


def _snapshot(**kwargs):
    return Snapshot(as_of=datetime(2026, 5, 19, tzinfo=timezone.utc), **kwargs)


class QECapabilityTests(unittest.TestCase):
    def test_people_capacity_flags_morale_and_missing_or_stale_one_on_ones(self):
        snapshot = _snapshot(
            team_members=[
                TeamMember(id="qe-1", name="Alex", morale_flag="Amber"),
                TeamMember(
                    id="qe-2",
                    name="Jordan",
                    on_vacation=True,
                    last_one_on_one=datetime(2026, 4, 10),
                ),
            ]
        )

        md = render_people_capacity_md(snapshot, {"people": {"one_on_one_stale_days": 21}})
        bullets = people_capacity_summary_bullets(
            snapshot,
            {"people": {"one_on_one_stale_days": 21}},
        )

        self.assertIn("Morale watch (amber/red):** Alex", md)
        self.assertIn("1:1 stale (>21d or missing):** Alex, Jordan", md)
        self.assertEqual(bullets[0], "QE team (file): 2 people, 1 flagged on vacation.")
        self.assertEqual(
            bullets[1],
            "1:1 hygiene: 2 member(s) past 21d or missing last 1:1 date.",
        )

    def test_resource_allocation_warns_on_overallocation_and_groups_by_app(self):
        snapshot = _snapshot(
            capacity_allocations=[
                CapacityAllocation(
                    id="a1",
                    person_id="qe-1",
                    person_name="Alex",
                    app_name="Billing",
                    sprint_label="2026-W20",
                    focus_pct=60,
                ),
                CapacityAllocation(
                    id="a2",
                    person_id="qe-1",
                    person_name="Alex",
                    app_name="Admin",
                    sprint_label="2026-W20",
                    focus_pct=50,
                    commitment_note="Release | regression",
                ),
                CapacityAllocation(
                    id="a3",
                    person_id="qe-2",
                    person_name="Jordan",
                    app_name="Admin",
                    sprint_label="2026-W20",
                    focus_pct=None,
                ),
            ]
        )

        md = render_resource_allocation_md(snapshot, {})
        bullets = resource_allocation_summary_bullets(snapshot, {})

        self.assertIn("**Warning:** focus % sums > 100 for:", md)
        self.assertIn("- qe-1 @ 2026-W20", md)
        self.assertLess(md.index("### Admin"), md.index("### Billing"))
        self.assertIn("| Alex | Admin | 2026-W20 | 50 | Release \\| regression |", md)
        self.assertIn("| Jordan | Admin | 2026-W20 | \u2014 |  |", md)
        self.assertEqual(bullets, ["Allocations: 3 row(s) across 2 app bucket(s)."])

    def test_strategy_lens_orders_p0_first_and_escapes_table_pipes(self):
        snapshot = _snapshot(
            strategy_signals=[
                StrategySignal(
                    id="s1",
                    pillar="Ownership",
                    summary="Clarify QE | dev ownership",
                    horizon="FY26",
                    priority="P1",
                    status="Draft",
                    evidence_ref="Workshop | notes",
                ),
                StrategySignal(
                    id="s2",
                    pillar="Automation",
                    summary="Raise API coverage",
                    horizon="2026-H2",
                    priority="p0",
                    status="Active",
                ),
            ]
        )

        md = render_strategy_md(snapshot, {})
        bullets = strategy_summary_bullets(snapshot, {})

        self.assertLess(md.index("## Automation"), md.index("## Ownership"))
        self.assertIn("Clarify QE \\| dev ownership", md)
        self.assertIn("Workshop \\| notes", md)
        self.assertEqual(
            bullets,
            [
                "Strategy file: 2 signal(s); top priority line "
                "\u2014 **Automation** (p0): Raise API coverage"
            ],
        )

    def test_qe_pack_combines_all_three_sections_with_separators(self):
        snapshot = _snapshot(
            team_members=[TeamMember(id="qe-1", name="Alex")],
            capacity_allocations=[
                CapacityAllocation(id="a1", person_id="qe-1", app_name="Billing")
            ],
            strategy_signals=[
                StrategySignal(id="s1", pillar="Automation", summary="Raise API coverage")
            ],
        )

        md = render_qe_subagent_pack(snapshot, {})

        self.assertIn("# People & capacity (QE)", md)
        self.assertIn("# Resource allocation (QE)", md)
        self.assertIn("# Strategy lens (QE)", md)
        self.assertEqual(md.count("\n---\n\n"), 2)


if __name__ == "__main__":
    unittest.main()
