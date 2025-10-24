#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

DB="data/eplus_vc.sqlite3"
TZ="America/New_York"
RESOLVER_BASE="http://192.168.86.72:8094"
CC_HOST="192.168.86.72"
CC_PORT="5589"

# 1) Ingest today + tomorrow (adjust days as you like)
./.venv/bin/python bin/ingest_watch_graph_all_to_db.py --db "$DB" --days 2 --tz "$TZ"

# 2) Build plan + publish
./.venv/bin/python bin/build_plan.py      --db "$DB" --valid-hours 72 --tz "$TZ" --note "pipeline hourly"
./.venv/bin/python bin/xmltv_from_plan.py --db "$DB" --out out/virtual_channels.xml --tz "$TZ"
./.venv/bin/python bin/m3u_from_plan.py   --db "$DB" --out out/virtual_channels.m3u \
  --resolver-base "$RESOLVER_BASE" --cc-host "$CC_HOST" --cc-port "$CC_PORT" --only-live
