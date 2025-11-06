# `/whatson` (and friends) — Quick Guide

These endpoints expose the **current ESPN+ event UID** per lane from your resolver’s plan DB. They’re built for lightweight automation (ADB launchers, dashboards, cron audits) and are shell-friendly.

---

## Endpoints

### 1) `GET /whatson/{lane}`

Returns the **active event’s ESPN UID** for a single lane at a given instant.

- **Lane input**  
  Accepts either a number (`10`) or a channel id string (`eplus10`).  
  Internally it tries both forms against the DB (e.g., `eplus10` and `10`).

- **Query params**
  - `at=<ISO-8601>` (optional): “time travel” audit. Examples:
    - `2025-11-06T19:00:00Z`
    - `2025-11-06T14:00:00-05:00`
    - `2025-11-06 19:00:00` (naive → treated as UTC)
  - `format=txt` (optional): return just the **play_id** (plain text). See examples.

- **Response (default JSON)**
  ```json
  {
    "ok": true,
    "lane": 10,                                       // normalized: number if possible
    "event_uid": "f5bfa5bc-...-b4b2:32eb4b11-...-fcb2b",  // "play_id:feed_id"
    "at": "2025-11-06T19:00:00+00:00"
  }
  ```
  - `event_uid` is **already stripped** of the `espn-watch:` prefix.
  - If no event is active, `event_uid` is `null` (still `200 OK` in JSON mode).

- **Response (`format=txt`)**
  - If event is active: plain text **play_id** only (no quotes, no newline guaranteed by `curl -s`).
  - If **no** event is active: **204 No Content** (empty body).

---

### 2) `GET /whatson_all`

Returns a **snapshot across all lanes** at an instant.

- **Query params**
  - `at=<ISO-8601>` (optional): same parsing rules as `/whatson`.

- **Response (JSON)**
  ```json
  {
    "ok": true,
    "at": "2025-11-06T19:00:00+00:00",
    "items": [
      { "lane": 9,  "event_uid": "8fca688b-...:56f9ac3e..." },
      { "lane": 10, "event_uid": "f5bfa5bc-...:32eb4b11..." },
      { "lane": 11, "event_uid": null },
      ...
    ]
  }
  ```
  - `lane` numbers are normalized (e.g., `"eplus14"` becomes `14`).
  - List is **sorted** numerically (1…N), then any non-numeric lanes alphabetically.

---

## What’s an “event UID”?

- Format: `play_id:feed_id` (two UUIDs joined by a colon).
- Example:  
  `8fca688b-e27b-4352-a188-4a5438c21eac:56f9ac3e6246a61b8e2fa3b88bacc7a7`
- This is derived from ESPN’s internal “watch” identifier. We **strip** the `espn-watch:` prefix for convenience.

If you only need the **play_id** (first UUID), use `format=txt` on `/whatson/{lane}`.

---

## Common usage

### Get the active event for one lane (JSON)
```bash
curl -sS "http://<resolver-host>:8094/whatson/9" | jq
```

### Get only the play_id as plain text (best for scripts)
```bash
curl -sS "http://<resolver-host>:8094/whatson/9?format=txt"
# → 8fca688b-e27b-4352-a188-4a5438c21eac
```

### Time travel audit for one lane
```bash
curl -sS "http://<resolver-host>:8094/whatson/9?at=2025-11-06T19:00:00Z" | jq
```

### All lanes (JSON)
```bash
curl -sS "http://<resolver-host>:8094/whatson_all" | jq
```

### Filter to only lanes with an event (now)
```bash
curl -sS "http://<resolver-host>:8094/whatson_all" | jq -r '.items[] | select(.event_uid) | "\(.lane)\t\(.event_uid)"'
```

---

## ADB launch example (Fire TV / Android TV)

Use the **play_id** to open the ESPN stream via deeplink:

```bash
LANE=9
PLAYID=$(curl -sS "http://<resolver-host>:8094/whatson/$LANE?format=txt")
if [ -n "$PLAYID" ]; then
  adb -s 192.168.86.37:5555 shell am start     -n com.espn.gtv/com.espn.startup.presentation.StartupActivity     -d "sportscenter://x-callback-url/showWatchStream?playID=$PLAYID"
else
  echo "No active event on lane $LANE"
fi
```

---

## Status codes & behaviors

- **200 OK (JSON)** — Always returned by `/whatson` and `/whatson_all` in JSON mode; `event_uid` is either a string or `null`.
- **200 OK (text/plain)** — `/whatson?format=txt` when an event is active (content = `play_id`).
- **204 No Content** — `/whatson?format=txt` when **no** event is active (clean for shell checks).
- **404** — DB missing/unreadable or there’s no `plan_run` row yet.

---

## Time parsing rules (`at=`)

- Accepts:
  - `Z`-suffixed UTC: `2025-11-06T19:00:00Z`
  - Offset: `2025-11-06T14:00:00-05:00`
  - Naive: `2025-11-06 19:00:00` (treated as UTC)
- Internally normalized to a UTC ISO string for DB comparisons: `start_utc <= at < end_utc`.

---

## Lane normalization

- Input can be `eplus10` **or** `10`.
- DB lookup tries both `eplus10` and `10` to match whatever you stored in `plan_slot.channel_id`.
- Output normalizes to the numeric lane (`10`) when possible.
