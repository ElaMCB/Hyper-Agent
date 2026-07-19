import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError

from src.shadow.adapters.aqua import load_aqua_report


def _payload(snapshot_id: str) -> dict:
    return {
        "aqua_report": {
            "version": "0.1.0",
            "snapshot_id": snapshot_id,
            "generated_at": "2026-07-19T10:00:00Z",
            "scenarios": [],
        }
    }


class AquaEndpointTests(unittest.TestCase):
    def test_missing_report_file_loads_configured_endpoint_with_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch(
                "src.shadow.adapters.aqua._load_json_from_endpoint",
                return_value=_payload("remote-snapshot"),
            ) as fetch:
                report, notes = load_aqua_report(
                    root,
                    {
                        "enabled": True,
                        "report_path": "data/missing-aqua-report.json",
                        "endpoint": "https://aqua.example/report.json",
                        "timeout_seconds": 3,
                    },
                )

        fetch.assert_called_once_with("https://aqua.example/report.json", 3)
        self.assertIsNotNone(report)
        assert report is not None
        self.assertEqual(report.snapshot_id, "remote-snapshot")
        self.assertEqual(notes, [])

    def test_existing_report_file_takes_precedence_over_endpoint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report_path = root / "aqua-report.json"
            report_path.write_text(json.dumps(_payload("local-snapshot")), encoding="utf-8")

            with patch(
                "src.shadow.adapters.aqua._load_json_from_endpoint",
                return_value=_payload("remote-snapshot"),
            ) as fetch:
                report, notes = load_aqua_report(
                    root,
                    {
                        "enabled": True,
                        "report_path": report_path.name,
                        "endpoint": "https://aqua.example/report.json",
                    },
                )

        fetch.assert_not_called()
        self.assertIsNotNone(report)
        assert report is not None
        self.assertEqual(report.snapshot_id, "local-snapshot")
        self.assertEqual(notes, [])

    def test_endpoint_failure_is_reported_without_aborting_snapshot_input(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch(
                "src.shadow.adapters.aqua._load_json_from_endpoint",
                side_effect=URLError("service unavailable"),
            ):
                report, notes = load_aqua_report(
                    root,
                    {
                        "enabled": True,
                        "report_path": "missing-aqua-report.json",
                        "endpoint": "https://aqua.example/report.json",
                    },
                )

        self.assertIsNone(report)
        self.assertEqual(len(notes), 1)
        self.assertIn("AQUA endpoint:", notes[0])
        self.assertIn("service unavailable", notes[0])


if __name__ == "__main__":
    unittest.main()
