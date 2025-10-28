#!/usr/bin/env bash
set -euo pipefail

# -- run from repo root --
SCRIPT_DIR="$(cd -- "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# -- load .env for PORT and VC_RESOLVER_BASE_URL, fallbacks safe --
if [[ -f ./.env ]]; then
  set -a; . ./.env; set +a
fi
PORT="${PORT:-8094}"
VC_RESOLVER_BASE_URL="${VC_RESOLVER_BASE_URL:-http://127.0.0.1:${PORT}}"

# -- build & up --
echo "== docker compose: build =="
docker compose build
echo "== docker compose: up =="
docker compose up -d

# -- boot delay + readiness wait --
BOOT_DELAY="${BOOT_DELAY:-20}"
echo "== boot delay: sleeping ${BOOT_DELAY}s before health checks =="
sleep "$BOOT_DELAY"

HEALTH_URL="${VC_RESOLVER_BASE_URL%/}/health"
echo "== readiness wait on ${HEALTH_URL} =="
for i in {1..30}; do
  if curl -fsS "$HEALTH_URL" >/dev/null; then
    echo "Resolver healthy."
    break
  fi
  sleep 2
  if [[ $i -eq 30 ]]; then
    echo "ERROR: Resolver failed to report healthy at ${HEALTH_URL}" >&2
    exit 1
  fi
done

# -- first-run refresh via host-side script (guarantees migration/ingest/build/emit) --
echo "== first run: generating plan + outputs via update_schedule.sh =="
./update_schedule.sh

