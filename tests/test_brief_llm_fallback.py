from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from src.shadow.capabilities.brief import render_brief
from src.shadow.models import Defect, Snapshot


class BriefLlmFallbackTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = Snapshot(
            as_of=datetime(2026, 7, 23, 10, 0, tzinfo=timezone.utc),
            sources=["File: defects (defects.json)"],
            defects=[
                Defect(
                    id="BUG-42",
                    title="Checkout rejects valid payment",
                    severity="Critical",
                    status="Open",
                )
            ],
            notes=["Gmail: provider unavailable"],
        )
        self.config = {
            "brief": {"max_bullets": 2},
            "llm": {"provider": "openai", "model": "test-model"},
        }

    def _root_with_system_prompt(self, directory: str) -> Path:
        root = Path(directory)
        prompts = root / "config" / "prompts"
        prompts.mkdir(parents=True)
        (prompts / "brief_system.txt").write_text("Polish the brief.", encoding="utf-8")
        return root

    def test_successful_llm_polish_keeps_provenance_and_adapter_notes(self):
        with TemporaryDirectory() as directory:
            root = self._root_with_system_prompt(directory)
            with (
                patch("src.llm.client.load_prompt", return_value="Prepared user prompt") as load_prompt,
                patch("src.llm.client.llm_complete", return_value="# Polished brief") as complete,
            ):
                markdown = render_brief(
                    self.snapshot,
                    root,
                    self.config,
                    use_llm=True,
                    max_bullets=2,
                )

        load_prompt.assert_called_once()
        prompt_call = load_prompt.call_args
        self.assertEqual(prompt_call.args, ("brief_user.txt",))
        self.assertEqual(prompt_call.kwargs["max_bullets"], "2")
        self.assertIn("BUG-42", prompt_call.kwargs["summary"])
        complete.assert_called_once_with(
            "Polish the brief.",
            "Prepared user prompt",
            provider="openai",
            model="test-model",
        )
        self.assertTrue(markdown.startswith("# Polished brief"))
        self.assertIn("As of 2026-07-23T10:00:00Z (UTC)", markdown)
        self.assertIn("Sources: File: defects (defects.json)", markdown)
        self.assertIn("*Gmail: provider unavailable*", markdown)

    def test_llm_failure_returns_deterministic_brief_with_audit_context(self):
        with TemporaryDirectory() as directory:
            root = self._root_with_system_prompt(directory)
            with (
                patch("src.llm.client.load_prompt", return_value="Prepared user prompt"),
                patch("src.llm.client.llm_complete", side_effect=RuntimeError("provider timeout")),
            ):
                markdown = render_brief(
                    self.snapshot,
                    root,
                    self.config,
                    use_llm=True,
                    max_bullets=2,
                )

        self.assertIn("# Morning brief", markdown)
        self.assertIn("Defects: 1 total, 1 critical/high, 1 not closed.", markdown)
        self.assertIn("Top severity: BUG-42 — Checkout rejects valid payment", markdown)
        self.assertIn("*(LLM skipped: provider timeout)*", markdown)
        self.assertIn("As of 2026-07-23T10:00:00Z (UTC)", markdown)
        self.assertIn("*Gmail: provider unavailable*", markdown)


if __name__ == "__main__":
    unittest.main()
