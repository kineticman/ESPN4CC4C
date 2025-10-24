# ESPN Clean v2
---
# ESPN Clean v2 — Runtime Notes (Oct 2025)

## Overview
- **Resolver service (FastAPI, :8094)** decides where each channel should go:
  - Live ESPN+ event → 302 to ESPN player URL.
  - No live event → 302 to your **slate** (idle fallback).
- **M3U is static** and always points to the resolver, e.g.  
  `chrome://192.168.86.72:5589/stream?url=http://192.168.86.72:8094/vc/eplus1`
- **XMLTV** is generated from the DB plan. Placeholders show **“Stand By”**.

## What we changed tonight
- Switched all internal URLs to **LAN IP** (no 127.0.0.1).
- Resolver default behavior: if nothing live, **redirect to slate**.
- **M3U** no longer includes `only_live=1` (the server decides).
- **XMLTV**:
  - Placeholder title → **“Stand By”** (customizable via env).
  - Every programme includes a `Sports` category.
  - Real sports events also get: **`Live`** and **`Sports Event`** categories.
  - Non-sports shows (e.g., SportsCenter) do **not** get `Live/Sports Event`.
- Added health, debug, and lane endpoints; tightened unit/service config.

## Config (env)
These can be set in your systemd unit or shell before generating:
- `VC_PLACEHOLDER_TITLE` (default: `Stand By`)
- `VC_PLACEHOLDER_SUBTITLE` (default: empty)
- `VC_PLACEHOLDER_SUMMARY` (default: `No live event scheduled`)

## Commands I use
**Build plan → XML → M3U**
- `python3 bin/build_plan.py --db data/eplus_vc.sqlite3 --valid-hours 72 --tz America/New_York`
- `python3 bin/xmltv_from_plan.py --db data/eplus_vc.sqlite3 --out out/virtual_channels.xml`
- `python3 bin/m3u_from_plan.py   --db data/eplus_vc.sqlite3 --out out/virtual_channels.m3u`

**Quick checks**
- `xmllint --noout out/virtual_channels.xml` (well-formed)
- `grep -c '<programme ' out/virtual_channels.xml` (count programmes)
- `curl -i "http://192.168.86.72:8094/vc/eplus1"` (302 to live or slate)
- `curl -s "http://192.168.86.72:8094/vc/eplus1/debug" | jq .` (active slot info)

## Resolver service
- Unit: `/etc/systemd/system/vc-resolver-v2.service`
- Key env:
  - `VC_DB=/home/brad/Projects/ESPN_clean_v2/data/eplus_vc.sqlite3`
  - `VC_RESOLVER_ORIGIN=http://192.168.86.72:8094`
  - `VC_CC_BASE=chrome://192.168.86.72:5589/stream?url=`
  - `VC_LOG_PATH=/var/log/espnvc-v2/vc_resolver.jsonl`
- Restart + health:
  - `sudo systemctl restart vc-resolver-v2`
  - `curl -s http://192.168.86.72:8094/health | jq .`

## Troubleshooting
- Resolver 500 + “unable to open database file” → fix permissions on:
  - `/home/brad/Projects/ESPN_clean_v2/data`, `/var/log/espnvc-v2`
- XML shows only placeholders → re-ingest and rebuild plan:
  - `python3 bin/ingest_watch_graph_all_to_db.py --db data/eplus_vc.sqlite3 --days 1 --tz America/New_York`
  - Then rebuild plan and XML (see above).

