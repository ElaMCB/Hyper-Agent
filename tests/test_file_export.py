import json
import tempfile
import unittest
from pathlib import Path

from src.shadow.adapters.file_export import (
    FileExportAdapter,
    load_allocations_from_json,
    load_team_from_json,
)


class FileExportParsingTests(unittest.TestCase):
    def test_team_loader_parses_string_booleans_without_truthiness_bug(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "team.json"
            path.write_text(
                json.dumps(
                    [
                        {"id": "qe-1", "name": "Alex", "on_vacation": "false"},
                        {"id": "qe-2", "name": "Blair", "vacation": "yes"},
                        {"id": "qe-3", "name": "Casey", "on_vacation": "0"},
                    ]
                ),
                encoding="utf-8",
            )

            members = load_team_from_json(path)

        self.assertEqual([m.on_vacation for m in members], [False, True, False])

    def test_allocation_loader_preserves_zero_focus_percent(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "allocations.json"
            path.write_text(
                json.dumps(
                    [
                        {
                            "id": "a-1",
                            "person_id": "qe-1",
                            "app_name": "Billing",
                            "focus_pct": 0,
                        },
                        {
                            "id": "a-2",
                            "person_id": "qe-2",
                            "app_name": "Checkout",
                            "allocation_pct": "25",
                        },
                    ]
                ),
                encoding="utf-8",
            )

            allocations = load_allocations_from_json(path)

        self.assertEqual([a.focus_pct for a in allocations], [0, 25])

    def test_adapter_returns_empty_lists_for_missing_optional_files(self):
        with tempfile.TemporaryDirectory() as td:
            adapter = FileExportAdapter(Path(td))

            self.assertEqual(adapter.get_team_members(), [])
            self.assertEqual(adapter.get_allocations(), [])
            self.assertEqual(adapter.get_strategy_signals(), [])


if __name__ == "__main__":
    unittest.main()
