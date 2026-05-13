import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from src.shadow.adapters.azure_devops import AzureDevOpsAdapter, _work_item_to_defect
from src.shadow.adapters.gmail import _header_map, _parse_internal_date
from src.shadow.output.writer import prune_headquarters_archives


class _Response:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        return None


class GmailMetadataTests(unittest.TestCase):
    def test_header_map_is_case_insensitive_and_skips_blank_names(self):
        payload = {
            "headers": [
                {"name": "Subject", "value": "Release plan"},
                {"name": "FROM", "value": "qa@example.test"},
                {"name": "", "value": "ignored"},
            ]
        }

        self.assertEqual(
            _header_map(payload),
            {"subject": "Release plan", "from": "qa@example.test"},
        )

    def test_parse_internal_date_returns_utc_datetime_or_none(self):
        self.assertEqual(_parse_internal_date("0"), datetime(1970, 1, 1, tzinfo=timezone.utc))
        self.assertIsNone(_parse_internal_date(""))
        self.assertIsNone(_parse_internal_date("not-a-timestamp"))


class AzureDevOpsAdapterTests(unittest.TestCase):
    def test_work_item_to_defect_maps_fields_and_zulu_created_date(self):
        defect = _work_item_to_defect(
            {
                "id": 42,
                "fields": {
                    "System.Title": "Checkout fails for guest users",
                    "System.State": "Active",
                    "Microsoft.VSTS.Common.Severity": "1 - Critical",
                    "System.CreatedDate": "2026-05-13T10:02:25.593Z",
                },
            }
        )

        self.assertEqual(defect.id, "ado-42")
        self.assertEqual(defect.title, "Checkout fails for guest users")
        self.assertEqual(defect.status, "Active")
        self.assertEqual(defect.severity, "1 - Critical")
        self.assertIsNotNone(defect.created)
        self.assertEqual(defect.created.tzinfo, timezone.utc)

    @patch("src.shadow.adapters.azure_devops.requests.get")
    @patch("src.shadow.adapters.azure_devops.requests.post")
    def test_fetch_bugs_runs_wiql_and_fetches_work_items_up_to_limit(self, post, get):
        post.return_value = _Response({"workItems": [{"id": 101}, {"id": 102}, {"id": 103}]})
        get.return_value = _Response(
            {
                "value": [
                    {
                        "id": 101,
                        "fields": {
                            "System.Title": "Payment bug",
                            "System.State": "New",
                            "System.CreatedDate": "2026-05-13T10:00:00Z",
                        },
                    },
                    {
                        "id": 102,
                        "fields": {
                            "System.Title": "Search bug",
                            "System.State": "Active",
                            "Microsoft.VSTS.Common.Severity": "High",
                        },
                    },
                ]
            }
        )

        defects = AzureDevOpsAdapter("org", "Project", "pat", max_items=2).fetch_bugs()

        self.assertEqual([d.id for d in defects], ["ado-101", "ado-102"])
        self.assertEqual(defects[0].severity, "Unknown")
        post.assert_called_once()
        get.assert_called_once()
        self.assertIn("/_apis/wit/wiql?api-version=7.1", post.call_args.args[0])
        self.assertIn("ids=101,102&api-version=7.1", get.call_args.args[0])
        self.assertNotIn("103", get.call_args.args[0])


class HeadquartersWriterTests(unittest.TestCase):
    def test_prune_headquarters_archives_keeps_newest_archives_and_latest_files(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            hq = root / "output" / "headquarters"
            hq.mkdir(parents=True)
            for name in [
                "headquarters-2026-05-13T080000Z.html",
                "headquarters-2026-05-13T090000Z.html",
                "headquarters-2026-05-13T100000Z.html",
            ]:
                (hq / name).write_text(name, encoding="utf-8")
            (hq / "latest.html").write_text("latest", encoding="utf-8")
            (hq / "latest.md").write_text("latest md", encoding="utf-8")

            removed = prune_headquarters_archives(root, "output/headquarters", max_keep=2)

            remaining = sorted(p.name for p in hq.iterdir())

        self.assertEqual(removed, 1)
        self.assertEqual(
            remaining,
            [
                "headquarters-2026-05-13T090000Z.html",
                "headquarters-2026-05-13T100000Z.html",
                "latest.html",
                "latest.md",
            ],
        )


if __name__ == "__main__":
    unittest.main()
