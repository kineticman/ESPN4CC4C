#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

echo "== Applying v2.0 schema =="
sqlite3 data/eplus_vc.sqlite3 < sql/plan_schema_v2.sql

echo "== Building plan (72h) =="
python3 bin/build_plan.py --db data/eplus_vc.sqlite3 --valid-hours 72 --tz America/New_York --note "v2.0 manual run"

echo "== Rendering XMLTV =="
python3 bin/xmltv_from_plan.py --db data/eplus_vc.sqlite3 --out out/virtual_channels.xml --tz America/New_York

echo "== Rendering M3U =="
python3 bin/m3u_from_plan.py --db data/eplus_vc.sqlite3 --out out/virtual_channels.m3u --resolver-base http://192.168.86.72:8093 --cc-host 192.168.86.72 --cc-port 5589 --only-live

echo "All done. Files in ./out"
