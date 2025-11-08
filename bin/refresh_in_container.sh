#!/usr/bin/env bash
set -euo pipefail

# --- load .env if present (non-fatal) ---
if [ -f /app/.env ]; then
  # shellcheck disable=SC1091
  . /app/.env || true
fi

# --- env & defaults (container paths) ---
DB=${DB:-/app/data/eplus_vc.sqlite3}
OUT_DIR=${OUT:-/app/out}
LOGS_DIR=${LOGS:-/app/logs}
VC_M3U_PATH=${VC_M3U_PATH:-${OUT_DIR}/playlist.m3u}

TZ=${TZ:-America/New_York}
VALID_HOURS=${VALID_HOURS:-72}
LANES=${LANES:-40}
ALIGN=${ALIGN:-30}
MIN_GAP_MINS=${MIN_GAP_MINS:-30}

VC_RESOLVER_BASE_URL=${VC_RESOLVER_BASE_URL:-http://127.0.0.1:8094}
CC_HOST=${CC_HOST:-127.0.0.1}
CC_PORT=${CC_PORT:-5589}

LOCK_FILE=/tmp/espn4cc.lock
LOG_FILE="${LOGS_DIR}/cron.log"

mkdir -p /app/data "${OUT_DIR}" "${LOGS_DIR}"
: >"${LOG_FILE}" || true
chmod 666 "${LOG_FILE}" || true

# --- single-run lock (in case cron fires twice) ---
exec 9>"${LOCK_FILE}"
if ! flock -n 9; then
  echo "[${TZ} $(date +"%F %T")] Another refresh is running; exiting." | tee -a "${LOG_FILE}"
  exit 0
fi

echo "[${TZ} $(date +"%F %T")] refresh_in_container: start" | tee -a "${LOG_FILE}"

# --- light jitter (helps when many users run at the top of the hour) ---
sleep $((RANDOM % 5))

# --- export TZ for Python libs that respect it ---
export TZ

# --- ensure DB exists & migrate schema ---
[ -f "${DB}" ] || : > "${DB}"
[ -x /app/bin/db_migrate.py ] && python3 /app/bin/db_migrate.py --db "${DB}" --lanes "${LANES}" | tee -a "${LOG_FILE}" || true

# --- ingest if empty (retry a couple times; ESPN sometimes 503s) ---
needs_ingest=$(sqlite3 "${DB}" "SELECT CASE WHEN (SELECT COUNT(*) FROM events) = 0 THEN 1 ELSE 0 END;") || needs_ingest=1
if [ "${needs_ingest}" = "1" ]; then
  for attempt in 1 2 3; do
    echo "[${TZ} $(date +"%F %T")] ingest attempt ${attempt}" | tee -a "${LOG_FILE}"
    if python3 /app/bin/ingest_watch_graph_all_to_db.py --db "${DB}" --days 3 --tz "${TZ}" | tee -a "${LOG_FILE}"; then
      break
    fi
    sleep $((attempt * 3))
  done
fi

# --- build plan ---
python3 /app/bin/build_plan.py \
  --db "${DB}" \
  --valid-hours "${VALID_HOURS}" \
  --min-gap-mins "${MIN_GAP_MINS}" \
  --align "${ALIGN}" \
  --lanes "${LANES}" \
  --tz "${TZ}" | tee -a "${LOG_FILE}"

# --- write XMLTV & M3U (respect OUT/VC_M3U_PATH) ---
python3 /app/bin/xmltv_from_plan.py --db "${DB}" --out "${OUT_DIR}/epg.xml" | tee -a "${LOG_FILE}"
python3 /app/bin/m3u_from_plan.py   --db "${DB}" --out "${VC_M3U_PATH}" \
  --resolver-base "${VC_RESOLVER_BASE_URL}" \
  --cc-host "${CC_HOST}" \
  --cc-port "${CC_PORT}" | tee -a "${LOG_FILE}"

# --- tiny success trailer for quick greps ---
prog_count=$(grep -c "<programme " "${OUT_DIR}/epg.xml" || echo 0)
echo "[${TZ} $(date +"%F %T")] refresh_in_container: done; programmes=${prog_count}; m3u=$(basename "${VC_M3U_PATH}")" | tee -a "${LOG_FILE}"
