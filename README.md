# ESPN4CC4C (ESPN Clean v2)

Virtual-channel pipeline that ingests ESPN Watch Graph airings, packs them into 40 “EPlus” lanes, and publishes an XMLTV EPG, M3U playlist, and live FastAPI resolver that redirects each lane to its best available stream.

---

## TL;DR

- **Ingest → Plan → Publish** automatically on a systemd schedule  
- Placeholders auto-align to `:00` / `:30` and show **“Stand By”**  
- XMLTV back-dates programme start to the real event start  
- Resolver serves:  
  `/epg.xml`, `/playlist.m3u`, `/vc/<lane>` (302 redirect), `/vc/<lane>/debug`

---

## Quick start

```bash
git clone https://github.com/kineticman/ESPN4CC4C.git ~/Projects/ESPN4CC
cd ~/Projects/ESPN4CC
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt

# 1) create initial DB (seed events)
python3 bin/ingest_watch_graph_all_to_db.py --db data/eplus_vc.sqlite3 --days 1 --tz America/New_York

# 2) build a plan (48–72 hours is typical)
python3 bin/build_plan.py --db data/eplus_vc.sqlite3 --valid-hours 72 --tz America/New_York

# 3) compute your LAN resolver base (avoid 127.0.0.1 in URLs)
H=$(hostname -I | awk '{print $1}')
BASE="http://$H:8094"

# 4) generate XMLTV and M3U using the LAN base
python3 bin/xmltv_from_plan.py   --db data/eplus_vc.sqlite3   --out out/epg.xml   --resolver-base "$BASE"

# IMPORTANT: write the SAME file the resolver serves at /playlist.m3u.
# By default the resolver serves out/virtual_channels.m3u unless VC_M3U_PATH is set.
python3 bin/m3u_from_plan.py   --db data/eplus_vc.sqlite3   --out out/virtual_channels.m3u   --resolver-base "$BASE"   --cc-host 192.168.86.72   --cc-port 5589
```

### Start resolver (dev)

```bash
uvicorn vc_resolver.app:app --host 0.0.0.0 --port 8094
```

| Endpoint | Purpose |
|-----------|----------|
| `/health` | simple ping |
| `/epg.xml` | current XMLTV |
| `/playlist.m3u` | M3U pointing to lanes |
| `/vc/<lane>` | 302 redirect to stream |
| `/vc/<lane>/debug` | JSON debug for lane |

---

## Notes on resolver base & playlist path

- The writers accept `--resolver-base`; use your LAN IP (e.g., `http://192.168.1.50:8094`) to avoid `127.0.0.1` in client URLs.
- The resolver’s `/playlist.m3u` endpoint serves **`out/virtual_channels.m3u`** by default. If you prefer to keep writing `out/playlist.m3u`, either:
  - set the environment for the resolver process:  
    ```bash
    export VC_M3U_PATH="$PWD/out/playlist.m3u"
    ```
  - **or** change the `--out` path for `m3u_from_plan.py` to `out/virtual_channels.m3u` (recommended).

- Writers also honor environment fallbacks when `--resolver-base` isn’t passed:
  - `VC_RESOLVER_BASE_URL` (preferred), then `VC_RESOLVER_ORIGIN`.

Example:
```bash
export VC_RESOLVER_BASE_URL="$BASE"
```

---

## Components

| File | Role |
|------|------|
| `bin/ingest_watch_graph_all_to_db.py` | Fetch ESPN Watch Graph → SQLite (`events`, `feeds`) |
| `bin/build_plan.py` | Pack events into 40 lanes, insert placeholders |
| `bin/xmltv_from_plan.py` | Generate XMLTV |
| `bin/m3u_from_plan.py` | Generate M3U |
| `vc_resolver/app.py` | FastAPI resolver |
| `tools/vc_diag.py` | Self-check tool for services, DB, XMLTV parity |

---

## Data model (SQLite)

- **events** (id, start_utc, stop_utc, title, sport, subtitle, summary, image)  
- **feeds** (id, event_id → events.id, url, is_primary)  
- **channel** (id, chno, name, group_name, active)  
- **plan_run** (id, generated_at_utc, valid_from_utc, valid_to_utc, checksum, note)  
- **plan_slot** (plan_id → plan_run.id, channel_id, event_id, start_utc, end_utc, kind, placeholder_reason, preferred_feed_id)  
- **plan_meta** (key, value) – stores active plan pointer  

---

## Configuration

Use environment variables or `.env.plan` (env wins). Example:

```ini
DB=/home/brad/Projects/ESPN4CC/data/eplus_vc.sqlite3
OUT=/home/brad/Projects/ESPN4CC/out/epg.xml
# Prefer LAN base; used by writers if --resolver-base is omitted
VC_RESOLVER_BASE_URL=http://192.168.1.50:8094
VC_RESOLVER_ORIGIN=http://192.168.1.50:8094
TZ=America/New_York
VALID_HOURS=72
LANES=40
ALIGN=30
MIN_GAP_MINS=30
PORT=8094
# If you want the resolver to serve a different M3U path:
# VC_M3U_PATH=/home/brad/Projects/ESPN4CC/out/playlist.m3u
```

---

## Systemd install quickstart

The repo ships with templated units under `contrib/systemd/` **and** a `Makefile`.

### Option A — Makefile (recommended)

```bash
make systemd-install USER=$USER PROJECT_DIR=$PWD
make systemd-status USER=$USER
make plan-run USER=$USER
make resolver-restart USER=$USER
make diag LANE=eplus11 QUIET=1
```

### Option B — manual install

```bash
PROJECT_DIR=$PWD
sudo install -Dm0644 contrib/systemd/vc-resolver-v2.service /etc/systemd/system/vc-resolver-v2@.service
sudo install -Dm0644 contrib/systemd/vc-plan.service       /etc/systemd/system/vc-plan@.service
sudo install -Dm0644 contrib/systemd/vc-plan.timer         /etc/systemd/system/vc-plan@.timer
sudo sed -i "s|\${PROJECT_DIR}|$PROJECT_DIR|g" /etc/systemd/system/vc-resolver-v2@.service
sudo sed -i "s|\${PROJECT_DIR}|$PROJECT_DIR|g" /etc/systemd/system/vc-plan@.service
sudo systemctl daemon-reload
sudo systemctl enable --now vc-resolver-v2@$USER.service
sudo systemctl enable --now vc-plan@$USER.timer
```

➡ See [`contrib/systemd/README.md`](contrib/systemd/README.md) for full details.

---

## Diagnostics

```bash
python3 tools/vc_diag.py --lane eplus11 --quiet-errors
```

Output summary includes:
- service status
- resolver endpoint health
- DB vs XMLTV programme & channel counts
- current slot and feeds
- fleet placeholder ratio  
*(all ✅ when healthy)*

---

## Troubleshooting

- **Module not found** → ensure `.venv/bin/python` used in unit  
- **“unrecognized arguments”** → upgrade scripts (`--tz` removed for xmltv)  
- **Resolver 500** → check `/vc/<lane>/debug` and DB path in `.env.plan`  
- **NAMESPACE errors** → verify `ReadWritePaths=${PROJECT_DIR}` in service  
- **Playlist shows 127.0.0.1** → pass `--resolver-base "$BASE"` (LAN) to writers, or set `VC_RESOLVER_BASE_URL`; ensure the writer’s `--out` matches what the resolver serves.
 
---

## License
MIT (or your preferred license)
