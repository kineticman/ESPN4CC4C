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

# create initial DB
python3 bin/ingest_watch_graph_all_to_db.py --db data/eplus_vc.sqlite3 --days 1 --tz America/New_York
python3 bin/build_plan.py --db data/eplus_vc.sqlite3 --valid-hours 72 --tz America/New_York
python3 bin/xmltv_from_plan.py --db data/eplus_vc.sqlite3 --out out/epg.xml
python3 bin/m3u_from_plan.py   --db data/eplus_vc.sqlite3 --out out/playlist.m3u
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

Environment variables or `.env.plan` (env wins). Example:

```ini
DB=/home/brad/Projects/ESPN4CC/data/eplus_vc.sqlite3
OUT=/home/brad/Projects/ESPN4CC/out/epg.xml
RESOLVER_BASE=http://127.0.0.1:8094
TZ=America/New_York
VALID_HOURS=72
LANES=40
ALIGN=30
MIN_GAP_MINS=30
PORT=8094
```

---

## Systemd install quickstart

The repo ships with templated units under `contrib/systemd/` **and** a `Makefile`.

### Option A — Makefile (recommended)

```bash
make systemd-install USER=brad PROJECT_DIR=/home/brad/Projects/ESPN4CC
make systemd-status USER=brad
make plan-run USER=brad
make resolver-restart USER=brad
make diag LANE=eplus11 QUIET=1
```

### Option B — manual install

```bash
PROJECT_DIR=/home/brad/Projects/ESPN4CC
sudo install -Dm0644 contrib/systemd/vc-resolver-v2.service /etc/systemd/system/vc-resolver-v2@.service
sudo install -Dm0644 contrib/systemd/vc-plan.service       /etc/systemd/system/vc-plan@.service
sudo install -Dm0644 contrib/systemd/vc-plan.timer         /etc/systemd/system/vc-plan@.timer
sudo sed -i "s|\${PROJECT_DIR}|$PROJECT_DIR|g" /etc/systemd/system/vc-resolver-v2@.service
sudo sed -i "s|\${PROJECT_DIR}|$PROJECT_DIR|g" /etc/systemd/system/vc-plan@.service
sudo systemctl daemon-reload
sudo systemctl enable --now vc-resolver-v2@brad.service
sudo systemctl enable --now vc-plan@brad.timer
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

---

## License
MIT (or your preferred license)
