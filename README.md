# ESPN4CC4C — ESPN+ Virtual Channels for Channels DVR (Docker Edition)

Turn ESPN+ events into **stable virtual channels** (eplus1–eplus40) your **Channels DVR** can ingest via **XMLTV** and **M3U** — all packaged in a single Docker service.

---

## What You Need

- **Docker Desktop** installed and running (Windows) or **Docker Engine** (Linux)
- Your computer's **local IP address**
- **Channels DVR** installed and accessible on your network
- Outbound HTTPS access to ESPN

**Port Used:** `8094/tcp`

---

## Installation — Windows

### Step 1: Get the Project Files

**Option A - Using Git (recommended):**
```powershell
git clone https://github.com/kineticman/ESPN4CC4C.git
cd ESPN4CC4C
```

**Option B - Download ZIP:**
1. Go to **https://github.com/kineticman/ESPN4CC4C**
2. Click the green **"Code"** button → **"Download ZIP"**
3. Extract to a location like `C:\ESPN4CC4C`
4. Open that folder

### Step 2: Find Your Computer's IP Address
1. Press `Windows Key + R`, type `cmd`, and press Enter
2. Type `ipconfig` and press Enter
3. Look for **"IPv4 Address"** under your active network adapter
   - Example: `192.168.1.100` or `10.0.0.50`
   - Note: This is NOT `127.0.0.1`
4. Write down this IP address

### Step 3: Configure Your Settings
1. In the project folder, copy **`.env.example`** to **`.env`**:
   - Right-click on `.env.example` and select **Copy**
   - Right-click in the folder and select **Paste**
   - Rename the copy from `.env.example - Copy` to **`.env`**
   - (If you can't see the files, enable "Show hidden files" in File Explorer's View menu)
2. Right-click **`.env`** and open it with Notepad
3. Find these two lines and update them with your IP from Step 2:
   ```
   VC_RESOLVER_BASE_URL=http://YOUR_LAN_IP:8094
   CC_HOST=YOUR_LAN_IP
   ```
   Change to:
   ```
   VC_RESOLVER_BASE_URL=http://192.168.1.100:8094
   CC_HOST=192.168.1.100
   ```
4. Save and close the file

### Step 4: Run the Bootstrap Script
1. Right-click in the project folder while holding **Shift**
2. Select **"Open PowerShell window here"**
3. Run the bootstrap script:
   ```powershell
   .\windowsbootstrap.ps1 -LanIp 192.168.1.100
   ```
   (Replace `192.168.1.100` with your actual IP)
4. Wait 1-2 minutes while it sets everything up

The script will:
- Create necessary folders (`data`, `logs`, `out`)
- Start the Docker container
- Download ESPN+ event data
- Build the channel guide and playlist

### Step 5: Verify Installation
Open a web browser and go to (using your IP):
```
http://192.168.1.100:8094/health
```

You should see: `{"ok":true}`

**Success!** Continue to "Add to Channels DVR" below.

---

### Windows Troubleshooting

**Script won't run / Execution policy error:**
- Right-click `windowsbootstrap.ps1` and select "Run with PowerShell"
- If prompted about execution policy, choose "Yes" or "Run anyway"

**Can't see the `.env.example` or `.ps1` files:**
- In File Explorer, go to View → Show → File name extensions
- Make sure "Hidden items" is checked

**Health check fails:**
- Verify Docker Desktop is running (whale icon in system tray)
- In Docker Desktop, go to Containers and confirm `espn4cc` is running
- Check that port 8094 isn't blocked by your firewall

**"Ingested 0 airings" error:**
- Check that `WATCH_API_KEY` is set in your `.env` file
- The default key should be: `0dbf88e8-cc6d-41da-aa83-18b5c630bc5c`

**Container shows as "Exited":**
- Open Docker Desktop → Containers
- Click on `espn4cc` to view logs for error messages
- Try clicking the restart button

---

## Installation — Linux

### Step 1: Get the Project Files
```bash
git clone https://github.com/kineticman/ESPN4CC4C.git
cd ESPN4CC4C
```

### Step 2: Find Your IP Address
```bash
hostname -I | awk '{print $1}'
```
Note the output (e.g., `192.168.1.100`)

### Step 3: Configure Settings
```bash
cp .env.example .env
nano .env
```

Update these lines with your IP address (replace `YOUR_LAN_IP` with your actual IP):
```
VC_RESOLVER_BASE_URL=http://192.168.1.100:8094
CC_HOST=192.168.1.100
```

Optionally adjust `TZ=` for your timezone.

Save with `Ctrl+X`, then `Y`, then `Enter`

### Step 4: Run Bootstrap
```bash
./bootstrap.sh
```

