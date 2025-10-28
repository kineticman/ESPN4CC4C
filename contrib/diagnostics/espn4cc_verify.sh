#!/usr/bin/env bash
set -euo pipefail
HOST="${1:-192.168.86.72}"; PORT="${2:-8094}"; BASE="http://$HOST:$PORT"
echo "== readiness =="; i=0; until curl -sf "$BASE/health" >/dev/null || [ $i -ge 30 ]; do i=$((i+1)); echo "  waiting ($i/30)"; sleep 1; done
curl -s "$BASE/health" && echo
echo "== m3u (first 12) =="; curl -s "$BASE/playlist.m3u" | sed -n '1,12p'
curl -s "$BASE/playlist.m3u" | grep -Ei 'localhost|127\.0\.0\.1' >/dev/null && echo "✖ localhost found in M3U" || echo "✔ no localhost in M3U"
echo "== xmltv head =="; curl -s "$BASE/epg.xml" | sed -n '1,6p'
echo "== channel probe =="; curl -s -o /dev/null -w "HTTP %{http_code}\n" "$BASE/vc/eplus9?only_live=1"
echo "== cron =="; if docker compose ps espn4cc >/dev/null 2>&1; then docker compose exec espn4cc sh -lc 'crontab -l || true'; fi
