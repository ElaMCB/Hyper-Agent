import os
import sys
import types
import unittest
from datetime import timezone
from tempfile import TemporaryDirectory
from unittest.mock import patch

from src.shadow.adapters.gmail import _header_map, _parse_internal_date, fetch_gmail_messages


class GmailAdapterTests(unittest.TestCase):
    def test_header_map_normalizes_names_and_last_duplicate_wins(self):
        payload = {
            "headers": [
                {"name": "Subject", "value": "old"},
                {"name": "FROM", "value": "sender@example.com"},
                {"name": "subject", "value": "new"},
                {"name": "", "value": "ignored"},
            ]
        }

        self.assertEqual(
            _header_map(payload),
            {"subject": "new", "from": "sender@example.com"},
        )

    def test_parse_internal_date_returns_utc_datetime_or_none(self):
        parsed = _parse_internal_date("1735689600000")

        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.tzinfo, timezone.utc)
        self.assertEqual(parsed.isoformat(), "2025-01-01T00:00:00+00:00")
        self.assertIsNone(_parse_internal_date(None))
        self.assertIsNone(_parse_internal_date(""))
        self.assertIsNone(_parse_internal_date("not-a-date"))

    def test_fetch_gmail_messages_maps_metadata_and_skips_failed_messages(self):
        class FakeCredentials:
            valid = True
            expired = False
            refresh_token = None

            @classmethod
            def from_authorized_user_file(cls, _path, _scopes):
                return cls()

            def to_json(self):
                return "{}"

        class FakeFlow:
            @classmethod
            def from_client_secrets_file(cls, _path, _scopes):
                return cls()

            def run_local_server(self, port, open_browser):
                self.port = port
                self.open_browser = open_browser
                return FakeCredentials()

        class FakeRequest:
            pass

        class FakeExecutable:
            def __init__(self, result):
                self.result = result

            def execute(self):
                return self.result

        class FakeMessages:
            def __init__(self):
                self.list_kwargs = None

            def list(self, **kwargs):
                self.list_kwargs = kwargs
                return FakeExecutable({"messages": [{"id": "a"}, {"id": "b"}, {"id": "c"}]})

            def get(self, **kwargs):
                message_id = kwargs["id"]
                if message_id == "c":
                    raise RuntimeError("detail fetch failed")
                if message_id == "b":
                    return FakeExecutable(
                        {
                            "payload": {"headers": [{"name": "From", "value": "nobody@example.com"}]},
                            "snippet": "No subject",
                            "labelIds": [],
                        }
                    )
                return FakeExecutable(
                    {
                        "payload": {
                            "headers": [
                                {"name": "Subject", "value": "S" * 600},
                                {"name": "From", "value": "sender@example.com"},
                            ]
                        },
                        "snippet": "hello\rworld",
                        "internalDate": "1735689600000",
                        "labelIds": ["INBOX", "UNREAD"],
                    }
                )

        class FakeService:
            def __init__(self):
                self.messages_resource = FakeMessages()

            def users(self):
                return self

            def messages(self):
                return self.messages_resource

        service = FakeService()

        def fake_build(*args, **kwargs):
            self.assertEqual(args[:2], ("gmail", "v1"))
            self.assertFalse(kwargs["cache_discovery"])
            return service

        modules = {
            "google": types.ModuleType("google"),
            "google.oauth2": types.ModuleType("google.oauth2"),
            "google.oauth2.credentials": types.ModuleType("google.oauth2.credentials"),
            "google_auth_oauthlib": types.ModuleType("google_auth_oauthlib"),
            "google_auth_oauthlib.flow": types.ModuleType("google_auth_oauthlib.flow"),
            "google.auth": types.ModuleType("google.auth"),
            "google.auth.transport": types.ModuleType("google.auth.transport"),
            "google.auth.transport.requests": types.ModuleType("google.auth.transport.requests"),
            "googleapiclient": types.ModuleType("googleapiclient"),
            "googleapiclient.discovery": types.ModuleType("googleapiclient.discovery"),
        }
        modules["google.oauth2.credentials"].Credentials = FakeCredentials
        modules["google_auth_oauthlib.flow"].InstalledAppFlow = FakeFlow
        modules["google.auth.transport.requests"].Request = FakeRequest
        modules["googleapiclient.discovery"].build = fake_build

        with TemporaryDirectory() as tmp, patch.dict(sys.modules, modules), patch.dict(
            os.environ,
            {"GMAIL_OAUTH_CLIENT_JSON": "", "GMAIL_TOKEN_JSON": ""},
        ):
            root = __import__("pathlib").Path(tmp)
            (root / "client.json").write_text("{}", encoding="utf-8")

            messages, notes = fetch_gmail_messages(
                root,
                {
                    "credentials_file": "client.json",
                    "token_file": "token.json",
                    "query": "label:unread",
                    "max_messages": 5,
                },
            )

        self.assertEqual(notes, [])
        self.assertEqual(service.messages_resource.list_kwargs["maxResults"], 5)
        self.assertEqual(service.messages_resource.list_kwargs["q"], "label:unread")
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0].id, "a")
        self.assertEqual(messages[0].subject, "S" * 500)
        self.assertEqual(messages[0].snippet, "hello world")
        self.assertTrue(messages[0].is_unread)
        self.assertEqual(messages[1].subject, "(no subject)")
        self.assertFalse(messages[1].is_unread)


if __name__ == "__main__":
    unittest.main()
