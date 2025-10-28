#!/usr/bin/env bash
set -euo pipefail

# --- always run from repo root ---
SCRIPT_DIR="$(cd -- "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# --- load host-side .env (LAN, PORT, etc.) ---
if [ -f ".env" ]; then
  set -a; . ./.env; set +a
fi

# --- defaults ---
PORT="${PORT:-8094}"
TZ="${TZ:-America/New_York}"
VALID_HOURS="${VALID_HOURS:-72}"
LANES="${LANES:-40}"
ALIGN="${ALIGN:-30}"
MIN_GAP_MINS="${MIN_GAP_MINS:-30}"
VC_RESOLVER_BASE_URL="${VC_RESOLVER_BASE_URL:-http://127.0.0.1:${PORT}}"
LAN="${VC_RESOLVER_BASE_URL#http://}"; LAN="${LAN#https://}"

# --- SANITIZE: never allow /app/* on the host ---
if [[ "${DB:-}" == /app/* ]];   then echo "[FATAL] .env DB is a container path (${DB}). Use host-relative (e.g., ./data/eplus_vc.sqlite3)." >&2; exit 1; fi
if [[ "${OUT:-}" == /app/* ]];  then echo "[FATAL] .env OUT is a container path (${OUT}). Use host-relative (e.g., ./out)." >&2; exit 1; fi
if [[ "${LOGS:-}" == /app/* ]]; then echo "[FATAL] .env LOGS is a container path (${LOGS}). Use host-relative (e.g., ./logs)." >&2; exit 1; fi

# --- host paths (container maps these into /app/*) ---
if [ -z "${DB:-}" ]; then
  HOST_DB="$PWD/data/eplus_vc.sqlite3"
else
  # keep user-provided absolute/relative host paths
  [[ "$DB" = /* ]] && HOST_DB="$DB" || HOST_DB="$PWD/$DB"
fi
HOST_OUT="${OUT:-$PWD/out}"
HOST_LOGS="${LOGS:-$PWD/logs}"
mkdir -p "$(dirname "$HOST_DB")" "$HOST_OUT" "$HOST_LOGS"

echo "== docker compose: build =="
docker compose build --pull

echo "== docker compose: up =="
docker compose up -d

echo "== boot delay: sleeping 20s before health checks =="
sleep 20

echo "== readiness wait on ${VC_RESOLVER_BASE_URL}/health =="
for i in {1..60}; do
  if curl -fsS "${VC_RESOLVER_BASE_URL}/health" >/dev/null; then
    echo "Resolver healthy."
    break
  fi
  sleep 1
done

echo "== first run: DB ensure + migrate (inside container) =="
docker compose exec -T espn4cc bash -lc '
  set -e
  : "${DB:=/app/data/eplus_vc.sqlite3}"
  : "${TZ:=America/New_York}"
  mkdir -p /app/data /app/out /app/logs
  [ -f "$DB" ] || : > "$DB"
  if [ -x /app/bin/db_migrate.py ]; then
    python3 /app/bin/db_migrate.py --db "$DB" || true
  else
    echo "[warn] bin/db_migrate.py missing (container)."
  fi
'

echo "== first run: generating plan + outputs via update_schedule.sh =="
./update_schedule.sh || true

# --- quick sanities (host-side HTTP GETs) ---
curl -fsS "http://${LAN}/out/epg.xml" | wc -l || true
curl -fsS "http://${LAN}/out/playlist.m3u" | wc -l || true
curl -fsS "http://${LAN}/out/epg.xml" | grep -c '<programme ' || true
