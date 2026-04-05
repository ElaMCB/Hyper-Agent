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
from src.shadow.capabilities.prep import run_prep
from src.shadow.output.writer import write_brief_artifact
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


def main() -> None:
    config = _load_config()
    if len(sys.argv) < 2:
        print("Usage: python src/main.py <command>")
        print("  brief   Morning brief (snapshot → markdown; saves under output/briefs by default)")
        print("  prep    Meeting prep (stub)")
        sys.exit(0)

    cmd = sys.argv[1].lower()
    if cmd == "brief":
        cmd_brief(config)
    elif cmd == "prep":
        print(run_prep(_ROOT, config))
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()
