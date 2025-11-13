# ESPN4CC4C Virtual Channel Resolver API Documentation

## Base URL
```
http://your-server:8094
```

---

## Core Endpoints

### 1. Health Check
**GET** `/health`

Check if the resolver is running.

**Response:**
```json
{
  "status": "ok",
  "version": "4.x.x"
}
```

---

### 2. Current Channel Status
**GET** `/whatson/{lane}`

Get what's currently playing on a specific channel/lane.

**Parameters:**
- `lane` (path) - Channel number (1-40)
- `at` (query, optional) - ISO timestamp, defaults to now
- `include` (query, optional) - Set to `deeplink` to include deeplink URL
- `deeplink` (query, optional) - Set to `1` to include deeplink URL
- `dynamic` (query, optional) - Set to `1` to include deeplink URL
- `format` (query, optional) - Set to `txt` for plain text response
- `param` (query, optional) - For text format: `deeplink_url`, `deeplink_url_full`

**Examples:**

Basic JSON (no deeplink):
```bash
curl "http://192.168.86.72:8094/whatson/1"
```
Response:
```json
{
  "ok": true,
  "lane": 1,
  "event_uid": "espn-watch:UUID:hash",
  "at": "2025-11-13T11:41:25+00:00",
  "deeplink_url": null
}
```

With deeplink URL:
```bash
curl "http://192.168.86.72:8094/whatson/1?include=deeplink"
# OR
curl "http://192.168.86.72:8094/whatson/1?deeplink=1"
# OR
curl "http://192.168.86.72:8094/whatson/1?dynamic=1"
```
Response:
```json
{
  "ok": true,
  "lane": 1,
  "event_uid": "07927671-cdfb-4de6-9586-3efbd2dd0a52:hash",
  "at": "2025-11-13T11:41:25+00:00",
  "deeplink_url": "sportscenter://x-callback-url/showWatchStream?playID=07927671-cdfb-4de6-9586-3efbd2dd0a52"
}
```

Plain text deeplink:
```bash
curl "http://192.168.86.72:8094/whatson/1?format=txt&param=deeplink_url"
```
Response:
```
sportscenter://x-callback-url/showWatchStream?playID=07927671-cdfb-4de6-9586-3efbd2dd0a52
```

---

### 3. All Channels Status
**GET** `/whatson/all`

Get status across all channels at once.

**Parameters:**
- `at` (query, optional) - ISO timestamp
- `include` (query, optional) - Set to `deeplink` to include deeplink URLs
- `deeplink` (query, optional) - Set to `1` to include deeplink URLs
- `dynamic` (query, optional) - Set to `1` to include deeplink URLs

**Example:**
```bash
curl "http://192.168.86.72:8094/whatson/all?include=deeplink"
```

Response:
```json
{
  "ok": true,
  "at": "2025-11-13T11:41:25+00:00",
  "items": [
    {
      "lane": 1,
      "channel_id": 1,
      "kind": "event",
      "event_uid": "UUID:hash",
      "deeplink_url": "sportscenter://x-callback-url/showWatchStream?playID=UUID"
    },
    {
      "lane": 2,
      "channel_id": 2,
      "kind": "placeholder",
      "event_uid": null,
      "deeplink_url": null
    }
  ]
}
```

---

### 4. Virtual Channel Stream
**GET** `/vc/{channel_id}`

Get the HLS stream for a virtual channel. This is what your DVR/player actually calls.

**Parameters:**
- `channel_id` (path) - Channel number (1-40)

**Example:**
```bash
curl "http://192.168.86.72:8094/vc/1"
```

**Response:**
- `302 Redirect` - Redirects to the actual ESPN+ stream URL
- `204 No Content` - Nothing scheduled on this channel right now
- `404 Not Found` - Invalid channel or no plan available

**This endpoint:**
1. Checks what's scheduled on the channel NOW
2. Looks up the event's stream URL from the feeds table
3. Redirects your player to the ESPN+ stream

---

### 5. EPG (Electronic Program Guide)
**GET** `/out/epg.xml`

Get the XMLTV EPG file for all channels.

**Example:**
```bash
curl "http://192.168.86.72:8094/out/epg.xml"
```

**Response:** XMLTV XML file with:
- Channel definitions
- Programme schedules
- Rich metadata (titles, descriptions, categories, icons, language)

**Features:**
- ✅ Proper descriptions (e.g., "NCAA Football: SMU vs. Boston College (ACCN)")
- ✅ Categories (Sports, Football, NCAA Football, Network, Live)
- ✅ Icons (ESPN artwork URLs)
- ✅ Language tags (en, es, etc.)

---

### 6. M3U Playlist
**GET** `/out/playlist.m3u`

Get the M3U playlist with all virtual channels.

**Example:**
```bash
curl "http://192.168.86.72:8094/out/playlist.m3u"
```

**Response:** M3U8 playlist with:
- Channel names
- Channel numbers (LCN)
- Stream URLs pointing to `/vc/{channel_id}`
- Channel groups

