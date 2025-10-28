#!/usr/bin/env bash
set -euo pipefail

# Always run from repo root
SCRIPT_DIR="$(cd -- "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Load .env if present
if [ -f ".env" ]; then
  set -a; . ./.env; set +a
fi

# Defaults
PORT="${PORT:-8094}"
TZ="${TZ:-America/New_York}"

# Map DB/OUT/LOGS to host paths (not /app/*) when this script runs on host
if [ -z "${DB:-}" ]; then
  DB="$PWD/data/eplus_vc.sqlite3"
elif [[ "$DB" == /app/* ]]; then
  DB="$PWD${DB#/app}"
fi
if [ -z "${OUT:-}" ]; then
  OUT="$PWD/out"
elif [[ "$OUT" == /app/* ]]; then
  OUT="$PWD${OUT#/app}"
fi
if [ -z "${LOGS:-}" ]; then
  LOGS="$PWD/logs"
elif [[ "$LOGS" == /app/* ]]; then
  LOGS="$PWD${LOGS#/app}"
fi
mkdir -p "$(dirname "$DB")" "$OUT" "$LOGS"

# Planner tunables
VALID_HOURS="${VALID_HOURS:-72}"
LANES="${LANES:-40}"
ALIGN="${ALIGN:-30}"
MIN_GAP_MINS="${MIN_GAP_MINS:-30}"

# Resolver base & CC
VC_RESOLVER_BASE_URL="${VC_RESOLVER_BASE_URL:-http://127.0.0.1:${PORT}}"
CC_HOST="${CC_HOST:-${VC_RESOLVER_BASE_URL#http://}}"
CC_HOST="${CC_HOST#https://}"; CC_HOST="${CC_HOST#http://}"
CC_HOST="${CC_HOST%%:*}"
CC_PORT="${CC_PORT:-5589}"
M3U_GROUP_TITLE="${M3U_GROUP_TITLE:-ESPN+ VC}"

ts() { date +"%Y-%m-%d %H:%M:%S%z"; }

echo "[$(ts)] Pre-wait: sleeping ${PRE_WAIT:-5}s before health checks..."
sleep "${PRE_WAIT:-5}"

echo "[$(ts)] Pre-check: waiting for resolver health at ${VC_RESOLVER_BASE_URL%/}/health ..."
curl -fsS "${VC_RESOLVER_BASE_URL%/}/health" >/dev/null
echo "[$(ts)] Resolver is healthy."

# --- Migrate (hard fail if missing) ---
if [ ! -x bin/db_migrate.py ]; then
  echo "[$(ts)] FATAL: bin/db_migrate.py not found in $PWD — aborting."
  exit 1
fi
echo "[$(ts)] Migrating DB -> $DB ..."
python3 bin/db_migrate.py --db "$DB" | tee -a "$LOGS/db_migrate.log"

# --- Ingest (~72h ESPN+ airings) ---
if [ -n "${WATCH_API_KEY:-}" ]; then
  echo "[$(ts)] Ingesting ~${VALID_HOURS}h ESPN+ airings into $DB ..."
  python3 bin/ingest_watch_graph_all_to_db.py --db "$DB" --days 3 --tz "$TZ" | tee -a "$LOGS/ingest.log"
else
  echo "[$(ts)] WARN: WATCH_API_KEY not set; skipping ingest (plan may be placeholders)."
fi

# --- Plan build ---
echo "[$(ts)] Building plan -> bin/build_plan.py --db $DB --valid-hours $VALID_HOURS --min-gap-mins $MIN_GAP_MINS --align $ALIGN --lanes $LANES --tz $TZ ..."
python3 bin/build_plan.py \
  --db "$DB" \
  --valid-hours "$VALID_HOURS" \
  --min-gap-mins "$MIN_GAP_MINS" \
  --align "$ALIGN" \
  --lanes "$LANES" \
  --tz "$TZ" | tee -a "$LOGS/plan.log"

# --- Emit XMLTV/M3U (host OUT path) ---
XML="$OUT/epg.xml"
M3U="$OUT/playlist.m3u"
echo "[$(ts)] Writing XMLTV -> $XML ..."
python3 bin/xmltv_from_plan.py --db "$DB" --out "$XML" | tee -a "$LOGS/xmltv.log"

echo "[$(ts)] Writing M3U -> $M3U ..."
python3 bin/m3u_from_plan.py --db "$DB" --out "$M3U" \
  --resolver-base "$VC_RESOLVER_BASE_URL" \
  --cc-host "$CC_HOST" \
  --cc-port "$CC_PORT" \
  | tee -a "$LOGS/m3u.log"

# --- Sanity checks (GET-only) ---
echo "[$(ts)] Sanity: checking health again..."
curl -fsS "${VC_RESOLVER_BASE_URL%/}/health" | tee "$LOGS/health_last.json" >/dev/null || true

echo "[$(ts)] Sanity: measuring XMLTV bytes @ ${VC_RESOLVER_BASE_URL%/}/out/epg.xml ..."
curl -fsS "${VC_RESOLVER_BASE_URL%/}/out/epg.xml" | wc -c | awk '{print "[info] XMLTV bytes: "$1}'

echo "[$(ts)] Sanity: measuring M3U bytes @ ${VC_RESOLVER_BASE_URL%/}/out/playlist.m3u ..."
curl -fsS "${VC_RESOLVER_BASE_URL%/}/out/playlist.m3u" | wc -c | awk '{print "[info] M3U bytes: "$1}'

echo "[info] git describe: $(git describe --tags --always --dirty 2>/dev/null || echo n/a)"
