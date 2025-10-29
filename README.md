# ESPN4CC4C — Docker Edition (v3.2.0)

**ESPN4CC4C (ESPN+ Virtual Channels for Channels DVR)** provides a containerized resolver that turns ESPN+ events into a stable set of virtual channels. It exposes **XMLTV** and **M3U** endpoints that Channels DVR can ingest.

---

## Features
- 40 managed virtual channels (default)
- XMLTV EPG generation + M3U playlist
- Idempotent DB migration on refresh
- Health endpoint + sanity checks (GET-only)
- Simple Docker Compose deployment
- Persistent `data/`, `logs/`, and `out/` (bind mounts)
- **Built‑in cron inside the container** (defaults to every 6 hours) to refresh guide + playlist automatically

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
> **Host vs container paths:** On the host, use **relative paths** like `./data`, `./out`, `./logs`. Inside the container those are bind‑mounted to `/app/data`, `/app/out`, `/app/logs`. The scripts hard‑fail if you set `/app/...` in the host `.env`.

### 2) Bring it up (recommended)
```bash
./bootstrap.sh
```
What it does:
- Builds + starts the container
- Waits for **/health** (with a short boot delay)
- Ensures the DB exists and runs migrations (inside the container)
- Generates an initial plan, **XMLTV**, and **M3U**
- Prints a quick install summary + a sample programme title

(Manual alternative)
```bash
docker compose build
docker compose up -d
curl -fsS http://<LAN-IP>:8094/health | jq .
./update_schedule.sh
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

You can manually refresh anytime:
```bash
./update_schedule.sh
```
That performs: **DB migrate → Plan → Emit XML/M3U → Sanity checks** (all container‑side and GET‑only).

### 🔁 Internal Cron Jobs (inside the container)
Starting with v3.x, the container runs a small cron to keep things fresh automatically:

- **Every 6 hours** (default): `update_schedule.sh` refreshes the DB/plan/XMLTV/M3U and writes logs to `/app/logs/schedule.log` (host `./logs/schedule.log`).  
- **Weekly VACUUM**: Every **Sunday at 03:17** container‑local time, the SQLite DB is vacuumed to keep size/perf in check.

You can tweak the refresh cadence by setting **`SCHEDULE_HOURS`** in the container environment (e.g., `SCHEDULE_HOURS=3` for every 3 hours).

> Tip: To view the last run log on the host:  
> `tail -n 120 ./logs/schedule.log`

---

## Environment Variables (excerpt)

| Variable | Default | Notes |
|---|---|---|
| `PORT` | `8094` | Port published by Docker Compose and used when `VC_RESOLVER_BASE_URL` is unset. |
| `TZ` | `America/New_York` | Container timezone. |
| `DB` | `/app/data/eplus_vc.sqlite3` | SQLite DB path (container). Host should use `./data/eplus_vc.sqlite3`. |
| `OUT` | `/app/out` | Output dir (container). Host should use `./out`. |
| `LOGS` | `/app/logs` | Logs dir (container). Host should use `./logs`. |
| `VC_M3U_PATH` | `/app/out/virtual_channels.m3u` | Optional/legacy target; safe to ignore. |
| `VALID_HOURS` | `72` | Planning window (hours). |
| `LANES` | `40` | Number of virtual channels. |
| `ALIGN` | `30` | Align start times to minute grid. |
| `MIN_GAP_MINS` | `30` | Minimum gap between slots. |
| `VC_RESOLVER_BASE_URL` | *(required)* | Must be reachable by Channels DVR (e.g., `http://192.168.x.x:8094`). |
| `CC_HOST` | `YOUR_LAN_IP` | The server where CC4C is running. |
| `CC_PORT` | `5589` | Chrome Capture port. |
| `M3U_GROUP_TITLE` | `'ESPN+ VC'` | Keep **quotes**; contains a space. |
| `SCHEDULE_HOURS` | `6` | **Container cron** cadence (hours) for automatic refreshes. |

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

# DB peek (inside the container)
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
  ```ini
  VC_RESOLVER_BASE_URL=http://192.168.86.72:8094
  PORT=8094
  ```
- Re‑run:
  ```bash
  ./bootstrap.sh
  ```

**Host `.env` accidentally uses `/app/...`:**
- The host scripts now **hard‑fail** to avoid bad mounts. Change to host‑relative paths like `./data`, `./out`, `./logs`.

---

## Notes
- Channel IDs are **numeric** right now (stable). A future toggle for `eplusXX` IDs can be added if desired.
- Sanity checks and endpoint probes use **GET** only.
- The M3U writer is invoked with flags so it honors `VC_RESOLVER_BASE_URL`, `CC_HOST`, and `CC_PORT` from `.env` on each refresh.

---

**Version:** v3.2.0  
**License:** MIT  
**Maintainer:** kineticman  
**This project is not affiliated with or endorsed by ESPN, Disney, or Channels DVR.
