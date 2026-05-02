"""Persist brief artifacts for audit trail ("what did Shadow know at standup?")."""

from datetime import datetime
from pathlib import Path


def write_headquarters_latest_md(root: Path, markdown: str, hq_dir: str) -> Path:
    """
    Mirror the run's morning brief next to HQ HTML: `output/headquarters/latest.md` (overwritten each run).
    """
    out_dir = root / hq_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "latest.md"
    path.write_text(markdown, encoding="utf-8")
    return path


def prune_headquarters_archives(root: Path, hq_dir: str, max_keep: int) -> int:
    """
    Delete oldest `headquarters-*.html` files in hq_dir, keeping the `max_keep` newest by filename.
    Does not touch `latest.html` or `latest.md`. Returns number of files removed.
    """
    if max_keep <= 0:
        return 0
    d = root / hq_dir
    if not d.is_dir():
        return 0
    archived = sorted(d.glob("headquarters-*.html"), key=lambda p: p.name, reverse=True)
    to_remove = archived[max_keep:]
    for p in to_remove:
        p.unlink(missing_ok=True)
    return len(to_remove)


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


def write_capability_artifact(
    root: Path, markdown: str, as_of: datetime, *, out_subdir: str, filename_prefix: str
) -> Path:
    """Write e.g. `output/qe/qe-pack-2026-05-02T120000Z.md` for subagent runs."""
    out_dir = root / out_subdir
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = as_of.strftime("%Y-%m-%dT%H%M%SZ")
    path = out_dir / f"{filename_prefix}-{stamp}.md"
    path.write_text(markdown, encoding="utf-8")
    return path


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
