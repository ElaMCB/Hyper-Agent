"""QE subagent: portfolio / quality strategy signals you supply — summarize and order, no invention."""

from __future__ import annotations

from ..models import Snapshot


def _priority_rank(p: str) -> tuple[int, str]:
    u = (p or "").strip().upper()
    if u.startswith("P0"):
        return (0, u)
    if u.startswith("P1"):
        return (1, u)
    if u.startswith("P2"):
        return (2, u)
    return (9, u)


def render_strategy_md(snapshot: Snapshot, config: dict) -> str:
    items = list(snapshot.strategy_signals)
    lines: list[str] = ["# Strategy lens (QE)", ""]

    if not items:
        lines.append(
            "*No strategy rows — set `data.load_strategy: true` and add `data/strategy.json`.*"
        )
        lines.append("")
        return "\n".join(lines)

    items.sort(key=lambda s: (_priority_rank(s.priority), s.horizon, s.pillar))

    lines.append("Ordered by priority (P0 first), then horizon and pillar.")
    lines.append("")
    for s in items:
        lines.append(f"## {s.pillar or '(pillar)'} — `{s.priority or '—'}` · {s.horizon or '—'}")
        lines.append("")
        lines.append(s.summary or "_(no summary)_")
        lines.append("")
        if s.status:
            lines.append(f"- **Status:** {s.status}")
        if s.evidence_ref:
            lines.append(f"- **Evidence / link:** {s.evidence_ref}")
        lines.append("")

    lines.append("| Pillar | Priority | Horizon | Status | Summary | Evidence |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for s in items:
        summ = (s.summary or "").replace("|", "\\|")[:120]
        ev = (s.evidence_ref or "").replace("|", "\\|")[:60]
        lines.append(
            f"| {s.pillar} | {s.priority} | {s.horizon} | {s.status} | {summ} | {ev} |"
        )
    lines.append("")
    lines.append("*You own the facts; this section only structures them for steering prep.*")
    return "\n".join(lines)


def strategy_summary_bullets(snapshot: Snapshot, _config: dict) -> list[str]:
    items = snapshot.strategy_signals
    if not items:
        return []
    sorted_items = sorted(items, key=lambda s: (_priority_rank(s.priority), s.horizon, s.pillar))
    top = sorted_items[0]
    return [
        f"Strategy file: {len(items)} signal(s); top priority line — **{top.pillar}** ({top.priority or '—'}): {(top.summary or '')[:100]}{'…' if len(top.summary or '') > 100 else ''}"
    ]
