import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from src.shadow.adapters.file_export import load_allocations_from_json, load_team_from_json
from src.shadow.capabilities.brief import get_brief_bullets_and_focus
from src.shadow.capabilities.people_capacity import render_people_capacity_md
from src.shadow.capabilities.resource_allocation import render_resource_allocation_md
from src.shadow.models import Snapshot
from src.shadow.snapshot import build_snapshot


class QeDataIngestionTests(unittest.TestCase):
    def test_team_json_aliases_and_markdown_escape_risk_fields(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "team.json"
            path.write_text(
                json.dumps(
                    {
                        "members": [
                            {
                                "employee_id": "qe-1",
                                "name": "Ava",
                                "role": "Lead",
                                "skills": "api, automation, release",
                                "vacation": True,
                                "vacation_until": "2026-05-10",
                                "morale": "Amber",
                                "last_1_1": "2026-04-01",
                                "performance_note": "Owns payments | checkout",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            team = load_team_from_json(path)

        self.assertEqual(len(team), 1)
        member = team[0]
        self.assertEqual(member.id, "qe-1")
        self.assertEqual(member.skills, ["api", "automation", "release"])
        self.assertTrue(member.on_vacation)
        self.assertEqual(member.vacation_until, datetime(2026, 5, 10))
        self.assertEqual(member.morale_flag, "Amber")
        self.assertEqual(member.last_one_on_one, datetime(2026, 4, 1))

        snapshot = Snapshot(
            as_of=datetime(2026, 5, 6, tzinfo=timezone.utc),
            team_members=team,
        )
        markdown = render_people_capacity_md(snapshot, {"people": {"one_on_one_stale_days": 21}})

        self.assertIn("**On vacation (flag):** 1", markdown)
        self.assertIn("**Morale watch (amber/red):** Ava", markdown)
        self.assertIn("**1:1 stale (>21d or missing):** Ava", markdown)
        self.assertIn("Owns payments \\| checkout", markdown)

    def test_allocation_json_aliases_warn_when_focus_exceeds_capacity(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "allocations.json"
            path.write_text(
                json.dumps(
                    {
                        "assignments": [
                            {
                                "key": "a-1",
                                "person": "qe-1",
                                "name": "Ava",
                                "app": "Checkout",
                                "sprint": "Sprint 12",
                                "pct": "60",
                                "note": "Regression | smoke",
                            },
                            {
                                "key": "a-2",
                                "person": "qe-1",
                                "name": "Ava",
                                "app": "Payments",
                                "sprint": "Sprint 12",
                                "allocation_pct": 50,
                            },
                            {
                                "key": "a-3",
                                "person": "qe-2",
                                "app": "Search",
                                "sprint": "Sprint 12",
                                "focus_pct": "not-a-number",
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )

            rows = load_allocations_from_json(path)

        self.assertEqual([row.focus_pct for row in rows], [60, 50, None])
        self.assertEqual(rows[0].person_id, "qe-1")
        self.assertEqual(rows[0].app_name, "Checkout")

        markdown = render_resource_allocation_md(
            Snapshot(as_of=datetime(2026, 5, 6, tzinfo=timezone.utc), capacity_allocations=rows),
            {},
        )

        self.assertIn("**Warning:** focus % sums > 100 for:", markdown)
        self.assertIn("- qe-1 @ Sprint 12", markdown)
        self.assertIn("Regression \\| smoke", markdown)
        self.assertIn("| qe-2 | Search | Sprint 12 | \u2014 |", markdown)


class SnapshotAndBriefIntegrationTests(unittest.TestCase):
    def test_build_snapshot_loads_qe_files_only_when_enabled_and_records_sources(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            data = root / "data"
            data.mkdir()
            (data / "team.json").write_text(
                json.dumps([{"id": "qe-1", "name": "Ava"}]),
                encoding="utf-8",
            )
            (data / "allocations.json").write_text(
                json.dumps([{"id": "a-1", "person_id": "qe-1", "app_name": "Checkout"}]),
                encoding="utf-8",
            )
            (data / "strategy.json").write_text(
                json.dumps([{"id": "s-1", "pillar": "Payments", "priority": "P1"}]),
                encoding="utf-8",
            )

            disabled = build_snapshot(root, {"data": {"dir": "data"}})
            enabled = build_snapshot(
                root,
                {
                    "data": {
                        "dir": "data",
                        "load_defects": False,
                        "load_test_runs": False,
                        "load_team": True,
                        "load_allocations": True,
                        "load_strategy": True,
                    }
                },
            )

        self.assertEqual(disabled.team_members, [])
        self.assertEqual(disabled.capacity_allocations, [])
        self.assertEqual(disabled.strategy_signals, [])
        self.assertEqual(len(enabled.team_members), 1)
        self.assertEqual(len(enabled.capacity_allocations), 1)
        self.assertEqual(len(enabled.strategy_signals), 1)
        self.assertIn("File: team (team.json)", enabled.sources)
        self.assertIn("File: allocations (allocations.json)", enabled.sources)
        self.assertIn("File: strategy (strategy.json)", enabled.sources)

    def test_brief_qe_context_is_capped_and_sets_qe_only_focus(self) -> None:
        snapshot = Snapshot(
            as_of=datetime(2026, 5, 6, tzinfo=timezone.utc),
            team_members=[
                load_team_from_json(
                    self._write_temp_json(
                        [
                            {
                                "id": "qe-1",
                                "name": "Ava",
                                "on_vacation": True,
                                "last_one_on_one": "2026-04-01",
                            }
                        ]
                    )
                )[0]
            ],
            capacity_allocations=load_allocations_from_json(
                self._write_temp_json(
                    [{"id": "a-1", "person_id": "qe-1", "app_name": "Checkout", "focus_pct": 80}]
                )
            ),
        )

        bullets, focus = get_brief_bullets_and_focus(
            snapshot,
            {
                "brief": {
                    "include_qe_context": True,
                    "max_bullets": 2,
                    "max_qe_context_bullets": 2,
                },
                "people": {"one_on_one_stale_days": 21},
            },
        )

        self.assertEqual(len(bullets), 2)
        self.assertEqual(bullets[0], "QE team (file): 1 people, 1 flagged on vacation.")
        self.assertEqual(
            bullets[1],
            "1:1 hygiene: 1 member(s) past 21d or missing last 1:1 date.",
        )
        self.assertEqual(
            focus,
            "Reconcile team capacity and sprint allocations with strategy signals; pick 1\u20132 leadership moves today.",
        )

    def _write_temp_json(self, payload: object) -> Path:
        handle = tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False)
        with handle:
            json.dump(payload, handle)
        return Path(handle.name)


if __name__ == "__main__":
    unittest.main()
