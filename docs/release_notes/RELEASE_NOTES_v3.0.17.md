## v3.0.17 — fresh-install wins
- Host/Container path hygiene: never write /app/* on host
- `bootstrap.sh`: health-gated first run, DB migrate inside container, install summary
- `update_schedule.sh`: migrator + ingest + plan + XMLTV/M3U + sanity probe
- `.env.example`: host-relative paths (DB/OUT/LOGS), easy LAN wiring
- `db_migrate.py`: sticky map + TEXT ids; safe for fresh & upgrades
- Docker entrypoint: root-safe tz/cron; always ensure /app dirs
