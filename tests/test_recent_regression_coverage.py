import sys
import types
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from src.shadow.adapters.gmail import fetch_gmail_messages
from src.shadow.capabilities.brief import get_brief_bullets_and_focus
from src.shadow.capabilities.headquarters import render_headquarters_html
from src.shadow.capabilities.people_capacity import render_people_capacity_md
from src.shadow.models import MailMessage, Snapshot, TeamMember
from src.shadow.snapshot import build_snapshot


class GmailSnapshotRegressionTests(unittest.TestCase):
    def test_gmail_failure_records_note_without_claiming_empty_inbox(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = {
                "gmail": {"enabled": True},
                "data": {
                    "load_defects": False,
                    "load_test_runs": False,
                    "load_team": False,
                    "load_allocations": False,
                    "load_strategy": False,
                },
            }

            with patch(
                "src.shadow.snapshot.fetch_gmail_messages",
                return_value=([], ["Gmail: OAuth client JSON not found at /tmp/missing.json"]),
            ):
                snapshot = build_snapshot(root, config)

        self.assertIn("Gmail: OAuth client JSON not found", snapshot.notes[0])
        self.assertFalse(
            any("Gmail: connected (0 messages" in source for source in snapshot.sources),
            snapshot.sources,
        )
        self.assertIn("(No sources", snapshot.sources[0])


class GmailAdapterRegressionTests(unittest.TestCase):
    def test_fetch_gmail_messages_maps_metadata_and_skips_failed_fetches(self):
        calls = {}

        class FakeCredentials:
            expired = False
            refresh_token = None
            valid = True

            @classmethod
            def from_authorized_user_file(cls, path, scopes):
                calls["token_path"] = path
                calls["scopes"] = scopes
                return cls()

            def to_json(self):
                return "{}"

        class FakeRequest:
            def __init__(self, payload=None, exc=None):
                self.payload = payload
                self.exc = exc

            def execute(self):
                if self.exc:
                    raise self.exc
                return self.payload

        class FakeMessages:
            def list(self, **kwargs):
                calls["list_kwargs"] = kwargs
                return FakeRequest({"messages": [{"id": "msg-1"}, {"id": "skip-me"}]})

            def get(self, **kwargs):
                if kwargs["id"] == "skip-me":
                    return FakeRequest(exc=RuntimeError("metadata unavailable"))
                calls["get_kwargs"] = kwargs
                return FakeRequest(
                    {
                        "payload": {
                            "headers": [
                                {"name": "Subject", "value": "S" * 510},
                                {"name": "From", "value": "sender@example.com"},
                            ]
                        },
                        "snippet": "line\r" + ("x" * 320),
                        "internalDate": "1717243200000",
                        "labelIds": ["INBOX", "UNREAD"],
                    }
                )

        class FakeUsers:
            def __init__(self):
                self._messages = FakeMessages()

            def messages(self):
                return self._messages

        class FakeService:
            def __init__(self):
                self._users = FakeUsers()

            def users(self):
                return self._users

        def fake_build(*args, **kwargs):
            calls["build_args"] = args
            calls["build_kwargs"] = kwargs
            return FakeService()

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
        modules["google_auth_oauthlib.flow"].InstalledAppFlow = object
        modules["google.auth.transport.requests"].Request = object
        modules["googleapiclient.discovery"].build = fake_build

        with TemporaryDirectory() as tmp, patch.dict(sys.modules, modules):
            root = Path(tmp)
            (root / "secrets").mkdir()
            (root / "secrets" / "client.json").write_text("{}", encoding="utf-8")
            (root / "secrets" / "token.json").write_text("{}", encoding="utf-8")

            messages, notes = fetch_gmail_messages(
                root,
                {
                    "credentials_file": "secrets/client.json",
                    "token_file": "secrets/token.json",
                    "query": "is:unread",
                    "max_messages": 2,
                },
            )

        self.assertEqual([], notes)
        self.assertEqual(1, len(messages))
        message = messages[0]
        self.assertEqual("msg-1", message.id)
        self.assertEqual("S" * 500, message.subject)
        self.assertEqual("sender@example.com", message.from_addr)
        self.assertEqual(300, len(message.snippet))
        self.assertTrue(message.snippet.startswith("line "))
        self.assertEqual(datetime(2024, 6, 1, 12, 0, tzinfo=timezone.utc), message.internal_date)
        self.assertTrue(message.is_unread)
        self.assertEqual(
            {"userId": "me", "q": "is:unread", "maxResults": 2},
            calls["list_kwargs"],
        )
        self.assertEqual("metadata", calls["get_kwargs"]["format"])
        self.assertEqual(["Subject", "From", "Date"], calls["get_kwargs"]["metadataHeaders"])


class BriefRegressionTests(unittest.TestCase):
    def test_personal_only_gmail_brief_prioritizes_inbox_and_focus(self):
        snapshot = Snapshot(
            as_of=datetime(2026, 6, 3, 10, 0, tzinfo=timezone.utc),
            sources=["Gmail: 2 message(s)"],
            mail_messages=[
                MailMessage(
                    id="1",
                    subject="Board packet review",
                    from_addr="chief@example.com",
                    snippet="Please review.",
                    is_unread=True,
                ),
                MailMessage(
                    id="2",
                    subject="Newsletter",
                    from_addr="news@example.com",
                    snippet="Digest",
                    is_unread=False,
                ),
            ],
        )

        bullets, suggested = get_brief_bullets_and_focus(
            snapshot,
            {"brief": {"max_bullets": 4}},
        )

        self.assertEqual("Gmail: 2 in view, 1 unread.", bullets[0])
        self.assertIn("Board packet review", bullets[1])
        self.assertIn("Newsletter", bullets[2])
        self.assertNotIn("No defect data", "\n".join(bullets))
        self.assertEqual(
            "Triage unread Gmail; reply, archive, or snooze so nothing important slips.",
            suggested,
        )


class QePeopleRegressionTests(unittest.TestCase):
    def test_people_capacity_flags_morale_vacation_and_stale_one_on_one(self):
        snapshot = Snapshot(
            as_of=datetime(2026, 6, 3, 10, 0, tzinfo=timezone.utc),
            team_members=[
                TeamMember(
                    id="qe-001",
                    name="Alex Kim",
                    role="Senior QE",
                    skills=["API testing", "CI", "Java"],
                    morale_flag="green",
                    last_one_on_one=datetime(2026, 5, 28, tzinfo=timezone.utc),
                    performance_note="On track",
                ),
                TeamMember(
                    id="qe-002",
                    name="Jordan Lee",
                    role="QE II",
                    skills=["UI", "Accessibility"],
                    on_vacation=True,
                    morale_flag="amber",
                    last_one_on_one=datetime(2026, 3, 1, tzinfo=timezone.utc),
                    performance_note="Check workload after PTO",
                ),
            ],
        )

        markdown = render_people_capacity_md(
            snapshot,
            {"people": {"one_on_one_stale_days": 21}},
        )

        self.assertIn("**Headcount in file:** 2", markdown)
        self.assertIn("**On vacation (flag):** 1", markdown)
        self.assertIn("**Morale watch (amber/red):** Jordan Lee", markdown)
        self.assertIn("**1:1 stale (>21d or missing):** Jordan Lee", markdown)
        self.assertIn("| Jordan Lee | QE II | UI, Accessibility | Yes", markdown)
        self.assertIn("Check workload after PTO", markdown)


class HeadquartersRegressionTests(unittest.TestCase):
    def test_headquarters_escapes_gmail_and_qe_table_content(self):
        snapshot = Snapshot(
            as_of=datetime(2026, 6, 3, 10, 0, tzinfo=timezone.utc),
            sources=["Gmail: 1 message(s)", "File: team (team.json)"],
            mail_messages=[
                MailMessage(
                    id="mail-123456789012345",
                    subject="<script>alert('mail')</script>",
                    from_addr="bad@example.com",
                    snippet="<b>urgent</b>",
                    internal_date=datetime(2026, 6, 3, 9, 30, tzinfo=timezone.utc),
                    is_unread=True,
                )
            ],
            team_members=[
                TeamMember(
                    id="qe-001",
                    name="Jordan <Lead>",
                    role="QE",
                    skills=["UI"],
                    morale_flag="amber",
                    performance_note="<img src=x onerror=alert(1)>",
                )
            ],
        )

        html = render_headquarters_html(
            snapshot,
            {
                "brief": {"max_bullets": 5},
                "headquarters": {
                    "title": "Shadow",
                    "show_qe_panels": True,
                    "max_mail_rows": 5,
                    "max_team_rows": 5,
                },
            },
            full_brief_markdown="# Brief\n\n<script>raw</script>",
        )

        self.assertIn("&lt;script&gt;alert(&#x27;mail&#x27;)&lt;/script&gt;", html)
        self.assertIn("&lt;b&gt;urgent&lt;/b&gt;", html)
        self.assertIn("Jordan &lt;Lead&gt;", html)
        self.assertIn("&lt;img src=x onerror=alert(1)&gt;", html)
        self.assertIn("&lt;script&gt;raw&lt;/script&gt;", html)
        self.assertNotIn("<script>alert('mail')</script>", html)
        self.assertNotIn("<b>urgent</b>", html)
        self.assertNotIn("<script>raw</script>", html)


if __name__ == "__main__":
    unittest.main()
