# ESPN4CC4C — Docker Edition (v3.0.15)

[![Version](https://img.shields.io/badge/version-v3.0.15-blue.svg)](https://github.com/kineticman/ESPN4CC4C/releases)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Docker](https://img.shields.io/badge/docker-compose%20ready-orange.svg)]()

**ESPN4CC4C (ESPN+ Virtual Channels for Channels DVR)** turns ESPN+ events into a stable lineup of virtual channels.  
It exposes **XMLTV** and **M3U** endpoints that Channels DVR can ingest directly.

---

### 📡 Quick Links

| Type | URL Pattern |
|------|--------------|
| **M3U** | `http://<LAN-IP>:8094/out/playlist.m3u` |
| **XMLTV** | `http://<LAN-IP>:8094/out/epg.xml` |
| **Health** | `http://<LAN-IP>:8094/health` |

---

## 🚀 Quick Start

### 1️⃣ Configure Environment
```bash
cp .env.example .env
# Edit .env and set your LAN IP, timezone, and optional Chrome Capture host.
# ⚠️ Never use /app/* paths on the host.
```

Key lines in `.env`:
```ini
PORT=8094
TZ=America/New_York
VC_RESOLVER_BASE_URL=http://YOUR_LAN_IP:8094
M3U_GROUP_TITLE='ESPN+ VC'
DB=./data/eplus_vc.sqlite3
OUT=./out
LOGS=./logs
```

### 2️⃣ Start the Stack
```bash
./bootstrap.sh
```
This will:
- Build + start the resolver container
- Wait for `/health`
- Migrate + seed the DB
- Generate XMLTV + M3U
- Print a **sanity summary** and first real program title

Example output:
```text
== sanity summary ==
host=kuhn29-MINI-S  programmes=5758  placeholders=4000  real=1758
== first non-placeholder title ==
NHL Frozen Frenzy
```

### 3️⃣ Add to Channels DVR
Use the LAN IP and port from `.env`:

```
M3U:   http://192.168.86.72:8094/out/playlist.m3u
XMLTV: http://192.168.86.72:8094/out/epg.xml
```

---

## 🔁 Update / Refresh

```bash
./update_schedule.sh
```
This runs:
- DB migrate → Plan build → XMLTV/M3U emit → Sanity checks

All network calls are **GET-only**, no `HEAD`.

---

## ⚙️ Environment Variables (Excerpt)

| Variable | Default | Description |
|-----------|----------|-------------|
| `PORT` | 8094 | Port published by Docker Compose |
| `TZ` | America/New_York | Timezone |
| `DB` | ./data/eplus_vc.sqlite3 | SQLite DB (host-side) |
| `OUT` | ./out | Output dir for XMLTV + M3U (host-side) |
| `LOGS` | ./logs | Log directory (host-side) |
| `VALID_HOURS` | 72 | Schedule window |
| `LANES` | 40 | Virtual channels |
| `ALIGN` | 30 | Time grid alignment |
| `MIN_GAP_MINS` | 30 | Minimum slot gap |
| `VC_RESOLVER_BASE_URL` | required | Base URL for Channels DVR |
| `CC_HOST` | YOUR_LAN_IP | Chrome Capture host |
| `CC_PORT` | 5589 | Chrome Capture port |
| `M3U_GROUP_TITLE` | 'ESPN+ VC' | M3U group label |

---

## 🔍 Endpoints

| Path | Purpose |
|------|----------|
| `/health` | JSON health check |
| `/out/epg.xml` | XMLTV guide |
| `/out/playlist.m3u` | M3U playlist |
| `/vc/{{lane}}` | Redirect to live ESPN+ stream |
| `/vc/{{lane}}/debug` | Debug info for lane |

---

## 🧰 Common Commands

```bash
# Start / stop
docker compose up -d
docker compose down

# Rebuild image
docker compose build --no-cache

# Follow logs
docker compose logs -f

# DB peek
docker compose exec espn4cc sqlite3 /app/data/eplus_vc.sqlite3 "SELECT COUNT(*) FROM events;"
```

---

## 🧯 Troubleshooting

**Container name conflict (`espn4cc`):**
```bash
docker compose down --remove-orphans
docker rm -f espn4cc 2>/dev/null || true
docker network rm espn4cc4c_default 2>/dev/null || true
docker compose up -d
```

**Wrong LAN IP / Port:**
```bash
VC_RESOLVER_BASE_URL=http://192.168.86.72:8094
PORT=8094
./bootstrap.sh
```

---

## 🧩 Recent Changes (v3.0.15)

- Added installation summary at end of `bootstrap.sh`
- Host‑path validation (`no /app/*` on host)
- Sanity summary prints program counts and first real title
- Unified log + output directories
- GET‑only endpoint checks
- Improved Docker build hygiene and readiness wait

---

**Maintainer:** [@kineticman](https://github.com/kineticman)  
**License:** MIT  
**Version:** v3.0.15  
