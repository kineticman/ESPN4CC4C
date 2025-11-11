# ESPN4CC4C - ESPN+ Virtual Channels for Channels DVR (Docker Edition)

Turn ESPN+ events into **stable virtual channels** (eplus1–eplus40) your **Channels DVR** can ingest via **XMLTV** and **M3U** — all packaged in a single Docker service.

> **Latest tag:** `v4.8.2` (Nov 2025)

---

## 🚀 What’s new in v4.8.2

**Filtering & API**
- New **filter-first flow**: fast way to see what’s in DB and how filters affect it.
- `/whatson/{lane}` and `/whatson_all` return clearer, lane-aware snapshots (JSON or text).
- `/deeplink/{lane}` can include the **full `sportscenter://` deeplink** when available (handy for ADBTuner).
- Added **language-aware** event parsing and optional **XML enrich hooks** (logos/hero images).

**Windows bootstrap**
- Fixes for PowerShell parsing errors on older builds.
- Post-install checks for **XMLTV** and **M3U** with readable error messages.
- Clear guidance for IP/port and firewall checks.

**Pipeline**
- Image scraping hooks (opt‑in), language support, and enrich options exposed.
- Minor stability fixes and logging cleanup.

---

## What You Need

- **Docker Desktop** (Windows) or **Docker Engine** (Linux)
- Your computer’s **local IP address**
- **Channels DVR** on your network
- Outbound HTTPS access to ESPN

**Port Used:** `8094/tcp`

---

## Installation — Windows

### 1) Get the Project Files

**Option A — Git (recommended):**
```powershell
git clone https://github.com/kineticman/ESPN4CC4C.git
cd ESPN4CC4C
```

**Option B — Download ZIP:**
1. Go to **https://github.com/kineticman/ESPN4CC4C**
2. **Code → Download ZIP** and extract to `C:\ESPN4CC4C`
3. Open that folder

### 2) Find Your Computer’s IP
1. `Win` + `R` → type `cmd` → Enter
2. Run `ipconfig`
3. Copy your **IPv4 Address** (e.g., `192.168.86.72`)

### 3) Configure Settings
1. Copy **`.env.example`** → **`.env`**
2. Edit `.env` in Notepad, set these two lines:
   ```
   VC_RESOLVER_BASE_URL=http://192.168.86.72:8094
   CC_HOST=192.168.86.72
   ```
3. Save

### 4) Run the Bootstrap Script
Right‑click the folder background while holding **Shift** → **Open PowerShell window here**, then:
```powershell
.\windowsbootstrap.ps1 -LanIp 192.168.86.72
```
It will create folders, start Docker, ingest ESPN+ data, and build the guide.

### 5) Verify
Open a browser:
```
http://192.168.86.72:8094/health
```
You should see: `{"ok":true}`

#### Windows Troubleshooting
- **Execution policy**: right‑click `windowsbootstrap.ps1` → Run with PowerShell. Approve prompts.
- **Health fails**: ensure Docker Desktop is running and port 8094 allowed through firewall.
- **“Ingested 0 airings”**: verify `WATCH_API_KEY` in `.env` (default key is prefilled).
- **Container “Exited”**: open Docker Desktop → espn4cc → Logs; restart if needed.

---

## Installation — Linux

```bash
git clone https://github.com/kineticman/ESPN4CC4C.git
cd ESPN4CC4C
cp .env.example .env
nano .env
```
Update:
```
VC_RESOLVER_BASE_URL=http://192.168.1.63:8094
CC_HOST=192.168.1.63
```
Then:
```bash
./bootstrap.sh
curl http://192.168.1.63:8094/health
# -> {"ok":true}
```

---

## Add to Channels DVR

**XMLTV Guide:**
```
http://<LAN-IP>:8094/out/epg.xml
```

**M3U Playlist:**
```
http://<LAN-IP>:8094/out/playlist.m3u
```

You’ll see **eplus1–eplus40** with guide data.

---

## 🔎 API Cheat‑Sheet (test filtering fast)

All endpoints are served by the resolver (`PORT=8094` by default). Replace `<HOST>` with your LAN IP.

### Health
```
GET http://<HOST>:8094/health
→ {"ok":true}
```

### What’s on (all lanes)
```
GET http://<HOST>:8094/whatson_all?format=json
GET http://<HOST>:8094/whatson_all?format=txt
```
Tip: Great “at a glance” view after editing `filters.ini`.

### What’s on (single lane)
```
GET http://<HOST>:8094/whatson/9?format=json
GET http://<HOST>:8094/whatson/9?format=txt
```

### Deeplink for current lane program
```
GET http://<HOST>:8094/deeplink/9
→ may include full sportscenter:// URL
```

### VC helpers
```
GET http://<HOST>:8094/vc/9
GET http://<HOST>:8094/vc/9/debug
```

### Outputs consumed by Channels
```
GET http://<HOST>:8094/out/epg.xml
GET http://<HOST>:8094/out/playlist.m3u
```

---

## 🎛️ Content Filtering (Optional, recommended)

Use `filters.ini` in the project root to control which events make it into the plan.

### Quick Start

**See what’s in the DB + generate a starter config:**
```bash
# Linux/Mac (host)
python3 bin/generate_filter_options.py ./data/eplus_vc.sqlite3 --generate-config > filters.ini

# Windows (inside the container)
docker exec espn4cc python3 /app/bin/generate_filter_options.py /app/data/eplus_vc.sqlite3 --generate-config > /app/filters.ini
docker cp espn4cc:/app/filters.ini ./filters.ini
```

