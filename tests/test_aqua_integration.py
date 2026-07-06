import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.shadow.adapters.aqua import (  # noqa: E402
    AquaReport,
    AquaScenario,
    parse_aqua_payload,
)
from src.shadow.capabilities.aqua_brief import aqua_summary_bullets  # noqa: E402
from src.shadow.capabilities.brief import render_brief  # noqa: E402
from src.shadow.models import Snapshot  # noqa: E402
from src.shadow.snapshot import build_snapshot  # noqa: E402


class AquaParserTests(unittest.TestCase):
    def test_parse_payload_returns_none_when_report_block_is_missing(self):
        self.assertIsNone(parse_aqua_payload({"not_aqua": {}}))

    def test_parse_payload_tolerates_malformed_external_shapes(self):
        report = parse_aqua_payload(
            {
                "aqua_report": {
                    "version": "0.1.0",
                    "snapshot_id": "snap-123",
                    "generated_at": "2026-07-06T09:00:00Z",
                    "source": "not-a-dict",
                    "scenarios": [
                        "skip me",
                        {
                            "id": 42,
                            "description": "Malformed confidence should not crash",
                            "confidence": "not-a-number",
                            "rationale": None,
                            "alternatives": [
                                {"hypothesis": "Bad probability", "probability": "unknown"},
                                object(),
                            ],
                            "impact": "high",
                            "status": "generated",
                            "affected_paths": "src/payment/validation.ts",
                        },
                    ],
                    "production_drift": {"bad": "shape"},
                    "recommendations": {"bad": "shape"},
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
        self.assertEqual(scenario.rationale, "None")
        self.assertEqual(scenario.affected_paths, [])
        self.assertEqual(len(scenario.alternatives), 1)
        self.assertEqual(scenario.alternatives[0].probability, 0.0)


class AquaBriefIntegrationTests(unittest.TestCase):
    def test_build_snapshot_loads_malformed_report_and_brief_includes_review_signal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report_path = root / "aqua-report.json"
            report_path.write_text(
                """
                {
                  "aqua_report": {
                    "version": "0.1.0",
                    "snapshot_id": "abcdef1234567890",
                    "generated_at": "2026-07-06T09:00:00Z",
                    "scenarios": [
                      {
                        "id": "scenario-1",
                        "description": "Checkout coupon expiry might be skipped",
                        "confidence": "unknown",
                        "rationale": "External report emitted a non-numeric confidence",
                        "alternatives": [
                          {"hypothesis": "Retry path hides the failure", "probability": "n/a"}
                        ],
                        "impact": "high",
                        "status": "generated",
                        "affected_paths": "src/payment/validation.ts"
                      }
                    ],
                    "production_drift": [
                      {"id": "drift-1", "description": "Checkout failures rising"}
                    ]
                  }
                }
                """,
                encoding="utf-8",
            )
            config = {
                "data": {
                    "load_defects": False,
                    "load_test_runs": False,
                },
                "integrations": {
                    "aqua": {
                        "enabled": True,
                        "report_path": str(report_path),
                        "alert_threshold": 0.75,
                    }
                },
                "brief": {"max_bullets": 5, "max_aqua_bullets": 4},
            }

            snapshot = build_snapshot(root, config)
            markdown = render_brief(snapshot, root, config)

        self.assertIsNotNone(snapshot.aqua_report)
        self.assertEqual(snapshot.aqua_report.scenarios[0].confidence, 0.0)
        self.assertEqual(snapshot.aqua_report.scenarios[0].affected_paths, [])
        self.assertTrue(
            any(source.startswith("A.Q.U.A: 1 scenario(s)") for source in snapshot.sources),
            snapshot.sources,
        )
        self.assertIn("A.Q.U.A: 1 scenario(s) below 75% confidence", markdown)
        self.assertIn("Checkout coupon expiry might be skipped (0%, high impact)", markdown)
        self.assertIn("A.Q.U.A: 1 production drift signal(s)", markdown)

    def test_aqua_summary_prioritizes_high_impact_low_confidence_scenarios(self):
        snapshot = Snapshot(
            as_of=datetime(2026, 7, 6, tzinfo=timezone.utc),
            aqua_report=AquaReport(
                version="0.1.0",
                snapshot_id="snap-abcdef",
                generated_at="2026-07-06T09:00:00Z",
                scenarios=[
                    AquaScenario(
                        id="medium-low",
                        description="Medium impact low confidence",
                        confidence=0.2,
                        rationale="",
                        impact="medium",
                        status="generated",
                    ),
                    AquaScenario(
                        id="high-low",
                        description="High impact low confidence",
                        confidence=0.7,
                        rationale="",
                        impact="high",
                        status="generated",
                    ),
                    AquaScenario(
                        id="high-lower",
                        description="Second high impact low confidence",
                        confidence=0.6,
                        rationale="",
                        impact="high",
                        status="generated",
                    ),
                ],
            ),
        )
        config = {"integrations": {"aqua": {"enabled": True, "alert_threshold": 0.75}}}

        bullets = aqua_summary_bullets(snapshot, config)

        self.assertEqual(
            bullets,
            [
                "A.Q.U.A: 3 scenario(s) \u00b7 snapshot snap-abc\u2026",
                "A.Q.U.A: 3 scenario(s) below 75% confidence \u2014 manager review",
                "\u2014 High impact low confidence (70%, high impact)",
                "\u2014 Second high impact low confidence (60%, high impact)",
            ],
        )


if __name__ == "__main__":
    unittest.main()
