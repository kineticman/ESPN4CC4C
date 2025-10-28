#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"
set -euo pipefail

# Always execute from repo root so relative paths are correct.
SCRIPT_DIR="$(cd -- "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Load .env into the current shell (safe on host).
if [[ -f ".env" ]]; then
  set -a; . ./.env; set +a
fi

# --- defaults & derived host paths ---
PORT="${PORT:-8094}"
TZ="${TZ:-America/New_York}"

# If DB/OUT/LOGS refer to /app (container paths), map them to host repo paths.
if [[ -z "${DB:-}" ]]; then
  DB="$PWD/data/eplus_vc.sqlite3"
elif [[ "$DB" == /app/* ]]; then
  DB="$PWD${DB#/app}"
fi
OUT="${OUT:-$PWD/out}"
LOGS="${LOGS:-$PWD/logs}"

mkdir -p "$(dirname "$DB")" "$OUT" "$LOGS"

# --- planner tunables (with safe fallbacks) ---
VALID_HOURS="${VALID_HOURS:-72}"
LANES="${LANES:-40}"
ALIGN="${ALIGN:-30}"
MIN_GAP_MINS="${MIN_GAP_MINS:-30}"

# --- resolver base + Chrome Capture envs ---
VC_RESOLVER_BASE_URL="${VC_RESOLVER_BASE_URL:-http://127.0.0.1:${PORT}}"
CC_HOST="${CC_HOST:-${VC_RESOLVER_BASE_URL#http://}}"
CC_HOST="${CC_HOST%%:*}"             # ensure host only
CC_PORT="${CC_PORT:-5589}"
M3U_GROUP_TITLE="${M3U_GROUP_TITLE:-ESPN+ VC}"

# --- health pre-check (against running container) ---
PRE_WAIT="${PRE_WAIT:-5}"
echo "[${TZ} $(date +'%Y-%m-%d %H:%M:%S')] Pre-wait: sleeping ${PRE_WAIT}s before health checks..."
sleep "$PRE_WAIT"

HEALTH_URL="${VC_RESOLVER_BASE_URL%/}/health"
echo "[${TZ} $(date +'%Y-%m-%d %H:%M:%S')] Pre-check: waiting for resolver health at ${HEALTH_URL} ..."
if curl -fsS "$HEALTH_URL" >/dev/null; then
  echo "[${TZ} $(date +'%Y-%m-%d %H:%M:%S')] Resolver is healthy."
else
  echo "[${TZ} $(date +'%Y-%m-%d %H:%M:%S')] ERROR: Resolver not healthy at ${HEALTH_URL}" >&2
  exit 1
fi

# --- ensure migrator exists and run it inside the container (canonicalize schema to v3) ---
if [[ ! -f "bin/db_migrate.py" ]]; then
  echo "FATAL: bin/db_migrate.py not found in $PWD — aborting."
  exit 1
fi
echo "[${TZ} $(date +'%Y-%m-%d %H:%M:%S')] Migrating DB schema (v3)..."
docker compose exec -T espn4cc python3 /app/bin/db_migrate.py --db /app/data/eplus_vc.sqlite3 >/dev/null

# --- ingest if events table is empty (container-side) ---
echo "[${TZ} $(date +'%Y-%m-%d %H:%M:%S')] Ingest if empty..."
docker compose exec -T espn4cc bash -lc '
  set -e
  DB=${DB:-/app/data/eplus_vc.sqlite3}
  TZ=${TZ:-America/New_York}
  NEED=$(sqlite3 "$DB" "SELECT COUNT(*) FROM events;" 2>/dev/null || echo 0)
  if [ "$NEED" -eq 0 ]; then
    python3 /app/bin/ingest_watch_graph_all_to_db.py --db "$DB" --days 3 --tz "$TZ"
  fi
'

# --- build plan (host-side, writes to host paths) ---
echo "[${TZ} $(date +'%Y-%m-%d %H:%M:%S')] Building plan -> bin/build_plan.py --db ${DB} --valid-hours ${VALID_HOURS} --min-gap-mins ${MIN_GAP_MINS} --align ${ALIGN} --lanes ${LANES} --tz ${TZ} ..."
python3 bin/build_plan.py \
  --db "$DB" \
  --valid-hours "$VALID_HOURS" \
  --min-gap-mins "$MIN_GAP_MINS" \
  --align "$ALIGN" \
  --lanes "$LANES" \
  --tz "$TZ" \
  | tee -a "$LOGS/plan.log" || true

# --- emit XMLTV ---
echo "[${TZ} $(date +'%Y-%m-%d %H:%M:%S')] Writing XMLTV -> ${OUT}/epg.xml ..."
python3 bin/xmltv_from_plan.py --db "$DB" --out "${OUT}/epg.xml" | tee -a "$LOGS/xmltv.log" || true

# --- emit M3U (always pass explicit flags so .env is honored) ---
echo "[${TZ} $(date +'%Y-%m-%d %H:%M:%S')] Writing M3U -> ${OUT}/playlist.m3u ..."
python3 bin/m3u_from_plan.py \
  --db "$DB" \
  --out "${OUT}/playlist.m3u" \
  --resolver-base "${VC_RESOLVER_BASE_URL}" \
  --cc-host "${CC_HOST}" \
  --cc-port "${CC_PORT}" \
  | tee -a "$LOGS/m3u.log" || true

# --- GET-only sanity checks on resolver-served files ---
echo "[${TZ} $(date +'%Y-%m-%d %H:%M:%S')] Sanity: checking health again..."
curl -fsS "$HEALTH_URL" -o "$LOGS/health_last.json" >/dev/null && echo "[${TZ} $(date +'%Y-%m-%d %H:%M:%S')] Health OK, saved: $LOGS/health_last.json"

XML_URL="${VC_RESOLVER_BASE_URL%/}/out/epg.xml"
M3U_URL="${VC_RESOLVER_BASE_URL%/}/out/playlist.m3u"

echo "[${TZ} $(date +'%Y-%m-%d %H:%M:%S')] Sanity: measuring XMLTV bytes @ ${XML_URL} ..."
XML_BYTES=$(curl -fsS "$XML_URL" | wc -c | awk "{print \$1}")
echo "[${TZ} $(date +'%Y-%m-%d %H:%M:%S')] XMLTV bytes: ${XML_BYTES}"

echo "[${TZ} $(date +'%Y-%m-%d %H:%M:%S')] Sanity: measuring M3U bytes @ ${M3U_URL} ..."
M3U_BYTES=$(curl -fsS "$M3U_URL" | wc -c | awk "{print \$1}")
echo "[${TZ} $(date +'%Y-%m-%d %H:%M:%S')] M3U bytes: ${M3U_BYTES}"

# provenance
echo "[info] git describe: $(git describe --tags --always --dirty 2>/dev/null || echo n/a)"
