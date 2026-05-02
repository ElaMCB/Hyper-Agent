"""QE subagent: who is on which app this sprint — from Snapshot.capacity_allocations."""

from __future__ import annotations

from collections import defaultdict

from ..models import Snapshot


def render_resource_allocation_md(snapshot: Snapshot, config: dict) -> str:
    rows = snapshot.capacity_allocations
    lines: list[str] = ["# Resource allocation (QE)", ""]

    if not rows:
        lines.append(
            "*No allocation rows — set `data.load_allocations: true` and add `data/allocations.json`.*"
        )
        lines.append("")
        return "\n".join(lines)

    totals: dict[tuple[str, str], int] = defaultdict(int)
    for a in rows:
        if a.focus_pct is not None:
            totals[(a.person_id, a.sprint_label)] += a.focus_pct

    over = [f"{pid} @ {sp}" for (pid, sp), v in totals.items() if v > 100]
    if over:
        lines.append("**Warning:** focus % sums > 100 for:")
        for x in over:
            lines.append(f"- {x}")
        lines.append("")

    by_app: dict[str, list] = defaultdict(list)
    for a in rows:
        key = a.app_name or "(no app)"
        by_app[key].append(a)

    lines.append("## By app")
    for app in sorted(by_app.keys()):
        lines.append(f"### {app}")
        for a in by_app[app]:
            who = a.person_name or a.person_id
            pct = f"{a.focus_pct}%" if a.focus_pct is not None else "—"
            sp = a.sprint_label or "—"
            note = a.commitment_note or ""
            lines.append(f"- **{who}** — {pct} · sprint `{sp}`" + (f" — _{note}_" if note else ""))
        lines.append("")

    lines.append("| Person | App | Sprint | % | Commitment |")
    lines.append("| --- | --- | --- | --- | --- |")
    for a in rows:
        who = a.person_name or a.person_id
        pct = str(a.focus_pct) if a.focus_pct is not None else "—"
        note = (a.commitment_note or "").replace("|", "\\|")[:100]
        lines.append(
            f"| {who} | {a.app_name} | {a.sprint_label} | {pct} | {note} |"
        )
    lines.append("")
    return "\n".join(lines)


def resource_allocation_summary_bullets(snapshot: Snapshot, _config: dict) -> list[str]:
    rows = snapshot.capacity_allocations
    if not rows:
        return []
    apps = {a.app_name or "(no app)" for a in rows}
    return [f"Allocations: {len(rows)} row(s) across {len(apps)} app bucket(s)."]
