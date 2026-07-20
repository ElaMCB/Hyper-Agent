import unittest
from datetime import timezone

from src.shadow.adapters.gmail import _header_map, _parse_internal_date


class GmailAdapterTests(unittest.TestCase):
    def test_header_map_normalizes_names_and_ignores_incomplete_rows(self):
        headers = _header_map(
            {
                "headers": [
                    {"name": "Subject", "value": "Release approval"},
                    {"name": "FROM", "value": "lead@example.com"},
                    {"name": "", "value": "ignored"},
                    {"value": "missing name"},
                ]
            }
        )

        self.assertEqual(
            headers,
            {
                "subject": "Release approval",
                "from": "lead@example.com",
            },
        )

    def test_parse_internal_date_returns_utc_datetime_or_none(self):
        parsed = _parse_internal_date("1714608000000")

        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.tzinfo, timezone.utc)
        self.assertEqual(parsed.isoformat(), "2024-05-02T00:00:00+00:00")
        self.assertIsNone(_parse_internal_date(None))
        self.assertIsNone(_parse_internal_date("not-a-timestamp"))


if __name__ == "__main__":
    unittest.main()
