# CC4C Fullscreen Helper (FIXED VERSION) — Installation Guide

## 🆕 What's New in This Version?

This is the **FIXED** version that addresses all the bugs found by the community:
- ✅ No more double-triggering of fullscreen
- ✅ No more toggle on/off behavior
- ✅ Proper flag coordination between handlers
- ✅ Works correctly for ALL channels (ESPN, NBC, custom channels, etc.)

**Previous Version:** `main.cc4c-autofs.20251030-222408.js` (863 lines, BUGGY)  
**Fixed Version:** `main.cc4c-autofs.20241230-fixed.js` (894 lines, FIXED)  
**SHA256:** `3de6b5c82e8ad0457e290891347de5ec6c2c3d91d28e1917baee2afac102f210`

See `CHANGELOG_main_fixed.md` for complete details on what was fixed.

---

## Prerequisites
- Running `cc4c` container (image `bnhf/cc4c:latest`)
- Fixed file saved on host: `contrib/cc4c/main.cc4c-autofs.20241230-fixed.js`
- Optional checksum: `contrib/cc4c/main.cc4c-autofs.20241230-fixed.js.sha256`

---

## Installation Steps

### 1) Backup Current File
```bash
docker exec -it cc4c sh -lc 'cp -n /home/chrome/main.js /home/chrome/main.js.bak.$(date +%Y%m%d-%H%M%S)'
docker exec -it cc4c sh -lc 'ls -l /home/chrome/main.js*'
```

You should see something like:
```
-rw-r--r-- 1 chrome chrome 28234 Dec 30 17:00 /home/chrome/main.js
-rw-r--r-- 1 chrome chrome 28234 Dec 30 17:00 /home/chrome/main.js.bak.20241230-170015
```

### 2) (Optional) Verify Checksum
```bash
cd ~/Projects/ESPN4CC4C
sha256sum -c contrib/cc4c/main.cc4c-autofs.20241230-fixed.js.sha256
```

Expected output:
```
contrib/cc4c/main.cc4c-autofs.20241230-fixed.js: OK
```

### 3) Copy Fixed File to Container
```bash
cd ~/Projects/ESPN4CC4C
docker cp contrib/cc4c/main.cc4c-autofs.20241230-fixed.js cc4c:/home/chrome/main.js
```

### 4) Verify the Fixed File Was Copied
Check that the helper function is present:
```bash
docker exec -it cc4c sh -lc "head -60 /home/chrome/main.js"
```

You should see `sendFullscreenKey` function around line 29-56. If you see the old duplicate code at lines 18-35, the copy failed.

### 5) Restart Container
```bash
docker restart cc4c
```

### 6) Monitor Logs
```bash
docker logs -f cc4c | grep -i 'arming\|fullscreen\|fallback'
```

---

## Testing

### Test 1: ESPN/NBC Channel
Tune to an ESPN+ or NBC Sports stream.

**Expected Logs:**
```
[cc4c] Arming per-request fullscreen fallback timer...
Waiting 15000ms for stream to fully load...
Sending F key via xdotool (OS-level input)
Shift+F sent successfully via xdotool
```

**Should NOT See:**
- "Fallback: site not recognized..." (means the ESPN handler worked!)
- Two "sent successfully" messages (would indicate double-sending)

**Visual Test:**
- Stream should go fullscreen and STAY fullscreen
- No toggle on/off behavior

### Test 2: Custom Channel (e.g., Golf Channel)
Tune to a custom channel that doesn't have a specific handler.

**Expected Logs:**
```
[cc4c] Arming per-request fullscreen fallback timer...
Fallback: site not recognized or no fullscreen sent — sending F now…
Fallback F key sent successfully via xdotool
```

**Visual Test:**
- Stream should go fullscreen after the delay (default 15 seconds)
- Should stay fullscreen

### Test 3: Rapid Channel Changes
Switch between channels quickly.

**Expected Behavior:**
- Each channel switch resets the flag
- Each channel gets its own fullscreen trigger
- No errors in logs
- No "already sent" messages during normal operation

---

## Tuning the Delay

If streams need more or less time to load before triggering fullscreen:

### Via Docker Run
```bash
docker run ... bnhf/cc4c:latest --fullscreenDelay=12000
```

### Via Docker Compose
```yaml
services:
  cc4c:
    image: bnhf/cc4c:latest
    command: ["--fullscreenDelay=12000"]
```

**Recommended Values:**
- Fast-loading streams (ESPN+): `8000` (8 seconds)
- Average streams: `15000` (15 seconds, default)
- Slow-loading streams: `20000` (20 seconds)

---

## Troubleshooting

### Problem: Stream toggles fullscreen on/off
**Diagnosis:** You might still have the old buggy version installed.

**Fix:**
1. Check which version is in the container:
   ```bash
   docker exec -it cc4c sh -lc "grep -n 'sendFullscreenKey' /home/chrome/main.js"
   ```
   If this returns nothing, you have the old buggy version.

