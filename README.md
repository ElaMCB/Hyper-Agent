<div align="center">

<a href="https://ElaMCB.github.io/Hyper-Agent/">
  <img src="docs/shadow-wordmark.svg" alt="Shadow — AI test architect" width="520">
</a>

*Your AI test architect*

**AI brain · Second brain · Clarity layer**

</div>

---

## The idea

Test leadership is **decision-making under load**: Azure DevOps, Outlook, chat, decks, and memory all compete for the same mental bandwidth. Tools record work; they rarely **synthesize** it for *you* in the moment you need to lead.

**Shadow** is an **intelligence layer** on top of that stack—not a replacement for ADO or your rituals, but a system that:

1. **Ingests** what already exists (work items, runs, exports; calendar and mail when you wire them).
2. **Compresses** it into **briefs, prep, and stakeholder-ready framing** with clear provenance—so you know what it saw and when.
3. **Returns time** for what only you can do: coaching QA, aligning with delivery, owning risk, and signing your name to outcomes.

**Hyper-Agent** is the project that builds **Shadow**. Shadow is the name of the agent you run, deploy, and eventually talk to every day.

### What makes it powerful

| Lever | Why it matters |
|--------|----------------|
| **Rhythm** | A repeatable morning brief (and later, pre-meeting prep) builds *situational awareness* without relying on willpower. |
| **Evidence** | Escalations, steering bullets, and readiness views start from **structured facts**, not what you remembered in the car. |
| **Composable** | Same codebase: files today, **live ADO bugs** now, Outlook/Graph and test runs next—each integration makes the next cheaper. |
| **Human-in-the-loop** | Shadow **frames** and **suggests**; you **edit and decide**. No black-box “the AI said ship it.” |

> Shadow shadows *you*: QA team oversight, delivery collaboration, daily orchestration. It keeps the picture sharp and the paperwork light so your judgment lands with weight.

---

## Vision & capability system

How Shadow maps to a Test Manager’s world:

**[→ Vision (full narrative)](docs/VISION-ai-test-architect.md)** — daily orchestration, QA oversight, delivery, decision support, governance, second brain.

### Capability diagram

```mermaid
flowchart TB
    CORE["Shadow<br/>AI brain · Second brain · Clarity layer"]
    CORE --- A1
    CORE --- A2
    CORE --- A3
    CORE --- A4
    CORE --- A5
    CORE --- A6
    A1["1. Daily orchestration & focus"]
    A2["2. QA team oversight"]
    A3["3. Delivery collaboration"]
    A4["4. Decision support"]
    A5["5. Governance & consistency"]
    A6["6. Second brain"]
```

| Area | Sub-capabilities |
|------|------------------|
| **1. Daily orchestration** | Morning brief · Priority stack · Meeting prep |
| **2. QA team oversight** | Commitment vs actuals · Single view · Escalation support · Consistency |
| **3. Delivery collaboration** | Scope ↔ test alignment · Release readiness · Communication |
| **4. Decision support** | Go/no-go evidence · Prioritization · Impact of changes |
| **5. Governance** | Standards · Patterns |
| **6. Second brain** | Status on demand · Your preferences |

*More diagrams:* [docs/DIAGRAM-capabilities.md](docs/DIAGRAM-capabilities.md)

---

## Build & evolve Shadow

**[→ Recommended next steps](docs/NEXT-STEPS.md)** — first slice, data sources, form factor, tech baseline.

**[→ How to build (architecture)](docs/BUILD-PLAN.md)** — adapters, capabilities, CLI/API.

---

## Run

From the repo root:

**CLI (morning brief):**
```bash
pip install -r requirements.txt
python src/main.py brief
```
Builds a **Snapshot** (UTC time + sources + defects + test runs), renders the brief, and by default **saves** `output/briefs/brief-YYYY-MM-DDTHHMMSSZ.md` for an audit trail. Toggle in `config/config.yaml` under `output`.