This will:
- Build and start the container
- Download ESPN+ schedule data
- Generate XMLTV guide and M3U playlist
- Show a summary with URLs

Verify the service is running:
```bash
curl http://192.168.1.100:8094/health
```

Expected response: `{"ok":true}`

---

## Add to Channels DVR

Once the service is running, configure Channels DVR to use your new virtual channels:

1. Open **Channels DVR Settings**
2. Navigate to **Sources** → **XMLTV** or **TVE Sources**
3. Add the following URLs (replace `192.168.1.100` with your actual IP):

**XMLTV Guide Data:**
```
http://192.168.1.100:8094/out/epg.xml
```

**M3U Playlist:**
```
http://192.168.1.100:8094/out/playlist.m3u
```

4. Save and allow Channels DVR to refresh

You should now see 40 ESPN+ virtual channels (`eplus1` through `eplus40`) in your channel lineup with guide data populated.

---

## Optional: Chrome Capture Integration

For improved streaming reliability, you can install [Chrome Capture](https://github.com/fancybits/chrome-capture-for-channels) on the same host at port `5589`.

The M3U playlist is pre-configured to use Chrome Capture if available. If not installed, streams will resolve directly through the built-in resolver.

---

## FAQ

**How many channels do I get?**  
40 channels by default (`eplus1` through `eplus40`). Configurable via `LANES` in `.env`.

**How often does the guide update?**  
Automatically rebuilds based on your configuration. Default window is 72 hours of programming.

**Where are files stored?**
- Database: `data/eplus_vc.sqlite3`
- Guide (XMLTV): `out/epg.xml`
- Channels (M3U): `out/playlist.m3u`
- Logs: `logs/`

**Something not working?**
1. Verify Docker is running
2. Check `http://YOUR-IP:8094/health` returns `{"ok":true}`
3. Review container logs: `docker logs espn4cc --tail 100`
4. Ensure port 8094 isn't blocked by firewall

---

## Configuration Reference

### Environment Variables (.env)

The `.env` file controls all service behavior. Here's what you need to know:

#### Must Update ⚠️
These **must** be changed from defaults:

| Variable | Description | Example |
|----------|-------------|---------|
| `VC_RESOLVER_BASE_URL` | Your computer's IP + port (must be reachable by Channels DVR) | `http://192.168.1.100:8094` |
| `CC_HOST` | Same IP as above (for Chrome Capture integration) | `192.168.1.100` |
| `TZ` | Your timezone in IANA format ([list](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones)) | `America/New_York` |

#### Common Settings
Good defaults, but adjust if needed:

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `8094` | Service port |
| `LANES` | `40` | Number of virtual channels (eplus1–eplusN) |
| `VALID_HOURS` | `72` | Hours of guide data to maintain |
| `CC_PORT` | `5589` | Chrome Capture port (if using) |

#### Advanced Settings
Don't change unless you have a specific need:

| Variable | Default | Description |
|----------|---------|-------------|
| `ALIGN` | `30` | Align programs to minute marks (:00, :30) |
| `MIN_GAP_MINS` | `30` | Minimum gap between programs |
| `WATCH_API_KEY` | (provided) | ESPN API key (shared, don't change) |

---

## Manual Operations

### Rebuild Guide Manually
```bash
docker exec espn4cc python3 /app/bin/build_plan.py --db /app/data/eplus_vc.sqlite3 --valid-hours 72
docker exec espn4cc python3 /app/bin/xmltv_from_plan.py --db /app/data/eplus_vc.sqlite3 --out /app/out/epg.xml
docker exec espn4cc python3 /app/bin/m3u_from_plan.py --db /app/data/eplus_vc.sqlite3 --out /app/out/playlist.m3u --resolver-base http://192.168.1.100:8094 --cc-host 192.168.1.100 --cc-port 5589
```

### Refresh ESPN+ Schedule Data
```bash
docker exec espn4cc python3 /app/bin/ingest_watch_graph_all_to_db.py --db /app/data/eplus_vc.sqlite3 --days 3 --tz America/New_York
```

### View Logs
```bash
docker logs espn4cc --tail 200
```

### Force Restart
```bash
docker compose down
docker compose up -d --force-recreate
```

---

## Project Structure

```
ESPN4CC4C/
├─ bin/                      # Python scripts that build the guide
├─ data/                     # SQLite database (persisted)
├─ logs/                     # Log files
├─ out/                      # epg.xml + playlist.m3u (what Channels DVR reads)
├─ docker-compose.yml        # Docker configuration
├─ .env                      # Your settings (IP addresses, etc)
├─ windowsbootstrap.ps1      # Windows installer script
├─ bootstrap.sh              # Linux installer script
└─ README.md                 # This file
```

---

**Enjoy!** If something's confusing, open an issue and tell us what you expected to see versus what happened.
