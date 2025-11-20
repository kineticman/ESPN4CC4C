#!/usr/bin/env bash
set -Eeuo pipefail

# Defaults
DB="${DB:-/app/data/eplus_vc.sqlite3}"
LOG_DIR="${LOGS:-/app/logs}"
mkdir -p "$LOG_DIR"

# Write crontab WITHOUT username field (since we're loading it as root's crontab)
cat >/tmp/espn4cc4c_crontab <<CRON
# Refresh 3× daily (08:05, 14:05, 20:05)
5 8,14,20 * * * /usr/bin/flock -n /tmp/espn4cc4c_refresh.lock /usr/local/bin/python3 /app/bin/refresh_in_container.py >> ${LOG_DIR}/cron_refresh.log 2>&1

# Weekly VACUUM (Sunday 03:10)
10 3 * * 0 /usr/bin/flock -n /tmp/espn4cc4c_vacuum.lock /usr/bin/sqlite3 ${DB} 'PRAGMA wal_checkpoint(TRUNCATE); VACUUM;' >> ${LOG_DIR}/cron_vacuum.log 2>&1
CRON

# Install as root's crontab
crontab /tmp/espn4cc4c_crontab

echo "Crontab installed successfully"