**Edit `filters.ini`**, then **rebuild**:
```bash
# Linux
./update_schedule.sh

# Windows
.\windowsbootstrap.ps1 -LanIp <LAN-IP>
```

**Verify effect:**
```
GET http://<HOST>:8094/whatson_all?format=txt
```
and check the filter summary in logs (included/filtered counts).

### Common Scenarios

**ESPN+ only**
```ini
[filters]
enabled_networks = ESPN+
require_espn_plus = true
```

**Cable/satellite only**
```ini
[filters]
exclude_networks = ESPN+
require_espn_plus = false
```

**Specific sports**
```ini
[filters]
enabled_sports = Football,Basketball
```

**Pro leagues only (no college)**
```ini
[filters]
enabled_leagues = NFL,NBA,NHL,MLS
```

**No replays**
```ini
[filters]
exclude_event_types = OVER
```

### Reference

| Key | Example | Notes |
|---|---|---|
| `enabled_networks` | `ESPN,ESPN2,ESPNU,ESPN+` | Whitelist |
| `exclude_networks` | `ESPN Deportes,ESPN PPV` | Blacklist |
| `enabled_sports` | `Football,Basketball,Soccer` | Whitelist |
| `exclude_sports` | `*College*` | Substring match allowed |
| `enabled_leagues` | `NFL,NBA,NHL` | Whitelist |
| `exclude_leagues` | `G League` | Blacklist |
| `enabled_event_types` | `LIVE,UPCOMING` | Only these |
| `exclude_event_types` | `OVER` | Drop replays |
| `require_espn_plus` | `true/false` | Filter by platform |
| `exclude_ppv` | `true` | Drop PPV |

> Tip: run `generate_filter_options.py` (no args) to see counts by network/sport/league for the current DB snapshot.

---

## 🧩 ADBTuner / Deep‑linking notes

If your automation can launch Android TV/Fire TV apps, the resolver exposes deeplinks per lane:
```
GET /deeplink/{lane}
```
When available you’ll get a full `sportscenter://x-callback-url/showWatchStream?playID=...` URL.
Example pseudo‑workflow:
1. Query `/whatson/{lane}?format=json` → get `event_uid` and meta
2. Query `/deeplink/{lane}` → get `sportscenter://…` URL
3. Feed that into ADBTuner/script to open ESPN app to the correct stream

---

## Configuration Reference (.env)

**Update these:**
| Var | Example |
|---|---|
| `VC_RESOLVER_BASE_URL` | `http://192.168.86.72:8094` |
| `CC_HOST` | `192.168.86.72` |
| `TZ` | `America/New_York` |

**Common:**
| Var | Default | Meaning |
|---|---|---|
| `PORT` | `8094` | Service port |
| `LANES` | `40` | eplus1–eplusN |
| `VALID_HOURS` | `72` | Guide window |
| `CC_PORT` | `5589` | Chrome Capture |

**Advanced:**
| Var | Default |
|---|---|
| `ALIGN=30` | start at :00/:30 |
| `MIN_GAP_MINS=30` | spacing |
| `WATCH_API_KEY` | (provided) |

---

## Manual Ops

```bash
# rebuild plan + outputs
docker exec espn4cc python3 /app/bin/build_plan.py --db /app/data/eplus_vc.sqlite3 --valid-hours 72
docker exec espn4cc python3 /app/bin/xmltv_from_plan.py --db /app/data/eplus_vc.sqlite3 --out /app/out/epg.xml
docker exec espn4cc python3 /app/bin/m3u_from_plan.py --db /app/data/eplus_vc.sqlite3 --out /app/out/playlist.m3u --resolver-base http://<HOST>:8094 --cc-host <HOST> --cc-port 5589

# refresh ingest
docker exec espn4cc python3 /app/bin/ingest_watch_graph_all_to_db.py --db /app/data/eplus_vc.sqlite3 --days 3 --tz America/New_York

# logs
docker logs espn4cc --tail 200
```

---

## Release Notes (v4.8.2)

- **API:** clearer `/whatson_*` shapes; `/deeplink/{lane}` can return full `sportscenter://` when available.
- **Filtering:** new helper script + better summaries; language hints respected; XML enrich hooks (logos/images) available.
- **Bootstrap (Windows):** parsing fixes; better post‑run checks for XMLTV/M3U; clearer failure messages.
- **Planner/Writer:** stability & logging polish.

---

## Project Structure

```
ESPN4CC4C/
├─ bin/                      # Python tools
│  ├─ build_plan.py          # Planner
│  ├─ xmltv_from_plan.py     # XML writer
│  ├─ m3u_from_plan.py       # M3U writer
│  ├─ ingest_watch_graph_all_to_db.py
│  ├─ generate_filter_options.py
├─ data/                     # SQLite DB (persisted)
├─ logs/
├─ out/                      # epg.xml + playlist.m3u
├─ docker-compose.yml
├─ .env
├─ filters.ini               # optional
├─ windowsbootstrap.ps1
├─ bootstrap.sh
└─ README.md
```

---

**Enjoy!** If something’s confusing, open an issue with what you expected vs. what happened.
