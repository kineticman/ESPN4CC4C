ESPN4CC4C — ESPN+ Virtual Channels for Channels DVR

Status: ✅ Production-ready
Deployment: Containerized (single Docker container) or legacy systemd
Endpoints: http://<HOST>:8094/health, /epg.xml, /playlist.m3u, /vc/<lane>

----------------------------------------------------------------

What is this?
ESPN4CC4C builds ~40 virtual channels from ESPN+ event data and exposes:
- XMLTV (/epg.xml) for guide data
- M3U (/playlist.m3u) for Channel stream entries
- Resolver (/vc/<lane>) that redirects to the correct ESPN Watch player (used by ChromeCapture → Channels DVR)

----------------------------------------------------------------

CONTAINERIZED DEPLOYMENT (RECOMMENDED)

We now support a single-container install that bundles:
- FastAPI resolver (uvicorn) — PID 1
- Cron scheduler — runs ingest → plan → XML/M3U generation on a schedule
- Health checks + readiness gate — GET /health only (no HEAD)
- Log rotation + weekly SQLite VACUUM
- Timezone inside container (America/New_York)

Quick start:
  git clone https://github.com/kineticman/ESPN4CC4C.git
  cd ESPN4CC4C
  bash ./espn4cc_bootstrap.sh   # writes Docker files, builds, starts, verifies

What the bootstrap sets up:
- docker-compose.yml (service espn4cc, init: true, restart: unless-stopped)
- Dockerfile (Python 3.11 slim)
- docker-entrypoint.sh (starts cron + resolver)
- update_schedule.sh (ingest → plan → xmltv/m3u; jitter; logrotate; health-gated)
- espn4cc_verify.sh (health + content checks)
- .env (LAN base URL, paths, schedule)

Important: The FastAPI app module is bin.vc_resolver:app

Channels DVR setup:
- M3U:  http://<LAN_IP>:8094/playlist.m3u
- EPG:  http://<LAN_IP>:8094/epg.xml

More details: see README_DOCKER.md

----------------------------------------------------------------

LEGACY SYSTEMD (STILL SUPPORTED)
If you prefer systemd units and timers on the host, the original scripts and units continue to work. The Docker image mirrors the same behavior internally (resolver as a service + timer-like scheduler).

----------------------------------------------------------------

ARCHITECTURE (CONTAINER)

ESPN Watch Graph API
        ↓
    ingest_* → SQLite (/app/data/eplus_vc.sqlite3)
        ↓
   build_plan (40 lanes, ~72h horizon)
        ↓
  xmltv_from_plan  → /app/out/epg.xml
  m3u_from_plan    → /app/out/virtual_channels.m3u
        ↓
  FastAPI resolver (uvicorn) → /health /epg.xml /playlist.m3u /vc/<lane>
                                ↑
                             Channels DVR

----------------------------------------------------------------

OPS CHEATSHEET

# start/stop
docker compose up -d
docker compose down

# logs
docker compose logs -f --tail=100

# manual update cycle
docker compose exec espn4cc /app/update_schedule.sh

# verify endpoints
./espn4cc_verify.sh <LAN_IP> 8094

----------------------------------------------------------------

TROUBLESHOOTING

Port 8094 in use (old systemd units)?
  sudo systemctl stop vc-resolver-v2.service vc-plan.timer || true
  sudo systemctl disable vc-resolver-v2.service vc-plan.timer || true
  sudo systemctl daemon-reload
  docker compose up -d

M3U shows localhost/127.0.0.1?
  Set VC_RESOLVER_BASE_URL=http://<LAN_IP>:8094 in .env, rebuild:
  docker compose up -d --build
  ./espn4cc_verify.sh <LAN_IP> 8094

----------------------------------------------------------------

NOTES & CONVENTIONS
- All readiness checks use GET (no HEAD) by design.
- Timezone is America/New_York inside the container.
- Weekly VACUUM keeps SQLite lean.
- Default planning horizon is ~72h.

----------------------------------------------------------------

License
MIT (see LICENSE)
