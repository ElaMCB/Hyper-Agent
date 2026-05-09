import json
import sys
import tempfile
import types
import unittest
from datetime import timezone
from pathlib import Path
from unittest.mock import patch

from src.shadow.adapters.gmail import _header_map, _parse_internal_date, fetch_gmail_messages


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

    def test_fetch_messages_maps_gmail_metadata_without_network_or_browser(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            credentials_path = root / "secrets" / "client.json"
            token_path = root / "secrets" / "token.json"
            credentials_path.parent.mkdir()
            credentials_path.write_text("{}", encoding="utf-8")
            token_path.write_text("{}", encoding="utf-8")

            installed_modules, recorder = _fake_google_modules()
            with patch.dict(sys.modules, installed_modules), patch.dict(
                "os.environ",
                {"GMAIL_OAUTH_CLIENT_JSON": "", "GMAIL_TOKEN_JSON": ""},
                clear=False,
            ):
                messages, notes = fetch_gmail_messages(
                    root,
                    {
                        "credentials_file": "secrets/client.json",
                        "token_file": "secrets/token.json",
                        "query": "   ",
                        "max_messages": 0,
                    },
                )

        self.assertEqual(notes, [])
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].id, "m-1")
        self.assertEqual(messages[0].subject, "Checkout & refunds")
        self.assertEqual(messages[0].from_addr, "Lead <lead@example.com>")
        self.assertEqual(messages[0].snippet, "Line one  line two")
        self.assertTrue(messages[0].is_unread)
        self.assertEqual(messages[0].internal_date.isoformat(), "2023-11-14T22:13:20+00:00")
        self.assertEqual(
            recorder["list_call"],
            {"userId": "me", "q": None, "maxResults": 1},
        )
        self.assertEqual(
            recorder["get_call"],
            {
                "userId": "me",
                "id": "m-1",
                "format": "metadata",
                "metadataHeaders": ["Subject", "From", "Date"],
            },
        )
        self.assertEqual(json.loads(token_path.read_text(encoding="utf-8")), {"token": "saved"})


def _fake_google_modules():
    recorder = {}

    class FakeCredentials:
        expired = False
        refresh_token = None
        valid = True

        @classmethod
        def from_authorized_user_file(cls, path, scopes):
            recorder["token_path"] = path
            recorder["scopes"] = scopes
            return cls()

        def to_json(self):
            return json.dumps({"token": "saved"})

    class FakeMessages:
        def list(self, **kwargs):
            recorder["list_call"] = kwargs
            return types.SimpleNamespace(execute=lambda: {"messages": [{"id": "m-1"}]})

        def get(self, **kwargs):
            recorder["get_call"] = kwargs
            return types.SimpleNamespace(
                execute=lambda: {
                    "payload": {
                        "headers": [
                            {"name": "Subject", "value": "Checkout & refunds"},
                            {"name": "From", "value": "Lead <lead@example.com>"},
                        ]
                    },
                    "snippet": "Line one\r line two",
                    "internalDate": "1700000000000",
                    "labelIds": ["INBOX", "UNREAD"],
                }
            )

    class FakeUsers:
        def messages(self):
            return FakeMessages()

    class FakeService:
        def users(self):
            return FakeUsers()

    class FakeFlow:
        @classmethod
        def from_client_secrets_file(cls, *args, **kwargs):
            raise AssertionError("existing valid token should avoid browser sign-in")

    def fake_build(*args, **kwargs):
        recorder["build_call"] = (args, kwargs)
        return FakeService()

    modules = {
        "google": types.ModuleType("google"),
        "google.oauth2": types.ModuleType("google.oauth2"),
        "google.oauth2.credentials": types.SimpleNamespace(Credentials=FakeCredentials),
        "google_auth_oauthlib": types.ModuleType("google_auth_oauthlib"),
        "google_auth_oauthlib.flow": types.SimpleNamespace(InstalledAppFlow=FakeFlow),
        "google.auth": types.ModuleType("google.auth"),
        "google.auth.transport": types.ModuleType("google.auth.transport"),
        "google.auth.transport.requests": types.SimpleNamespace(Request=lambda: object()),
        "googleapiclient": types.ModuleType("googleapiclient"),
        "googleapiclient.discovery": types.SimpleNamespace(build=fake_build),
    }
    return modules, recorder


if __name__ == "__main__":
    unittest.main()
