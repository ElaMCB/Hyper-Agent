# Gmail (personal, read-only)

Shadow can pull **recent Gmail metadata** (subject, from, snippet, unread flag) into the same snapshot as defects and test runs. Scope is **read-only** (`gmail.readonly`).

## Keep private data off GitHub

1. **Never commit** OAuth client JSON, refresh tokens, `.env`, or `output/` briefs/HTML that contain your mail.
2. Repo `.gitignore` already ignores `secrets/*` (except `secrets/.gitkeep`), `.env`, and `output/briefs/` / `output/headquarters/`.
3. Keep **`gmail.enabled: false`** in the copy of `config/config.yaml` you push to GitHub. For your machine only, enable Gmail in a **local** config workflow:
   - Either edit `config/config.yaml` locally and **do not commit** those lines, or
   - Maintain an untracked override (advanced): copy `config.yaml` to something gitignored and point your runs at it (not built into the CLI today—simplest is local-only edits you revert before push, or use a private fork).

## Google Cloud setup (one time)

1. Open [Google Cloud Console](https://console.cloud.google.com/), create or pick a project.
2. **APIs & Services → Enable APIs** → enable **Gmail API**.
3. **APIs & Services → Credentials → Create credentials → OAuth client ID**.
4. Application type: **Desktop app**. Download the JSON.
5. Save it **only on your PC** as e.g. `secrets/gmail_oauth_client.json` inside this repo (that path is gitignored except `.gitkeep`).

## Hyper-Agent config

In `config/config.yaml` (local):

```yaml
gmail:
  enabled: true
  credentials_file: secrets/gmail_oauth_client.json
  token_file: secrets/gmail_token.json
  query: "is:unread newer_than:7d"   # optional; "" = recent messages
  max_messages: 25

data:
  load_defects: false
  load_test_runs: false

brief:
  title: "# Personal brief"
  max_bullets: 7

headquarters:
  title: "Shadow — Personal HQ"
```

Optional environment overrides (no secrets in YAML):

- `GMAIL_OAUTH_CLIENT_JSON` — absolute or repo-relative path to the Desktop OAuth client JSON.
- `GMAIL_TOKEN_JSON` — where to store the refresh token (default `secrets/gmail_token.json`).

## First run

```bash
pip install -r requirements.txt
python src/main.py brief
```

A browser opens for Google sign-in. After consent, a **token file** is written under `secrets/` (gitignored). Later runs reuse it until you revoke access.

## LLM warning

If `llm.enabled` is true, **subjects and snippets** from the deterministic summary may be sent to your LLM provider. For strict privacy, keep the LLM off for Gmail-backed briefs.

## CI / public deploy

Do **not** put Gmail OAuth files or tokens in GitHub Actions or public hosts. Use Gmail only on **your machine** or a **private** environment with secrets injected by your host’s secret store.
