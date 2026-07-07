"""Load A.Q.U.A reports from file or HTTP endpoint (shared schema with ElaMCB/AQUA)."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen


@dataclass
class AquaAlternative:
    hypothesis: str
    probability: float
    evidence: str = ""


@dataclass
class AquaScenario:
    id: str
    description: str
    confidence: float
    rationale: str
    impact: str
    status: str
    alternatives: list[AquaAlternative] = field(default_factory=list)
    affected_paths: list[str] = field(default_factory=list)


@dataclass
class AquaReport:
    version: str
    snapshot_id: str
    generated_at: str
    scenarios: list[AquaScenario] = field(default_factory=list)
    source: dict[str, Any] = field(default_factory=dict)
    production_drift: list[dict[str, Any]] = field(default_factory=list)
    recommendations: list[dict[str, Any]] = field(default_factory=list)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if math.isfinite(parsed) else default


def _dict_list(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]


def _parse_alternatives(raw: Any) -> list[AquaAlternative]:
    out: list[AquaAlternative] = []
    for item in _dict_list(raw):
        out.append(
            AquaAlternative(
                hypothesis=str(item.get("hypothesis", item.get("description", ""))),
                probability=_safe_float(item.get("probability", 0)),
                evidence=str(item.get("evidence", "")),
            )
        )
    return out


def parse_aqua_payload(raw: dict[str, Any]) -> AquaReport | None:
    if not isinstance(raw, dict):
        return None
    block = raw.get("aqua_report")
    if not isinstance(block, dict):
        return None

    scenarios: list[AquaScenario] = []
    for item in _dict_list(block.get("scenarios", [])):
        affected_paths = item.get("affected_paths", [])
        scenarios.append(
            AquaScenario(
                id=str(item.get("id", "")),
                description=str(item.get("description", "")),
                confidence=_safe_float(item.get("confidence", 0)),
                rationale=str(item.get("rationale", "")),
                impact=str(item.get("impact", "medium")),
                status=str(item.get("status", "generated")),
                alternatives=_parse_alternatives(item.get("alternatives", [])),
                affected_paths=[str(p) for p in affected_paths] if isinstance(affected_paths, list) else [],
            )
        )

    source = block.get("source", {})

    return AquaReport(
        version=str(block.get("version", "0.1.0")),
        snapshot_id=str(block.get("snapshot_id", "")),
        generated_at=str(block.get("generated_at", "")),
        scenarios=scenarios,
        source=source if isinstance(source, dict) else {},
        production_drift=_dict_list(block.get("production_drift", [])),
        recommendations=_dict_list(block.get("recommendations", [])),
    )


def _load_json_from_endpoint(endpoint: str, timeout: int) -> dict[str, Any]:
    request = Request(endpoint, headers={"Accept": "application/json"})
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def load_aqua_report(root: Path, cfg: dict) -> tuple[AquaReport | None, list[str]]:
    """
    Read aqua-report.json from report_path and/or fetch from endpoint.
    File wins when both exist and file is newer; endpoint used when file missing.
    """
    notes: list[str] = []
    report_path = str(cfg.get("report_path", "data/aqua-report.json"))
    path = Path(report_path)
    if not path.is_absolute():
        path = root / path

    raw: dict[str, Any] | None = None
    endpoint = (cfg.get("endpoint") or "").strip()
    timeout = int(cfg.get("timeout_seconds", 10))

    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            notes.append(f"AQUA file ({path.name}): {exc}")
    elif endpoint:
        try:
            raw = _load_json_from_endpoint(endpoint, timeout)
        except (URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
            notes.append(f"AQUA endpoint: {exc}")
    elif cfg.get("enabled"):
        notes.append(f"AQUA: no report at {path} and no endpoint configured")

    if raw is None:
        return None, notes

    report = parse_aqua_payload(raw)
    if report is None:
        notes.append("AQUA: invalid report payload (missing aqua_report)")
        return None, notes

    return report, notes
