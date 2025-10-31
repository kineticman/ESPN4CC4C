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
