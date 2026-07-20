import unittest
from datetime import datetime, timezone

from src.shadow.capabilities.headquarters import render_headquarters_html
from src.shadow.models import Defect, MailMessage, Snapshot


class HeadquartersRenderingTests(unittest.TestCase):
    def test_user_controlled_snapshot_fields_are_html_escaped(self):
        snapshot = Snapshot(
            as_of=datetime(2026, 5, 21, 10, 0, tzinfo=timezone.utc),
            sources=["File: defects (defects.json)"],
            defects=[
                Defect(
                    id="BUG-1",
                    title="<script>alert('defect')</script>",
                    severity="High",
                    status="Open",
                )
            ],
            mail_messages=[
                MailMessage(
                    id="gmail-message-id-that-is-long",
                    subject="<script>alert('subject')</script>",
                    from_addr='Team <team@example.com>"',
                    snippet="<b>Release blocker</b>",
                    is_unread=True,
                )
            ],
            notes=["Gmail: <token expired>"],
        )

        page = render_headquarters_html(
            snapshot,
            {
                "headquarters": {
                    "title": "Shadow <HQ>",
                    "show_qe_panels": False,
                }
            },
            full_brief_markdown="# Brief\n\n<script>alert('brief')</script>",
        )

        self.assertIn("Shadow &lt;HQ&gt;", page)
        self.assertIn("&lt;script&gt;alert(&#x27;defect&#x27;)&lt;/script&gt;", page)
        self.assertIn("&lt;script&gt;alert(&#x27;subject&#x27;)&lt;/script&gt;", page)
        self.assertIn("&lt;b&gt;Release blocker&lt;/b&gt;", page)
        self.assertIn("Gmail: &lt;token expired&gt;", page)
        self.assertIn("&lt;script&gt;alert(&#x27;brief&#x27;)&lt;/script&gt;", page)
        self.assertNotIn("<script>alert('defect')</script>", page)
        self.assertNotIn("<script>alert('subject')</script>", page)
        self.assertNotIn("<script>alert('brief')</script>", page)

    def test_qe_panels_can_be_suppressed_for_shared_dashboard(self):
        snapshot = Snapshot(
            as_of=datetime(2026, 5, 21, 10, 0, tzinfo=timezone.utc),
            sources=["File: team (team.json)"],
        )

        page = render_headquarters_html(
            snapshot,
            {"headquarters": {"show_qe_panels": False}},
            full_brief_markdown="# Brief",
        )

        self.assertNotIn("QE team (file)", page)
        self.assertNotIn("QE allocations", page)
        self.assertNotIn("QE strategy signals", page)


if __name__ == "__main__":
    unittest.main()
