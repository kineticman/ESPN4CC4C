# ESPN4CC4C — Docker Edition (v3.0.0)

**ESPN4CC4C (ESPN+ Virtual Channels for Channels DVR)** provides a containerized resolver that turns ESPN+ events into a stable set of virtual channels. It exposes **XMLTV** and **M3U** endpoints that Channels DVR can ingest.

---

## Features
- 40 managed virtual channels (default)
- XMLTV EPG generation + M3U playlist
- Idempotent DB migration on refresh
- Health endpoint + sanity checks (GET-only)
- Simple Docker Compose deployment
- Persistent `data/`, `logs/`, and `out/` (bind mounts)

---

## Prerequisites
- Docker Engine 20.10+  
- Docker Compose v2  
- **CC4C** (Chrome Capture) if you want to actually open/watch streams (not included here)  
- A LAN‑reachable host IP (so Channels can reach this container)  
- (Optional) Channels DVR to consume the M3U + XMLTV

---

## Quick Start

### 1) Configure environment
```bash
cp .env.example .env
# Edit .env and set your LAN IP and desired port (default 8094).
# Example:
# VC_RESOLVER_BASE_URL=http://192.168.86.72:8094
# TZ=America/New_York
```

Key lines in `.env`:
```ini
PORT=8094
TZ=America/New_York
VC_RESOLVER_BASE_URL=http://YOUR_LAN_IP:8094
M3U_GROUP_TITLE='ESPN+ VC'  # keep quotes
```
> `OUT` is a **directory** (`/app/out`); the stack writes `epg.xml` and `playlist.m3u` inside it.

### 2) Bring it up (recommended)
```bash
./bootstrap.sh
```
- Builds + starts the container
- Waits for **/health** (with a default boot delay), then prints:
  - XMLTV bytes, M3U bytes
  - First `<channel id>` from XML
  - First `tvg-id` from M3U  
- Shows the exact URLs to paste into Channels DVR

(Manual alternative)
```bash
docker compose build
docker compose up -d
curl -fsS http://<LAN-IP>:8094/health | jq .
```

### 3) Add to Channels DVR
Use the LAN IP and port from `.env`:

- **M3U**:   `http://<LAN-IP>:<PORT>/out/playlist.m3u`  
- **XMLTV**: `http://<LAN-IP>:<PORT>/out/epg.xml`

Example:
```
http://192.168.86.72:8094/out/playlist.m3u
http://192.168.86.72:8094/out/epg.xml
```

> Note: The resolver may **not** serve a root `/playlist.m3u`. Always use the **`/out/playlist.m3u`** path shown above.

---

## Update / Refresh Cycle

The refresh script runs: **DB migrate → Plan → Emit XML/M3U → Sanity checks**.

```bash
./update_schedule.sh
```
Options:
- `PRE_WAIT=5 ./update_schedule.sh` — give the resolver a short warm‑up before checks.
- All checks use **GET** (no `HEAD`).

---

## Environment Variables (excerpt)

| Variable | Default | Notes |
|---|---|---|
| `PORT` | `8094` | Port published by Docker Compose and used when `VC_RESOLVER_BASE_URL` is unset. |
| `TZ` | `America/New_York` | Container timezone. |
| `DB` | `/app/data/eplus_vc.sqlite3` | SQLite DB path (inside container). |
| `OUT` | `/app/out` | Output dir (container). `epg.xml` and `playlist.m3u` live here. |
| `LOGS` | `/app/logs` | Logs dir (container). |
| `VC_M3U_PATH` | `/app/out/virtual_channels.m3u` | Optional/legacy target; safe to ignore. |
| `VALID_HOURS` | `72` | Planning window (hours). |
| `LANES` | `40` | Number of virtual channels. |
| `ALIGN` | `30` | Align start times to minute grid. |
| `MIN_GAP_MINS` | `30` | Minimum gap between slots. |
| `VC_RESOLVER_BASE_URL` | *(required)* | Must be reachable by Channels DVR (e.g., `http://192.168.x.x:8094`). |
| `CC_HOST` | `YOUR_LAN_IP` | The server where CC4C is running. |
| `CC_PORT` | `5589` | Chrome Capture port. |
| `M3U_GROUP_TITLE` | `'ESPN+ VC'` | Keep **quotes**; contains a space. Not recommended to change. |

---

## Endpoints

| Path | Purpose |
|---|---|
| `/health` | JSON health check |
| `/out/epg.xml` | XMLTV guide |
| `/out/playlist.m3u` | M3U playlist (recommended path) |
| `/vc/{lane}` | Resolver redirect to current event in a lane |
| `/vc/{lane}/debug` | Debug info for a lane |

---

## Common Commands

```bash
# Start / stop
docker compose up -d
docker compose down

# Rebuild image
docker compose build --no-cache
docker compose up -d

# Follow logs
docker compose logs -f

# DB peek (requires sqlite3 in the container image)
docker compose exec espn4cc sqlite3 /app/data/eplus_vc.sqlite3 "SELECT COUNT(*) FROM events;"
```

---

## Troubleshooting

**Container name conflict (`espn4cc`):**
```bash
docker compose down --remove-orphans
docker rm -f espn4cc 2>/dev/null || true
docker network rm espn4cc4c_default 2>/dev/null || true
docker compose up -d
```

**Wrong LAN IP / Port:**
- Fix in `.env`:
  ```
  VC_RESOLVER_BASE_URL=http://192.168.86.72:8094
  PORT=8094
  ```
- Re‑run:
  ```bash
  ./bootstrap.sh
  ```

---

## Notes
- Channel IDs are **numeric** right now (stable). A future toggle for `eplusXX` IDs can be added if desired.
- Sanity checks and endpoint probes use **GET** only.
- The M3U writer is invoked with flags so it honors `VC_RESOLVER_BASE_URL`, `CC_HOST`, and `CC_PORT` from `.env` on each refresh.

---

**Version:** v3.0.0  
**License:** MIT  
**Maintainer:** kineticman  
**This project is not affiliated with or endorsed by ESPN, Disney, or Channels DVR.
