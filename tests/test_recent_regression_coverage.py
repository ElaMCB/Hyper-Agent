import html
import json
import sys
import tempfile
import types
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from src.shadow.adapters.file_export import (  # noqa: E402
    load_allocations_from_json,
    load_strategy_from_json,
    load_team_from_json,
)
from src.shadow.adapters.gmail import fetch_gmail_messages  # noqa: E402
from src.shadow.capabilities.brief import get_brief_bullets_and_focus  # noqa: E402
from src.shadow.capabilities.headquarters import render_headquarters_html  # noqa: E402
from src.shadow.capabilities.resource_allocation import render_resource_allocation_md  # noqa: E402
from src.shadow.capabilities.strategy_lens import render_strategy_md  # noqa: E402
from src.shadow.models import (  # noqa: E402
    CapacityAllocation,
    Defect,
    MailMessage,
    Snapshot,
    StrategySignal,
    TeamMember,
    TestRun,
)
from src.shadow.output.writer import prune_headquarters_archives  # noqa: E402
from src.shadow.snapshot import build_snapshot  # noqa: E402


class RecentRegressionCoverageTests(unittest.TestCase):
    def test_file_export_loaders_coerce_wrapped_qe_exports(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
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

    def test_snapshot_loads_enabled_qe_files_and_keeps_gmail_failure_in_notes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
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

        fake_modules = self._google_modules(FakeCredentials, FakeFlow, FakeRequest, fake_build)

        with tempfile.TemporaryDirectory() as tmp, patch.dict(sys.modules, fake_modules):
            root = Path(tmp)
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

    def test_brief_qe_context_uses_budget_without_hiding_work_signals(self):
        snapshot = Snapshot(
            as_of=datetime(2026, 5, 30, tzinfo=timezone.utc),
            sources=["fixture"],
            defects=[Defect(id="BUG-1", title="Critical login breakage", severity="Critical", status="Open")],
            mail_messages=[
                MailMessage(
                    id="mail-1",
                    subject="Escalation from support",
                    from_addr="support@example.com",
                    snippet="",
                    is_unread=True,
                )
            ],
            team_members=[
                TeamMember(
                    id="qe-1",
                    name="Avery",
                    last_one_on_one=datetime(2026, 5, 29, tzinfo=timezone.utc),
                )
            ],
            capacity_allocations=[
                CapacityAllocation(id="alloc-1", person_id="qe-1", person_name="Avery", app_name="Checkout")
            ],
            strategy_signals=[
                StrategySignal(id="sig-1", pillar="Reliability", summary="Protect checkout", priority="P0")
            ],
        )

        bullets, suggested = get_brief_bullets_and_focus(
            snapshot,
            {"brief": {"include_qe_context": True, "max_bullets": 3, "max_qe_context_bullets": 2}},
        )

        self.assertEqual(3, len(bullets))
        self.assertTrue(bullets[0].startswith("QE team (file):"))
        self.assertTrue(bullets[1].startswith("Allocations:"))
        self.assertTrue(bullets[2].startswith("Gmail:"))
        self.assertEqual(
            "Balance people/capacity/strategy context with inbox and execution signals for today.",
            suggested,
        )

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
        self.assertLess(strategy_md.index("## Test automation"), strategy_md.index("## Quality ownership"))

    def test_headquarters_escapes_user_fields_and_enforces_row_caps(self):
        unsafe = '<img src=x onerror="alert(1)">'
        snapshot = Snapshot(
            as_of=datetime(2026, 5, 30, 10, 0, tzinfo=timezone.utc),
            sources=[f"source {unsafe}"],
            notes=[f"note {unsafe}"],
            defects=[
                Defect(id="BUG-1", title=f"first {unsafe}", severity="High", status="Open"),
                Defect(id="BUG-2", title="second should be capped", severity="Low", status="Open"),
            ],
            test_runs=[
                TestRun(id="RUN-1", name=f"run {unsafe}", status="Passed", total=1, passed=1, failed=0)
            ],
            mail_messages=[
                MailMessage(
                    id="mail-1",
                    subject=f"mail {unsafe}",
                    from_addr="qa@example.com",
                    snippet=f"snippet {unsafe}",
                    internal_date=datetime(2026, 5, 30, tzinfo=timezone.utc),
                ),
                MailMessage(id="mail-2", subject="second mail should be capped", from_addr="", snippet=""),
            ],
            team_members=[TeamMember(id="qe-1", name=f"Avery {unsafe}", role="Lead")],
            capacity_allocations=[
                CapacityAllocation(
                    id="alloc-1",
                    person_id="qe-1",
                    person_name=f"Avery {unsafe}",
                    app_name="Checkout",
                    commitment_note=f"note {unsafe}",
                )
            ],
            strategy_signals=[
                StrategySignal(id="sig-1", pillar=f"Reliability {unsafe}", summary=f"summary {unsafe}")
            ],
        )

        rendered = render_headquarters_html(
            snapshot,
            {
                "headquarters": {
                    "title": f"HQ {unsafe}",
                    "links": [{"label": f"Docs {unsafe}", "url": 'https://example.test/?q="bad"'}],
                    "max_mail_rows": 1,
                },
                "brief": {"max_bullets": 2},
            },
            full_brief_markdown=f"# Brief\n\n{unsafe}",
            max_defect_rows=1,
        )

        self.assertNotIn(unsafe, rendered)
        self.assertIn(html.escape(unsafe), rendered)
        self.assertIn("first", rendered)
        self.assertNotIn("second should be capped", rendered)
        self.assertIn("mail", rendered)
        self.assertNotIn("second mail should be capped", rendered)
        self.assertIn("Showing 1 of 2.", rendered)
        self.assertIn("https://example.test/?q=&quot;bad&quot;", rendered)

    def test_prune_headquarters_archives_keeps_latest_by_stamp_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            hq = root / "output" / "headquarters"
            hq.mkdir(parents=True)
            for name in [
                "headquarters-2026-05-28T100000Z.html",
                "headquarters-2026-05-29T100000Z.html",
                "headquarters-2026-05-30T100000Z.html",
                "latest.html",
                "latest.md",
                "headquarters-notes.txt",
            ]:
                (hq / name).write_text(name, encoding="utf-8")

            removed = prune_headquarters_archives(root, "output/headquarters", max_keep=2)
            remaining = {p.name for p in hq.iterdir()}

        self.assertEqual(1, removed)
        self.assertNotIn("headquarters-2026-05-28T100000Z.html", remaining)
        self.assertIn("headquarters-2026-05-29T100000Z.html", remaining)
        self.assertIn("headquarters-2026-05-30T100000Z.html", remaining)
        self.assertIn("latest.html", remaining)
        self.assertIn("latest.md", remaining)
        self.assertIn("headquarters-notes.txt", remaining)

    @staticmethod
    def _google_modules(credentials_cls, flow_cls, request_cls, build_func):
        google = types.ModuleType("google")
        google_oauth2 = types.ModuleType("google.oauth2")
        google_oauth2_credentials = types.ModuleType("google.oauth2.credentials")
        google_auth = types.ModuleType("google.auth")
        google_auth_transport = types.ModuleType("google.auth.transport")
        google_auth_transport_requests = types.ModuleType("google.auth.transport.requests")
        google_auth_oauthlib = types.ModuleType("google_auth_oauthlib")
        google_auth_oauthlib_flow = types.ModuleType("google_auth_oauthlib.flow")
        googleapiclient = types.ModuleType("googleapiclient")
        googleapiclient_discovery = types.ModuleType("googleapiclient.discovery")

        google.oauth2 = google_oauth2
        google_oauth2.credentials = google_oauth2_credentials
        google_auth.transport = google_auth_transport
        google_auth_transport.requests = google_auth_transport_requests
        google_auth_oauthlib.flow = google_auth_oauthlib_flow
        googleapiclient.discovery = googleapiclient_discovery

        google_oauth2_credentials.Credentials = credentials_cls
        google_auth_transport_requests.Request = request_cls
        google_auth_oauthlib_flow.InstalledAppFlow = flow_cls
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
