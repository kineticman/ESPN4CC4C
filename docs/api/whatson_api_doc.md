# `/whatson` (and friends) — Quick Guide (v4.01, short‑only)

These endpoints expose the **current ESPN+ event UID** per lane from your resolver’s plan DB. They’re built for lightweight automation (ADB launchers, dashboards, cron audits) and are shell‑friendly.

> **What changed in v4.01**
> - **Short deeplinks are the only default/output**. We no longer emit or document any “full” (`play_id:feed_id`) variants.
> - Any request that previously asked for a “full” deeplink now returns the **short** deeplink instead (backward‑compatible, safer).

---

## Endpoints

### 1) `GET /whatson/{lane}`

Returns the **active event’s ESPN UID** for a single lane at a given instant.

- **Lane input**
  - Accepts either a number (`10`) or a channel id string (`eplus10`).
  - Internally it tries both forms against the DB (e.g., `eplus10` and `10`).

- **Query params**
  - `at=<ISO-8601>` (optional): audit at a specific time.
  - `include=deeplink` (optional): add a **short deeplink** field to JSON.
  - `format=txt` (optional): return **plain text**.
  - `param=` (txt mode only):
    - `param=deeplink_url` → short deeplink
    - *(empty)* → legacy **short `play_id`** only

- **Response (default JSON)**

```json
{
  "ok": true,
  "lane": 10,
  "event_uid": "f5bfa5bc-...-b4b2",
  "at": "2025-11-06T19:00:00+00:00",
  "deeplink_url": "sportscenter://x-callback-url/showWatchStream?playID=f5bfa5bc-...-b4b2" // only when include=deeplink
}
```

- `event_uid` is the **short** `play_id` (the resolver strips any `:feed_id` suffix internally).
- If no event is active, `event_uid` is `null` (still `200 OK` JSON).

- **TXT modes**
  - `?format=txt` → **short `play_id`**.
  - `?param=deeplink_url&format=txt` → **short deeplink**.
  - No event → **204 No Content**.

---

### 2) `GET /deeplink/{lane}`

Returns a **short deeplink** (plain text) for the current event in the lane:

```
sportscenter://x-callback-url/showWatchStream?playID=<play_id>
```

- Always **short** (no `:<hash>` suffix).
- `204 No Content` when there is no current event.

---

### 3) `GET /whatson_all`

Returns a **snapshot across all lanes** at an instant.

- **Query params**
  - `at=<ISO-8601>` (optional).
  - `include=deeplink` (optional): include **short** deeplinks per lane.

- **Response (JSON)**

```json
{
  "ok": true,
  "at": "2025-11-06T19:00:00+00:00",
  "items": [
    { "lane": 9,  "event_uid": "8fca688b-...-21eac", "deeplink_url": "sportscenter://x-callback-url/showWatchStream?playID=8fca688b-...-21eac" },
    { "lane": 10, "event_uid": null, "deeplink_url": null }
  ]
}
```

- `lane` numbers are normalized (e.g., `"eplus14"` → `14`).
- Sorted numerically (1…N), then any non‑numeric lanes alphabetically.

---

## “Event UID” refresher

- We use **short** `play_id` everywhere (first UUID only).
- Example: `8fca688b-e27b-4352-a188-4a5438c21eac`.
- This is what the ESPN app expects most consistently; it keeps clients simple and robust.

---

## Channels endpoints

- `GET /channels` → **XMLTV‑backed** array (what Channels DVR sees).
- `GET /channels_db` → **DB‑backed** authoritative list.

Use both to verify your guide export matches your plan DB.

---

## Quick smoke tests (dev server: 192.168.86.72)

**Bash**
```bash
BASE=http://192.168.86.72:8094
LANE=6
curl -s "$BASE/health" | jq .
curl -s "$BASE/channels" | jq '.[0:3]'
curl -s "$BASE/channels_db" | jq '.count, .channels[0:3]'
curl -s "$BASE/whatson/$LANE?include=deeplink" | jq .
curl -s "$BASE/whatson/$LANE?format=txt"
curl -s "$BASE/whatson/$LANE?param=deeplink_url&format=txt"
curl -s "$BASE/deeplink/$LANE"
```

**PowerShell**
```powershell
$Base = "http://192.168.86.72:8094"
$Lane = 6
(Invoke-WebRequest "$Base/health" -UseBasicParsing).Content
(Invoke-WebRequest "$Base/channels" -UseBasicParsing).Content
(Invoke-WebRequest "$Base/channels_db" -UseBasicParsing).Content
(Invoke-WebRequest "$Base/whatson/$Lane?include=deeplink" -UseBasicParsing).Content
(Invoke-WebRequest "$Base/whatson/$Lane?format=txt" -UseBasicParsing).Content
(Invoke-WebRequest "$Base/whatson/$Lane?param=deeplink_url&format=txt" -UseBasicParsing).Content
(Invoke-WebRequest "$Base/deeplink/$Lane" -UseBasicParsing).Content
```

**Version:** v4.01 • **File:** `docs/api/whatson_api_doc.md`
