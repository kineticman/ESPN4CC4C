#!/bin/bash
set -e

echo "Starting ESPN4CC4C..."

if [ -f /app/.env ]; then
    export $(grep -v '^#' /app/.env | xargs)
fi

export DB=${DB:-/app/data/eplus_vc.sqlite3}
export OUT=${OUT:-/app/out/epg.xml}
export TZ=${TZ:-America/New_York}
export VALID_HOURS=${VALID_HOURS:-72}
export PORT=${PORT:-8094}
export SCHEDULE_HOURS=${SCHEDULE_HOURS:-6}

echo "Database: $DB"
echo "Timezone: $TZ"
echo "Resolver: $VC_RESOLVER_BASE_URL"

if [ ! -f "$DB" ]; then
    echo "Creating database..."
    python3 bin/ingest_watch_graph_all_to_db.py --db "$DB" --days 1 --tz "$TZ" 2>&1 | tee -a /app/logs/ingest.log
    python3 bin/build_plan.py --db "$DB" --valid-hours "$VALID_HOURS" --tz "$TZ" 2>&1 | tee -a /app/logs/plan.log
    python3 bin/xmltv_from_plan.py --db "$DB" --out "$OUT" --resolver-base "$VC_RESOLVER_BASE_URL" 2>&1 | tee -a /app/logs/xmltv.log
    M3U_OUT=${VC_M3U_PATH:-/app/out/virtual_channels.m3u}
    python3 bin/m3u_from_plan.py --db "$DB" --out "$M3U_OUT" --resolver-base "$VC_RESOLVER_BASE_URL" 2>&1 | tee -a /app/logs/m3u.log
fi

cat > /app/update_schedule.sh << 'UPDATEEOF'
#!/bin/bash
source /app/.env 2>/dev/null || true
export DB=${DB:-/app/data/eplus_vc.sqlite3}
export OUT=${OUT:-/app/out/epg.xml}
export TZ=${TZ:-America/New_York}
export VALID_HOURS=${VALID_HOURS:-72}

echo "[$(date)] Starting update..." >> /app/logs/schedule.log
python3 /app/bin/ingest_watch_graph_all_to_db.py --db "$DB" --days 1 --tz "$TZ" >> /app/logs/ingest.log 2>&1
python3 /app/bin/build_plan.py --db "$DB" --valid-hours "$VALID_HOURS" --tz "$TZ" >> /app/logs/plan.log 2>&1
python3 /app/bin/xmltv_from_plan.py --db "$DB" --out "$OUT" --resolver-base "$VC_RESOLVER_BASE_URL" >> /app/logs/xmltv.log 2>&1
M3U_OUT=${VC_M3U_PATH:-/app/out/virtual_channels.m3u}
python3 /app/bin/m3u_from_plan.py --db "$DB" --out "$M3U_OUT" --resolver-base "$VC_RESOLVER_BASE_URL" >> /app/logs/m3u.log 2>&1
echo "[$(date)] Update completed" >> /app/logs/schedule.log
UPDATEEOF

chmod +x /app/update_schedule.sh

CRON_SCHEDULE="0 */$SCHEDULE_HOURS * * *"
echo "$CRON_SCHEDULE /app/update_schedule.sh" > /etc/cron.d/espn4cc
chmod 0644 /etc/cron.d/espn4cc
crontab /etc/cron.d/espn4cc

cron

echo "Starting resolver on port $PORT..."
exec python3 -m uvicorn bin.vc_resolver:app --host 0.0.0.0 --port "$PORT"
