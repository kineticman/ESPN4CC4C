# 🏈 ESPN4CC4C - Docker Edition

> **ESPN+ for Chrome Capture For Channels** - Dockerized for easy deployment

Transform ESPN+ content into 40 virtual channels for your Channels DVR, all running in a single, self-contained Docker container.

[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?logo=docker&logoColor=white)](https://www.docker.com/)
[![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

-----

## ✨ Features

- 🎯 **40 Virtual Channels** - Automatically organized ESPN+ streams
- 📺 **Full EPG Support** - XMLTV guide data for all channels
- 🔄 **Auto-Scheduling** - Smart event planning with no overlaps
- 🐳 **Single Container** - Everything bundled together
- 📦 **Persistent Data** - SQLite database survives restarts
- ⏱️ **Automated Updates** - Schedule refreshes every 6 hours
- 🏥 **Health Monitoring** - Built-in health checks
- 🚀 **Easy Deployment** - Just `docker-compose up -d`

-----

## 📋 Prerequisites

- Docker Engine 20.10+
- Docker Compose 2.0+
- Network access to ESPN+ APIs
- Channels DVR (optional, for full integration)

-----

## 🚀 Quick Start

### 1. Clone the Repository

```bash
git clone https://github.com/kineticman/ESPN4CC4C.git
cd ESPN4CC4C
```

### 2. Configure Environment

Get your LAN IP address:

```bash
# On Linux/Mac
hostname -I | awk '{print $1}'

# Result example: 192.168.1.50
```

Create your `.env` file:

```bash
cp .env.example .env
nano .env
```

**Critical:** Update `VC_RESOLVER_BASE_URL` with your actual LAN IP:

```bash
VC_RESOLVER_BASE_URL=http://192.168.1.50:8094  # Replace with YOUR IP
```

### 3. Build and Run

```bash
docker-compose build
docker-compose up -d
```

### 4. Verify It’s Working

```bash
# Check health
curl http://YOUR_IP:8094/health

# View logs
docker-compose logs -f
```

You should see:

```
INFO:     Uvicorn running on http://0.0.0.0:8094
```

-----
-----

## 🎮 Chrome Capture Integration

If you use **Chrome Capture (cc4c)** to render ESPN+ streams in fullscreen,  
you can control which host/port the M3U playlist uses by setting two variables in your `.env`.

| Variable      | Default             | Description                                      |
|----------------|--------------------|--------------------------------------------------|
| `CC_HOST`      | *(auto-detected)*  | LAN IP or hostname where Chrome Capture runs.    |
| `CC_PORT`      | `5589`             | Chrome Capture service port.                     |
| `VC_RESOLVER_BASE_URL` | *(required)* | Base URL of this ESPN4CC4C resolver.            |

These values drive the new **dynamic playlist** endpoint:
```
http://YOUR_IP:8094/playlist_cc.m3u
```

### Example

If Chrome Capture runs on `192.168.86.72:5589` (default):
```bash
CC_HOST=192.168.86.72
CC_PORT=5589
```

If it’s on another host or port:
```bash
CC_HOST=192.168.86.50
CC_PORT=5599
```

Then rebuild:
```bash
docker compose up -d --build
```

You can verify the dynamic playlist with:
```bash
curl -s http://192.168.86.72:8094/playlist_cc.m3u | head -12
```

It should show:
```
chrome://192.168.86.50:5599/stream?url=http%3A%2F%2F192.168.86.72%3A8094%2Fvc%2Feplus1
```

> 💡 The default static `/playlist.m3u` still works,  
> but `/playlist_cc.m3u` will always reflect your `.env` settings.


## 📺 Channels DVR Integration

### Add as Source

1. Open Channels DVR settings
1. Go to **Sources** → **Add Source** → **M3U Playlist**
1. Configure:
- **M3U URL:** `http://YOUR_IP:8094/playlist.m3u`
- **XMLTV URL:** `http://YOUR_IP:8094/epg.xml`
1. Save and scan for channels

### What You’ll Get

- 40 channels (EPlus 1-40)
- Channel numbers 20010-20049
- Full EPG data (72 hours ahead)
- Automatic stream selection

-----

## 🔧 Configuration

### Environment Variables

|Variable              |Default           |Description                 |
|----------------------|------------------|----------------------------|
|`VC_RESOLVER_BASE_URL`|*required*        |Your LAN IP (not 127.0.0.1!)|
|`TZ`                  |`America/New_York`|Timezone for scheduling     |
|`SCHEDULE_HOURS`      |`6`               |Update frequency (hours)    |
|`VALID_HOURS`         |`72`              |Planning horizon (hours)    |
|`LANES`               |`40`              |Number of virtual channels  |
|`PORT`                |`8094`            |API server port             |

### Advanced Configuration

Edit `.env` to customize:

```bash
# Update every 4 hours instead of 6
SCHEDULE_HOURS=4

# Plan 4 days ahead instead of 3
VALID_HOURS=96

# Use 50 channels instead of 40
LANES=50
```

Restart to apply changes:

```bash
docker-compose restart
```

-----

## 📡 API Endpoints

|Endpoint                 |Description    |Example            |
|-------------------------|---------------|-------------------|
|`GET /health`            |Health check   |`{"ok":true}`      |
|`GET /epg.xml`           |XMLTV EPG data |Full XML document  |
|`GET /playlist.m3u`      |M3U playlist   |Channel list       |
|`GET /vc/{channel}`      |Stream redirect|`/vc/eplus01`      |
|`GET /vc/{channel}/debug`|Debug info     |`/vc/eplus01/debug`|

### Example Usage

```bash
# Get health status
curl http://192.168.1.50:8094/health

# Download EPG
curl http://192.168.1.50:8094/epg.xml -o epg.xml

# Test channel redirect
curl -I http://192.168.1.50:8094/vc/eplus01

# View channel debug info
curl http://192.168.1.50:8094/vc/eplus01/debug | jq
```

-----

## 🛠️ Management Commands

### Container Operations

```bash
# Start container
docker-compose up -d

# Stop container
docker-compose down

# Restart container
docker-compose restart

# View logs (live)
docker-compose logs -f

# View logs (last 100 lines)
docker-compose logs --tail=100

# Check container status
docker-compose ps

# Access container shell
docker-compose exec espn4cc bash
```

### Manual Operations

```bash
# Trigger immediate update
docker-compose exec espn4cc /app/update_schedule.sh

# View cron schedule
docker-compose exec espn4cc crontab -l

# Check database
docker-compose exec espn4cc sqlite3 /app/data/eplus_vc.sqlite3 "SELECT COUNT(*) FROM events;"

# View specific logs
tail -f logs/schedule.log
tail -f logs/ingest.log
tail -f logs/plan.log
```

### Rebuilding

After code changes:

```bash
# Rebuild and restart
docker-compose up -d --build

# Force clean rebuild
docker-compose build --no-cache
docker-compose up -d
```

-----

## 🔍 Troubleshooting

### Container Won’t Start

**Issue:** Port 8094 already in use

```bash
# Find what's using the port
sudo lsof -i :8094

# Stop conflicting service
sudo systemctl stop vc-resolver-v2.service
```

**Issue:** Permission denied on volumes

```bash
# Fix permissions
sudo chown -R $USER:$USER data/ out/ logs/
```

-----

### No Channels Showing

**Issue:** Wrong LAN IP in configuration

```bash
# Verify your IP
hostname -I | awk '{print $1}'

# Update .env
nano .env
# Change: VC_RESOLVER_BASE_URL=http://YOUR_CORRECT_IP:8094

# Restart
docker-compose restart
```

**Issue:** Database not initialized

```bash
# Check if database exists
ls -lh data/

# Manually initialize
docker-compose exec espn4cc python3 bin/ingest_watch_graph_all_to_db.py \
  --db /app/data/eplus_vc.sqlite3 --days 1 --tz America/New_York
```

-----

### EPG Not Updating

**Issue:** Cron not running

```bash
# Check cron status
docker-compose exec espn4cc ps aux | grep cron

# Check schedule log
docker-compose exec espn4cc tail -f /app/logs/schedule.log

# Manually trigger update
docker-compose exec espn4cc /app/update_schedule.sh
```

**Issue:** Timezone problems

```bash
# Verify timezone
docker-compose exec espn4cc date

# Update .env
TZ=America/Los_Angeles  # Use your timezone

# Restart
docker-compose restart
```

-----

### Performance Issues

**Issue:** Container using too much memory

```bash
# Check resource usage
docker stats espn4cc

# Reduce planning horizon
nano .env
# Change: VALID_HOURS=48

# Restart
docker-compose restart
```

**Issue:** Slow updates

```bash
# Reduce update frequency
nano .env
# Change: SCHEDULE_HOURS=12

# Or reduce number of channels
LANES=20

# Restart
docker-compose restart
```

-----

### Debug Mode

Enable detailed logging:

```bash
# View all logs in real-time
docker-compose logs -f

# Export logs to file
docker-compose logs > debug.log

# Check specific component
docker-compose exec espn4cc cat /app/logs/ingest.log
docker-compose exec espn4cc cat /app/logs/plan.log
docker-compose exec espn4cc cat /app/logs/xmltv.log
```

-----

## 📊 Monitoring

### Health Checks

Container includes built-in health monitoring:

```bash
# Docker health status
docker-compose ps

# Manual health check
curl http://YOUR_IP:8094/health

# Watch health status
watch -n 5 'curl -s http://YOUR_IP:8094/health | jq'
```

### Log Monitoring

Important logs to watch:

```bash
# Schedule execution
tail -f logs/schedule.log

# API requests
docker-compose logs -f | grep INFO

# Errors only
docker-compose logs -f | grep ERROR
```

### Database Stats

```bash
# Event count
docker-compose exec espn4cc sqlite3 /app/data/eplus_vc.sqlite3 \
  "SELECT COUNT(*) as events FROM events;"

# Channel count
docker-compose exec espn4cc sqlite3 /app/data/eplus_vc.sqlite3 \
  "SELECT COUNT(*) as channels FROM channel WHERE active=1;"

# Latest plan
docker-compose exec espn4cc sqlite3 /app/data/eplus_vc.sqlite3 \
  "SELECT * FROM plan_run ORDER BY generated_at_utc DESC LIMIT 1;"
```

-----

## 💾 Backup and Restore

### Backup

```bash
# Backup database
cp data/eplus_vc.sqlite3 backups/eplus_vc.$(date +%Y%m%d).sqlite3

# Backup everything
tar -czf espn4cc-backup-$(date +%Y%m%d).tar.gz data/ out/ .env

# Automated backup script
cat > backup.sh << 'EOF'
#!/bin/bash
BACKUP_DIR="./backups"
mkdir -p "$BACKUP_DIR"
DATE=$(date +%Y%m%d-%H%M%S)
tar -czf "$BACKUP_DIR/backup-$DATE.tar.gz" data/ out/ .env
find "$BACKUP_DIR" -mtime +30 -delete
EOF
chmod +x backup.sh
```

### Restore

```bash
# Stop container
docker-compose down

# Restore from backup
tar -xzf espn4cc-backup-20251026.tar.gz

# Start container
docker-compose up -d
```

-----

## 🔄 Updating

### Update Application

```bash
# Pull latest code
git pull origin main

# Rebuild and restart
docker-compose up -d --build
```

### Update Dependencies

```bash
# Edit requirements.txt
nano requirements.txt

# Rebuild with no cache
docker-compose build --no-cache
docker-compose up -d
```

-----

## 📁 Project Structure

```
ESPN4CC4C/
├── bin/                      # Python scripts
│   ├── vc_resolver.py       # FastAPI application
│   ├── ingest_*.py          # ESPN API ingestion
│   ├── build_plan.py        # Scheduling logic
│   ├── xmltv_from_plan.py   # EPG generation
│   └── m3u_from_plan.py     # Playlist generation
├── data/                     # SQLite database (persistent)
├── out/                      # Generated EPG/M3U (persistent)
├── logs/                     # Application logs (persistent)
├── Dockerfile               # Container definition
├── docker-compose.yml       # Service orchestration
├── docker-entrypoint.sh     # Startup script
├── .env.example             # Configuration template
└── requirements.txt         # Python dependencies
```

-----

## 🤝 Contributing

Contributions welcome! Please:

1. Fork the repository
1. Create a feature branch
1. Make your changes
1. Submit a pull request

-----

## 📝 License

This project is licensed under the MIT License - see the <LICENSE> file for details.

-----

## 🙏 Acknowledgments

- **Channels DVR** - For the amazing DVR platform
- **ESPN+** - For the sports content
- **FastAPI** - For the excellent web framework
- **Docker** - For containerization made easy

-----

## 📞 Support

- **Issues:** [GitHub Issues](https://github.com/kineticman/ESPN4CC4C/issues)
- **Discussions:** [GitHub Discussions](https://github.com/kineticman/ESPN4CC4C/discussions)
- **Documentation:** [Wiki](https://github.com/kineticman/ESPN4CC4C/wiki)

-----

## 📈 Roadmap

- [ ] Multi-architecture support (ARM/ARM64)
- [ ] Prometheus metrics endpoint
- [ ] Web UI for configuration
- [ ] Notifications (email/webhook)
- [ ] Kubernetes deployment manifests
- [ ] Advanced scheduling algorithms

-----

## ⚠️ Disclaimer

This project is not affiliated with, endorsed by, or connected to ESPN, Disney, or Channels DVR. Use at your own discretion and ensure compliance with applicable terms of service.

-----

<div align="center">

**Made with ❤️ by the community**

⭐ Star this repo if you find it useful!

</div>
