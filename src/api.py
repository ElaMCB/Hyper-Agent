"""
Hyper-Agent API. Run: uvicorn src.api:app --reload
Same spine as CLI: build_snapshot → render_brief.
"""
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import yaml
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, PlainTextResponse

from src.shadow.capabilities.brief import render_brief
from src.shadow.capabilities.headquarters import render_headquarters_html
from src.shadow.capabilities.qe_pack import render_qe_subagent_pack
from src.shadow.output.writer import (
    prune_headquarters_archives,
    write_brief_artifact,
    write_headquarters_artifacts,
    write_headquarters_latest_md,
)
from src.shadow.snapshot import build_snapshot

app = FastAPI(
    title="Shadow",
    description="AI Test Architect — morning brief, prep, and more.",
    version="0.2.0",
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
        "architecture": "snapshot → capabilities (brief, …)",
        "endpoints": {
            "brief": "/brief",
            "brief_md": "/brief.md",
            "headquarters": "/headquarters.html",
            "qe_md": "/qe.md",
            "health": "/health",
        },
    }


@app.get("/health")
def health():
    return {"status": "ok"}


def _brief_markdown(config: dict, *, persist: bool = False) -> str:
    snap = build_snapshot(_ROOT, config)
    llm_on = bool(config.get("llm", {}).get("enabled"))
    md = render_brief(snap, _ROOT, config, use_llm=llm_on)
    out_cfg = config.get("output", {})
    if persist and out_cfg.get("save_on_api", False):
        briefs_dir = out_cfg.get("briefs_dir", "output/briefs")
        write_brief_artifact(_ROOT, md, snap.as_of, briefs_dir)
    return md


@app.get("/brief")
def get_brief(persist: bool = False):
    """Return morning brief as JSON. Use ?persist=1 to write artifact if save_on_api is true in config."""
    config = _load_config()
    markdown = _brief_markdown(config, persist=persist)
    return {"markdown": markdown}


@app.get("/brief.md", response_class=PlainTextResponse)
def get_brief_raw(persist: bool = False):
    config = _load_config()
    return _brief_markdown(config, persist=persist)


def _headquarters_html(config: dict, *, persist: bool = False) -> str:
    snap = build_snapshot(_ROOT, config)
    llm_on = bool(config.get("llm", {}).get("enabled"))
    md = render_brief(snap, _ROOT, config, use_llm=llm_on)
    html_page = render_headquarters_html(snap, config, full_brief_markdown=md)
    if persist:
        hq_cfg = config.get("headquarters", {}) or {}
        hq_dir = hq_cfg.get("dir", "output/headquarters")
        write_latest = bool(hq_cfg.get("write_latest", True))
        write_headquarters_artifacts(_ROOT, html_page, snap.as_of, hq_dir, write_latest=write_latest)
        write_headquarters_latest_md(_ROOT, md, hq_dir)
        ret_cfg = hq_cfg.get("retention") or {}
        if not isinstance(ret_cfg, dict):
            ret_cfg = {}
        max_arch = int(ret_cfg.get("max_archived_html", 0))
        prune_headquarters_archives(_ROOT, hq_dir, max_arch)
    return html_page


@app.get("/qe.md", response_class=PlainTextResponse)
def get_qe_pack():
    """QE subagent pack: people & capacity + allocation + strategy (markdown)."""
    config = _load_config()
    snap = build_snapshot(_ROOT, config)
    return render_qe_subagent_pack(snap, config)


@app.get("/headquarters.html", response_class=HTMLResponse)
def get_headquarters(persist: bool = False):
    """Single-page dashboard (same data as brief). ?persist=1 writes output/headquarters/ on the server."""
    config = _load_config()
    return _headquarters_html(config, persist=persist)
