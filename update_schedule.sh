#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"
set -Eeuo pipefail

# ------------ config / env ------------
if [[ -f ".env" ]]; then
  set -a
  . ./.env
  set +a
fi

TZ="${TZ:-America/New_York}"
PORT="${PORT:-8094}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_DIR="${DATA_DIR:-$ROOT_DIR/data}"
OUT_DIR="${OUT_DIR:-$ROOT_DIR/out}"
LOG_DIR="${LOG_DIR:-$ROOT_DIR/logs}"
mkdir -p "$DATA_DIR" "$OUT_DIR" "$LOG_DIR" "$OUT_DIR/backups"

DB_HOST="${DB_HOST:-$DATA_DIR/eplus_vc.sqlite3}"

BASE_URL="${VC_RESOLVER_BASE_URL:-http://127.0.0.1:${PORT}}"
HEALTH_URL="${BASE_URL%/}/health"
XML_URL="${BASE_URL%/}/out/epg.xml"
M3U_URL="${BASE_URL%/}/out/playlist.m3u"

VALID_HOURS="${VALID_HOURS:-72}"
LANES="${LANES:-40}"
ALIGN="${ALIGN:-30}"
MIN_GAP_MINS="${MIN_GAP_MINS:-30}"

CC_HOST="${CC_HOST:-127.0.0.1}"
CC_PORT="${CC_PORT:-5589}"

PRE_WAIT="${PRE_WAIT:-5}"
READINESS_TRIES="${READINESS_TRIES:-120}"
READINESS_SLEEP="${READINESS_SLEEP:-1}"

ts() { date +"[%Y-%m-%d %H:%M:%S%z]"; }

# ------------ readiness ------------
echo "$(ts) Pre-wait: sleeping ${PRE_WAIT}s before health checks..."
sleep "$PRE_WAIT"

echo "$(ts) Pre-check: waiting for resolver health at ${HEALTH_URL} ..."
ok=0
for _ in $(seq 1 "$READINESS_TRIES"); do
  code="$(curl -s -o /dev/null -w '%{http_code}' "$HEALTH_URL" || true)"
  if [[ "$code" == "200" ]]; then ok=1; break; fi
  sleep "$READINESS_SLEEP"
done
if [[ "$ok" != "1" ]]; then
  echo "$(ts) ERROR: resolver not healthy at ${HEALTH_URL}" >&2
  exit 1
fi
echo "$(ts) Resolver is healthy."

# ------------ migrate ------------
if [[ -x "bin/db_migrate.py" ]]; then
  echo "$(ts) Running DB migration -> bin/db_migrate.py --db \"$DB_HOST\" ..."
  python3 bin/db_migrate.py --db "$DB_HOST" || true
else
  echo "$(ts) WARN: bin/db_migrate.py not found; skipping migrate."
fi

# ------------ build plan ------------
echo "$(ts) Building plan -> bin/build_plan.py --db $DB_HOST --valid-hours $VALID_HOURS --min-gap-mins $MIN_GAP_MINS --align $ALIGN --lanes $LANES --tz $TZ ..."
python3 bin/build_plan.py \
  --db "$DB_HOST" \
  --valid-hours "$VALID_HOURS" \
  --min-gap-mins "$MIN_GAP_MINS" \
  --align "$ALIGN" \
  --lanes "$LANES" \
  --tz "$TZ"

# ------------ write outputs ------------
echo "$(ts) Writing XMLTV -> $OUT_DIR/epg.xml ..."
python3 bin/xmltv_from_plan.py --db "$DB_HOST" --out "$OUT_DIR/epg.xml"

echo "$(ts) Writing M3U -> $OUT_DIR/playlist.m3u ..."
python3 bin/m3u_from_plan.py --db "$DB_HOST" --out "$OUT_DIR/playlist.m3u" --resolver-base "${BASE_URL%/}" --cc-host "${CC_HOST}" --cc-port "${CC_PORT}"

# small XML backup
cp -f "$OUT_DIR/epg.xml" "$OUT_DIR/backups/epg_$(date +%Y%m%d-%H%M%S).xml" 2>/dev/null || true

# ------------ sanity ------------
echo "$(ts) Sanity: checking health again..."
curl -fsS "$HEALTH_URL" -o "$LOG_DIR/health_last.json" && echo "$(ts) Health OK, saved: $LOG_DIR/health_last.json"

echo "$(ts) Sanity: measuring XMLTV bytes @ $XML_URL ..."
xml_bytes="$(curl -fsS "$XML_URL" | wc -c | tr -d ' ' || echo 0)"
echo "$(ts) XMLTV bytes: ${xml_bytes}"

echo "$(ts) Sanity: measuring M3U bytes @ $M3U_URL ..."
m3u_bytes="$(curl -fsS "$M3U_URL" | wc -c | tr -d ' ' || echo 0)"
echo "$(ts) M3U bytes: ${m3u_bytes}"
