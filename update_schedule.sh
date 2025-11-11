#!/usr/bin/env bash
set -euo pipefail

# --- always run from repo root ---
SCRIPT_DIR="$(cd -- "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# --- load .env if present (host-side) ---
if [ -f ".env" ]; then
  set -a; . ./.env; set +a
fi

# --- defaults (host-side) ---
PORT="${PORT:-8094}"
TZ="${TZ:-America/New_York}"
VALID_HOURS="${VALID_HOURS:-72}"
LANES="${LANES:-40}"
ALIGN="${ALIGN:-30}"
MIN_GAP_MINS="${MIN_GAP_MINS:-30}"
VC_RESOLVER_BASE_URL="${VC_RESOLVER_BASE_URL:-http://127.0.0.1:${PORT}}"
LAN="${VC_RESOLVER_BASE_URL#http://}"; LAN="${LAN#https://}"

# --- SANITIZE: never allow /app/* on the host ---
if [[ "${DB:-}" == /app/* ]];   then echo "[FATAL] .env DB is a container path (${DB}). Use host-relative (e.g., ./data/eplus_vc.sqlite3)." >&2; exit 1; fi
if [[ "${OUT:-}" == /app/* ]];  then echo "[FATAL] .env OUT is a container path (${OUT}). Use host-relative (e.g., ./out)." >&2; exit 1; fi
if [[ "${LOGS:-}" == /app/* ]]; then echo "[FATAL] .env LOGS is a container path (${LOGS}). Use host-relative (e.g., ./logs)." >&2; exit 1; fi

# --- resolve host paths (container bind-mounts map these into /app/*) ---
if [ -z "${DB:-}" ]; then
  HOST_DB="$PWD/data/eplus_vc.sqlite3"
else
  [[ "$DB" = /* ]] && HOST_DB="$DB" || HOST_DB="$PWD/$DB"
fi
HOST_OUT="${OUT:-$PWD/out}"
HOST_LOGS="${LOGS:-$PWD/logs}"
mkdir -p "$(dirname "$HOST_DB")" "$HOST_OUT" "$HOST_LOGS"

ts() { date +'%Y-%m-%d %H:%M:%S'; }

echo "[${TZ} $(ts)] Pre-wait: sleeping 5s before health checks..."
sleep 5

echo "[${TZ} $(ts)] Pre-check: waiting for resolver health at ${VC_RESOLVER_BASE_URL}/health ..."
for i in {1..30}; do
  if curl -fsS "${VC_RESOLVER_BASE_URL}/health" >/dev/null; then
    echo "[${TZ} $(ts)] Resolver is healthy."
    break
  fi
  sleep 1
done

# --- ensure DB exists + migrate (INSIDE container, safe to use /app/*) ---
echo "[${TZ} $(ts)] Ensure DB exists + migrate (inside container)..."
docker compose exec -T espn4cc bash -lc '
  set -e
  : "${DB:=/app/data/eplus_vc.sqlite3}"
  : "${TZ:=America/New_York}"
  : "${LANES:=40}"
  mkdir -p /app/data /app/out /app/logs
  [ -f "$DB" ] || : > "$DB"
  if [ -x /app/bin/db_migrate.py ]; then
    # Idempotent; also normalizes legacy epoch/text columns
    python3 /app/bin/db_migrate.py --db "$DB" --lanes "$LANES" || true
  else
    echo "[warn] bin/db_migrate.py missing (container)."
  fi
'

# --- ingest if empty (INSIDE container) ---
echo "[${TZ} $(ts)] Ingest if empty..."
docker compose exec -T espn4cc bash -lc '
  set -e
  : "${DB:=/app/data/eplus_vc.sqlite3}"
  : "${TZ:=America/New_York}"
  cnt=$(sqlite3 "$DB" "SELECT COUNT(*) FROM events;" 2>/dev/null || echo 0)
  if [ "$cnt" -eq 0 ]; then
    python3 /app/bin/ingest_watch_graph_all_to_db.py --db "$DB" --days 3 --tz "$TZ"
  fi
'

# --- build plan (INSIDE container) ---
echo "[${TZ} $(ts)] Building plan -> bin/build_plan.py ..."
docker compose exec -T espn4cc bash -lc '
  set -e
  : "${DB:=/app/data/eplus_vc.sqlite3}"
  : "${VALID_HOURS:=72}"
  : "${LANES:=40}"
  : "${ALIGN:=30}"
  : "${MIN_GAP_MINS:=30}"
  : "${TZ:=America/New_York}"
  python3 /app/bin/build_plan.py \
    --db "$DB" \
    --valid-hours "$VALID_HOURS" \
    --min-gap-mins "$MIN_GAP_MINS" \
    --align "$ALIGN" \
    --lanes "$LANES" \
    --tz "$TZ"
'

# --- emit XMLTV + M3U (INSIDE container) ---
echo "[${TZ} $(ts)] Writing XMLTV -> $HOST_OUT/epg.xml ..."
docker compose exec -T espn4cc bash -lc '
  set -e
  : "${DB:=/app/data/eplus_vc.sqlite3}"
  python3 /app/bin/xmltv_from_plan.py --db "$DB" --out /app/out/epg.xml
'

echo "[${TZ} $(ts)] Writing M3U -> $HOST_OUT/playlist.m3u ..."
docker compose exec -T espn4cc bash -lc '
  set -e
  : "${DB:=/app/data/eplus_vc.sqlite3}"
  : "${VC_RESOLVER_BASE_URL:=http://127.0.0.1:8094}"
  : "${CC_HOST:=YOUR_LAN_IP}"
  : "${CC_PORT:=5589}"
  python3 /app/bin/m3u_from_plan.py --db "$DB" --out /app/out/playlist.m3u \
    --resolver-base "$VC_RESOLVER_BASE_URL" \
    --cc-host "$CC_HOST" \
    --cc-port "$CC_PORT"
'

# --- sanity (host) via epg_probe.sh ---
bin/epg_probe.sh "${VC_RESOLVER_BASE_URL}" || true

# --- next-12h summary (latest plan; normalizes epoch/text) ---
echo "== sanity summary =="
docker compose exec -T espn4cc bash -lc '
  sqlite3 /app/data/eplus_vc.sqlite3 "
WITH latest AS (SELECT MAX(plan_id) pid FROM plan_slot),
norm AS (
  SELECT CASE
           WHEN typeof(start_utc)=\"text\" THEN strftime(\"%s\",start_utc)
           WHEN start_utc IS NOT NULL     THEN start_utc
           ELSE starts_at
         END AS s_epoch,
         is_placeholder
  FROM plan_slot, latest WHERE plan_slot.plan_id = latest.pid
)
SELECT
  (SELECT COUNT(*) FROM norm WHERE s_epoch>=strftime(\"%s\",\"now\") AND s_epoch<strftime(\"%s\",\"now\",\"+12 hours\")) AS total_12h,
  (SELECT COUNT(*) FROM norm WHERE is_placeholder=0 AND s_epoch>=strftime(\"%s\",\"now\") AND s_epoch<strftime(\"%s\",\"now\",\"+12 hours\")) AS real_12h,
  (SELECT COUNT(*) FROM norm WHERE is_placeholder=1 AND s_epoch>=strftime(\"%s\",\"now\") AND s_epoch<strftime(\"%s\",\"now\",\"+12 hours\")) AS placeholders_12h;"
' || true

echo "== first non-placeholder title =="
grep -m1 -A1 -B2 -F "<title>" "$HOST_OUT/epg.xml" || true

# --- filter summary (if filters.ini exists) ---
if [ -f "filters.ini" ]; then
  echo "== filter summary =="
  docker compose exec -T espn4cc bash -lc '
    set -e
    : "${DB:=/app/data/eplus_vc.sqlite3}"
    total_events=$(sqlite3 "$DB" "SELECT COUNT(*) FROM events;" 2>/dev/null || echo 0)
    latest_plan=$(sqlite3 "$DB" "SELECT MAX(plan_id) FROM plan_slot;" 2>/dev/null || echo 0)
    if [ "$latest_plan" -gt 0 ]; then
      included_events=$(sqlite3 "$DB" "SELECT COUNT(DISTINCT event_id) FROM plan_slot WHERE plan_id=$latest_plan AND kind=\"event\" AND event_id IS NOT NULL;" 2>/dev/null || echo 0)
      filtered_out=$((total_events - included_events))
      echo "total_events_in_db=$total_events  included_in_plan=$included_events  filtered_out=$filtered_out"

      # Show breakdown by filter dimension if we have filter stats
      if [ -f /app/filters.ini ]; then
        echo "Active filters: /app/filters.ini"
        grep -E "^(enabled_|exclude_|require_)" /app/filters.ini | grep -v "^#" | grep -v "= \*$" | grep -v "= $" | sed "s/^/  /" || echo "  (all filters set to default '*')"
      fi
    else
      echo "No plan generated yet"
    fi
  ' || echo "(filter summary unavailable)"
fi

# Provenance
echo "[info] git describe: $(git describe --tags --always --dirty 2>/dev/null || echo n/a)"

# --- install summary (host) ---
echo "== installation summary =="
echo "Resolver: ${VC_RESOLVER_BASE_URL}"
echo "Health:   ${VC_RESOLVER_BASE_URL}/health"
echo "XMLTV:    ${VC_RESOLVER_BASE_URL}/out/epg.xml"
echo "M3U:      ${VC_RESOLVER_BASE_URL}/out/playlist.m3u"
echo
echo "In Channels DVR: Settings > Sources > Add >"
echo "  - M3U:    ${VC_RESOLVER_BASE_URL}/out/playlist.m3u"
echo "  - XMLTV:  ${VC_RESOLVER_BASE_URL}/out/epg.xml"
