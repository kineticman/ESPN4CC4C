# ESPN4CC4C — Docker Install (Single-Container)

**Works on:** Ubuntu/Debian host with Docker.  
**Exposes:** `http://<HOST>:8094` (resolver + XMLTV/M3U).

---

## Quick start

```bash
git clone https://github.com/kineticman/ESPN4CC4C.git
cd ESPN4CC4C

# one-liner bootstrap: writes Docker files, builds, starts, verifies
bash ./espn4cc_bootstrap.sh
```

What the bootstrap sets up:
- `docker-compose.yml` (single service: `espn4cc`, `init: true`, `restart: unless-stopped`)
- `Dockerfile` (Python 3.11 slim, uvicorn)
- `docker-entrypoint.sh` (starts cron + resolver)
- `update_schedule.sh` (ingest → plan → xmltv/m3u; **GET-only** readiness gate; jitter; log rotation)
- `espn4cc_verify.sh` (health + content checks)
- `.env` (LAN IP base URL, DB/out paths, schedule freq)

> **Important:** The FastAPI app is `bin.vc_resolver:app` (not `vc_resolver.app:app`).

---

## Ports & Volumes

- Port: `8094` (host) → `8094` (container)
- Volumes:
  - `./data` → `/app/data` (SQLite)
  - `./out`  → `/app/out`  (EPG/M3U)
  - `./logs` → `/app/logs` (logs)
  - `.env`   → `/app/.env` (read-only)

---

## Environment (.env)

```env
VC_RESOLVER_BASE_URL=http://<YOUR_LAN_IP>:8094
TZ=America/New_York
DB=/app/data/eplus_vc.sqlite3
OUT=/app/out/epg.xml
VC_M3U_PATH=/app/out/virtual_channels.m3u
VALID_HOURS=72
LANES=40
ALIGN=30
MIN_GAP_MINS=30
SCHEDULE_HOURS=6
PORT=8094
```

> Use your **LAN IP** (not `localhost/127.0.0.1`) so Channels DVR can reach it.

---

## Operate

```bash
# build / start
docker compose up -d

# verify
./espn4cc_verify.sh <LAN_IP> 8094

# logs (follow)
docker compose logs -f --tail=100

# manual update cycle
docker compose exec espn4cc /app/update_schedule.sh
```

---

## Channels DVR Setup

- **M3U:** `http://<LAN_IP>:8094/playlist.m3u`  
- **EPG:** `http://<LAN_IP>:8094/epg.xml`

Tune an `eplus` channel from the guide; ChromeCapture should fullscreen automatically.

---

## Design Notes

- Single-container for simplicity: resolver (uvicorn) is PID 1; cron runs in background.
- Readiness gate (GET `/health`) before each scheduler run; **no HEAD** requests anywhere.
- Jittered scheduler to avoid thundering herd when running on multiple hosts.
- Timezone inside container is respected (`TZ=America/New_York`).
- Weekly SQLite `VACUUM` (Sunday 03:17).

---

## Troubleshooting

- **Port 8094 already in use?** Stop legacy units:
  ```bash
  sudo systemctl stop vc-resolver-v2.service vc-plan.timer || true
  sudo systemctl disable vc-resolver-v2.service vc-plan.timer || true
  sudo systemctl daemon-reload
  docker compose up -d
  ```
- **“localhost” inside M3U?** Fix `.env` to the LAN IP and rebuild:
  ```bash
  sed -i "s#VC_RESOLVER_BASE_URL=.*#VC_RESOLVER_BASE_URL=http://<LAN_IP>:8094#" .env
  docker compose up -d --build
  ./espn4cc_verify.sh <LAN_IP> 8094
  ```
