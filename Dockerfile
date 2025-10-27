FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl cron ca-certificates tzdata sqlite3 \
 && rm -rf /var/lib/apt/lists/*
ENV PYTHONUNBUFFERED=1 UVICORN_TIMEOUT_KEEP_ALIVE=5
WORKDIR /app
COPY requirements.txt /tmp/requirements.txt
RUN if [ ! -s /tmp/requirements.txt ]; then \
      printf "fastapi\nuvicorn[standard]\npython-dotenv\n" > /tmp/requirements.txt; \
    fi && pip install --no-cache-dir -r /tmp/requirements.txt
COPY . .
RUN mkdir -p /app/data /app/out /app/logs
COPY docker-entrypoint.sh /docker-entrypoint.sh
COPY update_schedule.sh /app/update_schedule.sh
RUN chmod +x /docker-entrypoint.sh /app/update_schedule.sh
EXPOSE 8094
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=5 \
  CMD curl -fsS http://localhost:8094/health || exit 1
ENTRYPOINT ["/docker-entrypoint.sh"]
