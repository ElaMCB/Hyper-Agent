"""
Hyper-Agent CLI. Run from repo root: python src/main.py brief
Architecture: build_snapshot → render_brief → optional artifact on disk.
"""
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import yaml
from src.shadow.capabilities.brief import render_brief
from src.shadow.capabilities.headquarters import render_headquarters_html
from src.shadow.capabilities.prep import run_prep
from src.shadow.output.writer import write_brief_artifact, write_headquarters_artifacts
from src.shadow.snapshot import build_snapshot


def _load_config() -> dict:
    path = _ROOT / "config" / "config.yaml"
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def cmd_brief(config: dict) -> None:
    snap = build_snapshot(_ROOT, config)
    llm_on = bool(config.get("llm", {}).get("enabled"))
    md = render_brief(snap, _ROOT, config, use_llm=llm_on)
    print(md, flush=True)

    out_cfg = config.get("output", {})
    if out_cfg.get("save_on_cli", True):
        briefs_dir = out_cfg.get("briefs_dir", "output/briefs")
        path = write_brief_artifact(_ROOT, md, snap.as_of, briefs_dir)
        print(f"\nSaved: {path}", file=sys.stderr, flush=True)


def cmd_headquarters(config: dict) -> None:
    """One snapshot → markdown brief on disk + HTML dashboard (latest + timestamped)."""
    snap = build_snapshot(_ROOT, config)
    llm_on = bool(config.get("llm", {}).get("enabled"))
    md = render_brief(snap, _ROOT, config, use_llm=llm_on)
    page = render_headquarters_html(snap, config, full_brief_markdown=md)

    out_cfg = config.get("output", {})
    if out_cfg.get("save_on_cli", True):
        briefs_dir = out_cfg.get("briefs_dir", "output/briefs")
        bp = write_brief_artifact(_ROOT, md, snap.as_of, briefs_dir)
        print(f"Brief saved: {bp}", file=sys.stderr, flush=True)

    hq_cfg = config.get("headquarters", {}) or {}
    hq_dir = hq_cfg.get("dir", "output/headquarters")
    write_latest = bool(hq_cfg.get("write_latest", True))
    stamped, latest = write_headquarters_artifacts(
        _ROOT, page, snap.as_of, hq_dir, write_latest=write_latest
    )
    print(f"Headquarters: {stamped}", file=sys.stderr, flush=True)
    if latest:
        print(f"Open: {latest}", file=sys.stderr, flush=True)


def main() -> None:
    config = _load_config()
    if len(sys.argv) < 2:
        print("Usage: python src/main.py <command>")
        print("  brief        Morning brief (snapshot → markdown; saves under output/briefs by default)")
        print("  headquarters Same snapshot + HTML dashboard (brief + tables; saves latest.html)")
        print("  prep         Meeting prep (stub)")
        sys.exit(0)

    cmd = sys.argv[1].lower()
    if cmd == "brief":
        cmd_brief(config)
    elif cmd in ("headquarters", "hq"):
        cmd_headquarters(config)
    elif cmd == "prep":
        print(run_prep(_ROOT, config))
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()
