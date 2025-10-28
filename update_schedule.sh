#!/usr/bin/env bash
set -euo pipefail
# ESPN4CC4C refresh cycle: ingest -> plan -> xmltv -> m3u
# - honors .env values
# - rotates /app/logs/*.log (size-based, gzipped)
# - optional rewrite of static M3U with CC_HOST/CC_PORT

set -Eeuo pipefail

# -----------------------------
# config (from .env where set)
# -----------------------------
export TZ="${TZ:-America/New_York}"

BASE_URL="${VC_RESOLVER_BASE_URL:-http://127.0.0.1:8094}"
DB="${DB:-/app/data/eplus_vc.sqlite3}"
EPG_OUT="${OUT:-/app/out/epg.xml}"
M3U_OUT="${VC_M3U_PATH:-/app/out/virtual_channels.m3u}"

CC_HOST="${CC_HOST:-}"
CC_PORT="${CC_PORT:-5589}"
M3U_GROUP_TITLE="${M3U_GROUP_TITLE:-ESPN+ VC}"

LOG_DIR="/app/logs"
mkdir -p "$LOG_DIR"

# rotation tunables (can be overridden in .env)
LOG_MAX_SIZE_MB="${LOG_MAX_SIZE_MB:-5}"   # rotate at ~5 MB
LOG_KEEP="${LOG_KEEP:-7}"                 # keep 7 gz archives
LOG_MAX_BYTES=$(( LOG_MAX_SIZE_MB * 1024 * 1024 ))

log() { printf '[%(%Y-%m-%dT%H:%M:%S%z)T] %s\n' -1 "$*"; }
on_err() { log "ERROR: line $1 exited non-zero"; }
trap 'on_err $LINENO' ERR

# -----------------------------
# mini log rotation
# -----------------------------
rotate_logs() {
  shopt -s nullglob
  for f in "$LOG_DIR"/*.log; do
    [[ -f "$f" ]] || continue
    sz=$(stat -c%s "$f" 2>/dev/null || echo 0)
    if (( sz >= LOG_MAX_BYTES )); then
      # shift older gz files N..2 -> N+1..3
      for i in $(seq "$LOG_KEEP" -1 2); do
        [[ -f "$f.$((i-1)).gz" ]] && mv -f "$f.$((i-1)).gz" "$f.$i.gz"
      done
      # roll current to .1 and gzip it
      cp -f "$f" "$f.1" && : > "$f"
      gzip -f "$f.1"
    fi
  done
  # prune gz archives older than 30 days
  find "$LOG_DIR" -type f -name '*.gz' -mtime +30 -delete || true
  shopt -u nullglob
}

# -----------------------------
# helpers
# -----------------------------
derive_host_from_base() {
  # input like http://192.168.86.72:8094
  local base="$1"
  echo "${base#*://}" | cut -d/ -f1 | cut -d: -f1
}

rewrite_static_m3u_for_cc() {
  # If the generator wrote chrome://host:port/, rewrite to CC_HOST/CC_PORT
  local file="$1"
  [[ -f "$file" ]] || return 0
  local host="${CC_HOST}"
  if [[ -z "$host" ]]; then
    host="$(derive_host_from_base "$BASE_URL")"
  fi
  # in-place replace: chrome://<anything>:<port>/
  sed -Ei "s#chrome://[^:/]+:[0-9]{2,5}/#chrome://${host}:${CC_PORT}/#g" "$file" || true
}

# -----------------------------
# jitter + health wait
# -----------------------------
# small randomized jitter (0..120s) stagger multiple containers
sleep $(( RANDOM % 121 ))

# wait for resolver readiness (max ~60s)
for i in {1..20}; do
  if curl -sf "$BASE_URL/health" >/dev/null; then
    break
  fi
  log "waiting /health ($i/20)…"
  sleep 3
done

# rotate logs at the start of every cycle
rotate_logs

# -----------------------------
# pipeline
# -----------------------------
if [[ -f "/app/bin/ingest_watch_graph_all_to_db.py" ]]; then
  log "Ingest…"
  python3 /app/bin/ingest_watch_graph_all_to_db.py \
    --db "$DB" --days 3 --tz "$TZ"  \
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
fi

if [[ -f "/app/bin/m3u_from_plan.py" ]]; then
  log "M3U…"
  mkdir -p "$(dirname "$M3U_OUT")"
  python3 /app/bin/m3u_from_plan.py \
    --db "$DB" --out "$M3U_OUT" \
    >> "$LOG_DIR/m3u.log" 2>&1 || log "M3U failed"
  # ensure static file reflects CC_HOST/CC_PORT
  rewrite_static_m3u_for_cc "$M3U_OUT"
fi

log "Update cycle complete."
