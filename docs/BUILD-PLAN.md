# How to build the AI shadow

Concrete plan for building Hyper-Agent: architecture, first slice, and how to grow.

---

## 1. High-level architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  You (Test Manager)                                              │
│  · Run CLI / open chat / receive scheduled report                │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  Hyper-Agent (orchestrator)                                       │
│  · Picks capability (brief / prep / ask / etc.)                   │
│  · Loads config & prompts                                         │
│  · Calls data layer + optional LLM → returns result               │
└────────────────────────────┬────────────────────────────────────┘
                             │
         ┌───────────────────┼───────────────────┐
         ▼                   ▼                   ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│  Data layer     │  │  LLM (optional) │  │  Output         │
│  · Adapters     │  │  · Summarise    │  │  · Markdown     │
│  · Files / APIs │  │  · Draft text   │  │  · Chat reply   │
│  · Cache        │  │  · Answer Q     │  │  · Email / Slack│
└─────────────────┘  └─────────────────┘  └─────────────────┘
```

- **One codebase**, one repo. Multiple entrypoints (e.g. `brief`, `prep`, `ask`) that share the same data layer and prompts.
- **Data layer** = adapters. Each adapter knows how to read from one source (file, Jira, Excel, etc.) and returns a normalised shape. The agent doesn’t care where the data came from.
- **LLM** = optional. Use it for: turning raw data into a brief, drafting escalation text, answering “what’s the status of X?”. You can do a v0 with no LLM (structured summary only) and add the LLM next.
- **Output** = whatever you need: print to console, write markdown to a file, return a string for Slack/email, or stream into a chat UI.

---

## 2. Repo layout (snapshot spine)

**Flow:** `build_snapshot(config)` → **`Snapshot`** (UTC `as_of`, `sources`, `defects`, `test_runs`, `notes`) → `render_brief(snapshot, …)` → markdown + optional **artifact** under `output/briefs/`.

```
Hyper-Agent/
├── config/
│   ├── config.yaml
│   └── prompts/
├── src/
│   ├── main.py              # CLI: brief | prep
│   ├── api.py               # FastAPI: same spine as CLI
│   ├── llm/
│   │   └── client.py        # Optional polish (after deterministic brief)
│   └── shadow/
│       ├── models.py        # Defect, TestRun, Action, Snapshot
│       ├── snapshot.py      # build_snapshot — adapters in, one spine out
│       ├── adapters/        # file_export, azure_devops, …
│       ├── capabilities/    # brief, prep (ask later)
│       └── output/          # formatter, writer (timestamped brief-*.md)
├── data/                    # JSON/CSV exports
├── output/briefs/           # Generated snapshots (gitignored by default)
└── requirements.txt
```

- **Snapshot** = single object every capability reads; provenance lives in `sources` and `as_of`.
- **Adapters** = only populate the snapshot; no capability calls ADO directly.
- **Capabilities** = pure(ish) transforms: `Snapshot` → string (markdown).

---

## 3. Data layer (adapters)

- Define **small, shared models** (e.g. `TestRun`, `Defect`, `Action`, `Commitment`) so every adapter outputs the same shape.
- **File adapter** first: read CSV/JSON from `data/` or a path you pass. No API keys, no network. You export from Jira/Excel and drop the file in.
- **API adapters** later: Jira, Azure DevOps, etc. Each adapter:
  - Takes config (base URL, auth from env).
  - Fetches and maps to the shared models.
  - Handles rate limits and errors.
- **Caching** (optional): store last successful fetch per source with a TTL so repeated runs don’t hammer APIs.

---

## 4. First slice: morning brief

**Goal:** One command → one markdown brief (e.g. in terminal or a file).

**Steps:**

1. **Define the brief format** (e.g. 5 bullets + “Suggested focus today”).
2. **Implement a file adapter** that reads at least one of: test run summary, defects list. Use CSVs or JSON you can export today.
3. **`shadow/capabilities/brief.py`** (reads `Snapshot`):
   - Load data via the data layer (file adapter only for v0).
   - Build a short structured summary (e.g. “N defects open, M critical, last run at X”). No LLM needed for v0.
   - Optionally: send that summary + a prompt to the LLM to get a tighter, natural-language brief.
4. **`main` entrypoint:** `python src/main.py brief` → print markdown and save under `output/briefs/` (configurable).
5. **Config:** path(s) to data files or “data directory”; optional LLM on/off and model name.

**Acceptance:** You run the command, you get a brief you can use. Then refine prompts and add more data sources.

---

## 5. Second slice: meeting prep

**Goal:** Input = meeting title or date; output = talking points + open actions.

**Steps:**

1. **Data:** Either a static list of actions (CSV/JSON) or a calendar adapter (e.g. Google Calendar API) + an “actions” file. Start with file.
2. **`shadow/capabilities/prep.py`:**
   - Load actions and (if available) last meeting notes or commitments.
   - Filter by meeting or “today”.
   - Optionally LLM: “Given these actions and commitments, suggest 3–5 talking points.”
3. **Entrypoint:** `python src/main.py prep --meeting "QA sync"` (or `--date today`).
4. **Output:** Same as brief — markdown to console or file.

---

## 6. LLM usage

- **Where:** Summarisation (brief), drafting (escalation text, steering bullets), Q&A (“status of X?”). Not for “deciding” — only for generating text you then approve.
- **How:** One `llm/client` that accepts a system prompt + user message (or a single prompt). Use config for model name and provider.
- **Prompts:** Store in `config/prompts/` as text or template files. E.g. `brief_system.txt`, `brief_user.txt` with placeholders like `{{defects_summary}}`. Keep them editable without touching code.
- **Safety:** No secrets in prompts; no piping raw PII to the LLM unless your policy allows. Prefer “summary” inputs (e.g. defect counts and titles, not full descriptions) if you’re unsure.

---

## 7. Form factors (how you use it)

| Form | How to add it |
|------|----------------|
| **CLI / on demand** | Already covered: `main.py brief`, `main.py prep`. Run locally or on a server. |
| **Scheduled report** | Cron (Linux/macOS) or Task Scheduler (Windows): run `main.py brief` at 7am, pipe output to a file or a script that sends email/Slack. |
| **Chat** | Add a small server (e.g. FastAPI/Express) that accepts a message, maps it to “ask” or “prep”, runs the capability, returns the reply. Front with Slack/Teams bot or a simple web UI. |
| **Dashboard** | Same server; add a page that calls `brief` (and later more) and renders the markdown. Optional: store last run in a file or DB and show “last updated at”. |

Start with CLI; add scheduling and chat once the brief (and prep) are useful.

---

## 8. Order of work (summary)

1. **Repo + config** — Add `config/`, `src/`, placeholders for `main` and `config.yaml`.
2. **Data models** — Define `Defect`, `TestRun`, `Action` (and maybe `Commitment`) in code.
3. **File adapter** — Read one CSV/JSON of defects or test runs; return list of models.
4. **Brief capability** — No LLM: aggregate data → structured summary → format as markdown. Run from `main.py brief`.
5. **Optional LLM** — Wire in one provider; use it in `brief` to turn structured summary into a short narrative.
6. **Meeting prep** — Actions file + `prep` capability; optional LLM for talking points.
7. **More adapters** — Jira, Excel, etc., as you need them.
8. **Scheduling / chat** — When you’re happy with the output, add cron + email or a small chat server.

This is how I would build the AI shadow: one capability at a time, data layer abstracted, LLM as an optional enhancement, and a single codebase you can grow into the full [capability diagram](DIAGRAM-capabilities.md).
