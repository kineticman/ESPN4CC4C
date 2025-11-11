#!/usr/bin/env bash
# ESPN4CC verify helper
# Usage:
#   contrib/diagnostics/espn4cc_verify.sh [HOST] [PORT]
# Behavior:
#   - If VC_RESOLVER_BASE_URL is set, it wins (e.g., http://192.168.1.100:8094)
#   - Else use HOST/PORT args
#   - Else default to primary LAN IP + 8094
set -euo pipefail

# --- derive BASE ---
parse_from_env() {
  # expects VC_RESOLVER_BASE_URL like http://x.x.x.x:port
  local base="${VC_RESOLVER_BASE_URL:-}"
  if [[ -n "$base" ]]; then
    # strip any trailing path
    base="${base%%/}"
    echo "$base"
    return 0
  fi
  return 1
}

BASE=""
if ! BASE="$(parse_from_env)"; then
  HOST="${1:-}"
  PORT="${2:-}"
  if [[ -z "${HOST}" ]]; then
    HOST="$(hostname -I | awk '{print $1}')"
  fi
  if [[ -z "${PORT}" ]]; then
    PORT="8094"
  fi
  BASE="http://${HOST}:${PORT}"
fi

echo "== verify against ${BASE} =="

# --- readiness loop ---
echo "== readiness =="
i=0
until curl -sf "${BASE}/health" >/dev/null || [[ $i -ge 30 ]]; do
  i=$((i+1))
  echo "  waiting ($i/30)"
  sleep 1
done
curl -s "${BASE}/health" && echo

# --- M3U first lines + sanity (no localhost) ---
echo "== m3u (first 12) =="
curl -s "${BASE}/playlist.m3u" | sed -n '1,12p' || true
if curl -s "${BASE}/playlist.m3u" | grep -Ei 'localhost|127\.0\.0\.1' >/dev/null; then
  echo "✖ localhost found in M3U"
  exit 2
else
  echo "✔ no localhost in M3U"
fi

# --- XMLTV head ---
echo "== xmltv head =="
curl -s "${BASE}/epg.xml" | sed -n '1,6p' || true

# --- channel probe (only_live) ---
echo "== channel probe (eplus9 only_live) =="
curl -s -o /dev/null -w "HTTP %{http_code}\n" "${BASE}/vc/eplus9?only_live=1" || true

# --- cron inside container (if present) ---
echo "== cron (inside espn4cc container if present) =="
if docker compose ps espn4cc >/dev/null 2>&1; then
  docker compose exec espn4cc sh -lc 'crontab -l || true'
else
  echo "(docker compose service espn4cc not detected)"
fi

# --- host consistency check (BASE vs M3U/EPG) ---
echo "== host consistency check =="
m3u_host="$(curl -s "${BASE}/playlist.m3u" | grep -m1 -Eo 'http://[0-9.]+:8094' || true)"
epg_host="$(curl -s "${BASE}/epg.xml"      | grep -m1 -Eo 'http://[0-9.]+:8094' || true)"
base_host="$(echo "${BASE}" | grep -Eo 'http://[0-9.]+:8094')"
if [[ -z "${base_host}" ]]; then
  # if BASE is not an http://IP:PORT (e.g., hostname), skip strict compare and just report
  echo "(note) BASE not in http://IP:PORT form; reported BASE=${BASE}"
else
  if [[ "$m3u_host" != "$base_host" || "$epg_host" != "$base_host" ]]; then
    echo "✖ host mismatch: BASE=${base_host} M3U=${m3u_host:-<none>} EPG=${epg_host:-<none>}"
    exit 3
  else
    echo "✔ hosts consistent (${base_host})"
  fi
fi

# --- lane count check (optional; requires LANES in env) ---
if [[ -n "${LANES:-}" ]]; then
  echo "== lane count check =="
  m3u_count="$(curl -s "${BASE}/playlist.m3u" | grep -c '^#EXTINF' || true)"
  if [[ -z "${m3u_count}" ]]; then
    echo "(warn) could not count lanes from M3U"
  elif [[ "${m3u_count}" -ne "${LANES}" ]]; then
    echo "✖ lane count mismatch: M3U=${m3u_count} expected=${LANES}"
    exit 4
  else
    echo "✔ lane count OK (${LANES})"
  fi
fi
