# CC4C Fullscreen Helper - Fixed Version Changelog

## Version: main_fixed.js
**Date:** December 30, 2024  
**Original:** main.cc4c-autofs.20251030-222408.js (863 lines)  
**Fixed:** main_fixed.js (894 lines)  
**SHA256:** `3de6b5c82e8ad0457e290891347de5ec6c2c3d91d28e1917baee2afac102f210`

---

## Bugs Fixed

### 🐛 Bug #1: Duplicate Fallback Timer Setup
**Problem:** Lines 1-16 defined `armFullscreenFallback()` function, but lines 18-35 duplicated the EXACT same logic inline. This caused TWO fallback timers to be created for every stream request.

**Fix:** Removed duplicate inline code (lines 18-35). Now only the function definition exists.

**Impact:** Eliminates double-firing of fallback timer.

---

### 🐛 Bug #2: Flag Cleared at Wrong Time
**Problem:** `globalThis.__cc4c_sentFullscreen = false` was cleared inside `armFullscreenFallback()`, which meant:
- Flag reset every time the function was called
- Race conditions between site handlers and fallback timer
- Flag could be cleared AFTER a site handler already set it to true

**Fix:** 
- Removed flag clearing from `armFullscreenFallback()`
- Added flag reset at the START of `setupPage()` function (line 423)
- Flag now only resets once per NEW stream request

**Impact:** Proper flag lifecycle prevents race conditions.

---

### 🐛 Bug #3: ESPN/NBC Handler Didn't Check Flag
**Problem:** The ESPN/NBC handler (lines 668-684) sent `Shift+F` via xdotool WITHOUT checking if fullscreen was already sent. Additionally, it had duplicate flag-setting code:
```javascript
globalThis.__cc4c_sentFullscreen = true;
globalThis.__cc4c_sentFullscreen = true;  // duplicate!
```

**Fix:**
- Added flag check before sending xdotool command
- Removed duplicate flag-setting lines
- Cleaned up flag management code

**Impact:** Prevents ESPN/NBC handler from conflicting with fallback timer.

---

### 🐛 Bug #4: Race Condition Causing Toggle
**Problem:** Timeline of bug causing fullscreen to toggle on then off:
```
Time 0s:   Request → flag cleared → fallback armed for 15s
Time 8s:   ESPN handler fires → sends Shift+F → fullscreen ON
Time 8s:   ESPN sets flag to true (async)
Time 15s:  Fallback fires → flag might still be false → sends 'f' → fullscreen OFF
```

**Fix:** All fixes above combine to eliminate this race condition:
- Single timer setup
- Flag cleared only at request start
- All handlers check flag before sending
- Proper flag coordination throughout request lifecycle

**Impact:** Fullscreen stays ON once triggered, no toggle behavior.

---

## New Features Added

### ✨ Helper Function: sendFullscreenKey()
**Location:** Lines 29-56

A new helper function that encapsulates proper fullscreen key sending with automatic flag checking:

```javascript
function sendFullscreenKey(keyCombo = 'f', label = 'generic') {
  // Checks flag before sending
  // Cancels fallback timer on success
  // Sets flag after sending
  // Includes proper error handling
  // Returns a Promise
}
```

**Benefits:**
- Makes it easy to add new site-specific handlers correctly
- Prevents duplicate code
- Ensures consistent flag management
- Better logging with labeled handlers

**Usage Example:**
```javascript
await sendFullscreenKey('shift+f', 'ESPN');
```

---

### ✨ Enhanced Logging
**Changes:**
- More descriptive log messages
- Handler-specific labels (e.g., "[ESPN]", "[Fallback]")
- Explicit "skipping duplicate" messages when flag check prevents re-sending
- Better error messages with context

**Benefits:**
- Easier debugging
- Clear visibility into what's happening
- Can track exactly which handler sent fullscreen

---

## Code Structure Improvements

### 📐 Better Organization
1. **Helper functions at top** (lines 1-57)
   - `armFullscreenFallback()`
   - `sendFullscreenKey()`
   
2. **Requires and setup** (lines 58-150)
   - Module imports
   - Argument parsing
   - Configuration

3. **Main logic** (lines 151+)
   - Browser management
   - Stream handling
   - Site-specific handlers

