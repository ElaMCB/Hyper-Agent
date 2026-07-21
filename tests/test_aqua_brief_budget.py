import unittest
from datetime import datetime, timezone

from src.shadow.adapters.aqua import AquaReport, AquaScenario
from src.shadow.capabilities.aqua_brief import aqua_summary_bullets
from src.shadow.capabilities.brief import get_brief_bullets_and_focus
from src.shadow.models import Snapshot, TestRun


def _scenario(
    scenario_id: str,
    description: str,
    confidence: float,
    *,
    impact: str = "medium",
) -> AquaScenario:
    return AquaScenario(
        id=scenario_id,
        description=description,
        confidence=confidence,
        rationale="Regression fixture",
        impact=impact,
        status="generated",
    )


def _snapshot(report: AquaReport, *, test_runs: list[TestRun] | None = None) -> Snapshot:
    return Snapshot(
        as_of=datetime(2026, 7, 21, 10, 0, tzinfo=timezone.utc),
        sources=["A.Q.U.A: fixture"],
        test_runs=test_runs or [],
        aqua_report=report,
    )


def _config(*, include_in_brief: bool = True) -> dict:
    return {
        "integrations": {
            "aqua": {
                "enabled": True,
                "include_in_brief": include_in_brief,
                "alert_threshold": 0.75,
            }
        },
        "brief": {
            "max_bullets": 5,
            "max_aqua_bullets": 3,
            "include_qe_context": False,
        },
    }


class AquaBriefBudgetTests(unittest.TestCase):
    def test_threshold_boundary_prioritizes_high_impact_scenario(self) -> None:
        report = AquaReport(
            version="0.1.0",
            snapshot_id="boundary",
            generated_at="2026-07-21T10:00:00Z",
            scenarios=[
                _scenario("at", "Exactly at threshold", 0.75),
                _scenario("lower", "Lower impact uncertainty", 0.60, impact="low"),
                _scenario("high", "High impact uncertainty", 0.74, impact="high"),
            ],
        )

        bullets = aqua_summary_bullets(_snapshot(report), _config())

        self.assertIn("2 scenario(s) below 75% confidence", bullets[1])
        self.assertIn("High impact uncertainty", bullets[2])
        self.assertNotIn("Exactly at threshold", "\n".join(bullets[1:]))
        self.assertNotIn("Lower impact uncertainty", "\n".join(bullets[2:]))

    def test_drift_is_visible_and_brief_opt_out_is_respected(self) -> None:
        report = AquaReport(
            version="0.1.0",
            snapshot_id="drift",
            generated_at="2026-07-21T10:00:00Z",
            scenarios=[_scenario("stable", "Stable scenario", 0.90)],
            production_drift=[{"id": "drift-1"}, {"id": "drift-2"}],
        )
        snapshot = _snapshot(report)

        bullets = aqua_summary_bullets(snapshot, _config())

        self.assertTrue(any("all scenarios ≥ 75%" in bullet for bullet in bullets))
        self.assertIn("A.Q.U.A: 2 production drift signal(s)", bullets)
        self.assertEqual(
            aqua_summary_bullets(snapshot, _config(include_in_brief=False)),
            [],
        )

    def test_shared_budget_keeps_aqua_risk_and_latest_test_run(self) -> None:
        report = AquaReport(
            version="0.1.0",
            snapshot_id="budget",
            generated_at="2026-07-21T10:00:00Z",
            scenarios=[
                _scenario("high", "Async timeout under load", 0.68, impact="high"),
                _scenario("stable", "Stable checkout behavior", 0.88, impact="high"),
            ],
        )
        test_run = TestRun(
            id="run-1",
            name="Checkout regression",
            status="Passed",
            passed=42,
            failed=0,
            total=42,
        )

        bullets, _ = get_brief_bullets_and_focus(
            _snapshot(report, test_runs=[test_run]),
            _config(),
        )

        self.assertLessEqual(len(bullets), 5)
        self.assertTrue(any("Async timeout under load" in bullet for bullet in bullets))
        self.assertTrue(any("Latest test run: Checkout regression" in bullet for bullet in bullets))


if __name__ == "__main__":
    unittest.main()
