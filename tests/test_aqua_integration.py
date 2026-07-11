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


def _aqua_config() -> dict:
    return {
        "integrations": {
            "aqua": {
                "enabled": True,
                "report_path": "data/aqua-report.json",
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
            "include_qe_context": False,
            "title": "# Morning brief",
        },
    }


class AquaIntegrationTests(unittest.TestCase):
    def test_parse_payload_coerces_malformed_external_fields(self) -> None:
        report = parse_aqua_payload(
            {
                "aqua_report": {
                    "version": "0.1.0",
                    "snapshot_id": "snapshot-12345678",
                    "generated_at": "2026-07-11T10:00:00Z",
                    "source": ["not", "a", "mapping"],
                    "scenarios": [
                        {
                            "id": "S-1",
                            "description": "Malformed confidence should not crash",
                            "confidence": "not-a-number",
                            "rationale": "External reports can drift from schema.",
                            "impact": "HIGH",
                            "status": "generated",
                            "alternatives": {
                                "description": "Single malformed alternative",
                                "probability": "nan",
                                "evidence": "A non-finite value arrived from JSON.",
                            },
                            "affected_paths": "src/shadow/adapters/aqua.py",
                        },
                        "skip non-object scenario",
                    ],
                    "production_drift": "not-a-list",
                    "recommendations": {
                        "id": "R-1",
                        "scenario_id": "S-1",
                        "action": "Review the malformed report",
                        "risk": "low",
                    },
                }
            }
        )

        self.assertIsNotNone(report)
        assert report is not None
        self.assertEqual(report.source, {})
        self.assertEqual(report.production_drift, [])
        self.assertEqual(report.recommendations[0]["id"], "R-1")

        self.assertEqual(len(report.scenarios), 1)
        scenario = report.scenarios[0]
        self.assertEqual(scenario.confidence, 0.0)
        self.assertEqual(scenario.impact, "HIGH")
        self.assertEqual(scenario.affected_paths, ["src/shadow/adapters/aqua.py"])
        self.assertEqual(len(scenario.alternatives), 1)
        self.assertEqual(scenario.alternatives[0].probability, 0.0)

    def test_snapshot_and_brief_survive_enabled_malformed_aqua_report(self) -> None:
        payload = {
            "aqua_report": {
                "version": "0.1.0",
                "snapshot_id": "brief-snapshot-12345678",
                "generated_at": "2026-07-11T10:00:00Z",
                "scenarios": [
                    {
                        "id": "S-2",
                        "description": "Checkout coupon expiry regression",
                        "confidence": "inf",
                        "rationale": "External confidence was non-finite.",
                        "alternatives": ["skip non-object alternative"],
                        "impact": "high",
                        "status": "generated",
                        "affected_paths": ["src/payment/validation.ts"],
                    }
                ],
            }
        }

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_dir = root / "data"
            data_dir.mkdir()
            (data_dir / "aqua-report.json").write_text(json.dumps(payload), encoding="utf-8")

            snapshot = build_snapshot(root, _aqua_config())
            rendered = render_brief(snapshot, root, _aqua_config())

        self.assertEqual(snapshot.notes, [])
        self.assertIsNotNone(snapshot.aqua_report)
        self.assertIn("A.Q.U.A: 1 scenario(s) (data/aqua-report.json)", snapshot.sources)
        self.assertIn("A.Q.U.A: 1 scenario(s) below 75% confidence", rendered)
        self.assertIn("Checkout coupon expiry regression (0%, high impact)", rendered)

    def test_aqua_brief_prioritizes_high_impact_case_insensitively(self) -> None:
        report = AquaReport(
            version="0.1.0",
            snapshot_id="case-priority-12345678",
            generated_at="2026-07-11T10:00:00Z",
            scenarios=[
                AquaScenario(
                    id="S-medium",
                    description="Medium impact low confidence",
                    confidence=0.20,
                    rationale="Lower business risk.",
                    impact="medium",
                    status="generated",
                ),
                AquaScenario(
                    id="S-high",
                    description="High-impact low confidence",
                    confidence=0.70,
                    rationale="Leadership should see this first.",
                    impact="HIGH",
                    status="generated",
                ),
            ],
        )
        snapshot = Snapshot(
            as_of=datetime(2026, 7, 11, 10, 0, tzinfo=timezone.utc),
            sources=["A.Q.U.A"],
            aqua_report=report,
        )

        bullets = aqua_summary_bullets(snapshot, _aqua_config())

        self.assertIn("High-impact low confidence", bullets[2])
        self.assertNotIn("Medium impact low confidence", bullets[2])


if __name__ == "__main__":
    unittest.main()
