# ESPN4CC4C — ESPN+ Virtual Channels for Channels DVR

Turn ESPN+ events into **stable virtual channels** (eplus1–eplus40) your **Channels DVR** can ingest via **XMLTV** and **M3U** — all in one Docker service.

> **Baseline:** v5.1.x (2025‑11‑12+) — prebuilt image with cron & tzdata; default onboarding = clone → `docker compose up`.

---

## 🆕 What’s new (v5.1.x+)

- **Compose‑only onboarding**: just drop a Portainer Stack or run `docker compose up` — no extra setup.
- **Built‑in cron**: auto refresh at **08:05 / 14:05 / 20:05**; weekly **VACUUM** Sun **03:10**.
- **Safer compose**: init‑enabled, graceful stop, `${PORT}`‑aware healthcheck, and log rotation.
- **Environment variable filtering** ⭐ **NEW**: Configure all filters via env vars in docker-compose.yml (no more INI file confusion!)
  - 16 filter variables covering networks, sports, leagues, languages, ESPN+, PPV, replays, and more
  - Priority: **Env Vars > filters.ini > Defaults**
  - See filtering section below for examples
- **Filtering workflow**: `filters.ini` still supported as fallback, plus `/whatson` views to confirm results fast.
- **Improved XMLTV**:
  - Adds an internal `content_kind` classifier (`sports_event` vs `sports_show` vs `other`) based on ESPN Watch Graph structure.
  - Exposes that to Channels as richer categories (e.g., **Sports** vs **Sports Talk**) and adds an **ESPN4CC4C** category tag for both sports and non‑sports events (not placeholders).
- **Experimental extra M3U for Channels‑4‑Chrome**:
  - Still writes the original Channels‑friendly M3U: `/out/playlist.m3u`.
  - Also writes `/out/playlist.ch4c.m3u` using plain `http://` URLs, controlled by `CH4C_HOST` / `CH4C_PORT` env vars.
  - Lets you point CH4C at the `.ch4c.m3u` while leaving Channels DVR on the standard M3U.

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
      - VC_RESOLVER_BASE_URL=${VC_RESOLVER_BASE_URL:-http://192.0.2.10:8094}
      - CC_HOST=${CC_HOST:-192.0.2.10}
      - CC_PORT=${CC_PORT:-5589}
      # Optional: Channels‑4‑Chrome (CH4C) bridge for http:// playlists
      - CH4C_HOST=${CH4C_HOST:-127.0.0.1}
      - CH4C_PORT=${CH4C_PORT:-2442}
      - PORT=${PORT:-8094}
      - APP_MODULE=${APP_MODULE:-bin.vc_resolver:app}
      - VALID_HOURS=${VALID_HOURS:-72}
      - LANES=${LANES:-40}
      - ALIGN=${ALIGN:-30}
      - MIN_GAP_MINS=${MIN_GAP_MINS:-30}
      - M3U_GROUP_TITLE=${M3U_GROUP_TITLE:-ESPN+ VC}
      - VC_M3U_PATH=${VC_M3U_PATH:-/app/out/playlist.m3u}
      - WATCH_API_KEY=${WATCH_API_KEY:-0dbf88e8-cc6d-41da-aa83-18b5c630bc5c}
      # Optional: Event filtering (see Filtering section below)
      # - FILTER_EXCLUDE_NETWORKS=ACCN,ESPN,ESPN2,ESPNDeportes,ESPNU
      # - FILTER_REQUIRE_ESPN_PLUS=true
      # - FILTER_EXCLUDE_PPV=true
      # - FILTER_EXCLUDE_REAIR=true

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
- *(optional)* `CH4C_HOST` / `CH4C_PORT` if CH4C lives somewhere other than `127.0.0.1:2442`

5) **Deploy the stack**

6) **Sanity checks (browser or curl)**
```text
http://<YOUR-IP>:8094/health             → {"ok": true}
http://<YOUR-IP>:8094/epg.xml        → XMLTV guide
http://<YOUR-IP>:8094/playlist.m3u       → M3U with eplus1–eplus40 (Channels)
http://<YOUR-IP>:8094/playlist.ch4c.m3u  → experimental M3U for CH4C
http://<YOUR-IP>:8094/whatson_all        → quick view of all lanes
```

---

## 🚀 Quick Start (Git + Compose — power without Portainer)

```bash
# 1) clone
git clone https://github.com/kineticman/ESPN4CC4C.git
cd ESPN4CC4C

# 2) (optional) adjust PORT/paths/IPs inside docker-compose.yml
#    set VC_RESOLVER_BASE_URL and CC_HOST to your host IP
#    optionally set CH4C_HOST / CH4C_PORT if using Channels-4-Chrome

# 3) bring it up
mkdir -p data out logs
docker compose up -d

# 4) verify
curl -fsS "http://<YOUR-IP>:8094/health" && echo
curl -fsS "http://<YOUR-IP>:8094/playlist.m3u" | head -n 20
```

---

## ➕ Add to Channels DVR

- **XMLTV:** `http://<YOUR-IP>:8094/out/epg.xml`
- **M3U (Channels DVR):** `http://<YOUR-IP>:8094/playlist.m3u`
- **M3U (CH4C, experimental):** `http://<YOUR-IP>:8094/out/playlist.ch4c.m3u` (for Channels‑4‑Chrome or other http‑only launchers)

You’ll see **ESPN+ EPlus 1…40** with guide data.

---

## 🎛️ Filtering Events (keep only what you care about)

