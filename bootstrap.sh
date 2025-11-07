#!/usr/bin/env bash
GIT_REF="${GIT_REF:-v3.91}"
set -euo pipefail

# --- Always run from repo root ---
SCRIPT_DIR="$(cd -- "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# --- Preflight: required commands & files ---
need() { command -v "$1" >/dev/null 2>&1 || { echo "[FATAL] Missing command: $1" >&2; exit 1; }; }
need docker
if ! docker compose version >/dev/null 2>&1; then
  echo "[FATAL] Docker Compose v2 not available. Update Docker Desktop." >&2
  exit 1
fi
[[ -f Dockerfile ]] || { echo "[FATAL] Dockerfile not found in $PWD" >&2; exit 1; }
[[ -f docker-compose.yml ]] || { echo "[FATAL] docker-compose.yml not found in $PWD" >&2; exit 1; }
[[ -f docker-entrypoint.sh ]] || { echo "[FATAL] docker-entrypoint.sh missing at repo root (did cleanup move/delete it?)" >&2; exit 1; }

# --- Load host-side .env (LAN, PORT, etc.) ---
if [ -f ".env" ]; then
  set -a; . ./.env; set +a
fi

# --- Defaults ---
PORT="${PORT:-8094}"
TZ="${TZ:-America/New_York}"
VALID_HOURS="${VALID_HOURS:-72}"
LANES="${LANES:-40}"
ALIGN="${ALIGN:-30}"
MIN_GAP_MINS="${MIN_GAP_MINS:-30}"
VC_RESOLVER_BASE_URL="${VC_RESOLVER_BASE_URL:-http://127.0.0.1:${PORT}}"
LAN="${VC_RESOLVER_BASE_URL#http://}"; LAN="${LAN#https://}"

# --- Host path mapping (NEVER use /app on host) ---
if [[ "${DB:-}" =~ ^/app/ ]];  then echo "[FATAL] .env DB is a container path (${DB}). Use host-relative (e.g., ./data/eplus_vc.sqlite3)." >&2; exit 1; fi
if [[ "${OUT:-}" =~ ^/app/ ]]; then echo "[FATAL] .env OUT is a container path (${OUT}). Use host-relative (e.g., ./out)." >&2; exit 1; fi
if [[ "${LOGS:-}" =~ ^/app/ ]]; then echo "[FATAL] .env LOGS is a container path (${LOGS}). Use host-relative (e.g., ./logs)." >&2; exit 1; fi

# Resolve host-side paths (mkdir only on host paths)
HOST_DB="${DB:-$PWD/data/eplus_vc.sqlite3}"
[[ "$HOST_DB" = /* ]] || HOST_DB="$PWD/${HOST_DB#./}"
HOST_OUT="${OUT:-$PWD/out}"
[[ "$HOST_OUT" = /* ]] || HOST_OUT="$PWD/${HOST_OUT#./}"
HOST_LOGS="${LOGS:-$PWD/logs}"
[[ "$HOST_LOGS" = /* ]] || HOST_LOGS="$PWD/${HOST_LOGS#./}"

mkdir -p "$(dirname "$HOST_DB")" "$HOST_OUT" "$HOST_LOGS"

echo "== docker compose: build =="
docker compose build --pull

echo "== docker compose: up =="
docker compose up -d

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

echo "== first run: generating plan + outputs (inline) == "
docker compose exec -T espn4cc bash -lc '
  set -e
  DB="${DB:-/app/data/eplus_vc.sqlite3}"
  python3 /app/bin/ingest_watch_graph_all_to_db.py --db "$DB" --days "${DAYS:-3}" || true
  python3 /app/bin/build_plan.py --db "$DB" --valid-hours "${VALID_HOURS:-72}" --min-gap-mins "${MIN_GAP_MINS:-30}" --align 30 || true
  python3 /app/bin/xmltv_from_plan.py --db "$DB" --out /app/out/epg.xml || true
  python3 /app/bin/m3u_from_plan.py --db "$DB" --out /app/out/playlist.m3u --resolver-base "${VC_RESOLVER_BASE_URL}" --cc-host "${CC_HOST:-127.0.0.1}" --cc-port "${CC_PORT:-8089}" || true
'

# ---------- Final tests & summary ----------
echo ""
echo "== Re-check XMLTV (counting programmes) =="
PROG_COUNT=$(curl -fsS "${VC_RESOLVER_BASE_URL}/out/epg.xml" 2>/dev/null | grep -c '<programme' || echo "0")
echo "✓ ${PROG_COUNT} programmes found"

echo ""
echo "== Re-check M3U (preview first 600 chars) =="
curl -fsS "${VC_RESOLVER_BASE_URL}/out/playlist.m3u" 2>/dev/null | head -c 600 || echo "[warn] Could not fetch M3U"

echo ""
echo "========================================"
echo "✓ DONE"
echo "Health   : ${VC_RESOLVER_BASE_URL}/health"
echo "XMLTV    : ${VC_RESOLVER_BASE_URL}/out/epg.xml"
echo "M3U      : ${VC_RESOLVER_BASE_URL}/out/playlist.m3u"
echo "========================================"

# Provenance
echo ""
echo "[info] git describe: $(git describe --tags --always --dirty 2>/dev/null || echo n/a)"
