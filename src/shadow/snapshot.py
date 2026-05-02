"""Build a Snapshot from config: adapters in, one spine out."""

import os
from datetime import datetime, timezone
from pathlib import Path

from .models import Snapshot
from .adapters.file_export import FileExportAdapter
from .adapters.gmail import fetch_gmail_messages


def find_repo_root(cwd: Path | None = None) -> Path:
    cwd = cwd or Path.cwd()
    if (cwd / "config" / "config.yaml").exists():
        return cwd
    if (cwd.parent / "config" / "config.yaml").exists():
        return cwd.parent
    return cwd


def build_snapshot(root: Path, config: dict) -> Snapshot:
    """
    Collect defects and test runs from all enabled adapters.
    `as_of` is UTC; `sources` lists what contributed (provenance for the brief).
    """
    as_of = datetime.now(timezone.utc)
    data_cfg = config.get("data", {})
    data_dir = root / data_cfg.get("dir", "data")
    defects_file = data_cfg.get("defects_file")
    test_runs_file = data_cfg.get("test_runs_file")

    sources: list[str] = []
    notes: list[str] = []
    defects: list = []
    mail_messages: list = []
    team_members: list = []
    capacity_allocations: list = []
    strategy_signals: list = []

    if config.get("azure_devops", {}).get("enabled"):
        try:
            from .adapters.azure_devops import AzureDevOpsAdapter

            ado_cfg = config["azure_devops"]
            ado = AzureDevOpsAdapter.from_config(ado_cfg)
            bugs = ado.fetch_bugs()
            defects.extend(bugs)
            org = (ado_cfg.get("organization") or os.getenv("AZDO_ORG") or "").strip()
            proj = (ado_cfg.get("project") or os.getenv("AZDO_PROJECT") or "").strip()
            if org and proj:
                sources.append(f"Azure DevOps: {org}/{proj} (open Bugs)")
            else:
                sources.append("Azure DevOps: open Bugs")
        except Exception as e:
            notes.append(f"Azure DevOps: {e}")

    files = FileExportAdapter(data_dir)
    load_defects = data_cfg.get("load_defects", True)
    load_test_runs = data_cfg.get("load_test_runs", True)

    file_defects: list = []
    if load_defects is not False:
        file_defects = files.get_defects(defects_file)
        if file_defects:
            sources.append(f"File: defects ({defects_file or 'defects.json'})")
    defects.extend(file_defects)

    test_runs = []
    if load_test_runs is not False:
        test_runs = files.get_test_runs(test_runs_file)
        if test_runs:
            sources.append(f"File: test runs ({test_runs_file or 'test_runs.json'})")

    gmail_cfg = config.get("gmail") or {}
    if gmail_cfg.get("enabled"):
        msgs, gmail_notes = fetch_gmail_messages(root, gmail_cfg)
        mail_messages.extend(msgs)
        notes.extend(gmail_notes)
        if msgs:
            sources.append(f"Gmail: {len(msgs)} message(s)")
        elif not gmail_notes:
            sources.append("Gmail: connected (0 messages for this query)")
        # errors-only: provenance stays in notes; avoid claiming "0 messages" on failure

    load_team = data_cfg.get("load_team", False)
    if load_team is not False:
        team_file = data_cfg.get("team_file", "team.json")
        tm = files.get_team_members(team_file)
        team_members.extend(tm)
        if tm:
            sources.append(f"File: team ({team_file})")

    load_alloc = data_cfg.get("load_allocations", False)
    if load_alloc is not False:
        alloc_file = data_cfg.get("allocations_file", "allocations.json")
        al = files.get_allocations(alloc_file)
        capacity_allocations.extend(al)
        if al:
            sources.append(f"File: allocations ({alloc_file})")

    load_strategy = data_cfg.get("load_strategy", False)
    if load_strategy is not False:
        strat_file = data_cfg.get("strategy_file", "strategy.json")
        st = files.get_strategy_signals(strat_file)
        strategy_signals.extend(st)
        if st:
            sources.append(f"File: strategy ({strat_file})")

    if not sources:
        sources.append(
            "(No sources — enable Gmail/ADO, load team/allocations/strategy in config, or add data/ files.)"
        )

    return Snapshot(
        as_of=as_of,
        sources=sources,
        defects=defects,
        test_runs=test_runs,
        mail_messages=mail_messages,
        team_members=team_members,
        capacity_allocations=capacity_allocations,
        strategy_signals=strategy_signals,
        notes=notes,
    )
