#!/usr/bin/env bash
set -Eeuo pipefail

# === cron_boot.sh — install default schedules and start cron ===
# Schedules:
#  - Refresh database 3× daily (08:05, 14:05, 20:05 local time)
#  - Weekly VACUUM on Sunday at 03:10 (also checkpoints WAL)
#
# Logs go to $LOGS (default /app/logs). DB defaults to /app/data/eplus_vc.sqlite3.
# Uses flock so runs never overlap.

DB="${DB:-/app/data/eplus_vc.sqlite3}"
LOG_DIR="${LOGS:-/app/logs}"
mkdir -p "$LOG_DIR"

cat >/etc/cron.d/espn4cc4c <<CRON
# Refresh 3× daily (08:05, 14:05, 20:05)
5 8,14,20 * * * root /usr/bin/flock -n /tmp/espn4cc4c_refresh.lock /usr/bin/python3 /app/bin/refresh_in_container.py >> ${LOG_DIR}/cron_refresh.log 2>&1

# Weekly VACUUM (Sunday 03:10)
10 3 * * 0 root /usr/bin/flock -n /tmp/espn4cc4c_vacuum.lock /usr/bin/sqlite3 ${DB} 'PRAGMA wal_checkpoint(TRUNCATE); VACUUM;' >> ${LOG_DIR}/cron_vacuum.log 2>&1
CRON

chmod 0644 /etc/cron.d/espn4cc4c
crontab /etc/cron.d/espn4cc4c

# Start cron (Debian slim ships /usr/sbin/cron). Run best-effort.
if command -v cron >/dev/null 2>&1; then
  cron || true
elif [ -x /usr/sbin/cron ]; then
  /usr/sbin/cron || true
else
  echo "[warn] cron binary not found; built-in schedule disabled" >&2
fi

exit 0
