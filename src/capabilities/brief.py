"""Morning brief capability: aggregate data, optional LLM, return markdown."""

from pathlib import Path

from src.data.adapters.file_export import FileExportAdapter
from src.output.formatter import format_brief_md


def _find_repo_root() -> Path:
    cwd = Path.cwd()
    if (cwd / "config" / "config.yaml").exists():
        return cwd
    if (cwd.parent / "config" / "config.yaml").exists():
        return cwd.parent
    return cwd


def run_brief(
    data_dir: Path | None = None,
    defects_file: str | None = None,
    test_runs_file: str | None = None,
    use_llm: bool = False,
    max_bullets: int = 5,
) -> str:
    """
    Load defects and test runs, build a short summary, optionally use LLM to polish.
    Returns markdown string.
    """
    root = _find_repo_root()
    data_dir = data_dir or root / "data"
    adapter = FileExportAdapter(data_dir)

    defects = adapter.get_defects(defects_file)
    test_runs = adapter.get_test_runs(test_runs_file)

    # Structured summary (no LLM)
    bullets, suggested = _build_summary(defects, test_runs, max_bullets)

    if use_llm and bullets:
        try:
            from src.llm.client import load_prompt, llm_complete
            import yaml
            cfg_path = root / "config" / "config.yaml"
            cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) if cfg_path.exists() else {}
            llm_cfg = cfg.get("llm", {})
            summary = "\n".join(f"- {b}" for b in bullets) + "\n\nSuggested focus: " + suggested
            user = load_prompt("brief_user.txt", summary=summary, max_bullets=str(max_bullets))
            system = (root / "config" / "prompts" / "brief_system.txt").read_text(encoding="utf-8")
            out = llm_complete(
                system,
                user,
                provider=llm_cfg.get("provider", "openai"),
                model=llm_cfg.get("model", "gpt-4o-mini"),
            )
            return out.strip() if out else format_brief_md(bullets, suggested)
        except Exception as e:
            # Fallback to non-LLM if key missing or API error
            return format_brief_md(bullets, suggested) + f"\n\n*(LLM skipped: {e})*"

    return format_brief_md(bullets, suggested)


def _build_summary(defects: list, test_runs: list, max_bullets: int) -> tuple[list[str], str]:
    """Build bullet list and suggested focus from raw data."""
    bullets = []

    if defects:
        critical = [d for d in defects if d.severity and "critical" in d.severity.lower()]
        open_count = len([d for d in defects if d.status and "open" in d.status.lower() or "new" in d.status.lower()])
        bullets.append(f"Defects: {len(defects)} total, {len(critical)} critical/high, {open_count} open.")
        if critical and len(bullets) < max_bullets:
            bullets.append(f"Critical/open: {critical[0].id} — {critical[0].title[:60]}...")
    else:
        bullets.append("No defect data loaded. Drop defects.json (or defects.csv) into data/.")

    if test_runs:
        latest = test_runs[0]
        bullets.append(f"Latest test run: {latest.name} — {latest.status}." + (
            f" Passed: {latest.passed}, Failed: {latest.failed}" if latest.total else ""
        ))
    else:
        bullets.append("No test run data. Drop test_runs.json into data/ for execution summary.")

    if len(bullets) > max_bullets:
        bullets = bullets[:max_bullets]

    suggested = "Review open defects and latest test run; align with your QA team on priorities." if defects or test_runs else "Add data exports to data/ and run brief again."
    return bullets, suggested
