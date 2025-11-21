# ESPN4CC4C - Dockerfile for production deployment
# Multi-arch friendly: buildx supports linux/amd64,linux/arm64
FROM python:3.11-slim

# System deps (tzdata for correct time, removed cron since using APScheduler)
RUN apt-get update && apt-get install -y \
    sqlite3 \
    curl \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY bin/ /app/bin/
COPY tools/ /app/tools/
COPY version.py /app/
COPY static/ /app/static/

# Ensure directories exist
RUN mkdir -p /app/data /app/out /app/logs /app/config

# Shell helpers may exist; ignore if none
RUN chmod +x /app/bin/*.sh 2>/dev/null || true

# Reasonable defaults (override via compose/env)
ENV PORT=8094 \
    TZ=America/New_York \
    VALID_HOURS=72 \
    LANES=40 \
    ALIGN=30 \
    MIN_GAP_MINS=30 \
    DB=/app/data/eplus_vc.sqlite3 \
    OUT=/app/out

EXPOSE ${PORT}

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

# Simplified startup (no cron needed, APScheduler handles scheduling):
#   1) run the Python refresher (does migrate/ingest/plan/write)
#   2) launch API server (uvicorn) which starts APScheduler in background
CMD ["/bin/bash","-c","echo '[STARTUP] Running initial refresh...' && /app/bin/refresh_in_container.sh && echo '[STARTUP] Launching API server with background scheduler on port ${PORT}...' && exec python3 -m uvicorn bin.vc_resolver:app --host 0.0.0.0 --port ${PORT}"]