---

## Important API Behavior Changes

### ⚠️ Deeplink URLs Are Now Opt-In

**OLD (might have been automatic):**
- Deeplink URLs always included

**NEW (current behavior):**
- Deeplink URLs are `null` by default
- Must explicitly request with `?include=deeplink` or `?deeplink=1`

**If your client broke:** Add `?include=deeplink` to whatson requests!

---

## Query Parameter Reference

### For `/whatson/{lane}` and `/whatson/all`

| Parameter | Values | Purpose |
|-----------|--------|---------|
| `include` | `deeplink` | Include deeplink_url in JSON response |
| `deeplink` | `1` | Include deeplink_url in JSON response |
| `dynamic` | `1` | Include deeplink_url in JSON response |
| `at` | ISO timestamp | Query status at specific time (default: now) |
| `format` | `txt` | Return plain text instead of JSON |
| `param` | `deeplink_url`, `deeplink_url_full` | For text format, which value to return |

---

## Response Codes

| Code | Meaning |
|------|---------|
| `200` | Success |
| `204` | No Content (nothing scheduled, placeholder) |
| `302` | Redirect (for `/vc/{channel_id}` streams) |
| `404` | Not Found (invalid channel, no plan) |
| `500` | Server Error |

---

## Integration Examples

### Channels DVR
```
EPG URL: http://192.168.86.72:8094/out/epg.xml
M3U URL: http://192.168.86.72:8094/out/playlist.m3u
```

### Custom Client Polling
```python
import requests

# Check what's playing on channel 5
response = requests.get("http://192.168.86.72:8094/whatson/5?include=deeplink")
data = response.json()

if data["ok"] and data["deeplink_url"]:
    print(f"Playing: {data['event_uid']}")
    print(f"Deeplink: {data['deeplink_url']}")
else:
    print("Nothing scheduled or placeholder")
```

### Fire TV ADB Integration
```bash
# Get deeplink and launch ESPN app
DEEPLINK=$(curl -s "http://192.168.86.72:8094/whatson/1?format=txt&param=deeplink_url")
adb shell am start -a android.intent.action.VIEW -d "$DEEPLINK"
```

---

## Database Schema Reference

The resolver queries these tables:

### `plan_slot`
- Current schedule by channel/lane
- Links to `events` via `event_id`

### `events`
- Event metadata (title, sport, league, network, language, etc.)
- NEW fields: `image`, `language`, `league_abbr`, `sport_abbr`, `packages`, `event_type`

### `feeds`
- Stream URLs for events
- Links to `events` via `event_id`

### `channel`
- Channel definitions
- Channel numbers (chno), names, active status

---

## Troubleshooting

### Deeplink is NULL
**Problem:** `deeplink_url` is always `null`

**Solution:** Add `?include=deeplink` to your request
```bash
# Wrong
curl "http://192.168.86.72:8094/whatson/1"

# Right
curl "http://192.168.86.72:8094/whatson/1?include=deeplink"
```

### 204 No Content on /vc/{channel_id}
**Problem:** Channel returns 204 instead of stream

**Causes:**
1. Nothing scheduled on that channel right now (placeholder/gap)
2. Event has no feed URL in database
3. Plan hasn't been generated yet

**Check:**
```bash
curl "http://192.168.86.72:8094/whatson/{channel_id}"
```

### EPG is Empty
**Problem:** `/out/epg.xml` has no programmes

**Causes:**
1. No plan has been built yet
2. Database has no events
3. All events were filtered out

**Fix:**
```bash
# Inside container
python3 /app/bin/ingest_watch_graph_all_to_db.py --db /app/data/eplus_vc.sqlite3 --days 3
python3 /app/bin/build_plan.py --db /app/data/eplus_vc.sqlite3
python3 /app/bin/xmltv_from_plan.py --db /app/data/eplus_vc.sqlite3 --out /app/out/epg.xml
```

---

## Rate Limiting & Performance

- No explicit rate limits on endpoints
- `/vc/{channel_id}` performs database query + redirect (fast)
- `/whatson/all` queries all channels (slightly slower)
- EPG/M3U files are static (cached by web server)

---

## Version History

### v4.x (Current)
- ✅ Deeplink URLs opt-in via query parameter
- ✅ Rich XMLTV metadata (icons, language, enhanced descriptions)
- ✅ Event filtering support
- ✅ Language field in database
- ✅ Enhanced categories and metadata

### v3.x
- Basic XMLTV/M3U generation
- Simple deeplink support

---

## Support

If something's broken after today's updates:

1. **Check if you need `?include=deeplink`** in your whatson calls
2. **Verify EPG/M3U URLs** haven't changed
3. **Check container logs:** `docker logs espn4cc4c`
4. **Test health:** `curl http://192.168.86.72:8094/health`

The core `/vc/{channel_id}` streaming endpoint behavior is **unchanged** - it still works the same way!
