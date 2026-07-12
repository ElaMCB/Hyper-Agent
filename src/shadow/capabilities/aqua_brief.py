"""A.Q.U.A bullets for Shadow briefs — low-confidence scenarios surface for leadership."""

from __future__ import annotations

from ..adapters.aqua import AquaReport
from ..models import Snapshot


def aqua_summary_bullets(snapshot: Snapshot, config: dict) -> list[str]:
    aqua_cfg = (config.get("integrations") or {}).get("aqua") or {}
    if not aqua_cfg.get("enabled"):
        return []
    if not aqua_cfg.get("include_in_brief", True):
        return []
    report: AquaReport | None = snapshot.aqua_report
    if report is None or not report.scenarios:
        return []

    threshold = float(aqua_cfg.get("alert_threshold", 0.75))
    bullets: list[str] = [
        f"A.Q.U.A: {len(report.scenarios)} scenario(s) · snapshot {report.snapshot_id[:8]}…"
    ]

    low = [s for s in report.scenarios if s.confidence < threshold]
    high_impact_low = [s for s in low if (s.impact or "").strip().lower() == "high"]

    if low:
        bullets.append(
            f"A.Q.U.A: {len(low)} scenario(s) below {threshold:.0%} confidence — manager review"
        )
        for scenario in (high_impact_low or low)[:2]:
            pct = f"{scenario.confidence:.0%}"
            bullets.append(f"— {scenario.description} ({pct}, {scenario.impact} impact)")
    else:
        top = max(report.scenarios, key=lambda s: s.confidence)
        bullets.append(
            f"A.Q.U.A: all scenarios ≥ {threshold:.0%}; highest — {top.description} ({top.confidence:.0%})"
        )

    drift = report.production_drift
    if drift:
        bullets.append(f"A.Q.U.A: {len(drift)} production drift signal(s)")

    return bullets
