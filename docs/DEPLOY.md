# Deploying Hyper-Agent API

The API is a small FastAPI app. You can run it locally or deploy to a cloud host so you can call `/brief` from a browser, Slack, or scripts.

---

## Run locally

From repo root:

```bash
pip install -r requirements.txt
uvicorn src.api:app --reload --host 0.0.0.0 --port 8000
```

- **http://localhost:8000** — service info and endpoints  
- **http://localhost:8000/brief** — brief as JSON  
- **http://localhost:8000/brief.md** — brief as plain markdown  
- **http://localhost:8000/health** — health check  
- **http://localhost:8000/docs** — Swagger UI  

---

## Deploy to a host

The app is stateless: it reads `config/` and `data/` from the repo at runtime. On deployment, the **repo root** must be the working directory so `config/config.yaml` and `data/` are found.

### Railway

1. Connect your GitHub repo at [railway.app](https://railway.app).
2. Add a new project from the repo.
3. **Build:** no build command needed if you use a **Nixpacks** or **Dockerfile** (see below). Or set **Build Command** to `pip install -r requirements.txt`.
4. **Start Command:** `uvicorn src.api:app --host 0.0.0.0 --port $PORT`
5. Railway sets `PORT`; use it in the start command.
6. Add **Variables** if needed: `OPENAI_API_KEY` (if LLM enabled).
7. Deploy. Your `data/` and `config/` are in the repo, so they’re deployed too. For live data you’d later replace with API adapters or a mounted volume.

### Render

1. [render.com](https://render.com) → New → Web Service, connect the repo.
2. **Build Command:** `pip install -r requirements.txt`
3. **Start Command:** `uvicorn src.api:app --host 0.0.0.0 --port $PORT`
4. **Environment:** add `OPENAI_API_KEY` if you use the LLM.
5. Deploy. Render runs from repo root by default.

### Azure App Service / other

- **Working directory:** repo root (so `src/`, `config/`, `data/` are present).
- **Install:** `pip install -r requirements.txt`
- **Start:** `uvicorn src.api:app --host 0.0.0.0 --port 8000` (or the port your host uses).
- Set env vars (e.g. `OPENAI_API_KEY`) in the host’s configuration.

### Optional: Dockerfile

If the host expects a Docker image, add a `Dockerfile` at repo root:

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["uvicorn", "src.api:app", "--host", "0.0.0.0", "--port", "8000"]
```

Build and run locally: `docker build -t hyper-agent . && docker run -p 8000:8000 hyper-agent`

---

## After deploy

- Open `https://your-app-url/brief.md` in a browser for the brief.
- Use `https://your-app-url/brief` from Slack (Incoming Webhook or a small script that GETs and posts the `markdown` field).
- Use `/health` for readiness checks.

Keep the repo **private** and use the host’s auth (or add an API key in a middleware) if the endpoint should not be public.
