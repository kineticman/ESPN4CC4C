# ESPN4CC4C

ESPN+ virtual channels for [Channels DVR](https://getchannels.com/).

ESPN4CC4C turns the ESPN+ event schedule into 40 stable virtual channels (`eplus1`–`eplus40`) and serves them to Channels DVR as an XMLTV guide plus an M3U playlist, all from a single Docker container.

> **Project status: no longer maintained.**
> This project has not been updated in a long time and is dated. Please use **[FastChannels](https://github.com/kineticman/FastChannels)** instead. It is actively maintained and provides M3U/XMLTV output with a web admin console. This repository is kept for reference only.

## Contents

- [Features](#features)
- [Quick start](#quick-start)
- [Adding to Channels DVR](#adding-to-channels-dvr)
- [Configuration](#configuration)
- [Event filtering](#event-filtering)
- [Event padding](#event-padding)
- [HTTP endpoints](#http-endpoints)
- [Operations](#operations)
- [Troubleshooting](#troubleshooting)
- [Security](#security)
- [Documentation](#documentation)
- [License and credits](#license-and-credits)

## Features

- 40 virtual channels with a rolling XMLTV guide (default 72 hours)
- Three M3U formats generated together: Chrome Capture, Channels4Chrome and PrismCast
- Event filtering by network, sport, league, language and content type, configurable through environment variables or `filters.ini`
- Configurable pre/post event padding so recordings of live sports are not cut off by overtime
- Labels for multi-feed games (for example home and away broadcasts for NHL and NBA)
- Built-in scheduler (APScheduler) with a daily refresh, weekly SQLite `VACUUM` and weekly log cleanup, so no system cron is needed
- Admin dashboard with manual refresh and `VACUUM` triggers

## Quick start

### Docker Compose

```bash
git clone https://github.com/kineticman/ESPN4CC4C.git
cd ESPN4CC4C

# Edit docker-compose.yml (or create a .env file) and set at least:
#   VC_RESOLVER_BASE_URL=http://<YOUR-IP>:8094
#   CC_HOST=<YOUR-IP>

mkdir -p data out logs
docker compose up -d

curl -fsS http://<YOUR-IP>:8094/health
```

The published image is `ghcr.io/kineticman/espn4cc4c`. Pin a specific tag rather than `latest` for anything long-lived.

### Portainer

1. Go to **Stacks → Add stack** and name it `espn4cc4c`.
2. Paste the contents of [`docker-compose.yml`](docker-compose.yml).
3. Set the required environment variables (below) and deploy.

Windows and Linux helper scripts (`setup-windows.ps1`, `setup-linux.sh`) are described in [DOCKER.md](DOCKER.md).

### Verify

| URL | Purpose |
|-----|---------|
| `/health` | Health check |
| `/admin` | Admin dashboard |
| `/epg.xml` | XMLTV guide |
| `/playlist.m3u` | Chrome Capture M3U |
| `/playlist.ch4c.m3u` | Channels4Chrome M3U |
| `/playlist.prismcast.m3u` | PrismCast M3U |
| `/whatson_all` | What is on every lane right now |

On a new install, trigger a manual refresh from `/admin/refresh` so the database is populated before the first scheduled run (03:00 daily).

## Adding to Channels DVR

1. In Channels DVR, open **Settings → Sources → Custom Channels** and add a source.
2. Set the **XMLTV guide** to `http://<YOUR-IP>:8094/epg.xml`.
3. Set the **M3U playlist** to one of the formats below.

The channels appear as **ESPN+ EPlus 1–40** with guide data.

| Format | Playlist | Use when |
|--------|----------|----------|
| Chrome Capture | `/playlist.m3u` | Standard browser-based playback (most users) |
| Channels4Chrome | `/playlist.ch4c.m3u` | You use the Channels4Chrome HTTP bridge |
| PrismCast | `/playlist.prismcast.m3u` | You run a PrismCast server that launches native ESPN apps |

Example entries for `eplus1`:

```text
# Chrome Capture
chrome://192.0.2.10:5589/stream?url=http%3A%2F%2F192.0.2.10%3A8094%2Fvc%2Feplus1

# Channels4Chrome
http://127.0.0.1:2442/stream?url=http%3A%2F%2F192.0.2.10%3A8094%2Fvc%2Feplus1

# PrismCast
http://127.0.0.1:5589/play?url=http://192.0.2.10:8094/vc/eplus1
```

For PrismCast, set `PCAST_SERVER` and `PCAST_PORT` to your PrismCast host, and configure PrismCast to recognize ESPN domains. See the PrismCast documentation for profile setup.

## Configuration

Settings are environment variables. [`.env.example`](.env.example) lists all of them.

**Required**

| Variable | Description |
|----------|-------------|
| `TZ` | Your timezone, for example `America/New_York` |
| `VC_RESOLVER_BASE_URL` | Base URL clients use to reach this service, for example `http://<YOUR-IP>:8094` |
| `CC_HOST` | Host or IP of your Chrome Capture server |

**Common options**

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `8094` | HTTP port |
| `LANES` | `40` | Number of virtual channels |
| `VALID_HOURS` | `72` | Length of the guide window |
| `ALIGN` | `30` | Slot alignment in minutes |
| `MIN_GAP_MINS` | `30` | Minimum gap between events on a lane |
| `M3U_GROUP_TITLE` | `ESPN+ VC` | Group title used in the playlists |
| `CC_PORT` | `5589` | Chrome Capture port |
| `CH4C_HOST` / `CH4C_PORT` | `127.0.0.1` / `2442` | Channels4Chrome bridge |
| `PCAST_SERVER` / `PCAST_PORT` | `127.0.0.1` / `5589` | PrismCast server |
| `HOST_DIR` | `.` | Host directory holding `data/`, `out/` and `logs/` |

## Event filtering

Filters are applied when the schedule is refreshed. Precedence is **environment variables > `filters.ini` > defaults**.

Examples:

```yaml
environment:
  # ESPN+ content only (drop linear networks)
  - FILTER_REQUIRE_ESPN_PLUS=true
  - FILTER_EXCLUDE_NETWORKS=ESPN,ESPN2,ESPNU,ESPNDeportes,ESPNEWS

  # No pay-per-view or replays
  - FILTER_EXCLUDE_PPV=true
  - FILTER_EXCLUDE_REAIR=true

  # Specific sports or leagues
  - FILTER_ENABLED_SPORTS=Football,Basketball,Baseball,Hockey
  - FILTER_ENABLED_LEAGUES=NFL,NBA,MLB,NHL

  # No Spanish-language events
  - FILTER_EXCLUDE_LANGUAGES=es,spa,spanish
```

| Variable | Default | Description |
|----------|---------|-------------|
| `FILTER_ENABLED_NETWORKS` / `FILTER_EXCLUDE_NETWORKS` | `*` / empty | Networks to include / exclude (comma-separated) |
| `FILTER_ENABLED_SPORTS` / `FILTER_EXCLUDE_SPORTS` | `*` / empty | Sports to include / exclude |
| `FILTER_ENABLED_LEAGUES` / `FILTER_EXCLUDE_LEAGUES` | `*` / empty | Leagues to include / exclude |
| `FILTER_ENABLED_EVENT_TYPES` / `FILTER_EXCLUDE_EVENT_TYPES` | `*` / empty | Event types (for example `LIVE`, `REPLAY`) |
| `FILTER_ENABLED_LANGUAGES` / `FILTER_EXCLUDE_LANGUAGES` | `*` / empty | Languages (`en`, `es`, ...) |
| `FILTER_REQUIRE_ESPN_PLUS` | unset | `true` = ESPN+ only, `false` = exclude ESPN+ |
| `FILTER_EXCLUDE_PPV` | `false` | Exclude pay-per-view events |
| `FILTER_EXCLUDE_REAIR` | `false` | Exclude replays and re-airs |
| `FILTER_EXCLUDE_NO_SPORT` | `false` | Exclude studio shows with no sport |
| `FILTER_CASE_INSENSITIVE` | `true` | Case-insensitive matching |
| `FILTER_PARTIAL_LEAGUE_MATCH` | `true` | Allow partial league-name matches |

**Finding valid values.** Open `/setupfilters` to list the networks, sports, leagues and packages currently in your database, with copy-ready snippets. The same data is at `/filters/json`.

**Using `filters.ini` instead.** Generate a starter file, mount it at `/app/filters.ini`, then trigger a refresh:

```bash
docker compose exec espn4cc4c python3 /app/bin/generate_filter_options.py \
  /app/data/eplus_vc.sqlite3 --generate-config > filters.ini
```

After changing filters, check `/whatson_all?format=txt` to see the result. More detail is in [docs/FILTERING_FAQ.md](docs/FILTERING_FAQ.md) and [docs/FILTER_ENV_VARS.md](docs/FILTER_ENV_VARS.md).

## Event padding

Live sports often run past their scheduled slot. Padding widens an event's start and end times in the guide so recordings capture the whole game.

| Variable | Default | Description |
|----------|---------|-------------|
| `PADDING_START_MINS` | `0` | Minutes added before the event start |
| `PADDING_END_MINS` | `0` | Minutes added after the event end |
| `PADDING_LIVE_ONLY` | `true` | Pad only live sports; skip studio shows, replays and events with no sport |

Suggested starting points:

```yaml
# Catch overtime only
- PADDING_START_MINS=0
- PADDING_END_MINS=30

# More generous
- PADDING_START_MINS=10
- PADDING_END_MINS=60
```

Padded events are logged. To confirm padding is applied:

```bash
docker compose logs | grep "Padding applied"
```

## HTTP endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /health` | Health check |
| `GET /admin` | Admin dashboard hub |
| `GET /admin/refresh` | Scheduler status and manual triggers |
| `POST /admin/refresh/trigger` | Run a refresh now |
| `POST /admin/vacuum/trigger` | Run a SQLite `VACUUM` now |
| `GET /epg.xml` | XMLTV guide |
| `GET /playlist.m3u` | Chrome Capture M3U |
| `GET /playlist.ch4c.m3u` | Channels4Chrome M3U |
| `GET /playlist.prismcast.m3u` | PrismCast M3U |
| `GET /whatson_all?format=json\|txt` | All lanes at a glance |
| `GET /whatson/{lane}?format=json\|txt` | One lane in detail |
| `GET /deeplink/{lane}` | ESPN deeplink for a lane |
| `GET /setupfilters` | Filter helper UI |
| `GET /filters/json` | Available filter values |

Full reference: [docs/api/API_DOCUMENTATION.md](docs/api/API_DOCUMENTATION.md).

## Operations

**Schedule (container timezone).** Refresh runs daily at 03:00. `VACUUM` runs Sundays at 03:10 and log cleanup at 03:30. A refresh typically takes 2–5 minutes. Expect roughly 200–300 MB of RAM, and under 500 MB of disk including logs.

**Common commands**

```bash
docker compose logs -f --tail=200                       # follow logs
docker compose exec espn4cc4c python3 /app/bin/refresh_in_container.py   # manual refresh
docker compose exec espn4cc4c sqlite3 /app/data/eplus_vc.sqlite3 'VACUUM;'
```

**Update**

```bash
docker compose pull && docker compose up -d
```

In Portainer, use **Stacks → espn4cc4c → Pull and redeploy**.

**Back up the database**

```bash
docker compose exec espn4cc4c sqlite3 /app/data/eplus_vc.sqlite3 '.backup /app/data/backup.db'
docker compose cp espn4cc4c:/app/data/backup.db ./backup-$(date +%Y%m%d).db
```

Docker logs are rotated (10 MB x 5 files). See [docs/LOG_ROTATION.md](docs/LOG_ROTATION.md).

## Troubleshooting

| Symptom | What to check |
|---------|---------------|
| Health check fails | Docker is running, `PORT` is free, firewall allows the port |
| No channels or empty guide | `/whatson_all` for what is scheduled; filters may be too strict; trigger a refresh at `/admin/refresh`; read `docker compose logs` |
| Filters have no effect | Variables are set in `docker-compose.yml`; `docker compose exec espn4cc4c env \| grep FILTER`; the refresh log prints the active filters; environment variables override `filters.ini` |
| PrismCast playlist missing | `PCAST_SERVER` and `PCAST_PORT` are set; `docker compose exec espn4cc4c ls -l /app/out/playlist.prismcast.m3u` (all three playlists are generated together) |
| Hostnames do not resolve | Use IP addresses; `dns_search` only adds search suffixes and does not create DNS records |
| Games cut off at the end | Increase `PADDING_END_MINS` |

When reporting a problem, include the output of `docker compose logs --tail=500`, `docker compose config`, your Docker version and platform, and the image tag. Remove personal information first.

## Security

- The service has **no authentication**. Run it on a trusted LAN or VPN (for example Tailscale) and do not expose it to the internet.
- ESPN account sign-in is handled by ESPN's own services.
- Pin image tags, and back up `data/eplus_vc.sqlite3` if you care about its state.

## Documentation

- [DOCKER.md](DOCKER.md): Docker setup details and helper scripts
- [CHANGELOG.md](CHANGELOG.md): release history
- [docs/](docs): filtering, log rotation and API references
- [contrib/cc4c](contrib/cc4c): Chrome Capture userscript

Related projects: [Channels DVR](https://getchannels.com/), Chrome Capture, Channels4Chrome, PrismCast.

## License and credits

No license file is currently included in this repository.

Built with FastAPI, APScheduler and SQLite, using ESPN's Watch API. Author: [kineticman](https://github.com/kineticman).