**New in v5.1+:** Configure filters via **environment variables** (recommended) or `filters.ini` file. Environment variables take precedence and are easier to manage in Docker.

### Quick Filter Examples (Environment Variables)

Add these to your docker-compose.yml `environment:` section:

**ESPN+ only, no PPV/replays**
```yaml
environment:
  - FILTER_REQUIRE_ESPN_PLUS=true
  - FILTER_EXCLUDE_PPV=true
  - FILTER_EXCLUDE_REAIR=true
```

**Exclude ESPN linear networks (keep ESPN+, SEC, ACC, etc.)**
```yaml
environment:
  - FILTER_EXCLUDE_NETWORKS=ESPN,ESPN2,ESPNU,ESPNDeportes,ESPNEWS
```

**Only specific sports**
```yaml
environment:
  - FILTER_ENABLED_SPORTS=Football,Basketball,Baseball,Hockey
```

**Pro leagues only**
```yaml
environment:
  - FILTER_ENABLED_LEAGUES=NFL,NBA,MLB,NHL
```

**College sports only**
```yaml
environment:
  - FILTER_ENABLED_LEAGUES=NCAA
  - FILTER_PARTIAL_LEAGUE_MATCH=true
```

### All Filter Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `FILTER_ENABLED_NETWORKS` | `*` | Networks to include (comma-separated) |
| `FILTER_EXCLUDE_NETWORKS` | `` | Networks to exclude |
| `FILTER_ENABLED_SPORTS` | `*` | Sports to include |
| `FILTER_EXCLUDE_SPORTS` | `` | Sports to exclude |
| `FILTER_ENABLED_LEAGUES` | `*` | Leagues to include |
| `FILTER_EXCLUDE_LEAGUES` | `` | Leagues to exclude |
| `FILTER_ENABLED_EVENT_TYPES` | `*` | Event types to include |
| `FILTER_EXCLUDE_EVENT_TYPES` | `` | Event types to exclude |
| `FILTER_ENABLED_LANGUAGES` | `*` | Languages to include (`en`, `es`, etc.) |
| `FILTER_EXCLUDE_LANGUAGES` | `` | Languages to exclude |
| `FILTER_REQUIRE_ESPN_PLUS` | `` | `true` = ESPN+ only, `false` = exclude ESPN+ |
| `FILTER_EXCLUDE_PPV` | `false` | Exclude Pay-Per-View events |
| `FILTER_EXCLUDE_REAIR` | `false` | Exclude replays/re-airs |
| `FILTER_EXCLUDE_NO_SPORT` | `false` | Exclude studio shows/non-sport content |
| `FILTER_CASE_INSENSITIVE` | `true` | Case-insensitive matching |
| `FILTER_PARTIAL_LEAGUE_MATCH` | `true` | Allow partial league name matching |

### Discovery Tool: What content is available?

Generate a report showing all networks, sports, and leagues with event counts:

```bash
docker compose exec espn4cc4c python3 /app/bin/generate_filter_options.py /app/data/eplus_vc.sqlite3
```

### Alternative: Using filters.ini (Legacy)

If you prefer an INI file over environment variables:

**1) Generate starter config:**
```bash
docker compose exec espn4cc4c bash -lc "python3 /app/bin/generate_filter_options.py /app/data/eplus_vc.sqlite3 --generate-config" > filters.ini
```

**2) Edit `filters.ini`** at the repo root (will be `/app/filters.ini` in container)

**3) Rebuild schedule:**
```bash
docker compose exec espn4cc4c bash -lc "/app/bin/refresh_in_container.sh"
```

**Note:** Environment variables override INI file settings. Priority: **Env Vars > filters.ini > Defaults**

### Verify Filter Results

After changing filters, check what's in your channels:

```text
GET http://<YOUR-IP>:8094/whatson_all?format=txt
```

You'll see a snapshot of all 40 lanes reflecting your active filters.

---

## 🔎 API Cheat‑Sheet

- `GET /health` → service OK
- `GET /whatson_all?format=json|txt` → all lanes at a glance
- `GET /whatson/{lane}?format=json|txt` → a single lane
- `GET /deeplink/{lane}` → when available, returns a `sportscenter://…` URL (handy for ADBTuner / deep‑link launchers)
- Outputs for Channels:
  - `GET /out/epg.xml` → XMLTV
  - `GET /out/playlist.m3u` → standard M3U (Channels DVR)
  - `GET /out/playlist.ch4c.m3u` → experimental M3U (CH4C/http‑only)

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
- **Filters not working**: Ensure you're using environment variables correctly (see Filtering section). Check container logs during refresh to see "Active Filters" summary. Environment variables override `filters.ini`.
- **Hostname doesn’t resolve**: use IPs or ensure your LAN/Tailscale DNS resolves hostnames; `dns_search` alone doesn’t create DNS.
- **Large Docker logs**: rotation is enabled (10MB×5). You can tune under `logging` in compose.

---

## Security & Policies

- No proxies for ESPN endpoints.
- GET‑only for checks (avoid HEAD).
- Don’t expose the service publicly; it’s designed for trusted LAN use.

---

## Credits & Links

- GitHub: https://github.com/kineticman/ESPN4CC4C
- GHCR image: https://github.com/kineticman/ESPN4CC4C/pkgs/container/espn4cc4c
- Channels DVR: https://getchannels.com/

---

*Have an improvement? PRs welcome. Tell us what you expected vs. what happened and include the logs snippet if possible.*
