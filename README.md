# ESPN4CC4C — ESPN+ Virtual Channels for Channels DVR

Turn ESPN+ events into **stable virtual channels** (eplus1–eplus40) your **Channels DVR** can ingest via **XMLTV** and **M3U** — all in one Docker service.

> **Current Version:** v5.2.x (2025-02-14+) — PrismCast support, improved admin interface, in-process scheduler (APScheduler), and comprehensive event filtering.

---

## 🆕 What's New

### v5.2.x — PrismCast & Polish
- **PrismCast M3U output** ⭐ **NEW**: Third M3U export format enabling native app launching for ESPN content
  - `playlist.prismcast.m3u` - Launch ESPN/WatchESPN apps directly instead of browser-only
  - Readable URLs (no URL encoding) for easier debugging
  - Uses `/play` endpoint with raw URL parameters
  - Configured via `PCAST_SERVER` and `PCAST_PORT` environment variables
  - All three M3U formats (CC, CH4C, PrismCast) generated simultaneously
- **Polished admin interface**: Improved layout and organization of admin pages
- **Enhanced documentation**: Comprehensive guides for all M3U formats

### v5.1.x — Event Padding & Advanced Filtering
- **Admin pages**: `/admin` hub linking to all useful endpoints; `/admin/refresh` shows scheduler status with manual trigger buttons
- **Event Padding**: Configurable pre/post padding for live sports to handle overtime and early starts
  - `PADDING_START_MINS` - Minutes before event (catch pre-game/early starts)
  - `PADDING_END_MINS` - Minutes after event (catch overtime/extra innings)
  - `PADDING_LIVE_ONLY` - Smart detection: only pad live sports, skip studio shows (default: true)
- **Environment variable filtering**: Configure all filters via env vars (no INI file required!)
  - 16 filter variables: networks, sports, leagues, languages, ESPN+, PPV, replays, and more
  - Priority: **Env Vars > filters.ini > Defaults**
  - `/setupfilters` helper UI to explore available values
- **Built-in scheduler (APScheduler)**: Runs inside FastAPI (no system cron needed)
  - Daily refresh at **03:00**
  - Weekly SQLite VACUUM on Sundays at **03:10**
  - Weekly log cleanup on Sundays at **03:30**
- **Improved XMLTV**: Content classification, richer categories, multi-feed game labels (NHL/NBA home & away broadcasts)
- **Channels-4-Chrome M3U**: Optional `playlist.ch4c.m3u` for HTTP-only launchers

---

## 🚀 Quick Start (Portainer — Recommended)

This is the easiest flow for Channels DVR users.

### 1. Open Portainer → Stacks → Add Stack

**Name:** `espn4cc4c`

