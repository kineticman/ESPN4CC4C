# ESPN Clean v2 — Changelog

## v2.0.1-night1 (2025-10-24)
**Milestone:** Slate fallback, resolver hardening, stable M3U/XMLTV output

### 🧠 Overview
- Resolver now returns *something* 100% of the time (live ESPN+ or fallback slate)
- End-to-end pipeline proven: ingest → DB → plan → M3U/XML → resolver tune
- All paths use LAN IP instead of 127.0.0.1

### ⚙️ Major changes
| Area | Update |
|------|--------|
| **vc_resolver.py** | Default `only_live=0`; `VC_SLATE_URL` support; cleaner debug; 302 to ESPN when live, slate when idle |
| **Systemd unit** | `vc-resolver-v2.service` runs as brad; proper env + perms; uses python -m uvicorn |
| **M3U generator** | ChromeCapture URLs with LAN IP; removed `only_live=1` reliance |
| **XMLTV generator** | Emits from v2 schema; validated programmes |
| **Ingest/DB** | Confirmed `plan_slot`, `events`, `feeds`; backfill feeds to ESPN player URLs |
| **Health/Logs** | `/health` JSON; logs at `/var/log/espnvc-v2/vc_resolver.jsonl` |
| **Env Defaults** | Global host IP `192.168.86.72`; `VC_SLATE_URL=http://192.168.86.72/slate.mp4` |

### 🧩 Behavior
| Scenario | Result |
|---------|--------|
| Live slot | 302 → ESPN player |
| Placeholder | 302 → slate |
| `/health` | 200 JSON |
| `/vc/{lane}/debug` | 200 JSON (lane, slot, feed, slate) |

### 🗂️ Verified Artifacts
- `out/virtual_channels.m3u` (40 lanes)
- `out/virtual_channels.xml` (events + placeholders)
- `/etc/systemd/system/vc-resolver-v2.service`
- `/var/log/espnvc-v2/vc_resolver.jsonl`

### 🧱 Next steps
1) Timer for hourly ingest/plan/publish  
2) Optional per-lane slate customization  
3) Optional Channels lineup nudge post-publish

**Tag:** `v2.0.1-night1` • **Date:** 2025-10-24 00:15 EDT • **Maintainer:** Brad Herrold
