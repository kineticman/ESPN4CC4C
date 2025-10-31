# Changelog

## [3.96] - 2025-10-31
- Fix: standby /vc/* 500 due to missing RedirectResponse import
- Docs: cleaned CC4C fullscreen helper guide


## v0.1.1 — 2025-10-30
- Windows + Linux bootstrap verified
- README updated (Windows onboarding + notes)
- No-proxy + GET-only sanity checks reiterated
- Minor bootstrap.sh fixes

## v0.1.0 — Initial Docker edition
- FastAPI resolver on :8094 (EPG/M3U/health)
- Idempotent DB migration + plan builder
- 40 virtual channels (default)
## v3.5 — 2025-10-30
- Windows + Linux bootstrap verified end-to-end
- README refreshed (onboarding + sanity checks)
- Small bootstrap.sh fixes and cleanup

## v3.7
- Seed channels 20010+ (EPlus naming)
- Env-driven M3U defaults (+ VC_M3U_PATH)
- Guarded version import

## v3.95 — 2025-10-30
- fix(resolver): route collision on /channels (split DB vs XMLTV list)
- fix(resolver): add missing imports (JSONResponse, RedirectResponse, HTMLResponse)
- chore: env alignment (DB path), tidy OUT_DIR handling

## v3.97 — 2025-10-31
- Ops: bind-mount cron schedule into container under `/etc/cron.d/espn4cc`
- Ensure cron.d file has `root:root 0644` so Debian cron honors it
- Daily 02:00 refresh + weekly VACUUM included by default
- Health/sanity checks retained (GET-only), no proxies

## v3.97 — 2025-10-31
- Ops: bind-mount cron schedule into container under `/etc/cron.d/espn4cc`
- Ensure cron.d file has `root:root 0644` so Debian cron honors it
- Daily 02:00 refresh + weekly VACUUM included by default
- Health/sanity checks retained (GET-only), no proxies
## v3.97 — 2025-10-31
- Ops: bind-mount cron schedule into container under `/etc/cron.d/espn4cc`
- Ensure cron.d file has `root:root 0644` so Debian cron honors it
- Daily 02:00 refresh + weekly VACUUM included by default
- Health/sanity checks retained (GET-only), no proxies
