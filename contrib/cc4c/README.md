# CC4C Fullscreen Helper (contrib)

## 🆕 Latest Version: FIXED (December 30, 2024)

### Current Files
- **Fixed Version:** `main.cc4c-autofs.20241230-fixed.js` ✅ **RECOMMENDED**
  - SHA256: `3de6b5c82e8ad0457e290891347de5ec6c2c3d91d28e1917baee2afac102f210`
  - 894 lines
  - **All bugs fixed** - no more toggle behavior!
  - Works correctly with ESPN, NBC, and custom channels
  - See `CHANGELOG_main_fixed.md` for complete details

- **Old Version:** `main.cc4c-autofs.20251030-222408.js` ⚠️ **DEPRECATED - HAS BUGS**
  - 863 lines
  - Contains race conditions causing fullscreen toggle on/off
  - Duplicate timer setup
  - **Use the fixed version instead!**

### What Was Fixed
The fixed version addresses community-reported bugs:
- ✅ Eliminated duplicate fullscreen timer setup
- ✅ Fixed race condition between site handlers and fallback
- ✅ Proper flag coordination prevents toggle on/off behavior
- ✅ Added `sendFullscreenKey()` helper for clean handler implementation
- ✅ Enhanced logging for easier debugging

## Installation

### Quick Install (Fixed Version)
Replace the CC4C container's `/home/chrome/main.js` with the fixed file:

```bash
# Backup current file first
docker exec -it cc4c sh -lc 'cp -n /home/chrome/main.js /home/chrome/main.js.bak.$(date +%Y%m%d-%H%M%S)'

# Copy fixed version
docker cp contrib/cc4c/main.cc4c-autofs.20241230-fixed.js cc4c:/home/chrome/main.js

# Restart container
docker restart cc4c

# Monitor logs
docker logs -f cc4c | grep -i 'fullscreen\|fallback'
```

### Verify Installation
```bash
# Should show "sendFullscreenKey" function (indicates fixed version)
docker exec -it cc4c sh -lc "grep -c 'sendFullscreenKey' /home/chrome/main.js"
# Expected output: 3

# Old buggy version would return: 0
```

### Optional: Verify Checksum
```bash
sha256sum -c contrib/cc4c/main.cc4c-autofs.20241230-fixed.js.sha256
# Expected: main.cc4c-autofs.20241230-fixed.js: OK
```

## How It Works

This helper adds automatic fullscreen triggering to CC4C with two mechanisms:

### 1. Site-Specific Handlers
Built-in handlers for sites that need special treatment:
- ESPN / ESPN+ (sends `Shift+F`)
- NBC Sports (sends `Shift+F`)
- Peacock
- Sling TV
- Spectrum
- DirecTV Stream
- Google Photos

### 2. Fallback Timer (Universal)
Safety net for **any** site without a specific handler:
- Arms a timer when stream request arrives
- Waits for configured delay (default 15 seconds)
- If no handler has sent fullscreen yet, fallback sends `F` key
- **Perfect for custom channels** (like Golf Channel, etc.)

## URL Format

Works seamlessly with ESPN4CC4C resolver URLs using ChromeCapture schema:

```bash
# Standard format
chrome://<LAN-IP>:5589/stream?url=http%3A%2F%2F<LAN-IP>%3A8094%2Fvc%2Feplus8

# With autofs anchor (optional)
chrome://<LAN-IP>:5589/stream?url=http%3A%2F%2F<LAN-IP>%3A8094%2Fvc%2Feplus8%23autofs

# With key-send parameter (optional - fallback handles this now)
chrome://<LAN-IP>:5589/stream?url=http%3A%2F%2F<LAN-IP>%3A8094%2Fvc%2Feplus8%3Fsend%3Dkeys%253Af

# Custom channels work too!
chrome://<LAN-IP>:5589/stream?url=http%3A%2F%2F<LAN-IP>%3A8094%2Fvc%2Fgolfchannel
```

**Example with your setup:**
```bash
chrome://192.168.86.72:5589/stream?url=http%3A%2F%2F192.168.86.72%3A8094%2Fvc%2Feplus8
```

## Configuration

### Adjusting Fullscreen Delay

Different channels load at different speeds. Tune the delay as needed:

**Via Docker Run:**
```bash
docker run ... bnhf/cc4c:latest --fullscreenDelay=12000
```

**Via Docker Compose:**
```yaml
services:
  cc4c:
    image: bnhf/cc4c:latest
    command: ["--fullscreenDelay=12000"]
```