### 📝 Improved Comments
- Explains WHY flag is NOT cleared in `armFullscreenFallback()`
- Documents flag lifecycle clearly
- Notes about timer cancellation
- Helper function usage documentation

---

## Testing Recommendations

### Test Case 1: ESPN/NBC Streams
**Expected:** Fullscreen triggers once at configured delay, stays fullscreen
```bash
docker logs -f cc4c | grep -i 'espn\|fullscreen\|fallback'
```

Should see:
```
[cc4c] Arming per-request fullscreen fallback timer...
Waiting 15000ms for stream to fully load...
Sending F key via xdotool (OS-level input)
Shift+F sent successfully via xdotool
```

Should NOT see:
```
Fallback: site not recognized...  # This means handler worked!
```

### Test Case 2: Custom Channels (Golf, etc.)
**Expected:** Fallback timer fires and triggers fullscreen
```bash
docker logs -f cc4c | grep -i 'fullscreen\|fallback'
```

Should see:
```
[cc4c] Arming per-request fullscreen fallback timer...
Fallback: site not recognized or no fullscreen sent — sending F now…
Fallback F key sent successfully via xdotool
```

### Test Case 3: No Double-Toggle
**Expected:** Fullscreen key sent ONCE, not twice

Check logs for:
- Only ONE "sent successfully" message per stream
- No "Fallback: fullscreen already sent by site handler, skipping" (means handler beat fallback)
- Stream stays fullscreen, doesn't toggle back

---

## Migration Guide

### From Old Version to Fixed Version

1. **Backup current file:**
```bash
docker exec -it cc4c sh -lc 'cp /home/chrome/main.js /home/chrome/main.js.bak.$(date +%Y%m%d-%H%M%S)'
```

2. **Verify backup:**
```bash
docker exec -it cc4c sh -lc 'ls -l /home/chrome/main.js*'
```

3. **Copy new fixed file:**
```bash
cd ~/Projects/ESPN4CC4C
docker cp contrib/cc4c/main_fixed.js cc4c:/home/chrome/main.js
```

4. **Restart container:**
```bash
docker restart cc4c
```

5. **Test with streams:**
```bash
docker logs -f cc4c | grep -i 'fullscreen\|fallback'
```

### Rollback if Needed
```bash
docker exec -it cc4c sh -lc 'latest=$(ls -1t /home/chrome/main.js.bak.* 2>/dev/null | head -n1); if [ -n "$latest" ]; then cp -v "$latest" /home/chrome/main.js; else echo "No backup found"; fi'
docker restart cc4c
```

---

## Future Development

### Adding New Site Handlers
When adding support for a new streaming site, use this pattern:

```javascript
else if (u.includes('newsite.com')) {
  console.log('URL contains newsite.com')
  try {
    // Site-specific setup code...
    await delay(2000);
    
    // Use the helper function for fullscreen
    await sendFullscreenKey('f', 'NewSite');
    
    console.log('NewSite stream setup complete')
  } catch (e) {
    console.log('Error for newsite.com:', e)
  }
}
```

The `sendFullscreenKey()` helper automatically:
- Checks if fullscreen already sent
- Cancels the fallback timer
- Sets the flag
- Logs appropriately

---

## Known Limitations

1. **Requires xdotool:** The container must have xdotool installed for keyboard simulation
2. **Fixed key mapping:** Assumes sites use 'f' or 'shift+f' for fullscreen
3. **Timing dependent:** Some sites may need delay adjustments via `--fullscreenDelay`
4. **Single display:** Works with one browser instance at a time

---

## Questions & Support

If you encounter issues:

1. **Check logs:** `docker logs -f cc4c | grep -i 'fullscreen\|fallback\|error'`
2. **Verify file copied:** `docker exec -it cc4c sh -lc "head -60 /home/chrome/main.js"`
3. **Check for helper function:** Should see `sendFullscreenKey` in the output
4. **Adjust delay if needed:** Add `--fullscreenDelay=20000` to container command

---

## Credits

**Original Implementation:** Brad (@KineticMan)  
**Bug Discovery:** Forum poster (identified toggle behavior)  
**Fixed Version:** December 30, 2024
