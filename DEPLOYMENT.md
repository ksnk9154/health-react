# Deployment Guide — Health Management System

Fully-free deployment: **GitHub Pages** (frontend) + **Render.com** or **Hugging Face Spaces** (backend).

## Quick Summary

This project is a full-stack health management system:
- **Backend** — FastAPI (Python 3.12) → Render.com or Hugging Face Spaces (FREE)
- **Frontend** — React / Vite (SPA) → GitHub Pages (FREE, no credit card)

After deployment:
- Frontend: `https://<github-username>.github.io/health-react/`
- Backend API: `https://health-api.onrender.com` (or your HF Spaces URL)
- Admin login: username = `admin`, password = `admin123` (auto-created on startup)

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Option A — One-Touch Render Deploy (Recommended)](#2-option-a--one-touch-render-deploy-recommended)
3. [Option B — Hugging Face Spaces (No Credit Card)](#3-option-b--hugging-face-spaces-no-credit-card)
4. [Frontend → GitHub Pages](#4-frontend--github-pages)
5. [Combined Frontend + Backend Docker (single container)](#5-combined-frontend--backend-docker-single-container)
6. [Local Production Testing (docker-compose)](#6-local-production-testing-docker-compose)
7. [Post-Deploy Checklist](#7-post-deploy-checklist)
8. [Environment Variables Reference](#8-environment-variables-reference)
9. [Troubleshooting](#9-troubleshooting)

---

## 1. Prerequisites

- **GitHub account** (free)
- **Render.com account** (free tier available; check render.com/pricing)
  — *or* — **Hugging Face account** (free, no credit card required)

### 1.1 Generate a JWT Secret

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Copy the output — you'll need it for Step 3.

---

## 2. Option A — One-Touch Render Deploy (Recommended)

The fastest path. A single `render.yaml` at the repo root tells Render exactly how to build and run both the database and the web service.

### Step 1 — Click the Deploy Button

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/kenai-project/health-react)

Or manually:
1. Go to https://dashboard.render.com → New → Web Service
2. Connect your GitHub repo: `kenai-project/health-react`
3. Select the "Deploy from render.yaml" option.

### Step 2 — Add Environment Variables

After the service is created, go to the Render Dashboard → your service → Environment:

| Key | Value |
|-----|-------|
| `JWT_SECRET` | `<the-secret-you-generated-above>` |
| `DATABASE_URL` | *(leave empty → SQLite fallback)* |

Render will automatically:
- Provision a free 256 MB PostgreSQL database (from `render.yaml` → `databases`)
- Build the Docker image from `backend/Dockerfile`
- Run `python db/migrate.py` then `uvicorn api.main:app`
- Expose HTTPS automatically

Your backend will be live at `https://health-api.onrender.com`.

---

## 3. Option B — Hugging Face Spaces (No Credit Card)

Hugging Face Spaces gives you 30 GB storage and a 2 vCPU / 8 GB RAM container — completely free, no credit card required.

### Step 1 — Create a Space

1. Go to https://huggingface.co/spaces/new
2. Choose:
   - **SDK**: Docker
   - **Visibility**: Public (free tier)
   - **Hardware**: Basic (CPU, free)
3. Name it, e.g. `health-react-backend`

### Step 2 — Set Environment Variables

In the Space Settings → Environment Variables:

| Key | Value |
|-----|-------|
| `PORT` | `7860` |
| `JWT_SECRET` | `<32-byte-random-secret>` |
| `HEALTH_DB_PATH` | `/data/health.db` |
| `DOCUMENT_STORAGE_PATH` | `/data/storage/uploads` |

### Step 3 — Push Your Code

```bash
git clone https://github.com/kenai-project/health-react
cd health-react
git remote add hf https://huggingface.co/spaces/YOUR-USERNAME/health-react-backend
git push hf main
```

Your backend will be live at: `https://YOUR-USERNAME-health-react-backend.hf.space`

> **Note**: The free HF Spaces filesystem is ephemeral — your SQLite DB resets on restart. Enable "PostgreSQL" add-on in Space settings for persistence.

---

## 4. Frontend → GitHub Pages

GitHub Pages is already partially configured in `package.json` (homepage URL + `gh-pages` deploy script). A GitHub Actions workflow (`.github/workflows/deploy-frontend.yml`) builds and deploys automatically on every push to `main`.

### Step 1 — Set the API URL Secret

GitHub repo → Settings → Secrets and variables → Actions → New repository secret:

| Name | Value |
|------|-------|
| `VITE_API_URL` | `https://health-api.onrender.com` *(your backend URL)* |

> This tells the React app where to find the backend API. The path is set at **build time**, so you must re-deploy the frontend after changing this secret.

### Step 2 — Enable GitHub Pages

1. Settings → Pages → Build and deployment → Source: **"Deploy from a workflow"**
2. Select the `deploy-frontend.yml` workflow.

### Step 3 — Deploy

```bash
git add .
git commit -m "configure deployment"
git push origin main
```

GitHub Actions will:
1. Build the frontend with `pnpm build`
2. Upload `frontend/dist/` as a Pages artifact
3. Publish to `https://kenai-project.github.io/health-react/`

---

## 5. Combined Frontend + Backend Docker (single container)

If you prefer to deploy everything as **one container** (useful when you have only one free hosting slot), use `backend/Dockerfile.multicloud`.

This Dockerfile:
- Builds the React frontend in a Node stage
- Copies it into `backend/static/`
- The FastAPI app (`main.py`) mounts `/static` as a `StaticFiles` route
- One container serves both the SPA and the API — zero CORS issues.

```bash
# Build and run locally
docker build -f backend/Dockerfile.multicloud -t health-react-all .
docker run -p 8000:8000 \
  -e JWT_SECRET=$(python -c "import secrets; print(secrets.token_urlsafe(32))") \
  health-react-all
```

Visit `http://localhost:8000` — both the frontend and API (at `/docs`) are served from the same origin.

**Deploy**: Use this Dockerfile on Render.com (select "Docker" → use `Dockerfile.multicloud`), Fly.io, Koyeb, or Hugging Face Spaces.

---

## 6. Local Production Testing (docker-compose)

```bash
docker compose up --build -d
```

| Service | URL |
|---------|-----|
| Frontend | http://localhost:5173 |
| Backend API | http://localhost:8000 |
| API docs | http://localhost:8000/docs |

To stop:
```bash
docker compose down -v    # -v also removes the database volume
```

---

## 7. Post-Deploy Checklist

- [ ] Backend `/docs` loads: `https://<backend-url>/docs`
- [ ] Login works: `admin` / `admin123`
- [ ] Frontend loads and can authenticate against the backend
- [ ] Health records CRUD works
- [ ] Document upload works (test with a small PDF or text file)
- [ ] LLM assistant shows "unavailable" — **expected** on free hosts (Ollama cannot run there)
- [ ] HTTPS is active (Render / Fly / GH-Pages provide this automatically)
---

## 8. Environment Variables Reference

### Backend (set on the hosting platform)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `JWT_SECRET` | **Yes** | — | ≥32-byte random string. Generate with `python -c "import secrets; print(secrets.token_urlsafe(32))"` |
| `DATABASE_URL` | No | — | PostgreSQL connection string. Leave empty for SQLite. |
| `HEALTH_DB_PATH` | No | `health.db` | SQLite file path (used when `DATABASE_URL` is empty). |
| `DOCUMENT_STORAGE_PATH` | No | `storage/uploads` | Directory for uploaded files. |
| `OLLAMA_URL` | No | `http://localhost:11434` | Ollama LLM API (not available on free hosts). |
| `DEFAULT_LLM_MODEL` | No | `llama3.1:8b` | Default LLM model. |
| `OLLAMA_TIMEOUT` | No | `60` | LLM request timeout (seconds). |
| `RATE_LIMIT_ENABLED` | No | `true` | Enable/disable rate limiting. |
| `MAX_UPLOAD_SIZE_MB` | No | `20` | Max upload size in MB. |
| `PORT` | No | `8000` | Server port (HF Spaces overrides to `7860`). |

### Frontend (set at build time)

| Variable | Description |
|----------|-------------|
| `VITE_API_URL` | Backend API URL. e.g. `https://health-api.onrender.com` |

### Frontend GitHub Secret

Set in GitHub repo → Settings → Secrets → `VITE_API_URL`.

---

## 9. Troubleshooting

| Problem | Fix |
|---------|-----|
| "JWT_SECRET is not set" at startup | Set `JWT_SECRET` env var on your host to a 32+ byte random string. |
| Frontend "Invalid response" from API | Ensure `VITE_API_URL` points to the **backend** URL, not the frontend. Re-deploy frontend after changing the secret. |
| Admin login fails | DB may have reset. Bootstrap creates admin on each startup — redeploy the backend. |
| LLM returns 503 "service unavailable" | Expected on free hosts (Ollama can't run there). Run Ollama locally for full features. |
| Document upload fails | Ensure `DOCUMENT_STORAGE_PATH` is writable (use `/data` in Docker). |
| CORS errors | Backend currently allows `*` origins. To restrict, edit `CORSMiddleware` in `backend/api/main.py`. |

---

## Architecture Notes

**Backend**: FastAPI + uvicorn + SQLAlchemy + SQLite (fallback) / PostgreSQL (production) + Ollama LLM (optional) + Streamlit dashboard (optional, separate process).

**Frontend**: React 18 + Vite + React Router 7 + Tailwind CSS + Capacitor (mobile).

---

_— Happy deploying! 🚀_


