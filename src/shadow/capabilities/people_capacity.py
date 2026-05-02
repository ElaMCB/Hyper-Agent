"""QE subagent: people, skills, vacation, morale flags, 1:1 recency, performance notes — from Snapshot.team_members."""

from __future__ import annotations

from datetime import timezone

from ..models import Snapshot


def _days_since(as_of, dt) -> int | None:
    if dt is None:
        return None
    a = as_of
    d = dt
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return (a - d).days


def render_people_capacity_md(snapshot: Snapshot, config: dict) -> str:
    people_cfg = config.get("people") or {}
    stale_days = int(people_cfg.get("one_on_one_stale_days", 21))
    team = snapshot.team_members
    lines: list[str] = ["# People & capacity (QE)", ""]

    if not team:
        lines.append(
            "*No team rows in this snapshot. Set `data.load_team: true` and add `data/team.json` (see sample).*"
        )
        lines.append("")
        return "\n".join(lines)

    on_leave = sum(1 for m in team if m.on_vacation)
    morale_watch = [
        m.name or m.id
        for m in team
        if (m.morale_flag or "").lower() in ("amber", "yellow", "red")
    ]
    stale_121: list[str] = []
    for m in team:
        if m.last_one_on_one is None:
            stale_121.append(m.name or m.id)
        else:
            days = _days_since(snapshot.as_of, m.last_one_on_one)
            if days is not None and days > stale_days:
                stale_121.append(m.name or m.id)

    lines.append(f"- **Headcount in file:** {len(team)}")
    lines.append(f"- **On vacation (flag):** {on_leave}")
    if morale_watch:
        lines.append(f"- **Morale watch (amber/red):** {', '.join(morale_watch)}")
    if stale_121:
        lines.append(f"- **1:1 stale (>{stale_days}d or missing):** {', '.join(stale_121)}")
    lines.append("")
    lines.append("| Name | Role | Skills | Vacation | Morale | Last 1:1 | Performance note |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- |")
    for m in team:
        skills = ", ".join(m.skills[:6]) + ("…" if len(m.skills) > 6 else "")
        vac = "Yes" if m.on_vacation else "No"
        vu = ""
        if m.vacation_until:
            vu = m.vacation_until.strftime("%Y-%m-%d")
        ooo = m.last_one_on_one.strftime("%Y-%m-%d") if m.last_one_on_one else "—"
        note = (m.performance_note or "").replace("|", "\\|")[:80]
        lines.append(
            f"| {m.name or m.id} | {m.role} | {skills} | {vac} {vu} | {m.morale_flag or '—'} | {ooo} | {note} |"
        )
    lines.append("")
    lines.append(
        "*Morale and performance fields are labels you maintain; Shadow does not infer them from chat or HR systems.*"
    )
    return "\n".join(lines)


def people_capacity_summary_bullets(snapshot: Snapshot, config: dict) -> list[str]:
    """Short lines for the main morning brief when `brief.include_qe_context` is on."""
    team = snapshot.team_members
    if not team:
        return []
    people_cfg = config.get("people") or {}
    stale_days = int(people_cfg.get("one_on_one_stale_days", 21))
    on_leave = sum(1 for m in team if m.on_vacation)
    stale_ct = 0
    for m in team:
        if m.last_one_on_one is None:
            stale_ct += 1
        else:
            d = _days_since(snapshot.as_of, m.last_one_on_one)
            if d is not None and d > stale_days:
                stale_ct += 1
    bullets = [f"QE team (file): {len(team)} people, {on_leave} flagged on vacation."]
    if stale_ct:
        bullets.append(f"1:1 hygiene: {stale_ct} member(s) past {stale_days}d or missing last 1:1 date.")
    return bullets