### 2. Paste this compose YAML:

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
      # Core settings
      - TZ=${TZ:-America/New_York}
      - VC_RESOLVER_BASE_URL=${VC_RESOLVER_BASE_URL:-http://192.0.2.10:8094}
      - PORT=${PORT:-8094}
      - APP_MODULE=${APP_MODULE:-bin.vc_resolver:app}
      
      # Channel configuration
      - LANES=${LANES:-40}
      - VALID_HOURS=${VALID_HOURS:-72}
      - ALIGN=${ALIGN:-30}
      - MIN_GAP_MINS=${MIN_GAP_MINS:-30}
      - M3U_GROUP_TITLE=${M3U_GROUP_TITLE:-ESPN+ VC}
      
      # Chrome Capture (standard)
      - CC_HOST=${CC_HOST:-192.0.2.10}
      - CC_PORT=${CC_PORT:-5589}
      
      # Channels-4-Chrome (optional)
      - CH4C_HOST=${CH4C_HOST:-127.0.0.1}
      - CH4C_PORT=${CH4C_PORT:-2442}
      
      # PrismCast (optional, for native app launching)
      - PCAST_SERVER=${PCAST_SERVER:-127.0.0.1}
      - PCAST_PORT=${PCAST_PORT:-5589}
      
      # ESPN Watch API
      - WATCH_API_KEY=${WATCH_API_KEY:-0dbf88e8-cc6d-41da-aa83-18b5c630bc5c}
      
      # Optional: Event padding (handle games that run long)
      # - PADDING_START_MINS=${PADDING_START_MINS:-0}
      # - PADDING_END_MINS=${PADDING_END_MINS:-30}
      # - PADDING_LIVE_ONLY=${PADDING_LIVE_ONLY:-true}
      
      # Optional: Event filtering examples (see Filtering section)
      # - FILTER_EXCLUDE_NETWORKS=ESPN,ESPN2,ESPNU,ESPNDeportes,ESPNEWS
      # - FILTER_REQUIRE_ESPN_PLUS=true
      # - FILTER_EXCLUDE_PPV=true
      # - FILTER_EXCLUDE_REAIR=true

    volumes:
      - ${HOST_DIR:-.}/data:/app/data
      - ${HOST_DIR:-.}/out:/app/out
      - ${HOST_DIR:-.}/logs:/app/logs

    # Optional DNS search (suffix matching, not resolution)
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

### 3. Configure Environment Variables

In Portainer's "Environment variables" panel, set:

**Required:**
- `TZ=America/New_York` (your timezone)
- `VC_RESOLVER_BASE_URL=http://<YOUR-IP>:8094`
- `CC_HOST=<YOUR-IP>` (your server's IP or hostname)

**Optional:**
- `HOST_DIR=/data/espn4cc4c` (custom host path for data/out/logs)
- `CH4C_HOST` / `CH4C_PORT` (if using Channels-4-Chrome)
- `PCAST_SERVER` / `PCAST_PORT` (if using PrismCast for native apps)
- `PADDING_START_MINS=0` / `PADDING_END_MINS=30` (event padding)

### 4. Deploy the Stack

### 5. Verify Installation

Open in browser or use curl:

```bash
http://<YOUR-IP>:8094/health              # Health check
http://<YOUR-IP>:8094/admin               # Admin dashboard
http://<YOUR-IP>:8094/epg.xml             # XMLTV guide
http://<YOUR-IP>:8094/playlist.m3u        # Chrome Capture M3U
http://<YOUR-IP>:8094/playlist.ch4c.m3u   # Channels4Chrome M3U
http://<YOUR-IP>:8094/playlist.prismcast.m3u  # PrismCast M3U (NEW!)
http://<YOUR-IP>:8094/whatson_all         # Quick lane preview
```

---

## 🚀 Quick Start (Git + Compose)

For users who prefer git clone and docker compose:

```bash
# 1. Clone repository
git clone https://github.com/kineticman/ESPN4CC4C.git
cd ESPN4CC4C

# 2. (Optional) Edit docker-compose.yml
#    - Set VC_RESOLVER_BASE_URL and CC_HOST to your server IP
#    - Adjust PORT, PCAST_SERVER, or other settings as needed

# 3. Create directories and start container
mkdir -p data out logs
docker compose up -d

# 4. Verify installation
curl -fsS "http://<YOUR-IP>:8094/health" && echo "✓ Service is healthy"
curl -fsS "http://<YOUR-IP>:8094/playlist.m3u" | head -n 20
```

---

## ➕ Add to Channels DVR

### Choose Your M3U Format

ESPN4CC4C generates **three M3U formats** simultaneously:

| Format | File | URL | Best For |
|--------|------|-----|----------|
| **Chrome Capture** | `playlist.m3u` | `/playlist.m3u` | Standard browser-based playback (recommended for most users) |
| **Channels4Chrome** | `playlist.ch4c.m3u` | `/playlist.ch4c.m3u` | HTTP-only launchers, CH4C bridge |
| **PrismCast** ⭐ **NEW** | `playlist.prismcast.m3u` | `/playlist.prismcast.m3u` | **Native app launching** (ESPN/WatchESPN apps) |

### Configure in Channels DVR

1. **Open Channels DVR Settings → Custom Channels**
2. **Add Source**
3. **Configure URLs:**
   - **XMLTV Guide:** `http://<YOUR-IP>:8094/epg.xml`
   - **M3U Playlist:** Choose one:
     - Chrome Capture: `http://<YOUR-IP>:8094/playlist.m3u`
     - Channels4Chrome: `http://<YOUR-IP>:8094/playlist.ch4c.m3u`
     - PrismCast: `http://<YOUR-IP>:8094/playlist.prismcast.m3u`

You'll see **ESPN+ EPlus 1–40** channels with full guide data.

### M3U Format Details

**Chrome Capture (Standard)**
```
chrome://192.0.2.10:5589/stream?url=http%3A%2F%2F192.0.2.10%3A8094%2Fvc%2Feplus1
```
- Uses `chrome://` protocol
- URL-encoded parameters
- Browser-based playback via Chrome Capture proxy

**Channels4Chrome**
```
http://127.0.0.1:2442/stream?url=http%3A%2F%2F192.0.2.10%3A8094%2Fvc%2Feplus1
```
- Uses `http://` protocol
- URL-encoded parameters
- HTTP-only bridge for systems that don't support `chrome://`

**PrismCast (Native Apps)** ⭐ **NEW**
```
http://127.0.0.1:5589/play?url=http://192.0.2.10:8094/vc/eplus1
```
- Uses `http://` protocol with `/play` endpoint
- Raw URL parameters (not encoded)
- **Launches native ESPN/WatchESPN apps** instead of browser
- More readable URLs for debugging
- Requires separate PrismCast server (configured to recognize ESPN domains)

**PrismCast Configuration:**
- Set `PCAST_SERVER` to your PrismCast host/IP
- Set `PCAST_PORT` to your PrismCast port (typically 5589)
- Configure PrismCast profiles to recognize ESPN domains and launch appropriate apps
- See PrismCast documentation for profile configuration details

---

## 🏒 Multi-Feed Games (NHL / NBA Home & Away Broadcasts)

Some ESPN+ games—especially **NHL** and **NBA**—include multiple feeds (home broadcast, away broadcast, national feed). ESPN4CC4C keeps all available feeds and labels them clearly:

- Each feed becomes a separate `<programme>` entry in `epg.xml`
- When ESPN provides feed metadata, descriptions are annotated:
  - `Bruins vs Ducks • Bruins broadcast`
  - `Bruins vs Ducks • Ducks broadcast`
- In Channels DVR, you'll see multiple entries with the same title/time but different descriptions
- Choose the feed you want without trial-and-error

---

## ⏱️ Event Padding (Handle Games That Run Long)

Live sports often exceed their scheduled duration. Event padding extends start/end times in your EPG to ensure recordings capture the entire event.

### Why Padding?

- **Football games** can run 3.5+ hours with overtime (scheduled for 3 hours)
- **Baseball games** can go 12+ innings
- **Basketball games** can have multiple overtimes
- **Pre-game shows** sometimes start earlier than scheduled

### Configuration

```yaml
environment:
  - PADDING_START_MINS=5    # Start recording 5 minutes early
  - PADDING_END_MINS=30     # Keep recording 30 minutes past scheduled end
  - PADDING_LIVE_ONLY=true  # Only pad live sports (skip studio shows)
```

### How It Works

1. **Smart Detection**: Automatically identifies live sports events vs studio shows/replays
2. **Selective Padding**: Only pads events marked as live (unless `PADDING_LIVE_ONLY=false`)
3. **EPG Integration**: Modified times appear in XMLTV guide automatically
4. **Comprehensive Logging**: Every padded event logged for audit trail

### Configuration Options

| Variable | Default | Description |
|----------|---------|-------------|
| `PADDING_START_MINS` | `0` | Minutes to add before event start |
| `PADDING_END_MINS` | `0` | Minutes to add after event end |
| `PADDING_LIVE_ONLY` | `true` | Only pad live events (skip studio shows/replays) |

### Example Scenarios

**Conservative (catch overtime only):**
```yaml
- PADDING_START_MINS=0
- PADDING_END_MINS=30
- PADDING_LIVE_ONLY=true
```

**Aggressive (catch everything):**
```yaml
- PADDING_START_MINS=10
- PADDING_END_MINS=60
- PADDING_LIVE_ONLY=true
```

**Pad everything including studio shows:**
```yaml
- PADDING_START_MINS=5
- PADDING_END_MINS=30
- PADDING_LIVE_ONLY=false
```

### What Gets Padded?

✅ **Padded:**
- Live sports events (NFL, NBA, MLB, NHL, etc.)
- Events marked as "LIVE" in ESPN data

❌ **Not Padded (when PADDING_LIVE_ONLY=true):**
- Studio shows (SportsCenter, Get Up, etc.)
- Replays/re-airs
- Upcoming events (not yet started)
- Shows without sport classification

### Verification

Check padded events in logs:
```bash
docker compose logs | grep "Padding applied"
```

Or review the EPG to see modified times:
```bash
curl http://<YOUR-IP>:8094/epg.xml | grep -A 5 "padding"
```

---

## 🔧 Event Filtering

Filter events by network, sport, league, language, or content type using environment variables.

### Quick Examples

**ESPN+ content only (exclude linear networks):**
```yaml
environment:
  - FILTER_REQUIRE_ESPN_PLUS=true
  - FILTER_EXCLUDE_NETWORKS=ESPN,ESPN2,ESPNU,ESPNDeportes,ESPNEWS
```

**No Pay-Per-View or replays:**
```yaml
environment:
  - FILTER_EXCLUDE_PPV=true
  - FILTER_EXCLUDE_REAIR=true
```

**Specific sports only:**
```yaml
environment:
  - FILTER_ENABLED_SPORTS=Football,Basketball,Baseball,Hockey
```

**Pro leagues only:**
```yaml
environment:
  - FILTER_ENABLED_LEAGUES=NFL,NBA,MLB,NHL
```

**College sports only:**
```yaml
environment:
  - FILTER_ENABLED_LEAGUES=NCAA
  - FILTER_PARTIAL_LEAGUE_MATCH=true
```

**No Spanish content:**
```yaml
environment:
  - FILTER_EXCLUDE_LANGUAGES=es,spa,spanish
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
| `FILTER_ENABLED_EVENT_TYPES` | `*` | Event types (LIVE, REPLAY, etc.) |
| `FILTER_EXCLUDE_EVENT_TYPES` | `` | Event types to exclude |
| `FILTER_ENABLED_LANGUAGES` | `*` | Languages (`en`, `es`, etc.) |
| `FILTER_EXCLUDE_LANGUAGES` | `` | Languages to exclude |
| `FILTER_REQUIRE_ESPN_PLUS` | `` | `true`=ESPN+ only, `false`=exclude ESPN+ |
| `FILTER_EXCLUDE_PPV` | `false` | Exclude Pay-Per-View events |
| `FILTER_EXCLUDE_REAIR` | `false` | Exclude replays/re-airs |
| `FILTER_EXCLUDE_NO_SPORT` | `false` | Exclude studio shows |
| `FILTER_CASE_INSENSITIVE` | `true` | Case-insensitive matching |
| `FILTER_PARTIAL_LEAGUE_MATCH` | `true` | Allow partial league name matching |

**Priority:** Environment Variables > `filters.ini` > Defaults

### Filter Helper UI

Don't know what to filter? The built-in helper shows what's available:

```
http://<YOUR-IP>:8094/setupfilters
```

This page:
- Scans your current database
- Shows all distinct networks, sports, leagues, and packages
- Generates ready-to-copy filter snippets
- Available as JSON: `http://<YOUR-IP>:8094/filters/json`

### Using filters.ini (Legacy Alternative)

If you prefer INI files over environment variables:

```bash
# Generate starter config
docker compose exec espn4cc4c python3 /app/bin/generate_filter_options.py \
  /app/data/eplus_vc.sqlite3 --generate-config > filters.ini

# Edit filters.ini as needed
# Mount it: - ./filters.ini:/app/filters.ini

# Trigger refresh
docker compose exec espn4cc4c bash -lc "python3 /app/bin/refresh_in_container.py"
```

**Note:** Environment variables override `filters.ini` settings.

### Verify Results

After changing filters, check what's scheduled:

```
http://<YOUR-IP>:8094/whatson_all?format=txt
```

Shows a snapshot of all 40 lanes reflecting your active filters.

---

## 🔎 API Reference

### Core Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /health` | Health check (returns `{"ok": true}`) |
| `GET /admin` | Admin dashboard hub (links to all tools) |
| `GET /admin/refresh` | Refresh/VACUUM dashboard with manual triggers |

### Content Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /epg.xml` | XMLTV guide data |
| `GET /playlist.m3u` | Chrome Capture M3U |
| `GET /playlist.ch4c.m3u` | Channels4Chrome M3U |
| `GET /playlist.prismcast.m3u` | PrismCast M3U (native apps) |

### Debug & Inspection

| Endpoint | Description |
|----------|-------------|
| `GET /whatson_all?format=json\|txt` | All lanes at a glance |
| `GET /whatson/{lane}?format=json\|txt` | Single lane details |
| `GET /deeplink/{lane}` | ESPN deeplink URL for lane |
| `GET /setupfilters` | Interactive filter helper UI |
| `GET /filters/json` | Available filter values (JSON) |

### Admin Actions

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/admin/refresh/trigger` | POST | Trigger database refresh now |
| `/admin/vacuum/trigger` | POST | Trigger SQLite VACUUM now |

---

## 🧰 Operations

### Admin Dashboard (Recommended)

**Main Hub:**
```
http://<YOUR-IP>:8094/admin
```

Links to:
- Health checks
- EPG/M3U outputs (all three formats)
- Filter helpers
- Lane debugging tools
- Refresh/VACUUM dashboard

**Refresh Dashboard:**
```
http://<YOUR-IP>:8094/admin/refresh
```

Shows:
- Last refresh time and duration
- Last VACUUM time and duration
- Scheduler status
- Manual trigger buttons

### Manual Operations (Web)

**Trigger Refresh:**
1. Navigate to `http://<YOUR-IP>:8094/admin/refresh`
2. Click **"🔄 Trigger Refresh Now"**
3. Page shows status and progress

**Trigger VACUUM:**
1. Same page: `http://<YOUR-IP>:8094/admin/refresh`
2. Click **"🗄️ Run VACUUM Now"**
3. Compacts SQLite database

### Manual Operations (CLI)

**Refresh via CLI:**
```bash
docker compose exec espn4cc4c bash -lc "python3 /app/bin/refresh_in_container.py"
```

**View Logs:**
```bash
docker compose logs -f --tail=200
```

**Check Container Status:**
```bash
docker compose ps
docker compose exec espn4cc4c curl http://localhost:8094/health
```

### First-Run Note

On new installations, scheduler timestamps won't show until:
- First scheduled run occurs (3:00 AM for refresh, Sunday 3:10 AM for VACUUM)
- You manually trigger via `/admin/refresh`

Recommendation: Trigger a manual refresh after first deployment to seed the database.

---

## 🆘 Troubleshooting

### Common Issues

**Health check fails:**
- Ensure Docker is running
- Check that configured `PORT` (default 8094) is free
- Verify firewall allows connections on `PORT`

**No channels in M3U/EPG:**
- Check `/whatson_all` to see what's scheduled
- Review active filters (might be too restrictive)
- Trigger manual refresh via `/admin/refresh`
- Check container logs: `docker compose logs`

**Filters not working:**
- Verify environment variables are set correctly in `docker-compose.yml`
- Check container environment: `docker compose exec espn4cc4c env | grep FILTER`
- Look for "Active Filters" summary in refresh logs
- Remember: Environment variables override `filters.ini`

**PrismCast M3U not generating:**
- Verify `PCAST_SERVER` and `PCAST_PORT` are set
- Check that file exists: `docker compose exec espn4cc4c ls -la /app/out/playlist.prismcast.m3u`
- All three M3U files are always generated together

**Hostname doesn't resolve:**
- Use IP addresses instead of hostnames
- Ensure DNS can resolve your hostnames (LAN/Tailscale DNS)
- Note: `dns_search` only adds suffixes, doesn't create DNS entries

**Large Docker logs:**
- Log rotation is enabled (10MB × 5 files max)
- Adjust in `docker-compose.yml` under `logging.options`

**Events missing overtime/running long:**
- Configure event padding (see Event Padding section)
- Set `PADDING_END_MINS=30` or higher
- Check logs to confirm padding is applied: `grep "Padding applied"`

### Getting Help

**Check logs first:**
```bash
docker compose logs --tail=500 > espn4cc4c.log
```

**Verify configuration:**
```bash
docker compose config
docker compose exec espn4cc4c env | sort
```

**Test individual components:**
```bash
# Health
curl http://<YOUR-IP>:8094/health

# EPG
curl -I http://<YOUR-IP>:8094/epg.xml

# M3U
curl -I http://<YOUR-IP>:8094/playlist.m3u
curl -I http://<YOUR-IP>:8094/playlist.prismcast.m3u

# Lanes
curl http://<YOUR-IP>:8094/whatson_all?format=txt
```

---

## 📊 Performance & Resource Usage

### Typical Resource Usage
- **CPU:** Minimal during normal operation; brief spikes during refresh
- **RAM:** ~200-300MB typical, ~500MB during refresh
- **Disk:** 
  - Database: 50-150MB (depends on filtering)
  - Logs: 50MB max (with rotation)
  - Total: <500MB

### Refresh Timing
- **Daily refresh:** ~2-5 minutes (depends on network speed)
- **Weekly VACUUM:** ~30-60 seconds
- **Scheduled times:** 
  - Refresh: 3:00 AM daily
  - VACUUM: 3:10 AM Sundays
  - Log cleanup: 3:30 AM Sundays

### Optimization Tips
- Use event filtering to reduce database size
- Run VACUUM periodically (automated weekly)
- Enable log rotation (already configured)
- Consider `VALID_HOURS=48` instead of `72` to reduce EPG size

---

## 🔐 Security & Best Practices

### Security Guidelines
- **Do NOT expose publicly** — designed for trusted LAN use only
- Use within your local network or VPN (Tailscale, etc.)
- No authentication built-in (rely on network security)
- ESPN account credentials handled by ESPN's servers (OAuth flow)

### Best Practices
- Keep container image updated
- Use specific version tags instead of `:latest` in production
- Monitor logs for unusual activity
- Back up database periodically: `data/eplus_vc.sqlite3`
- Review filters regularly to match your viewing preferences

---

## 🔄 Updates & Maintenance

### Updating the Container

**Using Portainer:**
1. Navigate to Stacks → espn4cc4c
2. Click "Pull and redeploy"

**Using Docker Compose:**
```bash
docker compose pull
docker compose up -d
```

### Database Maintenance

**Automatic:**
- Weekly VACUUM (Sundays 3:10 AM)
- Automatic index optimization
- Log rotation (10MB × 5 files)

**Manual:**
- Trigger VACUUM via `/admin/refresh` dashboard
- CLI: `docker compose exec espn4cc4c sqlite3 /app/data/eplus_vc.sqlite3 'VACUUM;'`

### Backup

**Database backup:**
```bash
docker compose exec espn4cc4c sqlite3 /app/data/eplus_vc.sqlite3 '.backup /app/data/backup.db'
docker compose cp espn4cc4c:/app/data/backup.db ./backup-$(date +%Y%m%d).db
```

---

## 📚 Additional Resources

### Documentation Files
- `ESPN4CC4C_PRISMCAST_INTEGRATION.md` - Technical details on PrismCast implementation
- `PRISMCAST_QUICKSTART.md` - User guide for PrismCast M3U format
- `.env.example` - Complete environment variable reference

### Related Projects
- **Channels DVR:** https://getchannels.com/
- **Chrome Capture:** Browser-based video capture for Channels
- **Channels-4-Chrome:** HTTP bridge for Chrome Capture
- **PrismCast:** Native app launcher for streaming content

### Community & Support
- **GitHub Repository:** https://github.com/kineticman/ESPN4CC4C
- **Container Registry:** https://github.com/kineticman/ESPN4CC4C/pkgs/container/espn4cc4c
- **Issues:** https://github.com/kineticman/ESPN4CC4C/issues

---

## 🤝 Contributing

Improvements welcome! When submitting PRs or issues:

1. **Describe what you expected vs. what happened**
2. **Include relevant logs** (sanitize personal info)
3. **List your environment:**
   - Docker version
   - OS/platform
   - ESPN4CC4C version/tag
   - Relevant environment variables
4. **Steps to reproduce** (if reporting a bug)

---

## 📝 License & Credits

**License:** MIT (see LICENSE file)

**Credits:**
- ESPN Watch API integration
- Built with FastAPI, APScheduler, SQLite
- Container orchestration via Docker Compose
- Integration designed for Channels DVR ecosystem

**Author:** kineticman
**Repository:** https://github.com/kineticman/ESPN4CC4C

---

*Last updated: 2025-02-14*
