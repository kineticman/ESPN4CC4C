# ESPN4CC4C — ESPN+ Virtual Channels for Channels DVR

Turn ESPN+ events into **stable virtual channels** (eplus1–eplus40) your **Channels DVR** can ingest via **XMLTV** and **M3U** — all in one Docker service.

> **Baseline:** v5.1.x (2025‑11‑12) — prebuilt image with cron & tzdata; default onboarding = clone → `docker compose up`.

---

## 🆕 What’s new (v5.1.x)
- **Compose‑only onboarding**: just drop a Portainer Stack or run `docker compose up` — no extra setup.
- **Built‑in cron**: auto refresh at **08:05 / 14:05 / 20:05**; weekly **VACUUM** Sun **03:10**.
- **Safer compose**: init‑enabled, graceful stop, `${PORT}`‑aware healthcheck, and log rotation.
- **Filtering workflow**: simple `filters.ini` + `/whatson` views to confirm results fast.
- **API polish**: lane‑aware `/whatson_all`, `/whatson/{lane}` (JSON/TXT) and `/deeplink/{lane}` for ADBTuner‑style launchers.

> Standing rules: **GET‑only** for checks (no HEAD), **never** use proxies for ESPN endpoints.

---

## 🚀 Quick Start (Portainer — easiest)
This is the recommended flow for Channels users.

1) **Open Portainer → Stacks → Add Stack**

2) **Name:** `espn4cc4c`

3) **Compose** (paste this YAML):

```yaml
services:
  espn4cc4c:
    image: ghcr.io/kineticman/espn4cc4c:${TAG:-latest}
    container_name: espn4cc4c
    init: true
    stop_grace_period: 20s

    ports:
      - ${PORT:-8094}:${PORT:-8094}

    environment:
      - TZ=${TZ:-America/New_York}
      - VC_RESOLVER_BASE_URL=${VC_RESOLVER_BASE_URL:-http://192.168.86.72:8094}
      - CC_HOST=${CC_HOST:-192.168.86.72}
      - CC_PORT=${CC_PORT:-5589}
      - PORT=${PORT:-8094}
      - APP_MODULE=${APP_MODULE:-bin.vc_resolver:app}
      - VALID_HOURS=${VALID_HOURS:-72}
      - LANES=${LANES:-40}
      - ALIGN=${ALIGN:-30}
      - MIN_GAP_MINS=${MIN_GAP_MINS:-30}
      - M3U_GROUP_TITLE=${M3U_GROUP_TITLE:-ESPN+ VC}
      - VC_M3U_PATH=${VC_M3U_PATH:-/app/out/playlist.m3u}
      - WATCH_API_KEY=${WATCH_API_KEY:-0dbf88e8-cc6d-41da-aa83-18b5c630bc5c}

    volumes:
      - ${HOST_DIR:-.}/data:/app/data
      - ${HOST_DIR:-.}/out:/app/out
      - ${HOST_DIR:-.}/logs:/app/logs

    # Optional: helps suffix matching only; actual name resolution must work in your LAN/Tailscale DNS.
    dns_search:
      - ${DOMAIN:-localdomain}
      - ${TAILNET:-tailxxxxx.ts.net}

    healthcheck:
      test: ["CMD-SHELL", "curl -fsS http://localhost:${PORT:-8094}/health >/dev/null"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s

    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "5"

    restart: unless-stopped
```

4) **Env vars** (Portainer’s “Environment variables” panel)
- `TZ=America/New_York`
- `VC_RESOLVER_BASE_URL=http://<YOUR-IP>:8094`
- `CC_HOST=<YOUR-IP>`
- *(optional)* `HOST_DIR=/data/espn4cc4c` to store DB/out/logs under a specific host path

5) **Deploy the stack**

6) **Sanity checks (browser or curl)**
```
http://<YOUR-IP>:8094/health            → {"ok": true}
http://<YOUR-IP>:8094/out/epg.xml       → XMLTV guide
http://<YOUR-IP>:8094/playlist.m3u      → M3U with eplus1–eplus40
http://<YOUR-IP>:8094/whatson_all       → quick view of all lanes
```

---

## 🚀 Quick Start (Git + Compose — power without Portainer)

