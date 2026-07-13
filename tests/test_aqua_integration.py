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


def _minimal_aqua_config(report_path: Path) -> dict:
    return {
        "integrations": {
            "aqua": {
                "enabled": True,
                "report_path": str(report_path),
                "alert_threshold": 0.75,
                "include_in_brief": True,
            }
        },
        "data": {
            "dir": "data",
            "load_defects": False,
            "load_test_runs": False,
            "load_team": False,
            "load_allocations": False,
            "load_strategy": False,
        },
        "brief": {
            "max_bullets": 5,
            "max_aqua_bullets": 4,
            "title": "# Test brief",
        },
    }


class AquaIntegrationTests(unittest.TestCase):
    def test_parse_aqua_payload_normalizes_malformed_external_boundaries(self) -> None:
        report = parse_aqua_payload(
            {
                "aqua_report": {
                    "version": "0.1.0",
                    "snapshot_id": "snap-123",
                    "generated_at": "2026-07-13T10:00:00Z",
                    "source": "not-a-mapping",
                    "scenarios": {
                        "id": "scenario-1",
                        "description": "Async timeout or silent failure under load",
                        "confidence": "not-a-number",
                        "rationale": "External producer emitted malformed confidence",
                        "alternatives": {
                            "hypothesis": "Retry logic masks the failure",
                            "probability": "nan",
                        },
                        "impact": "High",
                        "status": "generated",
                        "affected_paths": "src/shadow/adapters/aqua.py",
                    },
                    "production_drift": {
                        "id": "drift-1",
                        "description": "Checkout latency shifted",
                    },
                    "recommendations": "manual review",
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
        self.assertEqual(report.production_drift, [{"id": "drift-1", "description": "Checkout latency shifted"}])
        self.assertEqual(report.recommendations, [])

    def test_build_snapshot_renders_aqua_risks_with_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report_path = root / "aqua-report.json"
            report_path.write_text(
                json.dumps(
                    {
                        "aqua_report": {
                            "version": "0.1.0",
                            "snapshot_id": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
                            "generated_at": "2026-07-13T10:00:00Z",
                            "source": {"repo": "ElaMCB/Hyper-Agent", "pr": 12},
                            "scenarios": [
                                {
                                    "id": "scenario-1",
                                    "description": "Expired coupon rejection at checkout",
                                    "confidence": 0.87,
                                    "rationale": "Validation refactor removed expiry checks",
                                    "alternatives": [],
                                    "impact": "high",
                                    "status": "generated",
                                    "affected_paths": ["src/payment/validation.ts"],
                                },
                                {
                                    "id": "scenario-2",
                                    "description": "Async timeout or silent failure under load",
                                    "confidence": 0.68,
                                    "rationale": "Async path lacks timeout handling",
                                    "alternatives": [],
                                    "impact": "high",
                                    "status": "generated",
                                    "affected_paths": ["src/shadow/adapters/aqua.py"],
                                },
                            ],
                            "production_drift": [
                                {
                                    "id": "drift-1",
                                    "description": "Checkout p95 latency shifted",
                                    "severity": "high",
                                    "detected_at": "2026-07-13T09:00:00Z",
                                }
                            ],
                            "recommendations": [],
                        }
                    }
                ),
                encoding="utf-8",
            )

            config = _minimal_aqua_config(report_path)
            snapshot = build_snapshot(root, config)
            markdown = render_brief(snapshot, root, config, use_llm=False)

        self.assertIsNotNone(snapshot.aqua_report)
        self.assertIn(f"A.Q.U.A: 2 scenario(s) ({report_path})", snapshot.sources)
        self.assertIn("A.Q.U.A: 2 scenario(s)", markdown)
        self.assertIn("A.Q.U.A: 1 scenario(s) below 75% confidence", markdown)
        self.assertIn("Async timeout or silent failure under load (68%, high impact)", markdown)
        self.assertIn("A.Q.U.A: 1 production drift signal(s)", markdown)
        self.assertIn(f"Sources: A.Q.U.A: 2 scenario(s) ({report_path})", markdown)

    def test_aqua_summary_prioritizes_high_impact_case_insensitively(self) -> None:
        snapshot = Snapshot(
            as_of=datetime.now(timezone.utc),
            aqua_report=AquaReport(
                version="0.1.0",
                snapshot_id="case-sensitivity-check",
                generated_at="2026-07-13T10:00:00Z",
                scenarios=[
                    AquaScenario(
                        id="medium-risk",
                        description="Lower-impact cache warning",
                        confidence=0.4,
                        rationale="Below threshold, but medium impact",
                        impact="medium",
                        status="generated",
                    ),
                    AquaScenario(
                        id="high-risk",
                        description="Checkout authorization bypass",
                        confidence=0.7,
                        rationale="Below threshold and high impact",
                        impact="High",
                        status="generated",
                    ),
                ],
            ),
        )
        config = {
            "integrations": {
                "aqua": {
                    "enabled": True,
                    "include_in_brief": True,
                    "alert_threshold": 0.75,
                }
            }
        }

        bullets = aqua_summary_bullets(snapshot, config)

        self.assertIn("— Checkout authorization bypass (70%, High impact)", bullets)
        self.assertNotIn("— Lower-impact cache warning (40%, medium impact)", bullets)
