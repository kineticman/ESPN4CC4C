#!/usr/bin/env bash
set -euo pipefail
DB=${DB:-/app/data/eplus_vc.sqlite3}
TZ=${TZ:-America/New_York}
VALID_HOURS=${VALID_HOURS:-72}
LANES=${LANES:-40}
ALIGN=${ALIGN:-30}
MIN_GAP_MINS=${MIN_GAP_MINS:-30}
VC_RESOLVER_BASE_URL=${VC_RESOLVER_BASE_URL:-http://127.0.0.1:8094}
CC_HOST=${CC_HOST:-YOUR_LAN_IP}
CC_PORT=${CC_PORT:-5589}
mkdir -p /app/data /app/out /app/logs
[ -f "$DB" ] || : > "$DB"
[ -x /app/bin/db_migrate.py ] && python3 /app/bin/db_migrate.py --db "$DB" --lanes "$LANES" || true
cnt=$(sqlite3 "$DB" "SELECT COUNT(*) FROM events;" 2>/dev/null || echo 0)
if [ "$cnt" -eq 0 ]; then
  python3 /app/bin/ingest_watch_graph_all_to_db.py --db "$DB" --days 3 --tz "$TZ"
fi
python3 /app/bin/build_plan.py --db "$DB" --valid-hours "$VALID_HOURS" --min-gap-mins "$MIN_GAP_MINS" --align "$ALIGN" --lanes "$LANES" --tz "$TZ"
python3 /app/bin/xmltv_from_plan.py --db "$DB" --out /app/out/epg.xml
python3 /app/bin/m3u_from_plan.py   --db "$DB" --out /app/out/playlist.m3u --resolver-base "$VC_RESOLVER_BASE_URL" --cc-host "$CC_HOST" --cc-port "$CC_PORT"
