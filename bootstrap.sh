#!/usr/bin/env bash
# ESPN4CC4C bootstrap: build, start, wait for health, first-run assist, sanity
set -Eeuo pipefail

# --- ensure dirs exist (host) ---
mkdir -p data logs out

# --- seed .env if missing ---
if [[ ! -f .env && -f .env.example ]]; then
  cp .env.example .env
fi

# --- load env (quote-safe) ---
if [[ -f ".env" ]]; then
  set -a
  . ./.env
  set +a
fi

# --- derive base URL + timings ---
PORT="${PORT:-8094}"
BASE_URL="${VC_RESOLVER_BASE_URL:-http://127.0.0.1:${PORT}}"
# normalize scheme if user set VC_RESOLVER_BASE_URL without http(s)://
if [[ "$BASE_URL" != http://* && "$BASE_URL" != https://* ]]; then
  BASE_URL="http://$BASE_URL"
fi

HEALTH_URL="${BASE_URL%/}/health"
EPG_URL="${BASE_URL%/}/out/epg.xml"
M3U_URL="${BASE_URL%/}/playlist.m3u"

# delays / tries
BOOT_DELAY="${BOOT_DELAY:-20}"         # seconds to sleep before health loop
READINESS_TRIES="${READINESS_TRIES:-120}"
READINESS_SLEEP="${READINESS_SLEEP:-1}"

echo "== docker compose: stop any previous stack =="
docker compose down --remove-orphans || true

# avoid name conflicts from strays
docker rm -f espn4cc 2>/dev/null || true
docker network rm espn4cc4c_default 2>/dev/null || true

echo "== docker compose: build =="
docker compose build --no-cache

echo "== docker compose: up =="
docker compose up -d

# initial warmup delay
if [[ "$BOOT_DELAY" -gt 0 ]]; then
  echo "== boot delay: sleeping ${BOOT_DELAY}s before health checks =="
  sleep "$BOOT_DELAY"
fi

echo "== readiness wait on ${HEALTH_URL} =="
ok=0
for i in $(seq 1 "$READINESS_TRIES"); do
  code="$(curl -s -o /dev/null -w '%{http_code}' "$HEALTH_URL" || true)"
  if [[ "$code" == "200" ]]; then ok=1; break; fi
  sleep "$READINESS_SLEEP"
done
if [[ "$ok" != "1" ]]; then
  echo "ERROR: resolver not healthy @ $HEALTH_URL" >&2
  docker compose ps
  docker compose logs --no-color | tail -n 200 || true
  exit 1
fi
echo "Resolver healthy."

# --- first-run assist: generate outputs if missing/404 ---
if ! curl -fsS "$EPG_URL" >/dev/null 2>&1 || ! curl -fsS "$M3U_URL" >/devnull 2>&1; then
  echo "== first run: generating plan + outputs via update_schedule.sh =="
  PRE_WAIT=5 ./update_schedule.sh
fi

echo "== sanity checks =="
xml_bytes="$(curl -fsS "$EPG_URL" | wc -c | tr -d ' ' || echo 0)"
m3u_bytes="$(curl -fsS "$M3U_URL" | wc -c | tr -d ' ' || echo 0)"
first_chan_id="$(curl -fsS "$EPG_URL" \
  | grep -oE '<channel[^>]+id="[^"]+"' \
  | head -n1 \
  | sed -E 's/.*id="([^"]+)".*/\1/')"
first_tvg_id="$(curl -fsS "$M3U_URL" \
  | awk '/^#EXTINF:/ {print; exit}' \
  | sed -n 's/.*tvg-id="\([^"]\+\)".*/\1/p')"

printf 'Health: OK\nXMLTV bytes: %s\nM3U bytes: %s\nFirst channel id: %s\nFirst tvg-id: %s\n' \
  "${xml_bytes:-0}" "${m3u_bytes:-0}" "${first_chan_id:-N/A}" "${first_tvg_id:-N/A}"

echo
echo "Add to Channels DVR:"
echo "  * M3U:   ${M3U_URL}"
echo "  * XMLTV: ${EPG_URL}"
