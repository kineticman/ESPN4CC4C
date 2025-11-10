# ESPN4CC4C: Filters Explorer + Ingest Columns + Resolver refinements

## Summary
This PR introduces **filter discovery endpoints** (`/filters`, `/filters/json`), adds richer **ingest columns** for future filtering, wires up an **offline filter pass** (`filter_events.py`), and makes deeplink return **opt-in** across `whatson` APIs. Includes docs and lint/CI cleanups.

## What’s new

### 1) New endpoints
- **GET `/filters`** — Dark-themed HTML summary of available filter values (Networks, Sports, Leagues, Event Types, Packages) with counts and usage tips.
- **GET `/filters/json`** — Same data in JSON (`totals`, `networks`, `sports`, `leagues`, `event_types`) for automation.

### 2) Ingest & schema
- `bin/ingest_watch_graph_all_to_db.py` now writes enriched fields to `events`:
  - `network, network_id, network_short`
  - `league_name, league_id, league_abbr`
  - `sport_id, sport_abbr` (existing `sport` retained)
  - `packages` (JSON array string)
  - `event_type, airing_id, simulcast_airing_id`
- Add/alter is **additive** (safe migration). Script prints `[migration] Adding column: …` on first run.

### 3) Filtering toolkit
- `bin/generate_filter_options.py` — Scans DB and prints available values with counts (and can emit a starter `filters.ini`).
- `bin/filter_events.py` — Applies `filters.ini` to produce decisions in `events_filterable` (creates table if missing).
- Example rules cover **include/exclude** by networks/sports/leagues/types and **require_espn_plus** / **exclude_ppv**.

### 4) Resolver behavior
- `whatson`/`whatson_all` **omit** `deeplink_url` **by default**; opt-in via `?include=deeplink` (or `deeplink=1`).
- `/vc/{lane}/debug` remains for deep inspection.

### 5) Docs & hygiene
- **README updated** with the new endpoints and a practical filtering quick-start.
- Pre-commit/flake8/black/isort fixes; removed backup files and unused vars/imports.

---

## Backward compatibility
- **No breaking DB changes** (columns added only).
- Existing users can pull + rebuild; services continue to function without `filters.ini`.
- Behavior change: `whatson*` no longer returns `deeplink_url` unless requested (`include=deeplink`).

---

## How to test (smoke)

```bash
# Rebuild + start
docker compose build --pull
docker compose up -d

# Wait for health
for i in {1..60}; do curl -fsS "http://<LAN-IP>:8094/health" && break; sleep 1; done; echo

# Core outputs
curl -s "http://<LAN-IP>:8094/channels" | jq '.[0:5]'
curl -s "http://<LAN-IP>:8094/epg.xml" | sed -n '1,8p'
curl -s "http://<LAN-IP>:8094/playlist.m3u" | sed -n '1,8p'

# Filters explorer
curl -s "http://<LAN-IP>:8094/filters" | sed -n '1,40p'
curl -s "http://<LAN-IP>:8094/filters/json" | jq '{totals,networks:.networks[0:5]}'

# whatson / deeplink gating
curl -s "http://<LAN-IP>:8094/whatson/6" | jq .
curl -s "http://<LAN-IP>:8094/whatson/6?include=deeplink" | jq .

# Lane debug
curl -s "http://<LAN-IP>:8094/vc/6/debug" | jq .
```

**Note:** If you trim `curl -i` output with `sed -n '1,10p'`, drain the pipe to avoid code 18:
```bash
curl -sS -i "http://<LAN-IP>:8094/deeplink/6" | { sed -n '1,10p'; cat >/dev/null; }
```

---

## Optional indexes (perf)
```sql
CREATE INDEX IF NOT EXISTS idx_events_filterable ON events_filterable(event_id, is_allowed);
CREATE INDEX IF NOT EXISTS idx_events_start ON events(start_utc);
CREATE INDEX IF NOT EXISTS idx_events_league ON events(league_abbr);
CREATE INDEX IF NOT EXISTS idx_events_sport ON events(sport_abbr);
```

---

## Example `filters.ini`
```ini
[filters]
# Only ESPN+ content
enabled_networks = ESPN+
require_espn_plus = true

# Drop replays
exclude_event_types = OVER

# Or pick pro leagues explicitly (example):
# enabled_leagues = NFL,NBA,NHL,MLS
```

---

## Rollout plan
1. `git pull` → `docker compose build && docker compose up -d`
2. Confirm `/health`, `/filters`, `/filters/json`.
3. (Optional) Generate `filters.ini` and apply via `./update_schedule.sh`.
4. Verify `whatson_all?include=deeplink` behavior in client integrations.

---

## Risks & mitigations
- **Different deeplink behavior**: now opt-in; documented in README and easy to toggle with `include=deeplink`.
- **DB writes**: additive migrations; no data loss; tested with both empty and populated DBs.

---

## Version/tag suggestion
- Propose **v0.2.0-beta1** (feature release: new APIs + filtering groundwork).

## Reviewer checklist
- [ ] `/filters` renders and shows realistic counts
- [ ] `/filters/json` schema matches README example
- [ ] `whatson_all` without/with `include=deeplink` behaves as documented
- [ ] `events` table contains the new columns (spot-check via `PRAGMA table_info(events);`)
- [ ] `events_filterable` exists after running `filter_events.py` and decisions match expectations
