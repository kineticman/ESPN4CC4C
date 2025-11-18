## ESPN4CC4C v4.0.2

**Highlights**
- Short deeplink by default for `/whatson` and `/whatson_all` when `include=deeplink`.
- Full deeplink (`playID:feedID`) via `include=deeplink_full`.
- TXT modes:
  - `?format=txt` → **play_id** only (legacy).
  - `?param=deeplink_url&format=txt` → short deeplink.
  - `?param=deeplink_url_full&format=txt` → full deeplink.
- New **/channels_db** endpoint (DB-backed list). **/channels** remains XMLTV-backed.
- Docs added: `docs/api/whatson_api_doc.md`.

**Fixes & hardening**
- Restored `docker-entrypoint.sh` in build context.
- Hardened `windowsbootstrap.ps1` pathing + health checks (GET-only).
- Bootstrap seeds `.env` from `.env.example` if missing.

**Endpoints quick ref**
- `GET /whatson/{lane}?include=deeplink|deeplink_full`
- `GET /whatson/{lane}?format=txt`
- `GET /whatson/{lane}?param=deeplink_url[_full]&format=txt`
- `GET /whatson_all?include=deeplink|deeplink_full`
- `GET /channels_db` (DB) and `GET /channels` (XMLTV)

**Notes**
- Keep `.env` in repo root; verify `VC_RESOLVER_BASE_URL`, `CC_HOST`, `CC_PORT`.
- No proxy usage for ESPN endpoints; use GET-only for health/EPG/M3U checks.
