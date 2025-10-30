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
: "${ENABLE_CRON:=1}"   # set to 0 to disable in-container scheduling

# --- ensure app dirs ---
mkdir -p /app/data /app/out /app/logs

# --- timezone ---
if [ -w /etc/localtime ] && [ -w /etc/timezone ] && [ -n "${TZ}" ]; then
  ln -sf "/usr/share/zoneinfo/${TZ}" /etc/localtime || true
  echo "${TZ}" > /etc/timezone || true
fi

# --- in-container cron (self-refresh) ---
if [ "${ENABLE_CRON}" = "1" ] && command -v cron >/dev/null 2>&1; then
  # If a packaged cron file exists, use it; otherwise install a sane default (daily 02:00)
  if [ -f /etc/cron.d/espn4cc ]; then
    chmod 0644 /etc/cron.d/espn4cc || true
    crontab /etc/cron.d/espn4cc || true
  else
    # default schedule if none was baked into the image
    {
      echo 'SHELL=/bin/bash'
      echo 'PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin'
      echo '0 2 * * * root /app/bin/refresh_in_container.sh >> /app/logs/schedule.log 2>&1'
      echo "17 3 * * 0 root sqlite3 /app/data/eplus_vc.sqlite3 'VACUUM;' >> /app/logs/schedule.log 2>&1"
    } > /etc/cron.d/espn4cc
    chmod 0644 /etc/cron.d/espn4cc || true
    crontab /etc/cron.d/espn4cc || true
  fi

  echo "[entrypoint] starting cron..."
  /usr/sbin/cron || true
else
  echo "[entrypoint] cron disabled or not available; ENABLE_CRON=${ENABLE_CRON}"
fi

# --- run API ---
exec python3 -m uvicorn bin.vc_resolver:app --host 0.0.0.0 --port "${PORT}"
