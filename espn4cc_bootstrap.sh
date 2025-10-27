#!/usr/bin/env bash
# file: espn4cc_bootstrap.sh
set -euo pipefail

APP_NAME="espn4cc"
PORT="${PORT:-8094}"
TZ_DEFAULT="America/New_York"
ROOT="$(pwd)"
DATA_DIR="$ROOT/data"; OUT_DIR="$ROOT/out"; LOG_DIR="$ROOT/logs"; ENV_FILE="$ROOT/.env"

msg(){ printf "\e[1;32m[espn4cc]\e[0m %s\n" "$*"; }
err(){ printf "\e[1;31m[err]\e[0m %s\n" "$*\n" >&2; exit 1; }

# Basic sanity
command -v docker >/dev/null || err "docker not installed or not on PATH"
if docker compose version >/dev/null 2>&1; then COMPOSE="docker compose";
elif command -v docker-compose >/dev/null 2>&1; then COMPOSE="docker-compose";
else err "Neither 'docker compose' nor 'docker-compose' found"; fi

# Detect LAN IP once; allow override
if [[ -z "${LAN_IP:-}" ]]; then
  LAN_IP="$(ip route get 1.1.1.1 2>/dev/null | awk '/ src /{print $7; exit}')"
  [[ -z "$LAN_IP" ]] && LAN_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
fi
[[ -z "${LAN_IP:-}" ]] && err "Could not determine LAN IP; set LAN_IP=…"

msg "LAN IP: $LAN_IP"
mkdir -p "$DATA_DIR" "$OUT_DIR" "$LOG_DIR"

# Write .env
cat > "$ENV_FILE" <<ENV
VC_RESOLVER_BASE_URL=http://$LAN_IP:$PORT
TZ=${TZ:-$TZ_DEFAULT}
DB=/app/data/eplus_vc.sqlite3
OUT=/app/out/epg.xml
VC_M3U_PATH=/app/out/virtual_channels.m3u
VALID_HOURS=72
LANES=40
ALIGN=30
MIN_GAP_MINS=30
SCHEDULE_HOURS=6
PORT=$PORT
ENV
msg "Wrote .env"

# docker-compose.yml
cat > docker-compose.yml <<'YML'
services:
  espn4cc:
    build: .
    container_name: espn4cc
    init: true
    stop_grace_period: 15s
    ports:
      - "${PORT:-8094}:8094"
    env_file:
      - .env
    environment:
      - TZ=${TZ:-America/New_York}
    volumes:
      - ./data:/app/data
      - ./out:/app/out
      - ./logs:/app/logs
      - ./.env:/app/.env:ro
      - /etc/localtime:/etc/localtime:ro
    restart: unless-stopped
YML
msg "Wrote docker-compose.yml"

# Dockerfile
cat > Dockerfile <<'DOCKER'
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
DOCKER
msg "Wrote Dockerfile"

# docker-entrypoint.sh
cat > docker-entrypoint.sh <<'ENTRY'
#!/usr/bin/env bash
set -euo pipefail
[ -f "/app/.env" ] && set -a && . /app/.env && set +a
: "${PORT:=8094}"; : "${TZ:=America/New_York}"
ln -sf "/usr/share/zoneinfo/$TZ" /etc/localtime || true; echo "$TZ" > /etc/timezone || true
mkdir -p /app/data /app/out /app/logs
SCHEDULE_HOURS="${SCHEDULE_HOURS:-6}"
echo "0 */${SCHEDULE_HOURS} * * * /app/update_schedule.sh >> /app/logs/schedule.log 2>&1" > /var/spool/cron/crontabs/root
echo "17 3 * * 0 sqlite3 /app/data/eplus_vc.sqlite3 'VACUUM;'" >> /var/spool/cron/crontabs/root
cron
exec python3 -m uvicorn bin.vc_resolver:app --host 0.0.0.0 --port "$PORT"
ENTRY
chmod +x docker-entrypoint.sh
msg "Wrote docker-entrypoint.sh"

