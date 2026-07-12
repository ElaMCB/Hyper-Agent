import json
import tempfile
import unittest
from pathlib import Path

from src.shadow.adapters.aqua import parse_aqua_payload
from src.shadow.capabilities.brief import render_brief
from src.shadow.snapshot import build_snapshot


class AquaIntegrationTests(unittest.TestCase):
    def test_parse_aqua_payload_normalizes_malformed_external_fields(self) -> None:
        report = parse_aqua_payload(
            {
                "aqua_report": {
                    "version": "0.1.0",
                    "snapshot_id": "risk-snapshot",
                    "generated_at": "2026-07-12T10:00:00Z",
                    "source": ["not", "a", "mapping"],
                    "scenarios": [
                        {
                            "id": "s-1",
                            "description": "Malformed external confidence does not crash",
                            "confidence": "not-a-number",
                            "rationale": "External report producers can drift independently.",
                            "impact": "High",
                            "status": "generated",
                            "alternatives": [
                                {"hypothesis": "Bad probability", "probability": "NaN"},
                                "skip this malformed alternative",
                            ],
                            "affected_paths": "src/shadow/adapters/aqua.py",
                        },
                        "skip this malformed scenario",
                    ],
                    "production_drift": {"id": "drift-1", "summary": "single object is accepted"},
                    "recommendations": "not-a-list",
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
        self.assertEqual(report.production_drift, [{"id": "drift-1", "summary": "single object is accepted"}])
        self.assertEqual(report.recommendations, [])

    def test_build_snapshot_renders_aqua_high_impact_low_confidence_first(self) -> None:
        payload = {
            "aqua_report": {
                "version": "0.1.0",
                "snapshot_id": "abcdef12-3456-7890-abcd-ef1234567890",
                "generated_at": "2026-07-12T10:00:00Z",
                "scenarios": [
                    {
                        "id": "medium-low",
                        "description": "Medium impact scenario should not displace high impact risk",
                        "confidence": 0.62,
                        "rationale": "Useful, but lower leadership risk.",
                        "impact": "medium",
                        "status": "generated",
                    },
                    {
                        "id": "high-low",
                        "description": "Case-insensitive high impact scenario needs manager review",
                        "confidence": 0.68,
                        "rationale": "Capitalized impact labels come from external systems.",
                        "impact": "High",
                        "status": "generated",
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
                "brief": {"max_bullets": 5, "max_aqua_bullets": 5, "title": "# Test brief"},
            }

            snapshot = build_snapshot(root, config)
            rendered = render_brief(snapshot, root, config)

        self.assertEqual(snapshot.sources, ["A.Q.U.A: 2 scenario(s) (data/aqua-report.json)"])
        self.assertIn("A.Q.U.A: 2 scenario(s)", rendered)
        self.assertIn("snapshot abcdef12", rendered)
        self.assertIn("A.Q.U.A: 2 scenario(s) below 75% confidence", rendered)
        self.assertIn(
            "Case-insensitive high impact scenario needs manager review (68%, High impact)",
            rendered,
        )
        self.assertNotIn("Medium impact scenario should not displace high impact risk (62%", rendered)
        self.assertIn("A.Q.U.A: 1 production drift signal(s)", rendered)


if __name__ == "__main__":
    unittest.main()
