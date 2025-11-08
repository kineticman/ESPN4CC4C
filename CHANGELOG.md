# Changelog

## v4.0.3 — 2025-11-07
- Windows: bootstrap pinned to script directory; writes .env to repo; robust M3U fetch (tries /out first, validates #EXTM3U, hard-fails on error).
- Tools: add/improve vc_diag (resolver health, lane audit, DB/XML cross-checks, helpful suggestions).
- Housekeeping: GET-only checks, prefer /out/* endpoints, no proxies for ESPN endpoints.


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