```bash
# 1) clone
git clone https://github.com/kineticman/ESPN4CC4C.git
cd ESPN4CC4C

# 2) (optional) adjust PORT/paths/IPs inside docker-compose.yml
#    set VC_RESOLVER_BASE_URL and CC_HOST to your host IP

# 3) bring it up
mkdir -p data out logs
docker compose up -d

# 4) verify
curl -fsS "http://<YOUR-IP>:8094/health" && echo
curl -fsS "http://<YOUR-IP>:8094/out/playlist.m3u" | head -n 20
```

---

## ➕ Add to Channels DVR
- **XMLTV:** `http://<YOUR-IP>:8094/out/epg.xml`
- **M3U:**   `http://<YOUR-IP>:8094/playlist.m3u`

You’ll see **ESPN+ EPlus 1…40** with guide data.

---

## 🎛️ Editing Filters (keep only what you care about)
`filters.ini` lets you whitelist/blacklist by network, sport, league, event type, and platform.

### 1) Generate a starter `filters.ini`
*(works best after first refresh so counts are meaningful)*

**Inside the container**
```bash
docker compose exec espn4cc4c bash -lc "python3 /app/bin/generate_filter_options.py /app/data/eplus_vc.sqlite3 --generate-config" > filters.ini
```

**Or on the host (if Python 3 is installed)**
```bash
python3 bin/generate_filter_options.py ./data/eplus_vc.sqlite3 --generate-config > filters.ini
```

### 2) Edit `filters.ini`
Examples:

**ESPN+ only, no replays**
```ini
[filters]
require_espn_plus = true
exclude_event_types = OVER
```

**Limit by sport**
```ini
[filters]
enabled_sports = Hockey,Soccer
```

**Pro leagues only**
```ini
[filters]
enabled_leagues = NHL,MLS,NBA,NFL
```

**Network allow‑list**
```ini
[filters]
enabled_networks = ESPN,ESPN2,ESPNU,ESPN+
```

### 3) Rebuild the schedule
```bash
# triggers ingest/plan/write (uses the in‑container scripts)
docker compose exec espn4cc4c bash -lc "/app/bin/refresh_in_container.sh"
```

### 4) Confirm the effect quickly
```
GET http://<YOUR-IP>:8094/whatson_all?format=txt
```
You should see lane snapshots that reflect your filter changes.

**Reference keys**
- `enabled_networks`, `exclude_networks`
- `enabled_sports`, `exclude_sports`
- `enabled_leagues`, `exclude_leagues`
- `enabled_event_types` (e.g., `LIVE,UPCOMING`)
- `exclude_event_types` (e.g., `OVER` to drop replays)
- `require_espn_plus` (true/false)
- `exclude_ppv` (true)

---

## 🔎 API Cheat‑Sheet
- `GET /health` → service OK
- `GET /whatson_all?format=json|txt` → all lanes at a glance
- `GET /whatson/{lane}?format=json|txt` → a single lane
- `GET /deeplink/{lane}` → when available, returns a `sportscenter://…` URL (handy for ADBTuner)
- Outputs for Channels: `GET /out/epg.xml`, `GET /out/playlist.m3u`

---

## 🧰 Operations

**Manual refresh now**
```bash
docker compose exec espn4cc4c bash -lc "/app/bin/refresh_in_container.sh"
```

**View logs**
```bash
docker compose logs -f --tail=200
```

**First‑run note**
If you see `logs/cron_refresh.log` missing, it’s normal before the first cron or manual refresh. Run the command above once and re‑check.

---

## 🆘 Troubleshooting
- **Health fails**: ensure Docker is running and your chosen `PORT` is free.
- **Nothing in M3U/XML**: check `/whatson_all`; review filters; run a manual refresh.
- **Hostname doesn’t resolve**: use IPs or ensure your LAN/Tailscale DNS resolves hostnames; `dns_search` alone doesn’t create DNS.
- **Large Docker logs**: rotation is enabled (10MB×5). You can tune under `logging` in compose.

---

## Security & Policies
- No proxies for ESPN endpoints.
- GET‑only for checks (no HEAD requests).
- Don’t expose the service publicly; it’s designed for trusted LAN use.

---

## Credits & Links
- GitHub: https://github.com/kineticman/ESPN4CC4C
- GHCR image: https://github.com/kineticman/ESPN4CC4C/pkgs/container/espn4cc4c
- Channels DVR: https://getchannels.com/

---

*Have an improvement? PRs welcome. Tell us what you expected vs. what happened and include the logs snippet if possible.*
