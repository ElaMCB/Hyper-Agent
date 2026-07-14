import unittest
from pathlib import Path

import yaml

from src.shadow.capabilities.brief import get_brief_bullets_and_focus
from src.shadow.snapshot import build_snapshot


ROOT = Path(__file__).resolve().parents[1]


class DefaultAquaConfigTests(unittest.TestCase):
    def test_enabled_aqua_sample_surfaces_low_confidence_risk(self) -> None:
        config = yaml.safe_load(
            (ROOT / "config" / "config.yaml").read_text(encoding="utf-8")
        )
        aqua_config = config["integrations"]["aqua"]

        self.assertTrue(aqua_config["enabled"])
        self.assertEqual(aqua_config["alert_threshold"], 0.75)

        snapshot = build_snapshot(ROOT, config)
        bullets, _ = get_brief_bullets_and_focus(snapshot, config)

        self.assertIsNotNone(snapshot.aqua_report)
        self.assertIn(
            "A.Q.U.A: 2 scenario(s) (data/aqua-report.json)",
            snapshot.sources,
        )
        self.assertIn(
            "A.Q.U.A: 1 scenario(s) below 75% confidence — manager review",
            bullets,
        )
        self.assertIn(
            "— Async timeout or silent failure under load (68%, high impact)",
            bullets,
        )
        self.assertFalse(
            any("Expired coupon rejection at checkout" in bullet for bullet in bullets)
        )


if __name__ == "__main__":
    unittest.main()
