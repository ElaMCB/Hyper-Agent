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
from src.shadow.capabilities.people_capacity import render_people_capacity_md
from src.shadow.capabilities.qe_pack import render_qe_subagent_pack
from src.shadow.capabilities.resource_allocation import render_resource_allocation_md
from src.shadow.capabilities.strategy_lens import render_strategy_md
from src.shadow.output.writer import (
    prune_headquarters_archives,
    write_brief_artifact,
    write_capability_artifact,
    write_headquarters_artifacts,
    write_headquarters_latest_md,
)
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
    md_path = write_headquarters_latest_md(_ROOT, md, hq_dir)
    print(f"Headquarters: {stamped}", file=sys.stderr, flush=True)
    print(f"Brief mirror: {md_path}", file=sys.stderr, flush=True)
    if latest:
        print(f"Open: {latest}", file=sys.stderr, flush=True)

    ret_cfg = hq_cfg.get("retention") or {}
    if not isinstance(ret_cfg, dict):
        ret_cfg = {}
    max_arch = int(ret_cfg.get("max_archived_html", 0))
    removed = prune_headquarters_archives(_ROOT, hq_dir, max_arch)
    if removed:
        print(f"Pruned {removed} old headquarters-*.html (keeping {max_arch} newest)", file=sys.stderr, flush=True)


def _qe_out(config: dict) -> tuple[str, bool]:
    qe = config.get("qe_subagents") or {}
    return str(qe.get("output_dir", "output/qe")), bool(qe.get("save_on_cli", False))


def cmd_people(config: dict) -> None:
    snap = build_snapshot(_ROOT, config)
    md = render_people_capacity_md(snap, config)
    print(md, flush=True)
    subdir, save = _qe_out(config)
    if save:
        path = write_capability_artifact(_ROOT, md, snap.as_of, out_subdir=subdir, filename_prefix="people")
        print(f"\nSaved: {path}", file=sys.stderr, flush=True)


def cmd_allocation(config: dict) -> None:
    snap = build_snapshot(_ROOT, config)
    md = render_resource_allocation_md(snap, config)
    print(md, flush=True)
    subdir, save = _qe_out(config)
    if save:
        path = write_capability_artifact(_ROOT, md, snap.as_of, out_subdir=subdir, filename_prefix="allocation")
        print(f"\nSaved: {path}", file=sys.stderr, flush=True)


def cmd_strategy(config: dict) -> None:
    snap = build_snapshot(_ROOT, config)
    md = render_strategy_md(snap, config)
    print(md, flush=True)
    subdir, save = _qe_out(config)
    if save:
        path = write_capability_artifact(_ROOT, md, snap.as_of, out_subdir=subdir, filename_prefix="strategy")
        print(f"\nSaved: {path}", file=sys.stderr, flush=True)


def cmd_qe(config: dict) -> None:
    snap = build_snapshot(_ROOT, config)
    md = render_qe_subagent_pack(snap, config)
    print(md, flush=True)
    subdir, save = _qe_out(config)
    if save:
        path = write_capability_artifact(_ROOT, md, snap.as_of, out_subdir=subdir, filename_prefix="qe-pack")
        print(f"\nSaved: {path}", file=sys.stderr, flush=True)


def main() -> None:
    config = _load_config()
    if len(sys.argv) < 2:
        print("Usage: python src/main.py <command>")
        print("  brief        Morning brief (snapshot → markdown; saves under output/briefs by default)")
        print("  headquarters Same snapshot + HQ HTML + latest.md; prunes old HQ archives if configured")
        print("  prep         Meeting prep (stub)")
        print("  people       QE subagent: people & capacity (from data/team.json)")
        print("  allocation   QE subagent: sprint / app allocation (from data/allocations.json)")
        print("  strategy     QE subagent: portfolio strategy signals (from data/strategy.json)")
        print("  qe           All three QE subagents in one markdown document")
        sys.exit(0)

    cmd = sys.argv[1].lower()
    if cmd == "brief":
        cmd_brief(config)
    elif cmd in ("headquarters", "hq"):
        cmd_headquarters(config)
    elif cmd == "prep":
        print(run_prep(_ROOT, config))
    elif cmd == "people":
        cmd_people(config)
    elif cmd in ("allocation", "alloc"):
        cmd_allocation(config)
    elif cmd == "strategy":
        cmd_strategy(config)
    elif cmd == "qe":
        cmd_qe(config)
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()
