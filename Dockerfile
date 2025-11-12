# ESPN4CC4C - Dockerfile for production deployment
# Multi-arch friendly: buildx supports linux/amd64,linux/arm64

FROM python:3.11-slim

# System deps (now includes cron & tzdata for built-in schedules and correct time)
RUN apt-get update && apt-get install -y \
    sqlite3 \
    curl \
    cron \
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

# Start sequence:
#   1) install cron schedules & start cron (non-fatal if unavailable)
#   2) run the Python refresher (does migrate/ingest/plan/write)
#   3) launch API server (uvicorn)
CMD ["/bin/bash","-c","/app/bin/cron_boot.sh || true; /app/bin/refresh_in_container.sh && exec python3 -m uvicorn bin.vc_resolver:app --host 0.0.0.0 --port ${PORT}"]
