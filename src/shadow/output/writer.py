"""Persist brief artifacts for audit trail ("what did Shadow know at standup?")."""

from datetime import datetime
from pathlib import Path


def write_headquarters_artifacts(
    root: Path,
    html: str,
    as_of: datetime,
    hq_dir: str,
    *,
    write_latest: bool = True,
) -> tuple[Path, Path | None]:
    """
    Write `headquarters-2026-04-05T073015Z.html` and optionally `latest.html` for a stable morning URL.
    """
    out_dir = root / hq_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = as_of.strftime("%Y-%m-%dT%H%M%SZ")
    stamped = out_dir / f"headquarters-{stamp}.html"
    stamped.write_text(html, encoding="utf-8")
    latest: Path | None = None
    if write_latest:
        latest = out_dir / "latest.html"
        latest.write_text(html, encoding="utf-8")
    return stamped, latest


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
