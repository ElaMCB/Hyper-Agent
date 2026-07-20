import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from src import api
from src.shadow.models import Snapshot


class ApiPersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.snapshot = Snapshot(as_of=datetime(2026, 7, 20, 10, 0, tzinfo=timezone.utc))

    def test_brief_persistence_requires_request_and_config_opt_in(self) -> None:
        config = {
            "llm": {"enabled": False},
            "output": {"save_on_api": True, "briefs_dir": "private/briefs"},
        }
        with (
            patch.object(api, "build_snapshot", return_value=self.snapshot),
            patch.object(api, "render_brief", return_value="# Brief"),
            patch.object(api, "write_brief_artifact") as write_brief,
        ):
            self.assertEqual(api._brief_markdown(config, persist=False), "# Brief")
            write_brief.assert_not_called()

            config["output"]["save_on_api"] = False
            self.assertEqual(api._brief_markdown(config, persist=True), "# Brief")
            write_brief.assert_not_called()

            config["output"]["save_on_api"] = True
            self.assertEqual(api._brief_markdown(config, persist=True), "# Brief")
            write_brief.assert_called_once_with(
                api._ROOT,
                "# Brief",
                self.snapshot.as_of,
                "private/briefs",
            )

    def test_headquarters_persistence_writes_mirrors_and_prunes_archives(self) -> None:
        config = {
            "llm": {"enabled": False},
            "headquarters": {
                "dir": "private/headquarters",
                "write_latest": False,
                "retention": {"max_archived_html": 7},
            },
        }
        with (
            patch.object(api, "build_snapshot", return_value=self.snapshot),
            patch.object(api, "render_brief", return_value="# Brief"),
            patch.object(api, "render_headquarters_html", return_value="<html>HQ</html>"),
            patch.object(api, "write_headquarters_artifacts") as write_html,
            patch.object(api, "write_headquarters_latest_md") as write_markdown,
            patch.object(api, "prune_headquarters_archives") as prune,
        ):
            result = api._headquarters_html(config, persist=True)

        self.assertEqual(result, "<html>HQ</html>")
        write_html.assert_called_once_with(
            api._ROOT,
            "<html>HQ</html>",
            self.snapshot.as_of,
            "private/headquarters",
            write_latest=False,
        )
        write_markdown.assert_called_once_with(
            api._ROOT,
            "# Brief",
            "private/headquarters",
        )
        prune.assert_called_once_with(api._ROOT, "private/headquarters", 7)

    def test_headquarters_without_persist_has_no_filesystem_side_effects(self) -> None:
        config = {"headquarters": {"retention": {"max_archived_html": 1}}}
        with (
            patch.object(api, "build_snapshot", return_value=self.snapshot),
            patch.object(api, "render_brief", return_value="# Brief"),
            patch.object(api, "render_headquarters_html", return_value="<html>HQ</html>"),
            patch.object(api, "write_headquarters_artifacts") as write_html,
            patch.object(api, "write_headquarters_latest_md") as write_markdown,
            patch.object(api, "prune_headquarters_archives") as prune,
        ):
            self.assertEqual(api._headquarters_html(config, persist=False), "<html>HQ</html>")

        write_html.assert_not_called()
        write_markdown.assert_not_called()
        prune.assert_not_called()


if __name__ == "__main__":
    unittest.main()
