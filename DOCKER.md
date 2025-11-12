# ESPN4CC4C - Docker Deployment Guide

This guide covers deploying ESPN4CC4C using Docker for easy, cross-platform setup.

## Quick Start

### Prerequisites

- **Docker Desktop** (Windows/Mac) or **Docker Engine** (Linux)
- ESPN+ subscription credentials
- Your computer's LAN IP address

### Windows Setup

1. **Install Docker Desktop**
   - Download from [docker.com](https://www.docker.com/products/docker-desktop/)
   - Start Docker Desktop

2. **Run Setup Script**
   ```powershell
   .\setup-windows.ps1
   ```

3. **Configure**
   - Edit `.env` with your ESPN+ credentials
   - Edit `docker-compose.yml` and update `VC_RESOLVER_BASE_URL` with your PC's IP

4. **Start**
   ```powershell
   docker-compose up -d
   ```

### Linux/Mac Setup

1. **Install Docker**
   - Linux: Follow [official guide](https://docs.docker.com/engine/install/)
   - Mac: Install [Docker Desktop](https://www.docker.com/products/docker-desktop/)

2. **Run Setup Script**
   ```bash
   chmod +x setup-linux.sh
   ./setup-linux.sh
   ```

3. **Configure**
   - Edit `.env` with your ESPN+ credentials
   - Edit `docker-compose.yml` and update `VC_RESOLVER_BASE_URL` with your machine's IP

4. **Start**
   ```bash
   docker-compose up -d
   ```

## Configuration

### Environment Variables

Edit `.env` file:

```bash
# Required
ESPN_EMAIL=your-email@example.com
ESPN_PASSWORD=your-password

# Optional: Chrome Capture integration
CC_HOST=192.168.1.100
CC_PORT=5589
```

Edit `docker-compose.yml` for other settings:

```yaml
environment:
  - PORT=8094                # API port
  - TZ=America/New_York      # Your timezone
  - VALID_HOURS=72           # How far ahead to plan
  - LANES=40                 # Number of channels

  # IMPORTANT: Set to your Docker host's LAN IP
  - VC_RESOLVER_BASE_URL=http://192.168.1.100:8094
```

### Finding Your LAN IP

**Windows PowerShell:**
```powershell
ipconfig | findstr IPv4
```

**Linux/Mac:**
```bash
hostname -I | awk '{print $1}'
```

## Usage

### Starting the Container

```bash
docker-compose up -d
```

The container will:
1. Initialize/update the database
2. Fetch ESPN+ events
3. Generate EPG and M3U files
4. Start the API server

### Accessing Services

- **Health Check**: http://localhost:8094/health
- **EPG (XMLTV)**: http://localhost:8094/epg.xml
- **Playlist (M3U)**: http://localhost:8094/playlist.m3u
- **Channel Debug**: http://localhost:8094/vc/eplus01/debug

### Viewing Logs

```bash
# Follow logs
docker-compose logs -f

# Last 100 lines
docker-compose logs --tail=100
```

### Stopping the Container

```bash
docker-compose down
```

### Restarting (triggers refresh)

```bash
docker-compose restart
```

### Forcing a Refresh

```bash
# Restart container (runs refresh_in_container.sh)
docker-compose restart

# Or manually trigger
docker-compose exec espn4cc4c /app/bin/refresh_in_container.sh
```

## Channels DVR Integration

1. **Add Custom Channel**
   - Open Channels DVR web UI
   - Settings → Sources → Custom Channels
   - Click "+" to add source

2. **Configure Source**
   - **Nickname**: ESPN4CC4C
   - **XMLTV URL**: `http://YOUR_IP:8094/epg.xml`
   - **M3U URL**: `http://YOUR_IP:8094/playlist.m3u`

   Replace `YOUR_IP` with your Docker host's LAN IP (e.g., `192.168.1.100`)

3. **Save and Refresh**

## Data Persistence

The following directories persist data between container restarts:

- `./data/` - SQLite database
- `./out/` - Generated EPG/M3U files

To completely reset:
```bash
docker-compose down
rm -rf data/ out/
docker-compose up -d
```

## Updating

### Using Pre-built Images

```bash
docker-compose pull
docker-compose up -d
```

### Building Locally

```bash
docker-compose build
docker-compose up -d
```

## Scheduled Refreshes

The container automatically refreshes data on startup. For periodic updates, you can:

1. **Use Docker restart policy** (already configured as `unless-stopped`)
2. **External scheduler** (cron/Task Scheduler) to restart container:

**Linux cron** (every 4 hours):
```bash
0 */4 * * * cd /path/to/ESPN4CC4C && docker-compose restart
```

**Windows Task Scheduler**:
```powershell
# Create scheduled task to run every 4 hours
schtasks /create /tn "ESPN4CC4C Refresh" /tr "docker-compose -f C:\path\to\ESPN4CC4C\docker-compose.yml restart" /sc hourly /mo 4
```

## Troubleshooting

### Container won't start

```bash
# Check logs
docker-compose logs

# Check if port 8094 is in use
# Windows:
netstat -ano | findstr :8094
# Linux:
lsof -i :8094
```

### ESPN+ authentication fails

- Verify credentials in `.env`
- Check if ESPN+ subscription is active
- Try logging in manually at espn.com

### Channels DVR can't connect

- Verify `VC_RESOLVER_BASE_URL` in docker-compose.yml uses LAN IP (not localhost)
- Ensure firewall allows port 8094
- Test URL in browser: `http://YOUR_IP:8094/health`

### No events showing up

```bash
# Check database
docker-compose exec espn4cc4c sqlite3 /app/data/eplus_vc.sqlite3 "SELECT COUNT(*) FROM events;"

# Force refresh
docker-compose restart
```

### Chrome Capture integration

If using Fire TV automation:
```yaml
environment:
  - CC_HOST=192.168.1.100  # Chrome Capture host IP
  - CC_PORT=5589           # Chrome Capture port
```

## Advanced

### Custom Filters

Mount a custom filters file (future feature):
```yaml
volumes:
  - ./config/filters.json:/app/config/filters.json:ro
```

### Development Mode

```yaml
services:
  espn4cc4c:
    build: .  # Build from local Dockerfile
    volumes:
      - ./bin:/app/bin       # Live reload scripts
      - ./vc_resolver:/app/vc_resolver
```

### Multi-Architecture

Pre-built images support:
- `linux/amd64` (x86_64 PCs)
- `linux/arm64` (Raspberry Pi 4, Apple Silicon)

Docker automatically pulls the correct architecture.

## Support

- **Issues**: [GitHub Issues](https://github.com/kineticman/ESPN4CC4C/issues)
- **Discussions**: [GitHub Discussions](https://github.com/kineticman/ESPN4CC4C/discussions)