**Recommended Values:**
- Fast streams (ESPN+): `8000` (8 seconds)
- Average streams: `15000` (15 seconds) ← **DEFAULT**
- Slow streams: `20000` (20 seconds)

### Container Logs
The container will show:
```
Selected settings:
...
Fullscreen Delay: 15000ms
```

When a stream starts, you'll see:
```
[cc4c] Arming per-request fullscreen fallback timer...
```

## Testing

### ESPN/NBC Channels
Expected behavior:
- Site-specific handler sends fullscreen after configured delay
- Stays fullscreen (no toggle)
- Logs show: "Shift+F sent successfully via xdotool"

### Custom Channels (Golf, etc.)
Expected behavior:
- Fallback timer triggers after delay
- Stays fullscreen (no toggle)
- Logs show: "Fallback F key sent successfully via xdotool"

### Verification
```bash
# Watch logs in real-time
docker logs -f cc4c | grep -E 'fullscreen|fallback|ESPN|NBC'

# Check for duplicate sends (should NOT see this in fixed version)
docker logs cc4c | grep -c "sent successfully"
# Should be 1 per stream, not 2+
```

## Troubleshooting

### Stream Toggles Fullscreen On/Off
**Problem:** You have the old buggy version installed.

**Solution:**
```bash
# Verify you have the fixed version
docker exec -it cc4c sh -lc "grep -c 'sendFullscreenKey' /home/chrome/main.js"

# If it returns 0, you have the old version
# Re-copy the fixed version
docker cp contrib/cc4c/main.cc4c-autofs.20241230-fixed.js cc4c:/home/chrome/main.js
docker restart cc4c
```

### No Fullscreen Triggers
**Problem:** Delay too short or xdotool issue.

**Solution:**
```bash
# Check xdotool is installed
docker exec -it cc4c which xdotool

# Increase delay
docker stop cc4c
docker run ... bnhf/cc4c:latest --fullscreenDelay=20000

# Check logs for errors
docker logs cc4c | grep -i error
```

### "Fullscreen Already Sent" Messages
**Status:** This is NORMAL and means the fix is working!

**Explanation:** A site-specific handler successfully sent fullscreen, so the fallback timer detected this and skipped (preventing duplicate). This is correct behavior.

## Rollback

If you need to revert to a previous version:

```bash
# List backups
docker exec -it cc4c sh -lc 'ls -lt /home/chrome/main.js.bak.*'

# Restore most recent backup
docker exec -it cc4c sh -lc 'latest=$(ls -1t /home/chrome/main.js.bak.* 2>/dev/null | head -n1); if [ -n "$latest" ]; then cp -v "$latest" /home/chrome/main.js; fi'

# Restart
docker restart cc4c
```

## Container Updates

**Important:** When you pull a new `bnhf/cc4c:latest` image or recreate the container, you must re-copy the patched `main.js` file as the container filesystem resets.

**Workflow:**
```bash
# Pull new image
docker pull bnhf/cc4c:latest

# Recreate container (via compose or run)
docker-compose up -d cc4c

# Re-apply the patch
docker cp contrib/cc4c/main.cc4c-autofs.20241230-fixed.js cc4c:/home/chrome/main.js
docker restart cc4c
```

Keep your patched file in the `contrib/cc4c/` directory for easy re-application.

## File Versions

| File | Date | Lines | Status | Notes |
|------|------|-------|--------|-------|
| `main.cc4c-autofs.20241230-fixed.js` | 2024-12-30 | 894 | ✅ **CURRENT** | All bugs fixed |
| `main.cc4c-autofs.20251030-222408.js` | 2024-10-30 | 863 | ⚠️ **DEPRECATED** | Has toggle bug |

## Documentation

- **INSTALL_GUIDE_FIXED.md** - Complete installation guide
- **CHANGELOG_main_fixed.md** - Detailed bug fixes and improvements
- **CC4C_Fullscreen_Helper_Manual_Install_Guide.md** - Original guide (for old version)

## Credits

- **Original Implementation:** Brad (@KineticMan)
- **Bug Discovery:** Forum community
- **Fixed Version:** December 30, 2024
- **Source:** Extracted and enhanced from running CC4C container

## Support

For issues or questions:
1. Check logs: `docker logs -f cc4c | grep -i 'fullscreen\|error'`
2. Verify fixed version installed: `docker exec -it cc4c sh -lc "head -60 /home/chrome/main.js"`
3. Review documentation in this directory
4. Post in forum with logs and setup details

## License

Same as CC4C and ESPN4CC4C projects.
