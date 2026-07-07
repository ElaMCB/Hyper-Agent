import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from src.shadow.adapters.aqua import AquaReport, AquaScenario, parse_aqua_payload
from src.shadow.capabilities.aqua_brief import aqua_summary_bullets
from src.shadow.capabilities.brief import render_brief
from src.shadow.models import Snapshot
from src.shadow.snapshot import build_snapshot


class AquaIntegrationTests(unittest.TestCase):
    def test_parse_aqua_payload_tolerates_malformed_external_shapes(self):
        report = parse_aqua_payload(
            {
                "aqua_report": {
                    "version": "0.1.0",
                    "snapshot_id": "snap-malformed",
                    "generated_at": "2026-07-07T10:00:00Z",
                    "source": ["not", "a", "mapping"],
                    "production_drift": {"signal": "wrong-shape"},
                    "recommendations": "retry manually",
                    "scenarios": [
                        {
                            "id": "scenario-1",
                            "description": "Checkout confidence drift",
                            "confidence": "not-a-number",
                            "rationale": "External service emitted a partial report",
                            "impact": "high",
                            "status": "generated",
                            "alternatives": [
                                {
                                    "hypothesis": "Coupon timeout",
                                    "probability": "NaN",
                                },
                                "skip malformed alternative",
                            ],
                            "affected_paths": "src/payment/validation.py",
                        },
                        "skip malformed scenario",
                    ],
                }
            }
        )

        self.assertIsNotNone(report)
        assert report is not None
        self.assertEqual(report.source, {})
        self.assertEqual(report.production_drift, [])
        self.assertEqual(report.recommendations, [])
        self.assertEqual(len(report.scenarios), 1)
        scenario = report.scenarios[0]
        self.assertEqual(scenario.confidence, 0.0)
        self.assertEqual(scenario.affected_paths, [])
        self.assertEqual(len(scenario.alternatives), 1)
        self.assertEqual(scenario.alternatives[0].probability, 0.0)

    def test_build_snapshot_and_brief_survive_malformed_aqua_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_dir = root / "data"
            data_dir.mkdir()
            (data_dir / "aqua-report.json").write_text(
                json.dumps(
                    {
                        "aqua_report": {
                            "snapshot_id": "b2c3d4e5-f6a7",
                            "source": "bad-source-shape",
                            "scenarios": [
                                {
                                    "description": "Checkout confidence drift",
                                    "confidence": "not-a-number",
                                    "impact": "high",
                                    "affected_paths": "src/payment/validation.py",
                                }
                            ],
                            "production_drift": "not-a-list",
                        }
                    }
                ),
                encoding="utf-8",
            )
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
                "brief": {
                    "title": "# Test brief",
                    "max_bullets": 5,
                    "max_aqua_bullets": 4,
                },
            }

            snapshot = build_snapshot(root, config)
            markdown = render_brief(snapshot, root, config)

        self.assertEqual(snapshot.notes, [])
        self.assertEqual(snapshot.sources, ["A.Q.U.A: 1 scenario(s) (data/aqua-report.json)"])
        self.assertIn("A.Q.U.A: 1 scenario(s) below 75% confidence", markdown)
        self.assertIn("Checkout confidence drift (0%, high impact)", markdown)
        self.assertNotIn("nan", markdown.lower())

    def test_aqua_summary_prioritizes_high_impact_case_insensitively(self):
        snapshot = Snapshot(
            as_of=datetime(2026, 7, 7, 10, 0, tzinfo=timezone.utc),
            sources=["test"],
            aqua_report=AquaReport(
                version="0.1.0",
                snapshot_id="snapshot-123456789",
                generated_at="2026-07-07T10:00:00Z",
                scenarios=[
                    AquaScenario(
                        id="medium-first",
                        description="Lower impact report noise",
                        confidence=0.25,
                        rationale="",
                        impact="medium",
                        status="generated",
                    ),
                    AquaScenario(
                        id="high-second",
                        description="Payment authorization can fail silently",
                        confidence=0.60,
                        rationale="",
                        impact="High",
                        status="generated",
                    ),
                ],
            ),
        )

        bullets = aqua_summary_bullets(
            snapshot,
            {
                "integrations": {
                    "aqua": {
                        "enabled": True,
                        "include_in_brief": True,
                        "alert_threshold": 0.75,
                    }
                }
            },
        )

        self.assertIn("Payment authorization can fail silently", bullets[2])
        self.assertNotIn("Lower impact report noise", bullets[2])


if __name__ == "__main__":
    unittest.main()
