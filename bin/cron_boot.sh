#!/usr/bin/env bash
set -Eeuo pipefail

# Defaults
DB="${DB:-/app/data/eplus_vc.sqlite3}"
LOG_DIR="${LOGS:-/app/logs}"
mkdir -p "$LOG_DIR"

# Export all current environment variables to a file that cron can source
# This ensures filter settings and other env vars are available to cron jobs
printenv | grep -v "^_" | sed 's/^\(.*\)$/export \1/g' > /tmp/cron_env.sh

# Write to /etc/cron.d/ which doesn't require passwd entry
# Format: minute hour day month weekday user command
cat >/etc/cron.d/espn4cc4c <<CRON
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
SHELL=/bin/bash

# Refresh 3× daily (08:05, 14:05, 20:05)
5 8,14,20 * * * root . /tmp/cron_env.sh && /usr/bin/flock -n /tmp/espn4cc4c_refresh.lock python3 /app/bin/refresh_in_container.py >> ${LOG_DIR}/cron_refresh.log 2>&1

# Weekly VACUUM (Sunday 03:10)
10 3 * * 0 root . /tmp/cron_env.sh && /usr/bin/flock -n /tmp/espn4cc4c_vacuum.lock sqlite3 ${DB} 'PRAGMA wal_checkpoint(TRUNCATE); VACUUM;' >> ${LOG_DIR}/cron_vacuum.log 2>&1
CRON

# Set proper permissions for /etc/cron.d/ file
chmod 0644 /etc/cron.d/espn4cc4c

# Touch the file so cron picks it up
touch /etc/cron.d/espn4cc4c

echo "Crontab installed successfully"