# update_schedule.sh
cat > update_schedule.sh <<'UPD'
#!/usr/bin/env bash
set -euo pipefail
BASE_URL="${VC_RESOLVER_BASE_URL:-http://127.0.0.1:8094}"
LOG_DIR="/app/logs"; mkdir -p "$LOG_DIR"
log(){ echo "[$(date +'%Y-%m-%dT%H:%M:%S%z')] $*"; }
sleep $((RANDOM % 121))
for i in $(seq 1 20); do curl -sf "$BASE_URL/health" >/dev/null && break; log "waiting /health ($i/20)…"; sleep 3; done
for f in "$LOG_DIR"/*.log; do [ -f "$f" ] || continue; [ "$(stat -c%s "$f")" -gt 1048576 ] && mv "$f" "$f.$(date +%Y%m%d-%H%M%S)" || true; done
find "$LOG_DIR" -name "*.log.*" -type f -mtime +14 -delete || true
if [ -f "/app/bin/ingest_watch_graph_all_to_db.py" ]; then
  log "Ingest…"; python3 /app/bin/ingest_watch_graph_all_to_db.py --db /app/data/eplus_vc.sqlite3 --days 3 --tz America/New_York --verbose >> "$LOG_DIR/ingest.log" 2>&1 || log "Ingest failed"
fi
if [ -f "/app/bin/build_plan.py" ]; then
  log "Plan…"; python3 /app/bin/build_plan.py --db /app/data/eplus_vc.sqlite3 --tz America/New_York >> "$LOG_DIR/plan.log" 2>&1 || log "Plan failed"
fi
if [ -f "/app/bin/xmltv_from_plan.py" ]; then
  log "XMLTV…"; python3 /app/bin/xmltv_from_plan.py --db /app/data/eplus_vc.sqlite3 --out /app/out/epg.xml >> "$LOG_DIR/xmltv.log" 2>&1 || log "XMLTV failed"
fi
if [ -f "/app/bin/m3u_from_plan.py" ]; then
  log "M3U…"; python3 /app/bin/m3u_from_plan.py --db /app/data/eplus_vc.sqlite3 --out /app/out/virtual_channels.m3u >> "$LOG_DIR/m3u.log" 2>&1 || log "M3U failed"
fi
log "Update cycle complete."
UPD
chmod +x update_schedule.sh
msg "Wrote update_schedule.sh"

# quick verify helper
cat > espn4cc_verify.sh <<'VER'
#!/usr/bin/env bash
set -euo pipefail
HOST="${1:-192.168.86.72}"; PORT="${2:-8094}"; BASE="http://$HOST:$PORT"
echo "== readiness =="; i=0; until curl -sf "$BASE/health" >/dev/null || [ $i -ge 30 ]; do i=$((i+1)); echo "  waiting ($i/30)"; sleep 1; done
curl -s "$BASE/health" && echo
echo "== m3u (first 12) =="; curl -s "$BASE/playlist.m3u" | sed -n '1,12p'
curl -s "$BASE/playlist.m3u" | grep -Ei 'localhost|127\.0\.0\.1' >/dev/null && echo "✖ localhost found in M3U" || echo "✔ no localhost in M3U"
echo "== xmltv head =="; curl -s "$BASE/epg.xml" | sed -n '1,6p'
echo "== channel probe =="; curl -s -o /dev/null -w "HTTP %{http_code}\n" "$BASE/vc/eplus9?only_live=1"
echo "== cron =="; if docker compose ps espn4cc >/dev/null 2>&1; then docker compose exec espn4cc sh -lc 'crontab -l || true'; fi
VER
chmod +x espn4cc_verify.sh
msg "Wrote espn4cc_verify.sh"

# Build + up
msg "Building image…"; $COMPOSE build
msg "Starting container…"; $COMPOSE up -d

# Verify
HOST="${LAN_IP}"; msg "Verifying on $HOST:$PORT …"
bash ./espn4cc_verify.sh "$HOST" "$PORT"
msg "Done."
