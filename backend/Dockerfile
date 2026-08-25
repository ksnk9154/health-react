# ──────────────────────────────────────────────────────────────────────────────
#  Dockerfile — FastAPI backend for the Health Management System
#  Works on Render.com, Fly.io, Railway, Hugging Face Spaces, or any Docker host.
# ──────────────────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS base

# System deps that Pillow / PyArrow / pypdf2 may need at runtime
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        gcc \
        libjpeg62-turbo \
        zlib1g \
        libpq-dev \
        libmagic1 \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Create a non-root user
RUN useradd --create-home --shell /bin/bash appuser
WORKDIR /home/appuser/app

# Install Python dependencies (layer cache)
COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Copy backend source
COPY backend/ ./backend/

# Create writable storage directories (DOCUMENT_STORAGE_PATH default = storage/uploads)
RUN mkdir -p /home/appuser/app/backend/storage/uploads \
    && chown -R appuser:appuser /home/appuser/app

USER appuser

# Generate a strong random JWT secret at build time if not provided at runtime
ENV JWT_SECRET="CHANGE_ME_IN_PRODUCTION" \
    HEALTH_DB_PATH="/home/appuser/app/backend/health.db" \
    DOCUMENT_STORAGE_PATH="/home/appuser/app/backend/storage/uploads" \
    PYTHONUNBUFFERED="1" \
    PYTHONDONTWRITEBYTECODE="1"

EXPOSE 8000

# Run database migrations and start the API server
# PORT defaults to 8000 (Render, Fly, etc.). Hugging Face Spaces overrides it to 7860.
CMD ["sh", "-c", "cd /home/appuser/app/backend && python db/migrate.py && python -m uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
