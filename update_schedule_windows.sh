#!/usr/bin/env bash
set -euo pipefail
LAN_IP="${1:-}"
PORT="${2:-8094}"
[[ -z "$LAN_IP" ]] && { echo "Usage: $0 <LAN_IP> [PORT]"; exit 1; }
dc(){ if docker compose version >/dev/null 2>&1; then docker compose "$@"; elif command -v docker-compose >/dev/null 2>&1; then docker-compose "$@"; else echo "[ERR] docker compose not found"; exit 1; fi; }
CExec(){ dc exec -T espn4cc sh -lc "$*"; }
VC_URL="http://${LAN_IP}:${PORT}"
for i in $(seq 1 30); do curl -fsS "${VC_URL}/health" | grep -q '"status"[[:space:]]*:[[:space:]]*"ok"' && break || sleep 2; done
CExec ': "${DB:=/app/data/eplus_vc.sqlite3}"; : "${TZ:=America/New_York}"; mkdir -p /app/data /app/out /app/logs; [ -f "$DB" ] || : > "$DB"; [ -x /app/bin/db_migrate.py ] && python3 /app/bin/db_migrate.py --db "$DB" || true'
CExec ': "${DB:=/app/data/eplus_vc.sqlite3}"; : "${TZ:=America/New_York}"; cnt=$(sqlite3 "$DB" "SELECT COUNT(*) FROM events;" 2>/dev/null || echo 0); if [ "$cnt" -eq 0 ]; then python3 /app/bin/ingest_watch_graph_all_to_db.py --db "$DB" --days 3 --tz "$TZ"; fi'
CExec ': "${DB:=/app/data/eplus_vc.sqlite3}"; : "${VALID_HOURS:=72}"; : "${LANES:=40}"; : "${ALIGN:=30}"; : "${MIN_GAP_MINS:=30}"; : "${TZ:=America/New_York}"; python3 /app/bin/build_plan.py --db "$DB" --valid-hours "$VALID_HOURS" --min-gap-mins "$MIN_GAP_MINS" --align "$ALIGN" --lanes "$LANES" --tz "$TZ"'
CExec ': "${DB:=/app/data/eplus_vc.sqlite3}"; python3 /app/bin/xmltv_from_plan.py --db "$DB" --out /app/out/epg.xml'
CExec ': "${DB:=/app/data/eplus_vc.sqlite3}"; : "${VC_RESOLVER_BASE_URL:='"$VC_URL"'}"; : "${CC_HOST:='"$LAN_IP"'}"; : "${CC_PORT:=5589}"; python3 /app/bin/m3u_from_plan.py --db "$DB" --out /app/out/playlist.m3u --resolver-base "$VC_RESOLVER_BASE_URL" --cc-host "$CC_HOST" --cc-port "$CC_PORT"'
curl -fsS "${VC_URL}/out/epg.xml" | tr -d '\r' | awk 'BEGIN{c=0}/<programme/{c++}END{print "[OK ] programmes="c}'
echo "[OK ] m3u head:"; curl -fsS "${VC_URL}/playlist.m3u" | sed -n '1,6p'