2. Re-copy the fixed file:
   ```bash
   docker cp contrib/cc4c/main.cc4c-autofs.20241230-fixed.js cc4c:/home/chrome/main.js
   docker restart cc4c
   ```

### Problem: No fullscreen at all
**Diagnosis:** xdotool might not be working or delay is too short.

**Fix:**
1. Check if xdotool is installed:
   ```bash
   docker exec -it cc4c sh -lc "which xdotool"
   ```
   
2. Check logs for xdotool errors:
   ```bash
   docker logs cc4c | grep -i xdotool
   ```

3. Try increasing the delay:
   ```bash
   # Restart with longer delay
   docker stop cc4c
   docker run ... bnhf/cc4c:latest --fullscreenDelay=20000
   ```

### Problem: "Fallback: fullscreen already sent by site handler, skipping"
**Diagnosis:** This is NORMAL and means the system is working correctly!

**Explanation:** 
- A site-specific handler (ESPN, NBC, etc.) successfully sent fullscreen
- The fallback timer fired but checked the flag first
- Saw fullscreen was already handled, so it skipped (preventing duplicate)

This is the CORRECT behavior showing the bug fixes are working.

### Problem: Logs show duplicate timer setup
**Diagnosis:** Old buggy version still in container.

**Fix:** Follow steps in "Stream toggles fullscreen" above.

---

## Rollback to Previous Version

If you need to revert to your backup:

```bash
# Find most recent backup
docker exec -it cc4c sh -lc 'ls -lt /home/chrome/main.js.bak.* | head -1'

# Restore it
docker exec -it cc4c sh -lc 'latest=$(ls -1t /home/chrome/main.js.bak.* 2>/dev/null | head -n1); if [ -n "$latest" ]; then cp -v "$latest" /home/chrome/main.js; else echo "No backup found"; fi'

# Restart
docker restart cc4c
```

---

## Differences from Old Version

| Feature | Old Version (BUGGY) | Fixed Version |
|---------|-------------------|---------------|
| Line count | 863 lines | 894 lines |
| Duplicate timer setup | ❌ Yes (lines 1-16 AND 18-35) | ✅ No (single function) |
| Flag cleared in wrong place | ❌ Yes (in armFullscreenFallback) | ✅ No (in setupPage) |
| ESPN handler checks flag | ❌ No | ✅ Yes |
| Helper function | ❌ No | ✅ Yes (sendFullscreenKey) |
| Toggle behavior | ❌ Broken | ✅ Fixed |
| Custom channels | ⚠️  Hit-or-miss | ✅ Reliable |

---

## FAQ

### Q: Do I need to recreate my virtual channels?
**A:** No! This only changes how CC4C handles fullscreen. Your ESPN4CC4C virtual channels are unchanged.

### Q: Will this work with my custom Golf Channel?
**A:** Yes! The fallback timer is designed specifically to handle ANY channel that doesn't have a site-specific handler.

### Q: Can I use a different key instead of 'f'?
**A:** Not without modifying the code. The `sendFullscreenKey()` helper function can be called with any key combo, but you'd need to change the xdotool command.

### Q: Does this affect audio/video quality?
**A:** No, this only affects when/how fullscreen is triggered. Bitrate, resolution, and framerate are unchanged.

### Q: What if I pull a new cc4c image?
**A:** You'll need to re-copy the fixed main.js file after pulling updates, since the container filesystem resets. Keep your patched file in your ESPN4CC4C repo so it's easy to re-apply.

---

## File Naming Convention

For your records, here's the naming scheme:

```
main.cc4c-autofs.YYYYMMDD-HHMMSS.js
                 └─ timestamp when created

Examples:
main.cc4c-autofs.20251030-222408.js  ← Original (buggy)
main.cc4c-autofs.20241230-fixed.js   ← This version (fixed)
```

Keep both in your `contrib/cc4c/` directory so you can compare or rollback if needed.

---

## Getting Help

If you encounter issues:

1. **Check logs first:**
   ```bash
   docker logs -f cc4c | grep -E 'fullscreen|fallback|error|xdotool'
   ```

2. **Verify installation:**
   ```bash
   docker exec -it cc4c sh -lc "grep -c 'sendFullscreenKey' /home/chrome/main.js"
   ```
   Should return: `3` (function definition + 2 comments)

3. **Post in forum with:**
   - Version info (check lines 1-60 of your main.js)
   - Log excerpts showing the issue
   - Which channels exhibit the problem
   - Your `--fullscreenDelay` setting

---

## Credits

**Original Implementation:** Brad (@KineticMan)  
**Bug Discovery:** Forum community  
**Fixed Version:** December 30, 2024  
**Tested On:** Docker CC4C with ESPN4CC4C virtual channels
