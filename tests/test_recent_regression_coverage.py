import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from src.shadow.adapters.file_export import load_allocations_from_json, load_team_from_json
from src.shadow.adapters.gmail import _header_map, _parse_internal_date
from src.shadow.capabilities.people_capacity import render_people_capacity_md
from src.shadow.capabilities.resource_allocation import render_resource_allocation_md
from src.shadow.snapshot import build_snapshot


class FileExportParsingTests(unittest.TestCase):
    def test_team_loader_coerces_exported_booleans_and_skills(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "team.json"
            path.write_text(
                json.dumps(
                    {
                        "members": [
                            {
                                "id": "qa-1",
                                "name": "Avery",
                                "skills": "api, automation, accessibility",
                                "on_vacation": "false",
                            },
                            {
                                "id": "qa-2",
                                "name": "Blair",
                                "skills": ["mobile", "security"],
                                "vacation": "yes",
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )

            members = load_team_from_json(path)

        self.assertFalse(members[0].on_vacation)
        self.assertEqual(members[0].skills, ["api", "automation", "accessibility"])
        self.assertTrue(members[1].on_vacation)
        self.assertEqual(members[1].skills, ["mobile", "security"])

    def test_allocation_loader_preserves_zero_and_uses_nonblank_aliases(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "allocations.json"
            path.write_text(
                json.dumps(
                    {
                        "assignments": [
                            {
                                "id": "a-0",
                                "person_id": "qa-1",
                                "person_name": "Avery",
                                "app_name": "Checkout",
                                "sprint_label": "S1",
                                "focus_pct": 0,
                                "allocation_pct": 80,
                            },
                            {
                                "id": "a-alias",
                                "person_id": "qa-2",
                                "person_name": "Blair",
                                "app_name": "Search",
                                "sprint_label": "S1",
                                "focus_pct": " ",
                                "pct": "35",
                            },
                            {
                                "id": "a-invalid",
                                "person_id": "qa-3",
                                "focus_pct": "not-a-number",
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )

            allocations = load_allocations_from_json(path)

        self.assertEqual([a.focus_pct for a in allocations], [0, 35, None])

    def test_qe_renderers_show_false_vacation_and_zero_allocation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_dir = root / "data"
            data_dir.mkdir()
            (data_dir / "team.json").write_text(
                json.dumps(
                    [
                        {
                            "id": "qa-1",
                            "name": "Avery",
                            "role": "QE Lead",
                            "on_vacation": "false",
                            "last_one_on_one": "2026-06-01",
                        }
                    ]
                ),
                encoding="utf-8",
            )
            (data_dir / "allocations.json").write_text(
                json.dumps(
                    [
                        {
                            "id": "a-0",
                            "person_id": "qa-1",
                            "person_name": "Avery",
                            "app_name": "Checkout",
                            "sprint_label": "S1",
                            "focus_pct": 0,
                        }
                    ]
                ),
                encoding="utf-8",
            )
            (data_dir / "strategy.json").write_text(
                json.dumps(
                    [
                        {
                            "id": "s-1",
                            "pillar": "Release readiness",
                            "summary": "Protect launch sign-off",
                            "priority": "P0",
                        }
                    ]
                ),
                encoding="utf-8",
            )

            snapshot = build_snapshot(
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

        self.assertEqual(
            snapshot.sources,
            [
                "File: team (team.json)",
                "File: allocations (allocations.json)",
                "File: strategy (strategy.json)",
            ],
        )
        self.assertFalse(snapshot.team_members[0].on_vacation)
        self.assertEqual(snapshot.capacity_allocations[0].focus_pct, 0)
        people_md = render_people_capacity_md(
            snapshot,
            {"people": {"one_on_one_stale_days": 21}},
        )
        allocation_md = render_resource_allocation_md(snapshot, {})
        self.assertIn("| Avery | QE Lead |  | No", people_md)
        self.assertIn("- **Avery** — 0% · sprint `S1`", allocation_md)
        self.assertIn("| Avery | Checkout | S1 | 0 |", allocation_md)


class GmailParsingTests(unittest.TestCase):
    def test_header_map_normalizes_header_names_and_defaults_values(self) -> None:
        payload = {
            "headers": [
                {"name": "Subject", "value": "Launch update"},
                {"name": "FROM", "value": "lead@example.com"},
                {"name": "Date"},
                {"value": "ignored"},
            ]
        }

        self.assertEqual(
            _header_map(payload),
            {"subject": "Launch update", "from": "lead@example.com", "date": ""},
        )

    def test_parse_internal_date_handles_valid_invalid_and_overflow_values(self) -> None:
        parsed = _parse_internal_date("1767225600000")

        self.assertEqual(parsed, datetime(2026, 1, 1, tzinfo=timezone.utc))
        self.assertIsNone(_parse_internal_date(None))
        self.assertIsNone(_parse_internal_date("not-a-date"))
        self.assertIsNone(_parse_internal_date("999999999999999999999999"))


if __name__ == "__main__":
    unittest.main()
