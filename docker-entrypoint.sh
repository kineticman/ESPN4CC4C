#!/usr/bin/env bash
set -euo pipefail

# --- container-only guard ---
if [ ! -f "/.dockerenv" ] && [ "${RUNNING_IN_CONTAINER:-}" != "1" ]; then
  echo "[FATAL] docker-entrypoint.sh is container-only. Do not run this on the host." >&2
  exit 1
fi

# --- env + defaults (container scope) ---
[ -f "/app/.env" ] && set -a && . /app/.env && set +a
: "${PORT:=8094}"
: "${TZ:=America/New_York}"
: "${SCHEDULE_HOURS:=6}"

# --- ensure app dirs ---
mkdir -p /app/data /app/out /app/logs

# --- timezone + cron only if we actually have perms (root images) ---
if [ "$(id -u)" = "0" ]; then
  # time
  if [ -w /etc/localtime ] && [ -w /etc/timezone ]; then
    ln -sf "/usr/share/zoneinfo/$TZ" /etc/localtime || true
    echo "$TZ" > /etc/timezone || true
  fi

  # cron
  if [ -d /var/spool/cron/crontabs ] && [ -w /var/spool/cron/crontabs ]; then
    {
      echo "0 */${SCHEDULE_HOURS} * * * /app/update_schedule.sh >> /app/logs/schedule.log 2>&1"
      echo "17 3 * * 0 sqlite3 /app/data/eplus_vc.sqlite3 'VACUUM;'"
    } > /var/spool/cron/crontabs/root || true

    command -v cron >/dev/null 2>&1 && cron || true
  fi
fi

# --- run API ---
exec python3 -m uvicorn bin.vc_resolver:app --host 0.0.0.0 --port "$PORT"
