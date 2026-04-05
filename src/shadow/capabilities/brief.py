"""Morning brief: Snapshot in → deterministic summary → optional LLM polish → markdown out."""

from pathlib import Path

from ..models import Snapshot
from ..output.formatter import format_brief_md

_CLOSED_STATES = frozenset({"closed", "done", "removed"})


def _is_open_status(status: str) -> bool:
    return (status or "").strip().lower() not in _CLOSED_STATES


def _is_high_severity(severity: str) -> bool:
    s = (severity or "").lower()
    if "critical" in s or "high" in s:
        return True
    t = (severity or "").strip()
    return t.startswith("1") or t.startswith("2")


def _provenance_footer(snapshot: Snapshot) -> str:
    as_of = snapshot.as_of.strftime("%Y-%m-%dT%H:%M:%SZ")
    src = " · ".join(snapshot.sources)
    return f"\n\n*As of {as_of} (UTC) · Sources: {src}*"


def get_brief_bullets_and_focus(
    snapshot: Snapshot,
    config: dict,
    *,
    max_bullets: int | None = None,
) -> tuple[list[str], str]:
    """Public summary used by brief and headquarters (same numbers, same focus line)."""
    mb = max_bullets if max_bullets is not None else int(config.get("brief", {}).get("max_bullets", 5))
    return _build_summary(snapshot, mb)


def _build_summary(snapshot: Snapshot, max_bullets: int) -> tuple[list[str], str]:
    defects = snapshot.defects
    test_runs = snapshot.test_runs
    bullets: list[str] = []

    if defects:
        high = [d for d in defects if _is_high_severity(d.severity)]
        open_count = len([d for d in defects if _is_open_status(d.status)])
        bullets.append(f"Defects: {len(defects)} total, {len(high)} critical/high, {open_count} not closed.")
        if high and len(bullets) < max_bullets:
            bullets.append(f"Top severity: {high[0].id} — {high[0].title[:60]}...")
    else:
        bullets.append("No defect data in this snapshot. Add data/ exports or enable Azure DevOps.")

    if test_runs:
        latest = test_runs[0]
        extra = f" Passed: {latest.passed}, Failed: {latest.failed}" if latest.total else ""
        bullets.append(f"Latest test run: {latest.name} — {latest.status}.{extra}")
    else:
        bullets.append("No test run data in snapshot. Add test_runs.json under data/.")

    if len(bullets) > max_bullets:
        bullets = bullets[:max_bullets]

    suggested = (
        "Review open defects and latest test run; align with your QA team on priorities."
        if defects or test_runs
        else "Attach data sources and run brief again."
    )
    return bullets, suggested


def render_brief(
    snapshot: Snapshot,
    root: Path,
    config: dict,
    *,
    use_llm: bool = False,
    max_bullets: int | None = None,
) -> str:
    """
    Deterministic brief from Snapshot; optional LLM pass; always append provenance + notes.
    """
    mb = max_bullets if max_bullets is not None else int(config.get("brief", {}).get("max_bullets", 5))

    bullets, suggested = get_brief_bullets_and_focus(snapshot, config, max_bullets=mb)
    md = format_brief_md(bullets, suggested)

    if use_llm and bullets:
        try:
            from src.llm.client import load_prompt, llm_complete

            llm_cfg = config.get("llm", {})
            summary = "\n".join(f"- {b}" for b in bullets) + "\n\nSuggested focus: " + suggested
            user = load_prompt("brief_user.txt", summary=summary, max_bullets=str(mb))
            system = (root / "config" / "prompts" / "brief_system.txt").read_text(encoding="utf-8")
            out = llm_complete(
                system,
                user,
                provider=llm_cfg.get("provider", "openai"),
                model=llm_cfg.get("model", "gpt-4o-mini"),
            )
            if out.strip():
                md = out.strip()
        except Exception as e:
            md += f"\n\n*(LLM skipped: {e})*"

    md += _provenance_footer(snapshot)

    for note in snapshot.notes:
        md += f"\n\n*{note}*"

    return md
