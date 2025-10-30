# syntax=docker/dockerfile:1
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    UVICORN_TIMEOUT_KEEP_ALIVE=5 \
    ENABLE_CRON=1

# OS deps: cron (scheduling), procps (pgrep/ps), curl (health), tzdata, sqlite3, ca-certs
RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      cron procps curl tzdata sqlite3 ca-certificates && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python deps (fallback minimal set if requirements.txt is empty)
COPY requirements.txt /tmp/requirements.txt
RUN if [ ! -s /tmp/requirements.txt ]; then \
      printf "fastapi\nuvicorn[standard]\npython-dotenv\n" > /tmp/requirements.txt; \
    fi && pip install --no-cache-dir -r /tmp/requirements.txt

# Project files
COPY . .

# Ensure runtime dirs
RUN mkdir -p /app/data /app/out /app/logs

# Ship cron job (daily 02:00 refresh + weekly VACUUM)
# expects contrib/cron/espn4cc in repo
RUN cp /app/contrib/cron/espn4cc /etc/cron.d/espn4cc && \
    chmod 0644 /etc/cron.d/espn4cc && \
    crontab /etc/cron.d/espn4cc

# Make scripts executable (best-effort)
RUN chmod +x /app/bin/refresh_in_container.sh 2>/dev/null || true && \
    chmod +x /app/update_schedule.sh 2>/dev/null || true

# Place entrypoint where ENTRYPOINT expects it
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

EXPOSE 8094
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=5 \
  CMD curl -fsS http://localhost:8094/health || exit 1

ENTRYPOINT ["/docker-entrypoint.sh"]
