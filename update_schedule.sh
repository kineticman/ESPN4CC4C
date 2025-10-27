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
