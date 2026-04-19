# syntax=docker/dockerfile:1.7

# ---------- Stage 1: build the frontend (static export) ----------
FROM node:20-slim AS frontend

WORKDIR /app

COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --no-audit --no-fund || npm install --no-audit --no-fund

COPY frontend/ ./
RUN npm run build


# ---------- Stage 2: backend runtime ----------
FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_SYSTEM_PYTHON=1 \
    UV_LINK_MODE=copy \
    PATH="/opt/uv/bin:$PATH"

# System deps: curl for healthcheck + uv installer.
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install uv into a known location.
RUN curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/opt/uv/bin sh

# Non-root user for the final process.
RUN useradd --create-home --uid 1000 app

WORKDIR /app

# Install Python deps first for layer cache. uv.lock may not exist yet.
COPY backend/pyproject.toml ./backend/pyproject.toml
COPY backend/uv.lock* ./backend/
RUN cd backend && \
    if [ -f uv.lock ]; then uv sync --frozen --no-dev; \
    else uv sync --no-dev; fi

# Copy application source.
COPY backend/ ./backend/

# Copy the built frontend static export.
COPY --from=frontend /app/out ./backend/static

# Runtime data directory (volume mount point).
RUN mkdir -p /app/db && chown -R app:app /app

USER app
WORKDIR /app/backend

ENV FINALLY_DB_PATH=/app/db/finally.db

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/api/health || exit 1

CMD ["uv", "run", "--no-dev", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
