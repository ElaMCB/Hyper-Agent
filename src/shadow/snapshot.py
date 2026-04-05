"""Build a Snapshot from config: adapters in, one spine out."""

import os
from datetime import datetime, timezone
from pathlib import Path

from .models import Snapshot
from .adapters.file_export import FileExportAdapter


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
    file_defects = files.get_defects(defects_file)
    if file_defects:
        sources.append(f"File: defects ({defects_file or 'defects.json'})")
    defects.extend(file_defects)

    test_runs = files.get_test_runs(test_runs_file)
    if test_runs:
        sources.append(f"File: test runs ({test_runs_file or 'test_runs.json'})")

    if not sources:
        sources.append("(No successful sources — enable ADO and/or add data/ files.)")

    return Snapshot(
        as_of=as_of,
        sources=sources,
        defects=defects,
        test_runs=test_runs,
        notes=notes,
    )
