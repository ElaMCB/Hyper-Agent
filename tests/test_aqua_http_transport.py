import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.shadow.adapters.aqua import load_aqua_report


class AquaHttpTransportTests(unittest.TestCase):
    def test_endpoint_request_and_response_are_processed_end_to_end(self) -> None:
        payload = {
            "aqua_report": {
                "version": "0.1.0",
                "snapshot_id": "remote-snapshot",
                "generated_at": "2026-07-22T10:00:00Z",
                "scenarios": [],
            }
        }
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps(payload).encode("utf-8")

        with tempfile.TemporaryDirectory() as tmp:
            with patch(
                "src.shadow.adapters.aqua.urlopen",
                return_value=response,
            ) as open_url:
                report, notes = load_aqua_report(
                    Path(tmp),
                    {
                        "enabled": True,
                        "report_path": "missing-report.json",
                        "endpoint": "https://aqua.example/report.json",
                        "timeout_seconds": 4,
                    },
                )

        self.assertIsNotNone(report)
        assert report is not None
        self.assertEqual(report.snapshot_id, "remote-snapshot")
        self.assertEqual(notes, [])

        request = open_url.call_args.args[0]
        self.assertEqual(request.full_url, "https://aqua.example/report.json")
        self.assertEqual(request.get_header("Accept"), "application/json")
        self.assertEqual(open_url.call_args.kwargs, {"timeout": 4})
        response.__exit__.assert_called_once()

    def test_malformed_endpoint_json_is_reported_without_raising(self) -> None:
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b"{not valid json"

        with tempfile.TemporaryDirectory() as tmp:
            with patch("src.shadow.adapters.aqua.urlopen", return_value=response):
                report, notes = load_aqua_report(
                    Path(tmp),
                    {
                        "enabled": True,
                        "report_path": "missing-report.json",
                        "endpoint": "https://aqua.example/report.json",
                    },
                )

        self.assertIsNone(report)
        self.assertEqual(len(notes), 1)
        self.assertIn("AQUA endpoint:", notes[0])


if __name__ == "__main__":
    unittest.main()
