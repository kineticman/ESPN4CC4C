#!/usr/bin/env bash
# ESPN4CC4C refresh cycle: ingest -> plan -> xmltv -> m3u
# Safe, idempotent, and LAN-aware (avoids 127.0.0.1 in XMLTV URLs).
# Honors .env values. GET-only. No proxies.
set -Eeuo pipefail

export TZ="${TZ:-America/New_York}"

BASE_URL="${VC_RESOLVER_BASE_URL:-http://127.0.0.1:8094}"
DB="${DB:-/app/data/eplus_vc.sqlite3}"
EPG_OUT="${OUT:-/app/out/epg.xml}"
M3U_OUT="${VC_M3U_PATH:-/app/out/virtual_channels.m3u}"

CC_HOST="${CC_HOST:-}"
CC_PORT="${CC_PORT:-5589}"
M3U_GROUP_TITLE="${M3U_GROUP_TITLE:-ESPN+ VC}"
LANES="${LANES:-40}"

LOG_DIR="/app/logs"
mkdir -p "$LOG_DIR"

LOG_MAX_SIZE_MB="${LOG_MAX_SIZE_MB:-5}"
LOG_KEEP="${LOG_KEEP:-7}"
LOG_MAX_BYTES=$(( LOG_MAX_SIZE_MB * 1024 * 1024 ))

log() { printf '[%(%Y-%m-%dT%H:%M:%S%z)T] %s\n' -1 "$*"; }
on_err() { log "ERROR: line $1 exited non-zero"; }
trap 'on_err $LINENO' ERR

rotate_logs() {
  shopt -s nullglob
  for f in "$LOG_DIR"/*.log; do
    [[ -f "$f" ]] || continue
    sz=$(stat -c%s "$f" 2>/dev/null || echo 0)
    if (( sz >= LOG_MAX_BYTES )); then
      for i in $(seq "$LOG_KEEP" -1 2); do
        [[ -f "$f.$((i-1)).gz" ]] && mv -f "$f.$((i-1)).gz" "$f.$i.gz"
      done
      cp -f "$f" "$f.1" && : > "$f"
      gzip -f "$f.1"
    fi
  done
  find "$LOG_DIR" -type f -name '*.gz' -mtime +30 -delete || true
  shopt -u nullglob
}

derive_host_from_base() {
  local base="$1"
  echo "${base#*://}" | cut -d/ -f1 | cut -d: -f1
}

rewrite_static_m3u_for_cc() {
  local file="$1"
  [[ -f "$file" ]] || return 0
  local host="${CC_HOST}"
  if [[ -z "$host" ]]; then
    host="$(derive_host_from_base "$BASE_URL")"
  fi
  sed -Ei "s#chrome://[^:/]+:[0-9]{2,5}/#chrome://${host}:${CC_PORT}/#g" "$file" || true
}

ensure_base_url() {
  if [[ "$BASE_URL" == *"127.0.0.1"* || "$BASE_URL" == *"localhost"* ]]; then
    local scheme="http" port="8094"
    [[ "$BASE_URL" == http://*  ]] && scheme="http"
    [[ "$BASE_URL" == https://* ]] && scheme="https"
    local tail="${BASE_URL##*:}"
    if [[ "$tail" =~ ^[0-9]{2,5}$ ]]; then port="$tail"; fi
    if [[ -n "$CC_HOST" ]]; then
      BASE_URL="${scheme}://${CC_HOST}:${port}"
      log "Adjusted BASE_URL to ${BASE_URL}"
    else
      log "WARNING: BASE_URL is ${BASE_URL}. Set VC_RESOLVER_BASE_URL in .env to your LAN IP."
    fi
  fi
}

sleep $(( RANDOM % 121 ))
ensure_base_url

for i in {1..20}; do
  if curl -sf "$BASE_URL/health" >/dev/null; then
    break
  fi
  log "waiting /health ($i/20)…"
  sleep 3
done

rotate_logs

# DB migrations (non-destructive)
if [[ -f "/app/tools/db_migrate.py" ]]; then
  log "DB migrate…"
  python3 /app/tools/db_migrate.py \
    --db "$DB" \
    --lanes "$LANES" \
    --seed-channels-if-empty \
    --drop-unique-plan-run \
    >> "$LOG_DIR/plan.log" 2>&1 || log "DB migrate failed (continuing)"
fi

# pipeline
if [[ -f "/app/bin/ingest_watch_graph_all_to_db.py" ]]; then
  log "Ingest…"
  python3 /app/bin/ingest_watch_graph_all_to_db.py \
    --db "$DB" --days 3 --tz "$TZ" \
    >> "$LOG_DIR/ingest.log" 2>&1 || log "Ingest failed"
fi

if [[ -f "/app/bin/build_plan.py" ]]; then
  log "Plan…"
  python3 /app/bin/build_plan.py \
    --db "$DB" --tz "$TZ" \
    >> "$LOG_DIR/plan.log" 2>&1 || log "Plan failed"
fi

if [[ -f "/app/bin/xmltv_from_plan.py" ]]; then
  log "XMLTV…"
  mkdir -p "$(dirname "$EPG_OUT")"
  VC_RESOLVER_ORIGIN="$BASE_URL" python3 /app/bin/xmltv_from_plan.py \
    --db "$DB" --out "$EPG_OUT" \
    >> "$LOG_DIR/xmltv.log" 2>&1 || log "XMLTV failed"
  if grep -q "127\.0\.0\.1" "$EPG_OUT" 2>/dev/null; then
    log "WARNING: epg.xml still contains 127.0.0.1 URLs (check VC_RESOLVER_BASE_URL)"
  fi
fi

if [[ -f "/app/bin/m3u_from_plan.py" ]]; then
  log "M3U…"
  mkdir -p "$(dirname "$M3U_OUT")"
  python3 /app/bin/m3u_from_plan.py \
    --db "$DB" --out "$M3U_OUT" \
    >> "$LOG_DIR/m3u.log" 2>&1 || log "M3U failed"
  rewrite_static_m3u_for_cc "$M3U_OUT"
fi

log "Update cycle complete."
