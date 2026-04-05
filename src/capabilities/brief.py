"""Morning brief capability: aggregate data, optional LLM, return markdown."""

from pathlib import Path

from src.data.adapters.file_export import FileExportAdapter
from src.output.formatter import format_brief_md


_CLOSED_STATES = frozenset({"closed", "done", "removed"})


def _is_open_status(status: str) -> bool:
    return (status or "").strip().lower() not in _CLOSED_STATES


def _is_high_severity(severity: str) -> bool:
    s = (severity or "").lower()
    if "critical" in s or "high" in s:
        return True
    t = (severity or "").strip()
    return t.startswith("1") or t.startswith("2")


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
    config: dict | None = None,
) -> str:
    """
    Load defects and test runs, build a short summary, optionally use LLM to polish.
    If config is passed and azure_devops.enabled, merges bugs from ADO with file-based defects.
    Returns markdown string.
    """
    root = _find_repo_root()
    if config is not None:
        mb = config.get("brief", {}).get("max_bullets")
        if mb is not None:
            max_bullets = int(mb)

    data_dir = data_dir or root / "data"
    adapter = FileExportAdapter(data_dir)

    defects: list = []
    ado_error = ""
    if config and config.get("azure_devops", {}).get("enabled"):
        try:
            from src.data.adapters.azure_devops import AzureDevOpsAdapter

            ado = AzureDevOpsAdapter.from_config(config["azure_devops"])
            defects.extend(ado.fetch_bugs())
        except Exception as e:
            ado_error = str(e)

    defects.extend(adapter.get_defects(defects_file))
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

    md = format_brief_md(bullets, suggested)
    if ado_error:
        md += f"\n\n*Azure DevOps: could not load bugs — {ado_error}*"
    elif config and config.get("azure_devops", {}).get("enabled"):
        if any(str(d.id).startswith("ado-") for d in defects):
            md += "\n\n*Bugs: live data from Azure DevOps.*"
    return md


def _build_summary(defects: list, test_runs: list, max_bullets: int) -> tuple[list[str], str]:
    """Build bullet list and suggested focus from raw data."""
    bullets = []

    if defects:
        high = [d for d in defects if _is_high_severity(d.severity)]
        open_count = len([d for d in defects if _is_open_status(d.status)])
        bullets.append(f"Defects: {len(defects)} total, {len(high)} critical/high, {open_count} not closed.")
        if high and len(bullets) < max_bullets:
            bullets.append(f"Top severity: {high[0].id} — {high[0].title[:60]}...")
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
