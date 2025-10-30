# ESPN4CC4C — ESPN+ Virtual Channels for Channels DVR (Docker Edition)

Turn ESPN+ events into **stable virtual channels** (eplus1–eplus40) your **Channels DVR** can ingest via **XMLTV** and **M3U** — all packaged in a single Docker service.

---

## What You Need

- **Docker Desktop** installed and running (Windows) or **Docker Engine** (Linux)
- Your computer's **local IP address**
- **Channels DVR** installed and accessible on your network
- Outbound HTTPS access to ESPN

**Port Used:** `8094/tcp`

## Installation — Windows

### If you have GIT, use this!  
1. git clone https://github.com/kineticman/ESPN4CC4C
2  go to step 3

### Step 1: Download the Project 
1. Go to **https://github.com/kineticman/ESPN4CC4C**
2. Click the green **"Code"** button
3. Click **"Download ZIP"**
4. Extract the ZIP file to a location like `C:\ESPN4CC4C` or your Desktop
5. Remember where you put this folder

### Step 2: Find Your Computer's IP Address
1. Press `Windows Key + R`, type `cmd`, and press Enter
2. In the command prompt, type `ipconfig` and press Enter
3. Look for **"IPv4 Address"** under your active network adapter
   - Example: `192.168.1.100` or `10.0.0.50`
   - Note: This is NOT `127.0.0.1`
4. Write down this IP address

### Step 3a:
1. Important - you must update the .ENV file!
2. Open Powershell, go to directory and:
	mv .env.example .env
3. Edit .ENV
4. Focus on the IP addresses and ports

### Step 3b: Run the Bootstrap Script
1. From Powershell project directory, run:
  ./windowsbootstrap.ps1
4. When prompted, enter your IP address from Step 2
5. Press Enter and wait 1-2 minutes while it sets everything up

The script will:
- Create necessary folders (`data`, `logs`, `out`)
- Configure your environment
- Start the Docker container
- Build the initial channel guide

### Step 4: Verify Installation
Open a web browser and navigate to (using your IP):
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

**Can't see the `.ps1` extension:**
- In File Explorer, go to View → Show → File name extensions

**Health check fails:**
- Verify Docker Desktop is running (whale icon in system tray)
- In Docker Desktop, go to Containers and confirm `espn4cc` is running
- Check that port 8094 isn't blocked by your firewall

**Container shows as "Exited":**
- Open Docker Desktop → Containers
- Click on `espn4cc` to view logs for error messages
- Try clicking the restart button

---

## Installation — Linux

### Step 1: Download the Project
```bash
git clone https://github.com/kineticman/ESPN4CC4C.git
cd ESPN4CC4C
```

Or download the ZIP from GitHub if you don't have git installed.

### Step 2: Find Your IP Address
```bash
hostname -I | awk '{print $1}'
```
Note the output (e.g., `192.168.1.100`)

### Step 3: Configure Environment
```bash
cp .env.example .env
nano .env
```

Update the ENV file - focus on the IP addresses.  Most of rest is fine to leave alone (at your own risk - be careful)
```

Save with `Ctrl+X`, then `Y`, then `Enter`

### Step 4: Start the Service
```bash
docker compose up -d
```

Wait 30 seconds, then verify:
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
3. Review container logs in Docker Desktop
4. Ensure port 8094 isn't blocked by firewall

---

## Technical Details (For Advanced Users)

### Default Settings
- **Port**: 8094
- **Channels**: 40 (configurable via `LANES` in `.env`)
- **Guide window**: 72 hours (configurable via `VALID_HOURS`)
- **Timezone**: America/New_York (change `TZ` in `.env`)

### Rebuild Guide Manually
```bash
docker compose exec espn4cc sh -c '
  python3 /app/bin/build_plan.py --db /app/data/eplus_vc.sqlite3 --valid-hours 72;
  python3 /app/bin/xmltv_from_plan.py --db /app/data/eplus_vc.sqlite3 --out /app/out/epg.xml;
  python3 /app/bin/m3u_from_plan.py --db /app/data/eplus_vc.sqlite3 --out /app/out/playlist.m3u
'
```

### View Logs
```bash
docker compose logs --tail=200 espn4cc
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
└─ README.md                 # This file
```

---


**Enjoy!** If something's confusing, open an issue and tell us what you expected to see versus what happened.
