import tempfile
import unittest
from pathlib import Path

import yaml

from src.shadow.capabilities.brief import get_brief_bullets_and_focus
from src.shadow.snapshot import build_snapshot


ROOT = Path(__file__).resolve().parents[1]


def load_default_config() -> dict:
    return yaml.safe_load(
        (ROOT / "config" / "config.yaml").read_text(encoding="utf-8")
    )


class AquaIntegrationTests(unittest.TestCase):
    def test_default_config_surfaces_low_confidence_high_impact_risk(self) -> None:
        config = load_default_config()
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

    def test_malformed_enabled_report_is_nonfatal_and_explains_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_dir = root / "data"
            data_dir.mkdir()
            (data_dir / "aqua-report.json").write_text("{not valid json", encoding="utf-8")
            config = {
                "integrations": {
                    "aqua": {
                        "enabled": True,
                        "report_path": "data/aqua-report.json",
                    }
                },
                "data": {
                    "dir": "data",
                    "load_defects": False,
                    "load_test_runs": False,
                },
            }

            snapshot = build_snapshot(root, config)

        self.assertIsNone(snapshot.aqua_report)
        self.assertEqual(snapshot.sources, ["A.Q.U.A: enabled (no report loaded)"])
        self.assertEqual(len(snapshot.notes), 1)
        self.assertIn("AQUA file (aqua-report.json)", snapshot.notes[0])

    def test_brief_opt_out_preserves_ingestion_provenance(self) -> None:
        config = load_default_config()
        config["integrations"]["aqua"]["include_in_brief"] = False
        config["data"]["load_defects"] = False
        config["data"]["load_test_runs"] = False

        snapshot = build_snapshot(ROOT, config)
        bullets, _ = get_brief_bullets_and_focus(snapshot, config)

        self.assertIsNotNone(snapshot.aqua_report)
        self.assertIn(
            "A.Q.U.A: 2 scenario(s) (data/aqua-report.json)",
            snapshot.sources,
        )
        self.assertFalse(any("A.Q.U.A" in bullet for bullet in bullets))


if __name__ == "__main__":
    unittest.main()
