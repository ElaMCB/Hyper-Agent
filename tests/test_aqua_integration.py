import json
import tempfile
import unittest
from pathlib import Path

from src.shadow.adapters.aqua import parse_aqua_payload
from src.shadow.capabilities.brief import render_brief
from src.shadow.snapshot import build_snapshot


class AquaIntegrationTests(unittest.TestCase):
    def test_parser_ignores_malformed_collections_and_defaults_bad_numbers(self):
        report = parse_aqua_payload(
            {
                "aqua_report": {
                    "version": "0.1.0",
                    "snapshot_id": "snap-123",
                    "generated_at": "2026-07-10T10:00:00Z",
                    "source": "not-a-source-dict",
                    "scenarios": [
                        {
                            "id": 42,
                            "description": "Checkout timeout path",
                            "confidence": "not-a-number",
                            "rationale": "external producer emitted bad confidence",
                            "alternatives": [
                                {"hypothesis": "worker starvation", "probability": "NaN"},
                                "skip me",
                            ],
                            "impact": "HIGH",
                            "status": "generated",
                            "affected_paths": "src/payment/checkout.py",
                        },
                        "skip me too",
                    ],
                    "production_drift": "not-a-list",
                    "recommendations": {"id": "not-a-list"},
                }
            }
        )

        self.assertIsNotNone(report)
        self.assertEqual(report.source, {})
        self.assertEqual(report.production_drift, [])
        self.assertEqual(report.recommendations, [])
        self.assertEqual(len(report.scenarios), 1)

        scenario = report.scenarios[0]
        self.assertEqual(scenario.id, "42")
        self.assertEqual(scenario.confidence, 0.0)
        self.assertEqual(scenario.impact, "high")
        self.assertEqual(scenario.affected_paths, ["src/payment/checkout.py"])
        self.assertEqual(len(scenario.alternatives), 1)
        self.assertEqual(scenario.alternatives[0].probability, 0.0)

    def test_build_snapshot_and_brief_prioritize_high_impact_aqua_scenarios(self):
        payload = {
            "aqua_report": {
                "version": "0.1.0",
                "snapshot_id": "abcdef12-3456-7890-abcd-ef1234567890",
                "generated_at": "2026-07-10T10:00:00Z",
                "source": {"repo": "ElaMCB/Hyper-Agent"},
                "scenarios": [
                    {
                        "id": "medium-risk",
                        "description": "Cosmetic layout drift",
                        "confidence": 0.31,
                        "rationale": "visual fixture changed",
                        "alternatives": [],
                        "impact": "medium",
                        "status": "generated",
                    },
                    {
                        "id": "high-risk",
                        "description": "Checkout authorization silently fails",
                        "confidence": 0.62,
                        "rationale": "external auth branch lacks coverage",
                        "alternatives": [],
                        "impact": "HIGH",
                        "status": "generated",
                    },
                ],
                "production_drift": [{"id": "drift-1", "description": "auth retries spiked"}],
                "recommendations": [],
            }
        }

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_dir = root / "data"
            data_dir.mkdir()
            (data_dir / "aqua-report.json").write_text(json.dumps(payload), encoding="utf-8")
            config = {
                "data": {
                    "dir": "data",
                    "load_defects": False,
                    "load_test_runs": False,
                    "load_team": False,
                    "load_allocations": False,
                    "load_strategy": False,
                },
                "integrations": {
                    "aqua": {
                        "enabled": True,
                        "report_path": "data/aqua-report.json",
                        "alert_threshold": 0.75,
                        "include_in_brief": True,
                    }
                },
                "brief": {"max_bullets": 5, "max_aqua_bullets": 4, "title": "# Test brief"},
            }

            snapshot = build_snapshot(root, config)
            markdown = render_brief(snapshot, root, config)

        self.assertIsNotNone(snapshot.aqua_report)
        self.assertIn("A.Q.U.A: 2 scenario(s) (data/aqua-report.json)", snapshot.sources)
        self.assertIn("A.Q.U.A: 1 production drift signal(s)", markdown)
        self.assertIn("Checkout authorization silently fails (62%, high impact)", markdown)
        self.assertNotIn("Cosmetic layout drift (31%, medium impact)", markdown)


if __name__ == "__main__":
    unittest.main()
