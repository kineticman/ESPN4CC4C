\
    #!/usr/bin/env bash
    # ESPN4CC4C bootstrap: build, run, first plan, and install in-container auto-refresh
    set -euo pipefail

    # --- Preflight ---
    need() { command -v "$1" >/dev/null 2>&1 || { echo "[FATAL] Missing command: $1" >&2; exit 1; }; }
    need docker
    docker compose version >/dev/null 2>&1 || { echo "[FATAL] Docker Compose v2 not available."; exit 1; }

    SCRIPT_DIR="$(cd -- "$(dirname "$0")" && pwd)"
    cd "$SCRIPT_DIR"

    [[ -f Dockerfile ]] || { echo "[FATAL] Dockerfile not found in $PWD" >&2; exit 1; }
    [[ -f docker-compose.yml ]] || { echo "[FATAL] docker-compose.yml not found in $PWD" >&2; exit 1; }

    # --- Load host .env if present ---
    if [ -f ".env" ]; then
      set -a; . ./.env; set +a
    fi

    # --- Sanity defaults ---
    PORT="${PORT:-8094}"
    TZ="${TZ:-America/New_York}"
    VALID_HOURS="${VALID_HOURS:-72}"
    LANES="${LANES:-40}"
    ALIGN="${ALIGN:-30}"
    MIN_GAP_MINS="${MIN_GAP_MINS:-30}"
    VC_RESOLVER_BASE_URL="${VC_RESOLVER_BASE_URL:-http://127.0.0.1:${PORT}}"
    CC_HOST="${CC_HOST:-127.0.0.1}"
    CC_PORT="${CC_PORT:-5589}"

    # --- Host path policy: NEVER use /app/* on host ---
    for var in DB OUT LOGS; do
      val="${!var:-}"
      if [[ "${val:-}" =~ ^/app/ ]]; then
        echo "[FATAL] .env $var is a container path (${val}). Use host-relative (e.g., ./data, ./out, ./logs)." >&2
        exit 1
      fi
    done

    # Resolve host-side paths and ensure they exist
    HOST_DB="${DB:-$PWD/data/eplus_vc.sqlite3}"; [[ "$HOST_DB" = /* ]] || HOST_DB="$PWD/${HOST_DB#./}"
    HOST_OUT="${OUT:-$PWD/out}";               [[ "$HOST_OUT" = /* ]] || HOST_OUT="$PWD/${HOST_OUT#./}"
    HOST_LOGS="${LOGS:-$PWD/logs}";            [[ "$HOST_LOGS" = /* ]] || HOST_LOGS="$PWD/${HOST_LOGS#./}"
    mkdir -p "$(dirname "$HOST_DB")" "$HOST_OUT" "$HOST_LOGS"

    echo "== docker compose: build =="
    docker compose build --pull

    echo "== docker compose: up =="
    docker compose up -d

    echo "== readiness wait on ${VC_RESOLVER_BASE_URL}/health =="
    for i in {1..90}; do
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
      fi
    '

    echo "== first run: generate plan + epg/m3u (inline) =="
    docker compose exec -T espn4cc bash -lc '
      set -e
      DB="${DB:-/app/data/eplus_vc.sqlite3}"
      TZ="${TZ:-America/New_York}"
      VALID_HOURS="${VALID_HOURS:-72}"
      MIN_GAP_MINS="${MIN_GAP_MINS:-30}"
      ALIGN="${ALIGN:-30}"
      LANES="${LANES:-40}"
      VC_RESOLVER_BASE_URL="${VC_RESOLVER_BASE_URL:-http://127.0.0.1:8094}"
      CC_HOST="${CC_HOST:-127.0.0.1}"
      CC_PORT="${CC_PORT:-5589}"
      # Seed if empty
      cnt=$(sqlite3 "$DB" "SELECT COUNT(*) FROM events;" 2>/dev/null || echo 0)
      if [ "$cnt" -eq 0 ]; then
        python3 /app/bin/ingest_watch_graph_all_to_db.py --db "$DB" --days 3 --tz "$TZ" || true
      fi
      python3 /app/bin/build_plan.py --db "$DB" --valid-hours "$VALID_HOURS" --min-gap-mins "$MIN_GAP_MINS" --align "$ALIGN" --lanes "$LANES" --tz "$TZ" || true
      python3 /app/bin/xmltv_from_plan.py --db "$DB" --out /app/out/epg.xml || true
      python3 /app/bin/m3u_from_plan.py   --db "$DB" --out /app/out/playlist.m3u --resolver-base "$VC_RESOLVER_BASE_URL" --cc-host "$CC_HOST" --cc-port "$CC_PORT" || true
    '

