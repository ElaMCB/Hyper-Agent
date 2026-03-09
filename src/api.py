"""
Hyper-Agent API. Run: uvicorn src.api:app --reload
From repo root: uvicorn src.api:app --host 0.0.0.0 --port 8000
"""
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import yaml
from fastapi import FastAPI
from fastapi.responses import PlainTextResponse

from src.capabilities.brief import run_brief

app = FastAPI(
    title="Shadow",
    description="AI Test Architect — morning brief, prep, and more.",
    version="0.1.0",
)


def _load_config() -> dict:
    path = _ROOT / "config" / "config.yaml"
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


@app.get("/")
def root():
    return {
        "service": "Shadow",
        "endpoints": {
            "brief": "/brief",
            "brief_md": "/brief.md",
            "health": "/health",
        },
    }


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/brief")
def get_brief():
    """Return morning brief as JSON (markdown in .markdown field)."""
    config = _load_config()
    data_cfg = config.get("data", {})
    data_dir = _ROOT / data_cfg.get("dir", "data")
    brief_cfg = config.get("brief", {})
    llm_cfg = config.get("llm", {})

    markdown = run_brief(
        data_dir=data_dir,
        defects_file=data_cfg.get("defects_file"),
        test_runs_file=data_cfg.get("test_runs_file"),
        use_llm=bool(llm_cfg.get("enabled")),
        max_bullets=brief_cfg.get("max_bullets", 5),
    )
    return {"markdown": markdown}


@app.get("/brief.md", response_class=PlainTextResponse)
def get_brief_raw():
    """Return morning brief as plain markdown (e.g. for browser or curl)."""
    config = _load_config()
    data_cfg = config.get("data", {})
    data_dir = _ROOT / data_cfg.get("dir", "data")
    brief_cfg = config.get("brief", {})
    llm_cfg = config.get("llm", {})

    return run_brief(
        data_dir=data_dir,
        defects_file=data_cfg.get("defects_file"),
        test_runs_file=data_cfg.get("test_runs_file"),
        use_llm=bool(llm_cfg.get("enabled")),
        max_bullets=brief_cfg.get("max_bullets", 5),
    )
