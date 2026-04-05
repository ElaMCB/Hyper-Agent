"""Persist brief artifacts for audit trail ("what did Shadow know at standup?")."""

from datetime import datetime
from pathlib import Path


def write_brief_artifact(root: Path, markdown: str, as_of: datetime, briefs_dir: str) -> Path:
    """
    Write `output/briefs/brief-2026-04-05T073015Z.md` (UTC, filesystem-safe).
    Returns path written.
    """
    out_dir = root / briefs_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = as_of.strftime("%Y-%m-%dT%H%M%SZ")
    path = out_dir / f"brief-{stamp}.md"
    path.write_text(markdown, encoding="utf-8")
    return path
