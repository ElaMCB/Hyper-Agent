import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from src.shadow.adapters.file_export import load_allocations_from_json, load_team_from_json
from src.shadow.capabilities.people_capacity import render_people_capacity_md
from src.shadow.capabilities.resource_allocation import render_resource_allocation_md
from src.shadow.capabilities.strategy_lens import render_strategy_md, strategy_summary_bullets
from src.shadow.models import CapacityAllocation, Snapshot, StrategySignal, TeamMember


class QEExportParsingRegressionTests(unittest.TestCase):
    def _write_json(self, root: Path, name: str, payload: object) -> Path:
        path = root / name
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_team_loader_coerces_exported_vacation_strings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_json(
                Path(tmp),
                "team.json",
                {
                    "team": [
                        {
                            "id": "qa-1",
                            "name": "Ada",
                            "role": "Lead QE",
                            "skills": "API, UI",
                            "on_vacation": "false",
                            "last_one_on_one": "2026-06-20",
                        },
                        {
                            "id": "qa-2",
                            "name": "Ben",
                            "role": "Automation",
                            "skills": ["Playwright"],
                            "vacation": "YES",
                            "last_one_on_one": "2026-06-22",
                        },
                        {
                            "id": "qa-3",
                            "name": "Cy",
                            "role": "Manual QE",
                            "on_vacation": "0",
                            "last_one_on_one": "2026-06-23",
                        },
                    ]
                },
            )

            members = load_team_from_json(path)

        self.assertEqual([False, True, False], [m.on_vacation for m in members])
        self.assertEqual(["API", "UI"], members[0].skills)

        snapshot = Snapshot(
            as_of=datetime(2026, 7, 3, tzinfo=timezone.utc),
            team_members=members,
        )
        markdown = render_people_capacity_md(snapshot, {})

        self.assertIn("- **On vacation (flag):** 1", markdown)
        self.assertIn("| Ada | Lead QE | API, UI | No ", markdown)
        self.assertIn("| Ben | Automation | Playwright | Yes ", markdown)

    def test_allocation_loader_preserves_zero_and_uses_nonblank_aliases(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_json(
                Path(tmp),
                "allocations.json",
                {
                    "allocations": [
                        {
                            "id": "alloc-1",
                            "person_id": "qa-1",
                            "person_name": "Ada",
                            "app": "Billing",
                            "sprint": "2026.14",
                            "focus_pct": 0,
                            "pct": 75,
                            "note": "explicit zero matters",
                        },
                        {
                            "id": "alloc-2",
                            "person_id": "qa-1",
                            "person_name": "Ada",
                            "app": "Search",
                            "sprint": "2026.14",
                            "focus_pct": "",
                            "allocation_pct": "60",
                            "note": "fallback alias",
                        },
                        {
                            "id": "alloc-3",
                            "person_id": "qa-2",
                            "person_name": "Ben",
                            "app": "Mobile",
                            "sprint": "2026.14",
                            "focus_pct": "not exported",
                        },
                    ]
                },
            )

            allocations = load_allocations_from_json(path)

        self.assertEqual([0, 60, None], [a.focus_pct for a in allocations])

        snapshot = Snapshot(
            as_of=datetime(2026, 7, 3, tzinfo=timezone.utc),
            capacity_allocations=allocations,
        )
        markdown = render_resource_allocation_md(snapshot, {})

        self.assertIn("- **Ada** — 0% · sprint `2026.14` — _explicit zero matters_", markdown)
        self.assertIn("- **Ada** — 60% · sprint `2026.14` — _fallback alias_", markdown)
        self.assertNotIn("75%", markdown)


class StrategyPriorityRegressionTests(unittest.TestCase):
    def test_p10_strategy_signal_does_not_sort_as_p1(self) -> None:
        snapshot = Snapshot(
            as_of=datetime(2026, 7, 3, tzinfo=timezone.utc),
            strategy_signals=[
                StrategySignal(
                    id="future",
                    pillar="Future automation",
                    summary="Later backlog item",
                    horizon="Later",
                    priority="P10",
                    status="Watching",
                ),
                StrategySignal(
                    id="guardrails",
                    pillar="Production guardrails",
                    summary="Harden the release gate",
                    horizon="Now",
                    priority="P2",
                    status="Active",
                ),
            ],
        )

        bullets = strategy_summary_bullets(snapshot, {})
        markdown = render_strategy_md(snapshot, {})

        self.assertIn("**Production guardrails** (P2)", bullets[0])
        self.assertLess(
            markdown.index("## Production guardrails"),
            markdown.index("## Future automation"),
        )


if __name__ == "__main__":
    unittest.main()
