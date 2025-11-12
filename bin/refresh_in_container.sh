#!/usr/bin/env bash
set -Eeuo pipefail
mkdir -p /app/logs
# stream to stdout AND persist to /app/logs/refresh.log inside container
# since /app/logs is bind-mounted, hosts will see logs/refresh.log
exec python3 /app/bin/refresh_in_container.py 2>&1 | tee -a /app/logs/refresh.log
