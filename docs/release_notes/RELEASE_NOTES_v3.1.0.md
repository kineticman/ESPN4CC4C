## ESPN4CC4C v3.1.0

- Fresh-install guardrails (no /app paths on host)
- Bootstrap/update scripts: health-gated first run + ingest-if-empty
- DB migrator v3 (TEXT PKs, sticky map fix), container-side only
- First-run sanity summary & first non-placeholder title
- Install summary printed (XMLTV/M3U URLs)

**Endpoints for Channels DVR**
- XMLTV: `http://<LAN-IP>:8094/out/epg.xml`
- M3U:   `http://<LAN-IP>:8094/out/playlist.m3u`
