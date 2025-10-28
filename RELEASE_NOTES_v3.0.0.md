# ESPN4CC4C v3.0.0

- Resolver + outputs: **/out/epg.xml**, **/out/playlist.m3u** (canonical)
- **bootstrap.sh**: builds/starts container, waits on **/health**, prints XML/M3U counts + first IDs
- **update_schedule.sh**: env-safe, calls db_migrate, builds plan w/ .env tunables, generates XMLTV/M3U w/ explicit flags, GET-only sanity
- README updated for /out paths + bootstrap flow
- Standing rules: GET-only checks; never use proxies for ESPN endpoints

## Commits since v0.1.1-rc6
- 5c5fb9b docs: update README for /out paths, flagged M3U writer, bootstrap flow (2025-10-28 12:22:10 -0400)
- 2aa0301 rc6: /out M3U sanity; pass resolver/CC flags to m3u_from_plan.py; clean shell (2025-10-28 12:10:43 -0400)
