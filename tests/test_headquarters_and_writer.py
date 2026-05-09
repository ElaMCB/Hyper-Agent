import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from src.shadow.capabilities.headquarters import render_headquarters_html
from src.shadow.models import MailMessage, Snapshot, TeamMember
from src.shadow.output.writer import prune_headquarters_archives


class HeadquartersAndWriterTests(unittest.TestCase):
    def test_headquarters_escapes_mail_content_and_can_hide_qe_panels(self):
        snapshot = Snapshot(
            as_of=datetime(2026, 5, 8, 10, 0, tzinfo=timezone.utc),
            sources=["test"],
            mail_messages=[
                MailMessage(
                    id="message-1234567890abcdef",
                    subject='Checkout <script>alert("x")</script>',
                    from_addr="Lead <lead@example.com>",
                    snippet="Refund & release <b>risk</b>",
                    is_unread=True,
                )
            ],
            team_members=[TeamMember(id="qa-1", name="Asha", role="QE Lead")],
        )

        html = render_headquarters_html(
            snapshot,
            {"headquarters": {"show_qe_panels": False, "max_mail_rows": 5}},
            full_brief_markdown="Brief with <unsafe> content",
        )

        self.assertIn("Checkout &lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;", html)
        self.assertIn("Lead &lt;lead@example.com&gt;", html)
        self.assertIn("Refund &amp; release &lt;b&gt;risk&lt;/b&gt;", html)
        self.assertIn("Brief with &lt;unsafe&gt; content", html)
        self.assertNotIn("QE team (file)", html)
        self.assertNotIn("QE allocations", html)
        self.assertNotIn("QE strategy signals", html)

    def test_prune_headquarters_archives_keeps_newest_by_filename_without_touching_latest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = root / "output" / "headquarters"
            out.mkdir(parents=True)
            for name in [
                "headquarters-2026-05-01T090000Z.html",
                "headquarters-2026-05-02T090000Z.html",
                "headquarters-2026-05-03T090000Z.html",
                "latest.html",
                "latest.md",
            ]:
                (out / name).write_text(name, encoding="utf-8")

            removed = prune_headquarters_archives(root, "output/headquarters", max_keep=2)

            remaining = {p.name for p in out.iterdir()}

        self.assertEqual(removed, 1)
        self.assertEqual(
            remaining,
            {
                "headquarters-2026-05-02T090000Z.html",
                "headquarters-2026-05-03T090000Z.html",
                "latest.html",
                "latest.md",
            },
        )


if __name__ == "__main__":
    unittest.main()
