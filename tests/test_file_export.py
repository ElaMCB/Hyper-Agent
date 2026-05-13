import json
import unittest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from src.shadow.adapters.file_export import (
    FileExportAdapter,
    load_allocations_from_json,
    load_defects_from_json,
)


class FileExportAdapterTests(unittest.TestCase):
    def test_load_defects_from_wrapped_json_maps_aliases_and_dates(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "defects.json"
            path.write_text(
                json.dumps(
                    {
                        "issues": [
                            {
                                "key": "BUG-123",
                                "summary": "Checkout failure",
                                "priority": "High",
                                "state": "Active",
                                "created_at": "2026-05-01T12:34:56Z",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            defects = load_defects_from_json(path)

        self.assertEqual(len(defects), 1)
        self.assertEqual(defects[0].id, "BUG-123")
        self.assertEqual(defects[0].title, "Checkout failure")
        self.assertEqual(defects[0].severity, "High")
        self.assertEqual(defects[0].status, "Active")
        self.assertEqual(defects[0].created, datetime(2026, 5, 1, 12, 34, 56))

    def test_load_allocations_coerces_valid_focus_and_ignores_bad_values(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "allocations.json"
            path.write_text(
                json.dumps(
                    {
                        "assignments": [
                            {
                                "key": "a1",
                                "person": "u1",
                                "name": "Riley",
                                "app": "Payments",
                                "sprint": "S42",
                                "pct": "75",
                            },
                            {
                                "key": "a2",
                                "person": "u2",
                                "name": "Morgan",
                                "app": "Orders",
                                "sprint": "S42",
                                "focus_pct": "not-a-number",
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )

            allocations = load_allocations_from_json(path)

        self.assertEqual([a.focus_pct for a in allocations], [75, None])
        self.assertEqual(allocations[0].person_id, "u1")
        self.assertEqual(allocations[0].app_name, "Payments")

    def test_get_defects_uses_csv_parser_for_csv_exports(self):
        with TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            (data_dir / "defects.csv").write_text(
                "Key,Summary,priority,Status,Created\n"
                "BUG-7,CSV imported bug,Critical,New,13/05/2026\n",
                encoding="utf-8",
            )

            defects = FileExportAdapter(data_dir).get_defects("defects.csv")

        self.assertEqual(len(defects), 1)
        self.assertEqual(defects[0].id, "BUG-7")
        self.assertEqual(defects[0].title, "CSV imported bug")
        self.assertEqual(defects[0].severity, "Critical")
        self.assertEqual(defects[0].created, datetime(2026, 5, 13))


if __name__ == "__main__":
    unittest.main()
