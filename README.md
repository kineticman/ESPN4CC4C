# ESPN4CC4C - Docker Edition

## Overview

**ESPN4CC4C (ESPN+ for Chrome Capture for Channels)** provides a fully containerized system that turns ESPN+ content into virtual live channels compatible with Channels DVR. The service runs as a single Docker container and exposes XMLTV and M3U endpoints for easy DVR integration.

---

## Features

- 40 automatically managed virtual channels
- Full XMLTV guide (EPG) generation
- Integrated scheduling and auto-updates
- Persistent SQLite database for stored events and metadata
- Dynamic M3U playlist generation for Chrome Capture
- Health monitoring and cron-based auto-refresh
- Simple Docker deployment

---

## Prerequisites

- Docker Engine 20.10+
- Docker Compose 2.0+
- Network access to ESPN+ APIs
- Channels DVR (optional but recommended)

---

## Quick Start

### 1. Clone the Repository

```bash
git clone https://github.com/kineticman/ESPN4CC4C.git
cd ESPN4CC4C
```

### 2. Configure Environment

Find your LAN IP:

```bash
hostname -I | awk '{print $1}'
```

Copy the example environment file and edit:

```bash
cp .env.example .env
nano .env
```

Example:

```bash
VC_RESOLVER_BASE_URL=http://192.168.1.50:8094
TZ=America/New_York
```

### 3. Build and Start

```bash
docker compose build
docker compose up -d
```

Check that the container is running:

```bash
curl http://192.168.1.50:8094/health
```

---

## Chrome Capture Integration

If you use **Chrome Capture (cc4c)** to display streams, you can configure which host and port the generated M3U uses.

Add the following to your `.env` file:

```bash
CC_HOST=TYPE YOUR ACTUAL CC4C SERVER LAN IP HERE (IE 192.168.55.55)
CC_PORT=5589
```

If your Chrome Capture runs on another port (for example 5599):

```bash
CC_PORT=5599
```

Then rebuild and restart:

```bash
docker compose up -d --build
```

The system will automatically generate a dynamic playlist:

```
http://YOUR_IP:8094/playlist_cc.m3u
```

Example entry:

```
chrome://192.168.86.72:5589/stream?url=http%3A%2F%2F192.168.86.72%3A8094%2Fvc%2Feplus1
```

> `/playlist_cc.m3u` respects your `.env` settings for Chrome Capture.
> `/playlist.m3u` remains available as the static version.

---

## Channels DVR Integration

### Add as a Source

1. Open Channels DVR settings  
2. Navigate to **Sources → Add Source → M3U Playlist**  
3. Enter:  
   - **M3U URL:** `http://YOUR_IP:8094/playlist_cc.m3u`  
   - **XMLTV URL:** `http://YOUR_IP:8094/epg.xml`  
4. Save and scan channels

Expected results:
- 40 ESPN+ virtual channels (EPlus 1–40)
- Channel numbers 20010–20049
- Full 72-hour guide data

---

## Configuration

### Environment Variables

| Variable | Default | Description |
|-----------|----------|-------------|
| `VC_RESOLVER_BASE_URL` | *(required)* | Base resolver URL, usually `http://LAN_IP:8094` |
| `CC_HOST` | Auto-detected | Chrome Capture host |
| `CC_PORT` | 5589 | Chrome Capture port |
| `TZ` | America/New_York | Timezone for scheduling |
| `SCHEDULE_HOURS` | 6 | Update frequency (hours) |
| `VALID_HOURS` | 72 | Planning window (hours) |
| `LANES` | 40 | Number of virtual channels |
| `PORT` | 8094 | FastAPI port |

Restart to apply changes:

```bash
docker compose restart
```

---

## API Endpoints

| Endpoint | Description |
|-----------|-------------|
| `/health` | Health status JSON |
| `/epg.xml` | XMLTV guide data |
| `/playlist.m3u` | Static M3U playlist |
| `/playlist_cc.m3u` | Chrome Capture dynamic M3U |
| `/vc/{channel}` | Redirect to current event |
| `/vc/{channel}/debug` | Detailed debug info |

---

## Common Commands

```bash
# Start container
docker compose up -d

# Stop container
docker compose down

# Logs
docker compose logs -f

# Rebuild
docker compose up -d --build

# Database check
docker compose exec espn4cc sqlite3 /app/data/eplus_vc.sqlite3 "SELECT COUNT(*) FROM events;"
```

---

## Troubleshooting

**Port in use:**  
If port 8094 is occupied:

```bash
sudo lsof -i :8094
sudo systemctl stop vc-resolver-v2.service
```

**Wrong LAN IP:**  
Ensure `.env` has your correct address:

```bash
VC_RESOLVER_BASE_URL=http://192.168.1.50:8094
docker compose restart
```

**No EPG updates:**  
Check logs:

```bash
docker compose exec espn4cc tail -f /app/logs/schedule.log
```

---

## Project Information

**License:** MIT  
**Maintainer:** kineticman  
**Repository:** [github.com/kineticman/ESPN4CC4C](https://github.com/kineticman/ESPN4CC4C)

This project is not affiliated with or endorsed by ESPN, Disney, or Channels DVR.

