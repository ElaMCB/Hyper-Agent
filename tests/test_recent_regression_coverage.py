import json
import sys
import types
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from src.shadow.adapters.file_export import (
    load_allocations_from_json,
    load_strategy_from_json,
    load_team_from_json,
)
from src.shadow.adapters.gmail import fetch_gmail_messages
from src.shadow.capabilities.resource_allocation import render_resource_allocation_md
from src.shadow.capabilities.strategy_lens import render_strategy_md
from src.shadow.models import CapacityAllocation, Snapshot, StrategySignal
from src.shadow.snapshot import build_snapshot


class RecentRegressionCoverageTests(unittest.TestCase):
    def test_file_export_loaders_coerce_wrapped_qe_exports(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            team_path = root / "team.json"
            alloc_path = root / "allocations.json"
            strategy_path = root / "strategy.json"

            team_path.write_text(
                json.dumps(
                    {
                        "members": [
                            {
                                "employee_id": "qe-1",
                                "name": "Alex",
                                "skills": "API, UI , CI",
                                "on_vacation": "false",
                                "last_1_1": "2026-04-01",
                            },
                            {
                                "id": "qe-2",
                                "name": "Jordan",
                                "skills": ["Accessibility"],
                                "vacation": "yes",
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )
            alloc_path.write_text(
                json.dumps(
                    {
                        "assignments": [
                            {
                                "key": "al-zero",
                                "person": "qe-1",
                                "app": "Billing",
                                "focus_pct": 0,
                                "allocation_pct": 80,
                            },
                            {
                                "id": "al-invalid",
                                "person_id": "qe-2",
                                "name": "Jordan",
                                "pct": "n/a",
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )
            strategy_path.write_text(
                json.dumps(
                    {
                        "signals": [
                            {
                                "key": "st-1",
                                "theme": "Coverage",
                                "title": "Protect checkout path",
                                "priority": "p1",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            team = load_team_from_json(team_path)
            allocations = load_allocations_from_json(alloc_path)
            strategy = load_strategy_from_json(strategy_path)

        self.assertEqual(["API", "UI", "CI"], team[0].skills)
        self.assertFalse(team[0].on_vacation)
        self.assertTrue(team[1].on_vacation)
        self.assertEqual("qe-1", allocations[0].person_id)
        self.assertEqual(0, allocations[0].focus_pct)
        self.assertIsNone(allocations[1].focus_pct)
        self.assertEqual("Coverage", strategy[0].pillar)
        self.assertEqual("Protect checkout path", strategy[0].summary)

    def test_build_snapshot_loads_qe_files_and_keeps_gmail_failure_in_notes(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            data = root / "data"
            data.mkdir()
            (data / "team.json").write_text(
                json.dumps([{"id": "qe-1", "name": "Alex", "on_vacation": False}]),
                encoding="utf-8",
            )
            (data / "allocations.json").write_text(
                json.dumps([{"id": "al-1", "person_id": "qe-1", "app_name": "Billing", "focus_pct": 50}]),
                encoding="utf-8",
            )
            (data / "strategy.json").write_text(
                json.dumps([{"id": "st-1", "pillar": "Automation", "summary": "Grow API checks"}]),
                encoding="utf-8",
            )
            config = {
                "data": {
                    "dir": "data",
                    "load_defects": False,
                    "load_test_runs": False,
                    "load_team": True,
                    "load_allocations": True,
                    "load_strategy": True,
                },
                "gmail": {"enabled": True},
            }

            gmail_note = "Gmail: OAuth client JSON not found at /tmp/missing.json"
            with patch("src.shadow.snapshot.fetch_gmail_messages", return_value=([], [gmail_note])):
                snapshot = build_snapshot(root, config)

        self.assertEqual(1, len(snapshot.team_members))
        self.assertEqual(1, len(snapshot.capacity_allocations))
        self.assertEqual(1, len(snapshot.strategy_signals))
        self.assertIn("File: team (team.json)", snapshot.sources)
        self.assertIn("File: allocations (allocations.json)", snapshot.sources)
        self.assertIn("File: strategy (strategy.json)", snapshot.sources)
        self.assertEqual([gmail_note], snapshot.notes)
        self.assertNotIn("Gmail: connected (0 messages for this query)", snapshot.sources)

    def test_gmail_fetch_maps_metadata_and_skips_failed_message_fetches(self):
        class FakeCredentials:
            valid = False
            expired = False
            refresh_token = None

            @classmethod
            def from_authorized_user_file(cls, *_args, **_kwargs):
                return cls()

        class FakeAuthorizedCredentials:
            valid = True
            expired = False
            refresh_token = None

            def to_json(self):
                return "{}"

        class FakeFlow:
            @classmethod
            def from_client_secrets_file(cls, *_args, **_kwargs):
                return cls()

            def run_local_server(self, **_kwargs):
                return FakeAuthorizedCredentials()

        class FakeRequest:
            pass

        class FakeExecutable:
            def __init__(self, value=None, error=None):
                self.value = value
                self.error = error

            def execute(self):
                if self.error:
                    raise self.error
                return self.value

        class FakeMessages:
            def list(self, **_kwargs):
                return FakeExecutable({"messages": [{"id": "ok"}, {"id": "bad"}]})

            def get(self, **kwargs):
                if kwargs["id"] == "bad":
                    return FakeExecutable(error=RuntimeError("transient fetch failure"))
                return FakeExecutable(
                    {
                        "payload": {
                            "headers": [
                                {"name": "Subject", "value": "S" * 600},
                                {"name": "From", "value": "sender@example.test"},
                                {"name": "Date", "value": "ignored by adapter"},
                            ]
                        },
                        "internalDate": "1700000000000",
                        "labelIds": ["INBOX", "UNREAD"],
                        "snippet": "Line one\r" + ("x" * 400),
                    }
                )

        class FakeUsers:
            def messages(self):
                return FakeMessages()

        class FakeService:
            def users(self):
                return FakeUsers()

        def fake_build(*_args, **_kwargs):
            return FakeService()

        fake_modules = self._google_modules(
            FakeCredentials,
            FakeFlow,
            FakeRequest,
            fake_build,
        )

        with TemporaryDirectory() as td, patch.dict(sys.modules, fake_modules):
            root = Path(td)
            (root / "client.json").write_text("{}", encoding="utf-8")
            messages, notes = fetch_gmail_messages(
                root,
                {
                    "credentials_file": "client.json",
                    "token_file": "secrets/token.json",
                    "query": "is:unread",
                    "max_messages": 2,
                },
            )

        self.assertEqual([], notes)
        self.assertEqual(1, len(messages))
        msg = messages[0]
        self.assertEqual("ok", msg.id)
        self.assertEqual(500, len(msg.subject))
        self.assertEqual("sender@example.test", msg.from_addr)
        self.assertEqual(300, len(msg.snippet))
        self.assertNotIn("\r", msg.snippet)
        self.assertTrue(msg.is_unread)
        self.assertEqual(datetime.fromtimestamp(1700000000, tz=timezone.utc), msg.internal_date)

    def test_qe_allocation_warning_and_strategy_priority_sorting(self):
        snapshot = Snapshot(
            as_of=datetime(2026, 5, 1, tzinfo=timezone.utc),
            capacity_allocations=[
                CapacityAllocation(
                    id="al-1",
                    person_id="qe-001",
                    person_name="Alex Kim",
                    app_name="Billing API",
                    sprint_label="2026-W18",
                    focus_pct=60,
                ),
                CapacityAllocation(
                    id="al-2",
                    person_id="qe-001",
                    person_name="Alex Kim",
                    app_name="Mobile checkout",
                    sprint_label="2026-W18",
                    focus_pct=50,
                ),
            ],
            strategy_signals=[
                StrategySignal(
                    id="st-2",
                    pillar="Quality ownership",
                    summary="Clarify test responsibility",
                    priority="P1",
                    horizon="2026-H2",
                ),
                StrategySignal(
                    id="st-1",
                    pillar="Test automation",
                    summary="Raise API coverage",
                    priority="p0",
                    horizon="FY26",
                ),
            ],
        )

        allocation_md = render_resource_allocation_md(snapshot, {})
        strategy_md = render_strategy_md(snapshot, {})

        self.assertIn("**Warning:** focus % sums > 100", allocation_md)
        self.assertIn("- qe-001 @ 2026-W18", allocation_md)
        self.assertLess(
            strategy_md.index("## Test automation"),
            strategy_md.index("## Quality ownership"),
        )

    @staticmethod
    def _google_modules(credentials_cls, flow_cls, request_cls, build_func):
        google = types.ModuleType("google")
        google_oauth2 = types.ModuleType("google.oauth2")
        google_oauth2_credentials = types.ModuleType("google.oauth2.credentials")
        google_oauth2_credentials.Credentials = credentials_cls
        google_auth = types.ModuleType("google.auth")
        google_auth_transport = types.ModuleType("google.auth.transport")
        google_auth_transport_requests = types.ModuleType("google.auth.transport.requests")
        google_auth_transport_requests.Request = request_cls
        google_auth_oauthlib = types.ModuleType("google_auth_oauthlib")
        google_auth_oauthlib_flow = types.ModuleType("google_auth_oauthlib.flow")
        google_auth_oauthlib_flow.InstalledAppFlow = flow_cls
        googleapiclient = types.ModuleType("googleapiclient")
        googleapiclient_discovery = types.ModuleType("googleapiclient.discovery")
        googleapiclient_discovery.build = build_func
        return {
            "google": google,
            "google.oauth2": google_oauth2,
            "google.oauth2.credentials": google_oauth2_credentials,
            "google.auth": google_auth,
            "google.auth.transport": google_auth_transport,
            "google.auth.transport.requests": google_auth_transport_requests,
            "google_auth_oauthlib": google_auth_oauthlib,
            "google_auth_oauthlib.flow": google_auth_oauthlib_flow,
            "googleapiclient": googleapiclient,
            "googleapiclient.discovery": googleapiclient_discovery,
        }


if __name__ == "__main__":
    unittest.main()
