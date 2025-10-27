# ESPN Clean v2 — Changelog

# CHANGELOG

## [v2.2.2] - 2025-10-26
### Added
- Dockerized single-container deployment (resolver + cron scheduler).
- Health-gated update routine with jitter and log rotation.
- Weekly SQLite VACUUM.
- `espn4cc_bootstrap.sh` and `espn4cc_verify.sh`.

### Fixed
- Clarified FastAPI module path: `bin.vc_resolver:app`.

### Notes
- Ensure `VC_RESOLVER_BASE_URL` uses LAN IP (not `localhost`) for Channels DVR.


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

## v2.0.2 — pipeline + resolver polish
- XMLTV: placeholder title = “Stand By”; add sport-specific `<category>` plus “Live” and “Sports Event” only for real events; always include generic “Sports” for events.
- Resolver: default fallback to slate; slate now points at local webpage (`http://<host>:8888/slate.html`).
- M3U/XMLTV `<url>` entries call resolver without `only_live`.
- Systemd: single pipeline timer (`vc-pipeline-v2.timer`) drives ingest→plan→publish; removed old `vc-plan` timer usage and bad flags.
- Repo hygiene: ignore `out/`, `logs/`, `releases/`, `backups/`; moved artifacts to `releases//`; DB backups to `backups/`.
2025-10-24  xmltv: enrich <desc> with summary/sport/title

## v2.2.4 — 2025-10-27
- fix: point slate template to `/slate?lane={lane}` (was `/static/standby.html`)
- feat: add `/standby?lane=…` redirect to `/slate`
- feat: HEAD handler for `/slate` to support `curl -I`
- chore: repo hygiene (CODEOWNERS, LICENSE, CI/healthcheck)
