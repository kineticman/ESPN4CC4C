# ESPN4CC4C - Dockerfile for production deployment
# Supports both amd64 and arm64 architectures

FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    sqlite3 \
    curl \
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

# Create necessary directories
RUN mkdir -p /app/data /app/out /app/logs /app/config

# Set execute permissions on shell scripts
RUN chmod +x /app/bin/*.sh 2>/dev/null || true

# Environment defaults (can be overridden)
ENV PORT=8094 \
    TZ=America/New_York \
    VALID_HOURS=72 \
    LANES=40 \
    ALIGN=30 \
    MIN_GAP_MINS=30 \
    DB=/app/data/eplus_vc.sqlite3 \
    OUT=/app/out

# Expose the API port
EXPOSE ${PORT}

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

# Startup script that initializes/refreshes data then starts API
CMD ["/bin/bash", "-c", "/app/bin/cron_boot.sh || true; /app/bin/refresh_in_container.sh && exec python3 -m uvicorn bin.vc_resolver:app --host 0.0.0.0 --port ${PORT}"]
