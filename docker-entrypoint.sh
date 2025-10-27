#!/usr/bin/env bash
set -euo pipefail
[ -f "/app/.env" ] && set -a && . /app/.env && set +a
: "${PORT:=8094}"; : "${TZ:=America/New_York}"
ln -sf "/usr/share/zoneinfo/$TZ" /etc/localtime || true; echo "$TZ" > /etc/timezone || true
mkdir -p /app/data /app/out /app/logs
SCHEDULE_HOURS="${SCHEDULE_HOURS:-6}"
echo "0 */${SCHEDULE_HOURS} * * * /app/update_schedule.sh >> /app/logs/schedule.log 2>&1" > /var/spool/cron/crontabs/root
echo "17 3 * * 0 sqlite3 /app/data/eplus_vc.sqlite3 'VACUUM;'" >> /var/spool/cron/crontabs/root
cron
exec python3 -m uvicorn bin.vc_resolver:app --host 0.0.0.0 --port "$PORT"
