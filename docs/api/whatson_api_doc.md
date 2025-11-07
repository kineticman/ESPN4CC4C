
# `/whatson` (and friends) — Quick Guide (v4.00)

These endpoints expose the **current ESPN+ event UID** per lane from your resolver’s plan DB. They’re built for lightweight automation (ADB launchers, dashboards, cron audits) and are shell-friendly.

> **New in v4.00**
> - **Short deeplinks are the default** (use only the first UUID: `play_id`).
> - Ask explicitly for the **full** value (`play_id:feed_id`) when needed.
> - `/channels` (XMLTV) and `/channels_db` (DB) are **separate** so tooling can compare “what the DB plans” vs “what the guide exposes.”

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
  - `include=deeplink_full` (optional): add a **full deeplink** field (`play_id:feed_id`).
  - `format=txt` (optional): return **plain text**.
  - `param=` (txt mode only):
    - `param=deeplink_url` → short deeplink (default for deeplink txt)
    - `param=deeplink_url_full` → full deeplink
    - *(empty)* → legacy **short `play_id`** only

- **Response (default JSON)**

```json
{
  "ok": true,
  "lane": 10,
  "event_uid": "f5bfa5bc-...-b4b2:32eb4b11-...-fcb2b",
  "at": "2025-11-06T19:00:00+00:00"
}
```

- `event_uid` is **stripped** of `espn-watch:`.
- If no event is active, `event_uid` is `null` (still `200 OK` JSON).
- With `include=` you’ll also see a `deeplink_url`.

- **TXT modes**
  - `?format=txt` → **short `play_id`**.
  - `?param=deeplink_url&format=txt` → **short deeplink**.
  - `?param=deeplink_url_full&format=txt` → **full deeplink**.
  - No event → **204 No Content**.

---

### 2) `GET /whatson_all`

Returns a **snapshot across all lanes** at an instant.

- **Query params**
  - `at=<ISO-8601>` (optional).
  - `include=deeplink` (optional): include **short** deeplinks per lane.
  - `include=deeplink_full` (optional): include **full** deeplinks per lane.

- **Response (JSON)**

```json
{
  "ok": true,
  "at": "2025-11-06T19:00:00+00:00",
  "items": [
    { "lane": 9,  "event_uid": "8fca688b-...:56f9ac3e...", "deeplink_url": "sportscenter://x-callback-url/showWatchStream?playID=8fca688b-..." },
    { "lane": 10, "event_uid": null, "deeplink_url": null }
  ]
}
```

- `lane` numbers are normalized (e.g., `"eplus14"` → `14`).
- Sorted numerically (1…N), then any non-numeric lanes alphabetically.
- With `include=deeplink`, each item gets a **short** `deeplink_url`; use `include=deeplink_full` for full links.

---

## “Event UID” refresher

- Format: `play_id:feed_id`.
- Example: `8fca688b-e27b-4352-a188-4a5438c21eac:56f9ac3e6246a61b8e2fa3b88bacc7a7`.
- The ESPN app typically only requires the **first UUID (play_id)**; hence short deeplinks are the default.

---

## Channels endpoints

- `GET /channels` → **XMLTV-backed** array (what Channels DVR sees).
- `GET /channels_db` → **DB-backed** authoritative list.

Use both to verify your guide export matches your plan DB.

---

## Quick smoke tests

**Bash**
```bash
BASE=http://<host>:8094
LANE=6
curl -s "$BASE/health" | jq .
curl -s "$BASE/channels" | jq '.[0:3]'
curl -s "$BASE/channels_db" | jq '.count, .channels[0:3]'
curl -s "$BASE/whatson/$LANE?include=deeplink" | jq .
curl -s "$BASE/whatson/$LANE?include=deeplink_full" | jq .
curl -s "$BASE/whatson/$LANE?format=txt"
curl -s "$BASE/whatson/$LANE?param=deeplink_url&format=txt"
curl -s "$BASE/whatson/$LANE?param=deeplink_url_full&format=txt"
curl -s "$BASE/whatson_all?include=deeplink" | jq '.items[0:6]'
curl -s "$BASE/whatson_all?include=deeplink_full" | jq '.items[0:6]'
```

**PowerShell**
```powershell
$Base = "http://<host>:8094"
$Lane = 6
(Invoke-WebRequest "$Base/health" -UseBasicParsing).Content
(Invoke-WebRequest "$Base/channels" -UseBasicParsing).Content
(Invoke-WebRequest "$Base/channels_db" -UseBasicParsing).Content
(Invoke-WebRequest "$Base/whatson/$Lane?include=deeplink" -UseBasicParsing).Content
(Invoke-WebRequest "$Base/whatson/$Lane?include=deeplink_full" -UseBasicParsing).Content
(Invoke-WebRequest "$Base/whatson/$Lane?format=txt" -UseBasicParsing).Content
(Invoke-WebRequest "$Base/whatson/$Lane?param=deeplink_url&format=txt" -UseBasicParsing).Content
(Invoke-WebRequest "$Base/whatson/$Lane?param=deeplink_url_full&format=txt" -UseBasicParsing).Content
(Invoke-WebRequest "$Base/whatson_all?include=deeplink" -UseBasicParsing).Content
(Invoke-WebRequest "$Base/whatson_all?include=deeplink_full" -UseBasicParsing).Content
```

**Version:** v4.00 • **File:** `docs/api/whatson_api_doc.md`

