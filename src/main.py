"""
Hyper-Agent CLI. Run from repo root: python src/main.py brief
"""
import sys
from pathlib import Path

# Ensure repo root is on path so "from src.xxx" works when running python src/main.py
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import yaml
from src.capabilities.brief import run_brief


def _load_config() -> dict:
    path = _ROOT / "config" / "config.yaml"
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def cmd_brief(config: dict) -> None:
    data_cfg = config.get("data", {})
    data_dir = _ROOT / data_cfg.get("dir", "data")
    brief_cfg = config.get("brief", {})
    llm_cfg = config.get("llm", {})

    out = run_brief(
        data_dir=data_dir,
        defects_file=data_cfg.get("defects_file"),
        test_runs_file=data_cfg.get("test_runs_file"),
        use_llm=bool(llm_cfg.get("enabled")),
        max_bullets=brief_cfg.get("max_bullets", 5),
        config=config,
    )
    print(out)


def main() -> None:
    config = _load_config()
    if len(sys.argv) < 2:
        print("Usage: python src/main.py <command>")
        print("  brief   Morning brief (data from data/)")
        print("  prep    Meeting prep (coming soon)")
        sys.exit(0)

    cmd = sys.argv[1].lower()
    if cmd == "brief":
        cmd_brief(config)
    elif cmd == "prep":
        print("Meeting prep: coming soon. Add actions.json to data/ and we'll wire it next.")
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()
