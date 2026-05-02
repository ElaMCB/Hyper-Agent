"""Morning brief: Snapshot in → deterministic summary → optional LLM polish → markdown out."""

from pathlib import Path

from ..models import Snapshot
from ..output.formatter import format_brief_md
from .people_capacity import people_capacity_summary_bullets
from .resource_allocation import resource_allocation_summary_bullets
from .strategy_lens import strategy_summary_bullets

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
    return _build_summary(snapshot, mb, config)


def _work_mail_bullets(snapshot: Snapshot, max_bullets: int) -> tuple[list[str], bool, bool]:
    defects = snapshot.defects
    test_runs = snapshot.test_runs
    mail = snapshot.mail_messages
    bullets: list[str] = []
    has_personal = bool(mail)
    has_work = bool(defects or test_runs)

    if mail:
        unread = sum(1 for m in mail if m.is_unread)
        bullets.append(f"Gmail: {len(mail)} in view, {unread} unread.")
        for m in mail:
            if len(bullets) >= max_bullets:
                break
            subj = (m.subject or "")[:72]
            suf = "…" if len(m.subject or "") > 72 else ""
            bullets.append(f"— {subj}{suf}")

    if defects and len(bullets) < max_bullets:
        high = [d for d in defects if _is_high_severity(d.severity)]
        open_count = len([d for d in defects if _is_open_status(d.status)])
        bullets.append(f"Defects: {len(defects)} total, {len(high)} critical/high, {open_count} not closed.")
        if high and len(bullets) < max_bullets:
            t = high[0].title[:60]
            suf = "…" if len(high[0].title) > 60 else ""
            bullets.append(f"Top severity: {high[0].id} — {t}{suf}")
    elif not has_personal and len(bullets) < max_bullets:
        bullets.append("No defect data in this snapshot. Add data/ exports or enable Azure DevOps.")

    if test_runs and len(bullets) < max_bullets:
        latest = test_runs[0]
        extra = f" Passed: {latest.passed}, Failed: {latest.failed}" if latest.total else ""
        bullets.append(f"Latest test run: {latest.name} — {latest.status}.{extra}")
    elif not has_personal and not defects and len(bullets) < max_bullets:
        bullets.append("No test run data in snapshot. Add test_runs.json under data/.")

    if len(bullets) > max_bullets:
        bullets = bullets[:max_bullets]
    return bullets, has_personal, has_work


def _build_summary(snapshot: Snapshot, max_bullets: int, config: dict) -> tuple[list[str], str]:
    brief_cfg = config.get("brief") or {}
    qe: list[str] = []
    if brief_cfg.get("include_qe_context"):
        qe_mx = int(brief_cfg.get("max_qe_context_bullets", 3))
        qe.extend(people_capacity_summary_bullets(snapshot, config))
        qe.extend(resource_allocation_summary_bullets(snapshot, config))
        qe.extend(strategy_summary_bullets(snapshot, config))
        qe = qe[:qe_mx]

    work_max = max(0, max_bullets - len(qe))
    work, has_personal, has_work = _work_mail_bullets(snapshot, work_max)
    bullets = qe + work
    if len(bullets) > max_bullets:
        bullets = bullets[:max_bullets]

    has_qe_data = bool(
        snapshot.team_members or snapshot.capacity_allocations or snapshot.strategy_signals
    )

    if has_personal and not has_work and not has_qe_data:
        suggested = "Triage unread Gmail; reply, archive, or snooze so nothing important slips."
    elif has_personal and has_work:
        suggested = "Blend inbox triage with defect and test-run priorities for today."
    elif has_work and not has_qe_data:
        suggested = "Review open defects and latest test run; align with your QA team on priorities."
    elif has_qe_data and not has_work and not has_personal:
        suggested = (
            "Reconcile team capacity and sprint allocations with strategy signals; pick 1–2 leadership moves today."
        )
    elif has_qe_data and (has_work or has_personal):
        suggested = "Balance people/capacity/strategy context with inbox and execution signals for today."
    else:
        suggested = "Enable Gmail, work data, and/or QE files (team, allocations, strategy), then run again."

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
    brief_cfg = config.get("brief") or {}
    title = str(brief_cfg.get("title", "# Morning brief")).strip() or "# Morning brief"
    md = format_brief_md(bullets, suggested, title=title)

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
