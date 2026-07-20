import unittest
from datetime import timezone

from src.shadow.adapters.gmail import _header_map, _parse_internal_date


class GmailMetadataParsingTests(unittest.TestCase):
    def test_header_map_is_case_insensitive_and_ignores_blank_names(self):
        payload = {
            "headers": [
                {"name": "Subject", "value": "Daily QE update"},
                {"name": "FROM", "value": "lead@example.com"},
                {"name": "", "value": "ignored"},
                {"value": "also ignored"},
            ]
        }

        headers = _header_map(payload)

        self.assertEqual("Daily QE update", headers["subject"])
        self.assertEqual("lead@example.com", headers["from"])
        self.assertNotIn("", headers)

    def test_internal_date_parsing_returns_utc_datetime_or_none(self):
        parsed = _parse_internal_date("1716206400000")

        self.assertIsNotNone(parsed)
        self.assertEqual(timezone.utc, parsed.tzinfo)
        self.assertEqual(2024, parsed.year)
        self.assertIsNone(_parse_internal_date(None))
        self.assertIsNone(_parse_internal_date("not milliseconds"))


if __name__ == "__main__":
    unittest.main()
