"""Deterministic markdown formatting (no LLM)."""


def format_brief_md(bullets: list[str], suggested_focus: str) -> str:
    lines = ["# Morning brief", ""]
    for b in bullets:
        lines.append(f"- {b}")
    lines.append("")
    lines.append(f"**Suggested focus today:** {suggested_focus}")
    return "\n".join(lines)
