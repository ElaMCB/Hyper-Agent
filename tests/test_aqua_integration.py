import json
import tempfile
import unittest
from pathlib import Path

from src.shadow.adapters.aqua import load_aqua_report, parse_aqua_payload
from src.shadow.capabilities.brief import render_brief
from src.shadow.snapshot import build_snapshot


class AquaIntegrationTests(unittest.TestCase):
    def test_parse_payload_normalizes_malformed_external_fields(self) -> None:
        report = parse_aqua_payload(
            {
                "aqua_report": {
                    "source": ["not", "a", "mapping"],
                    "scenarios": [
                        {
                            "id": "risk-1",
                            "description": "External producers can drift",
                            "confidence": "not-a-number",
                            "impact": "High",
                            "alternatives": [
                                {"hypothesis": "Invalid probability", "probability": "NaN"},
                                "skip malformed alternative",
                            ],
                            "affected_paths": "src/shadow/adapters/aqua.py",
                        },
                        "skip malformed scenario",
                    ],
                    "production_drift": {"id": "drift-1"},
                    "recommendations": "not-a-collection",
                }
            }
        )

        self.assertIsNotNone(report)
        assert report is not None
        self.assertEqual(report.source, {})
        self.assertEqual(len(report.scenarios), 1)
        scenario = report.scenarios[0]
        self.assertEqual(scenario.confidence, 0.0)
        self.assertEqual(scenario.affected_paths, ["src/shadow/adapters/aqua.py"])
        self.assertEqual(len(scenario.alternatives), 1)
        self.assertEqual(scenario.alternatives[0].probability, 0.0)
        self.assertEqual(report.production_drift, [{"id": "drift-1"}])
        self.assertEqual(report.recommendations, [])

    def test_load_report_rejects_non_object_json_without_crashing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report_path = root / "aqua-report.json"
            report_path.write_text("[]", encoding="utf-8")

            report, notes = load_aqua_report(
                root,
                {"enabled": True, "report_path": report_path.name},
            )

        self.assertIsNone(report)
        self.assertEqual(notes, ["AQUA: invalid report payload (missing aqua_report)"])

    def test_snapshot_and_brief_surface_high_impact_risk_and_drift(self) -> None:
        payload = {
            "aqua_report": {
                "snapshot_id": "abcdef12-3456-7890-abcd-ef1234567890",
                "scenarios": [
                    {
                        "id": "medium-low",
                        "description": "Medium impact scenario",
                        "confidence": 0.62,
                        "impact": "medium",
                    },
                    {
                        "id": "high-low",
                        "description": "Capitalized high impact scenario",
                        "confidence": 0.68,
                        "impact": "High",
                    },
                ],
                "production_drift": [{"id": "drift-1"}],
            }
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_dir = root / "data"
            data_dir.mkdir()
            (data_dir / "aqua-report.json").write_text(json.dumps(payload), encoding="utf-8")
            config = {
                "integrations": {
                    "aqua": {
                        "enabled": True,
                        "report_path": "data/aqua-report.json",
                        "alert_threshold": 0.75,
                        "include_in_brief": True,
                    }
                },
                "data": {"dir": "data", "load_defects": False, "load_test_runs": False},
                "brief": {"max_bullets": 5, "max_aqua_bullets": 5},
            }

            snapshot = build_snapshot(root, config)
            rendered = render_brief(snapshot, root, config)

        self.assertEqual(snapshot.sources, ["A.Q.U.A: 2 scenario(s) (data/aqua-report.json)"])
        self.assertIn("snapshot abcdef12", rendered)
        self.assertIn("A.Q.U.A: 2 scenario(s) below 75% confidence", rendered)
        self.assertIn("Capitalized high impact scenario (68%, High impact)", rendered)
        self.assertNotIn("Medium impact scenario (62%", rendered)
        self.assertIn("A.Q.U.A: 1 production drift signal(s)", rendered)


if __name__ == "__main__":
    unittest.main()
