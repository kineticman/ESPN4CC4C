#!/usr/bin/env bash
# ESPN4CC4C refresh: migrate DB -> build plan -> emit XMLTV/M3U -> sanity checks
set -Eeuo pipefail

export TZ="${TZ:-America/New_York}"

# Load .env (quote-safe)
if [[ -f ".env" ]]; then
  set -a
  . ./.env
  set +a
fi

# Derive base URL
PORT="${PORT:-8094}"
BASE_URL="${VC_RESOLVER_BASE_URL:-http://127.0.0.1:${PORT}}"
if [[ "$BASE_URL" != http://* && "$BASE_URL" != https://* ]]; then
  BASE_URL="http://$BASE_URL"
fi
export VC_RESOLVER_ORIGIN="${VC_RESOLVER_ORIGIN:-$BASE_URL}"

# Project root (host)
PROJ_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Container-style paths from .env (fallbacks)
DB="${DB:-/app/data/eplus_vc.sqlite3}"
OUT_ENV="${OUT:-/app/out}"
LOGS_ENV="${LOGS:-/app/logs}"

# Map /app/* -> host paths under $PROJ_DIR
resolve_host_path() {
  local p="$1"
  if [[ "$p" == /app/* ]]; then
    printf '%s/%s' "$PROJ_DIR" "${p#/app/}"
  else
    printf '%s' "$p"
  fi
}
DB_HOST="$(resolve_host_path "$DB")"
OUT_DIR="$(resolve_host_path "$OUT_ENV")"
LOG_DIR="$(resolve_host_path "$LOGS_ENV")"

mkdir -p "$OUT_DIR" "$LOG_DIR" "$(dirname "$DB_HOST")"

EPG_URL="${BASE_URL%/}/out/epg.xml"
M3U_URL="${BASE_URL%/}/out/playlist.m3u"
HEALTH_URL="${BASE_URL%/}/health"

log() { printf '[%s] %s\n' "$(date +'%Y-%m-%d %H:%M:%S%z')" "$*"; }

readiness_wait() {
  local url="$1" max_tries="${2:-120}" sleep_s="${3:-1}"
  local code
  for ((i=1;i<=max_tries;i++)); do
    code="$(curl -s -o /dev/null -w '%{http_code}' "$url" || true)"
    if [[ "$code" == "200" ]]; then return 0; fi
    sleep "$sleep_s"
  done
  return 1
}

# Optional pre-wait
PRE_WAIT="${PRE_WAIT:-0}"
if [[ "$PRE_WAIT" -gt 0 ]]; then
  log "Pre-wait: sleeping ${PRE_WAIT}s before health checks..."
  sleep "$PRE_WAIT"
fi

log "Pre-check: waiting for resolver health at $HEALTH_URL ..."
if ! readiness_wait "$HEALTH_URL" 120 1; then
  log "ERROR: resolver not healthy @ $HEALTH_URL"
  exit 1
fi
log "Resolver is healthy."

# DB migrate (ok if missing)
if [[ -x "bin/db_migrate.py" ]]; then
  log "Running DB migration -> bin/db_migrate.py --db \"$DB_HOST\" ..."
  python3 bin/db_migrate.py --db "$DB_HOST"
else
  log "WARN: bin/db_migrate.py not found; skipping migrate."
fi

# Build plan (pass --db and tunables if present)
BP_ARGS=( --db "$DB_HOST" )
[[ -n "${VALID_HOURS:-}"    ]] && BP_ARGS+=( --valid-hours "$VALID_HOURS" )
[[ -n "${MIN_GAP_MINS:-}"   ]] && BP_ARGS+=( --min-gap-mins "$MIN_GAP_MINS" )
[[ -n "${ALIGN:-}"          ]] && BP_ARGS+=( --align "$ALIGN" )
[[ -n "${LANES:-}"          ]] && BP_ARGS+=( --lanes "$LANES" )
[[ -n "${TZ:-}"             ]] && BP_ARGS+=( --tz "$TZ" )

if [[ -x "bin/build_plan.py" ]]; then
  log "Building plan -> bin/build_plan.py ${BP_ARGS[*]} ..."
  python3 bin/build_plan.py "${BP_ARGS[@]}"
else
  log "WARN: bin/build_plan.py not found; skipping plan build."
fi

# Emit XMLTV/M3U (pass --db + --out)
if [[ -x "bin/xmltv_from_plan.py" ]]; then
  log "Writing XMLTV -> $OUT_DIR/epg.xml ..."
  python3 bin/xmltv_from_plan.py --db "$DB_HOST" --out "$OUT_DIR/epg.xml"
else
  log "WARN: bin/xmltv_from_plan.py missing; assuming resolver serves XML."
fi

if [[ -x "bin/m3u_from_plan.py" ]]; then
  log "Writing M3U -> $OUT_DIR/playlist.m3u ..."
  python3 bin/m3u_from_plan.py --db "$DB_HOST" --out "$OUT_DIR/playlist.m3u" \
    --resolver-base "${BASE_URL%/}" \
    --cc-host "192.168.86.72}" \
    --cc-port "5589"
else
  log "WARN: bin/m3u_from_plan.py missing; assuming resolver serves M3U."
fi

# Sanity checks (GET only)
log "Sanity: checking health again..."
curl -fsS "$HEALTH_URL" -o "$LOG_DIR/health_last.json" || { log "ERROR: health GET failed"; exit 1; }
log "Health OK, saved: $LOG_DIR/health_last.json"

log "Sanity: measuring XMLTV bytes @ $EPG_URL ..."
XML_BYTES="$(curl -fsS "$EPG_URL" | wc -c | tr -d ' ')"
log "XMLTV bytes: $XML_BYTES"

log "Sanity: measuring M3U bytes @ $M3U_URL ..."
M3U_BYTES="$(curl -fsS "$M3U_URL" | wc -c | tr -d ' ')"
log "M3U bytes: $M3U_BYTES"

log "Sanity: first <channel id> from XMLTV ..."
FIRST_CHAN_ID="$(curl -fsS "$EPG_URL" | grep -oE '<channel[^>]+id="[^"]+"' | head -n1 | sed -E 's/.*id="([^"]+)".*/\1/')"
log "First channel id: ${FIRST_CHAN_ID:-N/A}"

log "Sanity: first tvg-id from M3U ..."
FIRST_TVG_ID="$(curl -fsS "$M3U_URL" | awk '/^#EXTINF:/ {print; exit}' | sed -n 's/.*tvg-id="\([^"]\+\)".*/\1/p')"
log "First tvg-id: ${FIRST_TVG_ID:-N/A}"

log "Cycle complete."
