#!/usr/bin/env bash
set -Eeuo pipefail

# Defaults
DB="${DB:-/app/data/eplus_vc.sqlite3}"
LOG_DIR="${LOGS:-/app/logs}"
mkdir -p "$LOG_DIR"

# Write crontab for root. Times are local; TZ is set via compose.
cat >/etc/cron.d/espn4cc4c <<CRON
# Refresh 3× daily (08:05, 14:05, 20:05)
5 8,14,20 * * * root /usr/bin/flock -n /tmp/espn4cc4c_refresh.lock /usr/bin/python3 /app/bin/refresh_in_container.py >> ${LOG_DIR}/cron_refresh.log 2>&1

# Weekly VACUUM (Sunday 03:10)
10 3 * * 0 root /usr/bin/flock -n /tmp/espn4cc4c_vacuum.lock /usr/bin/sqlite3 ${DB} 'PRAGMA wal_checkpoint(TRUNCATE); VACUUM;' >> ${LOG_DIR}/cron_vacuum.log 2>&1
CRON

chmod 0644 /etc/cron.d/espn4cc4c
crontab /etc/cron.d/espn4cc4c

# Start cron in the background, then exit (main CMD starts API)
service cron start >/dev/null 2>&1 || true
cron || true
exit 0
