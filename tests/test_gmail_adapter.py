import unittest
from datetime import timezone

from src.shadow.adapters.gmail import _header_map, _parse_internal_date


class GmailAdapterParsingTests(unittest.TestCase):
    def test_header_map_normalizes_header_names_and_ignores_blank_names(self):
        payload = {
            "headers": [
                {"name": "Subject", "value": "Sprint risks"},
                {"name": "FROM", "value": "lead@example.com"},
                {"name": "", "value": "ignored"},
                {"value": "also ignored"},
                {"name": "Subject", "value": "Updated sprint risks"},
            ]
        }

        self.assertEqual(
            _header_map(payload),
            {"subject": "Updated sprint risks", "from": "lead@example.com"},
        )

    def test_header_map_handles_missing_or_empty_headers(self):
        self.assertEqual(_header_map({}), {})
        self.assertEqual(_header_map({"headers": None}), {})

    def test_parse_internal_date_returns_utc_datetime_for_epoch_milliseconds(self):
        parsed = _parse_internal_date("1700000000123")

        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.tzinfo, timezone.utc)
        self.assertEqual(parsed.isoformat(), "2023-11-14T22:13:20.123000+00:00")

    def test_parse_internal_date_rejects_missing_or_malformed_values(self):
        self.assertIsNone(_parse_internal_date(None))
        self.assertIsNone(_parse_internal_date(""))
        self.assertIsNone(_parse_internal_date("not-ms"))


if __name__ == "__main__":
    unittest.main()
