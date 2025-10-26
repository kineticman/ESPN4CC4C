# ESPN Clean v2

Virtual-channel pipeline that ingests ESPN Watch Graph airings, packs them into 40 “EPlus” lanes, and publishes an XMLTV EPG, M3U playlist, and a live resolver (FastAPI) that redirects each lane to its best available stream.

## TL;DR
- **Ingest → Plan → Publish** on a schedule (systemd timers).
- **Placeholders** auto-align to `:00` / `:30` and are titled **Stand By**.
- **XMLTV** backdates programme start to true event start (so progress bars make sense).
- **Resolver** serves `epg.xml`, `playlist.m3u`, `/vc/<lane>` (302 to stream), and `/vc/<lane>/debug`.

---

## Quick start

```bash
git clone https://github.com/kineticman/ESPN4CC4C.git ESPN_clean_v2
cd ESPN_clean_v2
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cp config.ini.sample config.ini   # edit as needed
```

Initialize the DB (tables will be created on first ingest):
```bash
python3 bin/ingest_watch_graph_all_to_db.py --db data/eplus_vc.sqlite3 --days 1 --tz America/New_York
python3 bin/build_plan.py --db data/eplus_vc.sqlite3 --valid-hours 72 --tz America/New_York
python3 bin/xmltv_from_plan.py --db data/eplus_vc.sqlite3 --out out/epg.xml
python3 bin/m3u_from_plan.py  --db data/eplus_vc.sqlite3 --out out/playlist.m3u
```

Start the resolver (dev):
```bash
uvicorn bin.vc_resolver:app --host 0.0.0.0 --port 8094
# Health:        http://HOST:8094/health
# EPG:           http://HOST:8094/epg.xml
# Playlist:      http://HOST:8094/playlist.m3u
# Live redirect: http://HOST:8094/vc/eplus11
# Debug:         http://HOST:8094/vc/eplus11/debug
```

---

## What’s in here

### Components
- `bin/ingest_watch_graph_all_to_db.py`  
  Pulls ESPN Watch Graph airings → stores in `events` + `feeds`.
- `bin/build_plan.py`  
  Packs events greedily across lanes, inserts placeholders, writes `plan_run` + `plan_slot`.
- `bin/xmltv_from_plan.py`  
  Renders XMLTV from latest plan. Placeholders use `Stand By`. Event titles/categories preserved. `desc` includes short code + sport + title.
- `bin/m3u_from_plan.py`  
  Renders M3U pointing each lane at resolver `/vc/<lane>`.
- `bin/vc_resolver.py` (FastAPI)  
  - `/health`  
  - `/epg.xml` → `out/virtual_channels.xml`  
  - `/playlist.m3u` → `out/virtual_channels.m3u`  
  - `/vc/<lane>` → 302 to best event feed (or 404/204/Slate)  
  - `/vc/<lane>/debug` → JSON (slot/feed/now)

### Data model (SQLite)
- `events(id, start_utc, stop_utc, title, sport, subtitle, summary, image)`
- `feeds(id, event_id→events.id, url, is_primary)`
- `channel(id, chno, name, group_name, active)`
- `plan_run(id, generated_at_utc, valid_from_utc, valid_to_utc, source_version, note, checksum)`
- `plan_slot(plan_id→plan_run.id, channel_id, event_id, start_utc, end_utc, kind, placeholder_reason, preferred_feed_id)`
- `plan_meta(key, value)` (stores `active_plan_id` pointer)

---

## Configuration

All knobs can be set by **env** or **config.ini** (with env taking precedence). See `config.ini.sample`.

**Watch Graph:**
- `WATCH_API_BASE` (default: `https://watch.graph.api.espn.com/api`)
- `WATCH_API_KEY` (public key provided)
- `WATCH_FEATURES` (default: `pbov7`)
- `WATCH_API_REGION` (`US`)
- `WATCH_API_TZ` (`America/New_York`)
- `WATCH_API_DEVICE` (`desktop|mobile|tv`)
- `WATCH_API_VERIFY_SSL` (`1|0`)

**Resolver / outputs:**
- `VC_DB` → SQLite path (default `data/eplus_vc.sqlite3`)
- `VC_RESOLVER_ORIGIN` → used by XMLTV/M3U links (default `http://HOST:8094`)
- `VC_SLATE_URL` → optional slate page for placeholders
- Placeholder text:  
  `VC_PLACEHOLDER_TITLE`, `VC_PLACEHOLDER_SUBTITLE`, `VC_PLACEHOLDER_SUMMARY`

---

## Systemd (recommended)

Install units (samples in `systemd/`):

- **Pipeline (every 30 min):**
  - `vc-pipeline-v2.service` → ingest → build_plan → xmltv → m3u
  - `vc-pipeline-v2.timer`   → `OnCalendar=*:/0,30`
- **Resolver API:**
  - `vc-resolver-v2.service` → uvicorn FastAPI on :8094

Environment file example `/etc/systemd/system/espnvc-v2.env`:
```ini
VC_DB=/home/brad/Projects/ESPN_clean_v2/data/eplus_vc.sqlite3
VC_RESOLVER_ORIGIN=http://192.168.86.72:8094
VC_SLATE_URL=http://192.168.86.72:8094/slate
TZ=America/New_York

WATCH_API_REGION=US
WATCH_API_TZ=America/New_York
WATCH_API_DEVICE=desktop
WATCH_API_VERIFY_SSL=1
```

Enable:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now vc-pipeline-v2.timer
sudo systemctl enable --now vc-resolver-v2.service
journalctl -u vc-pipeline-v2.service -f
journalctl -u vc-resolver-v2.service -f
```

---

## Usage notes

- Placeholders align to `:00`/`:30`.  
- XMLTV start is **backdated** to true event start for accurate progress bars.  
- Resolver prefers `feeds.is_primary DESC, id DESC` and honors `preferred_feed_id` if set.

---

## Troubleshooting

- **No module named `fastapi`** → `pip install -r requirements.txt` inside `.venv` and ensure the unit uses `.venv/bin/python`.
- **“unrecognized arguments”** → older flags were removed (e.g., `--tz` for `xmltv_from_plan.py`).
- **Resolver 500** → check `/vc/<lane>/debug`, confirm DB path (`VC_DB`) and that `plan_slot` has a current event.

---

## License
MIT (or your preferred license)

## Systemd install quickstart

See [contrib/systemd/README.md](contrib/systemd/README.md) for full instructions.

**Makefile (recommended):**

```
make systemd-install USER=brad PROJECT_DIR=/home/brad/Projects/ESPN4CC
make systemd-status USER=brad
make plan-run USER=brad
make resolver-restart USER=brad
make diag LANE=eplus11 QUIET=1
```
