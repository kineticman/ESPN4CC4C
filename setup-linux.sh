#!/usr/bin/env bash
set -Eeuo pipefail

# Detect host IP for health check if not provided
HOST_IP="${HOST_IP:-$(hostname -I | awk '{print $1}')}"
PORT="${PORT:-8094}"

echo "Starting ESPN4CC4C (detached)..."
docker compose up -d

echo "Waiting for health at http://${HOST_IP}:${PORT}/health ..."
until curl -sf "http://${HOST_IP}:${PORT}/health" >/dev/null; do
  echo "  ...waiting"
  sleep 2
done

# Print the most recent refresh summary
LOG="logs/refresh.log"
echo ""
echo "======== Startup Summary ========"
if [[ -f "$LOG" ]]; then
  # Print last summary block between the markers
  awk '/=== ESPN4CC4C Container Refresh Started ===/{p=1} p; /=== Refresh Complete ===/{print; p=0}' "$LOG" | tail -n +1
else
  # Fallback: pull from container logs (last 10m)
  docker logs --since 10m espn4cc4c | sed -n '/=== ESPN4CC4C Container Refresh Started ===/,/=== Refresh Complete ===/p'
fi
echo "================================"
echo ""
echo "EPG:  http://${HOST_IP}:${PORT}/out/epg.xml"
echo "M3U:  http://${HOST_IP}:${PORT}/playlist.m3u"
echo "API:  http://${HOST_IP}:${PORT}/whatson_all"