**CLI (QE subagents — people, allocation, strategy from `data/*.json`):**
```bash
python src/main.py people      # people & capacity markdown (set qe_subagents.save_on_cli: true to write output/qe/*.md)
python src/main.py allocation  # sprint / app allocation
python src/main.py strategy    # portfolio strategy signals
python src/main.py qe          # all three in one document
```
Enable `data.load_team`, `load_allocations`, and/or `load_strategy` in `config/config.yaml`. Samples: `data/team.json`, `data/allocations.json`, `data/strategy.json`. Optional: `brief.include_qe_context: true` folds compact QE lines into the morning brief.

**CLI (daily Headquarters page):**
```bash
python src/main.py headquarters
```
Same snapshot and brief as above, plus a **single HTML dashboard** at `output/headquarters/latest.html` (overwritten each run) and the **same brief text** at `output/headquarters/latest.md`. Each run also adds a timestamped `headquarters-…Z.html` archive; **`headquarters.retention.max_archived_html`** (default 30 in sample config) drops older archives so the folder stays bounded—set to **0** to keep everything. Timestamped markdown briefs still land under `output/briefs/`. At-a-glance bullets, tables, sources, optional **quick links** in `headquarters.links`, collapsible full brief. Schedule nightly (Task Scheduler, `cron`, or **Nightly Headquarters** in `.github/workflows/`). CI uploads `output/headquarters/` as an artifact (secret **`AZDO_PAT`** if you use ADO).

**API (deploy or run locally):**
```bash
uvicorn src.api:app --reload --host 0.0.0.0 --port 8000
```
Then open **http://localhost:8000/brief.md** for the brief, **http://localhost:8000/headquarters.html** for the dashboard, **http://localhost:8000/qe.md** for the combined QE subagent pack, **http://localhost:8000/docs** for the API docs.

| Endpoint | Description |
|----------|-------------|
| `GET /` | Service info |
| `GET /brief` | Brief as JSON |
| `GET /brief.md` | Brief as markdown |
| `GET /qe.md` | QE subagent pack (people + allocation + strategy) as markdown |
| `GET /headquarters.html` | Headquarters dashboard (HTML); `?persist=1` writes `output/headquarters/` (`latest.html`, `latest.md`, archives, prune) if the server can write the repo |
| `GET /health` | Health check |

**Deploy:** [docs/DEPLOY.md](docs/DEPLOY.md) — Railway, Render, Azure, or Docker.

**Data:** `defects.json` and `test_runs.json` in `data/` (samples included). Optional: `llm.enabled` + `OPENAI_API_KEY` in `.env` for LLM-polished briefs.

**Gmail (personal, read-only):** [docs/INTEGRATION-GMAIL.md](docs/INTEGRATION-GMAIL.md) — OAuth in `secrets/` (gitignored); use `data.load_defects` / `load_test_runs: false` for inbox-only briefs. Do not commit tokens or push a config with `gmail.enabled: true` if the repo is public.

**Azure DevOps & Outlook:** [docs/INTEGRATION-ADO-OUTLOOK.md](docs/INTEGRATION-ADO-OUTLOOK.md) — live Bugs in the brief; Outlook via Graph or Power Automate.

---

## Roadmap

| Horizon | Focus |
|---------|--------|
| **Now** | **Snapshot spine** (UTC + sources + provenance) · morning brief · REST API · **Azure DevOps** bugs · timestamped `output/briefs/` |
| **Next** | Meeting prep · **Outlook** (calendar) via Graph or Power Automate · ADO test results |
| **Stretch** | Risk/readiness packs · steering narratives · authenticated endpoints · deeper “ask Shadow” over your data |

This repo is the living implementation of that roadmap—fork, extend, and tune it to how *you* run quality.

---

<div align="center">

[![Visits](https://visitor-badge.laobi.icu/badge?page_id=ElaMCB.Hyper-Agent&left_text=Visits&left_color=0c0e11&right_color=d4af37)](https://github.com/ElaMCB/Hyper-Agent/graphs/traffic)

*Counter updates when this README is loaded (approximate; includes bots). Repo owners: [Traffic](https://github.com/ElaMCB/Hyper-Agent/graphs/traffic).*

</div>
