import unittest
from datetime import timezone

from src.shadow.adapters.gmail import _header_map, _parse_internal_date


class GmailAdapterParsingTests(unittest.TestCase):
    def test_header_map_normalizes_names_and_ignores_empty_headers(self):
        payload = {
            "headers": [
                {"name": "Subject", "value": "Launch review"},
                {"name": "FROM", "value": "qa@example.com"},
                {"name": "", "value": "ignored"},
                {"value": "also ignored"},
            ]
        }

        self.assertEqual(
            _header_map(payload),
            {"subject": "Launch review", "from": "qa@example.com"},
        )

    def test_parse_internal_date_returns_utc_datetime_or_none(self):
        parsed = _parse_internal_date("1714670400000")

        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.tzinfo, timezone.utc)
        self.assertEqual(parsed.strftime("%Y-%m-%dT%H:%M:%SZ"), "2024-05-02T17:20:00Z")
        self.assertIsNone(_parse_internal_date(None))
        self.assertIsNone(_parse_internal_date("not-millis"))


if __name__ == "__main__":
    unittest.main()
