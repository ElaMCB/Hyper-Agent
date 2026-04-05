"""Headquarters: one HTML page from a Snapshot — open `output/headquarters/latest.html` each morning."""

from __future__ import annotations

import html
from datetime import datetime, timezone
from ..models import Defect, Snapshot, TestRun
from .brief import get_brief_bullets_and_focus


def _fmt_dt_utc(dt: datetime | None) -> str:
    if not dt:
        return "—"
    if dt.tzinfo is None:
        return dt.strftime("%Y-%m-%d %H:%M") + " (naive)"
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def render_headquarters_html(
    snapshot: Snapshot,
    config: dict,
    *,
    full_brief_markdown: str,
    max_defect_rows: int = 50,
    max_run_rows: int = 20,
) -> str:
    bullets, suggested = get_brief_bullets_and_focus(snapshot, config)
    hq_cfg = config.get("headquarters", {}) or {}
    links = hq_cfg.get("links") or []

    as_of_utc = snapshot.as_of.strftime("%Y-%m-%d %H:%M:%S UTC")
    title = html.escape(hq_cfg.get("title", "Shadow — Headquarters"))

    def rows_defects(defects: list[Defect]) -> str:
        parts: list[str] = []
        for d in defects[:max_defect_rows]:
            parts.append(
                "<tr>"
                f"<td><code>{html.escape(d.id)}</code></td>"
                f"<td>{html.escape(d.title[:120])}{'…' if len(d.title) > 120 else ''}</td>"
                f"<td>{html.escape(d.severity)}</td>"
                f"<td>{html.escape(d.status)}</td>"
                "</tr>"
            )
        if not parts:
            return '<tr><td colspan="4" class="muted">No defects in this snapshot.</td></tr>'
        return "\n".join(parts)

    def rows_runs(runs: list[TestRun]) -> str:
        parts: list[str] = []
        for r in runs[:max_run_rows]:
            counts = ""
            if r.total is not None:
                counts = f"P{r.passed or 0} / F{r.failed or 0} / T{r.total}"
            parts.append(
                "<tr>"
                f"<td><code>{html.escape(r.id)}</code></td>"
                f"<td>{html.escape(r.name)}</td>"
                f"<td>{html.escape(r.status)}</td>"
                f"<td>{html.escape(counts or '—')}</td>"
                f"<td class=\"muted\">{_fmt_dt_utc(r.executed_at)}</td>"
                "</tr>"
            )
        if not parts:
            return '<tr><td colspan="5" class="muted">No test runs in this snapshot.</td></tr>'
        return "\n".join(parts)

    bullets_html = "\n".join(f"<li>{html.escape(b)}</li>" for b in bullets)
    sources_html = "\n".join(f"<li>{html.escape(s)}</li>" for s in snapshot.sources)
    notes_html = ""
    if snapshot.notes:
        items = "".join(f"<li class=\"warn\">{html.escape(n)}</li>" for n in snapshot.notes)
        notes_html = f"<section class=\"panel warn-panel\"><h2>Attention</h2><ul>{items}</ul></section>"

    links_html = ""
    if links:
        items = []
        for link in links:
            if not isinstance(link, dict):
                continue
            lab = str(link.get("label", "Link"))
            url = str(link.get("url", "")).strip()
            if not url:
                continue
            items.append(
                f'<li><a href="{html.escape(url, quote=True)}" target="_blank" rel="noopener">{html.escape(lab)}</a></li>'
            )
        if items:
            links_html = (
                f"<section class=\"panel\"><h2>Quick links</h2><ul class=\"links\">{''.join(items)}</ul></section>"
            )

    more_def = len(snapshot.defects) - max_defect_rows
    defect_note = f'<p class="muted small">Showing {min(len(snapshot.defects), max_defect_rows)} of {len(snapshot.defects)}.</p>' if more_def > 0 else ""

    brief_pre = html.escape(full_brief_markdown)

    # Self-contained page; open locally or from artifact hosting.
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{title}</title>
  <style>
    :root {{
      --bg: #0c0e11;
      --panel: #12151c;
      --border: #2a313c;
      --text: #e8eaed;
      --muted: #8b929b;
      --accent: #d4af37;
      --warn-bg: rgba(180, 83, 9, 0.12);
      --warn-border: rgba(212, 175, 55, 0.35);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Segoe UI", system-ui, sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.5;
      padding: 1.5rem clamp(1rem, 4vw, 2.5rem) 3rem;
    }}
    header {{
      max-width: 56rem;
      margin: 0 auto 1.5rem;
      border-bottom: 1px solid var(--border);
      padding-bottom: 1rem;
    }}
    h1 {{
      font-size: clamp(1.35rem, 3vw, 1.75rem);
      font-weight: 700;
      margin: 0 0 0.35rem;
      letter-spacing: -0.02em;
    }}
    .stamp {{ color: var(--muted); font-size: 0.9rem; }}
    main {{ max-width: 56rem; margin: 0 auto; display: flex; flex-direction: column; gap: 1.25rem; }}
    .panel {{
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 1rem 1.15rem;
    }}
    .panel h2 {{
      margin: 0 0 0.65rem;
      font-size: 0.78rem;
      font-weight: 600;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      color: var(--accent);
    }}
    .warn-panel {{ border-color: var(--warn-border); background: var(--warn-bg); }}
    ul {{ margin: 0; padding-left: 1.2rem; }}
    li {{ margin: 0.35rem 0; }}
    li.warn {{ color: #fbbf24; }}
    .focus {{
      font-size: 1.05rem;
      border-left: 3px solid var(--accent);
      padding-left: 0.85rem;
      margin: 0;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 0.82rem;
    }}
    th, td {{ text-align: left; padding: 0.45rem 0.5rem; border-bottom: 1px solid var(--border); vertical-align: top; }}
    th {{ color: var(--muted); font-weight: 600; font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.06em; }}
    code {{ font-size: 0.85em; color: #c5cad3; }}
    .muted {{ color: var(--muted); }}
    .small {{ font-size: 0.8rem; margin: 0.5rem 0 0; }}
    .links {{ list-style: none; padding-left: 0; display: flex; flex-wrap: wrap; gap: 0.5rem 1.25rem; }}
    .links a {{ color: var(--accent); text-decoration: none; font-weight: 600; }}
    .links a:hover {{ text-decoration: underline; }}
    details {{
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 0.75rem 1rem;
    }}
    summary {{ cursor: pointer; font-weight: 600; color: var(--muted); }}
    pre {{
      margin: 0.75rem 0 0;
      overflow: auto;
      font-size: 0.78rem;
      color: var(--muted);
      white-space: pre-wrap;
      word-break: break-word;
    }}
  </style>
</head>
<body>
  <header>
    <h1>{title}</h1>
    <p class="stamp">Snapshot: {html.escape(as_of_utc)}</p>
  </header>
  <main>
    {links_html}
    <section class="panel">
      <h2>At a glance</h2>
      <ul>{bullets_html}</ul>
      <p class="focus"><strong>Suggested focus:</strong> {html.escape(suggested)}</p>
    </section>
    {notes_html}
    <section class="panel">
      <h2>Sources</h2>
      <ul>{sources_html}</ul>
    </section>
    <section class="panel">
      <h2>Defects in snapshot</h2>
      {defect_note}
      <div style="overflow-x:auto">
        <table>
          <thead><tr><th>ID</th><th>Title</th><th>Severity</th><th>Status</th></tr></thead>
          <tbody>{rows_defects(snapshot.defects)}</tbody>
        </table>
      </div>
    </section>
    <section class="panel">
      <h2>Test runs</h2>
      <div style="overflow-x:auto">
        <table>
          <thead><tr><th>ID</th><th>Name</th><th>Status</th><th>Counts</th><th>When</th></tr></thead>
          <tbody>{rows_runs(snapshot.test_runs)}</tbody>
        </table>
      </div>
    </section>
    <details>
      <summary>Full morning brief (markdown)</summary>
      <pre>{brief_pre}</pre>
    </details>
  </main>
</body>
</html>
"""
