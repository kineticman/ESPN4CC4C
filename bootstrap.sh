#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

mkdir -p data logs out
[[ -f .env ]] || cp -n .env.example .env

# Write/ensure your LAN resolver base (edit as needed)
if ! grep -q '^VC_RESOLVER_BASE_URL=' .env; then
  echo 'VC_RESOLVER_BASE_URL=http://192.168.86.72:8094' >> .env
fi

# Bring up container
if command -v docker compose >/dev/null 2>&1; then
  docker compose up -d
else
  docker-compose up -d
fi

# First-run nudge (creates DB, builds plan, writes outputs)
CID=$(docker ps --filter "name=espn4cc" --format '{{.ID}}')
docker exec -it "$CID" /app/update_schedule.sh || true

echo "Done. Test:"
echo "  EPG: http://<host>:8094/out/epg.xml"
echo "  M3U: http://<host>:8094/playlist.m3u"
