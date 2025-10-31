# ESPN4CC4C — Combined Release Notes

Generated: 2025-10-31 14:15:13


---

## v3.1.0  
_Source: RELEASE_NOTES_v3.1.0.md_

## ESPN4CC4C v3.1.0

- Fresh-install guardrails (no /app paths on host)
- Bootstrap/update scripts: health-gated first run + ingest-if-empty
- DB migrator v3 (TEXT PKs, sticky map fix), container-side only
- First-run sanity summary & first non-placeholder title
- Install summary printed (XMLTV/M3U URLs)

**Endpoints for Channels DVR**
- XMLTV: `http://<LAN-IP>:8094/out/epg.xml`
- M3U:   `http://<LAN-IP>:8094/out/playlist.m3u`

---

## v3.0.17  
_Source: RELEASE_NOTES_v3.0.17.md_

## v3.0.17 — fresh-install wins
- Host/Container path hygiene: never write /app/* on host
- `bootstrap.sh`: health-gated first run, DB migrate inside container, install summary
- `update_schedule.sh`: migrator + ingest + plan + XMLTV/M3U + sanity probe
- `.env.example`: host-relative paths (DB/OUT/LOGS), easy LAN wiring
- `db_migrate.py`: sticky map + TEXT ids; safe for fresh & upgrades
- Docker entrypoint: root-safe tz/cron; always ensure /app dirs

---

## v3.0.0  
_Source: RELEASE_NOTES_v3.0.0.md_

# ESPN4CC4C v3.0.0

- Resolver + outputs: **/out/epg.xml**, **/out/playlist.m3u** (canonical)
- **bootstrap.sh**: builds/starts container, waits on **/health**, prints XML/M3U counts + first IDs
- **update_schedule.sh**: env-safe, calls db_migrate, builds plan w/ .env tunables, generates XMLTV/M3U w/ explicit flags, GET-only sanity
- README updated for /out paths + bootstrap flow
- Standing rules: GET-only checks; never use proxies for ESPN endpoints

## Commits since v0.1.1-rc6
- 5c5fb9b docs: update README for /out paths, flagged M3U writer, bootstrap flow (2025-10-28 12:22:10 -0400)
- 2aa0301 rc6: /out M3U sanity; pass resolver/CC flags to m3u_from_plan.py; clean shell (2025-10-28 12:10:43 -0400)

---

## unknown  
_Source: RELEASE_NOTES_v3.97.md_

## Highlights
- Cron schedule now source-controlled and mounted into the container.
- Daily refresh at 02:00 local; weekly VACUUM Sunday 03:17 local.
- Preserves GET-only checks; no proxies for ESPN endpoints.

## Upgrade Notes
1. git pull the repo.
2. Ensure this volume is present in docker-compose.yml:
   - ./tools/cron/espn4cc:/etc/cron.d/espn4cc:ro
3. docker compose up -d

## Verification
- docker compose exec espn4cc bash -lc 'ls -l /etc/cron.d/espn4cc && tail -n 40 /app/logs/schedule.log'
- curl http://<host>:8094/health
- Check /out/epg.xml and /out/playlist.m3u updated times.

## Notes
- If you want hourly refresh too, add:
  7 * * * * root /app/bin/refresh_in_container.sh >> /app/logs/schedule.log 2>&1
